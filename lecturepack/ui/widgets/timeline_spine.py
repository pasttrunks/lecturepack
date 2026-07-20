"""
lecturepack.ui.widgets.timeline_spine
======================================

A horizontal, scrubbable "lecture timeline" spine used by the Review page:
a track spanning the lecture's full duration, a tick mark per detected
slide candidate (colored by accepted/rejected/pending decision), a playhead
for the slide currently being viewed, and a hover thumbnail preview that
follows the cursor.

``TopicTimeline`` is a lighter sibling for the Study page: labeled,
non-scrubbing segments spanning topic durations.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lecturepack.services.transcript_formats import fmt_clock
from lecturepack.ui import theme
from lecturepack.ui.widgets.slide_grid import thumb_path_for

TRACK_HEIGHT = 4
TICK_WIDTH = 3
TICK_HEIGHT = 14
PLAYHEAD_D = 14


def _nearest_index(times: List[float], target: float) -> int:
    """Index of the value in ``times`` nearest ``target`` (times must be sorted)."""
    if not times:
        return -1
    from bisect import bisect_right
    right = bisect_right(times, target)
    if right == 0:
        return 0
    if right >= len(times):
        return len(times) - 1
    before, after = times[right - 1], times[right]
    return right - 1 if (target - before) <= (after - target) else right


class _ScrubPreview(QFrame):
    """Floating thumbnail + timestamp popup that follows the cursor."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(150)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(7)
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(134, 72)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setScaledContents(False)
        outer.addWidget(self.thumb_lbl)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.time_lbl = QLabel()
        self.time_lbl.setStyleSheet(f"font: 700 11px '{theme.FONT_MONO}'; border: none; background: transparent;")
        self.state_lbl = QLabel()
        self.state_lbl.setStyleSheet(
            f"font: 600 9px '{theme.FONT_MONO}'; text-transform: uppercase; "
            f"border: none; background: transparent;")
        row.addWidget(self.time_lbl)
        row.addStretch(1)
        row.addWidget(self.state_lbl)
        outer.addLayout(row)
        self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"_ScrubPreview {{ background: {theme.c('panel')}; "
            f"border: 2px solid {theme.c('border')}; border-radius: 11px; }}")
        self.thumb_lbl.setStyleSheet(
            f"background: {theme.c('sunk')}; border: 2px solid {theme.c('line')}; "
            f"border-radius: 6px; color: {theme.c('muted')};")
        self.state_lbl.setStyleSheet(
            self.state_lbl.styleSheet() + f"color: {theme.c('muted')};")

    def show_at(self, global_x: int, global_top_y: int, time_text: str,
                state_text: str, pixmap: Optional[QPixmap]):
        self._restyle()
        self.time_lbl.setText(time_text)
        self.state_lbl.setText(state_text)
        if pixmap is not None and not pixmap.isNull():
            self.thumb_lbl.setPixmap(
                pixmap.scaled(134, 72, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation))
        else:
            self.thumb_lbl.setPixmap(QPixmap())
            self.thumb_lbl.setText("no frame")
        self.adjustSize()
        self.move(global_x - self.width() // 2, global_top_y - self.height() - 10)
        self.show()


class TimelineSpine(QWidget):
    """Scrubbable horizontal timeline of slide candidates over lecture duration."""

    seek_requested = Signal(float)  # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumHeight(26)
        self.setMaximumHeight(26)
        self._duration = 0.0
        self._candidates: List[Dict[str, Any]] = []
        self._job_paths: Optional[dict] = None
        self._current_seconds: Optional[float] = None
        self._hovering = False
        self._preview = _ScrubPreview()
        self._preview.hide()

    def set_duration(self, seconds: float) -> None:
        self._duration = max(0.0, float(seconds or 0.0))
        self.update()

    def set_job_paths(self, job_paths: Optional[dict]) -> None:
        self._job_paths = job_paths

    def set_candidates(self, candidates: List[Dict[str, Any]]) -> None:
        self._candidates = list(candidates or [])
        self.update()

    def set_current_seconds(self, seconds: Optional[float]) -> None:
        self._current_seconds = seconds
        self.update()

    def _frac_of(self, seconds: float) -> float:
        if self._duration <= 0:
            return 0.0
        return min(max(seconds / self._duration, 0.0), 1.0)

    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        track_y = 11
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.c("sunk")))
        painter.drawRoundedRect(0, track_y, w, TRACK_HEIGHT, 2, 2)

        if self._duration > 0 and self._current_seconds is not None:
            fill_w = int(w * self._frac_of(self._current_seconds))
            painter.setBrush(QColor(theme.c("secondary")))
            painter.drawRoundedRect(0, track_y, fill_w, TRACK_HEIGHT, 2, 2)

        for cand in self._candidates:
            t = float(cand.get("timestamp_seconds", 0.0))
            x = int(w * self._frac_of(t))
            decision = cand.get("decision")
            color = theme.c("red") if decision == "rejected" else theme.c("secondary")
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(x - TICK_WIDTH // 2, track_y - 5, TICK_WIDTH, TICK_HEIGHT, 2, 2)

        if self._duration > 0 and self._current_seconds is not None:
            cx = int(w * self._frac_of(self._current_seconds))
            painter.setPen(QPen(QColor(theme.c("panel")), 3))
            painter.setBrush(QColor(theme.c("primary")))
            painter.drawEllipse(QPoint(cx, track_y + TRACK_HEIGHT // 2), PLAYHEAD_D // 2, PLAYHEAD_D // 2)

        painter.end()

    def _nearest_candidate(self, t: float) -> Optional[Dict[str, Any]]:
        if not self._candidates:
            return None
        times = [float(c.get("timestamp_seconds", 0.0)) for c in self._candidates]
        idx = _nearest_index(times, t)
        return self._candidates[idx] if idx >= 0 else None

    def _preview_pixmap(self, cand: Optional[Dict[str, Any]]) -> Optional[QPixmap]:
        if not cand or not self._job_paths:
            return None
        name = cand.get("image_filename", "")
        if not name:
            return None
        tp = thumb_path_for(self._job_paths, name)
        if os.path.exists(tp):
            pix = QPixmap(tp)
            if not pix.isNull():
                return pix
        src = os.path.join(self._job_paths.get("candidates", ""), name)
        if os.path.exists(src):
            pix = QPixmap(src)
            if not pix.isNull():
                return pix
        return None

    def mouseMoveEvent(self, event):
        if self._duration <= 0 or self.width() <= 0:
            return
        frac = min(max(event.position().x() / self.width(), 0.0), 1.0)
        t = frac * self._duration
        self._hovering = True
        cand = self._nearest_candidate(t)
        state = "viewing"
        if cand is not None:
            state = "rejected" if cand.get("decision") == "rejected" else "accepted"
        pos = self.mapToGlobal(QPoint(int(event.position().x()), 0))
        self._preview.show_at(pos.x(), pos.y(), fmt_clock(t), state, self._preview_pixmap(cand))
        self.update()

    def leaveEvent(self, event):
        self._hovering = False
        self._preview.hide()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self._duration <= 0 or self.width() <= 0:
            return
        frac = min(max(event.position().x() / self.width(), 0.0), 1.0)
        self.seek_requested.emit(frac * self._duration)

    def hideEvent(self, event):
        self._preview.hide()
        super().hideEvent(event)


class TopicTimeline(QWidget):
    """Non-scrubbing segmented bar of topic durations, for the Study page."""

    topic_clicked = Signal(int)  # topic index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setMaximumHeight(20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._duration = 0.0
        self._topics: List[Dict[str, Any]] = []  # {"start": float, "label": str}
        self._current_index = -1

    def set_topics(self, topics: List[Dict[str, Any]], duration: float) -> None:
        self._topics = list(topics or [])
        self._duration = max(0.0, float(duration or 0.0))
        self.update()

    def set_current_index(self, index: int) -> None:
        self._current_index = index
        self.update()

    def _bounds(self):
        """Yield (start_frac, end_frac, topic) for each topic segment."""
        if not self._topics or self._duration <= 0:
            return
        starts = [max(0.0, min(1.0, float(t.get("start", 0.0)) / self._duration)) for t in self._topics]
        for i, topic in enumerate(self._topics):
            end = starts[i + 1] if i + 1 < len(starts) else 1.0
            yield starts[i], end, topic

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        y, h = 4, 16
        for i, (s, e, _topic) in enumerate(self._bounds()):
            x0, x1 = int(w * s), int(w * e)
            active = i == self._current_index
            painter.setPen(QPen(QColor(theme.c("secondary" if active else "line")), 1.5))
            painter.setBrush(QColor(theme.c("secondary_tint") if active else theme.c("sunk")))
            painter.drawRoundedRect(x0 + 1, y, max(2, x1 - x0 - 2), h, 4, 4)
        painter.end()

    def mousePressEvent(self, event):
        if not self._topics:
            return
        frac = min(max(event.position().x() / max(1, self.width()), 0.0), 1.0)
        for i, (s, e, _topic) in enumerate(self._bounds()):
            if s <= frac <= e:
                self.topic_clicked.emit(i)
                return
