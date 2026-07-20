"""Tests for the Settings -> engine-config bridge (P0.3 / P0.4 / P1.4).

The desktop Backend persists UI settings in QSettings, but the engine reads its
own config.json. LecturePackAdapter.on_setting_changed is the bridge that makes
the compute engine (CPU/Vulkan), endpoint, model path and Ollama model chosen in
Settings actually reach processing/AI. Without it, selecting Vulkan does nothing.

We construct the adapter via __new__ (skipping the heavy __init__, which would
otherwise point ConfigManager at the real ~/LecturePackData) and attach a temp
ConfigManager + a fake backend, so only the pure bridge logic is exercised.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    def __init__(self):
        self.log_line = _Signal()
        self.settings_changed = _Signal()
        self.ai_status = _Signal()
        self.ollama_models = _Signal()


def _make_adapter(tmp_path):
    adapter = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    adapter.config = ConfigManager(str(tmp_path))
    adapter.backend = _FakeBackend()
    return adapter


def _last_settings(adapter):
    return json.loads(adapter.backend.settings_changed.emissions[-1])


# ------------------------------------------------------------- compute engine
@pytest.mark.parametrize("value", ["cpu", "vulkan", "auto"])
def test_engine_selection_persists(tmp_path, value):
    a = _make_adapter(tmp_path)
    a.on_setting_changed("engine", value)
    assert a.config.get("engine") == value
    # Survives a fresh load of the same config.json.
    assert ConfigManager(str(tmp_path)).get("engine") == value
    assert _last_settings(a)["engine"] == value


def test_invalid_engine_falls_back_to_auto(tmp_path):
    a = _make_adapter(tmp_path)
    a.on_setting_changed("engine", "cuda-nonsense")
    assert a.config.get("engine") == "auto"


# ------------------------------------------------------------- ollama endpoint/model
def test_ollama_base_url_persists(tmp_path):
    a = _make_adapter(tmp_path)
    a.on_setting_changed("ollama_base_url", "http://localhost:1234")
    assert a.config.get("ollama")["base_url"] == "http://localhost:1234"
    assert _last_settings(a)["endpoint"] == "http://localhost:1234"


def test_ollama_model_persists_and_preserves_base_url(tmp_path):
    a = _make_adapter(tmp_path)
    a.on_setting_changed("ollama_base_url", "http://host:5")
    a.on_setting_changed("ollama_model", "llama3:8b")
    o = a.config.get("ollama")
    assert o["model"] == "llama3:8b"
    assert o["base_url"] == "http://host:5"  # not clobbered
    assert _last_settings(a)["ollama_model"] == "llama3:8b"


def test_whisper_model_persists(tmp_path):
    a = _make_adapter(tmp_path)
    a.on_setting_changed("whisper_model", r"C:\models\ggml-base.en.bin")
    assert a.config.get("whisper_model") == r"C:\models\ggml-base.en.bin"


def test_theme_is_ui_only_no_config_write(tmp_path):
    a = _make_adapter(tmp_path)
    before = dict(a.config.settings)
    a.on_setting_changed("theme", "light")
    assert a.config.settings == before  # engine config untouched


def test_open_missing_job_is_safe(tmp_path):
    # Opening a non-existent job must not raise or set current_job; it logs.
    a = _make_adapter(tmp_path)
    a.current_job = None
    a.open_job("does-not-exist")
    assert a.current_job is None
    logs = " ".join(a.backend.log_line.emissions)
    assert "not found" in logs


def test_settings_payload_reflects_config(tmp_path):
    a = _make_adapter(tmp_path)
    a.config.set("engine", "vulkan")
    a.config.set("ollama", {"base_url": "http://h:1", "model": "m1"})
    p = a._settings_payload()
    assert p["engine"] == "vulkan"
    assert p["endpoint"] == "http://h:1"
    assert p["ollama_model"] == "m1"
