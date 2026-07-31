"""Integration smoke test: the real LecturePackAdapter constructs and wires all
beta.3 services (WindowsIntegration + JobQueue + controller signal hookup) under
an offscreen Qt app, against a TEMP data dir — never real ~/LecturePackData.

Catches startup breakage introduced by the adapter/bridge wiring without needing
a visible window or the packaged build."""

import os
import sys
import json

import pytest


class _BootstrapResult:
    def __init__(self, state, fallback_notice=None):
        self.state = state
        self.validation_mode = "full"
        self.components = {"bin/ffmpeg.exe": {"healthy": state == "HEALTHY"}}
        self.fallback_notice = fallback_notice


class _BootstrapService:
    def __init__(self, result, events):
        self.result = result
        self.events = events

    def assess(self):
        self.events.append("assess")
        return self.result


class _RuntimeConfig:
    def get(self, key, default=None):
        return default

    def resolve_data_dir(self):
        # 01-06: Backend now probes data-directory writability off the main
        # thread on every construction (D-13 host-only checklist item). Route
        # this minimal stub at the shared OS temp dir -- never a real user
        # data directory -- so the probe file it writes-and-deletes is
        # harmless regardless of which test constructs a Backend with this
        # stub.
        import tempfile
        return tempfile.gettempdir()

    def setup_acknowledged(self):
        return False

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


@pytest.fixture
def _temp_data_dir(tmp_path, monkeypatch):
    """Point ConfigManager's default at a temp dir so constructing the real
    adapter can't read or write the user's real LecturePackData."""
    import lecturepack.constants as constants
    import lecturepack.infrastructure.config_manager as cm
    monkeypatch.setattr(constants, "DEFAULT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cm, "DEFAULT_DATA_DIR", str(tmp_path))
    return str(tmp_path)


class _FakeBackend:
    """Minimal backend: any attribute access returns a signal-like recorder."""
    class _Sig:
        def __init__(self): self.emissions = []
        def emit(self, payload): self.emissions.append(payload)
    def __init__(self):
        self._sigs = {}
    def __getattr__(self, name):
        # QObject signals are attributes; hand back a recorder for any of them.
        sig = self.__dict__.setdefault("_sigs", {}).get(name)
        if sig is None:
            sig = _FakeBackend._Sig()
            self._sigs[name] = sig
        return sig


def test_real_adapter_constructs_and_wires(qapp, _temp_data_dir):
    from desktop import engine_adapter as ea
    adapter = ea.LecturePackAdapter(_FakeBackend())
    # beta.3 services present
    assert adapter.win is not None
    assert adapter.queue is not None
    assert adapter._session_id
    # queue store landed in the TEMP dir, not the real data dir
    assert os.path.dirname(adapter.queue.path) == _temp_data_dir
    assert _temp_data_dir in adapter.config.data_dir or adapter.config.data_dir == _temp_data_dir
    # new control surface is callable without a job (no crash / no active job)
    adapter.get_notification_prefs()
    adapter.enqueue_job("j1")
    assert "j1" in adapter.queue.queued()
    adapter.pause_job()  # no active stage -> safe no-op


def test_adapter_never_targets_real_data_dir(qapp, _temp_data_dir):
    from desktop import engine_adapter as ea
    adapter = ea.LecturePackAdapter(_FakeBackend())
    real = os.path.expanduser(os.path.join("~", "LecturePackData"))
    assert os.path.abspath(adapter.config.data_dir) != os.path.abspath(real)


def test_backend_admits_adapter_once_only_after_healthy_assessment(qapp, qtbot, monkeypatch):
    from desktop import bridge

    events = []
    adapter = object()
    monkeypatch.setattr(bridge, "ConfigManager", lambda: events.append("config") or object())
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY"), events))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: events.append("adapter") or adapter)
    monkeypatch.setattr(bridge, "Updater", lambda backend: object())

    backend = bridge.Backend(None)
    # 01-06: assess() now runs on a worker thread and the completion handler
    # is marshalled onto the main thread (D-06/D-08); pump the event loop
    # until that marshal has landed instead of asserting immediately.
    qtbot.waitUntil(lambda: backend.runtime_health_result.state != bridge.ADMISSION_PENDING, timeout=2000)

    assert backend._adapter is adapter
    assert backend.runtime_health_result.state == "HEALTHY"
    assert events == ["config", "assess", "adapter"]


def test_backend_blocks_normal_adapter_and_ready_event_until_healthy(qapp, qtbot, monkeypatch):
    from desktop import bridge

    events = []
    monkeypatch.setattr(bridge, "ConfigManager", _RuntimeConfig)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("SETUP_REQUIRED"), events))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: events.append("adapter"))
    monkeypatch.setattr(bridge, "Updater", lambda backend: object())

    backend = bridge.Backend(None)
    # ui_ready is no longer admission-guarded (T-01-06): it must be callable,
    # and safely a no-op, at any point during the pending window.
    backend.ui_ready()
    qtbot.waitUntil(lambda: backend.runtime_health_result.state != bridge.ADMISSION_PENDING, timeout=2000)

    assert backend._adapter is None
    assert events == ["assess"]
    assert backend.runtime_health_result.state == "SETUP_REQUIRED"


def test_optional_fallback_is_post_health_and_distinct_from_ready(qapp, qtbot, monkeypatch):
    from desktop import bridge

    events = []
    fallback = {"requested": "cuda", "resolved": "whispercpp-cpu", "reason": "driver missing"}

    class _Adapter:
        def on_ui_ready(self):
            events.append("ready")
        def attach_window(self, window, tray):
            pass

    monkeypatch.setattr(bridge, "ConfigManager", _RuntimeConfig)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY", fallback), events))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: events.append("adapter") or _Adapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: type("_Updater", (), {"startup_check": lambda self: None})())

    backend = bridge.Backend(None)
    notices = []
    backend.diagnostics.connect(notices.append)
    # ui_ready is called before completion here, on purpose: it must be
    # recorded and dispatched once completion later promotes the adapter
    # (T-01-06-06), which is exactly the ordering the real WebChannel
    # handshake produces during a cold, deferred-assessment launch.
    backend.ui_ready()
    qtbot.waitUntil(lambda: events == ["assess", "adapter", "ready"], timeout=2000)

    assert [__import__("json").loads(item) for item in notices] == [
        {"type": "runtime_fallback", "fallback": fallback}
    ]


_GUARDED_BRIDGE_CALLS = (
    # ui_ready is deliberately excluded (T-01-06): it is no longer admission-
    # guarded, because it must always run to record readiness even while
    # assessment is pending (see Backend.ui_ready).
    ("set_setting", ("theme", "light")), ("browse_model", ()),
    ("test_endpoint", ()), ("validate_vulkan", ()), ("validate_cuda", ()),
    ("cuda_pack_status", ()), ("install_cuda_pack", ()), ("cancel_cuda_pack", ()),
    ("set_groq_key", ("key",)), ("remove_groq_key", ()), ("test_groq_key", ()),
    ("list_ollama_models", ()), ("smart_study_status", ()),
    ("set_study_preset", ("standard",)), ("install_smart_study", ("standard",)),
    ("cancel_smart_study", ()), ("launch_ollama_installer", ()), ("save_project", ()),
    ("browse_video", ()), ("import_video", ("C:/safe/video.mp4",)), ("notify_drag_over", ()),
    ("media_link_support", ()), ("probe_media_url", ("https://example.invalid",)),
    ("import_media_url", ("https://example.invalid", "lecture")), ("cancel_media_url", ()),
    ("start_processing", ("standard",)), ("open_job", ("job",)), ("delete_job", ("job",)),
    ("set_job_group", ("job", "group")), ("delete_jobs", ("[]",)),
    ("set_jobs_group", ("[]", "group")), ("cancel_job", ()), ("pause_job", ()),
    ("resume_job", ("job",)), ("restart_job", ("job",)), ("retry_stage", ("job", "inspect")),
    ("enqueue_job", ("job",)), ("reorder_queue", ("job", 0)), ("run_now", ("job",)),
    ("remove_from_queue", ("job",)), ("schedule_job", ("job", "tomorrow", "UTC", "skip")),
    ("unschedule_job", ("job",)), ("get_notification_prefs", ()),
    ("set_notification_prefs", ("{}",)), ("test_notification", ()),
    ("run_diagnostics", ("job",)), ("open_job_folder", ("job",)), ("get_post_completion", ()),
    ("set_slide_state", (0, "accepted")), ("save_corrections", ("{}",)),
    ("repair_selection", ()), ("ask_ai", ("prompt",)), ("generate_quiz", ("{}",)),
    ("cancel_quiz", ()), ("save_quiz_session", ("{}",)), ("generate_flashcards", ("{}",)),
    ("cancel_flashcards", ()), ("save_flashcard_session", ("{}",)), ("save_notes", ("notes",)),
    ("export_all", ("[]",)), ("export_one", ("pdf",)), ("open_export_folder", ()),
    ("check_updates", ()), ("get_updater_state", ()), ("start_update_download", ()),
    ("cancel_update_download", ()), ("install_downloaded_update", ()),
    ("open_release_page", ()), ("set_update_channel", ("beta",)), ("set_auto_check", ("true",)),
    ("skip_update_version", ()), ("clear_skipped_version", ()), ("install_update", ()),
    ("whatsnew_seen", ()),
)


def test_setup_required_guards_every_adapter_and_updater_bridge_call(qapp, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _RuntimeConfig)
    monkeypatch.setattr(
        bridge, "RuntimeBootstrapService",
        lambda config: _BootstrapService(_BootstrapResult("SETUP_REQUIRED"), []),
    )
    monkeypatch.setattr(bridge, "make_adapter", lambda *args, **kwargs: pytest.fail("adapter constructed"))
    monkeypatch.setattr(bridge, "Updater", lambda *args, **kwargs: pytest.fail("updater constructed"))
    backend = bridge.Backend(None)
    diagnostics = []
    backend.diagnostics.connect(diagnostics.append)

    for operation, args in _GUARDED_BRIDGE_CALLS:
        result = getattr(backend, operation)(*args)
        payload = json.loads(result) if operation == "get_updater_state" else json.loads(diagnostics.pop())
        assert payload == {
            "type": "setup_required",
            "operation": operation,
            "runtime_health": json.loads(backend.get_runtime_health_snapshot()),
        }
        assert backend._adapter is None
        assert backend._updater is None


def test_setup_required_bootstrap_reuses_canonical_admission_snapshot(qapp, qtbot, monkeypatch):
    from desktop import bridge

    snapshot = {"inventory_identity": "canonical", "admission_state": "SETUP_REQUIRED", "components": {}}

    class _Controller:
        def runtime_health_snapshot(self):
            return snapshot

    monkeypatch.setattr(bridge, "ConfigManager", _RuntimeConfig)
    monkeypatch.setattr(
        bridge, "RuntimeBootstrapService",
        lambda config: _BootstrapService(_BootstrapResult("SETUP_REQUIRED"), []),
    )
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsService", lambda config, result: object())
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsController", lambda service: _Controller())

    backend = bridge.Backend(None)
    # 01-06: bootstrap_pending only becomes False once the deferred
    # assessment has actually completed and been marshalled back.
    qtbot.waitUntil(lambda: backend.runtime_health_result.state != bridge.ADMISSION_PENDING, timeout=2000)

    bootstrap = json.loads(backend.get_bootstrap())
    assert bootstrap == {
        "theme": bootstrap["theme"],
        "version": bridge.version.__version__,
        "runtime_health_state": "SETUP_REQUIRED",
        "setup_required": snapshot,
        "bootstrap_pending": False,
        "validation_path": bootstrap["validation_path"],
        "setup_acknowledged": False,
        "checklist": bootstrap["checklist"],
    }
    assert bootstrap["validation_path"] in ("full", "light")
    assert [item["id"] for item in bootstrap["checklist"]] == list(bridge.FIRST_RUN_CHECKLIST_ITEMS)
    assert json.loads(backend.get_runtime_health_snapshot()) == snapshot


def test_setup_required_guard_applies_to_qt_slot_dispatch(qapp, monkeypatch):
    from PySide6.QtCore import QMetaObject, Qt, Q_ARG
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _RuntimeConfig)
    monkeypatch.setattr(
        bridge, "RuntimeBootstrapService",
        lambda config: _BootstrapService(_BootstrapResult("SETUP_REQUIRED"), []),
    )
    backend = bridge.Backend(None)
    diagnostics = []
    backend.diagnostics.connect(diagnostics.append)

    assert QMetaObject.invokeMethod(
        backend, "set_setting", Qt.ConnectionType.DirectConnection,
        Q_ARG(str, "theme"), Q_ARG(str, "light"),
    )
    assert json.loads(diagnostics.pop())["operation"] == "set_setting"
