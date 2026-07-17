import os
from PySide6.QtCore import QObject, Signal, QThread
from lecturepack.constants import (
    STAGE_INSPECT, STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE,
    STAGE_DETECT_SLIDES, STAGE_ALIGN, STAGE_REVIEW_READY, STAGE_EXPORT, STAGES,
    PRODUCT_MODE_STUDY_PACK, PRODUCT_MODE_TRANSCRIPT_ONLY, PRODUCT_MODE_SLIDES_ONLY,
)

# Processing stages that are not applicable to a given product mode. INSPECT,
# ALIGN (which produces the mode-aware exports), REVIEW_READY and EXPORT always
# run; ALIGN degrades gracefully when a side (slides or transcript) is absent.
STAGES_SKIPPED_BY_MODE = {
    PRODUCT_MODE_STUDY_PACK: set(),
    PRODUCT_MODE_TRANSCRIPT_ONLY: {STAGE_DETECT_SLIDES},
    PRODUCT_MODE_SLIDES_ONLY: {STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE},
}
from lecturepack.infrastructure.ffmpeg_wrapper import FFmpegWrapper
from lecturepack.infrastructure.whisper_wrapper import WhisperWrapper
from lecturepack.infrastructure.cv_engine import SlideDetectorWorker
from lecturepack.infrastructure.transcription_engines import (
    EngineRegistry, ENGINE_AUTO,
)
from lecturepack.services.export_service import ExportWorker, ExportService
from lecturepack.services.transcription_backends import (
    BACKEND_LOCAL_WHISPERCPP, BackendRegistry, TranscriptionRequest,
    TranscriptionResult,
)

class AlignWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self):
        try:
            # We run the align step from ExportService
            service = ExportService(self.job)
            service.align_and_export()
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))

# Bump when the detector algorithm changes in a way that invalidates cached
# detection results (part of the detection stage cache key).
DETECTOR_VERSION = "v1.1.0-piped-1"


class JobController(QObject):
    stage_started = Signal(str)
    stage_progress = Signal(str, int)
    stage_log = Signal(str, str)
    stage_finished = Signal(str, bool, str)
    stage_cached = Signal(str)  # stage skipped because its cache key matches
    backend_info = Signal(str)  # human-readable engine/backend line for the status bar

    pipeline_completed = Signal()
    pipeline_failed = Signal(str)

    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.ffmpeg_wrapper = FFmpegWrapper(config_manager)
        self.whisper_wrapper = WhisperWrapper()
        self.engine_registry = EngineRegistry(config_manager)
        self.transcription_backends = BackendRegistry(
            config_manager, self.whisper_wrapper, self.engine_registry)
        self.transcription_backend = None
        self._transcription_request = None
        self._requested_transcription_backend = BACKEND_LOCAL_WHISPERCPP

        self.job = None
        self.current_stage = None

        # Background worker references
        self.slide_worker = None
        self.align_worker = None
        self.export_worker = None
        self.retranscribe_only = False

        # v1.1 parallel scheduler state: transcription and slide detection are
        # independent after audio extraction, so they may run concurrently.
        self._active_stages = set()
        self._group_error = None
        self._cancelling = False
        # Latched by cancel(); prevents a late stage-finished event (e.g. a
        # process that ignored terminate()) from restarting the pipeline.
        self._user_cancelled = False
        # Workers replaced while still winding down are parked here so their
        # QThread objects are never garbage-collected while running.
        self._retired_workers = []

        # Connect ffmpeg signals
        self.ffmpeg_wrapper.progress.connect(self._handle_ffmpeg_log)
        self.ffmpeg_wrapper.finished.connect(self._handle_ffmpeg_finished)

        # Route the existing whisper.cpp wrapper through the provider-neutral
        # adapter. The public wrapper attribute remains for diagnostics/tests.
        local_backend, _ = self.transcription_backends.resolve(
            BACKEND_LOCAL_WHISPERCPP)
        self._set_transcription_backend(local_backend)

    def _set_transcription_backend(self, backend):
        if backend is self.transcription_backend:
            return
        if self.transcription_backend is not None:
            for signal, slot in (
                    (self.transcription_backend.progress, self._handle_whisper_log),
                    (self.transcription_backend.finished, self._handle_transcription_result),
                    (self.transcription_backend.backend_detected,
                     self._handle_backend_detected)):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        self.transcription_backend = backend
        backend.progress.connect(self._handle_whisper_log)
        backend.finished.connect(self._handle_transcription_result)
        backend.backend_detected.connect(self._handle_backend_detected)

    def set_job(self, job):
        self.job = job
        # Sync whisper executable path
        self.whisper_wrapper.whisper_exe_path = self.config_manager.get("whisper_exe", "")
        if job is not None:
            actual = (job.state.get("stages", {}).get(STAGE_TRANSCRIBE, {})
                      .get("backend_used"))
            if actual:
                self.backend_info.emit(f"loaded backend: {actual}")

    def _handle_backend_detected(self, backend):
        """Persist the backend reported by the running whisper binary."""
        if self.job is not None:
            stage = self.job.state.setdefault("stages", {}).setdefault(
                STAGE_TRANSCRIBE, {"status": "running"})
            stage["backend_used"] = backend
            self.job.save()
        self.backend_info.emit(f"loaded backend: {backend}")

    def parallel_enabled(self):
        """Concurrent transcribe+detect. On by default; config can disable."""
        if self.config_manager is None:
            return True
        return bool(self.config_manager.get("parallel_pipeline", True))

    def cancel(self):
        """Cancels any running stage safely (both branches when parallel)."""
        active = set(self._active_stages)
        if self.current_stage and self.current_stage not in active:
            active.add(self.current_stage)
        if not active:
            return

        self._cancelling = True
        self._user_cancelled = True
        for stage in active:
            self.stage_log.emit(stage, "Cancelling stage...\n")
            if stage == STAGE_EXTRACT_AUDIO:
                self.ffmpeg_wrapper.cancel()
            elif stage == STAGE_TRANSCRIBE:
                self.transcription_backend.cancel()
            elif stage == STAGE_DETECT_SLIDES:
                if self.slide_worker:
                    self.slide_worker.cancel()
            elif stage == STAGE_ALIGN:
                if self.align_worker:
                    self.align_worker.terminate()
            elif stage == STAGE_EXPORT:
                if self.export_worker:
                    self.export_worker.terminate()
            self.job.set_stage_status(stage, "cancelled")

        self._active_stages.clear()
        self._group_error = None
        self.current_stage = None
        self._cancelling = False

    def run_pipeline(self):
        """Finds the first incomplete stage and runs it."""
        if not self.job:
            self.pipeline_failed.emit("No job loaded.")
            return

        self._user_cancelled = False
        # Check overall state or reset failed/cancelled stages
        for stage in STAGES:
            status = self.job.get_stage_status(stage)
            if status in ["failed", "cancelled", "interrupted"]:
                self.job.set_stage_status(stage, "pending")

        self.run_next_stage()

    def _skipped_stages(self):
        """Stages that should not run for the current job's product mode."""
        if not self.job:
            return set()
        mode = self.job.get_product_mode()
        return STAGES_SKIPPED_BY_MODE.get(mode, set())

    # ------------------------------------------------------------------ #
    # Stage cache keys (Phase 8). A completed stage is only trusted when its
    # recorded fingerprint still matches the current source + settings.
    # ------------------------------------------------------------------ #
    def _fingerprints_path(self):
        return os.path.join(self.job.paths["root"], "stage_fingerprints.json")

    def _stage_fingerprint(self, stage):
        import hashlib
        import json
        src = self.job.manifest.get("source", {}).get("original_path", "")
        try:
            st = os.stat(src)
            src_sig = [src, st.st_size, int(st.st_mtime)]
        except OSError:
            src_sig = [src, 0, 0]
        w = self.job.settings.get("whisper", {})
        payload = None
        if stage == STAGE_EXTRACT_AUDIO:
            payload = {"src": src_sig}
        elif stage == STAGE_TRANSCRIBE:
            payload = {
                "src": src_sig,
                "model": os.path.basename(w.get("model", "")),
                "engine": w.get("engine", "auto"),
                "glossary": w.get("glossary", ""),
                "language": w.get("language", "en"),
                "vad": [bool(w.get("vad_enabled")),
                        os.path.basename(w.get("vad_model", "")),
                        w.get("vad_threshold"), w.get("vad_min_speech_duration_ms"),
                        w.get("vad_min_silence_duration_ms")],
            }
            # Preserve the exact v1.1/local cache key so existing jobs never
            # retranscribe merely because the provider-neutral default was
            # materialized. Future non-local adapters must be isolated.
            selected_backend = w.get(
                "transcription_backend", BACKEND_LOCAL_WHISPERCPP)
            if selected_backend != BACKEND_LOCAL_WHISPERCPP:
                payload["transcription_backend"] = selected_backend
                # Include the currently resolvable adapter. A run that fell
                # back to local must invalidate if that provider later becomes
                # available, rather than reusing local output under its name.
                effective, _ = self.transcription_backends.resolve(
                    selected_backend)
                payload["effective_transcription_backend"] = \
                    effective.capabilities().key
        elif stage == STAGE_DETECT_SLIDES:
            sd = self.job.settings.get("slide_detection", {})
            payload = {
                "src": src_sig,
                "preset": self.job.settings.get("preset", ""),
                "detector_version": DETECTOR_VERSION,
                "crop": sd.get("crop_region"),
                "masks": sd.get("ignore_masks"),
            }
        if payload is None:
            return None
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _record_stage_fingerprint(self, stage):
        fp = self._stage_fingerprint(stage)
        if fp is None:
            return
        from lecturepack.infrastructure.file_manager import FileManager
        data = FileManager.read_json_safe(self._fingerprints_path(), {}) or {}
        data[stage] = fp
        FileManager.write_json_atomic(self._fingerprints_path(), data)

    def _stage_cache_valid(self, stage):
        """A completed stage stays completed only while its inputs match.
        Jobs from before v1.1 have no recorded fingerprints; they are trusted
        (legacy behaviour) and gain fingerprints on their next run."""
        fp = self._stage_fingerprint(stage)
        if fp is None:
            return True
        from lecturepack.infrastructure.file_manager import FileManager
        data = FileManager.read_json_safe(self._fingerprints_path(), {}) or {}
        recorded = data.get(stage)
        if recorded is None:
            return True
        return recorded == fp

    def run_next_stage(self):
        if self._active_stages:
            return  # a parallel group is still running

        skipped = self._skipped_stages()
        pending = []
        for stage in STAGES:
            # We don't auto-run STAGE_EXPORT during main pipeline, it is triggered after review
            if stage == STAGE_EXPORT:
                continue
            if self.job.get_stage_status(stage) == "completed":
                if self._stage_cache_valid(stage):
                    self.stage_cached.emit(stage)
                    continue
                # Inputs changed since this stage last ran -- invalidate it.
                self.stage_log.emit(
                    stage, "Settings or source changed since the last run; re-running stage.\n")
                self.job.set_stage_status(stage, "pending")
            # Product-mode gating: mark inapplicable stages completed and move on.
            if stage in skipped:
                self.stage_log.emit(stage, f"Skipped for product mode '{self.job.get_product_mode()}'.\n")
                self.job.set_stage_status(stage, "completed")
                self.stage_finished.emit(stage, True, "")
                continue
            pending.append(stage)

        if not pending:
            # All processing stages completed
            self.current_stage = None
            if self.retranscribe_only:
                self.retranscribe_only = False
                self.export_now()
            else:
                self.pipeline_completed.emit()
            return

        next_stage = pending[0]

        # Parallel group: transcription and slide detection are independent
        # once audio has been extracted. Run them concurrently so total time
        # trends toward the slower branch instead of the sum.
        group = [next_stage]
        if (self.parallel_enabled()
                and next_stage in (STAGE_TRANSCRIBE, STAGE_DETECT_SLIDES)):
            for sibling in (STAGE_TRANSCRIBE, STAGE_DETECT_SLIDES):
                if sibling != next_stage and sibling in pending:
                    group.append(sibling)

        self._group_error = None
        self.current_stage = group[0]
        for stage in group:
            self._active_stages.add(stage)
            self.stage_started.emit(stage)
            self.job.set_stage_status(stage, "running")
        if len(group) > 1:
            self.stage_log.emit(group[0],
                                f"Running {' + '.join(group)} concurrently.\n")

        for stage in group:
            if stage == STAGE_INSPECT:
                self._run_inspect()
            elif stage == STAGE_EXTRACT_AUDIO:
                self._run_extract_audio()
            elif stage == STAGE_TRANSCRIBE:
                self._run_transcribe(parallel=len(group) > 1)
            elif stage == STAGE_DETECT_SLIDES:
                self._run_detect_slides(parallel=len(group) > 1)
            elif stage == STAGE_ALIGN:
                self._run_align()
            elif stage == STAGE_REVIEW_READY:
                self._stage_done(STAGE_REVIEW_READY, True, "")

    def _stage_done(self, stage, success, error_msg):
        """Common completion path for every stage; drives the parallel group."""
        if self._cancelling:
            return
        if self._user_cancelled:
            # A worker finished after the user cancelled (Windows console
            # processes can ignore terminate()); never resume the pipeline.
            self._active_stages.discard(stage)
            if self.job is not None and self.job.get_stage_status(stage) != "cancelled":
                self.job.set_stage_status(stage, "cancelled")
            return
        self._active_stages.discard(stage)
        if stage == self.current_stage:
            self.current_stage = next(iter(self._active_stages), None)

        if success:
            self.job.set_stage_status(stage, "completed")
            self._record_stage_fingerprint(stage)
            self.stage_finished.emit(stage, True, "")
        else:
            self.job.set_stage_status(stage, "failed", error_msg)
            self.stage_finished.emit(stage, False, error_msg)
            if self._group_error is None:
                self._group_error = f"{stage}: {error_msg}" if error_msg else stage
            # Stop the sibling branch cleanly.
            for other in list(self._active_stages):
                self.stage_log.emit(other, "Stopping due to failure in sibling stage...\n")
                if other == STAGE_TRANSCRIBE:
                    self.transcription_backend.cancel()
                elif other == STAGE_DETECT_SLIDES and self.slide_worker:
                    self.slide_worker.cancel()

        if self._active_stages:
            return  # wait for the sibling to finish/cancel

        if self._group_error is not None:
            err = self._group_error
            self._group_error = None
            self.pipeline_failed.emit(err)
            return

        self.run_next_stage()

    def _run_inspect(self):
        self.stage_log.emit(STAGE_INSPECT, "Starting video inspection...\n")
        try:
            video_path = self.job.manifest["source"]["original_path"]
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")

            metadata = self.ffmpeg_wrapper.inspect_video(video_path)
            self.job.source.update(metadata)
            self.job.save()

            self.stage_log.emit(STAGE_INSPECT, f"Inspection completed. Metadata: {metadata}\n")
            self._stage_done(STAGE_INSPECT, True, "")
        except Exception as e:
            self.stage_log.emit(STAGE_INSPECT, f"Inspection failed: {e}\n")
            self._stage_done(STAGE_INSPECT, False, str(e))

    def _run_extract_audio(self):
        video_path = self.job.manifest["source"]["original_path"]
        output_wav = os.path.join(self.job.paths["audio"], "lecture-16khz-mono.wav")
        self.stage_log.emit(STAGE_EXTRACT_AUDIO, f"Extracting audio from {video_path} to {output_wav}...\n")
        self.ffmpeg_wrapper.start_audio_extraction(video_path, output_wav)

    def _handle_ffmpeg_log(self, data):
        self.stage_log.emit(STAGE_EXTRACT_AUDIO, data)

    def _handle_ffmpeg_finished(self, success, error_msg):
        if success:
            self.stage_log.emit(STAGE_EXTRACT_AUDIO, "Audio extraction completed.\n")
        else:
            self.stage_log.emit(STAGE_EXTRACT_AUDIO, f"Audio extraction failed: {error_msg}\n")
        self._stage_done(STAGE_EXTRACT_AUDIO, success, error_msg)

    def _run_transcribe(self, parallel=False):
        audio_wav = os.path.join(self.job.paths["audio"], "lecture-16khz-mono.wav")

        whisper_settings = self.job.settings.get("whisper", {})
        requested_backend = whisper_settings.get(
            "transcription_backend", BACKEND_LOCAL_WHISPERCPP)
        self._requested_transcription_backend = requested_backend
        backend, backend_reason = self.transcription_backends.resolve(
            requested_backend)
        self._set_transcription_backend(backend)
        requested_engine = whisper_settings.get("engine", ENGINE_AUTO)
        engine = self.engine_registry.resolve(requested_engine) \
            if backend.capabilities().is_local else None

        model_path = self.config_manager.get("whisper_model", "")
        if whisper_settings.get("model") and os.path.isfile(whisper_settings.get("model", "")):
            model_path = whisper_settings["model"]

        # Output file prefix inside job transcript folder
        output_prefix = os.path.join(self.job.paths["transcript"], "raw")

        glossary = whisper_settings.get("glossary", "")
        threads = whisper_settings.get("threads", 8)

        vad_settings = {
            "enabled": whisper_settings.get("vad_enabled", False),
            "model_path": whisper_settings.get("vad_model", ""),
            "threshold": whisper_settings.get("vad_threshold", 0.50),
            "min_speech_duration_ms": whisper_settings.get("vad_min_speech_duration_ms", 250),
            "min_silence_duration_ms": whisper_settings.get("vad_min_silence_duration_ms", 100)
        }

        backend_label = backend.capabilities().label
        self.stage_log.emit(
            STAGE_TRANSCRIBE,
            f"Transcription backend: {backend_label} ({backend_reason})\n"
            + (f"Engine: {engine.label} ({engine.reason or 'default'})\n" if engine else "")
            + f"Starting transcription using model: {model_path}...\n")
        self.backend_info.emit(
            f"engine: {engine.key}" if engine else f"backend: {requested_backend}")
        self._transcription_request = TranscriptionRequest(
            audio_path=audio_wav, output_prefix=output_prefix,
            model=model_path, language=whisper_settings.get("language", "en"),
            prompt=glossary, threads=threads, vad=vad_settings,
            local_engine=requested_engine, job_id=self.job.job_id,
            source_duration_seconds=float(self.job.source.get("duration", 0.0) or 0.0))
        backend.start(self._transcription_request)

    def _handle_whisper_log(self, data):
        self.stage_log.emit(STAGE_TRANSCRIBE, data)

    def _handle_whisper_finished(self, success, error_msg):
        """Backward-compatible entry point for older tests/tools."""
        self._handle_transcription_result(TranscriptionResult(
            success=bool(success), backend_key=BACKEND_LOCAL_WHISPERCPP,
            provider="whisper.cpp", error_code="" if success else "local_process_failed",
            error_message=error_msg or "", retryable=not success,
            fallback_allowed=False))

    def _handle_transcription_result(self, result):
        if not isinstance(result, TranscriptionResult):
            result = TranscriptionResult(
                success=False, backend_key=BACKEND_LOCAL_WHISPERCPP,
                provider="unknown", error_code="invalid_backend_result",
                error_message="Transcription backend returned an invalid result.")
        if self.job is not None:
            stage = self.job.state.setdefault("stages", {}).setdefault(
                STAGE_TRANSCRIBE, {"status": "running"})
            stage["transcription_backend"] = result.backend_key
            stage["transcription_backend_requested"] = \
                self._requested_transcription_backend
            stage["transcription_provider"] = result.provider
            if result.engine_key:
                stage["engine_used"] = result.engine_key
            if result.actual_backend:
                stage["backend_used"] = result.actual_backend
            self.job.save()
        if result.success:
            self.stage_log.emit(STAGE_TRANSCRIBE, "Transcription completed.\n")
            self._build_normalized_transcript()
        else:
            self.stage_log.emit(
                STAGE_TRANSCRIBE,
                f"Transcription failed ({result.error_code or 'unknown'}): "
                f"{result.error_message}\n")
        self._stage_done(
            STAGE_TRANSCRIBE, result.success, result.error_message)

    def _build_normalized_transcript(self):
        """Layer the raw whisper.cpp output into the deterministic normalized
        transcript (services.transcript_service) and write the auditable
        artifacts. The raw layer is never modified. Failures here never fail the
        pipeline -- the raw transcript remains the source of truth."""
        try:
            import json
            from lecturepack.services import transcript_service as ts
            from lecturepack.infrastructure.file_manager import FileManager

            transcript_dir = self.job.paths["transcript"]
            raw_path = os.path.join(transcript_dir, "raw.json")
            if not os.path.exists(raw_path):
                self.stage_log.emit(STAGE_TRANSCRIBE, "Normalization skipped: raw.json not found.\n")
                return

            with open(raw_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            filename = self.job.manifest.get("source", {}).get("filename", "")
            raw = ts.parse_raw_whisper_json(data, meta={"source": filename, "job_id": self.job.job_id})
            norm = ts.normalize_transcript(raw)

            FileManager.write_json_atomic(
                os.path.join(transcript_dir, "normalized.json"), norm.to_dict())

            candidates = ts.propose_entity_candidates(norm, filename=filename)
            FileManager.write_json_atomic(
                os.path.join(transcript_dir, "context_candidates.json"),
                [c.to_dict() for c in candidates])

            self.stage_log.emit(
                STAGE_TRANSCRIBE,
                f"Normalized transcript: {len(raw.segments)} raw -> {len(norm.segments)} "
                f"segments, {len(norm.paragraphs)} paragraphs, "
                f"{len(candidates)} context candidates (raw hash {raw.content_hash()[:12]}).\n")
        except Exception as e:
            # Never let the optional layer break the pipeline.
            self.stage_log.emit(STAGE_TRANSCRIBE, f"Normalization skipped: {e}\n")

    def _run_detect_slides(self, parallel=False):
        # Never let a still-running worker be replaced (and garbage-collected
        # mid-run): retire it and keep a reference until its thread exits.
        if self.slide_worker is not None and self.slide_worker.isRunning():
            self.slide_worker.cancel()
            try:
                self.slide_worker.finished.disconnect(self._handle_detect_finished)
            except Exception:
                pass
            self._retired_workers.append(self.slide_worker)
            self.slide_worker.finished.connect(
                lambda *_a, w=self.slide_worker: self._reap_retired(w))
        self._retired_workers = [w for w in self._retired_workers if w.isRunning()]

        video_path = self.job.manifest["source"]["original_path"]
        crop = self.job.settings["slide_detection"]["crop_region"]
        masks = self.job.settings["slide_detection"]["ignore_masks"]
        preset = self.job.get_preset_settings()

        # Bound FFmpeg decode threads while whisper saturates the CPU; the
        # analysis decode is rarely the bottleneck of the detection branch.
        decode_threads = 2 if parallel else 0

        self.slide_worker = SlideDetectorWorker(
            video_path, crop, masks, preset, self.job.paths,
            ffmpeg_path=self.ffmpeg_wrapper.ffmpeg_path or None,
            decode_threads=decode_threads)
        self.slide_worker.progress.connect(lambda p: self.stage_progress.emit(STAGE_DETECT_SLIDES, p))
        self.slide_worker.status_message.connect(lambda m: self.stage_log.emit(STAGE_DETECT_SLIDES, m + "\n"))
        self.slide_worker.finished.connect(self._handle_detect_finished)
        self.slide_worker.start()

    def _reap_retired(self, worker):
        """Drop a retired detector worker once its thread has fully exited."""
        worker.wait(100)
        self._retired_workers = [w for w in self._retired_workers
                                 if w is not worker and w.isRunning()]

    def _handle_detect_finished(self, success, error_msg, candidates):
        if success:
            # Write candidates metadata file
            candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
            from lecturepack.infrastructure.file_manager import FileManager
            FileManager.write_json_atomic(candidates_path, candidates)
            self.stage_log.emit(STAGE_DETECT_SLIDES, "Slide detection completed.\n")
            if self.slide_worker is not None and self.slide_worker.decode_path_used:
                self.backend_info.emit(
                    f"detector decode: {self.slide_worker.decode_path_used}")
        else:
            self.stage_log.emit(STAGE_DETECT_SLIDES, f"Slide detection failed: {error_msg}\n")
        self._stage_done(STAGE_DETECT_SLIDES, success, error_msg)

    def _run_align(self):
        self.stage_log.emit(STAGE_ALIGN, "Aligning transcript segments to slides...\n")
        self.align_worker = AlignWorker(self.job)
        self.align_worker.finished.connect(self._handle_align_finished)
        self.align_worker.start()

    def _handle_align_finished(self, success, error_msg):
        if success:
            self.stage_log.emit(STAGE_ALIGN, "Alignment completed.\n")
        else:
            self.stage_log.emit(STAGE_ALIGN, f"Alignment failed: {error_msg}\n")
        self._stage_done(STAGE_ALIGN, success, error_msg)

    def export_now(self):
        """Manually triggers final exports (Stage 7) from the review view."""
        if not self.job:
            return

        self._user_cancelled = False
        self.current_stage = STAGE_EXPORT
        self.stage_started.emit(STAGE_EXPORT)
        self.job.set_stage_status(STAGE_EXPORT, "running")

        self.export_worker = ExportWorker(self.job)
        self.export_worker.progress.connect(lambda p: self.stage_progress.emit(STAGE_EXPORT, p))
        self.export_worker.status_message.connect(lambda m: self.stage_log.emit(STAGE_EXPORT, m + "\n"))
        self.export_worker.finished.connect(self._handle_export_finished)
        self.export_worker.start()

    def _handle_export_finished(self, success, error_msg):
        if success:
            self.stage_log.emit(STAGE_EXPORT, "Exports generated successfully.\n")
            self.job.set_stage_status(STAGE_EXPORT, "completed")
            self.stage_finished.emit(STAGE_EXPORT, True, "")
        else:
            self.stage_log.emit(STAGE_EXPORT, f"Export generation failed: {error_msg}\n")
            self.job.set_stage_status(STAGE_EXPORT, "failed", error_msg)
            self.stage_finished.emit(STAGE_EXPORT, False, error_msg)
        self.current_stage = None

    def run_retranscribe_only(self):
        """Runs the retranscription workflow, skipping inspection, slide detection, and candidate decisions."""
        if not self.job:
            self.pipeline_failed.emit("No job loaded.")
            return

        self._user_cancelled = False
        self.retranscribe_only = True

        # Set stages status:
        self.job.set_stage_status(STAGE_INSPECT, "completed")

        # Check audio WAV file validity (exists and not empty)
        audio_path = os.path.join(self.job.paths["audio"], "lecture-16khz-mono.wav")
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
            self.job.set_stage_status(STAGE_EXTRACT_AUDIO, "completed")
        else:
            self.job.set_stage_status(STAGE_EXTRACT_AUDIO, "pending")

        self.job.set_stage_status(STAGE_TRANSCRIBE, "pending")
        self.job.set_stage_status(STAGE_DETECT_SLIDES, "completed")
        self.job.set_stage_status(STAGE_ALIGN, "pending")
        self.job.set_stage_status(STAGE_REVIEW_READY, "completed")
        self.job.set_stage_status(STAGE_EXPORT, "pending")

        # Make sure settings are clean on start
        for s in STAGES:
            status = self.job.get_stage_status(s)
            if status in ["failed", "cancelled", "interrupted"]:
                self.job.set_stage_status(s, "pending")

        self.run_next_stage()
