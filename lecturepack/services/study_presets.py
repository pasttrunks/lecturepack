"""Smart Study model presets, hardware recommendation, and provider labels.

Pure standard library (no Qt, no engine imports) so the recommendation logic is
unit-testable without a running app or Ollama. Ported from the Qt desktop
``app/desktop/smart_study.py`` so the Electron sidecar can reuse the exact
preset/recommendation behavior without importing the Qt application.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List

PROVIDER_BUILTIN = "Built-in Study"
PROVIDER_LOCAL = "Local AI"
PROVIDER_ONLINE = "Online Enhanced"

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
    return [dict(STUDY_PRESETS[PRESET_LIGHTWEIGHT]), dict(STUDY_PRESETS[PRESET_BALANCED])]


def model_for_preset(preset: str, custom_model: str = "") -> str:
    p = STUDY_PRESETS.get(preset)
    if p:
        return p["model"]
    return custom_model or ""


def preset_for_model(model: str) -> str:
    for key, p in STUDY_PRESETS.items():
        if p["model"] == model:
            return key
    return PRESET_CUSTOM if model else ""


def usable_ram_gb() -> float:
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


OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"