"""Focus Mode controller for the Phase 2 shell.

Collapses the shell chrome (nav rail, command bar, status bar) -- fading to
opacity 0 while their width/height animate down to 0, mirroring the design
mockup's header/footer slide-away and sidebar collapse -- so the page stack
expands to fill the window, leaving only a floating "Exit Focus" button in
the bottom-right corner. On entry, the main content area gets a brief
"iris" opacity settle to draw the eye inward as the chrome clears.

Animations are ``QPropertyAnimation``s on per-widget
``QGraphicsOpacityEffect``s (for fade) and on ``maximumWidth``/
``maximumHeight`` (for collapse); widgets are hidden only after the
collapse completes (so the layout does not jump mid-animation) and
re-shown before the expand-back starts.
"""
from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, Signal,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QPushButton, QWidget

_ANIM_MS = 420
_IRIS_MS = 420
_MARGIN = 24

# Chrome widget entries are (widget, axis) where axis is the dimension that
# collapses to 0 -- "width" for the sidebar, "height" for header/footer.
ChromeEntry = Tuple[QWidget, str]


class FocusModeController(QObject):
    toggled = Signal(bool)

    def __init__(self, window: QWidget, chrome_widgets: List,
                 content_widget: QWidget = None, parent=None):
        super().__init__(parent or window)
        self._window = window
        self._content = content_widget
        self._active = False
        self._animations: List[QPropertyAnimation] = []

        # Back-compat: accept either a plain list of widgets (axis inferred
        # from aspect ratio) or a list of (widget, axis) tuples.
        self._chrome: List[ChromeEntry] = []
        for entry in chrome_widgets:
            if isinstance(entry, tuple):
                self._chrome.append(entry)
            else:
                axis = "width" if entry.height() > entry.width() else "height"
                self._chrome.append((entry, axis))

        self._natural = {}
        for widget, axis in self._chrome:
            self._natural[widget] = (
                widget.maximumWidth() if axis == "width" else widget.maximumHeight())

        self.exit_btn = QPushButton("Exit Focus", window)
        self.exit_btn.setObjectName("FocusExitButton")
        self.exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_btn.clicked.connect(self.exit)
        self.exit_btn.hide()

        window.installEventFilter(self)

    # ------------------------------------------------------------------ #
    def is_active(self) -> bool:
        return self._active

    def toggle(self):
        if self._active:
            self.exit()
        else:
            self.enter()

    # ------------------------------------------------------------------ #
    def enter(self):
        if self._active:
            return
        self._active = True
        self._stop_animations()
        for widget, axis in self._chrome:
            effect = self._ensure_effect(widget)
            self._fade(effect, 0.0)
            natural = self._natural[widget]
            size_anim = self._collapse(widget, axis, natural, 0)
            size_anim.finished.connect(lambda w=widget: self._hide_if_active(w))
        self._animate_iris()
        self._reposition_exit()
        self.exit_btn.show()
        self.exit_btn.raise_()
        self.toggled.emit(True)

    def exit(self):
        if not self._active:
            return
        self._active = False
        self._stop_animations()
        for widget, axis in self._chrome:
            widget.setVisible(True)
            effect = self._ensure_effect(widget)
            self._fade(effect, 1.0)
            natural = self._natural[widget]
            size_anim = self._collapse(widget, axis, 0, natural)
            size_anim.finished.connect(
                lambda w=widget, ax=axis, n=natural: self._restore_fixed(w, ax, n))
        self.exit_btn.hide()
        self.toggled.emit(False)

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _ensure_effect(self, widget: QWidget) -> QGraphicsOpacityEffect:
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(1.0)
            widget.setGraphicsEffect(effect)
        return effect

    def _fade(self, effect: QGraphicsOpacityEffect,
              target: float) -> QPropertyAnimation:
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(_ANIM_MS)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(effect.opacity())
        anim.setEndValue(target)
        anim.start()
        self._animations.append(anim)
        return anim

    def _collapse(self, widget: QWidget, axis: str, start: int,
                  end: int) -> QPropertyAnimation:
        if axis == "width":
            widget.setMinimumWidth(0)
            anim = QPropertyAnimation(widget, b"maximumWidth", self)
        else:
            widget.setMinimumHeight(0)
            anim = QPropertyAnimation(widget, b"maximumHeight", self)
        anim.setDuration(_ANIM_MS)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.start()
        self._animations.append(anim)
        return anim

    def _restore_fixed(self, widget: QWidget, axis: str, natural: int):
        if axis == "width":
            widget.setFixedWidth(natural)
        else:
            widget.setFixedHeight(natural)

    def _animate_iris(self):
        if self._content is None:
            return
        effect = QGraphicsOpacityEffect(self._content)
        effect.setOpacity(0.75)
        self._content.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(_IRIS_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(0.75)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: self._content.setGraphicsEffect(None))
        anim.start()
        self._animations.append(anim)

    def _hide_if_active(self, widget: QWidget):
        if self._active:
            widget.setVisible(False)

    def _stop_animations(self):
        for anim in self._animations:
            anim.stop()
        self._animations.clear()

    def _reposition_exit(self):
        self.exit_btn.adjustSize()
        x = max(_MARGIN, self._window.width() - self.exit_btn.width() - _MARGIN)
        y = max(_MARGIN, self._window.height() - self.exit_btn.height() - _MARGIN)
        self.exit_btn.move(x, y)

    def eventFilter(self, watched, event):  # noqa: N802 (Qt naming)
        if watched is self._window and self._active \
                and event.type() == QEvent.Type.Resize:
            self._reposition_exit()
        return super().eventFilter(watched, event)
