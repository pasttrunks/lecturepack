"""
lecturepack.ui.pages.home_page
==============================

Home / Jobs page (v1.1, Phase 1): job list with status chips, new-job entry,
archive / restore / export-archive actions.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget, QDialog,
)

from lecturepack.constants import SUPPORTED_VIDEO_EXTENSIONS, STAGES, STAGE_REVIEW_READY
from lecturepack.infrastructure.file_manager import FileManager


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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        title = QLabel("LecturePack")
        title.setProperty("h1", True)
        layout.addWidget(title)
        sub = QLabel("Turn lecture recordings into slides, transcripts and study packs — all on this PC.")
        sub.setProperty("muted", True)
        layout.addWidget(sub)

        drop_card = QFrame()
        drop_card.setProperty("card", True)
        dc = QHBoxLayout(drop_card)
        dc.setContentsMargins(16, 14, 16, 14)
        drop_lbl = QLabel("Drop a lecture video anywhere in this window, or")
        browse_btn = QPushButton("Browse for video…")
        browse_btn.setProperty("primary", True)
        browse_btn.clicked.connect(self._browse_video)
        dc.addWidget(drop_lbl)
        dc.addWidget(browse_btn)
        dc.addStretch(1)
        layout.addWidget(drop_card)

        hdr = QHBoxLayout()
        jobs_lbl = QLabel("Jobs")
        jobs_lbl.setProperty("h2", True)
        hdr.addWidget(jobs_lbl)
        hdr.addStretch(1)
        self.archive_btn = QPushButton("Archive job")
        self.archive_btn.clicked.connect(self.archive_requested.emit)
        self.restore_btn = QPushButton("Restore…")
        self.restore_btn.clicked.connect(self.restore_requested.emit)
        self.export_archive_btn = QPushButton("Export archive…")
        self.export_archive_btn.clicked.connect(self.export_archive_requested.emit)
        hdr.addWidget(self.archive_btn)
        hdr.addWidget(self.restore_btn)
        hdr.addWidget(self.export_archive_btn)
        layout.addLayout(hdr)

        self.jobs_list = QListWidget()
        self.jobs_list.setAlternatingRowColors(True)
        self.jobs_list.itemActivated.connect(self._on_job_activated)
        self.jobs_list.itemClicked.connect(self._on_job_activated)
        layout.addWidget(self.jobs_list, 1)

    def _browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Lecture Video", "",
            f"Video Files (*{' *'.join(SUPPORTED_VIDEO_EXTENSIONS)})")
        if file_path:
            self.video_chosen.emit(file_path)

    def refresh_jobs(self):
        self.jobs_list.clear()
        jobs_dir = os.path.join(self.config_manager.data_dir, "jobs")
        if not os.path.exists(jobs_dir):
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
        for created, job_id, man, state in entries:
            title = man.get("title", job_id)
            status = state.get("overall_status", "pending")
            source = man.get("source", {}).get("original_path", "")
            review_done = state.get("stages", {}).get(STAGE_REVIEW_READY, {}).get("status") == "completed"
            chip = {"completed": "✓ complete", "failed": "✕ failed",
                    "running": "… running"}.get(status, "· pending")
            if review_done and status != "completed":
                chip = "✓ review ready"
            item = QListWidgetItem(f"{title}\n    {chip}   ·   {created[:16]}   ·   {os.path.basename(source)}")
            item.setData(Qt.ItemDataRole.UserRole, (job_id, source))
            self.jobs_list.addItem(item)

    def _on_job_activated(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.job_selected.emit(data[0], data[1])
