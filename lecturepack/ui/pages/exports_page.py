"""
lecturepack.ui.pages.exports_page
=================================

Exports page (v1.1, Phase 1): format selection, export trigger, and a live
list of produced artifacts with sizes. Exports never rerun upstream stages.
Studio visual layout.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from lecturepack.ui import theme


class ExportsPage(QWidget):
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.job = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(44, 34, 44, 52)
        layout.setAlignment(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignmentFlag.AlignHCenter)

        wrapper = QWidget()
        wrapper.setMaximumWidth(960)
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        title = QLabel("Export study pack")
        title.setStyleSheet("font-size: 30px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 6px;")
        wl.addWidget(title)

        path_pill = QLabel(
            f"Generated locally into <span style='font: 500 13px monospace; "
            f"background: {theme.c('sunk')}; border: 1px solid {theme.c('line')}; "
            f"border-radius: 5px; padding: 1px 6px;'>~/LecturePackData/\u2026/exports</span>")
        path_pill.setTextFormat(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.TextFormat.RichText)
        path_pill.setStyleSheet(f"font-size: 15px; color: {theme.c('muted')}; margin-bottom: 28px;")
        wl.addWidget(path_pill)

        cards_grid = QHBoxLayout()
        cards_grid.setSpacing(18)

        pdf_card = QFrame()
        pdf_card.setProperty("card", True)
        theme.add_card_shadow(pdf_card)
        pc = QHBoxLayout(pdf_card)
        pc.setContentsMargins(20, 20, 20, 20)
        pc.setSpacing(15)
        pdf_icon = QFrame()
        pdf_icon.setFixedSize(46, 46)
        pdf_icon.setStyleSheet(f"background: {theme.c('primary_soft')}; border-radius: 11px;")
        pc.addWidget(pdf_icon)
        pdf_info = QVBoxLayout()
        pdf_title = QLabel("Slides PDF")
        pdf_title.setStyleSheet("font-weight: 700; font-size: 16px; border: none;")
        pdf_info.addWidget(pdf_title)
        pdf_desc = QLabel("14 accepted slides, one per page, full resolution.")
        pdf_desc.setWordWrap(True)
        pdf_desc.setStyleSheet(f"font-size: 13px; color: {theme.c('muted')}; line-height: 1.5; border: none;")
        pdf_info.addWidget(pdf_desc)
        pdf_info.addStretch(1)
        pc.addLayout(pdf_info, 1)
        cards_grid.addWidget(pdf_card)

        html_card = QFrame()
        html_card.setProperty("card", True)
        theme.add_card_shadow(html_card)
        hc = QHBoxLayout(html_card)
        hc.setContentsMargins(20, 20, 20, 20)
        hc.setSpacing(15)
        html_icon = QFrame()
        html_icon.setFixedSize(46, 46)
        html_icon.setStyleSheet(f"background: {theme.c('secondary_soft')}; border-radius: 11px;")
        hc.addWidget(html_icon)
        html_info = QVBoxLayout()
        html_title = QLabel("HTML study pack")
        html_title.setStyleSheet("font-weight: 700; font-size: 16px; border: none;")
        html_info.addWidget(html_title)
        html_desc = QLabel("Interactive slides + synced transcript in one file.")
        html_desc.setWordWrap(True)
        html_desc.setStyleSheet(f"font-size: 13px; color: {theme.c('muted')}; line-height: 1.5; border: none;")
        html_info.addWidget(html_desc)
        html_info.addStretch(1)
        hc.addLayout(html_info, 1)
        cards_grid.addWidget(html_card)

        wl.addLayout(cards_grid)
        wl.addSpacing(26)

        formats_card = QFrame()
        formats_card.setProperty("card", True)
        theme.add_card_shadow(formats_card)
        fc_l = QVBoxLayout(formats_card)
        fc_l.setContentsMargins(20, 20, 22, 20)
        fc_header = QHBoxLayout()
        fc_title = QLabel("Transcript formats")
        fc_title.setStyleSheet("font-weight: 700; font-size: 16px; border: none;")
        fc_header.addWidget(fc_title)
        fc_header.addStretch(1)
        fc_hint = QLabel("select to include")
        fc_hint.setStyleSheet(f"font: 500 11px monospace; color: {theme.c('muted')}; border: none;")
        fc_header.addWidget(fc_hint)
        fc_l.addLayout(fc_header)
        fc_l.addSpacing(15)

        formats_grid = QGridLayout()
        formats_grid.setSpacing(10)
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
        self.chk_vtt = QCheckBox("VTT")
        self.chk_csv = QCheckBox("CSV")
        self.chk_docx = QCheckBox("DOCX")
        self.chk_tsv = QCheckBox("TSV")
        all_chks = [
            (self.chk_slides_pdf, 0, 0), (self.chk_html_pack, 0, 1),
            (self.chk_srt, 0, 2), (self.chk_txt, 0, 3),
            (self.chk_json, 1, 0), (self.chk_vtt, 1, 1),
            (self.chk_csv, 1, 2), (self.chk_docx, 1, 3),
            (self.chk_tsv, 1, 4),
        ]
        for chk, r, c in all_chks:
            formats_grid.addWidget(chk, r, c)
        fc_l.addLayout(formats_grid)
        wl.addWidget(formats_card)
        wl.addSpacing(26)

        cta_card = QFrame()
        cta_card.setStyleSheet(
            f"background: {theme.c('panel2')}; border: 1.5px solid {theme.c('line')}; "
            f"border-radius: 13px;")
        theme.add_card_shadow(cta_card)
        cta_l = QHBoxLayout(cta_card)
        cta_l.setContentsMargins(22, 18, 22, 18)
        cta_text = QVBoxLayout()
        cta_title = QLabel("Export everything")
        cta_title.setStyleSheet(f"font-weight: 700; font-size: 16px; color: {theme.c('ink')}; border: none;")
        cta_text.addWidget(cta_title)
        cta_sub = QLabel("PDF + HTML + transcript formats")
        cta_sub.setStyleSheet(f"font: 500 12px monospace; color: {theme.c('muted')}; border: none;")
        cta_text.addWidget(cta_sub)
        cta_l.addLayout(cta_text, 1)
        self.export_btn = QPushButton("Export all")
        self.export_btn.setStyleSheet(
            f"font: 700 15px sans-serif; background: {theme.c('primary')}; color: #fff; "
            f"border: 1.5px solid {theme.c('primary_hover')}; border-radius: 10px; "
            f"padding: 12px 24px;")
        self.export_btn.clicked.connect(self.export_requested.emit)
        cta_l.addWidget(self.export_btn)
        wl.addWidget(cta_card)
        wl.addSpacing(30)

        artifacts_title = QLabel("Artifacts")
        artifacts_title.setStyleSheet("font-weight: 700; font-size: 18px; margin-bottom: 10px;")
        wl.addWidget(artifacts_title)

        self.artifacts_table = QTableWidget()
        self.artifacts_table.setColumnCount(3)
        self.artifacts_table.setHorizontalHeaderLabels(["File", "Size", "Modified"])
        self.artifacts_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.artifacts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        wl.addWidget(self.artifacts_table, 1)

        layout.addWidget(wrapper)
        scroll.setWidget(container)
        outer.addWidget(scroll)

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
