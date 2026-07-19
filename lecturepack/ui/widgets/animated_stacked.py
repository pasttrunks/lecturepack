"""QStackedWidget with a subtle slide+fade page transition (Phase 2).

The incoming page slides in from the right (~8% of width) while fading from
0 to 1, driven by a ``QParallelAnimationGroup``. The transition is skipped
before the window is first shown and guarded against rapid re-navigation
(the in-flight animation finishes instantly before the next one starts).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget

_TRANSITION_MS = 180
_OFFSET_FRACTION = 0.08


class AnimatedStackedWidget(QStackedWidget):
    def __init__(self, parent=None, animate: bool = True):
        super().__init__(parent)
        self._animate = animate
        self._group: Optional[QParallelAnimationGroup] = None

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 (Qt naming)
        index = int(index)
        if not self._animate or self.count() == 0 \
                or index == self.currentIndex():
            super().setCurrentIndex(index)
            return
        if self._group is not None:
            # Rapid navigation: kill the in-flight transition instantly.
            self._group.stop()
            self._cleanup_animation()
        target = self.widget(index)
        super().setCurrentIndex(index)
        if target is None or not self.isVisible():
            return

        offset = int(max(1, self.width()) * _OFFSET_FRACTION)
        effect = QGraphicsOpacityEffect(target)
        effect.setOpacity(0.0)
        target.setGraphicsEffect(effect)

        pos_anim = QPropertyAnimation(target, b"pos", self)
        pos_anim.setStartValue(target.pos() + QPoint(offset, 0))
        pos_anim.setEndValue(target.pos())
        pos_anim.setDuration(_TRANSITION_MS)
        pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade_anim = QPropertyAnimation(effect, b"opacity", self)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setDuration(_TRANSITION_MS)
        fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(pos_anim)
        group.addAnimation(fade_anim)
        group.finished.connect(self._cleanup_animation)
        group.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)
        self._group = group

    def _cleanup_animation(self) -> None:
        self._group = None
        widget = self.currentWidget()
        if widget is not None \
                and isinstance(widget.graphicsEffect(), QGraphicsOpacityEffect):
            widget.setGraphicsEffect(None)
