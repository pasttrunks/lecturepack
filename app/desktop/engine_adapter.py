"""Adapter between the UI bridge and the LecturePack engine.

THIS IS THE INTEGRATION SEAM. The existing engine (transcription, slide
detection, alignment, exports, local AI) plugs in here — nothing else in
desktop/ or ui/ needs to change.

Three adapters live here:

- EngineAdapter — the interface, with docstrings describing exactly what each
  method must do and which Backend signals it must emit.
- DemoAdapter   — a self-contained simulation (same demo content as the design
  prototype) so the shell runs and every screen is exercisable before the real
  engine is wired. It doubles as living documentation of the signal payloads.
- LecturePackAdapter — drives the real `lecturepack` engine (JobController,
  transcript/study services, exports, local Ollama AI). Returned by
  make_adapter().
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QFileDialog

from .assets import asset_url
from .paths import data_dir


class EngineAdapter(QObject):
    """Interface the desktop shell expects. All signal emission goes through
    self.backend (a Backend instance); payloads are JSON strings."""

    def __init__(self, backend):
        super().__init__()
        self.backend = backend

    # -- lifecycle -----------------------------------------------------------
    def on_ui_ready(self):
        """Push initial state: jobs_changed, status_changed, slides_changed,
        transcript_changed, study_changed, settings_changed, ai_status."""
        raise NotImplementedError

    def on_setting_changed(self, key: str, value: str):
        """Persisted already by Backend; react if the engine cares (theme is
        UI-only, model paths and endpoints belong to the engine)."""

    # -- import / processing --------------------------------------------------
    def browse_video(self, parent) -> None:
        """Open a native file dialog; on selection call self.import_video(path)."""
        raise NotImplementedError

    def import_video(self, path: str) -> None:
        """Probe the file (resolution/duration/codec/size) and drive the UI's
        New-job overlay via status/log signals, then wait for start_processing."""
        raise NotImplementedError

    def open_job(self, job_id: str) -> None:
        """Open an existing job from the Home grid; push its review/study data."""

    def notify_drag_over(self):
        """Optional: UI feedback while a file is dragged over the window."""

    def start_processing(self, mode: str) -> None:
        """Kick off the engine pipeline for the pending import. Emit
        pipeline_changed (stages/title/meta), log_line per engine log,
        status_changed for the footer, jobs_changed when the job list moves."""
        raise NotImplementedError

    def cancel_job(self) -> None:
        raise NotImplementedError

    # -- review ---------------------------------------------------------------
    def set_slide_state(self, index: int, state: str) -> None:
        """Persist accept/reject for a detected slide."""
        raise NotImplementedError

    def save_corrections(self, texts: list[str]) -> None:
        """Persist edited transcript segments for the current selection."""
        raise NotImplementedError

    def repair_selection(self) -> None:
        """Run the engine's context-repair on the selected segments."""
        raise NotImplementedError

    # -- study AI --------------------------------------------------------------
    def ask_ai(self, prompt: str) -> None:
        """Stream an answer: emit ai_token(accumulated_text) repeatedly, then
        ai_done(). Wire to the engine's local AI (Ollama endpoint) here."""
        raise NotImplementedError

    # -- exports ----------------------------------------------------------------
    def export_all(self, formats: list[str]) -> None:
        """Emit export_progress({pct,label}) during the run and
        export_done({files:[names], meta:'5 files · 42.6 MB · 3.2s'}) at the end."""
        raise NotImplementedError

    def export_one(self, kind: str) -> None:
        """kind is 'pdf' or 'html'."""
        raise NotImplementedError

    def export_folder(self) -> str | None:
        return None

    # -- misc -------------------------------------------------------------------
    def test_endpoint(self) -> None:
        """Ping the local AI endpoint; emit ai_status({label, model})."""

    def list_ollama_models(self) -> None:
        """List installed Ollama models; emit ollama_models({models, selected})."""

    def browse_model(self, parent) -> None:
        """Pick a whisper model file; emit settings_changed({model_path})."""

    def save_project(self) -> None:
        """Persist current job state."""


class DemoAdapter(EngineAdapter):
    """Runs the UI with the design prototype's demo behavior. No engine needed."""

    def on_ui_ready(self):
        self.backend.settings_changed.emit(
            json.dumps({"export_dir": os.path.join("~", "LecturePackData", "…", "exports")})
        )

    def browse_video(self, parent):
        path, _ = QFileDialog.getOpenFileName(
            parent,
            "Choose a lecture video",
            os.path.expanduser("~"),
            "Video files (*.mp4 *.mkv *.mov *.m4v *.webm)",
        )
        if path:
            self.import_video(path)

    def import_video(self, path: str):
        size_mb = os.path.getsize(path) / 1e6 if os.path.exists(path) else 0
        self.backend.log_line.emit(
            json.dumps(
                {
                    "tag": "[import]",
                    "color": "var(--blue-ink)",
                    "text": f"{os.path.basename(path)} · {size_mb:.1f} MB",
                }
            )
        )

    def start_processing(self, mode: str):
        self.backend.status_changed.emit(
            json.dumps({"label": "Transcribing", "pct": 0, "detail": "0% · starting", "side": "Transcribing 0%"})
        )

    def cancel_job(self):
        self.backend.status_changed.emit(
            json.dumps({"label": "Cancelled", "pct": 0, "detail": "job cancelled"})
        )

    def set_slide_state(self, index: int, state: str):
        pass  # demo state lives in the UI

    def save_corrections(self, texts):
        self.backend.log_line.emit(
            json.dumps({"tag": "[save]", "color": "var(--green)", "text": f"{len(texts)} segments saved"})
        )

    def repair_selection(self):
        pass

    def ask_ai(self, prompt: str):
        full = (
            "Great question. Based on the transcript around 00:55, the base sits level "
            "to under two centimeters and the sides align to true north within 3/60 of "
            "a degree — remarkable precision for 2560 BC."
        )
        self._chunks = [full[:i] for i in range(2, len(full) + 2, 2)]
        self._timer = QTimer(self)
        self._timer.setInterval(22)

        def step():
            if self._chunks:
                self.backend.ai_token.emit(self._chunks.pop(0))
            else:
                self._timer.stop()
                self.backend.ai_done.emit()

        self._timer.timeout.connect(step)
        QTimer.singleShot(320, self._timer.start)

    def export_all(self, formats):
        files = ["slides.pdf", "study_pack.html"] + [f"transcript.{f.lower()}" for f in formats]
        steps = [(20, "1 of %d · rendering slides PDF"), (45, "2 of %d · building HTML pack"),
                 (70, "3 of %d · writing transcripts"), (90, "4 of %d · finishing up")]
        total = len(files)
        self._export_i = 0

        def tick():
            if self._export_i < len(steps):
                pct, label = steps[self._export_i]
                self.backend.export_progress.emit(json.dumps({"pct": pct, "label": label % total}))
                self._export_i += 1
                QTimer.singleShot(420, tick)
            else:
                self.backend.export_done.emit(
                    json.dumps({"files": files, "meta": f"{total} files · 42.6 MB · 3.2s"})
                )

        QTimer.singleShot(200, tick)

    def export_one(self, kind: str):
        self.export_all(["txt"] if kind == "pdf" else ["md"])

    def export_folder(self):
        return data_dir()


# ===========================================================================
#  Real engine adapter
# ===========================================================================

# Deferred engine imports (kept lazy so the shell can boot even if the engine
# package has an import-time problem — make_adapter() falls back to DemoAdapter).
import sys
import threading
import time

# The engine package (`lecturepack`) lives at the repository root, one level
# above app/. When run from source it is not on sys.path; add it. When frozen
# by PyInstaller the package is bundled and already importable, so this is a
# harmless no-op.
from .paths import app_root as _app_root
_repo_root = os.path.dirname(_app_root())
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from lecturepack import constants
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.services import study_service, transcript_store
from lecturepack.services import study_assistant_service as sas
from lecturepack.services.export_service import ExportWorker


_MODE_MAP = {
    "study": constants.PRODUCT_MODE_STUDY_PACK,
    "transcript": constants.PRODUCT_MODE_TRANSCRIPT_ONLY,
    "slides": constants.PRODUCT_MODE_SLIDES_ONLY,
}

# Engine stage name -> (display label, active-bar color)
_STAGE_META = [
    (constants.STAGE_INSPECT, "Inspect", "orange"),
    (constants.STAGE_EXTRACT_AUDIO, "Extract audio", "green"),
    (constants.STAGE_TRANSCRIBE, "Transcribe", "orange"),
    (constants.STAGE_DETECT_SLIDES, "Detect slides", "blue"),
    (constants.STAGE_ALIGN, "Align", "orange"),
    (constants.STAGE_REVIEW_READY, "Review ready", "orange"),
]

_LOG_COLORS = {
    "inspect": "var(--muted)",
    "extract": "var(--green)",
    "audio": "var(--green)",
    "whisper": "var(--orange-ink)",
    "transcribe": "var(--orange-ink)",
    "t": "var(--ink)",
    "detect": "var(--blue-ink)",
    "slides": "var(--blue-ink)",
    "align": "var(--ink)",
    "export": "var(--ink)",
    "engine": "var(--blue-ink)",
    "error": "var(--red)",
}


def _fmt_hhmmss(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_mmss(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def _fmt_mmss_d(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:04.1f}"


def _human_size(num_bytes: float) -> str:
    num = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


def _esc(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class LecturePackAdapter(EngineAdapter):
    """Drives the real LecturePack engine behind the web UI."""

    def __init__(self, backend):
        super().__init__(backend)
        self.config = ConfigManager()
        self.controller = JobController(self.config)
        self.current_job: Job | None = None
        self._pending_job: Job | None = None
        self._stages: list[dict] = []
        self._pipeline_start = 0.0
        self._slide_frames: list[int] = []      # emit-order -> candidate frame_number
        self._review_ids: list[int] = []        # emit-order -> working segment id
        self._chat_history: list[dict] = []
        self._ai_worker = None
        self._repair_worker = None
        self._export_worker = None
        self._export_start = 0.0
        self._wire_controller()

    # ------------------------------------------------------------------ wiring
    def _wire_controller(self):
        c = self.controller
        c.stage_started.connect(self._on_stage_started)
        c.stage_progress.connect(self._on_stage_progress)
        c.stage_log.connect(self._on_stage_log)
        c.stage_finished.connect(self._on_stage_finished)
        c.stage_cached.connect(self._on_stage_cached)
        c.backend_info.connect(self._on_backend_info)
        c.transcript_segment.connect(self._on_transcript_segment)
        c.pipeline_completed.connect(self._on_pipeline_completed)
        c.pipeline_failed.connect(self._on_pipeline_failed)

    # ------------------------------------------------------------------ helpers
    def _ollama_settings(self) -> dict:
        return dict(self.config.get("ollama", {}) or {})

    def _emit(self, signal, payload):
        getattr(self.backend, signal).emit(
            payload if isinstance(payload, str) else json.dumps(payload))

    def _log(self, tag: str, text: str, key: str = ""):
        color = _LOG_COLORS.get(key or tag.strip("[]").lower(), "var(--ink)")
        for line in str(text).splitlines():
            line = line.strip()
            if line:
                self._emit("log_line", {"tag": tag, "color": color, "text": line})

    def _list_jobs(self) -> list[dict]:
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        rows = []
        if not os.path.isdir(jobs_dir):
            return rows
        entries = []
        for job_id in os.listdir(jobs_dir):
            manifest_p = os.path.join(jobs_dir, job_id, "manifest.json")
            man = FileManager.read_json_safe(manifest_p, None)
            if not isinstance(man, dict):
                continue
            state = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "state.json"), {}) or {}
            source = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "source.json"), {}) or {}
            entries.append((man.get("created_at", ""), job_id, man, state, source))
        entries.sort(reverse=True)
        for created_at, job_id, man, state, source in entries:
            title = man.get("title") or job_id[:8]
            filename = man.get("source", {}).get("filename", "")
            overall = state.get("overall_status", "pending")
            stages = state.get("stages", {})
            running_stage = next(
                (name for name, sd in stages.items()
                 if sd.get("status") == "running"), None)
            if running_stage:
                rows.append({
                    "id": job_id,
                    "name": title, "status": "running",
                    "stage": running_stage, "pct": 0, "eta": "",
                })
            else:
                dur = float(source.get("duration", 0.0) or 0.0)
                candidates = FileManager.read_json_safe(
                    os.path.join(jobs_dir, job_id, "candidates.json"), []) or []
                n_slides = sum(1 for c in candidates if c.get("decision") == "accepted")
                bits = []
                if dur:
                    bits.append(_fmt_mmss(dur))
                if candidates:
                    bits.append(f"{n_slides} slides")
                date = (man.get("created_at", "") or "")[:10]
                if date:
                    bits.append(date)
                done = stages.get(constants.STAGE_REVIEW_READY, {}).get("status") == "completed"
                rows.append({
                    "id": job_id,
                    "name": title, "file": filename,
                    "meta": "  ·  ".join(bits),
                    "status": "done" if (done or overall == "completed") else "pending",
                })
        return rows

    def _push_jobs(self):
        self._emit("jobs_changed", self._list_jobs())

    # ------------------------------------------------------------------ lifecycle
    def on_ui_ready(self):
        # Settings fields.
        self._emit("settings_changed", self._settings_payload())
        self._push_jobs()
        self._probe_ollama_async()
        # Show the most recent completed job's data so Review/Transcript/Study
        # aren't empty on launch.
        self._load_latest_completed_job()

    def _settings_payload(self) -> dict:
        """Current engine-config values the Settings screen reflects."""
        o = self._ollama_settings()
        return {
            "version": self._app_version(),
            "model_path": self.config.get("whisper_model", "") or "(not set)",
            "endpoint": o.get("base_url") or "http://localhost:11434",
            "engine": self.config.get("engine", "auto"),
            "ollama_model": o.get("model", ""),
            "export_dir": self.config.data_dir,
        }

    def on_setting_changed(self, key: str, value: str):
        """Bridge UI setting changes into the engine's ConfigManager.

        The Backend persists every setting in QSettings (UI state), but the
        engine reads its own config.json — so without this bridge the compute
        engine, endpoint, model path and Ollama model chosen in Settings never
        reach processing/AI. ``theme`` is intentionally UI-only.
        """
        if key == "theme":
            return
        if key == "engine":
            engine = value if value in ("auto", "cpu", "vulkan") else "auto"
            self.config.set("engine", engine)
            self._log("[engine]", f"compute engine set to {engine}", "engine")
        elif key == "whisper_model":
            self.config.set("whisper_model", value)
        elif key == "ollama_base_url":
            o = dict(self.config.get("ollama", {}) or {})
            o["base_url"] = value
            self.config.set("ollama", o)
        elif key == "ollama_model":
            o = dict(self.config.get("ollama", {}) or {})
            o["model"] = value
            self.config.set("ollama", o)
            self._log("[ai]", f"study/repair model set to {value}", "ai")
        # Re-emit so the UI reflects the persisted value.
        self._emit("settings_changed", self._settings_payload())

    def _app_version(self) -> str:
        try:
            from . import version
            return version.__version__
        except Exception:
            return "1.2.0"

    def _load_latest_completed_job(self):
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        if not os.path.isdir(jobs_dir):
            return
        best = None
        for job_id in os.listdir(jobs_dir):
            state = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "state.json"), {}) or {}
            stages = state.get("stages", {})
            if stages.get(constants.STAGE_REVIEW_READY, {}).get("status") == "completed":
                man = FileManager.read_json_safe(
                    os.path.join(jobs_dir, job_id, "manifest.json"), {}) or {}
                key = man.get("created_at", "")
                if best is None or key > best[0]:
                    best = (key, job_id)
        if best:
            try:
                self.current_job = Job(self.config.data_dir, job_id=best[1])
                self._push_review_data()
                self._push_study_data()
            except Exception:
                self.current_job = None

    def open_job(self, job_id: str):
        """Open a completed job from the Home grid: load it and push its review /
        study data so Review/Transcript/Study reflect the selection."""
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        if not job_id or not os.path.isdir(os.path.join(jobs_dir, job_id)):
            self._log("[error]", f"job not found: {job_id}", "error")
            return
        try:
            self.current_job = Job(self.config.data_dir, job_id=job_id)
        except Exception as exc:
            self._log("[error]", f"failed to open job: {exc}", "error")
            return
        self._push_review_data()
        self._push_study_data()
        self._log("[review]", f"opened job {self.current_job.manifest.get('title', job_id)}", "detect")

    # ------------------------------------------------------------------ import
    def browse_video(self, parent):
        path, _ = QFileDialog.getOpenFileName(
            parent, "Choose a lecture video", os.path.expanduser("~"),
            "Video files (*.mp4 *.mkv *.mov *.m4v *.webm);;All files (*.*)")
        if path:
            self.import_video(path)

    def import_video(self, path: str):
        if not os.path.exists(path):
            return
        try:
            job = Job(self.config.data_dir, video_path=path)
            self.controller.set_job(job)
            self._pending_job = job
            self.current_job = job
            meta_str = f"{_human_size(os.path.getsize(path))}"
            try:
                self.controller.ffmpeg_wrapper.detect_binaries()
                meta = self.controller.ffmpeg_wrapper.inspect_video(path)
                job.source.update(meta)
                job.save()
                meta_str = (f"{meta['width']}×{meta['height']} · "
                            f"{_fmt_mmss(meta['duration'])} · {meta['video_codec']} · "
                            f"{_human_size(meta['size_bytes'])}")
            except Exception as exc:  # inspection is best-effort
                self._log("[inspect]", f"metadata unavailable: {exc}", "error")
            # Open the New-job overlay's "detected" step with real info.
            self._emit("onboarding", {
                "name": os.path.basename(path), "meta": meta_str})
        except Exception as exc:
            self._log("[import]", f"failed to open video: {exc}", "error")

    def start_processing(self, mode: str):
        job = self._pending_job or self.current_job
        if job is None:
            self._log("[error]", "No video selected.", "error")
            return
        product_mode = _MODE_MAP.get(mode, constants.PRODUCT_MODE_STUDY_PACK)
        job.settings["product_mode"] = product_mode
        w_model = self.config.get("whisper_model", "")
        if w_model:
            job.settings.setdefault("whisper", {})["model"] = w_model
        # Apply the compute-engine choice (cpu/vulkan/auto) so a Vulkan
        # selection in Settings actually reaches the transcription backend.
        job.settings.setdefault("whisper", {})["engine"] = \
            self.config.get("engine", "auto")
        job.save()
        self.current_job = job

        # Validate whisper availability for modes that need it.
        needs_whisper = product_mode != constants.PRODUCT_MODE_SLIDES_ONLY
        w_exe = self.config.get("whisper_exe", "")
        if needs_whisper and (not w_exe or not os.path.exists(w_exe)
                              or not w_model or not os.path.exists(w_model)):
            self._emit("status_changed", {
                "label": "Setup needed", "pct": 0,
                "detail": "configure Whisper in Settings"})
            self._log("[error]",
                      "Whisper executable/model not configured — set them in "
                      "Settings before processing (or choose Slides Only).", "error")
            return

        # Fresh pipeline model.
        skipped = constants.__dict__.get("STAGES_SKIPPED_BY_MODE", {})
        self._stages = []
        for name, label, color in _STAGE_META:
            self._stages.append({
                "name": name, "label": label, "color": color,
                "state": "pending", "pct": 0})
        self._pipeline_start = time.time()
        self._emit("status_changed", {"job": job.manifest.get("title", "Job")})
        self._render_pipeline(title="Starting…", meta="preparing")
        self._log("[engine]", f"Product mode: "
                  f"{constants.PRODUCT_MODE_LABELS.get(product_mode, product_mode)}",
                  "engine")
        self.controller.run_pipeline()

    def cancel_job(self):
        try:
            self.controller.cancel()
        finally:
            self._emit("status_changed", {
                "label": "Cancelled", "pct": 0, "detail": "job cancelled"})
            self._log("[engine]", "Pipeline cancelled by user.", "engine")

    # ------------------------------------------------------------------ pipeline render
    def _stage_by_name(self, name: str) -> dict | None:
        return next((s for s in self._stages if s["name"] == name), None)

    def _render_pipeline(self, title=None, meta=None):
        elapsed = time.time() - self._pipeline_start if self._pipeline_start else 0
        done = sum(1 for s in self._stages if s["state"] == "done")
        total = len(self._stages) or 1
        overall = int(done / total * 100)
        if title is None:
            active = next((s for s in self._stages if s["state"] == "active"), None)
            title = f"{active['label']}…" if active else "Processing…"
        if meta is None:
            meta = f"elapsed {_fmt_mmss(elapsed)} · {overall}%"
        stages = [{"label": s["label"], "state": s["state"],
                   **({"pct": s["pct"], "color": s["color"]}
                      if s["state"] == "active" else {})}
                  for s in self._stages]
        self._emit("pipeline_changed", {"title": title, "meta": meta, "stages": stages})

    def _on_stage_started(self, name: str):
        s = self._stage_by_name(name)
        if s:
            s["state"] = "active"
            s["pct"] = 0
        self._render_pipeline()
        self._emit("status_changed", {
            "label": s["label"] if s else name, "pct": 0,
            "detail": f"0% · {s['label'] if s else name}",
            "side": f"{s['label'] if s else name} 0%"})

    def _on_stage_progress(self, name: str, pct: int):
        s = self._stage_by_name(name)
        if s:
            s["state"] = "active"
            s["pct"] = int(pct)
        self._render_pipeline()
        label = s["label"] if s else name
        self._emit("status_changed", {
            "label": label, "pct": int(pct),
            "detail": f"{int(pct)}% · {label}", "side": f"{label} {int(pct)}%"})

    def _on_stage_log(self, name: str, text: str):
        key = name.split()[0].lower()
        self._log(f"[{key}]", text, key)

    def _on_stage_finished(self, name: str, success: bool, error: str):
        s = self._stage_by_name(name)
        if s:
            s["state"] = "done" if success else "pending"
            s["pct"] = 100 if success else s["pct"]
        self._render_pipeline()
        if not success and error:
            self._log("[error]", f"{name}: {error}", "error")

    def _on_stage_cached(self, name: str):
        s = self._stage_by_name(name)
        if s:
            s["state"] = "done"
            s["pct"] = 100
        self._render_pipeline()
        self._log(f"[{name.split()[0].lower()}]", "cached — skipped", name.split()[0].lower())

    def _on_backend_info(self, text: str):
        self._log("[engine]", text, "engine")
        # Surface the ACTUAL loaded backend (not the requested one) in the UI.
        self._emit("settings_changed", {"actual_backend": text})

    def _on_transcript_segment(self, seg: dict):
        t0 = _fmt_hhmmss(seg.get("start_ms", 0) / 1000.0)
        t1 = _fmt_hhmmss(seg.get("end_ms", 0) / 1000.0)
        self._log("[t]", f"{t0} → {t1}  {seg.get('text', '').strip()}", "t")

    def _on_pipeline_completed(self):
        for s in self._stages:
            s["state"] = "done"
            s["pct"] = 100
        self._render_pipeline(title="Complete", meta="pipeline finished")
        self._emit("status_changed", {
            "label": "Done", "pct": 100, "detail": "processing complete", "side": "Done"})
        self._log("[engine]", "Pipeline complete.", "engine")
        self._push_jobs()
        self._push_review_data()
        self._push_study_data()

    def _on_pipeline_failed(self, msg: str):
        self._emit("status_changed", {
            "label": "Failed", "pct": 0, "detail": msg[:80]})
        self._log("[error]", f"Pipeline failed: {msg}", "error")
        self._push_jobs()

    # ------------------------------------------------------------------ review data
    def _push_review_data(self):
        job = self.current_job
        if job is None:
            return
        duration = float(job.source.get("duration", 0.0) or 0.0)
        candidates = FileManager.read_json_safe(
            os.path.join(job.paths["root"], "candidates.json"), []) or []
        candidates = sorted(candidates, key=lambda c: float(c.get("timestamp_seconds", 0.0)))
        slides, self._slide_frames = [], []
        for c in candidates:
            ts = float(c.get("timestamp_seconds", 0.0))
            pct = (ts / duration * 100.0) if duration else 0.0
            img_name = c.get("image_filename") or ""
            slides.append({
                "pct": round(pct, 2),
                "time": _fmt_hhmmss(ts),
                "state": "accepted" if c.get("decision") == "accepted" else "rejected",
                "frame": c.get("frame_number"),
                "img": asset_url(job.job_id, img_name) if img_name else "",
            })
            self._slide_frames.append(c.get("frame_number"))
        if slides:
            self._emit("slides_changed", {
                "slides": slides,
                "duration": _fmt_mmss(duration),
                "durationMid": _fmt_mmss(duration / 2.0)})

        # Transcript segments -> review rows + magazine blocks.
        segments = transcript_store.load_working(job.paths)
        self._review_ids = [s.get("id") for s in segments]
        review_segments = [{
            "t": _fmt_mmss_d(s.get("start", 0.0)),
            "text": s.get("text", ""),
        } for s in segments]
        corrections = sum(1 for s in segments if s.get("edited"))

        blocks, cur, cur_t, cur_len = [], [], None, 0
        for s in segments:
            if cur_t is None:
                cur_t = _fmt_mmss(s.get("start", 0.0))
            cur.append(_esc(s.get("text", "")))
            cur_len += len(s.get("text", ""))
            if cur_len >= 320:
                blocks.append({"t": cur_t, "html": " ".join(cur)})
                cur, cur_t, cur_len = [], None, 0
        if cur:
            blocks.append({"t": cur_t or "00:00", "html": " ".join(cur)})

        self._emit("transcript_changed", {
            "reviewSegments": review_segments or [{"t": "00:00.0", "text": "(no transcript)"}],
            "transcript": {
                "title": job.manifest.get("title", "Transcript"),
                "duration": _fmt_mmss(duration),
                "segments": len(segments),
                "corrections": corrections,
                "blocks": blocks or [{"t": "00:00", "html": "(no transcript yet)"}],
            }})

    def set_slide_state(self, index: int, state: str):
        job = self.current_job
        if job is None or index < 0 or index >= len(self._slide_frames):
            return
        frame = self._slide_frames[index]
        path = os.path.join(job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(path, []) or []
        for c in candidates:
            if c.get("frame_number") == frame:
                c["decision"] = "accepted" if state == "accepted" else "rejected"
                break
        FileManager.write_json_atomic(path, candidates)
        self._log("[review]", f"slide @ frame {frame} → {state}", "detect")

    def save_corrections(self, texts: list[str]):
        job = self.current_job
        if job is None:
            return
        segments = transcript_store.load_working(job.paths)
        by_id = {s.get("id"): s for s in segments}
        changed = 0
        for seg_id, text in zip(self._review_ids, texts):
            seg = by_id.get(seg_id)
            if seg is not None and seg.get("text", "") != text:
                seg["text"] = text
                seg["edited"] = True
                changed += 1
        transcript_store.save_working(job.paths, segments)
        self._log("[save]", f"{changed} segment(s) saved", "extract")
        self._push_review_data()

    def repair_selection(self):
        job = self.current_job
        if job is None:
            return
        o = self._ollama_settings()
        if not (o.get("enabled") and o.get("model")):
            self._log("[repair]", "Local AI is off — enable Ollama in Settings to "
                      "run context repair.", "error")
            return
        norm = FileManager.read_json_safe(
            os.path.join(job.paths["transcript"], "normalized.json"), None)
        if not norm:
            self._log("[repair]", "No normalized transcript to repair yet.", "error")
            return
        try:
            from lecturepack.services.ai_repair_service import AiRepairWorker
        except Exception as exc:
            self._log("[repair]", f"repair unavailable: {exc}", "error")
            return
        self._log("[repair]", "Running context repair…", "align")
        worker = AiRepairWorker(
            job.paths["transcript"], approved_names=[], norm_dict=norm,
            ollama_settings=o, course_title=job.manifest.get("title", ""))
        self._repair_worker = worker

        def ok(payload):
            n = len(payload.get("corrections", []) if isinstance(payload, dict) else [])
            self._log("[repair]", f"{n} correction proposal(s) generated.", "align")

        def fail(kind, message, details):
            self._log("[repair]", f"{message}", "error")

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()

    # ------------------------------------------------------------------ study
    def _push_study_data(self):
        job = self.current_job
        if job is None:
            return
        try:
            overview = study_service.build_overview(job)
        except Exception as exc:
            self._log("[study]", f"overview unavailable: {exc}", "error")
            return
        duration = float(overview.get("duration_seconds", 0.0) or 0.0)
        sections = overview.get("sections", []) or []

        topics, topic_blocks, topic_labels = [], [], []
        for i, sec in enumerate(sections):
            start = float(sec.get("start", 0.0) or 0.0)
            nxt = (float(sections[i + 1].get("start", duration) or duration)
                   if i + 1 < len(sections) else duration)
            heading = sec.get("heading", f"Section {i + 1}")
            topics.append({"t": _fmt_mmss(start), "title": heading, "active": i == 0})
            if duration:
                left = max(0.0, start / duration * 100.0)
                width = max(3.0, (nxt - start) / duration * 100.0)
                topic_blocks.append({"left": round(left, 1), "width": round(width, 1),
                                     "active": i == 0})
            short = heading.split(" ")
            topic_labels.append(" ".join(short[:2]))

        bookmarks = []
        for entry in (overview.get("bookmarked_slides", {}) or {}).values():
            if entry.get("bookmarked"):
                bookmarks.append({
                    "t": entry.get("timestamp_formatted", ""),
                    "text": entry.get("note") or "Bookmarked slide",
                    "color": "var(--orange)"})
        for entry in (overview.get("bookmarked_sections", {}) or {}).values():
            bookmarks.append({
                "t": _fmt_hhmmss(float(entry.get("start", 0.0) or 0.0)),
                "text": entry.get("heading") or "Bookmarked section",
                "color": "var(--blue)"})

        stats = [
            ["Slides", f"{overview.get('accepted_slide_count', 0)} kept"],
            ["Segments", str(overview.get("transcript_segment_count", 0))],
            ["Needs review", str(overview.get("needs_review_count", 0))],
        ]

        cards = []
        for card in (study_service.load_flashcards(job).get("cards") or []):
            term = card.get("term") or card.get("front") or card.get("q") or ""
            definition = card.get("definition") or card.get("back") or card.get("a") or ""
            if term or definition:
                cards.append({"q": term, "a": definition})
        if not cards:
            terms = overview.get("key_terms", []) or []
            if terms:
                cards = [{"q": "Key terms in this lecture",
                          "a": ", ".join(terms[:8])}]
            else:
                cards = [{"q": "No flashcards yet",
                          "a": "Open the AI assistant tab and generate flashcards "
                               "from this lecture."}]

        self._emit("study_changed", {
            "topics": topics or [{"t": "00:00", "title": "Lecture", "active": True}],
            "topicBlocks": topic_blocks or [{"left": 0.5, "width": 99, "active": True}],
            "topicLabels": topic_labels or ["Lecture"],
            "keyTerms": overview.get("key_terms", []) or [],
            "bookmarks": bookmarks,
            "stats": stats,
            "cards": cards})

    def ask_ai(self, prompt: str):
        job = self.current_job
        o = self._ollama_settings()
        if not (o.get("enabled") and o.get("model")):
            self._emit("ai_token", "Local AI is off. Enable Ollama in Settings "
                       "(Local AI endpoint) to use the study assistant.")
            self.backend.ai_done.emit()
            return
        if job is None:
            self._emit("ai_token", "Open or process a lecture first, then ask away.")
            self.backend.ai_done.emit()
            return
        segments = transcript_store.load_working(job.paths)
        transcript_text = sas.transcript_context(segments or [])
        self._emit("ai_status", {"label": "Thinking…", "model": o.get("model")})
        worker = sas.StudyAssistantWorker(
            "chat", transcript_text, o,
            history=list(self._chat_history), question=prompt, count=5)
        self._ai_worker = worker
        self._chat_history.append({"role": "user", "text": prompt})

        def ok(task, result):
            answer = (result or {}).get("answer", "") if isinstance(result, dict) else ""
            answer = answer or "I couldn't find an answer in the transcript."
            self._chat_history.append({"role": "assistant", "text": answer})
            self._emit("ai_token", answer)
            self.backend.ai_done.emit()
            self._emit("ai_status", {"label": "Local", "model": o.get("model")})
            if job is not None:
                try:
                    study_service.append_chat_message(job, "user", prompt)
                    study_service.append_chat_message(job, "assistant", answer)
                except Exception:
                    pass

        def fail(kind, message, details):
            self._emit("ai_token", f"⚠ {message}")
            self.backend.ai_done.emit()
            self._emit("ai_status", {"label": "AI error", "model": o.get("model")})

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()

    # ------------------------------------------------------------------ exports
    def export_all(self, formats: list[str]):
        self._run_export()

    def export_one(self, kind: str):
        self._run_export()

    def _run_export(self):
        job = self.current_job
        if job is None:
            self._emit("export_done", {"files": [], "meta": "no job loaded"})
            return
        self._export_start = time.time()
        self._emit("export_progress", {"pct": 5, "label": "starting export…"})
        worker = ExportWorker(job)
        self._export_worker = worker
        worker.progress.connect(
            lambda p: self._emit("export_progress",
                                 {"pct": int(p), "label": f"exporting… {int(p)}%"}))
        worker.status_message.connect(
            lambda m: self._emit("export_progress", {"pct": 50, "label": str(m)[:80]}))
        worker.finished.connect(lambda ok, err: self._on_export_finished(ok, err))
        worker.start()

    def _on_export_finished(self, success: bool, error: str):
        job = self.current_job
        if not success:
            self._emit("export_done", {"files": [], "meta": f"export failed: {error}"[:80]})
            return
        export_dir = job.paths["exports"]
        files, total_bytes = [], 0
        if os.path.isdir(export_dir):
            for name in sorted(os.listdir(export_dir)):
                fp = os.path.join(export_dir, name)
                if os.path.isfile(fp):
                    files.append(name)
                    total_bytes += os.path.getsize(fp)
        elapsed = time.time() - self._export_start
        self._emit("export_done", {
            "files": files,
            "meta": f"{len(files)} files · {_human_size(total_bytes)} · {elapsed:.1f}s"})

    def export_folder(self):
        if self.current_job is not None:
            return self.current_job.paths["exports"]
        return self.config.data_dir

    # ------------------------------------------------------------------ settings / misc
    def test_endpoint(self):
        self._probe_ollama_async(announce=True)

    def list_ollama_models(self):
        """Fetch installed Ollama models (/api/tags) and emit them for the
        Settings model picker. Never hard-hardcodes a single model."""
        o = self._ollama_settings()
        base = o.get("base_url") or "http://localhost:11434"
        selected = o.get("model", "")

        def worker():
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                models = OllamaClient(base).list_models()
                self._emit("ollama_models", {
                    "models": models, "selected": selected, "available": True})
            except Exception as exc:
                self._emit("ollama_models", {
                    "models": [], "selected": selected,
                    "available": False, "error": str(exc)})

        threading.Thread(target=worker, daemon=True).start()

    def _probe_ollama_async(self, announce: bool = False):
        o = self._ollama_settings()
        base = o.get("base_url") or "http://localhost:11434"
        model = o.get("model", "")

        def worker():
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                probe = OllamaClient(base).is_available()
            except Exception as exc:
                probe = {"available": False, "error": str(exc)}
            if probe.get("available") and o.get("enabled") and model:
                self._emit("ai_status", {"label": "Local", "model": model})
                if announce:
                    self._emit("settings_changed", {"update_status": ""})
            else:
                label = "AI off" if not o.get("enabled") else "Unavailable"
                self._emit("ai_status", {"label": label, "model": model or "—"})

        threading.Thread(target=worker, daemon=True).start()

    def browse_model(self, parent):
        path, _ = QFileDialog.getOpenFileName(
            parent, "Choose a Whisper model", os.path.expanduser("~"),
            "Whisper models (*.bin);;All files (*.*)")
        if path:
            self.config.set("whisper_model", path)
            self._emit("settings_changed", {"model_path": path})

    def save_project(self):
        if self.current_job is not None:
            self.current_job.save()
            self._log("[save]", "project saved", "extract")


def make_adapter(backend) -> EngineAdapter:
    """Return the real engine adapter, falling back to the demo on import error."""
    try:
        return LecturePackAdapter(backend)
    except Exception as exc:  # pragma: no cover - defensive boot guard
        import traceback
        traceback.print_exc()
        print(f"[engine_adapter] falling back to DemoAdapter: {exc}")
        return DemoAdapter(backend)
