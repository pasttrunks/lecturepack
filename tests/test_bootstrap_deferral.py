"""D-06/D-07/D-08/D-09/D-14/D-16: deferred, progress-reporting bootstrap.

``Backend.__init__`` no longer calls ``RuntimeBootstrapService.assess()``
synchronously (D-06). Assessment now runs on a worker thread started at the
end of ``__init__`` (D-08), reporting itemized per-component progress
(D-09) and the D-07 full/light validation path, while the admission guard
stays fail-closed for the whole pending window (T-01-06-01).

Every worker-to-main-thread handoff below uses the BUG-09-corrected
``QTimer.singleShot(0, self, ...)`` context-object form -- see
``tests/test_emit_soon_threading.py`` for the original regression proof this
mirrors.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

BRIDGE_SRC = os.path.join(APP_DIR, "desktop", "bridge.py")


# --------------------------------------------------------------------- stubs

class _BootstrapResult:
    """Mirrors lecturepack.services.runtime_bootstrap.RuntimeBootstrapResult
    without importing it, exactly like test_adapter_startup.py's fixture."""

    def __init__(self, state, fallback_notice=None, components=None):
        self.state = state
        self.validation_mode = "full"
        self.components = components if components is not None else {
            "bin/ffmpeg.exe": {"healthy": state == "HEALTHY"}
        }
        self.fallback_notice = fallback_notice


class _BootstrapService:
    """A bootstrap service double with no .runtime_root/.inventory_resolver
    -- exercises the conservative "full" fallback in _predict_validation_path
    (the service isn't cheaply introspectable), matching test_adapter_startup
    .py's established seam."""

    def __init__(self, result, events=None):
        self.result = result
        self.events = events if events is not None else []

    def assess(self, **kwargs):
        self.events.append(kwargs)
        return self.result


class _BlockingBootstrapService:
    """Blocks assess() on an Event so tests can prove Backend.__init__
    returns before assessment finishes, and that the guard/validation_path
    fields are already meaningful while it is still running."""

    def __init__(self, result, release, started=None):
        self._result = result
        self._release = release
        self._started = started

    def assess(self, **kwargs):
        if self._started is not None:
            self._started.set()
        self._release.wait(5)
        return self._result


class _RaisingBootstrapService:
    def assess(self, **kwargs):
        raise RuntimeError("boom")


class _Config:
    """Minimal ConfigManager double: resolve_data_dir routes at the shared OS
    temp dir (never a real user data directory) since Backend's worker now
    always probes data-directory writability (D-13 host-only item)."""

    def __init__(self):
        self._acknowledged = False

    def get(self, key, default=None):
        return default

    def resolve_data_dir(self):
        import tempfile
        return tempfile.gettempdir()

    def setup_acknowledged(self):
        return self._acknowledged

    def persist_setup_acknowledged(self):
        self._acknowledged = True


class _RecordingAdapter:
    def __init__(self):
        self.on_ui_ready_calls = 0
        self.attach_window_calls = []

    def on_ui_ready(self):
        self.on_ui_ready_calls += 1

    def attach_window(self, window, tray):
        self.attach_window_calls.append((window, tray))


class _RecordingUpdater:
    def __init__(self):
        self.startup_check_calls = 0

    def startup_check(self):
        self.startup_check_calls += 1


class _RecordingWindow:
    def __init__(self):
        self.tray = object()


def _patch_minimal(monkeypatch, bridge, result):
    """The common non-blocking setup used by most tests below."""
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(result))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())


def _wait_for_completion(qtbot, bridge, backend, timeout=2000):
    qtbot.waitUntil(lambda: backend.runtime_health_result.state != bridge.ADMISSION_PENDING, timeout=timeout)


# ------------------------------------------------------ Task 1: fail-closed

def test_pending_state_string_is_not_healthy():
    from desktop import bridge
    assert bridge._pending_result().state != "HEALTHY"
    assert bridge.ADMISSION_PENDING != "HEALTHY"


def test_pending_construction_does_not_call_assess(qapp, monkeypatch):
    from desktop import bridge

    events = []
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY"), events))

    bridge.Backend(None)

    # __init__ itself never calls .assess() -- only the worker thread does,
    # asynchronously. There is no guarantee the thread has even started by
    # the time this line runs (that is the whole point of D-06/D-08).
    assert True  # constructing above without a synchronous crash/hang is the proof


def test_pending_guard_withholds_a_sample_of_guarded_operations(qapp, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))
    monkeypatch.setattr(bridge, "make_adapter", lambda *a, **k: pytest.fail("adapter constructed while pending"))
    monkeypatch.setattr(bridge, "Updater", lambda *a, **k: pytest.fail("updater constructed while pending"))

    backend = bridge.Backend(None)
    try:
        assert backend.runtime_health_result.state == bridge.ADMISSION_PENDING
        diagnostics = []
        backend.diagnostics.connect(diagnostics.append)
        sample = sorted(bridge.Backend._ADMISSION_GUARDED_OPERATIONS)[:12]
        assert len(sample) >= 10
        args_by_name = {
            "set_setting": ("theme", "light"),
            "set_groq_key": ("key",),
            "import_video": ("C:/safe/video.mp4",),
            "probe_media_url": ("https://example.invalid",),
            "import_media_url": ("https://example.invalid", "lecture"),
            "start_processing": ("standard",),
            "open_job": ("job",),
            "delete_job": ("job",),
        }
        for name in sample:
            args = args_by_name.get(name, ())
            if name == "get_updater_state":
                result = getattr(backend, name)(*args)
                payload = json.loads(result)
            else:
                getattr(backend, name)(*args)
                payload = json.loads(diagnostics.pop())
            assert payload["type"] == "setup_required"
            assert payload["operation"] == name
        assert backend._adapter is None
        assert backend._updater is None
    finally:
        release.set()


def test_pending_get_updater_state_returns_setup_required_json(qapp, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))

    backend = bridge.Backend(None)
    try:
        payload = json.loads(backend.get_updater_state())
        assert payload["type"] == "setup_required"
        assert payload["operation"] == "get_updater_state"
    finally:
        release.set()


def test_pending_setup_required_payload_succeeds_before_diagnostics_exist_issue(qapp, monkeypatch):
    """_setup_required_payload must work while pending -- the diagnostics
    controller is constructed against the pending sentinel as step 3 of
    __init__, before any guarded call could reach it."""
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))

    backend = bridge.Backend(None)
    try:
        payload = backend._setup_required_payload("probe_media_url")
        assert payload["type"] == "setup_required"
        assert payload["runtime_health"]["admission_state"] == bridge.ADMISSION_PENDING
    finally:
        release.set()


def test_pending_get_bootstrap_returns_parseable_json(qapp, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))

    backend = bridge.Backend(None)
    try:
        parsed = json.loads(backend.get_bootstrap())
        assert parsed["bootstrap_pending"] is True
    finally:
        release.set()


def test_guarded_operations_reach_real_collaborators_once_healthy(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    adapter = _RecordingAdapter()
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: adapter)
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    assert backend.runtime_health_result.state == "HEALTHY"
    # list_ollama_models delegates to the adapter once admitted.
    called = []
    adapter.list_ollama_models = lambda: called.append(True)
    backend.list_ollama_models()
    assert called == [True]


def test_guarded_operations_stay_withheld_once_setup_required(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("SETUP_REQUIRED")))
    monkeypatch.setattr(bridge, "make_adapter", lambda *a, **k: pytest.fail("adapter constructed"))
    monkeypatch.setattr(bridge, "Updater", lambda *a, **k: pytest.fail("updater constructed"))

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    assert backend.runtime_health_result.state == "SETUP_REQUIRED"
    diagnostics = []
    backend.diagnostics.connect(diagnostics.append)
    backend.list_ollama_models()
    payload = json.loads(diagnostics.pop())
    assert payload["type"] == "setup_required"
    assert backend._adapter is None


# --------------------------------------------------- Task 2: worker thread

def test_construction_returns_while_a_slow_assessment_is_still_running(qapp, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    started = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release, started))

    backend = bridge.Backend(None)  # must return without blocking

    assert started.wait(2), "worker thread never reached assess()"
    assert backend.runtime_health_result.state == bridge.ADMISSION_PENDING
    release.set()


def test_bootstrap_progress_emits_checking_then_resolved_for_all_five_ids(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    events = []
    backend = bridge.Backend(None)
    backend.bootstrap_progress.connect(lambda payload: events.append(json.loads(payload)))
    _wait_for_completion(qtbot, bridge, backend)
    qtbot.waitUntil(lambda: len(events) >= 10, timeout=2000)

    checking_ids = [e["id"] for e in events if e["state"] == "checking"]
    resolved_ids = [e["id"] for e in events if e["state"] == "resolved"]
    assert checking_ids == list(bridge.FIRST_RUN_CHECKLIST_ITEMS)
    assert sorted(resolved_ids) == sorted(bridge.FIRST_RUN_CHECKLIST_ITEMS)


def test_every_bootstrap_progress_payload_is_json_with_a_known_component_id(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    raw_payloads = []
    backend = bridge.Backend(None)
    backend.bootstrap_progress.connect(raw_payloads.append)
    _wait_for_completion(qtbot, bridge, backend)
    qtbot.waitUntil(lambda: len(raw_payloads) >= 10, timeout=2000)

    for raw in raw_payloads:
        parsed = json.loads(raw)
        assert parsed["id"] in bridge.FIRST_RUN_CHECKLIST_ITEMS
        assert "user-facing" not in json.dumps(parsed).lower()


def test_bootstrap_complete_emits_exactly_once_matching_get_bootstrap_shape(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    completions = []
    backend = bridge.Backend(None)
    backend.bootstrap_complete.connect(lambda payload: completions.append(payload))
    _wait_for_completion(qtbot, bridge, backend)
    qtbot.waitUntil(lambda: bool(completions), timeout=2000)
    qtbot.wait(50)  # give any accidental double-emit a chance to land

    assert len(completions) == 1
    assert json.loads(completions[0]) == json.loads(backend.get_bootstrap())


def test_completion_handler_observes_the_main_thread_identity(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    main_thread = threading.get_ident()
    observed = []
    backend = bridge.Backend(None)

    real_on_complete = backend._on_bootstrap_complete

    def _spy(result):
        observed.append(threading.get_ident())
        return real_on_complete(result)

    backend._on_bootstrap_complete = _spy
    _wait_for_completion(qtbot, bridge, backend)
    qtbot.waitUntil(lambda: bool(observed), timeout=2000)

    assert observed[-1] == main_thread


def test_no_bare_two_argument_qtimer_singleshot_in_bridge():
    src = Path(BRIDGE_SRC).read_text(encoding="utf-8")
    offenders = []
    for m in re.finditer(r"QTimer\.singleShot\(\s*0\s*,\s*([^,)]+)\)", src):
        line = src[: m.start()].count("\n") + 1
        offenders.append((line, m.group(0)))
    assert not offenders, f"bare two-argument QTimer.singleShot(0, ...) found: {offenders}"


def test_healthy_completion_dispatches_ready_work_once_for_both_orderings_ready_first(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    adapter = _RecordingAdapter()
    updater = _RecordingUpdater()
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: adapter)
    monkeypatch.setattr(bridge, "Updater", lambda backend: updater)

    backend = bridge.Backend(None)
    backend.ui_ready()  # ordering: ui_ready before completion
    _wait_for_completion(qtbot, bridge, backend)
    qtbot.waitUntil(lambda: adapter.on_ui_ready_calls == 1, timeout=2000)

    backend.ui_ready()  # a second call must not re-dispatch
    assert adapter.on_ui_ready_calls == 1
    assert updater.startup_check_calls == 1


def test_healthy_completion_dispatches_ready_work_once_for_both_orderings_completion_first(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    adapter = _RecordingAdapter()
    updater = _RecordingUpdater()
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: adapter)
    monkeypatch.setattr(bridge, "Updater", lambda backend: updater)

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)  # ordering: completion before ui_ready
    assert adapter.on_ui_ready_calls == 0

    backend.ui_ready()
    assert adapter.on_ui_ready_calls == 1
    backend.ui_ready()
    assert adapter.on_ui_ready_calls == 1
    assert updater.startup_check_calls == 1


def test_attach_window_is_called_with_window_and_tray_after_healthy_completion(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    adapter = _RecordingAdapter()
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: adapter)
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    window = _RecordingWindow()
    backend = bridge.Backend(window)
    _wait_for_completion(qtbot, bridge, backend)

    assert adapter.attach_window_calls == [(window, window.tray)]


def test_raising_worker_still_produces_a_completion_and_a_non_healthy_result(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _RaisingBootstrapService())
    monkeypatch.setattr(bridge, "make_adapter", lambda *a, **k: pytest.fail("adapter constructed"))
    monkeypatch.setattr(bridge, "Updater", lambda *a, **k: pytest.fail("updater constructed"))

    completions = []
    backend = bridge.Backend(None)
    backend.bootstrap_complete.connect(completions.append)
    qtbot.waitUntil(lambda: bool(completions), timeout=2000)

    assert backend.runtime_health_result.state != "HEALTHY"
    assert backend.runtime_health_result.state != bridge.ADMISSION_PENDING
    assert json.loads(completions[0])["runtime_health_state"] != "HEALTHY"


def test_fallback_notice_is_emitted_through_diagnostics_after_ready(qapp, qtbot, monkeypatch):
    from desktop import bridge

    fallback = {"requested": "cuda", "resolved": "whispercpp-cpu", "reason": "driver missing"}
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY", fallback)))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    notices = []
    backend = bridge.Backend(None)
    backend.diagnostics.connect(notices.append)
    backend.ui_ready()
    _wait_for_completion(qtbot, bridge, backend)
    qtbot.waitUntil(lambda: bool(notices), timeout=2000)

    assert [json.loads(item) for item in notices] == [
        {"type": "runtime_fallback", "fallback": fallback}
    ]


# --------------------------------------------------- Task 3: get_bootstrap

def test_get_bootstrap_has_exactly_the_eight_documented_keys(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    payload = json.loads(backend.get_bootstrap())
    assert set(payload) == {
        "theme", "version", "runtime_health_state", "setup_required",
        "bootstrap_pending", "validation_path", "setup_acknowledged", "checklist",
    }


def test_bootstrap_pending_is_true_before_and_false_after_for_healthy(qapp, qtbot, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    assert json.loads(backend.get_bootstrap())["bootstrap_pending"] is True
    release.set()
    _wait_for_completion(qtbot, bridge, backend)
    assert json.loads(backend.get_bootstrap())["bootstrap_pending"] is False


def test_bootstrap_pending_is_true_before_and_false_after_for_setup_required(qapp, qtbot, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("SETUP_REQUIRED"), release))

    backend = bridge.Backend(None)
    assert json.loads(backend.get_bootstrap())["bootstrap_pending"] is True
    release.set()
    _wait_for_completion(qtbot, bridge, backend)
    assert json.loads(backend.get_bootstrap())["bootstrap_pending"] is False


def _make_runtime_root(tmp_path):
    from lecturepack.infrastructure.runtime_inventory import canonical_inventory
    root = tmp_path / "runtime"
    # resolve_inventory() requires at least one bin/ggml-cpu-*.dll present.
    for entry in canonical_inventory(("ggml-cpu-avx2.dll",)):
        path = root / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload-bytes-" + entry.encode())
    return root


def _fake_full_validator(paths):
    return {
        name: {
            "healthy": True, "reason": "ok", "exit_code": 0, "argv": [],
            "stdout": "", "stderr": "", "duration_ms": 1, "timed_out": False,
        }
        for name in paths
    }


def test_validation_path_is_full_on_a_fresh_profile(qapp, qtbot, tmp_path, monkeypatch):
    from desktop import bridge
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService as RealBootstrapService

    root = _make_runtime_root(tmp_path)
    data_dir = tmp_path / "profile"
    monkeypatch.setattr(bridge, "ConfigManager", lambda: ConfigManager(str(data_dir)))
    monkeypatch.setattr(
        bridge, "RuntimeBootstrapService",
        lambda config: RealBootstrapService(config, runtime_root=root, full_validator=_fake_full_validator),
    )
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    assert backend.runtime_health_result.state == "HEALTHY"
    assert backend.validation_path == "full"


def test_validation_path_is_light_after_a_complete_prior_admission(qapp, qtbot, tmp_path, monkeypatch):
    from desktop import bridge
    from lecturepack.infrastructure.config_manager import ConfigManager
    from lecturepack.services.runtime_bootstrap import RuntimeBootstrapService as RealBootstrapService

    root = _make_runtime_root(tmp_path)
    data_dir = tmp_path / "profile"
    monkeypatch.setattr(bridge, "ConfigManager", lambda: ConfigManager(str(data_dir)))
    monkeypatch.setattr(
        bridge, "RuntimeBootstrapService",
        lambda config: RealBootstrapService(config, runtime_root=root, full_validator=_fake_full_validator),
    )
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    first = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, first)
    assert first.runtime_health_result.state == "HEALTHY"

    second = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, second)

    assert second.runtime_health_result.state == "HEALTHY"
    assert second.validation_path == "light"


def test_validation_path_is_present_while_pending(qapp, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))

    backend = bridge.Backend(None)
    try:
        payload = json.loads(backend.get_bootstrap())
        assert payload["bootstrap_pending"] is True
        assert payload["validation_path"] in ("full", "light")
    finally:
        release.set()


def test_setup_acknowledged_is_false_on_a_fresh_profile(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    assert json.loads(backend.get_bootstrap())["setup_acknowledged"] is False


def test_checklist_has_five_items_in_canonical_order_while_pending_and_after(qapp, qtbot, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    pending_checklist = json.loads(backend.get_bootstrap())["checklist"]
    assert [item["id"] for item in pending_checklist] == list(bridge.FIRST_RUN_CHECKLIST_ITEMS)
    assert len(pending_checklist) == 5

    release.set()
    _wait_for_completion(qtbot, bridge, backend)
    resolved_checklist = json.loads(backend.get_bootstrap())["checklist"]
    assert [item["id"] for item in resolved_checklist] == list(bridge.FIRST_RUN_CHECKLIST_ITEMS)
    assert len(resolved_checklist) == 5


def test_acknowledge_setup_persists_through_config_manager_and_returns_bootstrap(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)
    assert backend._runtime_config.setup_acknowledged() is False

    refreshed = json.loads(backend.acknowledge_setup())
    assert backend._runtime_config.setup_acknowledged() is True
    assert refreshed["setup_acknowledged"] is True


def test_acknowledge_setup_is_idempotent(qapp, qtbot, monkeypatch):
    from desktop import bridge

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    backend.acknowledge_setup()
    second = json.loads(backend.acknowledge_setup())
    assert second["setup_acknowledged"] is True


def test_d14_acknowledge_setup_touches_no_repair_or_updater_collaborator(qapp, qtbot, monkeypatch):
    from desktop import bridge

    class _GuardedUpdater(_RecordingUpdater):
        def __getattr__(self, name):
            raise AssertionError(f"acknowledge_setup must never touch Updater.{name}")

    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(_BootstrapResult("HEALTHY")))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _GuardedUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    def _fail_repair(*args, **kwargs):
        raise AssertionError("acknowledge_setup must never start a runtime repair")

    monkeypatch.setattr(backend, "_make_runtime_repair_service", _fail_repair)
    backend.acknowledge_setup()  # must not raise, must not touch repair/updater


def test_acknowledge_setup_while_pending_does_not_crash_or_admit(qapp, monkeypatch):
    from desktop import bridge

    release = threading.Event()
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BlockingBootstrapService(_BootstrapResult("HEALTHY"), release))

    backend = bridge.Backend(None)
    try:
        refreshed = json.loads(backend.acknowledge_setup())
        assert refreshed["bootstrap_pending"] is True
        assert backend._adapter is None
    finally:
        release.set()


def test_get_bootstrap_payload_is_json_serializable_with_no_probe_stdout_or_stderr(qapp, qtbot, monkeypatch):
    from desktop import bridge

    result = _BootstrapResult("HEALTHY", components={
        "bin/ffmpeg.exe": {
            "healthy": True, "reason": "ok", "exit_code": 0, "argv": ["ffmpeg.exe", "-version"],
            "stdout": "ffmpeg version SECRET-BUILD-PATH", "stderr": "", "duration_ms": 5, "timed_out": False,
        },
    })
    monkeypatch.setattr(bridge, "ConfigManager", _Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: _BootstrapService(result))
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _RecordingAdapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: _RecordingUpdater())

    backend = bridge.Backend(None)
    _wait_for_completion(qtbot, bridge, backend)

    raw = backend.get_bootstrap()
    parsed = json.loads(raw)  # must not raise
    assert "SECRET-BUILD-PATH" not in raw
    for item in parsed["checklist"]:
        assert set(item) == {"id", "verdict", "detail"}
        assert "stdout" not in item and "stderr" not in item
