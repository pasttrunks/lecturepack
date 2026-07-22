"""CUDA (NVIDIA GPU) transcription engine — registry + adapter reporting.

Machine-independent: the CUDA binary path and NVIDIA-driver probe are
monkeypatched, so these pass with or without a real GPU/binary present.
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


def _reg(tmp_path, *, cuda_exe="", nvidia=False, vulkan_exe="", cpu_exe="cpu.exe", monkeypatch=None):
    cfg = ConfigManager(str(tmp_path))
    reg = te.EngineRegistry(cfg)
    monkeypatch.setattr(reg, "_cpu_exe", lambda: cpu_exe)
    monkeypatch.setattr(reg, "_vulkan_exe", lambda: vulkan_exe)
    monkeypatch.setattr(reg, "_cuda_exe", lambda: cuda_exe)
    monkeypatch.setattr(te, "nvidia_cuda_present", lambda: nvidia)
    monkeypatch.setattr(te, "vulkan_runtime_present", lambda: bool(vulkan_exe))
    return cfg, reg


def test_cuda_unavailable_without_binary(tmp_path, monkeypatch):
    _, reg = _reg(tmp_path, cuda_exe="", nvidia=True, monkeypatch=monkeypatch)
    cuda = reg.detect_engines()[te.ENGINE_CUDA]
    assert cuda.available is False and "not installed" in cuda.reason


def test_cuda_unavailable_without_driver(tmp_path, monkeypatch):
    _, reg = _reg(tmp_path, cuda_exe="C:/x/cuda/whisper-cli.exe", nvidia=False, monkeypatch=monkeypatch)
    cuda = reg.detect_engines()[te.ENGINE_CUDA]
    assert cuda.available is False and "nvcuda.dll" in cuda.reason


def test_cuda_available_with_binary_and_driver(tmp_path, monkeypatch):
    _, reg = _reg(tmp_path, cuda_exe="C:/x/cuda/whisper-cli.exe", nvidia=True, monkeypatch=monkeypatch)
    cuda = reg.detect_engines()[te.ENGINE_CUDA]
    assert cuda.available is True and cuda.backend == "CUDA"


def test_explicit_cuda_selected_when_available(tmp_path, monkeypatch):
    _, reg = _reg(tmp_path, cuda_exe="C:/x/cuda/whisper-cli.exe", nvidia=True, monkeypatch=monkeypatch)
    r = reg.resolve(te.ENGINE_CUDA)
    assert r.key == te.ENGINE_CUDA and "explicitly selected" in r.reason


def test_explicit_cuda_falls_back_to_cpu_when_unavailable(tmp_path, monkeypatch):
    _, reg = _reg(tmp_path, cuda_exe="", nvidia=False, monkeypatch=monkeypatch)
    r = reg.resolve(te.ENGINE_CUDA)
    assert r.key == te.ENGINE_CPU and "CUDA requested but unavailable" in r.reason


def test_auto_prefers_cuda_only_after_benchmark(tmp_path, monkeypatch):
    cfg, reg = _reg(tmp_path, cuda_exe="C:/x/cuda/whisper-cli.exe", nvidia=True, monkeypatch=monkeypatch)
    # Available but not benchmarked -> stays on verified CPU.
    assert reg.resolve(te.ENGINE_AUTO).key == te.ENGINE_CPU
    cfg.set("cuda_benchmark_ok", True)
    assert reg.resolve(te.ENGINE_AUTO).key == te.ENGINE_CUDA


def test_short_aliases_honour_explicit_selection(tmp_path, monkeypatch):
    # WebEngine UI stores short names; explicit "cpu" must force CPU even when a
    # benchmarked GPU is available (regression: it used to fall through to auto).
    cfg, reg = _reg(tmp_path, cuda_exe="C:/x/cuda/whisper-cli.exe", nvidia=True, monkeypatch=monkeypatch)
    cfg.set("cuda_benchmark_ok", True)
    assert reg.resolve("cuda").key == te.ENGINE_CUDA
    assert reg.resolve("cpu").key == te.ENGINE_CPU
    assert reg.resolve("auto").key == te.ENGINE_CUDA


def test_auto_prefers_cuda_over_vulkan(tmp_path, monkeypatch):
    cfg, reg = _reg(tmp_path, cuda_exe="C:/x/cuda/whisper-cli.exe", nvidia=True,
                    vulkan_exe="C:/x/vulkan/whisper-cli.exe", monkeypatch=monkeypatch)
    # Vulkan needs its companion dll to be "available"; give it one.
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    cfg.set("cuda_benchmark_ok", True)
    cfg.set("vulkan_benchmark_ok", True)
    assert reg.resolve(te.ENGINE_AUTO).key == te.ENGINE_CUDA


# ------------------------------------------------------------- adapter report
class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, p):
        self.emissions.append(p)


class _FakeBackend:
    def __init__(self):
        self.cuda_status = _Signal()
        self.log_line = _Signal()


def test_validate_cuda_reports_loaded(tmp_path, monkeypatch):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.config.set("engine", "cuda")
    a.backend = _FakeBackend()
    cuda = te.EngineInfo(key=te.ENGINE_CUDA, label="CUDA", available=True, backend="CUDA")
    monkeypatch.setattr(te.EngineRegistry, "detect_engines", lambda self: {te.ENGINE_CUDA: cuda})
    monkeypatch.setattr(te.EngineRegistry, "resolve", lambda self, requested=te.ENGINE_AUTO: cuda)
    a.validate_cuda()
    d = json.loads(a.backend.cuda_status.emissions[-1])
    assert d["state"] == "loaded" and d["available"] is True and d["selected"] is True
    assert d["resolved_backend"] == "CUDA"


def test_validate_cuda_reports_unavailable_reason(tmp_path, monkeypatch):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    cuda = te.EngineInfo(key=te.ENGINE_CUDA, label="CUDA", available=False, backend="CUDA",
                         reason="No NVIDIA CUDA driver (nvcuda.dll) detected")
    cpu = te.EngineInfo(key=te.ENGINE_CPU, label="CPU", available=True, backend="CPU")
    monkeypatch.setattr(te.EngineRegistry, "detect_engines", lambda self: {te.ENGINE_CUDA: cuda})
    monkeypatch.setattr(te.EngineRegistry, "resolve", lambda self, requested=te.ENGINE_AUTO: cpu)
    a.validate_cuda()
    d = json.loads(a.backend.cuda_status.emissions[-1])
    assert d["state"] == "unavailable" and "nvcuda.dll" in d["message"]
