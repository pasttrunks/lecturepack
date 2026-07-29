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
from pathlib import Path
import re
import subprocess

from PySide6.QtCore import QObject, QSettings, Signal, Slot
from PySide6.QtGui import QGuiApplication

from . import version
from .engine_adapter import make_adapter
from .paths import data_dir
from .updater import Updater
from .repair_worker import RuntimeRepairWorker
from lecturepack.controllers.runtime_diagnostics_controller import RuntimeDiagnosticsController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService
from lecturepack.services.runtime_diagnostics import RuntimeDiagnosticsService


class Backend(QObject):
    _ADMISSION_GUARDED_OPERATIONS = frozenset({
        "ui_ready", "set_setting", "browse_model", "test_endpoint", "validate_vulkan", "validate_cuda",
        "cuda_pack_status", "install_cuda_pack", "cancel_cuda_pack", "set_groq_key", "remove_groq_key",
        "test_groq_key", "list_ollama_models", "smart_study_status", "set_study_preset",
        "install_smart_study", "cancel_smart_study", "launch_ollama_installer", "save_project",
        "browse_video", "import_video", "notify_drag_over", "media_link_support", "probe_media_url",
        "import_media_url", "cancel_media_url", "start_processing", "open_job", "delete_job",
        "start_demo_job", "end_demo_job",
        "set_job_group", "delete_jobs", "set_jobs_group", "cancel_job", "pause_job", "resume_job",
        "restart_job", "retry_stage", "enqueue_job", "reorder_queue", "run_now", "remove_from_queue",
        "schedule_job", "unschedule_job", "get_notification_prefs", "set_notification_prefs",
        "test_notification", "run_diagnostics", "open_job_folder", "get_post_completion", "set_slide_state",
        "save_corrections", "repair_selection", "ask_ai", "generate_quiz", "cancel_quiz",
        "save_quiz_session", "generate_flashcards", "cancel_flashcards", "save_flashcard_session",
        "save_notes", "export_all", "export_one", "open_export_folder", "check_updates",
        "get_updater_state", "start_update_download", "cancel_update_download", "install_downloaded_update",
        "open_release_page", "set_update_channel", "set_auto_check", "skip_update_version",
        "clear_skipped_version", "install_update", "whatsnew_seen",
    })
    _RETURNING_GUARDED_OPERATIONS = frozenset({"get_updater_state"})
    # ---- signals consumed by ui/app.js (names must match bridge.js SIGNALS) ----
    jobs_changed = Signal(str)
    # disk usage of the data dir; the sidebar storage widget stays hidden until
    # this arrives, so it never shows an invented figure (BUG-04)
    storage_changed = Signal(str)
    # Which lecture the workspace screens belong to ({id, title}); id "" means
    # nothing is loaded and the workspace must render empty.
    active_job = Signal(str)
    # link import (paste a URL): capability report, probe result, transfer
    # progress, and terminal outcome. Mirrored in app/ui/bridge.js SIGNALS.
    media_link_state = Signal(str)
    media_probe = Signal(str)
    media_progress = Signal(str)
    media_done = Signal(str)
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
    # Guided-demo lifecycle payloads are JSON only: operation/session identity,
    # stage/progress, and terminal cleanup result.  The web UI can subscribe
    # later without receiving a Qt object or a persistent job handle.
    demo_event = Signal(str)
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
    # beta.3: queue/schedule, pause, notifications, diagnostics, completion.
    queue_changed = Signal(str)
    pause_state = Signal(str)
    notification_prefs = Signal(str)
    notification_navigate = Signal(str)
    diagnostics = Signal(str)
    job_completed = Signal(str)
    post_completion = Signal(str)
    repair_event = Signal(str)
    # Runtime admission evidence is a dedicated transport boundary.  It is not
    # ordinary status text and a fallback never implies a second ready event.

    def __init__(self, window):
        super().__init__()
        self._window = window
        self._settings = QSettings(version.ORG_NAME, version.APP_NAME)
        self._runtime_config = ConfigManager()
        self.runtime_health_result = RuntimeBootstrapService(self._runtime_config).assess()
        self._runtime_diagnostics = RuntimeDiagnosticsController(
            RuntimeDiagnosticsService(self._runtime_config, self.runtime_health_result)
        )
        self._adapter = None
        self._updater = None
        self._repair_worker = None
        self._repair_offer_id = None
        self._runtime_repair = None
        self._repair_confirmed = False
        self._repair_terminal_seen = False
        self._last_repair_diagnostics = "[]"
        if self.runtime_health_result.state == "HEALTHY":
            self._adapter = make_adapter(
                self,
                runtime_health_result=self.runtime_health_result,
                runtime_diagnostics_controller=self._runtime_diagnostics,
            )
            self._updater = Updater(self)

    def __getattribute__(self, name):
        """Keep every normal bridge operation unreachable until admission succeeds."""
        guarded = object.__getattribute__(self, "_ADMISSION_GUARDED_OPERATIONS")
        if name in guarded:
            state = object.__getattribute__(self, "__dict__").get("runtime_health_result")
            if state is not None and state.state != "HEALTHY":
                return lambda *args, **kwargs: self._guard_admitted_operation(name)
        return super().__getattribute__(name)

    def _setup_required_payload(self, operation: str) -> dict:
        """Return the one JSON-safe no-op shape for withheld collaborators."""
        return {
            "type": "setup_required",
            "operation": operation,
            "runtime_health": self._runtime_diagnostics.runtime_health_snapshot(),
        }

    def _guard_admitted_operation(self, operation: str):
        """Emit or return setup-required evidence before any collaborator access."""
        payload = self._setup_required_payload(operation)
        if operation in self._RETURNING_GUARDED_OPERATIONS:
            return json.dumps(payload)
        self.diagnostics.emit(json.dumps(payload))
        return None

    def _on_repair_event(self, payload):
        """Forward only the active repair operation and clear terminal workers."""
        if payload.get("operation_id") != self._repair_offer_id:
            return
        kind = payload.get("kind")
        if self._repair_terminal_seen:
            return
        if self._runtime_repair is not None:
            self._last_repair_diagnostics = self._runtime_repair.diagnostic_report()
        if kind == "metadata_ready":
            self._repair_offer_id = payload["operation_id"]
            self._repair_worker = None
        if kind in {"failed", "cancelled", "admitted"}:
            if kind == "admitted":
                # The service's final result was produced by the exact canonical
                # repair assessment inside RuntimeGenerationStore's rollback
                # callback.  Do not issue a second, unrollbackable assessment.
                result = self._runtime_repair.admission_result if self._runtime_repair is not None else None
                if result is not None and result.state == "HEALTHY":
                    self.runtime_health_result = result
                    self._runtime_diagnostics = RuntimeDiagnosticsController(RuntimeDiagnosticsService(self._runtime_config, result))
                if result is not None and result.state == "HEALTHY" and self._adapter is None:
                    self._adapter = make_adapter(self, runtime_health_result=self.runtime_health_result, runtime_diagnostics_controller=self._runtime_diagnostics)
                    self._updater = Updater(self)
                else:
                    payload = {"operation_id": self._repair_offer_id, "kind": "failed", "detail": "repaired runtime did not pass admission"}
            self._repair_terminal_seen = True
            self._repair_offer_id = None
            self._repair_worker = None
            self._runtime_repair = None
            self._repair_confirmed = False
        self.repair_event.emit(json.dumps(payload))

    def _start_repair_worker(self, worker):
        if self._repair_worker is not None:
            return json.dumps({"type": "repair_in_progress"})
        self._repair_worker = worker
        worker.repair_event.connect(self._on_repair_event)
        worker.start()
        return json.dumps({"operation_id": self._repair_offer_id})

    @Slot(str, result=str)
    def start_runtime_repair(self, operation_id: str) -> str:
        """Start metadata-only offer acquisition while setup is required."""
        if self.runtime_health_result.state == "HEALTHY":
            return json.dumps({"type": "repair_not_required"})
        if not operation_id:
            return json.dumps({"type": "invalid_repair_operation"})
        if self._repair_worker is not None or self._repair_offer_id is not None:
            return json.dumps({"type": "repair_in_progress", "operation_id": self._repair_offer_id})
        self._repair_offer_id = operation_id
        self._repair_confirmed = False
        self._repair_terminal_seen = False
        self._runtime_repair = self._make_runtime_repair_service()
        return self._start_repair_worker(RuntimeRepairWorker(self._runtime_repair, operation_id, parent=self))

    @Slot(str, result=str)
    def confirm_runtime_repair(self, operation_id: str) -> str:
        if operation_id != self._repair_offer_id:
            return json.dumps({"type": "invalid_repair_offer"})
        if self._runtime_repair is None or self._repair_worker is not None or self._repair_confirmed:
            return json.dumps({"type": "invalid_repair_offer"})
        self._repair_confirmed = True
        return self._start_repair_worker(RuntimeRepairWorker(self._runtime_repair, operation_id, confirm=True, parent=self))

    @Slot(str)
    def cancel_runtime_repair(self, operation_id: str):
        if operation_id != self._repair_offer_id or self._runtime_repair is None:
            return
        if self._repair_worker is not None:
            self._repair_worker.cancel()
            return
        start = len(self._runtime_repair.events)
        self._runtime_repair.cancel(operation_id)
        for event in self._runtime_repair.events[start:]:
            self._on_repair_event(event.payload())

    @Slot(result=str)
    def retry_runtime_assessment(self) -> str:
        self.runtime_health_result = RuntimeBootstrapService(self._runtime_config).assess(trigger="repair")
        self._runtime_diagnostics = RuntimeDiagnosticsController(RuntimeDiagnosticsService(self._runtime_config, self.runtime_health_result))
        return self.get_bootstrap()

    def _runtime_repair_report(self) -> str:
        """Return the service-owned, redacted repair report and nothing else."""
        if self._runtime_repair is not None:
            self._last_repair_diagnostics = self._runtime_repair.diagnostic_report()
        return self._last_repair_diagnostics

    @Slot(result=str)
    def copy_runtime_repair_diagnostics(self) -> str:
        """Copy only sanitized repair events while the setup gate is active."""
        report = self._runtime_repair_report()
        QGuiApplication.clipboard().setText(report)
        return json.dumps({"type": "runtime_repair_diagnostics_copied"})

    @Slot(str, result=str)
    def save_runtime_repair_diagnostics(self, file_name: str) -> str:
        """Save a sanitized report below app data; reject traversal/user paths."""
        if not isinstance(file_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.txt", file_name):
            return json.dumps({"type": "invalid_runtime_repair_diagnostics_path"})
        root = (Path(self._runtime_config.resolve_data_dir()) / "runtime-repair-diagnostics").resolve()
        destination = (root / file_name).resolve()
        if root not in destination.parents:
            return json.dumps({"type": "invalid_runtime_repair_diagnostics_path"})
        try:
            root.mkdir(parents=True, exist_ok=True)
            destination.write_text(self._runtime_repair_report(), encoding="utf-8", newline="\n")
        except OSError:
            return json.dumps({"type": "runtime_repair_diagnostics_save_failed"})
        return json.dumps({"type": "runtime_repair_diagnostics_saved", "path": str(destination)})

    def _make_runtime_repair_service(self):
        from lecturepack.services.runtime_repair import RuntimeRepairService
        from lecturepack.infrastructure.runtime_generation import RuntimeGenerationStore
        from urllib.request import urlopen
        class _Transport:
            def get(self, url):
                with urlopen(url, timeout=30) as response:
                    return response.read()
            def stream_get(self, url):
                with urlopen(url, timeout=30) as response:
                    while chunk := response.read(64 * 1024):
                        yield chunk
        evidence = {name: item.get("reason", name) for name, item in self.runtime_health_result.components.items() if not item.get("healthy")}
        def assess(root):
            return RuntimeBootstrapService(self._runtime_config, runtime_root=root).assess(trigger="repair")
        return RuntimeRepairService(version.__version__, _Transport(), admission_evidence=evidence,
                                    generation_store=RuntimeGenerationStore(self._runtime_config.resolve_data_dir()),
                                    bootstrap_assessor=assess)

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
        if self._adapter is None:
            return
        self._adapter.on_ui_ready()
        self._updater.startup_check()
        if self.runtime_health_result.fallback_notice:
            self.diagnostics.emit(json.dumps({
                "type": "runtime_fallback",
                "fallback": dict(self.runtime_health_result.fallback_notice),
            }))

    @Slot(result=str)
    def get_bootstrap(self) -> str:
        snapshot = self._runtime_diagnostics.runtime_health_snapshot()
        return json.dumps(
            {
                "theme": self._settings.value("theme", "dark"),
                "version": version.__version__,
                "runtime_health_state": snapshot["admission_state"],
                "setup_required": snapshot if snapshot["admission_state"] == "SETUP_REQUIRED" else None,
            }
        )

    @Slot(result=str)
    def get_runtime_health_snapshot(self) -> str:
        """Return the controller-owned canonical runtime-health JSON payload."""
        return json.dumps(self._runtime_diagnostics.runtime_health_snapshot())

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

    # ------------------------------------------------------- import from a link

    @Slot()
    def media_link_support(self):
        """Report whether link import is available in this build."""
        self._adapter.media_link_support()

    @Slot(str)
    def probe_media_url(self, url: str):
        """Look up a link's title/duration without downloading it."""
        self._adapter.probe_media_url(url)

    @Slot(str, str)
    def import_media_url(self, url: str, title: str):
        """Download a link, then hand the file to the normal import path."""
        self._adapter.import_media_url(url, title)

    @Slot()
    def cancel_media_url(self):
        self._adapter.cancel_media_url()

    @Slot(str)
    def start_processing(self, mode: str):
        self._adapter.start_processing(mode)

    @Slot(result=str)
    def start_demo_job(self) -> str:
        return json.dumps(self._adapter.start_demo_job())

    @Slot(str, result=str)
    def end_demo_job(self, reason: str = "ended") -> str:
        return json.dumps(self._adapter.end_demo_job(reason))

    @Slot(str)
    def open_job(self, job_id: str):
        self._adapter.open_job(job_id)

    @Slot(str)
    def delete_job(self, job_id: str):
        self._adapter.delete_job(job_id)

    @Slot(str, str)
    def set_job_group(self, job_id: str, group: str):
        self._adapter.set_job_group(job_id, group)

    @Slot(str)
    def delete_jobs(self, ids_json: str):
        """Bulk delete from Home multi-select; ids_json is a JSON array."""
        self._adapter.delete_jobs(ids_json)

    @Slot(str, str)
    def set_jobs_group(self, ids_json: str, group: str):
        """Bulk group from Home multi-select; ids_json is a JSON array."""
        self._adapter.set_jobs_group(ids_json, group)

    @Slot()
    def cancel_job(self):
        self._adapter.cancel_job()

    # ------------------------------------------------- beta.3 pause/resume/retry

    @Slot()
    def pause_job(self):
        self._adapter.pause_job()

    @Slot(str)
    def resume_job(self, job_id: str):
        self._adapter.resume_job(job_id)

    @Slot(str)
    def restart_job(self, job_id: str):
        self._adapter.restart_job(job_id)

    @Slot(str, str)
    def retry_stage(self, job_id: str, stage: str):
        self._adapter.retry_stage(job_id, stage)

    # ------------------------------------------------- beta.3 queue / scheduling

    @Slot(str)
    def enqueue_job(self, job_id: str):
        self._adapter.enqueue_job(job_id)

    @Slot(str, int)
    def reorder_queue(self, job_id: str, index: int):
        self._adapter.reorder_queue(job_id, index)

    @Slot(str)
    def run_now(self, job_id: str):
        self._adapter.run_now(job_id)

    @Slot(str)
    def remove_from_queue(self, job_id: str):
        self._adapter.remove_from_queue(job_id)

    @Slot(str, str, str, str)
    def schedule_job(self, job_id: str, when: str, tz: str, missed_policy: str):
        self._adapter.schedule_job(job_id, when, tz, missed_policy)

    @Slot(str)
    def unschedule_job(self, job_id: str):
        self._adapter.unschedule_job(job_id)

    # ------------------------------------------------- beta.3 notifications / diagnostics

    @Slot()
    def get_notification_prefs(self):
        self._adapter.get_notification_prefs()

    @Slot(str)
    def set_notification_prefs(self, prefs_json: str):
        self._adapter.set_notification_prefs(prefs_json)

    @Slot()
    def test_notification(self):
        self._adapter.test_notification()

    @Slot(str)
    def run_diagnostics(self, job_id: str):
        self._adapter.run_diagnostics(job_id)

    @Slot(str)
    def open_job_folder(self, job_id: str):
        self._adapter.open_job_folder(job_id)

    @Slot()
    def get_post_completion(self):
        self._adapter.get_post_completion()

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
