"""
lecturepack.ui.theme
====================

Studio refined orange-primary/teal-secondary light/dark theme.
Uses Fusion style with QPalette + QSS for header, sidebar, footer,
cards, and status chips.

Design language: 1.5px borders, soft multi-layer shadows, rounded corners
(7-16px), Space Grotesk + JetBrains Mono typography.

Brand: Orange = primary, Teal/cyan = secondary.
"""
from __future__ import annotations

import os

from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# ------------------------------------------------------------------ #
# Shared semantic colors                                              #
# ------------------------------------------------------------------ #
PRIMARY = "#F15A24"
PRIMARY_HOVER = "#D94812"
PRIMARY_SOFT_LIGHT = "#FBE2D5"
PRIMARY_SOFT_DARK = "#3B241A"

SECONDARY = "#159EAE"
SECONDARY_HOVER = "#0C7F8D"
SECONDARY_SOFT_LIGHT = "#DDF3F4"
SECONDARY_SOFT_DARK = "#15353A"

DANGER = "#D63A2C"
SUCCESS = "#128A52"
WARNING = "#D99400"

ACCENT = PRIMARY
ACCENT_HOVER = PRIMARY_HOVER
ACCENT_SOFT_LIGHT = PRIMARY_SOFT_LIGHT
ACCENT_SOFT_DARK = PRIMARY_SOFT_DARK

SELECTION_OUTLINE_WIDTH = 3
CHECKMARK_DIAMETER = 22

# ------------------------------------------------------------------ #
# Dark palette                                                        #
# ------------------------------------------------------------------ #
DARK_BG = "#121417"
DARK_PANEL = "#1B1F23"
DARK_PANEL2 = "#22272D"
DARK_SUNK = "#15191D"
DARK_INK = "#F0E9DF"
DARK_MUTED = "#949BA5"
DARK_BORDER = "#090A0C"
DARK_LINE = "#30363D"

DARK_PRIMARY = "#FF6B35"
DARK_PRIMARY_HOVER = "#FF8259"
DARK_PRIMARY_SOFT = "#3B241A"
DARK_PRIMARY_INK = "#FF9A76"

DARK_SECONDARY = "#45C6D3"
DARK_SECONDARY_HOVER = "#69D7E0"
DARK_SECONDARY_SOFT = "#15353A"
DARK_SECONDARY_INK = "#A6EBEF"

DARK_GREEN = "#4CCB86"
DARK_GREEN_SOFT = "#123020"
DARK_RED = "#FF6E5E"
DARK_RED_SOFT = "#361715"
DARK_YELLOW = "#F2C24A"
DARK_YELLOW_SOFT = "#332810"
DARK_NAV_INK = "#AEB3BF"

# ------------------------------------------------------------------ #
# Light palette                                                       #
# ------------------------------------------------------------------ #
LIGHT_BG = "#F4EFE6"
LIGHT_PANEL = "#FFFFFF"
LIGHT_PANEL2 = "#F9F5ED"
LIGHT_SUNK = "#EEE8DD"
LIGHT_INK = "#1D1915"
LIGHT_MUTED = "#81786B"
LIGHT_BORDER = "#2A241E"
LIGHT_LINE = "#DDD3C4"

LIGHT_PRIMARY = "#F15A24"
LIGHT_PRIMARY_HOVER = "#D94812"
LIGHT_PRIMARY_SOFT = "#FBE2D5"
LIGHT_PRIMARY_INK = "#B73A0B"

LIGHT_SECONDARY = "#159EAE"
LIGHT_SECONDARY_HOVER = "#0C7F8D"
LIGHT_SECONDARY_SOFT = "#DDF3F4"
LIGHT_SECONDARY_INK = "#095F69"

LIGHT_GREEN = "#128A52"
LIGHT_GREEN_SOFT = "#D3F0DF"
LIGHT_RED = "#D63A2C"
LIGHT_RED_SOFT = "#FADAD5"
LIGHT_YELLOW = "#D99400"
LIGHT_YELLOW_SOFT = "#FBEDC6"
LIGHT_NAV_INK = "#4A4438"

FONT_STACK = '"Space Grotesk", "Segoe UI", Inter, sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", monospace'


def selection_visuals(selected, focused, decision, dark):
    accent = QColor(PRIMARY)
    if decision == "rejected":
        base_bg = QColor(DARK_RED_SOFT) if dark else QColor(LIGHT_RED_SOFT)
        badge = QColor(DANGER)
    else:
        base_bg = QColor(DARK_GREEN_SOFT) if dark else QColor(LIGHT_GREEN_SOFT)
        badge = QColor(SUCCESS)
    if selected:
        bg = QColor(PRIMARY_SOFT_DARK) if dark else QColor(PRIMARY_SOFT_LIGHT)
    else:
        bg = base_bg
    return {
        "outline_color": accent if selected else QColor(0, 0, 0, 0),
        "outline_width": SELECTION_OUTLINE_WIDTH if selected else 0,
        "background": bg,
        "checkmark_visible": selected,
        "checkmark_bg": accent,
        "focus_ring_visible": selected and focused,
        "focus_ring_color": QColor(PRIMARY_HOVER),
        "decision_badge_color": badge,
    }


def _light_palette():
    p = QPalette()
    p.setColor(QPalette.Window, QColor(LIGHT_BG))
    p.setColor(QPalette.WindowText, QColor(LIGHT_INK))
    p.setColor(QPalette.Base, QColor(LIGHT_PANEL))
    p.setColor(QPalette.AlternateBase, QColor(LIGHT_PANEL2))
    p.setColor(QPalette.Text, QColor(LIGHT_INK))
    p.setColor(QPalette.Button, QColor(LIGHT_PANEL))
    p.setColor(QPalette.ButtonText, QColor(LIGHT_INK))
    p.setColor(QPalette.ToolTipBase, QColor(LIGHT_PANEL))
    p.setColor(QPalette.ToolTipText, QColor(LIGHT_INK))
    p.setColor(QPalette.Highlight, QColor(LIGHT_PRIMARY))
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.PlaceholderText, QColor(LIGHT_MUTED))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(LIGHT_MUTED))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(LIGHT_MUTED))
    return p


def _dark_palette():
    p = QPalette()
    p.setColor(QPalette.Window, QColor(DARK_BG))
    p.setColor(QPalette.WindowText, QColor(DARK_INK))
    p.setColor(QPalette.Base, QColor(DARK_PANEL))
    p.setColor(QPalette.AlternateBase, QColor(DARK_PANEL2))
    p.setColor(QPalette.Text, QColor(DARK_INK))
    p.setColor(QPalette.Button, QColor(DARK_PANEL))
    p.setColor(QPalette.ButtonText, QColor(DARK_INK))
    p.setColor(QPalette.ToolTipBase, QColor(DARK_PANEL))
    p.setColor(QPalette.ToolTipText, QColor(DARK_INK))
    p.setColor(QPalette.Highlight, QColor(DARK_PRIMARY))
    p.setColor(QPalette.HighlightedText, QColor(DARK_BG))
    p.setColor(QPalette.PlaceholderText, QColor(DARK_MUTED))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(DARK_MUTED))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(DARK_MUTED))
    return p


def _qss(dark):
    if dark:
        ink = DARK_INK
        border = DARK_BORDER
        muted = DARK_MUTED
        primary = DARK_PRIMARY
        primary_hover = DARK_PRIMARY_HOVER
        primary_soft = DARK_PRIMARY_SOFT
        primary_ink = DARK_PRIMARY_INK
        secondary = DARK_SECONDARY
        secondary_hover = DARK_SECONDARY_HOVER
        secondary_soft = DARK_SECONDARY_SOFT
        secondary_ink = DARK_SECONDARY_INK
        sidebar_bg = DARK_PANEL
        card_bg = DARK_PANEL
        panel2 = DARK_PANEL2
        sunk = DARK_SUNK
        line = DARK_LINE
        green = DARK_GREEN
        green_soft = DARK_GREEN_SOFT
        red = DARK_RED
        red_soft = DARK_RED_SOFT
        nav_ink = DARK_NAV_INK
    else:
        ink = LIGHT_INK
        border = LIGHT_BORDER
        muted = LIGHT_MUTED
        primary = LIGHT_PRIMARY
        primary_hover = LIGHT_PRIMARY_HOVER
        primary_soft = LIGHT_PRIMARY_SOFT
        primary_ink = LIGHT_PRIMARY_INK
        secondary = LIGHT_SECONDARY
        secondary_hover = LIGHT_SECONDARY_HOVER
        secondary_soft = LIGHT_SECONDARY_SOFT
        secondary_ink = LIGHT_SECONDARY_INK
        sidebar_bg = LIGHT_PANEL
        card_bg = LIGHT_PANEL
        panel2 = LIGHT_PANEL2
        sunk = LIGHT_SUNK
        line = LIGHT_LINE
        green = LIGHT_GREEN
        green_soft = LIGHT_GREEN_SOFT
        red = LIGHT_RED
        red_soft = LIGHT_RED_SOFT
        nav_ink = LIGHT_NAV_INK

    return f"""
    /* ===== HEADER BAR ===== */
    QFrame#AppHeaderBar {{
        background: {card_bg};
        border-bottom: 1.5px solid {border};
    }}
    QFrame#LogoMark {{
        background: {primary};
        border-radius: 8px;
    }}
    QLabel#LogoDiamond {{
        color: #FFFFFF;
        font-size: 11px;
    }}
    QLabel#AppBreadcrumb {{
        color: {muted};
        font: 500 13px {FONT_STACK};
    }}
    QToolButton#ThemeToggleBtn {{
        font: 600 12px {FONT_MONO};
        letter-spacing: 0.04em;
        background: {card_bg};
        color: {ink};
        border: 1.5px solid {border};
        border-radius: 9px;
        padding: 8px 11px;
    }}
    QToolButton#ThemeToggleBtn:hover {{ background: {panel2}; }}
    QToolButton#HeaderSaveBtn {{
        font: 600 13.5px {FONT_STACK};
        background: {card_bg};
        color: {ink};
        border: 1.5px solid {border};
        border-radius: 9px;
        padding: 9px 15px;
    }}
    QToolButton#HeaderSaveBtn:hover {{ background: {panel2}; }}
    QToolButton#HeaderExportBtn {{
        font: 600 13.5px {FONT_STACK};
        background: {primary};
        color: #FFFFFF;
        border: 1.5px solid {primary_hover};
        border-radius: 9px;
        padding: 9px 17px;
    }}
    QToolButton#HeaderExportBtn:hover {{ background: {primary_hover}; }}

    /* ===== SIDEBAR ===== */
    QWidget#NavSidebar {{
        background: {sidebar_bg};
        border-right: 1.5px solid {border};
    }}
    QLabel#SidebarSectionLabel {{
        font: 500 11px {FONT_MONO};
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: {muted};
        padding: 16px 8px 8px;
    }}
    QToolButton[navButton="true"] {{
        color: {nav_ink};
        background: transparent;
        border: 1.5px solid transparent;
        border-radius: 9px;
        padding: 9px 12px;
        font: 600 13.5px {FONT_STACK};
        text-align: left;
    }}
    QToolButton[navButton="true"]:hover {{ background: {panel2}; color: {ink}; }}
    QToolButton[navButton="true"]:checked {{
        background: {primary_soft};
        color: {primary_ink};
        font-weight: 700;
        border: 1.5px solid {primary};
    }}

    /* ===== JOB STATUS CARD ===== */
    QFrame#JobStatusCard {{
        background: {panel2};
        border: 1.5px solid {line};
        border-radius: 11px;
    }}
    QFrame#JobCardThumb {{
        background: {secondary_soft};
        border: 1.5px solid {line};
        border-radius: 6px;
    }}
    QLabel#JobCardTitle {{
        font-weight: 700;
        font-size: 13px;
        color: {ink};
    }}
    QLabel#JobCardStatus {{
        font: 500 11px {FONT_MONO};
        color: {primary};
    }}

    /* ===== STATUS FOOTER ===== */
    QFrame#AppStatusFooter {{
        background: {card_bg};
        border-top: 1.5px solid {border};
    }}
    QLabel#FooterStage {{
        font: 600 12px {FONT_MONO};
        text-transform: uppercase;
        color: {primary};
    }}
    QLabel#FooterElapsed {{
        font: 500 12px {FONT_MONO};
        color: {muted};
    }}
    QLabel#FooterEngine {{
        font: 500 12px {FONT_MONO};
        color: {muted};
    }}
    QLabel#FooterWarn {{
        color: {red};
        font-weight: 600;
    }}

    /* ===== COMMON ELEMENTS ===== */
    QFrame[card="true"] {{
        background: {card_bg};
        border: 1.5px solid {border};
        border-radius: 13px;
    }}
    QLabel[h1="true"] {{ font-size: 22px; font-weight: 700; }}
    QLabel[h2="true"] {{ font-size: 16px; font-weight: 600; }}
    QLabel[muted="true"] {{ color: {muted}; }}
    QPushButton[primary="true"] {{
        background: {primary}; color: #FFFFFF; font-weight: 700;
        border: 1.5px solid {primary_hover}; border-radius: 9px; padding: 9px 17px;
    }}
    QPushButton[primary="true"]:hover {{ background: {primary_hover}; }}
    QPushButton[primary="true"]:disabled {{ background: {sunk}; color: {muted}; border-color: {sunk}; }}
    QPushButton[danger="true"] {{
        background: transparent; color: {red}; font-weight: 600;
        border: 1.5px solid {red}; border-radius: 8px; padding: 6px 14px;
    }}
    QPushButton[danger="true"]:hover {{ background: {red}; color: #FFFFFF; }}
    QLabel[chip="ok"] {{ color: {green}; font-weight: 600; }}
    QLabel[chip="warn"] {{ color: {WARNING}; font-weight: 600; }}
    QLabel[chip="err"] {{ color: {red}; font-weight: 600; }}
    QTableWidget, QTableView {{
        gridline-color: {line};
        selection-background-color: {secondary_soft};
        selection-color: {ink};
    }}
    QHeaderView::section {{
        background: {sunk}; border: 1.5px solid {border};
        border-bottom: 1.5px solid {border};
        padding: 6px 8px; font-weight: 600;
    }}
    QSplitter::handle {{ background: {line}; }}
    QSplitter::handle:horizontal {{ width: 1.5px; }}
    QSplitter::handle:vertical {{ height: 1.5px; }}
    QStatusBar {{ background: {card_bg}; border-top: 1.5px solid {border}; }}

    /* ===== STUDIO PAGE ELEMENTS ===== */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent; width: 11px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {line}; min-height: 30px; border: 3px solid {card_bg};
        border-radius: 8px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent; height: 11px; margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {line}; min-width: 30px; border: 3px solid {card_bg};
        border-radius: 8px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QRadioButton {{
        spacing: 8px; font-size: 13px;
    }}
    QRadioButton::indicator {{
        width: 15px; height: 15px; border-radius: 50%;
        border: 1.5px solid {muted}; background: transparent;
    }}
    QRadioButton::indicator:checked {{
        border: 1.5px solid {primary}; background: radial-gradient({primary} 42%, transparent 46%);
    }}
    QCheckBox {{
        spacing: 8px; font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 5px;
        border: 1.5px solid {muted}; background: transparent;
    }}
    QCheckBox::indicator:checked {{
        background: {primary}; border-color: {primary};
    }}
    QLineEdit {{
        background: {sunk}; border: 1.5px solid {line}; border-radius: 9px;
        padding: 10px 13px; font: 500 13px {FONT_STACK}; color: {ink};
    }}
    QLineEdit:focus {{ border-color: {secondary}; }}
    QComboBox {{
        background: {card_bg}; border: 1.5px solid {border}; border-radius: 9px;
        padding: 8px 12px; font: 500 13px {FONT_STACK}; color: {ink};
    }}
    QComboBox:hover {{ border-color: {secondary}; }}
    QComboBox[outputMode="true"] {{
        background: {primary_soft}; border: 1.5px solid {primary}; color: {primary_ink};
    }}
    QFrame#DropzoneHero {{
        background: {sunk}; border: 1.5px dashed {line}; border-radius: 9px;
    }}
    QComboBox::drop-down {{
        border: none; width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {card_bg}; border: 1.5px solid {border}; border-radius: 8px;
        selection-background-color: {secondary_soft}; selection-color: {ink};
        outline: none; padding: 4px;
    }}
    QTextEdit, QPlainTextEdit {{
        background: {sunk}; border: 1.5px solid {line}; border-radius: 8px;
        padding: 10px 12px; font: 500 13px {FONT_STACK}; color: {ink};
    }}
    QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {secondary};
    }}
    QTextEdit[logConsole="true"] {{
        background: {sunk}; color: {green}; border: 1.5px solid {line};
        border-radius: 8px; padding: 10px 12px;
    }}
    QPushButton {{
        font: 600 13px {FONT_STACK}; background: {card_bg};
        color: {ink}; border: 1.5px solid {border}; border-radius: 9px;
        padding: 9px 15px;
    }}
    QPushButton:hover {{ background: {panel2}; }}
    QPushButton:pressed {{ background: {sunk}; }}
    QPushButton:disabled {{ background: {sunk}; color: {muted}; border-color: {sunk}; }}
    QPushButton[softPanel="true"], QToolButton[softPanel="true"] {{
        background: {card_bg}; border: 1.5px solid {line};
    }}
    QLabel[previewPane="true"] {{
        background: {panel2}; border: 1.5px solid {border};
    }}
    """


def load_qss(filename):
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


def add_card_shadow(widget, blur=14.0, y_offset=6.0, alpha=90):
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setXOffset(0.0)
    effect.setYOffset(y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return effect


def load_fonts():
    """Load Space Grotesk and JetBrains Mono from bundled fonts directory."""
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    if not os.path.isdir(fonts_dir):
        return
    for fname in os.listdir(fonts_dir):
        if fname.lower().endswith((".ttf", ".otf")):
            QFontDatabase.addApplicationFont(os.path.join(fonts_dir, fname))


def apply_theme(app, dark=False):
    load_fonts()
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if dark else _light_palette())
    qss = _qss(dark)
    if dark:
        qss = qss + "\n" + load_qss("dark_theme.qss")
    app.setStyleSheet(qss)
    app.setProperty("lp_dark_theme", dark)


def is_dark(app=None):
    app = app or QApplication.instance()
    return bool(app and app.property("lp_dark_theme"))


def c(attr):
    """Return a context color by name, respecting current theme.

    Attributes: panel, panel2, sunk, border, line, ink, muted,
                primary, primary_hover, primary_soft, primary_ink,
                secondary, secondary_soft, secondary_ink,
                green, red, danger, success, warning.
    """
    dark = is_dark()
    _MAP = {
        "panel": (DARK_PANEL, LIGHT_PANEL),
        "panel2": (DARK_PANEL2, LIGHT_PANEL2),
        "sunk": (DARK_SUNK, LIGHT_SUNK),
        "border": (DARK_BORDER, LIGHT_BORDER),
        "line": (DARK_LINE, LIGHT_LINE),
        "ink": (DARK_INK, LIGHT_INK),
        "muted": (DARK_MUTED, LIGHT_MUTED),
        "primary": (DARK_PRIMARY, LIGHT_PRIMARY),
        "primary_hover": (DARK_PRIMARY_HOVER, LIGHT_PRIMARY_HOVER),
        "primary_soft": (DARK_PRIMARY_SOFT, LIGHT_PRIMARY_SOFT),
        "primary_ink": (DARK_PRIMARY_INK, LIGHT_PRIMARY_INK),
        "secondary": (DARK_SECONDARY, LIGHT_SECONDARY),
        "secondary_soft": (DARK_SECONDARY_SOFT, LIGHT_SECONDARY_SOFT),
        "secondary_ink": (DARK_SECONDARY_INK, LIGHT_SECONDARY_INK),
        "green": (DARK_GREEN, LIGHT_GREEN),
        "green_soft": (DARK_GREEN_SOFT, LIGHT_GREEN_SOFT),
        "red": (DARK_RED, LIGHT_RED),
        "red_soft": (DARK_RED_SOFT, LIGHT_RED_SOFT),
        "danger": (DARK_RED, LIGHT_RED),
        "success": (DARK_GREEN, LIGHT_GREEN),
        "warning": (DARK_YELLOW, LIGHT_YELLOW),
    }
    pair = _MAP.get(attr, (DARK_PANEL, LIGHT_PANEL))
    return pair[0] if dark else pair[1]
