"""Phase 2 "Premium Glassmorphic Dark" UI overhaul tests.

M1: theme layer (QSS file, palette, shadow helper).
"""
from __future__ import annotations

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QFrame

from lecturepack.ui import theme


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    if existing is not None:
        yield existing
    else:
        application = QApplication([])
        yield application


# --------------------------------------------------------------------- M1 #
def test_dark_palette_uses_mocha_colors(app):
    theme.apply_theme(app, dark=True)
    palette = app.palette()
    assert palette.color(QPalette.Window).name() == "#1e1e2e"
    assert palette.color(QPalette.Base).name() == "#181825"
    assert palette.color(QPalette.Text).name() == "#cdd6f4"
    assert palette.color(QPalette.Highlight).name() == "#89b4fa"


def test_dark_qss_file_loaded_only_when_dark(app):
    theme.apply_theme(app, dark=True)
    assert "#1e1e2e" in app.styleSheet().lower()
    assert "#89b4fa" in app.styleSheet().lower()
    theme.apply_theme(app, dark=False)
    assert "#1e1e2e" not in app.styleSheet().lower()
    theme.apply_theme(app, dark=True)  # leave the app dark for other tests


def test_qss_uses_literal_hex_not_css_variables():
    qss = theme.load_qss("dark_theme.qss")
    assert qss.strip(), "dark_theme.qss must exist and be non-empty"
    assert "var(" not in qss
    assert "#1E1E2E" in qss
    assert "#89B4FA" in qss


def test_load_qss_missing_file_returns_empty_string():
    assert theme.load_qss("does_not_exist.qss") == ""


def test_selection_visuals_api_unchanged():
    # v1.1 contract relied on by test_ui_v11 and the slide delegate.
    vis = theme.selection_visuals(True, True, "accepted", True)
    assert vis["outline_color"].name() == theme.ACCENT
    assert vis["outline_width"] >= 2


def test_add_card_shadow_attaches_effect(app):
    frame = QFrame()
    effect = theme.add_card_shadow(frame)
    assert frame.graphicsEffect() is effect
    assert effect.blurRadius() == 24.0
    assert effect.yOffset() == 3.0
    assert effect.color().alpha() == 90
