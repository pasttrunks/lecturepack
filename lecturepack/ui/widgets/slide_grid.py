"""
lecturepack.ui.widgets.slide_grid
=================================

Slide candidate list/grid with UNMISTAKABLE selection (v1.1, Phase 2):

  * >= 3 px accent outline around the selected tile,
  * contrasting selected background,
  * checkmark badge on selected tiles,
  * a distinct focus ring while the widget has keyboard focus,
  * automatic scroll-into-view,
  * synchronized selection-count reporting.

Painting is driven by ``theme.selection_visuals`` -- a pure function tests
assert on directly, in addition to pixel-level checks.

Thumbnails are decoded lazily off the GUI thread (ThumbnailLoader) and cached
as WebP files under ``frames/thumbs/`` so re-opening a job never re-decodes
full-resolution candidate PNGs.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QRect, QSize, Qt, QThread, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QListWidget, QListWidgetItem, QMenu,
                               QStyle, QStyledItemDelegate)

from lecturepack.ui import theme

THUMB_ROLE = Qt.ItemDataRole.UserRole + 1     # QPixmap thumbnail
CAND_ROLE = Qt.ItemDataRole.UserRole          # candidate dict

THUMB_MAX_W = 320  # cached thumbnail width (grid shows ~176px, list ~120px)


def thumbs_dir(job_paths: dict) -> str:
    return os.path.join(job_paths["frames"], "thumbs")


def thumb_path_for(job_paths: dict, image_filename: str) -> str:
    base = os.path.splitext(image_filename)[0]
    return os.path.join(thumbs_dir(job_paths), base + ".webp")


class ThumbnailLoader(QThread):
    """Decodes/creates thumbnails off the GUI thread; emits (row, QImage)."""
    thumb_ready = Signal(int, QImage)

    def __init__(self, job_paths: dict, filenames: list, parent=None):
        super().__init__(parent)
        self.job_paths = job_paths
        self.filenames = list(filenames)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        os.makedirs(thumbs_dir(self.job_paths), exist_ok=True)
        for row, name in enumerate(self.filenames):
            if self._cancelled:
                return
            if not name:
                continue
            tp = thumb_path_for(self.job_paths, name)
            img = QImage(tp) if os.path.exists(tp) else QImage()
            if img.isNull():
                src = os.path.join(self.job_paths["candidates"], name)
                if not os.path.exists(src):
                    continue
                full = QImage(src)
                if full.isNull():
                    continue
                img = full.scaledToWidth(THUMB_MAX_W, Qt.SmoothTransformation)
                # WebP thumbnails: ~10x smaller than the source PNGs.
                img.save(tp, "WEBP", 82)
            if not img.isNull():
                self.thumb_ready.emit(row, img)


class SlideTileDelegate(QStyledItemDelegate):
    """Paints one slide tile according to theme.selection_visuals."""

    GRID_TILE = QSize(196, 158)
    LIST_TILE = QSize(0, 64)  # width follows the view

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view

    def sizeHint(self, option, index):
        if self.view.viewMode() == QListWidget.ViewMode.IconMode:
            return self.GRID_TILE
        return QSize(self.view.viewport().width(), 64)

    def paint(self, painter: QPainter, option, index):
        cand = index.data(CAND_ROLE) or {}
        thumb = index.data(THUMB_ROLE)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        focused = self.view.hasFocus()
        vis = theme.selection_visuals(
            selected, focused, cand.get("decision", "accepted"), theme.is_dark())

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = option.rect.adjusted(4, 4, -4, -4)

        # Background card
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        painter.fillPath(path, vis["background"])

        # Selection outline (>= 3 px accent)
        if vis["outline_width"]:
            pen = QPen(vis["outline_color"], vis["outline_width"])
            painter.setPen(pen)
            painter.drawRoundedRect(
                r.adjusted(vis["outline_width"] // 2, vis["outline_width"] // 2,
                           -(vis["outline_width"] // 2), -(vis["outline_width"] // 2)), 6, 6)
        if vis["focus_ring_visible"]:
            pen = QPen(vis["focus_ring_color"], 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 8, 8)

        grid = self.view.viewMode() == QListWidget.ViewMode.IconMode
        pad = 8
        if grid:
            img_rect = QRect(r.left() + pad, r.top() + pad, r.width() - 2 * pad,
                             r.height() - 2 * pad - 26)
            text_rect = QRect(r.left() + pad, img_rect.bottom() + 4,
                              r.width() - 2 * pad, 20)
        else:
            img_rect = QRect(r.left() + pad, r.top() + 6, 84, r.height() - 12)
            text_rect = QRect(img_rect.right() + 10, r.top() + 6,
                              r.width() - img_rect.width() - 3 * pad, r.height() - 12)

        if isinstance(thumb, QPixmap) and not thumb.isNull():
            scaled = thumb.scaled(img_rect.size(), Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation)
            dx = img_rect.x() + (img_rect.width() - scaled.width()) // 2
            dy = img_rect.y() + (img_rect.height() - scaled.height()) // 2
            painter.drawPixmap(dx, dy, scaled)
        else:
            painter.setPen(QPen(QColor("#9aa1ac")))
            painter.drawText(img_rect, Qt.AlignCenter, "…")

        # Label: timestamp + decision
        painter.setPen(option.palette.text().color())
        f = QFont(option.font)
        f.setPointSizeF(max(7.5, f.pointSizeF() - 0.5))
        painter.setFont(f)
        ts = cand.get("timestamp_formatted", "")
        label = ts.split(".")[0] if ts else ""
        decision = cand.get("decision", "accepted")
        if decision == "rejected":
            label += "  ·  rejected"
        fm = QFontMetrics(f)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         fm.elidedText(label, Qt.ElideRight, text_rect.width()))

        # Decision dot (green kept / red rejected)
        dot = QRect(r.right() - 14, r.bottom() - 14, 8, 8)
        painter.setBrush(vis["decision_badge_color"])
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(dot)

        # Selected checkmark badge (top-right)
        if vis["checkmark_visible"]:
            d = theme.CHECKMARK_DIAMETER
            badge = QRect(r.right() - d - 6, r.top() + 6, d, d)
            painter.setBrush(vis["checkmark_bg"])
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(badge)
            pen = QPen(QColor("white"), 2.4)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            cx, cy = badge.center().x(), badge.center().y()
            painter.drawLine(cx - 5, cy + 1, cx - 1, cy + 5)
            painter.drawLine(cx - 1, cy + 5, cx + 6, cy - 4)

        painter.restore()


class SlideGridWidget(QListWidget):
    """The review slide timeline. Compact-list and thumbnail-grid modes.

    Emits requests instead of mutating job data itself -- the review page owns
    persistence and undo.
    """
    decision_requested = Signal(str)          # 'keep' | 'reject' | 'restore'
    export_selected_requested = Signal()
    copy_image_requested = Signal(object)     # candidate dict
    open_timestamp_requested = Signal(object) # candidate dict
    activate_preview_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._delegate = SlideTileDelegate(self, self)
        self.setItemDelegate(self._delegate)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemSelectionChanged.connect(self._scroll_to_current)
        self._loader = None
        self.set_display_mode("grid")

    # ---- population ---------------------------------------------------- #
    def load_candidates(self, candidates: list, job_paths: dict):
        if self._loader is not None:
            self._loader.cancel()
            self._loader.wait(2000)
            self._loader = None
        self.clear()
        for cand in candidates:
            item = QListWidgetItem()
            item.setData(CAND_ROLE, cand)
            label = f"@{cand.get('timestamp_formatted', '')}"
            if cand.get("decision") == "rejected":
                label += " [Rejected]"
            item.setData(Qt.ItemDataRole.DisplayRole, label)  # accessibility/tests
            self.addItem(item)
        names = [c.get("image_filename", "") for c in candidates]
        if names and job_paths:
            self._loader = ThumbnailLoader(job_paths, names, self)
            self._loader.thumb_ready.connect(self._on_thumb_ready)
            self._loader.start()

    def _on_thumb_ready(self, row: int, img: QImage):
        if 0 <= row < self.count():
            self.item(row).setData(THUMB_ROLE, QPixmap.fromImage(img))
            self.viewport().update()

    def shutdown(self):
        if self._loader is not None:
            self._loader.cancel()
            self._loader.wait(2000)
            self._loader = None

    # ---- modes ---------------------------------------------------------- #
    def set_display_mode(self, mode: str):
        self._display_mode = mode
        if mode == "grid":
            self.setViewMode(QListWidget.ViewMode.IconMode)
            self.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.setWrapping(True)
            self.setSpacing(4)
            self.setFlow(QListWidget.Flow.LeftToRight)
        else:
            self.setViewMode(QListWidget.ViewMode.ListMode)
            self.setWrapping(False)
            self.setSpacing(2)
            self.setFlow(QListWidget.Flow.TopToBottom)
        self.doItemsLayout()

    def display_mode(self) -> str:
        return self._display_mode

    # ---- behavior -------------------------------------------------------- #
    def _scroll_to_current(self):
        item = self.currentItem()
        if item is not None:
            self.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Delete:
            self.decision_requested.emit("reject")
            return
        if key == Qt.Key_R and not event.modifiers():
            self.decision_requested.emit("restore")
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.activate_preview_requested.emit()
            return
        super().keyPressEvent(event)

    def _context_menu(self, pos):
        item = self.itemAt(pos)
        menu = QMenu(self)
        act_keep = menu.addAction("Keep")
        act_reject = menu.addAction("Reject")
        act_restore = menu.addAction("Restore")
        menu.addSeparator()
        act_export = menu.addAction("Export selected…")
        act_copy = menu.addAction("Copy image")
        act_open = menu.addAction("Open source timestamp")
        act_copy.setEnabled(item is not None)
        act_open.setEnabled(item is not None)
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_keep:
            self.decision_requested.emit("keep")
        elif chosen == act_reject:
            self.decision_requested.emit("reject")
        elif chosen == act_restore:
            self.decision_requested.emit("restore")
        elif chosen == act_export:
            self.export_selected_requested.emit()
        elif chosen == act_copy and item is not None:
            self.copy_image_requested.emit(item.data(CAND_ROLE))
        elif chosen == act_open and item is not None:
            self.open_timestamp_requested.emit(item.data(CAND_ROLE))
