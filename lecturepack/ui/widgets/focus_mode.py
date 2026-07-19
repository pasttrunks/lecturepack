"""Focus Mode controller for the Phase 2 shell.

Fades the shell chrome (nav rail, command bar, status bar) to opacity 0 and
hides it so the page stack expands to fill the window, leaving only a
floating, semi-transparent "Exit Focus" button in the bottom-right corner.
Animations are ``QPropertyAnimation``s on per-widget
``QGraphicsOpacityEffect``s; widgets are hidden only after the fade-out
completes (so the layout does not jump mid-animation) and re-shown before
the fade-in starts.
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import QEvent, QObject, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QPushButton, QWidget

_FADE_MS = 250
_MARGIN = 24


class FocusModeController(QObject):
    toggled = Signal(bool)

    def __init__(self, window: QWidget, chrome_widgets: List[QWidget],
                 parent=None):
        super().__init__(parent or window)
        self._window = window
        self._chrome = list(chrome_widgets)
        self._active = False
        self._animations: List[QPropertyAnimation] = []

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
        for widget in self._chrome:
            effect = self._ensure_effect(widget)
            anim = self._fade(effect, 0.0)
            anim.finished.connect(lambda w=widget: self._hide_if_active(w))
        self._reposition_exit()
        self.exit_btn.show()
        self.exit_btn.raise_()
        self.toggled.emit(True)

    def exit(self):
        if not self._active:
            return
        self._active = False
        self._stop_animations()
        for widget in self._chrome:
            widget.setVisible(True)
            effect = self._ensure_effect(widget)
            self._fade(effect, 1.0)
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
        anim.setDuration(_FADE_MS)
        anim.setStartValue(effect.opacity())
        anim.setEndValue(target)
        anim.start()
        self._animations.append(anim)
        return anim

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
