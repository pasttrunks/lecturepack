"""
lecturepack.ui.pages.process_page
=================================

Job setup + live processing view (Studio layout).

The page uses a two-column layout:
  Left (drawer): Source path, Transcription, Slide detection, Diagnostics
  Right (flex): Output mode, Pipeline progress, Live transcript, Live log

Every pre-existing widget attribute, object name and signal used by
MainWindow and the test-suite is preserved.
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


def _card(title: str = "", parent=None) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(parent)
    card.setProperty("card", True)
    theme.add_card_shadow(card)
    # NOTE: card background/border/radius come from the global
    # `QFrame[card="true"]` QSS rule (theme.py) so they stay correct across
    # theme toggles. A local literal `QFrame{...}` override here would be a
    # bare type selector that cascades onto every QFrame-derived descendant
    # (QLabel included, since QLabel subclasses QFrame) and both boxes every
    # child label and freezes the color to whatever theme was active at
    # construction time.
    lay = QVBoxLayout(card)
    lay.setContentsMargins(15, 13, 15, 13)
    lay.setSpacing(6)
    if title:
        lbl = QLabel(title)
        lbl.setProperty("muted", True)
        lbl.setStyleSheet(
            f"font:500 10px '{theme.FONT_MONO}';letter-spacing:0.12em;"
            f"text-transform:uppercase;border:none;background:transparent;margin-bottom:3px;"
        )
        lay.addWidget(lbl)
    return card, lay


class CollapsibleGroup(QFrame):
    """A titled, collapsible settings card."""

    def __init__(self, title, parent=None, collapsed=False):
        super().__init__(parent)
        self.setProperty("card", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 8)
        self.toggle = QToolButton()
        self.toggle.setText(("▸ " if collapsed else "▾ ") + title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(not collapsed)
        self.toggle.setStyleSheet("QToolButton{border:none;font-weight:700;font-size:13px;}")
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_active(False)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS):
                event.acceptProposedAction()
                self.file_dropped.emit(path)

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
            self._glow.setColor(QColor(theme.DARK_PRIMARY if theme.is_dark() else theme.LIGHT_PRIMARY))
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
        if theme.is_dark():
            _run_c = theme.DARK_PRIMARY
            _muted_c = theme.DARK_MUTED
        else:
            _run_c = theme.LIGHT_PRIMARY
            _muted_c = theme.LIGHT_MUTED
        icons = {"pending": ("○", ""),
                 "running": ("◔", f"color:{_run_c};font-weight:700;"),
                 "completed": ("●", f"color:{theme.SUCCESS};font-weight:700;"),
                 "failed": ("✕", f"color:{theme.DANGER};font-weight:700;"),
                 "cached": ("◍", f"color:{theme.SUCCESS};"),
                 "skipped": ("–", f"color:{_muted_c};"),
                 "cancelled": ("◌", f"color:{theme.WARNING};")}
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

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(0)
        self.splitter.setStyleSheet("QSplitter::handle{background:transparent;}")
        root.addWidget(self.splitter)

        # ── Left: Advanced settings drawer (styled as Studio config column) ── #
        self.advanced_drawer = QFrame()
        self.advanced_drawer.setObjectName("AdvancedDrawer")
        self.advanced_drawer.setStyleSheet(
            "QFrame#AdvancedDrawer{background:transparent;border:none;}"
        )
        drawer_scroll = QScrollArea()
        drawer_scroll.setWidgetResizable(True)
        drawer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        drawer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        drawer_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        drawer_body = QWidget()
        drawer_body.setStyleSheet("background:transparent;")
        dl = QVBoxLayout(drawer_body)
        dl.setContentsMargins(0, 0, 14, 0)
        dl.setSpacing(14)

        # -- Transcription card (inside drawer) --
        tr_card, tr_lay = _card("Transcription")
        tr_lay.addWidget(QLabel("Engine:"))
        self.transcription_mode_combo = QComboBox()
        for key, label in TRANSCRIPTION_MODE_LABELS.items():
            self.transcription_mode_combo.addItem(label, key)
        tr_lay.addWidget(self.transcription_mode_combo)

        tr_lay.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["Fast", "Balanced", "Accurate", "Custom"])
        tr_lay.addWidget(self.profile_combo)

        tr_lay.addWidget(QLabel("Compute engine:"))
        self.engine_combo = QComboBox()
        for key in (ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN):
            self.engine_combo.addItem(ENGINE_LABELS[key], key)
        tr_lay.addWidget(self.engine_combo)

        tr_lay.addWidget(QLabel("Threads:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(8)
        tr_lay.addWidget(self.threads_spin)

        tr_lay.addWidget(QLabel("Online requests:"))
        self.groq_concurrency_spin = QSpinBox()
        self.groq_concurrency_spin.setRange(1, 4)
        self.groq_concurrency_spin.setValue(
            int(self.config_manager.get("groq_concurrency", 2)))
        tr_lay.addWidget(self.groq_concurrency_spin)

        self.online_fallback_chk = QCheckBox(
            "Fall back to Private Local if online unavailable")
        self.online_fallback_chk.setChecked(bool(
            self.config_manager.get("online_fallback_local", True)))
        tr_lay.addWidget(self.online_fallback_chk)

        self.online_notice_lbl = QLabel(
            "Online modes upload only lossless 16 kHz mono audio chunks to Groq. "
            "Slides, video, transcripts, and job metadata stay local.")
        self.online_notice_lbl.setWordWrap(True)
        self.online_notice_lbl.setProperty("muted", True)
        tr_lay.addWidget(self.online_notice_lbl)

        self.engine_status_lbl = QLabel("")
        self.engine_status_lbl.setProperty("muted", True)
        self.engine_status_lbl.setWordWrap(True)
        tr_lay.addWidget(self.engine_status_lbl)

        self.vad_chk = QCheckBox("Voice Activity Detection (VAD)")
        tr_lay.addWidget(self.vad_chk)
        vad_row = QHBoxLayout()
        self.vad_model_edit = QLineEdit()
        self.vad_model_edit.setPlaceholderText("VAD model (.bin)…")
        vad_browse = QPushButton("…")
        vad_browse.setFixedWidth(28)
        vad_browse.clicked.connect(self._browse_vad_model)
        vad_row.addWidget(self.vad_model_edit)
        vad_row.addWidget(vad_browse)
        tr_lay.addLayout(vad_row)
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
        tr_lay.addWidget(self.vad_advanced)

        glossary_row = QHBoxLayout()
        glossary_row.addWidget(QLabel("Glossary:"))
        self.glossary_edit = QLineEdit()
        self.glossary_edit.setPlaceholderText("Comma separated key terms…")
        glossary_row.addWidget(self.glossary_edit)
        tr_lay.addLayout(glossary_row)
        self.transcription_mode_combo.currentIndexChanged.connect(
            self._update_transcription_mode)
        dl.addWidget(tr_card)

        # -- Slide detection card (inside drawer) --
        det_card, det_lay = _card("Slide sensitivity")
        det_lay.addWidget(QLabel("Sensitivity:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Conservative", "Balanced", "Detailed"])
        self.preset_combo.setCurrentIndex(1)
        det_lay.addWidget(self.preset_combo)

        self.preview_btn = QPushButton("Preview detection…")
        self.preview_btn.clicked.connect(self.preview_detection_requested.emit)
        det_lay.addWidget(self.preview_btn)

        from lecturepack.ui.widgets.crop_selector import CropSelector
        det_lay.addWidget(
            QLabel("Crop (green) and ignore regions (red):"))
        self.crop_selector = CropSelector()
        self.crop_selector.setMinimumHeight(150)
        det_lay.addWidget(self.crop_selector)

        tools_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.crop_radio = QRadioButton("Draw crop")
        self.crop_radio.setChecked(True)
        self.crop_radio.toggled.connect(
            lambda: self.crop_selector.set_draw_mode("crop"))
        self.ignore_radio = QRadioButton("Draw ignore region")
        self.ignore_radio.toggled.connect(
            lambda: self.crop_selector.set_draw_mode("ignore"))
        self.mode_group.addButton(self.crop_radio)
        self.mode_group.addButton(self.ignore_radio)
        clear_rects_btn = QPushButton("Clear")
        clear_rects_btn.clicked.connect(self.crop_selector.clear_rects)
        tools_layout.addWidget(self.crop_radio)
        tools_layout.addWidget(self.ignore_radio)
        tools_layout.addWidget(clear_rects_btn)
        det_lay.addLayout(tools_layout)
        dl.addWidget(det_card)

        # -- Diagnostics card (inside drawer) --
        diag_card, diag_lay = _card("System diagnostics")
        self.diag_lbl = QLabel("…")
        self.diag_lbl.setWordWrap(True)
        diag_lay.addWidget(self.diag_lbl)
        dl.addWidget(diag_card)

        dl.addStretch(1)
        drawer_scroll.setWidget(drawer_body)

        drawer_inner = QVBoxLayout(self.advanced_drawer)
        drawer_inner.setContentsMargins(0, 0, 0, 0)
        drawer_inner.addWidget(drawer_scroll)

        self.advanced_drawer.setMinimumWidth(0)
        self.advanced_drawer.setMaximumWidth(0)
        self.advanced_drawer.setVisible(False)
        self.splitter.addWidget(self.advanced_drawer)

        # ── Right: Main content column ─────────────────────────────── #
        main = QWidget()
        main_lay = QVBoxLayout(main)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(14)

        # Source card (outside drawer for test compat)
        src_card, src_lay = _card("Source")
        self.dropzone = DropzoneHero()
        self.dropzone.setMinimumHeight(60)
        self.dropzone.setMaximumHeight(80)
        dz_lay = QVBoxLayout(self.dropzone)
        dz_lay.setContentsMargins(10, 6, 10, 6)
        hint = QLabel("Drop video or browse…")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setProperty("muted", True)
        hint.setStyleSheet("font-size:11px;border:none;background:transparent;")
        dz_lay.addWidget(hint)
        self.dropzone.file_dropped.connect(self._on_dropzone_file)
        src_lay.addWidget(self.dropzone)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Video path…")
        self.video_path_edit.setStyleSheet(
            "QLineEdit{padding:5px 8px;border-radius:7px;font-size:12px;}"
        )
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(62)
        browse_btn.setStyleSheet(
            "QPushButton{padding:5px 8px;border-radius:7px;font-size:12px;font-weight:600;}"
        )
        browse_btn.clicked.connect(self._browse_video)
        path_row.addWidget(self.video_path_edit, 1)
        path_row.addWidget(browse_btn)
        src_lay.addLayout(path_row)

        self.metadata_lbl = QLabel("No video loaded.")
        self.metadata_lbl.setProperty("muted", True)
        self.metadata_lbl.setStyleSheet("font:500 11px 'JetBrains Mono';border:none;background:transparent;")
        src_lay.addWidget(self.metadata_lbl)
        main_lay.addWidget(src_card)

        # Action buttons row
        act_row = QHBoxLayout()
        act_row.setSpacing(10)
        self.start_btn = QPushButton("Start processing")
        self.start_btn.setProperty("primary", True)
        self.start_btn.setMinimumHeight(38)
        self.start_btn.clicked.connect(self.start_requested.emit)
        self.retranscribe_btn = QPushButton("Retranscribe only")
        self.retranscribe_btn.setEnabled(False)
        self.retranscribe_btn.clicked.connect(self.retranscribe_requested.emit)
        self.advanced_toggle = QPushButton("Advanced Settings")
        self.advanced_toggle.setObjectName("advancedSettingsToggle")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self.set_advanced_open)
        act_row.addWidget(self.start_btn, 1)
        act_row.addWidget(self.retranscribe_btn)
        act_row.addWidget(self.advanced_toggle)
        main_lay.addLayout(act_row)

        # Output mode card
        out_card, out_lay = _card("Output mode")
        self.product_mode_combo = QComboBox()
        for m in PRODUCT_MODES:
            self.product_mode_combo.addItem(PRODUCT_MODE_LABELS[m], m)
        self.product_mode_combo.setProperty("outputMode", True)
        self.product_mode_combo.setStyleSheet(
            "QComboBox{padding:7px 10px;border-radius:9px;font-weight:600;font-size:13px;}"
        )
        out_lay.addWidget(self.product_mode_combo)
        main_lay.addWidget(out_card)

        # Pipeline progress card
        prog_card, prog_lay = _card()
        self.stage_lbl = QLabel("Idle")
        self.stage_lbl.setStyleSheet("font-weight:700;font-size:20px;")
        prog_lay.addWidget(self.stage_lbl)
        prog_lay.addSpacing(6)

        self.stage_rows = {}
        for stage in STAGES:
            row = StageRow(stage)
            self.stage_rows[stage] = row
            prog_lay.addWidget(row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumHeight(8)
        self.progress_bar.setTextVisible(False)
        prog_lay.addWidget(self.progress_bar)
        main_lay.addWidget(prog_card)

        # Live transcript
        live_lbl = QLabel("Live transcript")
        live_lbl.setProperty("muted", True)
        main_lay.addWidget(live_lbl)
        self.live_transcript = TranscriptStreamView(live=True, max_blocks=200)
        self.live_transcript.setMinimumHeight(80)
        self.live_transcript.setMaximumHeight(150)
        main_lay.addWidget(self.live_transcript)

        # Live log card
        log_card = QFrame()
        log_card.setProperty("card", True)
        theme.add_card_shadow(log_card)
        log_lay = QVBoxLayout(log_card)
        log_lay.setContentsMargins(0, 0, 0, 0)
        log_lay.setSpacing(0)

        log_header = QHBoxLayout()
        log_header.setContentsMargins(16, 12, 16, 10)
        log_title = QLabel("Live log")
        log_title.setProperty("muted", True)
        log_title.setStyleSheet(
            f"font:500 10px '{theme.FONT_MONO}';letter-spacing:0.12em;"
            f"text-transform:uppercase;border:none;background:transparent;"
        )
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("danger", True)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        log_header.addWidget(self.cancel_btn)
        log_lay.addLayout(log_header)

        log_sep = QFrame()
        log_sep.setFrameShape(QFrame.Shape.HLine)
        log_sep.setStyleSheet(f"color:{theme.c('line')};")
        log_lay.addWidget(log_sep)

        self.log_toggle = QToolButton()
        self.log_toggle.setText("▾ Logs")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(True)
        self.log_toggle.setStyleSheet("QToolButton{border:none;font-weight:700;}")
        self.log_toggle.clicked.connect(self._toggle_logs)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setProperty("logConsole", True)
        self.log_text.setStyleSheet(
            f"font-family: {theme.FONT_MONO}; font-size: 11px;")
        self.log_text.setMinimumHeight(120)

        log_lay.addWidget(self.log_toggle)
        log_lay.addWidget(self.log_text, 1)
        main_lay.addWidget(log_card, 1)

        self.splitter.addWidget(main)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        self._update_transcription_mode()

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

    def reset_progress(self):
        for row in self.stage_rows.values():
            row.set_state("pending")
            row.bar.setValue(0)
            row.elapsed.setText("")
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.live_transcript.clear()

    def on_transcript_segment(self, segment):
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
