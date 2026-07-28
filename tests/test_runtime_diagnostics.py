"""Canonical runtime-health diagnostics transport contracts."""

import json
import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class _Config:
    def __init__(self):
        self.health = {
            "identity": "canonical-payload-v1",
            "components": {"bin/ffmpeg.exe": {"healthy": True, "reason": "success"}},
        }

    def get(self, key, default=None):
        return self.health if key == "runtime_health" else default


class _Result:
    state = "HEALTHY"
    validation_mode = "full"
    components = {"bin/ffmpeg.exe": {"healthy": True, "reason": "success"}}
    fallback_notice = {"requested": "cuda", "resolved": "whispercpp-cpu", "reason": "driver missing"}


def test_diagnostics_snapshot_uses_bootstrap_evidence_and_persisted_identity_only():
    from lecturepack.services.runtime_diagnostics import RuntimeDiagnosticsService

    snapshot = RuntimeDiagnosticsService(_Config(), _Result()).runtime_health_snapshot()

    assert snapshot == {
        "inventory_identity": "canonical-payload-v1",
        "admission_state": "HEALTHY",
        "validation_mode": "full",
        "components": {"bin/ffmpeg.exe": {"healthy": True, "reason": "success"}},
        "fallback_notice": {"requested": "cuda", "resolved": "whispercpp-cpu", "reason": "driver missing"},
    }


def test_adapter_and_bridge_transport_the_controller_snapshot_without_inventory_discovery(qapp, monkeypatch):
    from desktop import bridge

    snapshot = {"inventory_identity": "canonical-payload-v1", "admission_state": "HEALTHY", "components": {}}

    class _Controller:
        def runtime_health_snapshot(self):
            return snapshot

    class _Adapter:
        def runtime_health_snapshot(self):
            return snapshot

    class _Result:
        state = "HEALTHY"
        validation_mode = "full"
        components = {}
        fallback_notice = None

    monkeypatch.setattr(bridge, "ConfigManager", lambda: object())
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", lambda config: type("_Bootstrap", (), {"assess": lambda self: _Result()})())
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsService", lambda config, result: object())
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsController", lambda service: _Controller())
    monkeypatch.setattr(bridge, "make_adapter", lambda backend, **kwargs: _Adapter())
    monkeypatch.setattr(bridge, "Updater", lambda backend: object())

    backend = bridge.Backend(None)

    assert json.loads(backend.get_runtime_health_snapshot()) == snapshot
