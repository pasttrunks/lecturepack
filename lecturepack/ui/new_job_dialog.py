"""
lecturepack.ui.new_job_dialog
==============================

"New job" onboarding modal (v1.2): drag-drop / browse a lecture video,
confirm the detected file, pick an output mode, then hand off to Process.

Two internal states, matching the design mockup:
    drop      -- dashed dropzone + "Browse for video" (no file chosen yet)
    detected  -- real ffprobe-inspected file summary + output mode picker

Mirrors ``lecturepack.ui.context_repair_dialog``'s pattern of a thin QDialog
host; all real work (job creation, whisper/crop settings) still happens on
the Process page after this dialog is accepted -- this only resolves the
video path and the product mode.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from lecturepack.constants import (
    PRODUCT_MODE_LABELS, PRODUCT_MODE_STUDY_PACK, PRODUCT_MODES,
    SUPPORTED_VIDEO_EXTENSIONS,
)
from lecturepack.ui import theme


def _human_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class NewJobDialog(QDialog):
    def __init__(self, ffmpeg_wrapper, initial_path=None, parent=None):
        super().__init__(parent)
        self.ffmpeg_wrapper = ffmpeg_wrapper
        self.selected_path = None
        self.selected_mode = PRODUCT_MODE_STUDY_PACK
        self._mode_buttons = {}

        self.setWindowTitle("New job")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setAcceptDrops(True)

        self._build_ui()
        if initial_path:
            self._set_video(initial_path)

    # ------------------------------------------------------------------ #
    # UI                                                                  #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setProperty("card", True)
        header.setStyleSheet(
            f"border: none; border-bottom: 2px solid {theme.c('line')}; border-radius: 0;")
        h_l = QHBoxLayout(header)
        h_l.setContentsMargins(20, 15, 15, 15)
        mark = QFrame()
        mark.setFixedSize(26, 26)
        mark.setStyleSheet(f"background: {theme.c('primary')}; border-radius: 8px;")
        h_l.addWidget(mark)
        title = QLabel("New job")
        title.setStyleSheet("font-weight: 700; font-size: 15px; border: none; margin-left: 9px;")
        h_l.addWidget(title)
        h_l.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setProperty("softPanel", True)
        close_btn.clicked.connect(self.reject)
        h_l.addWidget(close_btn)
        outer.addWidget(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_drop_page())
        self.stack.addWidget(self._build_detected_page())
        outer.addWidget(self.stack)

    def _build_drop_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        zone = QFrame()
        zone.setObjectName("DropzoneHero")
        zone.setMinimumHeight(190)
        z_l = QVBoxLayout(zone)
        z_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        z_l.setSpacing(6)
        icon = QLabel("↑")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(48, 48)
        icon.setProperty("previewPane", True)
        icon.setStyleSheet(
            icon.styleSheet() +
            f"font-size: 22px; font-weight: 700; color: {theme.c('primary_ink')}; "
            f"border-radius: 14px; border: 2px solid {theme.c('primary')};")
        z_l.addWidget(icon)
        headline = QLabel("Drop a lecture video here")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setStyleSheet("font-weight: 700; font-size: 17px; border: none;")
        z_l.addWidget(headline)
        exts = QLabel(" · ".join(SUPPORTED_VIDEO_EXTENSIONS))
        exts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exts.setProperty("muted", True)
        exts.setStyleSheet("font: 500 12px monospace; border: none;")
        z_l.addWidget(exts)
        layout.addWidget(zone, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("softPanel", True)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        browse_btn = QPushButton("Browse for video")
        browse_btn.setProperty("primary", True)
        browse_btn.clicked.connect(self._browse)
        btn_row.addWidget(browse_btn)
        layout.addLayout(btn_row)
        return page

    def _build_detected_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        summary = QFrame()
        summary.setProperty("card", True)
        s_l = QHBoxLayout(summary)
        s_l.setContentsMargins(14, 14, 14, 14)
        s_l.setSpacing(14)
        thumb = QLabel("▦")
        thumb.setFixedSize(80, 50)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setProperty("previewPane", True)
        thumb.setStyleSheet(thumb.styleSheet() + f"border-radius: 8px; color: {theme.c('muted')}; font-size: 20px;")
        s_l.addWidget(thumb)
        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        self._name_lbl = QLabel()
        self._name_lbl.setStyleSheet("font-weight: 700; font-size: 15px; border: none;")
        info_col.addWidget(self._name_lbl)
        self._meta_lbl = QLabel()
        self._meta_lbl.setProperty("muted", True)
        self._meta_lbl.setStyleSheet("font: 500 11px monospace; border: none;")
        info_col.addWidget(self._meta_lbl)
        s_l.addLayout(info_col, 1)
        self._ready_pill = QLabel("Ready")
        self._ready_pill.setStyleSheet(
            f"font: 600 10px monospace; text-transform: uppercase; "
            f"color: {theme.c('green')}; background: {theme.c('green_soft')}; "
            f"border-radius: 6px; padding: 3px 8px; border: none;")
        s_l.addWidget(self._ready_pill)
        layout.addWidget(summary)

        mode_label = QLabel("OUTPUT MODE")
        mode_label.setProperty("muted", True)
        mode_label.setStyleSheet(
            "font: 500 10px monospace; letter-spacing: 0.12em; border: none;")
        layout.addWidget(mode_label)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        for mode in PRODUCT_MODES:
            btn = QPushButton(PRODUCT_MODE_LABELS[mode].split(" (")[0])
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, m=mode: self._pick_mode(m))
            mode_row.addWidget(btn, 1)
            self._mode_buttons[mode] = btn
        layout.addLayout(mode_row)
        self._pick_mode(PRODUCT_MODE_STUDY_PACK)

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("softPanel", True)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        start_btn = QPushButton("Start processing")
        start_btn.setProperty("primary", True)
        start_btn.clicked.connect(self._start)
        btn_row.addWidget(start_btn)
        layout.addLayout(btn_row)
        return page

    # ------------------------------------------------------------------ #
    # behaviour                                                          #
    # ------------------------------------------------------------------ #
    def _pick_mode(self, mode):
        self.selected_mode = mode
        for m, btn in self._mode_buttons.items():
            checked = m == mode
            btn.setChecked(checked)
            btn.setProperty("primary", checked)
            btn.setProperty("softPanel", not checked)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _browse(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Lecture Video", "",
            f"Video Files (*{' *'.join(SUPPORTED_VIDEO_EXTENSIONS)})")
        if file_path:
            self._set_video(file_path)

    def _set_video(self, path):
        if not path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS):
            return
        self.selected_path = path
        meta = {}
        try:
            self.ffmpeg_wrapper.detect_binaries()
            meta = self.ffmpeg_wrapper.inspect_video(path) or {}
        except Exception:
            meta = {}
        self._populate_detected(path, meta)
        self.stack.setCurrentIndex(1)

    def _populate_detected(self, path, meta):
        self._name_lbl.setText(os.path.basename(path))
        parts = []
        w, h = meta.get("width"), meta.get("height")
        if w and h:
            parts.append(f"{w}×{h}")
        dur = meta.get("duration")
        if dur:
            minutes, seconds = divmod(int(dur), 60)
            parts.append(f"{minutes}:{seconds:02d}")
        codec = meta.get("video_codec")
        if codec:
            parts.append(str(codec))
        try:
            parts.append(_human_size(os.path.getsize(path)))
        except OSError:
            pass
        self._meta_lbl.setText(" · ".join(parts) if parts else "Metadata unavailable")

    def _start(self):
        if self.selected_path:
            self.accept()

    # ------------------------------------------------------------------ #
    # drag & drop                                                        #
    # ------------------------------------------------------------------ #
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self._set_video(urls[0].toLocalFile())
