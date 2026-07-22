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
    update_state = Signal(str)
    whatsnew = Signal(str)
    settings_changed = Signal(str)
    ollama_models = Signal(str)
    job_deleted = Signal(str)
    quiz_changed = Signal(str)
    quiz_status = Signal(str)
    flashcards_changed = Signal(str)
    flashcards_status = Signal(str)
    vulkan_status = Signal(str)
    cuda_status = Signal(str)
    cuda_pack = Signal(str)
    groq_status = Signal(str)
    smart_study = Signal(str)

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
    def validate_vulkan(self):
        self._adapter.validate_vulkan()

    @Slot()
    def validate_cuda(self):
        self._adapter.validate_cuda()

    @Slot()
    def cuda_pack_status(self):
        self._adapter.cuda_pack_status()

    @Slot()
    def install_cuda_pack(self):
        self._adapter.install_cuda_pack()

    @Slot()
    def cancel_cuda_pack(self):
        self._adapter.cancel_cuda_pack()

    @Slot(str)
    def set_groq_key(self, key: str):
        self._adapter.set_groq_key(key)

    @Slot()
    def remove_groq_key(self):
        self._adapter.remove_groq_key()

    @Slot()
    def test_groq_key(self):
        self._adapter.test_groq_key()

    @Slot()
    def list_ollama_models(self):
        self._adapter.list_ollama_models()

    # ------------------------------------------------------------- Smart Study

    @Slot()
    def smart_study_status(self):
        self._adapter.smart_study_status()

    @Slot(str)
    def set_study_preset(self, preset: str):
        self._adapter.set_study_preset(preset)

    @Slot(str)
    def install_smart_study(self, preset: str):
        self._adapter.install_smart_study(preset)

    @Slot()
    def cancel_smart_study(self):
        self._adapter.cancel_smart_study()

    @Slot()
    def launch_ollama_installer(self):
        self._adapter.launch_ollama_installer()

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

    @Slot(str)
    def generate_quiz(self, opts_json: str):
        self._adapter.generate_quiz(opts_json)

    @Slot()
    def cancel_quiz(self):
        self._adapter.cancel_quiz()

    @Slot(str)
    def save_quiz_session(self, session_json: str):
        self._adapter.save_quiz_session(session_json)

    @Slot(str)
    def generate_flashcards(self, opts_json: str):
        self._adapter.generate_flashcards(opts_json)

    @Slot()
    def cancel_flashcards(self):
        self._adapter.cancel_flashcards()

    @Slot(str)
    def save_flashcard_session(self, session_json: str):
        self._adapter.save_flashcard_session(session_json)

    @Slot(str)
    def save_notes(self, text: str):
        self._adapter.save_notes(text)

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

    @Slot(result=str)
    def get_updater_state(self) -> str:
        return json.dumps(self._updater.updater_state_payload())

    @Slot()
    def start_update_download(self):
        self._updater.start_download()

    @Slot()
    def cancel_update_download(self):
        self._updater.cancel_download()

    @Slot()
    def install_downloaded_update(self):
        self._updater.install_downloaded()

    @Slot()
    def open_release_page(self):
        self._updater.open_release_page()

    @Slot(str)
    def set_update_channel(self, channel: str):
        self._updater.set_channel(channel)

    @Slot(str)
    def set_auto_check(self, enabled: str):
        self._updater.set_auto_check(str(enabled).lower() in ("1", "true", "yes", "on"))

    @Slot()
    def skip_update_version(self):
        self._updater.skip_current()

    @Slot()
    def clear_skipped_version(self):
        self._updater.clear_skipped()

    @Slot()
    def install_update(self):
        # Back-compat single-tap: download+verify, then (on update_ready) the UI
        # calls install_downloaded_update. Kept so older UI wiring still works.
        self._updater.start_download()

    @Slot()
    def whatsnew_seen(self):
        self._settings.setValue("last_seen_version", version.__version__)
