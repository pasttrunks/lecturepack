"""Transcript block widgets for the Phase 2 spatial workspace.

A transcript is rendered as a column of :class:`TranscriptBlockWidget` cards
inside a :class:`TranscriptStreamView` (a ``QScrollArea``). Blocks are
materialized lazily in batches so long lectures never pay the full widget
cost up front, while the pure ``bisect`` helpers keep timestamp matching
O(log n) over the segment data (no Qt required -> directly unit-testable).

Visual states are driven by the dynamic properties styled in
``themes/dark_theme.qss``: ``selected``, ``live`` and the built-in ``:hover``.
"""
from __future__ import annotations

from bisect import bisect_right
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from lecturepack.services.transcript_formats import fmt_clock

BATCH_SIZE = 120
SCROLL_DEBOUNCE_MS = 50


# --------------------------------------------------------------------- #
# pure timestamp matching (no Qt)                                        #
# --------------------------------------------------------------------- #
def find_segment_index(segments: List[Dict[str, Any]], timestamp: float) -> int:
    """Index of the segment containing ``timestamp`` (floor on start times).

    ``segments`` must be sorted by ``start`` (working transcripts always
    are). Returns -1 for empty input; timestamps before the first segment
    clamp to index 0.
    """
    if not segments:
        return -1
    starts = [float(s.get("start", 0.0)) for s in segments]
    idx = bisect_right(starts, float(timestamp)) - 1
    return max(0, min(idx, len(segments) - 1))


def find_slide_index(candidates: List[Dict[str, Any]], timestamp: float) -> int:
    """Index of the slide candidate whose timestamp is NEAREST to ``timestamp``.

    ``candidates`` must be sorted by ``timestamp_seconds``. Returns -1 for
    empty input.
    """
    if not candidates:
        return -1
    times = [float(c.get("timestamp_seconds", 0.0)) for c in candidates]
    target = float(timestamp)
    right = bisect_right(times, target)
    if right == 0:
        return 0
    if right >= len(times):
        return len(times) - 1
    before, after = times[right - 1], times[right]
    return right - 1 if (target - before) <= (after - target) else right


# --------------------------------------------------------------------- #
# single transcript block                                                #
# --------------------------------------------------------------------- #
class TranscriptBlockWidget(QFrame):
    """One transcript segment rendered as a hoverable/selectable card."""

    activated = Signal(float)   # start time in seconds (user clicked)

    def __init__(self, start_seconds: float, text: str,
                 live: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("TranscriptBlock")
        self.start_seconds = float(start_seconds)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        self.time_lbl = QLabel(fmt_clock(self.start_seconds))
        self.time_lbl.setProperty("blockTime", True)
        layout.addWidget(self.time_lbl)
        self.text_lbl = QLabel(text)
        self.text_lbl.setProperty("blockText", True)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.text_lbl)

        self._selected = False
        if live:
            self.setProperty("live", True)

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if selected == self._selected:
            return
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt naming)
        if event.button() == Qt.MouseButton.LeftButton \
                and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.start_seconds)
        super().mouseReleaseEvent(event)


# --------------------------------------------------------------------- #
# lazily-materialized scrollable column of blocks                        #
# --------------------------------------------------------------------- #
class TranscriptStreamView(QScrollArea):
    """Scrollable transcript column with lazy batching and smooth scrolling.

    - ``set_segments`` loads data; only the first ``batch_size`` blocks are
      built; more are appended as the user scrolls past 80% or when
      ``ensure_materialized`` requires them.
    - ``live=True`` + ``max_blocks=N`` makes it a capped streaming view for
      the Process page (oldest blocks are trimmed, auto-scroll when pinned
      to the bottom).
    """

    block_activated = Signal(float)     # start seconds of clicked block
    viewed_index_changed = Signal(int)  # topmost visible block (debounced)

    def __init__(self, live: bool = False, max_blocks: Optional[int] = None,
                 batch_size: int = BATCH_SIZE, animate_scroll: bool = True,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("TranscriptStreamArea")
        self.setWidgetResizable(True)
        self._live = live
        self._max_blocks = max_blocks
        self._batch = max(1, int(batch_size))
        self._animate_scroll = animate_scroll
        self._segments: List[Dict[str, Any]] = []
        self._blocks: List[TranscriptBlockWidget] = []
        self._selected_index = -1
        self._scroll_anim: Optional[QPropertyAnimation] = None

        self._container = QWidget()
        self._block_layout = QVBoxLayout(self._container)
        self._block_layout.setContentsMargins(8, 8, 8, 8)
        self._block_layout.setSpacing(4)
        self._block_layout.addStretch(1)
        self.setWidget(self._container)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SCROLL_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._emit_viewed_index)
        self.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    # ------------------------------------------------------------------ #
    # data                                                               #
    # ------------------------------------------------------------------ #
    def set_segments(self, segments: List[Dict[str, Any]]) -> None:
        self.clear()
        self._segments = list(segments or [])
        self._extend_to(min(self._batch, len(self._segments)))

    def append_segment(self, start: float, end: float, text: str) -> None:
        bar = self.verticalScrollBar()
        was_near_bottom = bar.value() >= bar.maximum() - 60
        self._segments.append(
            {"start": float(start), "end": float(end), "text": str(text)})
        self._append_block(self._segments[-1])
        self._trim_if_needed()
        if self._live and was_near_bottom:
            QTimer.singleShot(0, self._scroll_to_end)

    def clear(self) -> None:
        self._segments = []
        self._blocks = []
        self._selected_index = -1
        while self._block_layout.count() > 1:
            item = self._block_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # ------------------------------------------------------------------ #
    # introspection (used by sync engine and tests)                      #
    # ------------------------------------------------------------------ #
    def segment_count(self) -> int:
        return len(self._segments)

    def materialized_count(self) -> int:
        return len(self._blocks)

    def block_at(self, index: int) -> Optional[TranscriptBlockWidget]:
        if 0 <= index < len(self._blocks):
            return self._blocks[index]
        return None

    def selected_index(self) -> int:
        return self._selected_index

    def segment_at(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self._segments):
            return self._segments[index]
        return None

    # ------------------------------------------------------------------ #
    # navigation                                                         #
    # ------------------------------------------------------------------ #
    def ensure_materialized(self, index: int) -> None:
        if not self._segments:
            return
        index = min(max(0, index), len(self._segments) - 1)
        while len(self._blocks) <= index:
            self._extend_to(min(len(self._blocks) + self._batch,
                                len(self._segments)))

    def scroll_to_index(self, index: int, smooth: bool = True) -> None:
        if not self._segments:
            return
        self.ensure_materialized(index)
        block = self._blocks[min(max(0, index), len(self._blocks) - 1)]
        target = max(0, block.y() - 12)
        bar = self.verticalScrollBar()
        if smooth and self._animate_scroll:
            if self._scroll_anim is not None:
                self._scroll_anim.stop()
            anim = QPropertyAnimation(bar, b"value", self)
            anim.setDuration(300)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(bar.value())
            anim.setEndValue(target)
            anim.start()
            self._scroll_anim = anim
        else:
            bar.setValue(target)

    def select_index(self, index: int) -> None:
        old = self.block_at(self._selected_index)
        if old is not None:
            old.set_selected(False)
        self.ensure_materialized(index)
        block = self.block_at(index)
        self._selected_index = index if block is not None else -1
        if block is not None:
            block.set_selected(True)

    def top_visible_index(self) -> int:
        """Index of the block at (or just above) the viewport's top edge."""
        if not self._blocks:
            return -1
        top = self.verticalScrollBar().value() + 4
        ys = [block.y() for block in self._blocks]
        return max(0, bisect_right(ys, top) - 1)

    # ------------------------------------------------------------------ #
    # internals                                                          #
    # ------------------------------------------------------------------ #
    def _append_block(self, segment: Dict[str, Any]) -> None:
        block = TranscriptBlockWidget(
            float(segment.get("start", 0.0)),
            str(segment.get("text", "")),
            live=self._live)
        block.activated.connect(self.block_activated)
        self._block_layout.insertWidget(self._block_layout.count() - 1, block)
        self._blocks.append(block)

    def _extend_to(self, count: int) -> None:
        while len(self._blocks) < count:
            self._append_block(self._segments[len(self._blocks)])

    def _trim_if_needed(self) -> None:
        if not self._max_blocks:
            return
        while len(self._blocks) > self._max_blocks:
            block = self._blocks.pop(0)
            self._block_layout.removeWidget(block)
            block.deleteLater()
            if self._selected_index >= 0:
                self._selected_index -= 1
        while len(self._segments) > self._max_blocks:
            self._segments.pop(0)

    def _on_scrolled(self, value: int) -> None:
        bar = self.verticalScrollBar()
        if bar.maximum() > 0 and value >= int(bar.maximum() * 0.8):
            self._extend_to(min(len(self._blocks) + self._batch,
                                len(self._segments)))
        self._debounce.start()

    def _emit_viewed_index(self) -> None:
        index = self.top_visible_index()
        if index >= 0:
            self.viewed_index_changed.emit(index)

    def _scroll_to_end(self) -> None:
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
