"""
lecturepack.ui.pages.process_page
=================================

Job setup + live processing view (Phase 2 "minimalist dropzone" redesign).

The page leads with a large dropzone hero (drag a video in; the dashed
border glows accent-blue while a drag hovers). Engine knobs, VAD thresholds
and slide-detection settings live behind an animated "Advanced Settings"
slide-out drawer. The right column shows stage-by-stage progress, the live
transcript (streamed whisper.cpp segments rendered as TranscriptBlockWidget
cards; ephemeral view -- canonical text still derives from the raw layer)
and the throttled log. Every pre-existing widget attribute, object name and
signal used by MainWindow and the test-suite is preserved.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QElapsedTimer, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
    QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QRadioButton, QButtonGroup, QScrollArea,
    QSpinBox, QSplitter, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from lecturepack.constants import (
    STAGES, SUPPORTED_VIDEO_EXTENSIONS,
    PRODUCT_MODES, PRODUCT_MODE_LABELS, TRANSCRIPTION_MODE_LABELS,
    TRANSCRIPTION_BACKEND_LOCAL,
)
from lecturepack.infrastructure.transcription_engines import (
    ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN, ENGINE_LABELS,
)
from lecturepack.ui import theme
from lecturepack.ui.widgets.transcript_block import TranscriptStreamView

DRAWER_WIDTH = 380


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


class DropzoneHero(QFrame):
    """The big minimalist video drop target with an accent glow on drag."""

    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropzoneHero")
        self.setAcceptDrops(True)
        self._glow = None
        self._glow_anim = None

    # ---- drag & drop ---------------------------------------------------- #
    def dragEnterEvent(self, event):  # noqa: N802 (Qt naming)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):  # noqa: N802
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        self._set_active(False)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS):
                event.acceptProposedAction()
                self.file_dropped.emit(path)

    # ---- glow state ------------------------------------------------------ #
    def _set_active(self, active: bool):
        self.setProperty("dropActive", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if active:
            self._start_glow()
        else:
            self._stop_glow()

    def _start_glow(self):
        if self._glow is None:
            self._glow = QGraphicsDropShadowEffect(self)
            self._glow.setColor(QColor(theme.MOCHA_ACCENT))
            self._glow.setXOffset(0.0)
            self._glow.setYOffset(0.0)
            self._glow.setBlurRadius(18.0)
            self.setGraphicsEffect(self._glow)
        if self._glow_anim is None:
            anim = QPropertyAnimation(self._glow, b"blurRadius", self)
            anim.setDuration(600)
            anim.setStartValue(18.0)
            anim.setKeyValueAt(0.5, 34.0)
            anim.setEndValue(18.0)
            anim.setLoopCount(-1)
            anim.start()
            self._glow_anim = anim

    def _stop_glow(self):
        if self._glow_anim is not None:
            self._glow_anim.stop()
            self._glow_anim = None
        if self._glow is not None:
            self.setGraphicsEffect(None)
            self._glow = None


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
        icons = {"pending": ("○", ""),
                 "running": ("◔", "color:#89B4FA;font-weight:bold;"),
                 "completed": ("●", "color:#A6E3A1;font-weight:bold;"),
                 "failed": ("✕", "color:#F38BA8;font-weight:bold;"),
                 "cached": ("◍", "color:#A6E3A1;"),
                 "skipped": ("–", "color:#A6ADC8;"),
                 "cancelled": ("◌", "color:#F9E2AF;")}
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
        self._advanced_open = False
        self._drawer_anim = None
        self._build_ui()
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.splitter, 1)

        # ---- main column ------------------------------------------------ #
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 6, 0)
        ml.setSpacing(8)

        # Dropzone hero
        self.dropzone = DropzoneHero()
        self.dropzone.setMinimumHeight(150)
        dz = QVBoxLayout(self.dropzone)
        dz.setContentsMargins(18, 14, 18, 14)
        dz.addStretch(1)
        hint_icon = QLabel("⇩")
        hint_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_icon.setStyleSheet("font-size: 30px; color: #89B4FA;")
        dz.addWidget(hint_icon)
        hint = QLabel("Drop a lecture video here")
        hint.setProperty("dropHint", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.addWidget(hint)
        dz.addStretch(1)
        path_layout = QHBoxLayout()
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("…or paste a video path")
        browse_video_btn = QPushButton("Browse")
        browse_video_btn.clicked.connect(self._browse_video)
        path_layout.addWidget(self.video_path_edit, 1)
        path_layout.addWidget(browse_video_btn)
        dz.addLayout(path_layout)
        self.metadata_lbl = QLabel("No video loaded.")
        self.metadata_lbl.setProperty("muted", True)
        self.metadata_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.addWidget(self.metadata_lbl)
        self.dropzone.file_dropped.connect(self._on_dropzone_file)
        ml.addWidget(self.dropzone)

        # Primary controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Output:"))
        self.product_mode_combo = QComboBox()
        for m in PRODUCT_MODES:
            self.product_mode_combo.addItem(PRODUCT_MODE_LABELS[m], m)
        controls.addWidget(self.product_mode_combo)
        controls.addStretch(1)
        self.advanced_toggle = QPushButton("Advanced Settings")
        self.advanced_toggle.setObjectName("advancedSettingsToggle")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self.set_advanced_open)
        controls.addWidget(self.advanced_toggle)
        ml.addLayout(controls)

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
        ml.addLayout(act_row)

        self.stage_lbl = QLabel("Idle")
        self.stage_lbl.setProperty("h1", True)
        ml.addWidget(self.stage_lbl)

        stages_card = QFrame()
        stages_card.setProperty("card", True)
        theme.add_card_shadow(stages_card)
        sc = QVBoxLayout(stages_card)
        self.stage_rows = {}
        for stage in STAGES:
            row = StageRow(stage)
            self.stage_rows[stage] = row
            sc.addWidget(row)
        ml.addWidget(stages_card)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        ml.addWidget(self.progress_bar)

        # Live transcript: segments streamed from whisper.cpp stdout while
        # transcription runs (ephemeral view; canonical text comes from the
        # raw transcript layer after the stage completes).
        live_lbl = QLabel("Live transcript")
        live_lbl.setProperty("muted", True)
        ml.addWidget(live_lbl)
        self.live_transcript = TranscriptStreamView(live=True, max_blocks=200)
        self.live_transcript.setMinimumHeight(120)
        self.live_transcript.setMaximumHeight(180)
        ml.addWidget(self.live_transcript)

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
        ml.addLayout(log_hdr)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "background: #11111B; color: #A6E3A1; "
            "font-family: Consolas, monospace; font-size: 11px;")
        ml.addWidget(self.log_text, 1)

        self.splitter.addWidget(main)

        # ---- advanced settings slide-out drawer -------------------------- #
        self.advanced_drawer = QFrame()
        self.advanced_drawer.setObjectName("AdvancedDrawer")
        drawer_outer = QVBoxLayout(self.advanced_drawer)
        drawer_outer.setContentsMargins(8, 0, 0, 0)
        drawer_title = QLabel("Advanced Settings")
        drawer_title.setProperty("h2", True)
        drawer_outer.addWidget(drawer_title)

        drawer_scroll = QScrollArea()
        drawer_scroll.setWidgetResizable(True)
        drawer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        drawer_body = QWidget()
        dl = QVBoxLayout(drawer_body)
        dl.setContentsMargins(0, 0, 6, 0)

        # Transcription
        tr_grp = CollapsibleGroup("Transcription")
        grid = QGridLayout()
        grid.addWidget(QLabel("Processing:"), 0, 0)
        self.transcription_mode_combo = QComboBox()
        for key, label in TRANSCRIPTION_MODE_LABELS.items():
            self.transcription_mode_combo.addItem(label, key)
        grid.addWidget(self.transcription_mode_combo, 0, 1)
        grid.addWidget(QLabel("Profile:"), 1, 0)
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["Fast", "Balanced", "Accurate", "Custom"])
        grid.addWidget(self.profile_combo, 1, 1)
        grid.addWidget(QLabel("Engine:"), 2, 0)
        self.engine_combo = QComboBox()
        for key in (ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN):
            self.engine_combo.addItem(ENGINE_LABELS[key], key)
        grid.addWidget(self.engine_combo, 2, 1)
        grid.addWidget(QLabel("Threads:"), 3, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(8)
        grid.addWidget(self.threads_spin, 3, 1)
        grid.addWidget(QLabel("Online requests:"), 4, 0)
        self.groq_concurrency_spin = QSpinBox()
        self.groq_concurrency_spin.setRange(1, 4)
        self.groq_concurrency_spin.setValue(
            int(self.config_manager.get("groq_concurrency", 2)))
        grid.addWidget(self.groq_concurrency_spin, 4, 1)
        tr_grp.body_layout.addLayout(grid)
        self.online_fallback_chk = QCheckBox(
            "Fall back to Private Local if the online provider is unavailable")
        self.online_fallback_chk.setChecked(bool(
            self.config_manager.get("online_fallback_local", True)))
        tr_grp.body_layout.addWidget(self.online_fallback_chk)
        self.online_notice_lbl = QLabel(
            "Online modes upload only lossless 16 kHz mono audio chunks to Groq. "
            "Slides, video, transcripts, and job metadata stay local.")
        self.online_notice_lbl.setWordWrap(True)
        self.online_notice_lbl.setProperty("muted", True)
        tr_grp.body_layout.addWidget(self.online_notice_lbl)
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
        self.transcription_mode_combo.currentIndexChanged.connect(
            self._update_transcription_mode)
        dl.addWidget(tr_grp)

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
        dl.addWidget(det_grp)

        # Diagnostics
        diag_grp = CollapsibleGroup("System diagnostics", collapsed=True)
        self.diag_lbl = QLabel("…")
        self.diag_lbl.setWordWrap(True)
        diag_grp.body_layout.addWidget(self.diag_lbl)
        dl.addWidget(diag_grp)
        dl.addStretch(1)

        drawer_scroll.setWidget(drawer_body)
        drawer_outer.addWidget(drawer_scroll, 1)
        self.advanced_drawer.setMinimumWidth(0)
        self.advanced_drawer.setMaximumWidth(0)
        self.advanced_drawer.setVisible(False)
        root.addWidget(self.advanced_drawer)

        self._update_transcription_mode()

    # ------------------------------------------------------------------ #
    # advanced settings drawer
    # ------------------------------------------------------------------ #
    def set_advanced_open(self, open_: bool):
        open_ = bool(open_)
        if open_ == self._advanced_open:
            return
        self._advanced_open = open_
        self.advanced_toggle.blockSignals(True)
        self.advanced_toggle.setChecked(open_)
        self.advanced_toggle.blockSignals(False)
        if self._drawer_anim is not None:
            self._drawer_anim.stop()
        anim = QPropertyAnimation(self.advanced_drawer, b"maximumWidth", self)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self.advanced_drawer.maximumWidth())
        if open_:
            self.advanced_drawer.setVisible(True)
            anim.setEndValue(DRAWER_WIDTH)
        else:
            anim.setEndValue(0)
            anim.finished.connect(
                lambda: self.advanced_drawer.setVisible(False))
        anim.start()
        self._drawer_anim = anim

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

    def _on_dropzone_file(self, file_path):
        self.video_path_edit.setText(file_path)
        self.video_chosen.emit(file_path)

    def _browse_vad_model(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select VAD Model", "",
                                                   "Model files (*.bin)")
        if file_path:
            self.vad_model_edit.setText(file_path)

    def _update_transcription_mode(self):
        local = self.transcription_mode_combo.currentData() == TRANSCRIPTION_BACKEND_LOCAL
        for widget in (self.profile_combo, self.engine_combo, self.threads_spin,
                       self.vad_chk, self.vad_model_edit, self.vad_advanced):
            widget.setEnabled(local)
        self.groq_concurrency_spin.setEnabled(not local)
        self.online_fallback_chk.setVisible(not local)
        self.online_notice_lbl.setVisible(not local)

    # ---- controller feedback -------------------------------------------- #
    def reset_progress(self):
        for row in self.stage_rows.values():
            row.set_state("pending")
            row.bar.setValue(0)
            row.elapsed.setText("")
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.live_transcript.clear()

    def on_transcript_segment(self, segment):
        """Append one live segment block; arrival rate is a few per second."""
        text = str(segment.get("text", "")).strip()
        if not text:
            return
        try:
            start_ms = int(segment.get("start_ms", 0))
        except (TypeError, ValueError):
            start_ms = 0
        try:
            end_ms = int(segment.get("end_ms", start_ms))
        except (TypeError, ValueError):
            end_ms = start_ms
        self.live_transcript.append_segment(
            max(0, start_ms) / 1000.0, max(0, end_ms) / 1000.0, text)

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
