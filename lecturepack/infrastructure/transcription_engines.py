"""
lecturepack.infrastructure.transcription_engines
================================================

Narrow transcription-engine abstraction (v1.1, Phase 7).

An *engine* is a whisper.cpp-compatible CLI binary plus metadata about the
compute backend it uses. The rest of the pipeline (WhisperWrapper/QProcess,
JobController, exports) is engine-agnostic: it receives an executable path and
optional extra CLI arguments.

Engines:

    whispercpp-cpu     The verified CPU binary that has shipped since v0.2
                       (bin/Release/whisper-cli.exe in dev, bin/whisper-cli.exe
                       in the packaged bundle). Never removed; always the
                       fallback.
    whispercpp-vulkan  An optional whisper.cpp build with the ggml Vulkan
                       backend (bin/vulkan/whisper-cli.exe). Used only when
                       the binary exists, a Vulkan runtime is present, and the
                       engine passed its availability probe. Forced-CPU
                       operation is available via the ``-ng`` flag.

Selection policy ("auto"): prefer Vulkan when available AND the recorded
benchmark says it is not slower than CPU; otherwise CPU. The user can pin an
engine per job. Every decision is reported so the UI can display the actual
loaded backend.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

ENGINE_CPU = "whispercpp-cpu"
ENGINE_VULKAN = "whispercpp-vulkan"
ENGINE_CUDA = "whispercpp-cuda"
ENGINE_AUTO = "auto"

ENGINE_LABELS = {
    ENGINE_AUTO: "Auto (best available)",
    ENGINE_CPU: "whisper.cpp — CPU (verified)",
    ENGINE_VULKAN: "whisper.cpp — Vulkan GPU",
    ENGINE_CUDA: "whisper.cpp — CUDA (NVIDIA GPU)",
}

# Model profiles (Phase 7). Filenames follow the official ggml naming from
# https://huggingface.co/ggerganov/whisper.cpp -- profiles resolve to the
# first present file in the models search paths.
MODEL_PROFILES = {
    "fast": {
        "label": "Fast — base.en",
        "models": ["ggml-base.en.bin", "ggml-base.en-q5_1.bin"],
    },
    "balanced": {
        "label": "Balanced — small.en (q8_0 quantized)",
        "models": ["ggml-small.en-q8_0.bin", "ggml-small.en-q5_1.bin"],
    },
    "accurate": {
        "label": "Accurate — small.en (full)",
        "models": ["ggml-small.en.bin"],
    },
    "custom": {"label": "Custom — user selected", "models": []},
}


@dataclass
class EngineInfo:
    key: str
    label: str
    exe_path: str = ""
    available: bool = False
    backend: str = "CPU"          # advertised backend kind
    reason: str = ""              # why unavailable / how selected
    extra_args: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def vulkan_runtime_present() -> bool:
    """True when the Vulkan loader is installed (GPU driver ships it)."""
    if os.name != "nt":
        return False
    sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    return os.path.isfile(os.path.join(sysdir, "vulkan-1.dll"))


def nvidia_cuda_present() -> bool:
    """True when an NVIDIA CUDA driver is installed.

    ``nvcuda.dll`` ships in System32 with the NVIDIA display driver whenever a
    CUDA-capable GPU is present; ``nvidia-smi`` is a secondary signal. This only
    proves the *driver* is present — the CUDA whisper.cpp binary is checked
    separately, and auto-selection is still gated on a real benchmark.
    """
    if os.name == "nt":
        sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        if os.path.isfile(os.path.join(sysdir, "nvcuda.dll")):
            return True
        return bool(shutil.which("nvidia-smi"))
    # POSIX (not a shipping target, but keep detection honest for tests/dev).
    return os.path.exists("/proc/driver/nvidia/version") or bool(shutil.which("nvidia-smi"))


class EngineRegistry:
    """Discovers engines and applies the selection policy."""

    def __init__(self, config_manager=None):
        self.config_manager = config_manager

    # ---- discovery ---------------------------------------------------- #
    def _cpu_exe(self) -> str:
        if self.config_manager is not None:
            p = self.config_manager.get("whisper_exe", "")
            if p and os.path.isfile(p) and "vulkan" not in p.replace("\\", "/").lower():
                return p
        root = _app_root()
        for cand in (os.path.join(root, "whisper-cli.exe"),
                     os.path.join(root, "bin", "whisper-cli.exe"),
                     os.path.join(root, "bin", "Release", "whisper-cli.exe")):
            if os.path.isfile(cand):
                return cand
        # Fall back to whatever is configured even if it has 'vulkan' in it.
        if self.config_manager is not None:
            p = self.config_manager.get("whisper_exe", "")
            if p and os.path.isfile(p):
                return p
        return ""

    def _vulkan_exe(self) -> str:
        if self.config_manager is not None:
            p = self.config_manager.get("whisper_vulkan_exe", "")
            if p and os.path.isfile(p):
                return p
        root = _app_root()
        for cand in (os.path.join(root, "bin", "vulkan", "whisper-cli.exe"),
                     os.path.join(root, "bin-vulkan", "whisper-cli.exe")):
            if os.path.isfile(cand):
                return cand
        return ""

    def _cuda_exe(self) -> str:
        if self.config_manager is not None:
            p = self.config_manager.get("whisper_cuda_exe", "")
            if p and os.path.isfile(p):
                return p
        root = _app_root()
        for cand in (os.path.join(root, "bin", "cuda", "whisper-cli.exe"),
                     os.path.join(root, "bin-cuda", "whisper-cli.exe")):
            if os.path.isfile(cand):
                return cand
        return ""

    def detect_engines(self) -> Dict[str, EngineInfo]:
        cpu_exe = self._cpu_exe()
        cpu = EngineInfo(
            key=ENGINE_CPU, label=ENGINE_LABELS[ENGINE_CPU], exe_path=cpu_exe,
            available=bool(cpu_exe), backend="CPU",
            reason="" if cpu_exe else "whisper-cli.exe not found")

        v_exe = self._vulkan_exe()
        if not v_exe:
            vk = EngineInfo(key=ENGINE_VULKAN, label=ENGINE_LABELS[ENGINE_VULKAN],
                            available=False, backend="Vulkan",
                            reason="Vulkan whisper-cli.exe not installed")
        elif not vulkan_runtime_present():
            vk = EngineInfo(key=ENGINE_VULKAN, label=ENGINE_LABELS[ENGINE_VULKAN],
                            exe_path=v_exe, available=False, backend="Vulkan",
                            reason="No Vulkan runtime (vulkan-1.dll) on this system")
        else:
            vulkan_dll = os.path.join(os.path.dirname(v_exe), "ggml-vulkan.dll")
            if not os.path.isfile(vulkan_dll):
                vk = EngineInfo(key=ENGINE_VULKAN, label=ENGINE_LABELS[ENGINE_VULKAN],
                                exe_path=v_exe, available=False, backend="Vulkan",
                                reason="ggml-vulkan.dll missing next to the binary")
            else:
                vk = EngineInfo(key=ENGINE_VULKAN, label=ENGINE_LABELS[ENGINE_VULKAN],
                                exe_path=v_exe, available=True, backend="Vulkan")

        c_exe = self._cuda_exe()
        if not c_exe:
            cuda = EngineInfo(key=ENGINE_CUDA, label=ENGINE_LABELS[ENGINE_CUDA],
                              available=False, backend="CUDA",
                              reason="CUDA whisper-cli.exe not installed "
                                     "(drop a CUDA build in bin/cuda/)")
        elif not nvidia_cuda_present():
            cuda = EngineInfo(key=ENGINE_CUDA, label=ENGINE_LABELS[ENGINE_CUDA],
                              exe_path=c_exe, available=False, backend="CUDA",
                              reason="No NVIDIA CUDA driver (nvcuda.dll) detected")
        else:
            cuda = EngineInfo(key=ENGINE_CUDA, label=ENGINE_LABELS[ENGINE_CUDA],
                              exe_path=c_exe, available=True, backend="CUDA")
        return {ENGINE_CPU: cpu, ENGINE_VULKAN: vk, ENGINE_CUDA: cuda}

    # ---- selection ----------------------------------------------------- #
    # The WebEngine UI persists short engine aliases ("cpu"/"vulkan"/"cuda"),
    # while the registry keys are the full "whispercpp-*" ids. Normalize so an
    # explicit selection is honoured (not silently routed through auto).
    _ENGINE_ALIASES = {
        "cpu": ENGINE_CPU, "vulkan": ENGINE_VULKAN, "cuda": ENGINE_CUDA,
        "auto": ENGINE_AUTO,
    }

    def resolve(self, requested: str = ENGINE_AUTO) -> EngineInfo:
        """Return the engine to use for a run. Never returns an unavailable
        engine: unavailable requests degrade to the CPU engine with a reason.
        """
        requested = self._ENGINE_ALIASES.get(requested, requested)
        engines = self.detect_engines()
        cpu = engines[ENGINE_CPU]
        vk = engines[ENGINE_VULKAN]
        cuda = engines.get(ENGINE_CUDA) or EngineInfo(
            key=ENGINE_CUDA, label=ENGINE_LABELS[ENGINE_CUDA], available=False,
            backend="CUDA", reason="not detected")

        if requested == ENGINE_CPU:
            cpu.reason = "explicitly selected"
            return cpu
        if requested == ENGINE_CUDA:
            if cuda.available:
                cuda.reason = "explicitly selected"
                return cuda
            cpu.reason = f"CUDA requested but unavailable ({cuda.reason}); using CPU"
            return cpu
        if requested == ENGINE_VULKAN:
            if vk.available:
                vk.reason = "explicitly selected"
                return vk
            cpu.reason = f"Vulkan requested but unavailable ({vk.reason}); using CPU"
            return cpu

        # auto policy: prefer CUDA, then Vulkan, then verified CPU — but only a
        # GPU backend that has actually benchmarked faster on this machine.
        if cuda.available and self._benchmark_ok("cuda_benchmark_ok"):
            cuda.reason = "auto: CUDA available and benchmarked faster"
            return cuda
        if vk.available and self._benchmark_ok("vulkan_benchmark_ok"):
            vk.reason = "auto: Vulkan available and benchmarked faster"
            return vk
        if cuda.available:
            cpu.reason = "auto: CUDA present but not benchmarked faster; using verified CPU"
        elif vk.available:
            cpu.reason = "auto: Vulkan present but not benchmarked faster; using verified CPU"
        else:
            cpu.reason = f"auto: {cuda.reason}; using verified CPU"
        return cpu

    def _benchmark_ok(self, key: str) -> bool:
        """A GPU backend is auto-selected only after a recorded benchmark says
        it beat CPU on this machine. Defaults to False — never assume faster."""
        if self.config_manager is None:
            return False
        return bool(self.config_manager.get(key, False))

    def _vulkan_benchmark_ok(self) -> bool:  # back-compat alias
        return self._benchmark_ok("vulkan_benchmark_ok")


def resolve_profile_model(profile: str, search_dirs: List[str]) -> Optional[str]:
    """Find the first model file that satisfies a profile, or None."""
    prof = MODEL_PROFILES.get(profile)
    if not prof:
        return None
    for name in prof["models"]:
        for d in search_dirs:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return os.path.abspath(p)
    return None


def model_search_dirs(config_manager=None) -> List[str]:
    root = _app_root()
    dirs = [os.path.join(root, "models"), os.path.join(os.path.dirname(root), "models")]
    if config_manager is not None:
        dirs.append(os.path.join(config_manager.data_dir, "models"))
        current = config_manager.get("whisper_model", "")
        if current:
            dirs.append(os.path.dirname(current))
    return [d for d in dirs if os.path.isdir(d)]
