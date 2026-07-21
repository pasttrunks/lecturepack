"""QWebChannel bridge between the web UI and the LecturePack engine.

The JS side (ui/bridge.js) connects to the object registered as "backend".
Everything crossing the bridge is a JSON string (or a plain str/int), which
keeps the contract simple and easy to test.

Engine calls are delegated to an EngineAdapter (engine_adapter.py). The real
LecturePack engine is wired there — this file should not need to change.
"""

from __future__ import annotations

import json
import os
import subprocess

from PySide6.QtCore import QObject, QSettings, Signal, Slot

from . import version
from .engine_adapter import make_adapter
from .paths import data_dir
from .updater import Updater


class Backend(QObject):
    # ---- signals consumed by ui/app.js (names must match bridge.js SIGNALS) ----
    jobs_changed = Signal(str)
    pipeline_changed = Signal(str)
    log_line = Signal(str)
    status_changed = Signal(str)
    slides_changed = Signal(str)
    transcript_changed = Signal(str)
    study_changed = Signal(str)
    export_progress = Signal(str)
    export_done = Signal(str)
    ai_token = Signal(str)
    ai_done = Signal()
    ai_status = Signal(str)
    onboarding = Signal(str)
    update_available = Signal(str)
    update_progress = Signal(float)
    update_ready = Signal()
    update_error = Signal(str)
    whatsnew = Signal(str)
    settings_changed = Signal(str)
    ollama_models = Signal(str)
    job_deleted = Signal(str)

    def __init__(self, window):
        super().__init__()
        self._window = window
        self._settings = QSettings(version.ORG_NAME, version.APP_NAME)
        self._adapter = make_adapter(self)
        self._updater = Updater(self)

    def log_asset_error(self, tag: str, text: str, level: str = "error"):
        """Diagnostics hook for the asset resolver (see main.py). Surfaces a
        missing/blocked slide asset in the UI log instead of failing silently."""
        import sys
        print(f"[{tag}] {text}", file=sys.stderr)
        self.log_line.emit(json.dumps(
            {"tag": f"[{tag}]", "color": "var(--red)", "text": str(text)}))

    # ------------------------------------------------------------- lifecycle

    @Slot()
    def ui_ready(self):
        """Called once by the UI after the QWebChannel handshake."""
        self._adapter.on_ui_ready()
        self._updater.startup_check()

    @Slot(result=str)
    def get_bootstrap(self) -> str:
        return json.dumps(
            {
                "theme": self._settings.value("theme", "dark"),
                "version": version.__version__,
            }
        )

    # ------------------------------------------------------------- settings

    @Slot(str, str)
    def set_setting(self, key: str, value: str):
        self._settings.setValue(key, value)
        self._adapter.on_setting_changed(key, value)

    @Slot()
    def browse_model(self):
        self._adapter.browse_model(self._window)

    @Slot()
    def test_endpoint(self):
        self._adapter.test_endpoint()

    @Slot()
    def list_ollama_models(self):
        self._adapter.list_ollama_models()

    @Slot()
    def save_project(self):
        self._adapter.save_project()

    # ------------------------------------------------------------- import / jobs

    @Slot()
    def browse_video(self):
        self._adapter.browse_video(self._window)

    def import_video(self, path: str):
        """Native drop entry point (called from WebView.dropEvent)."""
        self._adapter.import_video(path)

    def notify_drag_over(self):
        self._adapter.notify_drag_over()

    @Slot(str)
    def start_processing(self, mode: str):
        self._adapter.start_processing(mode)

    @Slot(str)
    def open_job(self, job_id: str):
        self._adapter.open_job(job_id)

    @Slot(str)
    def delete_job(self, job_id: str):
        self._adapter.delete_job(job_id)

    @Slot(str, str)
    def set_job_group(self, job_id: str, group: str):
        self._adapter.set_job_group(job_id, group)

    @Slot()
    def cancel_job(self):
        self._adapter.cancel_job()

    # ------------------------------------------------------------- review

    @Slot(int, str)
    def set_slide_state(self, index: int, state: str):
        self._adapter.set_slide_state(index, state)

    @Slot(str)
    def save_corrections(self, texts_json: str):
        self._adapter.save_corrections(json.loads(texts_json))

    @Slot()
    def repair_selection(self):
        self._adapter.repair_selection()

    # ------------------------------------------------------------- study AI

    @Slot(str)
    def ask_ai(self, prompt: str):
        self._adapter.ask_ai(prompt)

    # ------------------------------------------------------------- exports

    @Slot(str)
    def export_all(self, formats_json: str):
        self._adapter.export_all(json.loads(formats_json))

    @Slot(str)
    def export_one(self, kind: str):
        self._adapter.export_one(kind)

    @Slot()
    def open_export_folder(self):
        folder = self._adapter.export_folder() or data_dir()
        if os.name == "nt":
            os.startfile(folder)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", folder])  # noqa: S603,S607

    # ------------------------------------------------------------- updates

    @Slot()
    def check_updates(self):
        self._updater.check(manual=True)

    @Slot()
    def install_update(self):
        self._updater.download_and_install()

    @Slot()
    def whatsnew_seen(self):
        self._settings.setValue("last_seen_version", version.__version__)
