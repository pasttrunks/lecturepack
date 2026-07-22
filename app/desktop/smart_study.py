"""Smart Study model presets, hardware recommendation, and provider labels.

Pure standard library (no Qt, no engine imports) so the recommendation logic is
unit-testable without a running app or Ollama. The desktop adapter
(engine_adapter.py) uses these helpers to drive the optional Smart Study setup:

  * Normal users pick between two named presets — Lightweight / Balanced — and
    never see raw model IDs on the main onboarding card (§5/§6 of the release
    spec). The IDs live under Advanced.
  * The recommendation is a simple RAM-based heuristic (§7); no GPU benchmark.
  * Provider labels are the single source of truth for how the UI names the
    active study provider (§8): Built-in Study / Local AI / Online Enhanced.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List

# ----------------------------------------------------------------------------
# Provider labels (§8) — used everywhere the UI names the active study provider.
# ----------------------------------------------------------------------------
PROVIDER_BUILTIN = "Built-in Study"
PROVIDER_LOCAL = "Local AI"
PROVIDER_ONLINE = "Online Enhanced"

# ----------------------------------------------------------------------------
# Model presets (§6). Only two normal choices; the model IDs belong to Advanced.
# ----------------------------------------------------------------------------
PRESET_LIGHTWEIGHT = "lightweight"
PRESET_BALANCED = "balanced"
PRESET_CUSTOM = "custom"

STUDY_PRESETS: Dict[str, dict] = {
    PRESET_LIGHTWEIGHT: {
        "key": PRESET_LIGHTWEIGHT,
        "label": "Lightweight Study",
        "model": "qwen3:1.7b",
        "approx_gb": 1.4,
        "blurb": "Lower-memory or slower computers",
        "recommended": False,
    },
    PRESET_BALANCED: {
        "key": PRESET_BALANCED,
        "label": "Balanced Study",
        "model": "qwen3:4b",
        "approx_gb": 2.5,
        "blurb": "Most computers with 12 GB or more usable RAM",
        "recommended": True,
    },
}


def preset_list() -> List[dict]:
    """Ordered presets for the UI (lightweight first, balanced second)."""
    return [dict(STUDY_PRESETS[PRESET_LIGHTWEIGHT]), dict(STUDY_PRESETS[PRESET_BALANCED])]


def model_for_preset(preset: str, custom_model: str = "") -> str:
    """Resolve a preset key to an Ollama model id.

    ``custom`` (or any unknown key) falls back to the caller-supplied model so
    users who picked their own model under Advanced keep it.
    """
    p = STUDY_PRESETS.get(preset)
    if p:
        return p["model"]
    return custom_model or ""


def preset_for_model(model: str) -> str:
    """Reverse map a model id to a named preset, else 'custom'."""
    for key, p in STUDY_PRESETS.items():
        if p["model"] == model:
            return key
    return PRESET_CUSTOM if model else ""


def usable_ram_gb() -> float:
    """Best-effort total physical RAM in GB. Returns 0.0 when unknown.

    Pure stdlib: ctypes GlobalMemoryStatusEx on Windows, sysconf on POSIX.
    """
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024 ** 3), 1)
        elif hasattr(os, "sysconf"):
            names = getattr(os, "sysconf_names", {})
            if "SC_PAGE_SIZE" in names and "SC_PHYS_PAGES" in names:
                page = os.sysconf("SC_PAGE_SIZE")
                pages = os.sysconf("SC_PHYS_PAGES")
                return round(page * pages / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


def recommend_preset(ram_gb: float) -> dict:
    """RAM-based Smart Study recommendation (§7).

    Returns {ram_gb, recommended, default_builtin, allow_advanced_models, note}.
    ``recommended`` is the preset key the onboarding card should highlight;
    ``default_builtin`` marks machines where Built-in Study is the safe default.
    """
    if ram_gb <= 0:
        return {
            "ram_gb": ram_gb,
            "recommended": PRESET_BALANCED,
            "default_builtin": False,
            "allow_advanced_models": True,
            "note": "Couldn't detect RAM — Balanced Study is the general default.",
        }
    if ram_gb < 12:
        return {
            "ram_gb": ram_gb,
            "recommended": PRESET_LIGHTWEIGHT,
            "default_builtin": True,
            "allow_advanced_models": False,
            "note": (f"{ram_gb:g} GB RAM — Built-in Study by default; "
                     "Lightweight Study is the lighter local option."),
        }
    if ram_gb <= 24:
        return {
            "ram_gb": ram_gb,
            "recommended": PRESET_BALANCED,
            "default_builtin": False,
            "allow_advanced_models": False,
            "note": f"{ram_gb:g} GB RAM — Balanced Study is recommended.",
        }
    return {
        "ram_gb": ram_gb,
        "recommended": PRESET_BALANCED,
        "default_builtin": False,
        "allow_advanced_models": True,
        "note": (f"{ram_gb:g} GB RAM — Balanced Study recommended; "
                 "other installed models are available under Advanced."),
    }


# Official Ollama download page. We open this in the browser rather than
# fetching/executing an installer ourselves — the user runs the official
# installer, which keeps LecturePack from ever downloading and running a binary.
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
