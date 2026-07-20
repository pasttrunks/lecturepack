"""Adapter between the UI bridge and the LecturePack engine.

THIS IS THE INTEGRATION SEAM. The existing engine (transcription, slide
detection, alignment, exports, local AI) plugs in here — nothing else in
desktop/ or ui/ needs to change.

Two adapters are provided:

- EngineAdapter — the interface, with docstrings describing exactly what each
  method must do and which Backend signals it must emit.
- DemoAdapter   — a self-contained simulation (same demo content as the design
  prototype) so the shell runs and every screen is exercisable before the real
  engine is wired. It doubles as living documentation of the signal payloads.

To integrate: subclass EngineAdapter (e.g. LecturePackAdapter), implement each
method against the real engine, and return it from make_adapter().
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QFileDialog

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


def make_adapter(backend) -> EngineAdapter:
    """INTEGRATION: return LecturePackAdapter(backend) once the real engine is wired."""
    return DemoAdapter(backend)
