"""
lecturepack.ui.pages.process_page
=================================

Job setup + live processing view (v1.1, Phases 1+9).

Left column: categorized, collapsible settings (video, output, transcription,
slide detection with crop editor, context). Right column: stage-by-stage
progress with elapsed time and estimated remaining, a live log drawer, and a
Cancel button. No modal frozen periods: everything updates from controller
signals.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QElapsedTimer, QTimer, Signal, QRectF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QRadioButton, QButtonGroup, QScrollArea, QSpinBox, QSplitter, QTextEdit,
    QToolButton, QVBoxLayout, QWidget,
)

from lecturepack.constants import (
    STAGES, STAGE_EXPORT, SUPPORTED_VIDEO_EXTENSIONS,
    PRODUCT_MODES, PRODUCT_MODE_LABELS,
)
from lecturepack.infrastructure.transcription_engines import (
    ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN, ENGINE_LABELS,
)


class CollapsibleGroup(QFrame):
    """A titled, collapsible settings card (VideoTranscriber-inspired)."""

    def __init__(self, title, parent=None, collapsed=False):
        super().__init__(parent)
        self.setProperty("card", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 8)
        self.toggle = QToolButton()
        self.toggle.setText(("▸ " if collapsed else "▾ ") + title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(not collapsed)
        self.toggle.setStyleSheet("QToolButton{border:none;font-weight:600;font-size:13px;}")
        self.toggle.clicked.connect(self._on_toggle)
        self._title = title
        outer.addWidget(self.toggle)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(2, 4, 2, 2)
        self.body.setVisible(not collapsed)
        outer.addWidget(self.body)

    def _on_toggle(self):
        open_ = self.toggle.isChecked()
        self.body.setVisible(open_)
        self.toggle.setText(("▾ " if open_ else "▸ ") + self._title)


class StageRow(QWidget):
    def __init__(self, stage, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        self.icon = QLabel("○")
        self.icon.setFixedWidth(18)
        self.name = QLabel(stage)
        self.name.setMinimumWidth(110)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setMaximumHeight(12)
        self.bar.setTextVisible(False)
        self.elapsed = QLabel("")
        self.elapsed.setProperty("muted", True)
        self.elapsed.setMinimumWidth(150)
        row.addWidget(self.icon)
        row.addWidget(self.name)
        row.addWidget(self.bar, 1)
        row.addWidget(self.elapsed)
        self.timer = QElapsedTimer()
        self.state = "pending"
        self.final_seconds = None

    def set_state(self, state):
        self.state = state
        icons = {"pending": ("○", ""), "running": ("◔", "color:#2563eb;font-weight:bold;"),
                 "completed": ("●", "color:#16a34a;font-weight:bold;"),
                 "failed": ("✕", "color:#dc2626;font-weight:bold;"),
                 "cached": ("◍", "color:#16a34a;"),
                 "skipped": ("–", "color:#8b93a1;"),
                 "cancelled": ("◌", "color:#d97706;")}
        icon, style = icons.get(state, ("○", ""))
        self.icon.setText(icon)
        self.icon.setStyleSheet(style)
        self.name.setStyleSheet(style)
        if state == "running":
            self.timer.restart()
        elif state in ("completed", "failed", "cancelled") and self.timer.isValid():
            self.final_seconds = self.timer.elapsed() / 1000.0
            self.elapsed.setText(f"{self.final_seconds:.1f}s")
            if state == "completed":
                self.bar.setValue(100)
        elif state in ("cached", "skipped"):
            self.elapsed.setText(state)
            self.bar.setValue(100)

    def tick(self):
        if self.state == "running" and self.timer.isValid():
            secs = self.timer.elapsed() / 1000.0
            pct = self.bar.value()
            eta = ""
            if 3 < pct < 100:
                remaining = secs * (100 - pct) / pct
                eta = f" · ~{remaining:.0f}s left"
            self.elapsed.setText(f"{secs:.0f}s{eta}")


class ProcessPage(QWidget):
    start_requested = Signal()
    retranscribe_requested = Signal()
    cancel_requested = Signal()
    preview_detection_requested = Signal()
    video_chosen = Signal(str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._build_ui()
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)

        # ---- left: settings --------------------------------------------- #
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)

        # Video
        vid_grp = CollapsibleGroup("Lecture video")
        path_layout = QHBoxLayout()
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Drop a video anywhere or browse…")
        browse_video_btn = QPushButton("Browse")
        browse_video_btn.clicked.connect(self._browse_video)
        path_layout.addWidget(self.video_path_edit)
        path_layout.addWidget(browse_video_btn)
        vid_grp.body_layout.addLayout(path_layout)
        self.metadata_lbl = QLabel("No video loaded.")
        self.metadata_lbl.setProperty("muted", True)
        vid_grp.body_layout.addWidget(self.metadata_lbl)
        ll.addWidget(vid_grp)

        # Output / product mode
        mode_grp = CollapsibleGroup("Output")
        self.product_mode_combo = QComboBox()
        for m in PRODUCT_MODES:
            self.product_mode_combo.addItem(PRODUCT_MODE_LABELS[m], m)
        mode_grp.body_layout.addWidget(self.product_mode_combo)
        ll.addWidget(mode_grp)

        # Transcription
        tr_grp = CollapsibleGroup("Transcription")
        grid = QGridLayout()
        grid.addWidget(QLabel("Profile:"), 0, 0)
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["Fast", "Balanced", "Accurate", "Custom"])
        grid.addWidget(self.profile_combo, 0, 1)
        grid.addWidget(QLabel("Engine:"), 1, 0)
        self.engine_combo = QComboBox()
        for key in (ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN):
            self.engine_combo.addItem(ENGINE_LABELS[key], key)
        grid.addWidget(self.engine_combo, 1, 1)
        grid.addWidget(QLabel("Threads:"), 2, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(8)
        grid.addWidget(self.threads_spin, 2, 1)
        tr_grp.body_layout.addLayout(grid)
        self.engine_status_lbl = QLabel("")
        self.engine_status_lbl.setProperty("muted", True)
        self.engine_status_lbl.setWordWrap(True)
        tr_grp.body_layout.addWidget(self.engine_status_lbl)

        self.vad_chk = QCheckBox("Voice Activity Detection (VAD)")
        tr_grp.body_layout.addWidget(self.vad_chk)
        vad_row = QHBoxLayout()
        self.vad_model_edit = QLineEdit()
        self.vad_model_edit.setPlaceholderText("VAD model (.bin)…")
        vad_browse = QPushButton("…")
        vad_browse.setFixedWidth(28)
        vad_browse.clicked.connect(self._browse_vad_model)
        vad_row.addWidget(self.vad_model_edit)
        vad_row.addWidget(vad_browse)
        tr_grp.body_layout.addLayout(vad_row)
        vgrid = QGridLayout()
        vgrid.addWidget(QLabel("Threshold:"), 0, 0)
        self.vad_thresh_spin = QDoubleSpinBox()
        self.vad_thresh_spin.setRange(0.01, 1.0)
        self.vad_thresh_spin.setSingleStep(0.05)
        self.vad_thresh_spin.setValue(0.50)
        vgrid.addWidget(self.vad_thresh_spin, 0, 1)
        vgrid.addWidget(QLabel("Min speech (ms):"), 1, 0)
        self.vad_spd_spin = QSpinBox()
        self.vad_spd_spin.setRange(10, 5000)
        self.vad_spd_spin.setSingleStep(50)
        self.vad_spd_spin.setValue(250)
        vgrid.addWidget(self.vad_spd_spin, 1, 1)
        vgrid.addWidget(QLabel("Min silence (ms):"), 2, 0)
        self.vad_sil_spin = QSpinBox()
        self.vad_sil_spin.setRange(10, 5000)
        self.vad_sil_spin.setSingleStep(50)
        self.vad_sil_spin.setValue(100)
        vgrid.addWidget(self.vad_sil_spin, 2, 1)
        self.vad_advanced = QWidget()
        self.vad_advanced.setLayout(vgrid)
        self.vad_advanced.setVisible(False)
        self.vad_chk.toggled.connect(self.vad_advanced.setVisible)
        tr_grp.body_layout.addWidget(self.vad_advanced)

        glossary_row = QHBoxLayout()
        glossary_row.addWidget(QLabel("Glossary:"))
        self.glossary_edit = QLineEdit()
        self.glossary_edit.setPlaceholderText("Comma separated key terms, names, acronyms…")
        glossary_row.addWidget(self.glossary_edit)
        tr_grp.body_layout.addLayout(glossary_row)
        ll.addWidget(tr_grp)

        # Slide detection
        det_grp = CollapsibleGroup("Slide detection")
        det_row = QHBoxLayout()
        det_row.addWidget(QLabel("Sensitivity:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Conservative", "Balanced", "Detailed"])
        self.preset_combo.setCurrentIndex(1)
        det_row.addWidget(self.preset_combo)
        self.preview_btn = QPushButton("Preview detection…")
        self.preview_btn.clicked.connect(self.preview_detection_requested.emit)
        det_row.addWidget(self.preview_btn)
        det_grp.body_layout.addLayout(det_row)

        from lecturepack.ui.widgets.crop_selector import CropSelector
        det_grp.body_layout.addWidget(
            QLabel("Crop (green) and ignore regions (red) — draw on the preview:"))
        self.crop_selector = CropSelector()
        self.crop_selector.setMinimumHeight(200)
        det_grp.body_layout.addWidget(self.crop_selector)
        tools_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.crop_radio = QRadioButton("Draw crop")
        self.crop_radio.setChecked(True)
        self.crop_radio.toggled.connect(lambda: self.crop_selector.set_draw_mode("crop"))
        self.ignore_radio = QRadioButton("Draw ignore region (max 3)")
        self.ignore_radio.toggled.connect(lambda: self.crop_selector.set_draw_mode("ignore"))
        self.mode_group.addButton(self.crop_radio)
        self.mode_group.addButton(self.ignore_radio)
        clear_rects_btn = QPushButton("Clear")
        clear_rects_btn.clicked.connect(self.crop_selector.clear_rects)
        tools_layout.addWidget(self.crop_radio)
        tools_layout.addWidget(self.ignore_radio)
        tools_layout.addWidget(clear_rects_btn)
        det_grp.body_layout.addLayout(tools_layout)
        ll.addWidget(det_grp)

        # Diagnostics
        diag_grp = CollapsibleGroup("System diagnostics", collapsed=True)
        self.diag_lbl = QLabel("…")
        self.diag_lbl.setWordWrap(True)
        diag_grp.body_layout.addWidget(self.diag_lbl)
        ll.addWidget(diag_grp)

        # Actions
        act_row = QHBoxLayout()
        self.start_btn = QPushButton("Start processing")
        self.start_btn.setProperty("primary", True)
        self.start_btn.setMinimumHeight(38)
        self.start_btn.clicked.connect(self.start_requested.emit)
        self.retranscribe_btn = QPushButton("Retranscribe only")
        self.retranscribe_btn.setEnabled(False)
        self.retranscribe_btn.clicked.connect(self.retranscribe_requested.emit)
        act_row.addWidget(self.start_btn, 1)
        act_row.addWidget(self.retranscribe_btn)
        ll.addLayout(act_row)
        ll.addStretch(1)

        left_scroll.setWidget(left)
        self.splitter.addWidget(left_scroll)

        # ---- right: progress -------------------------------------------- #
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        self.stage_lbl = QLabel("Idle")
        self.stage_lbl.setProperty("h1", True)
        rl.addWidget(self.stage_lbl)

        stages_card = QFrame()
        stages_card.setProperty("card", True)
        sc = QVBoxLayout(stages_card)
        self.stage_rows = {}
        for stage in STAGES:
            row = StageRow(stage)
            self.stage_rows[stage] = row
            sc.addWidget(row)
        rl.addWidget(stages_card)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        rl.addWidget(self.progress_bar)

        log_hdr = QHBoxLayout()
        self.log_toggle = QToolButton()
        self.log_toggle.setText("▾ Logs")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(True)
        self.log_toggle.setStyleSheet("QToolButton{border:none;font-weight:600;}")
        self.log_toggle.clicked.connect(self._toggle_logs)
        log_hdr.addWidget(self.log_toggle)
        log_hdr.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("danger", True)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        log_hdr.addWidget(self.cancel_btn)
        rl.addLayout(log_hdr)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "background: #101214; color: #7dd97b; font-family: Consolas, monospace; font-size: 11px;")
        rl.addWidget(self.log_text, 1)

        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------ #
    def _toggle_logs(self):
        open_ = self.log_toggle.isChecked()
        self.log_text.setVisible(open_)
        self.log_toggle.setText(("▾ " if open_ else "▸ ") + "Logs")

    def _tick(self):
        for row in self.stage_rows.values():
            row.tick()

    def _browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Lecture Video", "",
            f"Video Files (*{' *'.join(SUPPORTED_VIDEO_EXTENSIONS)})")
        if file_path:
            self.video_path_edit.setText(file_path)
            self.video_chosen.emit(file_path)

    def _browse_vad_model(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select VAD Model", "",
                                                   "Model files (*.bin)")
        if file_path:
            self.vad_model_edit.setText(file_path)

    # ---- controller feedback -------------------------------------------- #
    def reset_progress(self):
        for row in self.stage_rows.values():
            row.set_state("pending")
            row.bar.setValue(0)
            row.elapsed.setText("")
        self.progress_bar.setValue(0)
        self.log_text.clear()

    def on_stage_started(self, stage):
        self.stage_lbl.setText(f"Running: {stage}")
        row = self.stage_rows.get(stage)
        if row:
            row.set_state("running")

    def on_stage_progress(self, stage, percent):
        row = self.stage_rows.get(stage)
        if row:
            row.bar.setValue(percent)
        self.progress_bar.setValue(percent)

    def on_stage_finished(self, stage, success, error):
        row = self.stage_rows.get(stage)
        if row:
            row.set_state("completed" if success else "failed")

    def on_stage_log(self, stage, msg):
        self.log_text.insertPlainText(msg)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def mark_stage_cached(self, stage):
        row = self.stage_rows.get(stage)
        if row:
            row.set_state("cached")

    def set_engine_status(self, text):
        self.engine_status_lbl.setText(text)

    def set_diagnostics_text(self, text):
        self.diag_lbl.setText(text)
