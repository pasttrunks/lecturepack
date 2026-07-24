"""Integration smoke test: the real LecturePackAdapter constructs and wires all
beta.3 services (WindowsIntegration + JobQueue + controller signal hookup) under
an offscreen Qt app, against a TEMP data dir — never real ~/LecturePackData.

Catches startup breakage introduced by the adapter/bridge wiring without needing
a visible window or the packaged build."""

import os
import sys

import pytest

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
