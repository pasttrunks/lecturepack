"""Focused tests for Phase 9 Feature Group 5: runtime/diagnostics backend."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402
from lecturepack.services.job_ops import build_diagnostics  # noqa: E402


@pytest.fixture
def config(tmp_path: Path) -> ConfigManager:
    return ConfigManager(str(tmp_path))


def test_build_diagnostics_shape():
    diag = build_diagnostics(
        app_version="0.0.0",
        job_id="job-1",
        stage="Transcribe",
        status="failed",
        error="boom",
        exit_code=None,
        timestamp="2026-01-01T00:00:00",
        runtime_paths={"whisper_exe": "C:/bin/whisper.exe", "data_dir": "C:/data"},
    )
    assert isinstance(diag, dict)
    assert diag.get("job_id") == "job-1"
    assert "version" in diag or "app_version" in diag


def test_notification_prefs_persist(config: ConfigManager):
    config.set("notifications", {"job_completed": True, "job_failed": False})
    reloaded = ConfigManager(config.data_dir)
    prefs = reloaded.get("notifications") or {}
    assert prefs.get("job_completed") is True
    assert prefs.get("job_failed") is False


def test_notification_prefs_default_empty(config: ConfigManager):
    prefs = config.get("notifications", None)
    assert prefs is None or prefs == {}


def test_engine_registry_resolves(config: ConfigManager):
    from lecturepack.infrastructure.transcription_engines import EngineRegistry
    reg = EngineRegistry(config)
    resolved = reg.resolve(config.get("engine", "auto"))
    assert resolved.key
    assert resolved.backend
