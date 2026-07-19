"""
lecturepack.ui.pages.home_page
==============================

Home / Jobs page (v1.1, Phase 1): job list with status chips, new-job entry,
archive / restore / export-archive actions.  Studio visual layout.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from lecturepack.constants import SUPPORTED_VIDEO_EXTENSIONS, STAGES, STAGE_REVIEW_READY
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.ui import theme


class _JobCard(QFrame):
    """A single job card in the Studio home grid."""

    def __init__(self, job_id, title, source, status, created, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.source = source
        self.setProperty("card", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(210)
        self._build(title, status, created)
        theme.add_card_shadow(self)

    def _build(self, title, status, created):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        thumb = QFrame()
        thumb.setStyleSheet(
            f"background: {theme.c('sunk')}; border-bottom: 1.5px solid {theme.c('line')};")
        thumb.setFixedHeight(118)
        thumb_l = QHBoxLayout(thumb)
        thumb_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl = QLabel("\u25A6")
        icon_lbl.setStyleSheet(f"font-size: 30px; color: {theme.c('muted')}; border: none;")
        thumb_l.addWidget(icon_lbl)

        is_done = status in ("completed", "review_ready")
        is_running = status == "running"
        badge_frame = QFrame(thumb)
        badge_frame.setFixedSize(90, 22)
        badge_frame.setStyleSheet(
            f"position: absolute; top: 9px; right: 9px;")
        if is_done:
            badge_bg = "#D3F0DF"
            badge_color = "#128A52"
            dot_bg = "#128A52"
            badge_text = "Done"
        elif status == "failed":
            badge_bg = "#FADAD5"
            badge_color = "#D63A2C"
            dot_bg = "#D63A2C"
            badge_text = "Failed"
        elif is_running:
            badge_bg = "#FBE2D5"
            badge_color = "#B73A0B"
            dot_bg = "#F15A24"
            badge_text = "Running"
        else:
            badge_bg = "#F9F5ED"
            badge_color = "#81786B"
            dot_bg = "#81786B"
            badge_text = "Pending"
        badge_layout = QHBoxLayout(badge_frame)
        badge_layout.setContentsMargins(8, 0, 8, 0)
        badge_layout.setSpacing(5)
        dot = QLabel("\u25CF")
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(f"background: {dot_bg}; border-radius: 3px; font-size: 0;")
        badge_lbl = QLabel(badge_text)
        badge_lbl.setStyleSheet(
            f"font: 600 10px monospace; text-transform: uppercase; "
            f"color: {badge_color}; background: {badge_bg}; border-radius: 6px; "
            f"padding: 3px 8px; border: none;")
        badge_layout.addWidget(dot)
        badge_layout.addWidget(badge_lbl)
        badge_frame.move(thumb.width() - 100, 9)

        layout.addWidget(thumb)

        info = QWidget()
        info_l = QVBoxLayout(info)
        info_l.setContentsMargins(16, 14, 16, 16)
        info_l.setSpacing(5)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-weight: 700; font-size: 16px; color: {theme.c('ink')}; border: none;")
        info_l.addWidget(title_lbl)

        source_name = os.path.basename(self.source) if self.source else ""
        meta_lbl = QLabel(f"{source_name}\n{created}")
        meta_lbl.setStyleSheet(
            f"font: 500 11px monospace; color: {theme.c('muted')}; line-height: 1.7; border: none;")
        info_l.addWidget(meta_lbl)
        layout.addWidget(info, 1)


class HomePage(QWidget):
    video_chosen = Signal(str)
    job_selected = Signal(str, str)      # job_id, source_path
    archive_requested = Signal()
    restore_requested = Signal()
    export_archive_requested = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(44, 36, 44, 52)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        wrapper = QWidget()
        wrapper.setMaximumWidth(1140)
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        eyebrow = QLabel("Local \u00b7 Private \u00b7 No account")
        eyebrow.setStyleSheet(
            f"font: 500 11px monospace; letter-spacing: 0.16em; "
            f"text-transform: uppercase; color: {theme.c('secondary')};")
        wl.addWidget(eyebrow)

        headline = QLabel("Turn lecture recordings into study packs.")
        headline.setWordWrap(True)
        headline.setMaximumWidth(680)
        headline.setStyleSheet(
            f"font-size: 40px; font-weight: 700; letter-spacing: -0.025em; "
            f"line-height: 1.08; margin-top: 12px; margin-bottom: 12px; color: {theme.c('ink')};")
        wl.addWidget(headline)

        subtitle = QLabel(
            "Slides, transcripts and a study workspace \u2014 captured and "
            "exported beautifully, entirely on your machine.")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(540)
        subtitle.setStyleSheet(
            f"font-size: 16px; color: {theme.c('muted')}; "
            f"line-height: 1.55; margin-bottom: 30px;")
        wl.addWidget(subtitle)

        drop_card = QFrame()
        drop_card.setProperty("card", True)
        drop_card.setStyleSheet(drop_card.styleSheet() + "border-radius: 16px;")
        dc_l = QHBoxLayout(drop_card)
        dc_l.setContentsMargins(26, 24, 26, 24)
        dc_l.setSpacing(22)
        accent_bar = QFrame()
        accent_bar.setFixedWidth(5)
        accent_bar.setStyleSheet(
            f"background: {theme.c('primary')}; border-radius: 3px;")
        dc_l.addWidget(accent_bar)
        icon_box = QFrame()
        icon_box.setFixedSize(52, 52)
        icon_box.setStyleSheet(
            f"background: {theme.c('secondary_soft')}; border-radius: 13px;")
        icon_l = QHBoxLayout(icon_box)
        icon_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_sym = QLabel("\u2193")
        icon_sym.setStyleSheet(
            f"font-size: 24px; color: {theme.c('secondary_ink')}; border: none;")
        icon_l.addWidget(icon_sym)
        dc_l.addWidget(icon_box)
        drop_info = QVBoxLayout()
        drop_info.setSpacing(3)
        drop_title = QLabel("Drop a lecture video anywhere")
        drop_title.setStyleSheet(f"font-weight: 700; font-size: 18px; color: {theme.c('ink')}; border: none;")
        drop_info.addWidget(drop_title)
        drop_sub = QLabel(".mp4 \u00b7 .mkv \u00b7 .mov \u00b7 .m4v \u00b7 .webm \u2014 any length")
        drop_sub.setStyleSheet(
            f"font: 500 12px monospace; color: {theme.c('muted')}; border: none;")
        drop_info.addWidget(drop_sub)
        dc_l.addLayout(drop_info, 1)
        browse_btn = QPushButton("Browse for video")
        browse_btn.setStyleSheet(
            f"font: 600 15px sans-serif; background: {theme.c('primary')}; "
            f"color: #fff; border: 1.5px solid {theme.c('primary_hover')}; "
            f"border-radius: 11px; padding: 12px 22px;")
        browse_btn.clicked.connect(self._browse_video)
        dc_l.addWidget(browse_btn)
        theme.add_card_shadow(drop_card)
        wl.addWidget(drop_card)

        wl.addSpacing(40)

        jobs_header = QHBoxLayout()
        jobs_header.setSpacing(11)
        recent_lbl = QLabel("RECENT JOBS")
        recent_lbl.setStyleSheet(
            f"font: 500 12px monospace; letter-spacing: 0.14em; "
            f"text-transform: uppercase; border: none; color: {theme.c('ink')};")
        self._jobs_count_lbl = QLabel("0")
        self._jobs_count_lbl.setStyleSheet(
            f"font: 500 12px monospace; color: {theme.c('muted')}; border: none;")
        jobs_header.addWidget(recent_lbl)
        jobs_header.addWidget(self._jobs_count_lbl)
        jobs_header.addStretch(1)
        self.archive_btn = QPushButton("Archive")
        self.archive_btn.setStyleSheet(
            "font: 500 12px monospace; padding: 7px 12px; border-radius: 8px;")
        self.archive_btn.clicked.connect(self.archive_requested.emit)
        self.restore_btn = QPushButton("Restore")
        self.restore_btn.setStyleSheet(
            "font: 500 12px monospace; padding: 7px 12px; border-radius: 8px;")
        self.restore_btn.clicked.connect(self.restore_requested.emit)
        self.export_archive_btn = QPushButton("Export archive\u2026")
        self.export_archive_btn.setStyleSheet(
            "font: 500 12px monospace; padding: 7px 12px; border-radius: 8px;")
        self.export_archive_btn.clicked.connect(self.export_archive_requested.emit)
        jobs_header.addWidget(self.archive_btn)
        jobs_header.addWidget(self.restore_btn)
        wl.addLayout(jobs_header)

        wl.addSpacing(16)

        self._jobs_grid = QGridLayout()
        self._jobs_grid.setSpacing(18)
        self._jobs_grid_row = 0
        self._jobs_grid_col = 0
        self._job_cards = []
        wl.addLayout(self._jobs_grid, 1)

        self._empty_state = QLabel(
            "No jobs yet. Drop a lecture video above or browse to get started.")
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state.setWordWrap(True)
        self._empty_state.setStyleSheet(
            f"color: {theme.c('muted')}; font-size: 15px; padding: 40px 20px;")
        self._empty_state.setVisible(False)
        wl.addWidget(self._empty_state)

        wl.addStretch(1)

        layout.addWidget(wrapper)
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Lecture Video", "",
            f"Video Files (*{' *'.join(SUPPORTED_VIDEO_EXTENSIONS)})")
        if file_path:
            self.video_chosen.emit(file_path)

    def refresh_jobs(self):
        for card in self._job_cards:
            card.setParent(None)
            card.deleteLater()
        self._job_cards.clear()
        self._jobs_grid_row = 0
        self._jobs_grid_col = 0

        jobs_dir = os.path.join(self.config_manager.data_dir, "jobs")
        if not os.path.exists(jobs_dir):
            self._jobs_count_lbl.setText("0")
            self._empty_state.setVisible(True)
            return
        entries = []
        for job_id in os.listdir(jobs_dir):
            manifest_p = os.path.join(jobs_dir, job_id, "manifest.json")
            if not os.path.exists(manifest_p):
                continue
            man = FileManager.read_json_safe(manifest_p)
            if not isinstance(man, dict):
                continue
            state = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "state.json"), {}) or {}
            entries.append((man.get("created_at", ""), job_id, man, state))
        entries.sort(reverse=True)
        self._jobs_count_lbl.setText(str(len(entries)))
        self._empty_state.setVisible(len(entries) == 0)
        for created, job_id, man, state in entries:
            title = man.get("title", job_id)
            status = state.get("overall_status", "pending")
            source = man.get("source", {}).get("original_path", "")
            review_done = state.get("stages", {}).get(
                STAGE_REVIEW_READY, {}).get("status") == "completed"
            if review_done and status != "completed":
                status = "review_ready"
            created_short = created[:10] if created else ""
            card = _JobCard(job_id, title, source, status, created_short)
            card.mousePressEvent = lambda e, jid=job_id, sp=source: self.job_selected.emit(jid, sp)
            self._jobs_grid.addWidget(card, self._jobs_grid_row, self._jobs_grid_col)
            self._job_cards.append(card)
            self._jobs_grid_col += 1
            if self._jobs_grid_col >= 3:
                self._jobs_grid_col = 0
                self._jobs_grid_row += 1

    def _on_job_activated(self, item):
        pass
