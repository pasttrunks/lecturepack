"""Frozen (packaged) resource-path resolution for the desktop shell.

The packaged exe crashed on two things until fixed: the entry script used
relative imports, and app_root() looked beside the exe while PyInstaller 6 places
bundled data under sys._MEIPASS (the onedir _internal/ folder). These tests cover
the path logic; the entry wrapper is exercised by the packaged smoke launch.
"""
from __future__ import annotations

import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import paths  # noqa: E402


def test_source_run_app_root(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    root = paths.app_root()
    # Source layout: app/ (the dir that contains desktop/ and ui/).
    assert os.path.isdir(os.path.join(root, "desktop"))


def test_frozen_prefers_meipass_with_ui(monkeypatch, tmp_path):
    meipass = tmp_path / "_internal"
    (meipass / "ui").mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "LecturePack.exe"), raising=False)
    assert paths.app_root() == str(meipass)
    assert paths.ui_dir() == str(meipass / "ui")


def test_frozen_falls_back_to_exe_dir_when_meipass_has_no_ui(monkeypatch, tmp_path):
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    meipass = tmp_path / "meipass_no_ui"
    meipass.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "LecturePack.exe"), raising=False)
    assert paths.app_root() == str(exe_dir)


def test_frozen_without_meipass_uses_exe_dir(monkeypatch, tmp_path):
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "LecturePack.exe"), raising=False)
    assert paths.app_root() == str(exe_dir)
