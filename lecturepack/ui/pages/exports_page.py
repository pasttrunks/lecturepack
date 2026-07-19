"""
lecturepack.ui.pages.exports_page
=================================

Exports page (v1.1, Phase 1): format selection, export trigger, and a live
list of produced artifacts with sizes. Exports never rerun upstream stages.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class ExportsPage(QWidget):
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.job = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        title = QLabel("Exports")
        title.setProperty("h1", True)
        layout.addWidget(title)

        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        cl.addWidget(QLabel("Formats (product mode may skip some):"))
        formats_layout = QHBoxLayout()
        self.chk_slides_pdf = QCheckBox("Slides PDF")
        self.chk_slides_pdf.setChecked(True)
        self.chk_html_pack = QCheckBox("HTML Study Pack")
        self.chk_html_pack.setChecked(True)
        self.chk_srt = QCheckBox("SRT Subtitles")
        self.chk_srt.setChecked(True)
        self.chk_txt = QCheckBox("Plain Text")
        self.chk_txt.setChecked(True)
        self.chk_json = QCheckBox("Structured JSON")
        self.chk_json.setChecked(True)
        for c in (self.chk_slides_pdf, self.chk_html_pack, self.chk_srt,
                  self.chk_txt, self.chk_json):
            formats_layout.addWidget(c)
        formats_layout.addStretch(1)
        cl.addLayout(formats_layout)

        actions = QHBoxLayout()
        self.export_btn = QPushButton("Export accepted")
        self.export_btn.setProperty("primary", True)
        self.export_btn.clicked.connect(self.export_requested.emit)
        self.open_folder_btn = QPushButton("Open output folder")
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        actions.addWidget(self.export_btn)
        actions.addWidget(self.open_folder_btn)
        actions.addStretch(1)
        cl.addLayout(actions)
        layout.addWidget(card)

        lbl = QLabel("Artifacts")
        lbl.setProperty("h2", True)
        layout.addWidget(lbl)
        self.artifacts_table = QTableWidget()
        self.artifacts_table.setColumnCount(3)
        self.artifacts_table.setHorizontalHeaderLabels(["File", "Size", "Modified"])
        self.artifacts_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.artifacts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.artifacts_table, 1)

    def set_job(self, job):
        self.job = job
        self.refresh_artifacts()

    def refresh_artifacts(self):
        self.artifacts_table.setRowCount(0)
        if self.job is None:
            return
        exports_dir = self.job.paths["exports"]
        if not os.path.isdir(exports_dir):
            return
        import datetime
        rows = sorted(os.listdir(exports_dir))
        self.artifacts_table.setRowCount(len(rows))
        for r, name in enumerate(rows):
            p = os.path.join(exports_dir, name)
            try:
                st = os.stat(p)
                size = st.st_size
                if size > 1024 * 1024:
                    size_s = f"{size / (1024 * 1024):.1f} MB"
                elif size > 1024:
                    size_s = f"{size / 1024:.0f} KB"
                else:
                    size_s = f"{size} B"
                mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size_s, mtime = "?", "?"
            self.artifacts_table.setItem(r, 0, QTableWidgetItem(name))
            self.artifacts_table.setItem(r, 1, QTableWidgetItem(size_s))
            self.artifacts_table.setItem(r, 2, QTableWidgetItem(mtime))

    def _open_output_folder(self):
        if self.job is not None:
            exports_dir = self.job.paths["exports"]
            os.makedirs(exports_dir, exist_ok=True)
            os.startfile(exports_dir)
