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
from lecturepack.services.export_service import ExportWorker, ExportService

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

class JobController(QObject):
    stage_started = Signal(str)
    stage_progress = Signal(str, int)
    stage_log = Signal(str, str)
    stage_finished = Signal(str, bool, str)
    
    pipeline_completed = Signal()
    pipeline_failed = Signal(str)

    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.ffmpeg_wrapper = FFmpegWrapper(config_manager)
        self.whisper_wrapper = WhisperWrapper()
        
        self.job = None
        self.current_stage = None
        
        # Background worker references
        self.slide_worker = None
        self.align_worker = None
        self.export_worker = None
        self.retranscribe_only = False

        # Connect ffmpeg signals
        self.ffmpeg_wrapper.progress.connect(self._handle_ffmpeg_log)
        self.ffmpeg_wrapper.finished.connect(self._handle_ffmpeg_finished)

        # Connect whisper signals
        self.whisper_wrapper.progress.connect(self._handle_whisper_log)
        self.whisper_wrapper.finished.connect(self._handle_whisper_finished)

    def set_job(self, job):
        self.job = job
        # Sync whisper executable path
        self.whisper_wrapper.whisper_exe_path = self.config_manager.get("whisper_exe", "")

    def cancel(self):
        """Cancels any running stage safely."""
        if not self.current_stage:
            return

        self.stage_log.emit(self.current_stage, "Cancelling stage...\n")
        
        if self.current_stage == STAGE_EXTRACT_AUDIO:
            self.ffmpeg_wrapper.cancel()
        elif self.current_stage == STAGE_TRANSCRIBE:
            self.whisper_wrapper.cancel()
        elif self.current_stage == STAGE_DETECT_SLIDES:
            if self.slide_worker:
                self.slide_worker.cancel()
        elif self.current_stage == STAGE_ALIGN:
            if self.align_worker:
                self.align_worker.terminate()
        elif self.current_stage == STAGE_EXPORT:
            if self.export_worker:
                self.export_worker.terminate()

        self.job.set_stage_status(self.current_stage, "cancelled")
        self.current_stage = None

    def run_pipeline(self):
        """Finds the first incomplete stage and runs it."""
        if not self.job:
            self.pipeline_failed.emit("No job loaded.")
            return

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

    def run_next_stage(self):
        # Find next pending stage
        next_stage = None
        skipped = self._skipped_stages()
        for stage in STAGES:
            # We don't auto-run STAGE_EXPORT during main pipeline, it is triggered after review
            if stage == STAGE_EXPORT:
                continue

            status = self.job.get_stage_status(stage)
            if status == "completed":
                continue

            # Product-mode gating: mark inapplicable stages completed and move on.
            if stage in skipped:
                self.stage_log.emit(stage, f"Skipped for product mode '{self.job.get_product_mode()}'.\n")
                self.job.set_stage_status(stage, "completed")
                self.stage_finished.emit(stage, True, "")
                continue

            next_stage = stage
            break

        if not next_stage:
            # All processing stages completed
            self.current_stage = None
            if self.retranscribe_only:
                self.retranscribe_only = False
                self.export_now()
            else:
                self.pipeline_completed.emit()
            return

        self.current_stage = next_stage
        self.stage_started.emit(next_stage)
        self.job.set_stage_status(next_stage, "running")

        if next_stage == STAGE_INSPECT:
            self._run_inspect()
        elif next_stage == STAGE_EXTRACT_AUDIO:
            self._run_extract_audio()
        elif next_stage == STAGE_TRANSCRIBE:
            self._run_transcribe()
        elif next_stage == STAGE_DETECT_SLIDES:
            self._run_detect_slides()
        elif next_stage == STAGE_ALIGN:
            self._run_align()
        elif next_stage == STAGE_REVIEW_READY:
            self.job.set_stage_status(STAGE_REVIEW_READY, "completed")
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
            self.job.set_stage_status(STAGE_INSPECT, "completed")
            self.stage_finished.emit(STAGE_INSPECT, True, "")
            self.run_next_stage()
        except Exception as e:
            err_msg = str(e)
            self.stage_log.emit(STAGE_INSPECT, f"Inspection failed: {err_msg}\n")
            self.job.set_stage_status(STAGE_INSPECT, "failed", err_msg)
            self.stage_finished.emit(STAGE_INSPECT, False, err_msg)
            self.pipeline_failed.emit(err_msg)

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
            self.job.set_stage_status(STAGE_EXTRACT_AUDIO, "completed")
            self.stage_finished.emit(STAGE_EXTRACT_AUDIO, True, "")
            self.run_next_stage()
        else:
            self.stage_log.emit(STAGE_EXTRACT_AUDIO, f"Audio extraction failed: {error_msg}\n")
            self.job.set_stage_status(STAGE_EXTRACT_AUDIO, "failed", error_msg)
            self.stage_finished.emit(STAGE_EXTRACT_AUDIO, False, error_msg)
            self.pipeline_failed.emit(error_msg)

    def _run_transcribe(self):
        audio_wav = os.path.join(self.job.paths["audio"], "lecture-16khz-mono.wav")
        model_path = self.config_manager.get("whisper_model", "")
        
        # Output file prefix inside job transcript folder
        output_prefix = os.path.join(self.job.paths["transcript"], "raw")
        
        whisper_settings = self.job.settings.get("whisper", {})
        glossary = whisper_settings.get("glossary", "")
        threads = whisper_settings.get("threads", 8)
        
        vad_settings = {
            "enabled": whisper_settings.get("vad_enabled", False),
            "model_path": whisper_settings.get("vad_model", ""),
            "threshold": whisper_settings.get("vad_threshold", 0.50),
            "min_speech_duration_ms": whisper_settings.get("vad_min_speech_duration_ms", 250),
            "min_silence_duration_ms": whisper_settings.get("vad_min_silence_duration_ms", 100)
        }

        self.stage_log.emit(STAGE_TRANSCRIBE, f"Starting transcription using model: {model_path}...\n")
        self.whisper_wrapper.start_transcription(
            audio_wav, model_path, output_prefix,
            glossary=glossary, threads=threads, vad_settings=vad_settings
        )

    def _handle_whisper_log(self, data):
        self.stage_log.emit(STAGE_TRANSCRIBE, data)

    def _handle_whisper_finished(self, success, error_msg):
        if success:
            self.stage_log.emit(STAGE_TRANSCRIBE, "Transcription completed.\n")
            self._build_normalized_transcript()
            self.job.set_stage_status(STAGE_TRANSCRIBE, "completed")
            self.stage_finished.emit(STAGE_TRANSCRIBE, True, "")
            self.run_next_stage()
        else:
            self.stage_log.emit(STAGE_TRANSCRIBE, f"Transcription failed: {error_msg}\n")
            self.job.set_stage_status(STAGE_TRANSCRIBE, "failed", error_msg)
            self.stage_finished.emit(STAGE_TRANSCRIBE, False, error_msg)
            self.pipeline_failed.emit(error_msg)

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

    def _run_detect_slides(self):
        video_path = self.job.manifest["source"]["original_path"]
        crop = self.job.settings["slide_detection"]["crop_region"]
        masks = self.job.settings["slide_detection"]["ignore_masks"]
        preset = self.job.get_preset_settings()

        self.slide_worker = SlideDetectorWorker(video_path, crop, masks, preset, self.job.paths)
        self.slide_worker.progress.connect(lambda p: self.stage_progress.emit(STAGE_DETECT_SLIDES, p))
        self.slide_worker.status_message.connect(lambda m: self.stage_log.emit(STAGE_DETECT_SLIDES, m + "\n"))
        self.slide_worker.finished.connect(self._handle_detect_finished)
        self.slide_worker.start()

    def _handle_detect_finished(self, success, error_msg, candidates):
        if success:
            # Write candidates metadata file
            candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
            from lecturepack.infrastructure.file_manager import FileManager
            FileManager.write_json_atomic(candidates_path, candidates)

            self.stage_log.emit(STAGE_DETECT_SLIDES, "Slide detection completed.\n")
            self.job.set_stage_status(STAGE_DETECT_SLIDES, "completed")
            self.stage_finished.emit(STAGE_DETECT_SLIDES, True, "")
            self.run_next_stage()
        else:
            self.stage_log.emit(STAGE_DETECT_SLIDES, f"Slide detection failed: {error_msg}\n")
            self.job.set_stage_status(STAGE_DETECT_SLIDES, "failed", error_msg)
            self.stage_finished.emit(STAGE_DETECT_SLIDES, False, error_msg)
            self.pipeline_failed.emit(error_msg)

    def _run_align(self):
        self.stage_log.emit(STAGE_ALIGN, "Aligning transcript segments to slides...\n")
        self.align_worker = AlignWorker(self.job)
        self.align_worker.finished.connect(self._handle_align_finished)
        self.align_worker.start()

    def _handle_align_finished(self, success, error_msg):
        if success:
            self.stage_log.emit(STAGE_ALIGN, "Alignment completed.\n")
            self.job.set_stage_status(STAGE_ALIGN, "completed")
            self.stage_finished.emit(STAGE_ALIGN, True, "")
            self.run_next_stage()
        else:
            self.stage_log.emit(STAGE_ALIGN, f"Alignment failed: {error_msg}\n")
            self.job.set_stage_status(STAGE_ALIGN, "failed", error_msg)
            self.stage_finished.emit(STAGE_ALIGN, False, error_msg)
            self.pipeline_failed.emit(error_msg)

    def export_now(self):
        """Manually triggers final exports (Stage 7) from the review view."""
        if not self.job:
            return

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

    def run_retranscribe_only(self):
        """Runs the retranscription workflow, skipping inspection, slide detection, and candidate decisions."""
        if not self.job:
            self.pipeline_failed.emit("No job loaded.")
            return

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
