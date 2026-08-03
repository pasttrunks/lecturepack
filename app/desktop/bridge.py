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
import sys
import threading

from PySide6.QtCore import QObject, QSettings, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from . import version
from .engine_adapter import make_adapter
from .paths import data_dir
from .updater import Updater
from .repair_worker import RuntimeRepairWorker
from lecturepack.controllers.runtime_diagnostics_controller import RuntimeDiagnosticsController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.services.first_run_checklist import FIRST_RUN_CHECKLIST_ITEMS, build_first_run_checklist
from lecturepack.services.runtime_bootstrap import RuntimeBootstrapResult, RuntimeBootstrapService
from lecturepack.services.runtime_diagnostics import RuntimeDiagnosticsService

# Runtime admission is deferred to a worker thread (D-06/D-08): Backend.__init__
# must return without running any subprocess probe so the window can be shown
# immediately. ADMISSION_PENDING is the fail-closed sentinel state assigned
# before anything else in __init__ can observe self.runtime_health_result --
# see Backend.__init__ and __getattribute__ for why the ordering matters.
ADMISSION_PENDING = "PENDING"
TOUR_TRACE_ENV = "LECTUREPACK_TOUR_TRACE"


def _pending_result() -> RuntimeBootstrapResult:
    """Fail-closed sentinel for Backend.runtime_health_result's first value.

    Its state is deliberately never "HEALTHY", so __getattribute__ withholds
    every _ADMISSION_GUARDED_OPERATIONS name for the whole pending window,
    exactly as it already does for SETUP_REQUIRED.
    """
    return RuntimeBootstrapResult(ADMISSION_PENDING, "light", {})


def _pending_checklist() -> list[dict]:
    """Five placeholder rows so the UI can render all five checklist rows
    from the first frame -- never a blank or partially-built panel -- before
    assess() has returned anything to verdict them from (D-09)."""
    return [
        {"id": component_id, "verdict": "pending", "detail": ""}
        for component_id in FIRST_RUN_CHECKLIST_ITEMS
    ]


class Backend(QObject):
    _ADMISSION_GUARDED_OPERATIONS = frozenset({
        "set_setting", "browse_model", "test_endpoint", "validate_vulkan", "validate_cuda",
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
    # ui_ready is deliberately NOT guarded (T-01-06 hazard): the window is
    # shown and the WebChannel handshake completes while admission is still
    # pending (D-08), so ui_ready() must always run to record readiness --
    # see Backend.ui_ready. Being guarded like the engine-facing operations
    # would silently swallow every call behind a setup_required diagnostics
    # emission and self._ui_ready_seen would never be set.
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
    # Per-component checking/resolved progress and the final bootstrap
    # payload, emitted by the deferred assessment worker (D-06/D-08/D-09).
    # Same JSON-string convention as every other signal above.
    bootstrap_progress = Signal(str)
    bootstrap_complete = Signal(str)

    def __init__(self, window):
        super().__init__()
        self._window = window
        self._settings = QSettings(version.ORG_NAME, version.APP_NAME)
        self._runtime_config = ConfigManager()
        # Fail-closed (D-06/T-01-06-01): this MUST be the very next
        # assignment, before _runtime_diagnostics or any other collaborator,
        # because __getattribute__ withholds every
        # _ADMISSION_GUARDED_OPERATIONS name only when this attribute is
        # present and not HEALTHY. Deferring assess() to a worker thread
        # (see _start_bootstrap_async below) means this attribute would
        # otherwise sit unset for the whole pending window -- and an unset
        # attribute makes the guard fall through, opening every guarded
        # bridge operation before admission. Do not reorder this above
        # anything, and do not remove it even though the assignment looks
        # redundant with __getattribute__'s own None-check.
        self.runtime_health_result = _pending_result()
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
        # Deferred-bootstrap bookkeeping (D-08). ui_ready() is called by the
        # UI right after the WebChannel handshake, which happens while
        # assessment is still pending -- well before self._adapter exists.
        # These two flags make the deferred "ready" work
        # (on_ui_ready/startup_check/fallback_notice) run exactly once,
        # regardless of whether ui_ready() or bootstrap completion happens
        # first (T-01-06-06).
        self._ui_ready_seen = False
        self._ui_ready_dispatched = False
        # Conservative default (D-07): until the worker predicts cheaply,
        # assume the slow full path so the UI never silently suppresses the
        # checking overlay on what turns out to be a genuinely slow cold
        # start.
        self.validation_path = "full"
        self._tour_trace_enabled = os.environ.get(TOUR_TRACE_ENV, "").strip() == "1"
        self._bootstrap_progress_state: dict[str, tuple[str, str]] = {}
        self._bootstrap_progress_lock = threading.Lock()
        self._start_bootstrap_async()

    def _start_bootstrap_async(self) -> None:
        """Kick off runtime admission on a worker thread (D-06/D-08): the
        window can be shown and the WebChannel handshake can complete
        without waiting for the (possibly ~90s worst case) full validation
        path. Plan 01-03 already reduced that path's cost by parallelizing
        its three independent probes; this is the sequencing half."""
        threading.Thread(target=self._run_bootstrap_worker, daemon=True).start()

    def _run_bootstrap_worker(self) -> None:
        """Runs entirely off the main thread. Every UI-facing effect below is
        marshalled back onto the main thread through QTimer.singleShot with
        this Backend instance passed as the context object (the
        three-argument form). Per BUG-09, the bare two-argument
        QTimer.singleShot overload -- delay and callback only, no context --
        starts the timer in the *calling* thread and silently never fires
        from a plain ``threading.Thread`` with no Qt event loop of its own.

        Progress reporting is deliberately best-effort and wrapped
        separately from admission itself: a failure resolving the two
        host-only checklist items (windows_version, data_directory) must
        never prevent the real assess() call from running. A failure in
        assess() itself must still resolve to a safe non-HEALTHY completion,
        and bootstrap_complete must still be emitted, or the UI is left in
        the pending state forever (T-01-06-03).
        """
        try:
            for component_id in FIRST_RUN_CHECKLIST_ITEMS:
                self._emit_progress(component_id, "checking")
            self._emit_host_only_resolved()
        except Exception:
            pass

        try:
            bootstrap_service = RuntimeBootstrapService(self._runtime_config)
            self.validation_path = self._predict_validation_path(bootstrap_service)
            result = bootstrap_service.assess()
        except Exception as error:
            result = RuntimeBootstrapResult(
                "SETUP_REQUIRED", "light",
                {"bootstrap_worker": {"healthy": False, "reason": f"assessment worker failed: {error}"}},
            )

        try:
            self._emit_dependent_resolved(result)
        except Exception:
            pass

        QTimer.singleShot(0, self, lambda: self._on_bootstrap_complete(result))

    def _predict_validation_path(self, bootstrap_service) -> str:
        """Predict D-07's full-vs-light path using the exact ``_requires_full``
        inputs, without running any probe -- so the UI can decide whether to
        render the checking overlay before assess() (up to ~90s worst case)
        returns anything. Falls back to the conservative "full" prediction:
        rendering the overlay when it wasn't strictly needed is only a
        cosmetic cost, but predicting "light" and then silently taking the
        full path would reproduce exactly the D-08 defect this field exists
        to prevent. This duplicates one identity-hash pass that assess()
        will also perform -- see the plan Summary for that cost tradeoff.
        """
        try:
            if bootstrap_service.runtime_root is None:
                return "full"
            paths = dict(bootstrap_service.inventory_resolver(bootstrap_service.runtime_root))
            identity = bootstrap_service.identity_provider(bootstrap_service.runtime_root)
            previous = self._runtime_config.get("runtime_health")
            requires_full = bootstrap_service._requires_full(previous, identity, paths, "startup")
            return "full" if requires_full else "light"
        except Exception:
            return "full"

    def _emit_progress(self, component_id: str, state: str, detail: str = "") -> None:
        """Marshal one bootstrap_progress emission onto the main thread.
        Called from the worker thread; see _run_bootstrap_worker for why the
        context object is required (BUG-09)."""
        with self._bootstrap_progress_lock:
            self._bootstrap_progress_state[component_id] = (state, detail)
        payload = json.dumps({"id": component_id, "state": state, "detail": detail})
        QTimer.singleShot(0, self, lambda: self.bootstrap_progress.emit(payload))

    def _replay_bootstrap_progress(self) -> None:
        """Re-emit the latest known state per component for late subscribers.

        The bootstrap worker can finish emitting before the WebChannel
        handshake creates a UI subscriber. The UI reducer stores one state per
        component, so replaying this newest-per-id snapshot reconstructs the
        visible checklist without duplicating the historical event stream.
        """
        with self._bootstrap_progress_lock:
            snapshot = list(self._bootstrap_progress_state.items())
        for component_id, (state, detail) in snapshot:
            self.bootstrap_progress.emit(
                json.dumps({"id": component_id, "state": state, "detail": detail})
            )

    def _emit_host_only_resolved(self) -> None:
        """windows_version and data_directory never depend on assess() --
        report them the moment they're known rather than waiting for the
        (possibly ~90s) full validation to finish."""
        data_directory = self._runtime_config.resolve_data_dir()
        for item in build_first_run_checklist({}, data_dir=data_directory):
            if item["id"] in ("windows_version", "data_directory"):
                self._emit_progress(item["id"], "resolved", item["detail"])

    def _emit_dependent_resolved(self, result) -> None:
        """ffmpeg_ffprobe, whisper_runtime and bundled_model can only be
        verdicted from assess()'s own result -- RuntimeBootstrapService
        exposes no per-probe callback, so per D-09's honesty requirement
        their resolved state is reported at assess() completion rather than
        at an invented instant (see the plan Summary)."""
        data_directory = self._runtime_config.resolve_data_dir()
        for item in build_first_run_checklist(result, data_dir=data_directory):
            if item["id"] in ("ffmpeg_ffprobe", "whisper_runtime", "bundled_model"):
                self._emit_progress(item["id"], "resolved", item["detail"])

    def _on_bootstrap_complete(self, result) -> None:
        """Runs on the main thread via the _run_bootstrap_worker marshal.
        Promotes admission exactly once, following the same shape
        _on_repair_event's HEALTHY promotion already uses."""
        self.runtime_health_result = result
        self._runtime_diagnostics = RuntimeDiagnosticsController(
            RuntimeDiagnosticsService(self._runtime_config, result)
        )
        if result.state == "HEALTHY" and self._adapter is None:
            self._adapter = make_adapter(
                self,
                runtime_health_result=self.runtime_health_result,
                runtime_diagnostics_controller=self._runtime_diagnostics,
            )
            self._updater = Updater(self)
            # main.py's own attach_window call (main.py:161-164) runs before
            # this constructor path exists and is swallowed by its own bare
            # except. This handler is marshalled through the event loop, so
            # MainWindow.__init__ has already returned by the time it runs
            # -- self._window.tray is guaranteed to exist.
            try:
                self._adapter.attach_window(self._window, getattr(self._window, "tray", None))
            except Exception:
                pass
            if self._ui_ready_seen and not self._ui_ready_dispatched:
                self._dispatch_ui_ready_work()
        try:
            payload = self.get_bootstrap()
        except Exception:
            payload = json.dumps({
                "bootstrap_pending": False,
                "runtime_health_state": self.runtime_health_result.state,
            })
        self.bootstrap_complete.emit(payload)

    def _dispatch_ui_ready_work(self) -> None:
        """Run the deferred `ui_ready` work exactly once (T-01-06-06)."""
        self._ui_ready_dispatched = True
        self._adapter.on_ui_ready()
        self._updater.startup_check()
        if self.runtime_health_result.fallback_notice:
            self.diagnostics.emit(json.dumps({
                "type": "runtime_fallback",
                "fallback": dict(self.runtime_health_result.fallback_notice),
            }))

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
        print(f"[{tag}] {text}", file=sys.stderr)
        self.log_line.emit(json.dumps(
            {"tag": f"[{tag}]", "color": "var(--red)", "text": str(text)}))

    @Slot(str)
    def log_tour_trace(self, payload: str):
        """Write opt-in guided-tour diagnostics to the local stderr/log sink."""
        if not self._tour_trace_enabled:
            return
        text = str(payload)
        print(f"[tour-trace] {text}", file=sys.stderr, flush=True)
        self.log_line.emit(json.dumps(
            {"tag": "[tour-trace]", "color": "var(--muted)", "text": text}))

    # ------------------------------------------------------------- lifecycle

    @Slot()
    def ui_ready(self):
        """Called once by the UI after the QWebChannel handshake. Deliberately
        NOT in _ADMISSION_GUARDED_OPERATIONS (T-01-06 hazard closed here):
        the window is shown and the handshake completes while admission is
        still pending (D-08), so this must always record readiness --
        being guarded like the engine-facing operations would silently
        swallow it behind a setup_required diagnostics emission and
        self._ui_ready_seen would never be set."""
        self._ui_ready_seen = True
        self._replay_bootstrap_progress()
        if self._adapter is not None and not self._ui_ready_dispatched:
            self._dispatch_ui_ready_work()

    @Slot(result=str)
    def get_bootstrap(self) -> str:
        snapshot = self._runtime_diagnostics.runtime_health_snapshot()
        pending = self.runtime_health_result.state == ADMISSION_PENDING
        checklist = (
            _pending_checklist() if pending
            else build_first_run_checklist(self.runtime_health_result, data_dir=self._runtime_config.resolve_data_dir())
        )
        return json.dumps(
            {
                "theme": self.initial_theme(),
                "version": version.__version__,
                "runtime_health_state": snapshot["admission_state"],
                "setup_required": snapshot if snapshot["admission_state"] == "SETUP_REQUIRED" else None,
                "bootstrap_pending": pending,
                "validation_path": self.validation_path,
                "setup_acknowledged": self._runtime_config.setup_acknowledged(),
                "tour_trace_enabled": self._tour_trace_enabled,
                "checklist": checklist,
            }
        )

    @Slot(result=str)
    def acknowledge_setup(self) -> str:
        """Persist only a boolean (D-14: never a download/repair/reinstall of
        any kind). Deliberately NOT in _ADMISSION_GUARDED_OPERATIONS: it
        writes solely to the user's own config through ConfigManager and
        touches no engine collaborator, and the checklist screen it
        acknowledges is reachable in a HEALTHY-but-unacknowledged state --
        guarding it is not required."""
        self._runtime_config.persist_setup_acknowledged()
        return self.get_bootstrap()

    def initial_theme(self) -> str:
        """Return the only valid persisted theme before the WebEngine is shown."""
        theme = self._settings.value("theme", "light")
        return theme if theme in {"light", "dark"} else "light"

    @Slot(result=str)
    def get_runtime_health_snapshot(self) -> str:
        """Return the controller-owned canonical runtime-health JSON payload."""
        return json.dumps(self._runtime_diagnostics.runtime_health_snapshot())

    # ------------------------------------------------------------- settings

    @Slot(str, str)
    def set_setting(self, key: str, value: str):
        self._settings.setValue(key, value)
        self._adapter.on_setting_changed(key, value)
        if key == "theme":
            # The native WebEngine surface has its own compositor background.
            # Re-emit the saved value so MainWindow can update that surface in
            # the same user-triggered theme transaction as the DOM.
            self.settings_changed.emit(json.dumps({"theme": self.initial_theme()}))

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
