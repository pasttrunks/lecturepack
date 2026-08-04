"""Focused tests for Phase 9 Feature Group 3: settings persistence."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402


@pytest.fixture
def config(tmp_path: Path) -> ConfigManager:
    return ConfigManager(str(tmp_path))


def test_config_persists_engine(config: ConfigManager):
    config.set("engine", "cpu")
    reloaded = ConfigManager(config.data_dir)
    assert reloaded.get("engine") == "cpu"


def test_config_persists_transcription_backend(config: ConfigManager):
    config.set("transcription_backend", "local-whispercpp")
    reloaded = ConfigManager(config.data_dir)
    assert reloaded.get("transcription_backend") == "local-whispercpp"


def test_config_persists_slide_detection_preset(config: ConfigManager):
    config.set("slide_detection_preset", "detailed")
    reloaded = ConfigManager(config.data_dir)
    assert reloaded.get("slide_detection_preset") == "detailed"


def test_config_persists_ollama_settings(config: ConfigManager):
    config.set("ollama", {"base_url": "http://localhost:11434", "model": "llama3"})
    reloaded = ConfigManager(config.data_dir)
    o = reloaded.get("ollama") or {}
    assert o.get("base_url") == "http://localhost:11434"
    assert o.get("model") == "llama3"


def test_config_persists_whisper_model(config: ConfigManager):
    config.set("whisper_model", "C:/models/ggml-base.en.bin")
    reloaded = ConfigManager(config.data_dir)
    assert reloaded.get("whisper_model") == "C:/models/ggml-base.en.bin"


def test_config_defaults(config: ConfigManager):
    assert config.get("engine", "auto") == "auto"
    assert config.get("transcription_backend", "local-whispercpp") == "local-whispercpp"
    assert config.get("slide_detection_preset", "balanced") == "balanced"