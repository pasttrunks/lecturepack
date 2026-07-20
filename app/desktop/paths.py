"""Filesystem locations, source-run and PyInstaller-frozen aware."""

from __future__ import annotations

import os
import sys


def app_root() -> str:
    """Directory containing bundled resources (ui/, packaging assets)."""
    if getattr(sys, "frozen", False):  # PyInstaller onedir bundle
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ui_dir() -> str:
    return os.path.join(app_root(), "ui")


def data_dir() -> str:
    """Per-user mutable data (jobs, models, exports) — mirrors ~/LecturePackData."""
    d = os.path.join(os.path.expanduser("~"), "LecturePackData")
    os.makedirs(d, exist_ok=True)
    return d
