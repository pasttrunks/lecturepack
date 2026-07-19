"""Custom frameless title bar for the Phase 2 shell.

Replaces the native Windows title bar: app mark + title on the left,
minimize / maximize-restore / close buttons on the right. The bar drags the
host window (suppressed while maximized) and double-click toggles maximize.
Styling lives in ``themes/dark_theme.qss`` under ``#AppTitleBar``.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton


class TitleBarWidget(QFrame):
    minimize_clicked = Signal()
    toggle_maximize_clicked = Signal()
    close_clicked = Signal()

    HEIGHT = 40

    def __init__(self, title: str = "", app_mark: str = "◆", parent=None):
        super().__init__(parent)
        self.setObjectName("AppTitleBar")
        self.setFixedHeight(self.HEIGHT)
        self._drag_offset: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(8)

        self.mark_lbl = QLabel(app_mark)
        self.mark_lbl.setObjectName("AppTitleMark")
        layout.addWidget(self.mark_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("AppTitleText")
        layout.addWidget(self.title_lbl)
        layout.addStretch(1)

        self.min_btn = self._make_button("–", "titleBarMin",
                                         self.minimize_clicked)
        self.max_btn = self._make_button("□", "titleBarMax",
                                         self.toggle_maximize_clicked)
        self.close_btn = self._make_button("×", "titleBarClose",
                                           self.close_clicked)
        for button in (self.min_btn, self.max_btn, self.close_btn):
            layout.addWidget(button)

    # ------------------------------------------------------------------ #
    def _make_button(self, text: str, name: str, signal: Signal) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setObjectName(name)
        button.setProperty("titleBarButton", True)
        button.setFixedSize(40, 28)
        button.clicked.connect(signal.emit)
        return button

    def set_maximized(self, maximized: bool) -> None:
        self.max_btn.setText("▣" if maximized else "□")

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
