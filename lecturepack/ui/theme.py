"""
lecturepack.ui.theme
====================

Light/dark theme for the v1.1 shell. Uses the Fusion style with an explicit
QPalette plus a small QSS layer for the nav rail, command bar, cards and
status chips. No decorative gradients; spacing and contrast follow native
Windows 11 conventions.

The accent color and the selection visuals are defined HERE so widget code
and tests share one source of truth (tests assert on these values).
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#2563eb"            # selection outline / primary actions (blue-600)
ACCENT_HOVER = "#1d4ed8"
ACCENT_SOFT_LIGHT = "#dbeafe" # selected-row background on light theme
ACCENT_SOFT_DARK = "#1e3a8a"  # selected-row background on dark theme
DANGER = "#dc2626"
SUCCESS = "#16a34a"
WARNING = "#d97706"

# Slide-selection visuals (Phase 2). Used by the delegate AND by tests.
SELECTION_OUTLINE_WIDTH = 3   # px, >= 2 required
CHECKMARK_DIAMETER = 22

# ------------------------------------------------------------------ #
# Phase 2 "Premium Glassmorphic Dark" palette (Catppuccin Mocha).    #
# Literal hex values, mirrored by ui/themes/dark_theme.qss (QSS has  #
# no CSS variables). Widget code should use THESE constants so the   #
# QSS file and Python never drift apart.                             #
# ------------------------------------------------------------------ #
MOCHA_BASE = "#1E1E2E"          # window background
MOCHA_MANTLE = "#181825"        # rails, bars, sunken inputs
MOCHA_SURFACE0 = "#313244"      # cards, blocks
MOCHA_SURFACE1 = "#45475A"      # hover / strong borders
MOCHA_TEXT = "#CDD6F4"
MOCHA_SUBTEXT = "#A6ADC8"
MOCHA_ACCENT = "#89B4FA"        # neon blue: selection, primary, focus
MOCHA_ACCENT_HOVER = "#74A8F7"
MOCHA_GREEN = "#A6E3A1"
MOCHA_RED = "#F38BA8"
MOCHA_YELLOW = "#F9E2AF"
MOCHA_OVERLAY = "#6C7086"       # disabled text
FONT_STACK = '"Segoe UI Variable Text", Inter, "Segoe UI", sans-serif'


def selection_visuals(selected: bool, focused: bool, decision: str, dark: bool) -> dict:
    """Pure description of how a slide tile must be painted. Unit-testable
    without rendering. ``decision`` is 'accepted' or 'rejected'."""
    accent = QColor(ACCENT)
    if decision == "rejected":
        base_bg = QColor("#3b1d1d") if dark else QColor("#fee2e2")
        badge = QColor(DANGER)
    else:
        base_bg = QColor("#14261a") if dark else QColor("#f0fdf4")
        badge = QColor(SUCCESS)
    if selected:
        bg = QColor(ACCENT_SOFT_DARK) if dark else QColor(ACCENT_SOFT_LIGHT)
    else:
        bg = base_bg
    return {
        "outline_color": accent if selected else QColor(0, 0, 0, 0),
        "outline_width": SELECTION_OUTLINE_WIDTH if selected else 0,
        "background": bg,
        "checkmark_visible": selected,
        "checkmark_bg": accent,
        "focus_ring_visible": selected and focused,
        "focus_ring_color": QColor(ACCENT_HOVER),
        "decision_badge_color": badge,
    }


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#f5f6f8"))
    p.setColor(QPalette.WindowText, QColor("#1b1e23"))
    p.setColor(QPalette.Base, QColor("#ffffff"))
    p.setColor(QPalette.AlternateBase, QColor("#f2f4f7"))
    p.setColor(QPalette.Text, QColor("#1b1e23"))
    p.setColor(QPalette.Button, QColor("#ffffff"))
    p.setColor(QPalette.ButtonText, QColor("#1b1e23"))
    p.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    p.setColor(QPalette.ToolTipText, QColor("#1b1e23"))
    p.setColor(QPalette.Highlight, QColor(ACCENT))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.PlaceholderText, QColor("#8b93a1"))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor("#9aa1ac"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#9aa1ac"))
    return p


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(MOCHA_BASE))
    p.setColor(QPalette.WindowText, QColor(MOCHA_TEXT))
    p.setColor(QPalette.Base, QColor(MOCHA_MANTLE))
    p.setColor(QPalette.AlternateBase, QColor("#232334"))
    p.setColor(QPalette.Text, QColor(MOCHA_TEXT))
    p.setColor(QPalette.Button, QColor(MOCHA_SURFACE0))
    p.setColor(QPalette.ButtonText, QColor(MOCHA_TEXT))
    p.setColor(QPalette.ToolTipBase, QColor(MOCHA_SURFACE0))
    p.setColor(QPalette.ToolTipText, QColor(MOCHA_TEXT))
    p.setColor(QPalette.Highlight, QColor(MOCHA_ACCENT))
    p.setColor(QPalette.HighlightedText, QColor(MOCHA_BASE))
    p.setColor(QPalette.PlaceholderText, QColor(MOCHA_OVERLAY))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(MOCHA_OVERLAY))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MOCHA_OVERLAY))
    return p


def _qss(dark: bool) -> str:
    rail_bg = "#181b1f" if dark else "#eceef1"
    rail_hover = "#2b2f36" if dark else "#dde1e7"
    rail_checked = ACCENT_SOFT_DARK if dark else ACCENT_SOFT_LIGHT
    rail_text = "#c8cdd5" if dark else "#3b4149"
    card_bg = "#26292f" if dark else "#ffffff"
    border = "#3a3f47" if dark else "#d7dbe1"
    bar_bg = "#1b1e23" if dark else "#ffffff"
    return f"""
    QWidget#NavRail {{
        background: {rail_bg};
        border-right: 1px solid {border};
    }}
    QToolButton[navButton="true"] {{
        color: {rail_text};
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 8px 4px;
        font-size: 11px;
    }}
    QToolButton[navButton="true"]:hover {{ background: {rail_hover}; }}
    QToolButton[navButton="true"]:checked {{
        background: {rail_checked};
        color: {ACCENT if not dark else '#93b4f8'};
        font-weight: 600;
    }}
    QWidget#CommandBar {{
        background: {bar_bg};
        border-bottom: 1px solid {border};
    }}
    QFrame[card="true"] {{
        background: {card_bg};
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QLabel[h1="true"] {{ font-size: 18px; font-weight: 600; }}
    QLabel[h2="true"] {{ font-size: 14px; font-weight: 600; }}
    QLabel[muted="true"] {{ color: {'#9aa1ac' if not dark else '#8b93a1'}; }}
    QPushButton[primary="true"] {{
        background: {ACCENT}; color: white; font-weight: 600;
        border: none; border-radius: 6px; padding: 7px 16px;
    }}
    QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton[primary="true"]:disabled {{ background: {border}; color: #9aa1ac; }}
    QPushButton[danger="true"] {{
        background: transparent; color: {DANGER}; font-weight: 600;
        border: 1px solid {DANGER}; border-radius: 6px; padding: 6px 14px;
    }}
    QPushButton[danger="true"]:hover {{ background: {DANGER}; color: white; }}
    QLabel[chip="ok"] {{ color: {SUCCESS}; font-weight: 600; }}
    QLabel[chip="warn"] {{ color: {WARNING}; font-weight: 600; }}
    QLabel[chip="err"] {{ color: {DANGER}; font-weight: 600; }}
    QTableWidget, QTableView {{
        gridline-color: {border};
        selection-background-color: {rail_checked};
        selection-color: {'#e6e9ee' if dark else '#111827'};
    }}
    QHeaderView::section {{
        background: {card_bg}; border: none;
        border-bottom: 1px solid {border};
        padding: 6px 8px; font-weight: 600;
    }}
    QSplitter::handle {{ background: {border}; }}
    QSplitter::handle:horizontal {{ width: 2px; }}
    QSplitter::handle:vertical {{ height: 2px; }}
    QStatusBar {{ background: {bar_bg}; border-top: 1px solid {border}; }}
    """


def load_qss(filename: str) -> str:
    """Read a QSS file shipped next to this module under ``themes/``.

    Returns an empty string (and logs a warning) when the file is missing so
    a broken or unpackaged theme file never crashes startup.
    """
    import logging
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "themes", filename)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        logging.getLogger(__name__).warning("Theme file not found: %s", path)
        return ""


def add_card_shadow(widget, blur: float = 24.0, y_offset: float = 3.0,
                    alpha: int = 90):
    """Attach a soft drop shadow so cards float above the dark background.

    Returns the created ``QGraphicsDropShadowEffect`` (owned by ``widget``).
    """
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setXOffset(0.0)
    effect.setYOffset(y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return effect


def apply_theme(app: QApplication, dark: bool = False) -> None:
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if dark else _light_palette())
    qss = _qss(dark)
    if dark:
        # Appended last so the glassmorphic layer wins the cascade over the
        # v1.1 structural rules above (equal specificity -> later rule wins).
        qss = qss + "\n" + load_qss("dark_theme.qss")
    app.setStyleSheet(qss)
    app.setProperty("lp_dark_theme", dark)


def is_dark(app=None) -> bool:
    app = app or QApplication.instance()
    return bool(app and app.property("lp_dark_theme"))
