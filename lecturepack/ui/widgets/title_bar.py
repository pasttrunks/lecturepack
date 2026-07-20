"""Studio-style header bar for the LecturePack shell.

Replaces the native Windows title bar with a 56px header containing:
  - Logo (blue square + white diamond) + "LecturePack" wordmark
  - Vertical divider
  - Breadcrumb (job title > page name)
  - Theme toggle button
  - Save / Export buttons
  - Min / Max / Close window controls
  - 2px blue accent line at the bottom edge

The bar supports frameless window dragging and double-click maximize.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QWidget,
)


class HeaderBarWidget(QFrame):
    """56px Studio-style header bar with logo, breadcrumbs, and actions."""

    minimize_clicked = Signal()
    toggle_maximize_clicked = Signal()
    close_clicked = Signal()
    theme_toggled = Signal()
    save_clicked = Signal()
    export_clicked = Signal()

    HEIGHT = 56

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("AppHeaderBar")
        self.setFixedHeight(self.HEIGHT)
        self._drag_offset: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 12, 0)
        layout.setSpacing(0)

        # ---- logo mark (28x28 blue square with white diamond) ---- #
        logo_container = QFrame()
        logo_container.setObjectName("LogoMark")
        logo_container.setFixedSize(28, 28)
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        diamond = QLabel("\u25C7")
        diamond.setObjectName("LogoDiamond")
        diamond.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout.addWidget(diamond)
        layout.addWidget(logo_container)

        # ---- wordmark ---- #
        layout.addSpacing(9)
        self.wordmark_lbl = QLabel()
        self.wordmark_lbl.setObjectName("AppWordmark")
        self.wordmark_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.wordmark_lbl.setText(
            '<span style="font-weight:700;font-size:16px;">Lecture</span>'
            '<span style="font-weight:700;font-size:16px;color:#FF6B35;">Pack</span>'
        )
        layout.addWidget(self.wordmark_lbl)

        # ---- vertical divider ---- #
        layout.addSpacing(14)
        divider = QFrame()
        divider.setObjectName("HeaderDivider")
        divider.setFixedWidth(1)
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("background:transparent;")
        layout.addWidget(divider)

        # ---- breadcrumb ---- #
        layout.addSpacing(14)
        self.breadcrumb_lbl = QLabel("Home")
        self.breadcrumb_lbl.setObjectName("AppBreadcrumb")
        layout.addWidget(self.breadcrumb_lbl)
        layout.addStretch(1)

        # ---- theme toggle ---- #
        self.theme_btn = QToolButton()
        self.theme_btn.setObjectName("ThemeToggleBtn")
        self.theme_btn.setText("DARK")
        self.theme_btn.clicked.connect(self.theme_toggled.emit)
        layout.addWidget(self.theme_btn)

        # ---- spacer ---- #
        layout.addSpacing(8)

        # ---- save ---- #
        self.save_btn = QToolButton()
        self.save_btn.setObjectName("HeaderSaveBtn")
        self.save_btn.setText("Save")
        self.save_btn.clicked.connect(self.save_clicked.emit)
        layout.addWidget(self.save_btn)

        # ---- spacer ---- #
        layout.addSpacing(6)

        # ---- export (orange CTA) ---- #
        self.export_btn = QToolButton()
        self.export_btn.setObjectName("HeaderExportBtn")
        self.export_btn.setText("\u2B07 Export")
        self.export_btn.clicked.connect(self.export_clicked.emit)
        layout.addWidget(self.export_btn)

        # ---- spacer before window controls ---- #
        layout.addSpacing(12)

        # ---- min / max / close ---- #
        self.min_btn = self._make_button("\u2013", "titleBarMin",
                                         self.minimize_clicked)
        self.max_btn = self._make_button("\u25A1", "titleBarMax",
                                         self.toggle_maximize_clicked)
        self.close_btn = self._make_button("\u00D7", "titleBarClose",
                                           self.close_clicked)
        for button in (self.min_btn, self.max_btn, self.close_btn):
            layout.addWidget(button)

    # ------------------------------------------------------------------ #
    def _make_button(self, text: str, name: str, signal) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setObjectName(name)
        button.setProperty("titleBarButton", True)
        button.setFixedSize(40, 28)
        button.clicked.connect(signal.emit)
        return button

    def set_maximized(self, maximized: bool) -> None:
        self.max_btn.setText("\u25A3" if maximized else "\u25A1")

    def set_breadcrumb(self, text: str) -> None:
        """Update the breadcrumb label (e.g. 'egypt_excerpt > Process')."""
        self.breadcrumb_lbl.setText(text)

    def set_theme_label(self, dark: bool) -> None:
        """Update the theme toggle button label."""
        self.theme_btn.setText("LIGHT" if dark else "DARK")

    def set_wordmark_theme(self, dark: bool) -> None:
        """Update the wordmark color for theme."""
        pack_color = "#FF6B35" if dark else "#F15A24"
        self.wordmark_lbl.setText(
            f'<span style="font-weight:700;font-size:16px;">Lecture</span>'
            f'<span style="font-weight:700;font-size:16px;color:{pack_color};">Pack</span>'
        )

    # ------------------------------------------------------------------ #
    # window dragging                                                    #
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            self._drag_offset = (event.globalPosition().toPoint()
                                 - window.frameGeometry().topLeft())
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None \
                and event.buttons() & Qt.MouseButton.LeftButton:
            window = self.window()
            if not window.isMaximized():
                window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize_clicked.emit()
        super().mouseDoubleClickEvent(event)
