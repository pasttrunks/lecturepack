"""Vulkan validation reporting (§3).

validate_vulkan must report the honest compute-backend state (available /
selected / loaded / unavailable-with-reason) from the engine registry — never
silently claim CPU. Registry is monkeypatched so the test is machine-independent.
"""
from __future__ import annotations

import json
import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from lecturepack.infrastructure import transcription_engines as te  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, p):
        self.emissions.append(p)


class _FakeBackend:
    def __init__(self):
        self.vulkan_status = _Signal()
        self.log_line = _Signal()


def _adapter(tmp_path):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    return a


def test_validate_vulkan_available_and_selected(tmp_path, monkeypatch):
    a = _adapter(tmp_path)
    a.config.set("engine", "vulkan")
    a.config.set("vulkan_benchmark_ok", True)
    vk = te.EngineInfo(key=te.ENGINE_VULKAN, label="whisper.cpp — Vulkan GPU",
                       available=True, backend="Vulkan")
    monkeypatch.setattr(te.EngineRegistry, "detect_engines",
                        lambda self: {te.ENGINE_VULKAN: vk})
    monkeypatch.setattr(te.EngineRegistry, "resolve",
                        lambda self, requested=te.ENGINE_AUTO: vk)
    a.validate_vulkan()
    d = json.loads(a.backend.vulkan_status.emissions[-1])
    assert d["state"] == "loaded"
    assert d["available"] is True and d["selected"] is True
    assert d["resolved_backend"] == "Vulkan"


def test_validate_vulkan_available_but_not_selected(tmp_path, monkeypatch):
    a = _adapter(tmp_path)
    a.config.set("engine", "cpu")
    vk = te.EngineInfo(key=te.ENGINE_VULKAN, label="Vulkan", available=True, backend="Vulkan")
    cpu = te.EngineInfo(key=te.ENGINE_CPU, label="CPU", available=True, backend="CPU")
    monkeypatch.setattr(te.EngineRegistry, "detect_engines",
                        lambda self: {te.ENGINE_VULKAN: vk})
    monkeypatch.setattr(te.EngineRegistry, "resolve",
                        lambda self, requested=te.ENGINE_AUTO: cpu)
    a.validate_vulkan()
    d = json.loads(a.backend.vulkan_status.emissions[-1])
    assert d["state"] == "available" and d["selected"] is False
    assert "CPU" in d["message"]


def test_validate_vulkan_unavailable_shows_reason(tmp_path, monkeypatch):
    a = _adapter(tmp_path)
    vk = te.EngineInfo(key=te.ENGINE_VULKAN, label="Vulkan", available=False,
                       backend="Vulkan", reason="No Vulkan runtime (vulkan-1.dll) on this system")
    cpu = te.EngineInfo(key=te.ENGINE_CPU, label="CPU", available=True, backend="CPU")
    monkeypatch.setattr(te.EngineRegistry, "detect_engines",
                        lambda self: {te.ENGINE_VULKAN: vk})
    monkeypatch.setattr(te.EngineRegistry, "resolve",
                        lambda self, requested=te.ENGINE_AUTO: cpu)
    a.validate_vulkan()
    d = json.loads(a.backend.vulkan_status.emissions[-1])
    assert d["state"] == "unavailable"
    assert "No Vulkan runtime" in d["message"]
