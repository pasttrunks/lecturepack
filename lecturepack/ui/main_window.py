import os
import datetime
import shutil
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QComboBox, QRadioButton, QButtonGroup,
    QStackedWidget, QProgressBar, QTextEdit, QListWidget, QListWidgetItem,
    QCheckBox, QMessageBox, QGroupBox, QSplitter, QDialog, QTableWidgetItem
)
from PySide6.QtGui import QIcon, QPixmap, QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtCore import Qt, QSize, QRectF, QTimer

from lecturepack.constants import (
    STAGE_INSPECT, STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE,
    STAGE_DETECT_SLIDES, STAGE_ALIGN, STAGE_REVIEW_READY, STAGE_EXPORT,
    STAGES, DEFAULT_DATA_DIR, SUPPORTED_VIDEO_EXTENSIONS
)
from lecturepack.models.job import Job
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services.export_service import datetime_from_seconds



class RestoreDialog(QDialog):
    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore Archived Job")
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        layout.addWidget(QLabel("Select an archived job to restore:"))
        layout.addWidget(self.list_widget)
        
        self.archive_dir = os.path.join(data_dir, "archive")
        self.archived_jobs = []
        
        if os.path.exists(self.archive_dir):
            for job_id in os.listdir(self.archive_dir):
                manifest_p = os.path.join(self.archive_dir, job_id, "manifest.json")
                if os.path.exists(manifest_p):
                    man = FileManager.read_json_safe(manifest_p)
                    if isinstance(man, dict):
                        title = man.get("title", job_id)
                        self.list_widget.addItem(f"{title} ({job_id[:8]})")
                        self.archived_jobs.append(job_id)
                        
        buttons = QHBoxLayout()
        restore_btn = QPushButton("Restore")
        restore_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        buttons.addWidget(restore_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        
    def get_selected_job_id(self):
        row = self.list_widget.currentRow()
        if row >= 0 and row < len(self.archived_jobs):
            return self.archived_jobs[row]
        return None

# Easy preview extractor
def extract_preview(video_path, out_path):
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False
    # Grab frame at 2 seconds or midpoint if short
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(2.0 * fps))
    ret, frame = cap.read()
    if not ret or frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    if ret and frame is not None:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        cv2.imwrite(out_path, frame)
        cap.release()
        return True
    cap.release()
    return False

class MainWindow(QMainWindow):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.controller = JobController(config_manager)
        self.current_job = None
        self.undo_stack = []
        self.raw_segments = []
        self.edited_data = {}
        self.aligned_data = []
        self.current_search_match = -1
        
        # Async capability detection
        from lecturepack.infrastructure.whisper_detector import WhisperCapabilityDetector
        self.whisper_detector = WhisperCapabilityDetector(self)
        self.whisper_detector.finished.connect(self._on_whisper_detection_finished)
        self.current_whisper_caps = None

        from lecturepack import __version__
        self.setWindowTitle(f"Lecture Pack v{__version__}")
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        # Setup Main Stacked Widget
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._init_setup_view()
        self._init_processing_view()
        self._init_review_view()
        self._init_shortcuts()

        # Connect controller signals
        self.controller.stage_started.connect(self._on_stage_started)
        self.controller.stage_progress.connect(self._on_stage_progress)
        self.controller.stage_log.connect(self._on_stage_log)
        self.controller.stage_finished.connect(self._on_stage_finished)
        self.controller.pipeline_completed.connect(self._on_pipeline_completed)
        self.controller.pipeline_failed.connect(self._on_pipeline_failed)

        # Autodetect dependencies and scan jobs
        self.config_manager.autodetect_ffmpeg()
        self.config_manager.autodetect_whisper()
        self._reload_recent_jobs()
        self._refresh_diagnostics()

    # Drag and drop support
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS):
                self.video_path_edit.setText(file_path)
                self._on_video_selected(file_path)

    # 1. SETUP VIEW INITIALIZATION
    def _init_setup_view(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # Left pane: parameters & setup
        left_layout = QVBoxLayout()
        
        # Job select group
        job_grp = QGroupBox("Recent Jobs")
        job_layout = QVBoxLayout(job_grp)
        self.recent_jobs_combo = QComboBox()
        self.recent_jobs_combo.currentIndexChanged.connect(self._on_recent_job_changed)
        job_layout.addWidget(self.recent_jobs_combo)
        
        # Job archiving / restoring actions
        job_actions = QHBoxLayout()
        self.archive_btn = QPushButton("Archive Job")
        self.archive_btn.clicked.connect(self._archive_current_job)
        self.restore_btn_job = QPushButton("Restore Job...")
        self.restore_btn_job.clicked.connect(self._restore_archived_job)
        self.export_archive_btn = QPushButton("Export Archive...")
        self.export_archive_btn.clicked.connect(self._export_job_archive)
        job_actions.addWidget(self.archive_btn)
        job_actions.addWidget(self.restore_btn_job)
        job_actions.addWidget(self.export_archive_btn)
        job_layout.addLayout(job_actions)
        
        left_layout.addWidget(job_grp)

        # Video select group
        video_grp = QGroupBox("Lecture Video")
        video_layout = QVBoxLayout(video_grp)
        
        drag_lbl = QLabel("Drag video here or click Browse")
        drag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drag_lbl.setStyleSheet("border: 2px dashed #999; padding: 20px; background: #eee;")
        video_layout.addWidget(drag_lbl)

        path_layout = QHBoxLayout()
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Select lecture video path...")
        browse_video_btn = QPushButton("Browse")
        browse_video_btn.clicked.connect(self._browse_video)
        path_layout.addWidget(self.video_path_edit)
        path_layout.addWidget(browse_video_btn)
        video_layout.addLayout(path_layout)
        
        self.metadata_lbl = QLabel("No video loaded.")
        video_layout.addWidget(self.metadata_lbl)
        left_layout.addWidget(video_grp)

        # Whisper Settings Group
        whisper_grp = QGroupBox("Whisper Settings & Transcription Quality")
        whisper_layout = QVBoxLayout(whisper_grp)
        
        exe_layout = QHBoxLayout()
        exe_layout.addWidget(QLabel("Whisper Exe:"))
        self.whisper_exe_edit = QLineEdit(self.config_manager.get("whisper_exe", ""))
        self.whisper_exe_edit.textChanged.connect(lambda t: self.config_manager.set("whisper_exe", t))
        self.whisper_exe_edit.textChanged.connect(self._refresh_diagnostics)
        browse_exe_btn = QPushButton("Browse")
        browse_exe_btn.clicked.connect(self._browse_whisper_exe)
        exe_layout.addWidget(self.whisper_exe_edit)
        exe_layout.addWidget(browse_exe_btn)
        whisper_layout.addLayout(exe_layout)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model Path:"))
        self.whisper_model_edit = QLineEdit(self.config_manager.get("whisper_model", ""))
        self.whisper_model_edit.textChanged.connect(lambda t: self.config_manager.set("whisper_model", t))
        self.whisper_model_edit.textChanged.connect(self._refresh_diagnostics)
        browse_model_btn = QPushButton("Browse")
        browse_model_btn.clicked.connect(self._browse_whisper_model)
        model_layout.addWidget(self.whisper_model_edit)
        model_layout.addWidget(browse_model_btn)
        whisper_layout.addLayout(model_layout)

        # Profile selection
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["Fast", "Accurate", "Custom"])
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_layout.addWidget(self.profile_combo)
        
        # Thread count
        profile_layout.addWidget(QLabel("Threads:"))
        from PySide6.QtWidgets import QSpinBox
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(8)
        self.threads_spin.valueChanged.connect(self._refresh_diagnostics)
        profile_layout.addWidget(self.threads_spin)
        whisper_layout.addLayout(profile_layout)

        # Dynamic Model Info display
        self.whisper_model_info_lbl = QLabel("Model Info: -")
        self.whisper_model_info_lbl.setStyleSheet("font-size: 11px; color: #555;")
        whisper_layout.addWidget(self.whisper_model_info_lbl)

        # VAD Setup
        vad_layout = QVBoxLayout()
        self.vad_chk = QCheckBox("Enable Voice Activity Detection (VAD)")
        self.vad_chk.toggled.connect(self._on_vad_toggled)
        vad_layout.addWidget(self.vad_chk)

        vad_path_layout = QHBoxLayout()
        self.vad_model_label = QLabel("VAD Model:")
        self.vad_model_edit = QLineEdit()
        self.vad_model_edit.setPlaceholderText("Select VAD model (.bin)...")
        self.vad_model_edit.textChanged.connect(self._validate_vad_model)
        self.vad_browse_btn = QPushButton("Browse")
        self.vad_browse_btn.clicked.connect(self._browse_vad_model)
        vad_path_layout.addWidget(self.vad_model_label)
        vad_path_layout.addWidget(self.vad_model_edit)
        vad_path_layout.addWidget(self.vad_browse_btn)
        vad_layout.addLayout(vad_path_layout)

        # Warning / Missing VAD model label
        self.vad_warning_lbl = QLabel("")
        self.vad_warning_lbl.setStyleSheet("color: #f44336; font-weight: bold; font-size: 11px;")
        self.vad_warning_lbl.setVisible(False)
        vad_layout.addWidget(self.vad_warning_lbl)

        # Advanced VAD Settings Toggle & Layout
        self.advanced_vad_btn = QPushButton("Show Advanced VAD Settings")
        self.advanced_vad_btn.setCheckable(True)
        self.advanced_vad_btn.toggled.connect(self._toggle_advanced_vad)
        vad_layout.addWidget(self.advanced_vad_btn)

        self.advanced_vad_widget = QWidget()
        advanced_vad_layout = QVBoxLayout(self.advanced_vad_widget)
        
        # Threshold SpinBox
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("VAD Threshold (0.01-1.0):"))
        from PySide6.QtWidgets import QDoubleSpinBox
        self.vad_thresh_spin = QDoubleSpinBox()
        self.vad_thresh_spin.setRange(0.01, 1.0)
        self.vad_thresh_spin.setSingleStep(0.05)
        self.vad_thresh_spin.setValue(0.50)
        thresh_layout.addWidget(self.vad_thresh_spin)
        advanced_vad_layout.addLayout(thresh_layout)

        # Min Speech Duration ms
        spd_layout = QHBoxLayout()
        spd_layout.addWidget(QLabel("Min Speech Duration (ms):"))
        self.vad_spd_spin = QSpinBox()
        self.vad_spd_spin.setRange(10, 5000)
        self.vad_spd_spin.setSingleStep(50)
        self.vad_spd_spin.setValue(250)
        spd_layout.addWidget(self.vad_spd_spin)
        advanced_vad_layout.addLayout(spd_layout)

        # Min Silence Duration ms
        sil_layout = QHBoxLayout()
        sil_layout.addWidget(QLabel("Min Silence Duration (ms):"))
        self.vad_sil_spin = QSpinBox()
        self.vad_sil_spin.setRange(10, 5000)
        self.vad_sil_spin.setSingleStep(50)
        self.vad_sil_spin.setValue(100)
        sil_layout.addWidget(self.vad_sil_spin)
        advanced_vad_layout.addLayout(sil_layout)

        self.advanced_vad_widget.setVisible(False)
        vad_layout.addWidget(self.advanced_vad_widget)
        whisper_layout.addLayout(vad_layout)
        
        glossary_layout = QHBoxLayout()
        glossary_layout.addWidget(QLabel("Course Glossary:"))
        self.glossary_edit = QLineEdit()
        self.glossary_edit.setPlaceholderText("Comma separated key terms, acronyms...")
        whisper_layout.addLayout(glossary_layout)

        left_layout.addWidget(whisper_grp)

        # Preset group
        preset_grp = QGroupBox("Slide Detection Sensitivity")
        preset_layout = QVBoxLayout(preset_grp)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Conservative", "Balanced", "Detailed"])
        preset_layout.addWidget(self.preset_combo)
        
        self.preview_btn = QPushButton("Preview Detection")
        self.preview_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 5px;")
        self.preview_btn.clicked.connect(self._run_detection_preview)
        preset_layout.addWidget(self.preview_btn)
        
        left_layout.addWidget(preset_grp)

        # Diagnostics bar
        diag_grp = QGroupBox("Diagnostics")
        diag_layout = QHBoxLayout(diag_grp)
        self.diag_ffmpeg_lbl = QLabel("FFmpeg: ...")
        self.diag_ffprobe_lbl = QLabel("FFprobe: ...")
        self.diag_whisper_lbl = QLabel("Whisper: ...")
        self.diag_model_lbl = QLabel("Model: ...")
        self.diag_data_lbl = QLabel("Data Dir: ...")
        for lbl in [self.diag_ffmpeg_lbl, self.diag_ffprobe_lbl, self.diag_whisper_lbl, self.diag_model_lbl, self.diag_data_lbl]:
            lbl.setStyleSheet("font-size: 11px; padding: 2px 6px;")
            diag_layout.addWidget(lbl)
        left_layout.addWidget(diag_grp)

        # Action Buttons
        actions_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Processing")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px; padding: 10px;")
        self.start_btn.clicked.connect(self._start_processing)
        
        self.retranscribe_btn = QPushButton("Retranscribe Only")
        self.retranscribe_btn.setStyleSheet("background-color: #ff9800; color: white; font-weight: bold; font-size: 14px; padding: 10px;")
        self.retranscribe_btn.clicked.connect(self._retranscribe_only_workflow)
        self.retranscribe_btn.setEnabled(False)
        
        actions_layout.addWidget(self.start_btn)
        actions_layout.addWidget(self.retranscribe_btn)
        left_layout.addLayout(actions_layout)

        layout.addLayout(left_layout, 1)

        # Right pane: Crop selector
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Slide Crop & Ignore Regions (Draw directly on preview below)"))
        
        from lecturepack.ui.widgets.crop_selector import CropSelector
        self.crop_selector = CropSelector()
        right_layout.addWidget(self.crop_selector, 1)

        # Selector tools
        tools_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        
        self.crop_radio = QRadioButton("Draw Crop Area (Green)")
        self.crop_radio.setChecked(True)
        self.crop_radio.toggled.connect(lambda: self.crop_selector.set_draw_mode("crop"))
        
        self.ignore_radio = QRadioButton("Draw Ignore Region (Red, max 3)")
        self.ignore_radio.toggled.connect(lambda: self.crop_selector.set_draw_mode("ignore"))

        self.mode_group.addButton(self.crop_radio)
        self.mode_group.addButton(self.ignore_radio)
        
        clear_rects_btn = QPushButton("Clear Drawings")
        clear_rects_btn.clicked.connect(self.crop_selector.clear_rects)

        tools_layout.addWidget(self.crop_radio)
        tools_layout.addWidget(self.ignore_radio)
        tools_layout.addWidget(clear_rects_btn)
        right_layout.addLayout(tools_layout)

        layout.addLayout(right_layout, 2)

        self.stack.addWidget(widget)

    # 2. PROCESSING VIEW INITIALIZATION
    def _init_processing_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.stage_lbl = QLabel("Stage: Pending")
        self.stage_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.stage_lbl)

        # Stages checklist
        self.stages_labels = {}
        stages_layout = QHBoxLayout()
        for stage in STAGES:
            lbl = QLabel(f"• {stage}")
            lbl.setStyleSheet("color: #777; font-weight: bold; margin: 5px;")
            stages_layout.addWidget(lbl)
            self.stages_labels[stage] = lbl
        layout.addLayout(stages_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background: #000; color: #0f0; font-family: Consolas, monospace;")
        layout.addWidget(self.log_text)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._cancel_processing)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)

        self.stack.addWidget(widget)

    # 3. REVIEW VIEW INITIALIZATION
    def _init_review_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Horizontal splitter to divide slides list from the preview/transcript pane
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left pane: all slides list (unified)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Slides Timeline (Click, Shift-Click, Ctrl-Click to Select)"))
        
        self.slides_view = QListWidget()
        self.slides_view.setViewMode(QListWidget.ViewMode.IconMode)
        self.slides_view.setIconSize(QSize(160, 120))
        self.slides_view.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.slides_view.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.slides_view.itemSelectionChanged.connect(self._on_slides_selection_changed)
        left_layout.addWidget(self.slides_view)
        splitter.addWidget(left_widget)

        # Right panel: vertical splitter split into Preview/Controls (top) and Transcript Pane (bottom)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Top child: Slide preview & Controls
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        
        self.preview_lbl = QLabel("Select a slide to preview")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("background: #222; border: 1px solid #555; min-height: 240px;")
        preview_layout.addWidget(self.preview_lbl, 1)

        self.slide_info_lbl = QLabel("Timestamp: -")
        self.slide_info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slide_info_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        preview_layout.addWidget(self.slide_info_lbl)

        # Selected count & Bulk actions
        controls_layout = QHBoxLayout()
        self.selected_count_lbl = QLabel("Selected: 0")
        self.selected_count_lbl.setStyleSheet("font-weight: bold; color: #2196F3;")
        controls_layout.addWidget(self.selected_count_lbl)
        
        self.bulk_keep_btn = QPushButton("Keep Selected")
        self.bulk_keep_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 6px;")
        self.bulk_keep_btn.clicked.connect(self._bulk_keep)
        
        self.bulk_reject_btn = QPushButton("Reject Selected (Del)")
        self.bulk_reject_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 6px;")
        self.bulk_reject_btn.clicked.connect(self._bulk_reject)

        self.bulk_restore_btn = QPushButton("Restore Selected (R)")
        self.bulk_restore_btn.setStyleSheet("background-color: #ff9800; color: white; font-weight: bold; padding: 6px;")
        self.bulk_restore_btn.clicked.connect(self._bulk_restore)

        controls_layout.addWidget(self.bulk_keep_btn)
        controls_layout.addWidget(self.bulk_reject_btn)
        controls_layout.addWidget(self.bulk_restore_btn)
        preview_layout.addLayout(controls_layout)
        
        right_splitter.addWidget(preview_panel)

        # Bottom child: Transcript pane
        transcript_panel = QWidget()
        transcript_layout = QVBoxLayout(transcript_panel)
        transcript_layout.addWidget(QLabel("Aligned Transcript Segment(s)"))

        # Search layout
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search transcript (Ctrl+F, F3/Shift+F3)...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_prev_btn = QPushButton("Prev")
        self.search_prev_btn.clicked.connect(self._search_prev)
        self.search_next_btn = QPushButton("Next")
        self.search_next_btn.clicked.connect(self._search_next)
        self.timestamps_chk = QCheckBox("Include Timestamps")
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_prev_btn)
        search_layout.addWidget(self.search_next_btn)
        search_layout.addWidget(self.timestamps_chk)
        transcript_layout.addLayout(search_layout)

        # Copy buttons
        copy_layout = QHBoxLayout()
        self.copy_current_btn = QPushButton("Copy Slide Transcript")
        self.copy_current_btn.clicked.connect(self._copy_current_transcript)
        self.copy_selected_btn = QPushButton("Copy Selected Transcripts")
        self.copy_selected_btn.clicked.connect(self._copy_selected_transcripts)
        self.copy_full_btn = QPushButton("Copy Full Transcript")
        self.copy_full_btn.clicked.connect(self._copy_full_transcript)
        
        copy_layout.addWidget(self.copy_current_btn)
        copy_layout.addWidget(self.copy_selected_btn)
        copy_layout.addWidget(self.copy_full_btn)
        transcript_layout.addLayout(copy_layout)

        # Transcript table
        from PySide6.QtWidgets import QTableWidget, QHeaderView
        self.transcript_table = QTableWidget()
        self.transcript_table.setColumnCount(3)
        self.transcript_table.setHorizontalHeaderLabels(["Time Range", "Segment Text (Editable)", "Action"])
        self.transcript_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.transcript_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.transcript_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.transcript_table.verticalHeader().setVisible(False)
        transcript_layout.addWidget(self.transcript_table, 1)

        # Save/status row
        save_layout = QHBoxLayout()
        self.save_corrections_btn = QPushButton("Save Corrections (Ctrl+S)")
        self.save_corrections_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 6px;")
        self.save_corrections_btn.clicked.connect(self._save_corrections)
        
        self.transcript_status_lbl = QLabel("")
        self.transcript_status_lbl.setStyleSheet("font-weight: bold; color: #4CAF50;")
        
        save_layout.addWidget(self.save_corrections_btn)
        save_layout.addWidget(self.transcript_status_lbl)
        transcript_layout.addLayout(save_layout)
        
        right_splitter.addWidget(transcript_panel)
        splitter.addWidget(right_splitter)

        layout.addWidget(splitter, 1)

        # Export Pane at bottom
        export_grp = QGroupBox("Export & Align Output")
        export_layout = QVBoxLayout(export_grp)
        
        formats_layout = QHBoxLayout()
        self.chk_slides_pdf = QCheckBox("Slides PDF")
        self.chk_slides_pdf.setChecked(True)
        self.chk_html_pack = QCheckBox("HTML Study Pack")
        self.chk_html_pack.setChecked(True)
        self.chk_srt = QCheckBox("SRT Subtitles")
        self.chk_srt.setChecked(True)
        self.chk_txt = QCheckBox("Plain Text Transcript")
        self.chk_txt.setChecked(True)
        self.chk_json = QCheckBox("Structured JSON")
        self.chk_json.setChecked(True)

        formats_layout.addWidget(self.chk_slides_pdf)
        formats_layout.addWidget(self.chk_html_pack)
        formats_layout.addWidget(self.chk_srt)
        formats_layout.addWidget(self.chk_txt)
        formats_layout.addWidget(self.chk_json)
        export_layout.addLayout(formats_layout)

        action_layout = QHBoxLayout()
        export_btn = QPushButton("Export Accepted")
        export_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        export_btn.clicked.connect(self._export_outputs)
        
        open_folder_btn = QPushButton("Open Output Folder")
        open_folder_btn.clicked.connect(self._open_output_folder)
        
        back_setup_btn = QPushButton("Back to Setup")
        back_setup_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        action_layout.addWidget(export_btn)
        action_layout.addWidget(open_folder_btn)
        action_layout.addWidget(back_setup_btn)
        export_layout.addLayout(action_layout)

        layout.addWidget(export_grp)

        self.stack.addWidget(widget)

    # 4. VIEW SLOTS & LOGIC
    def _browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Lecture Video", "", f"Video Files (*{' *'.join(SUPPORTED_VIDEO_EXTENSIONS)})")
        if file_path:
            self.video_path_edit.setText(file_path)
            self._on_video_selected(file_path)

    def _browse_whisper_exe(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select whisper.cpp Executable", "", "Executables (*.exe *.bat *.py)")
        if file_path:
            self.whisper_exe_edit.setText(file_path)
            self.config_manager.set("whisper_exe", file_path)

    def _browse_whisper_model(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Whisper Model", "", "Model files (*.bin)")
        if file_path:
            self.whisper_model_edit.setText(file_path)
            self.config_manager.set("whisper_model", file_path)

    def _on_video_selected(self, video_path):
        """Initializes a new job or loads it if it matches an existing file."""
        if not os.path.exists(video_path):
            return
        
        self.current_job = Job(self.config_manager.data_dir, video_path=video_path)
        self.controller.set_job(self.current_job)

        try:
            self.controller.ffmpeg_wrapper.detect_binaries()
            meta = self.controller.ffmpeg_wrapper.inspect_video(video_path)
            self.current_job.source.update(meta)
            self.current_job.save()

            self.metadata_lbl.setText(
                f"Resolution: {meta['width']}x{meta['height']} | "
                f"Duration: {meta['duration']:.2f}s | "
                f"FPS: {meta['fps']:.2f} | Video Codec: {meta['video_codec']}"
            )
            
            preview_png = os.path.join(self.current_job.paths["logs"], "preview.png")
            if extract_preview(video_path, preview_png):
                self.crop_selector.set_preview_image(preview_png)
            else:
                self.crop_selector.clear_rects()

        except Exception as e:
            QMessageBox.critical(self, "Inspection Error", f"Failed to inspect video: {str(e)}")
            self.metadata_lbl.setText("Failed to inspect video.")

        # Enable/Disable Retranscribe button
        is_completed = self.current_job.get_stage_status(STAGE_REVIEW_READY) == "completed"
        self.retranscribe_btn.setEnabled(is_completed)

    def _reload_recent_jobs(self):
        self.recent_jobs_combo.clear()
        self.recent_jobs_combo.addItem("New Job / Select Video")
        
        jobs_dir = os.path.join(self.config_manager.data_dir, "jobs")
        if not os.path.exists(jobs_dir):
            return

        for job_id in os.listdir(jobs_dir):
            manifest_p = os.path.join(jobs_dir, job_id, "manifest.json")
            if os.path.exists(manifest_p):
                man = FileManager.read_json_safe(manifest_p)
                if isinstance(man, dict):
                    title = man.get("title", job_id)
                    source_path = man.get("source", {}).get("original_path", "")
                    self.recent_jobs_combo.addItem(f"{title} ({job_id[:8]})", (job_id, source_path))

    def _on_recent_job_changed(self, index):
        if index <= 0:
            self.retranscribe_btn.setEnabled(False)
            return
        
        job_id, source_path = self.recent_jobs_combo.itemData(index)
        self.current_job = Job(self.config_manager.data_dir, job_id=job_id)
        self.controller.set_job(self.current_job)
        self.undo_stack = [] # Reset undo stack on job load
        
        # Load source path to edit
        self.video_path_edit.setText(source_path)
        
        # Load Whisper Settings
        w_settings = self.current_job.settings.get("whisper", {})
        self.glossary_edit.setText(w_settings.get("glossary", ""))
        
        # Set profile
        profile = w_settings.get("profile", "fast")
        p_idx = self.profile_combo.findText(profile.title())
        if p_idx >= 0:
            self.profile_combo.setCurrentIndex(p_idx)
            
        # Set threads
        self.threads_spin.setValue(w_settings.get("threads", 8))
        
        # Set VAD settings
        self.vad_chk.setChecked(w_settings.get("vad_enabled", False))
        self.vad_model_edit.setText(w_settings.get("vad_model", ""))
        self.vad_thresh_spin.setValue(w_settings.get("vad_threshold", 0.50))
        self.vad_spd_spin.setValue(w_settings.get("vad_min_speech_duration_ms", 250))
        self.vad_sil_spin.setValue(w_settings.get("vad_min_silence_duration_ms", 100))
        
        # Load presets
        preset = self.current_job.settings.get("preset", "balanced")
        if preset in ["standard_lecture", "webcam_lecture", "whiteboard_lecture", "software_demo"]:
            preset = "balanced"
        idx = self.preset_combo.findText(preset.title())
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        else:
            self.preset_combo.setCurrentIndex(1) # Default to Balanced

        # Restore crop selector geometry
        sd = self.current_job.settings.get("slide_detection", {})
        crop = sd.get("crop_region", {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})
        self.crop_selector.crop_rect = QRectF(crop["x"], crop["y"], crop["width"], crop["height"])
        
        ignores = sd.get("ignore_masks", [])
        self.crop_selector.ignore_rects = [
            QRectF(i["x"], i["y"], i["width"], i["height"]) for i in ignores
        ]

        # Load preview frame if it exists
        preview_png = os.path.join(self.current_job.paths["logs"], "preview.png")
        if os.path.exists(preview_png):
            self.crop_selector.set_preview_image(preview_png)
        elif os.path.exists(source_path):
            if extract_preview(source_path, preview_png):
                self.crop_selector.set_preview_image(preview_png)
        else:
            self.crop_selector.clear_rects()

        # Update metadata display
        meta = self.current_job.source
        if meta:
            self.metadata_lbl.setText(
                f"Resolution: {meta.get('width', 0)}x{meta.get('height', 0)} | "
                f"Duration: {meta.get('duration', 0.0):.2f}s"
            )
        else:
            self.metadata_lbl.setText("No metadata available.")

        # Enable/Disable Retranscribe button
        is_completed = self.current_job.get_stage_status(STAGE_REVIEW_READY) == "completed"
        self.retranscribe_btn.setEnabled(is_completed)

        # If already review ready, jump directly to Review view!
        if is_completed:
            self._load_review_data()
            self.stack.setCurrentIndex(2)

    def _start_processing(self):
        if not self.current_job:
            QMessageBox.warning(self, "No video", "Please select a lecture video first.")
            return

        w_exe = self.whisper_exe_edit.text().strip()
        w_model = self.whisper_model_edit.text().strip()
        
        if not w_exe or not os.path.exists(w_exe):
            QMessageBox.warning(self, "Whisper Executable", "Please select a valid Whisper executable path.")
            return
        if not w_model or not os.path.exists(w_model):
            QMessageBox.warning(self, "Whisper Model", "Please select a valid Whisper model path.")
            return

        # VAD model check
        if self.vad_chk.isChecked():
            v_model = self.vad_model_edit.text().strip()
            if not v_model or not os.path.exists(v_model):
                QMessageBox.warning(self, "VAD Model", "VAD is enabled, but the VAD model file is missing.")
                return

        # Save settings first
        preset_name = self.preset_combo.currentText().lower().replace(" / ", "_").replace(" ", "_")
        self.current_job.settings["preset"] = preset_name
        
        # Save Whisper settings
        w_settings = self.current_job.settings["whisper"]
        w_settings["glossary"] = self.glossary_edit.text().strip()
        w_settings["model"] = w_model
        w_settings["profile"] = self.profile_combo.currentText().lower()
        w_settings["threads"] = self.threads_spin.value()
        w_settings["vad_enabled"] = self.vad_chk.isChecked()
        w_settings["vad_model"] = self.vad_model_edit.text().strip()
        w_settings["vad_threshold"] = self.vad_thresh_spin.value()
        w_settings["vad_min_speech_duration_ms"] = self.vad_spd_spin.value()
        w_settings["vad_min_silence_duration_ms"] = self.vad_sil_spin.value()

        self.current_job.settings["slide_detection"]["crop_region"] = {
            "x": self.crop_selector.crop_rect.x(),
            "y": self.crop_selector.crop_rect.y(),
            "width": self.crop_selector.crop_rect.width(),
            "height": self.crop_selector.crop_rect.height()
        }
        self.current_job.settings["slide_detection"]["ignore_masks"] = [
            {"x": r.x(), "y": r.y(), "width": r.width(), "height": r.height()}
            for r in self.crop_selector.ignore_rects
        ]
        self.current_job.save()

        # Update config manager paths
        self.config_manager.set("whisper_exe", w_exe)
        self.config_manager.set("whisper_model", w_model)

        # Switch to processing stack
        self.log_text.clear()
        self.stack.setCurrentIndex(1)
        
        # Start pipeline
        self.controller.run_pipeline()

    def _run_detection_preview(self):
        if not self.current_job:
            QMessageBox.warning(self, "No video", "Please select a lecture video first.")
            return

        crop_region = {
            "x": self.crop_selector.crop_rect.x(),
            "y": self.crop_selector.crop_rect.y(),
            "width": self.crop_selector.crop_rect.width(),
            "height": self.crop_selector.crop_rect.height()
        }
        ignore_masks = [
            {"x": r.x(), "y": r.y(), "width": r.width(), "height": r.height()}
            for r in self.crop_selector.ignore_rects
        ]
        
        current_preset = self.preset_combo.currentText().lower()
        
        dialog = DetectionPreviewDialog(
            parent=self,
            video_path=self.current_job.manifest["source"]["original_path"],
            crop_region=crop_region,
            ignore_masks=ignore_masks,
            current_preset=current_preset,
            job_paths=self.current_job.paths
        )
        dialog.exec()

    def _cancel_processing(self):
        self.controller.cancel()
        self.stack.setCurrentIndex(0)

    def _refresh_diagnostics(self):
        diag = self.config_manager.check_diagnostics()
        ok_style = "font-size: 11px; padding: 2px 6px; color: #4CAF50;"
        miss_style = "font-size: 11px; padding: 2px 6px; color: #f44336; font-weight: bold;"

        def _fmt(key, label, d):
            entry = d[key]
            if entry["valid"]:
                return f"{label}: OK", ok_style
            short = os.path.basename(entry["path"]) if entry["path"] else "not found"
            return f"{label}: {short}", miss_style

        text, style = _fmt("ffmpeg", "FFmpeg", diag)
        self.diag_ffmpeg_lbl.setText(text)
        self.diag_ffmpeg_lbl.setStyleSheet(style)

        text, style = _fmt("ffprobe", "FFprobe", diag)
        self.diag_ffprobe_lbl.setText(text)
        self.diag_ffprobe_lbl.setStyleSheet(style)

        text, style = _fmt("whisper_model", "Model", diag)
        self.diag_model_lbl.setText(text)
        self.diag_model_lbl.setStyleSheet(style)

        text, style = _fmt("data_dir", "Data Dir", diag)
        self.diag_data_lbl.setText(text)
        self.diag_data_lbl.setStyleSheet(style)

        w_exe = self.whisper_exe_edit.text().strip()
        
        # Disable buttons temporarily during checks
        self.start_btn.setEnabled(False)
        self.retranscribe_btn.setEnabled(False)
        self.start_btn.setStyleSheet("background-color: #999; color: #666; font-weight: bold; font-size: 14px; padding: 10px;")

        if not w_exe or not os.path.exists(w_exe):
            self.diag_whisper_lbl.setText("Whisper: not found")
            self.diag_whisper_lbl.setStyleSheet(miss_style)
            self._on_whisper_detection_finished(w_exe, {
                "version": "Unknown",
                "backend": "CPU",
                "flags": {"-oj", "-osrt", "-otxt"}
            })
        else:
            self.diag_whisper_lbl.setText("Whisper: checking...")
            self.diag_whisper_lbl.setStyleSheet("font-size: 11px; padding: 2px 6px; color: #2196F3;")
            self.whisper_detector.detect(w_exe)

    def _on_whisper_detection_finished(self, exe_path, caps):
        self.current_whisper_caps = caps
        
        if exe_path != self.whisper_exe_edit.text().strip():
            return

        diag = self.config_manager.check_diagnostics()
        ok_style = "font-size: 11px; padding: 2px 6px; color: #4CAF50;"
        miss_style = "font-size: 11px; padding: 2px 6px; color: #f44336; font-weight: bold;"

        if diag["whisper_cli"]["valid"]:
            self.diag_whisper_lbl.setText("Whisper: OK")
            self.diag_whisper_lbl.setStyleSheet(ok_style)
        else:
            short = os.path.basename(exe_path) if exe_path else "not found"
            self.diag_whisper_lbl.setText(f"Whisper: {short}")
            self.diag_whisper_lbl.setStyleSheet(miss_style)

        w_model = self.whisper_model_edit.text().strip()
        m_name = os.path.basename(w_model) if w_model else "None selected"
        m_size = "missing"
        if w_model and os.path.exists(w_model):
            m_size = f"{os.path.getsize(w_model) / (1024*1024):.1f} MB"
            
        w_version = caps["version"]
        w_backend = caps["backend"]
        threads = self.threads_spin.value()
        
        self.whisper_model_info_lbl.setText(
            f"Model: {m_name} ({m_size}) | whisper.cpp v{w_version} ({w_backend}) | Threads: {threads}"
        )

        self._validate_vad_model()

        deps_ok = diag["ffmpeg"]["valid"] and diag["whisper_cli"]["valid"] and diag["whisper_model"]["valid"]
        if self.vad_chk.isChecked():
            v_model = self.vad_model_edit.text().strip()
            if not v_model or not os.path.exists(v_model):
                deps_ok = False

        self.start_btn.setEnabled(deps_ok)
        if self.current_job and self.current_job.get_stage_status(STAGE_REVIEW_READY) == "completed":
            self.retranscribe_btn.setEnabled(deps_ok)
        else:
            self.retranscribe_btn.setEnabled(False)

        if deps_ok:
            self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px; padding: 10px;")
        else:
            self.start_btn.setStyleSheet("background-color: #999; color: #666; font-weight: bold; font-size: 14px; padding: 10px;")

    # 5. CONTROLLER SIGNAL HANDLERS
    def _on_stage_started(self, stage):
        self.stage_lbl.setText(f"Stage: {stage}")
        for s, lbl in self.stages_labels.items():
            if s == stage:
                lbl.setStyleSheet("color: #2196F3; font-weight: bold; margin: 5px;")
            else:
                lbl.setStyleSheet("color: #777; font-weight: bold; margin: 5px;")
        self.progress_bar.setValue(0)

    def _on_stage_progress(self, stage, percent):
        self.progress_bar.setValue(percent)

    def _on_stage_log(self, stage, msg):
        self.log_text.insertPlainText(msg)
        self.log_text.ensureCursorVisible()

    def _on_stage_finished(self, stage, success, error_msg):
        lbl = self.stages_labels.get(stage)
        if lbl:
            if success:
                lbl.setStyleSheet("color: #4CAF50; font-weight: bold; margin: 5px;")
            else:
                lbl.setStyleSheet("color: #f44336; font-weight: bold; margin: 5px;")

    def _on_pipeline_completed(self):
        QMessageBox.information(self, "Success", "Slide detection & transcription finished successfully.")
        self._load_review_data()
        self.stack.setCurrentIndex(2)
        self._reload_recent_jobs()

    def _on_pipeline_failed(self, error_msg):
        QMessageBox.critical(self, "Pipeline Error", f"Processing failed: {error_msg}\nCheck logs for more details.")
        self.stack.setCurrentIndex(0)

    # 6. REVIEW & EXPORT VIEWS SLOTS
    def _init_shortcuts(self):
        # Global shortcuts for the Slide Review workspace
        self.shortcut_delete = QShortcut(QKeySequence("Delete"), self)
        self.shortcut_delete.activated.connect(self._on_delete_shortcut)
        
        self.shortcut_r = QShortcut(QKeySequence("R"), self)
        self.shortcut_r.activated.connect(self._on_r_shortcut)
        
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self._undo_review_action)
        
        self.shortcut_copy = QShortcut(QKeySequence("Ctrl+C"), self)
        self.shortcut_copy.activated.connect(self._on_ctrl_c_shortcut)
        
        self.shortcut_focus_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_focus_search.activated.connect(self._focus_search)
        
        self.shortcut_save_corrections = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save_corrections.activated.connect(self._save_corrections)
        
        self.shortcut_f3 = QShortcut(QKeySequence("F3"), self)
        self.shortcut_f3.activated.connect(self._search_next)
        
        self.shortcut_shift_f3 = QShortcut(QKeySequence("Shift+F3"), self)
        self.shortcut_shift_f3.activated.connect(self._search_prev)

    def _load_review_data(self):
        self.slides_view.clear()
        self.preview_lbl.setText("Select a slide to preview")
        self.slide_info_lbl.setText("Timestamp: -")
        self.selected_count_lbl.setText("Selected: 0")

        # Load raw segments
        self.raw_segments = []
        transcript_json_path = os.path.join(self.current_job.paths["root"], "transcript", "raw.json")
        transcript_data = FileManager.read_json_safe(transcript_json_path, {})
        if isinstance(transcript_data, dict):
            transcription = transcript_data.get("result", {}).get("transcription", [])
            if not transcription and "transcription" in transcript_data:
                transcription = transcript_data["transcription"]
                
            for i, seg in enumerate(transcription):
                offsets = seg.get("offsets", {})
                start_sec = offsets.get("from", 0) / 1000.0
                end_sec = offsets.get("to", 0) / 1000.0
                text = seg.get("text", "").strip()
                self.raw_segments.append({
                    "id": i + 1,
                    "start": start_sec,
                    "end": end_sec,
                    "text": text
                })
        
        # Fallback to txt parsing if raw.json is empty
        if not self.raw_segments:
            raw_txt_path = os.path.join(self.current_job.paths["root"], "transcript", "raw.txt")
            if os.path.exists(raw_txt_path):
                with open(raw_txt_path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("[") and "->" in line:
                            try:
                                parts = line.split("]", 1)
                                ts_part = parts[0][1:]
                                text_part = parts[1].strip()
                                t1, t2 = ts_part.split("->")
                                def to_sec(s):
                                    s = s.strip()
                                    h, m, sec = s.split(":")
                                    return int(h)*3600 + int(m)*60 + float(sec)
                                start_sec = to_sec(t1)
                                end_sec = to_sec(t2)
                                self.raw_segments.append({
                                    "id": i + 1,
                                    "start": start_sec,
                                    "end": end_sec,
                                    "text": text_part
                                })
                            except Exception:
                                pass

        # Sort segments
        self.raw_segments.sort(key=lambda s: s["start"])

        # Load corrected segments mapping
        edited_path = os.path.join(self.current_job.paths["transcript"], "edited.json")
        self.edited_data = FileManager.read_json_safe(edited_path, {})

        # Load aligned segments
        aligned_json_path = os.path.join(self.current_job.paths["root"], "transcript", "aligned.json")
        self.aligned_data = FileManager.read_json_safe(aligned_json_path, [])

        # Load candidates
        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])

        candidates_dir = self.current_job.paths["candidates"]

        for cand in candidates:
            img_filename = cand.get("image_filename", "")
            img_p = os.path.join(candidates_dir, img_filename)
            
            icon = QIcon()
            if os.path.exists(img_p):
                icon = QIcon(img_p)

            ts_formatted = cand.get("timestamp_formatted", "00:00:00.000")
            decision = cand.get("decision", "accepted")
            
            lbl_text = f"@{ts_formatted}"
            if decision == "rejected":
                lbl_text += " [Rejected]"
                
            item = QListWidgetItem(icon, lbl_text)
            item.setData(Qt.ItemDataRole.UserRole, cand)

            # Clearly distinguish accepted vs rejected slides
            if decision == "rejected":
                item.setBackground(QBrush(QColor(255, 235, 235)))
                item.setForeground(QBrush(QColor(150, 0, 0)))
            else:
                item.setBackground(QBrush(QColor(235, 255, 235)))
                item.setForeground(QBrush(QColor(0, 100, 0)))

            self.slides_view.addItem(item)

    def _on_slides_selection_changed(self):
        selected_items = self.slides_view.selectedItems()
        self.selected_count_lbl.setText(f"Selected: {len(selected_items)}")
        
        if not selected_items:
            self.preview_lbl.setText("Select a slide to preview")
            self.slide_info_lbl.setText("Timestamp: -")
            self.transcript_table.setRowCount(0)
            return
            
        primary_item = selected_items[0]
        cand = primary_item.data(Qt.ItemDataRole.UserRole)
        self._show_slide_preview(cand)
        self._update_transcript_for_selected_slides()

    def _show_slide_preview(self, cand):
        img_filename = cand.get("image_filename", "")
        img_p = os.path.join(self.current_job.paths["candidates"], img_filename)
        
        if os.path.exists(img_p):
            pix = QPixmap(img_p)
            scaled = pix.scaled(self.preview_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_lbl.setPixmap(scaled)
        else:
            self.preview_lbl.setText("Image missing.")

        self.slide_info_lbl.setText(
            f"Timestamp: {cand.get('timestamp_formatted', '00:00:00')} | Frame: {cand.get('frame_number', 0)}"
        )

    def _update_transcript_for_selected_slides(self):
        selected_items = self.slides_view.selectedItems()
        if not selected_items:
            self.transcript_table.setRowCount(0)
            return

        selected_cands = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        selected_cands.sort(key=lambda c: c.get("timestamp_seconds", 0.0))
        
        video_duration = 0.0
        if self.current_job and self.current_job.source:
            video_duration = self.current_job.source.get("duration", 0.0)

        # Get list of all accepted slides for interval boundaries
        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        accepted_slides = [c for c in candidates if c.get("decision") == "accepted"]
        accepted_slides.sort(key=lambda s: s.get("timestamp_seconds", 0.0))
        
        intervals = []
        for cand in selected_cands:
            start = cand.get("timestamp_seconds", 0.0)
            end = video_duration
            for acc in accepted_slides:
                if acc.get("timestamp_seconds", 0.0) > start:
                    end = acc.get("timestamp_seconds", 0.0)
                    break
            intervals.append((start, max(start, end)))
            
        edited_path = os.path.join(self.current_job.paths["transcript"], "edited.json")
        self.edited_data = FileManager.read_json_safe(edited_path, {})
        
        matched_segments = []
        seen_seg_ids = set()
        
        for start, end in intervals:
            for seg in self.raw_segments:
                seg_start = seg["start"]
                seg_end = seg["end"]
                overlap = max(0.0, min(seg_end, end) - max(seg_start, start))
                if overlap > 0.0 or (seg_start <= (start + end)/2.0 <= seg_end):
                    if seg["id"] not in seen_seg_ids:
                        seen_seg_ids.add(seg["id"])
                        matched_segments.append(seg)
                        
        matched_segments.sort(key=lambda s: s["start"])
        
        self.transcript_table.setRowCount(len(matched_segments))
        for row, seg in enumerate(matched_segments):
            seg_id = seg["id"]
            t1 = datetime_from_seconds(seg["start"])
            t2 = datetime_from_seconds(seg["end"])
            
            # Non-editable timestamp item
            self.transcript_table.setItem(row, 0, QTableWidgetItem(f"{t1} -> {t2}"))
            
            text_edit = QTextEdit()
            text_edit.setAcceptRichText(False)
            current_text = self.edited_data.get(str(seg_id), seg["text"])
            text_edit.setPlainText(current_text)
            text_edit.setMinimumHeight(40)
            text_edit.setMaximumHeight(80)
            text_edit.setProperty("segment_id", seg_id)
            
            is_edited = str(seg_id) in self.edited_data
            self._style_segment_edit(text_edit, is_edited)
            text_edit.textChanged.connect(self._on_segment_text_changed)
            
            self.transcript_table.setCellWidget(row, 1, text_edit)
            
            reset_btn = QPushButton("Reset")
            reset_btn.setProperty("segment_id", seg_id)
            reset_btn.setProperty("text_edit", text_edit)
            reset_btn.clicked.connect(self._reset_segment_clicked)
            self.transcript_table.setCellWidget(row, 2, reset_btn)
            
        for r in range(len(matched_segments)):
            self.transcript_table.setRowHeight(r, 60)

    def _style_segment_edit(self, widget, is_edited):
        if is_edited:
            widget.setStyleSheet("background-color: #e8f5e9; border: 1px solid #c8e6c9; color: #1b5e20; font-weight: bold;")
        else:
            widget.setStyleSheet("background-color: white; border: 1px solid #ccc; color: black; font-weight: normal;")

    def _on_segment_text_changed(self):
        text_edit = self.sender()
        if not text_edit:
            return
        seg_id = text_edit.property("segment_id")
        raw_text = ""
        for seg in self.raw_segments:
            if seg["id"] == seg_id:
                raw_text = seg["text"]
                break
        current_text = text_edit.toPlainText().strip()
        is_edited = (current_text != raw_text)
        self._style_segment_edit(text_edit, is_edited)

    def _reset_segment_clicked(self):
        btn = self.sender()
        if not btn:
            return
        seg_id = btn.property("segment_id")
        text_edit = btn.property("text_edit")
        if not text_edit:
            return
            
        raw_text = ""
        for seg in self.raw_segments:
            if seg["id"] == seg_id:
                raw_text = seg["text"]
                break
                
        text_edit.setPlainText(raw_text)
        self._style_segment_edit(text_edit, False)
        
        if str(seg_id) in self.edited_data:
            del self.edited_data[str(seg_id)]
            edited_path = os.path.join(self.current_job.paths["transcript"], "edited.json")
            FileManager.write_json_atomic(edited_path, self.edited_data)
            self.transcript_status_lbl.setText("Segment reset to original.")
            QTimer.singleShot(2000, lambda: self.transcript_status_lbl.setText(""))

    def _save_corrections(self):
        if not self.current_job:
            return
            
        for row in range(self.transcript_table.rowCount()):
            text_edit = self.transcript_table.cellWidget(row, 1)
            if not text_edit:
                continue
            seg_id = text_edit.property("segment_id")
            text = text_edit.toPlainText().strip()
            
            raw_text = ""
            for seg in self.raw_segments:
                if seg["id"] == seg_id:
                    raw_text = seg["text"]
                    break
                    
            if text != raw_text:
                self.edited_data[str(seg_id)] = text
            else:
                if str(seg_id) in self.edited_data:
                    del self.edited_data[str(seg_id)]
                    
        edited_path = os.path.join(self.current_job.paths["transcript"], "edited.json")
        FileManager.write_json_atomic(edited_path, self.edited_data)
        
        self.transcript_status_lbl.setText("Corrections saved successfully.")
        QTimer.singleShot(3000, lambda: self.transcript_status_lbl.setText(""))

    def _on_delete_shortcut(self):
        if self.stack.currentIndex() == 2 and self.slides_view.hasFocus():
            self._bulk_reject()

    def _on_r_shortcut(self):
        if self.stack.currentIndex() == 2 and self.slides_view.hasFocus():
            self._bulk_restore()

    def _on_ctrl_c_shortcut(self):
        if self.stack.currentIndex() == 2:
            focused = self.focusWidget()
            if isinstance(focused, (QLineEdit, QTextEdit)):
                if isinstance(focused, QLineEdit) and focused.hasSelectedText():
                    return
                if isinstance(focused, QTextEdit):
                    cursor = focused.textCursor()
                    if cursor.hasSelection():
                        return
            self._copy_current_transcript()

    def _focus_search(self):
        if self.stack.currentIndex() == 2:
            self.search_input.setFocus()
            self.search_input.selectAll()

    def _on_search_text_changed(self):
        self.current_search_match = -1

    def _search_next(self):
        self._do_search(forward=True)

    def _search_prev(self):
        self._do_search(forward=False)

    def _do_search(self, forward=True):
        if self.stack.currentIndex() != 2:
            return
        query = self.search_input.text().strip().lower()
        if not query:
            return

        matches = []
        for row in range(self.transcript_table.rowCount()):
            text_edit = self.transcript_table.cellWidget(row, 1)
            if text_edit and query in text_edit.toPlainText().lower():
                matches.append(row)

        if not matches:
            return

        if forward:
            self.current_search_match += 1
            if self.current_search_match >= len(matches) or self.current_search_match < 0:
                self.current_search_match = 0
        else:
            self.current_search_match -= 1
            if self.current_search_match < 0 or self.current_search_match >= len(matches):
                self.current_search_match = len(matches) - 1

        matched_row = matches[self.current_search_match]
        self.transcript_table.scrollToItem(self.transcript_table.item(matched_row, 0))
        
        text_edit = self.transcript_table.cellWidget(matched_row, 1)
        if text_edit:
            text_edit.setFocus()
            cursor = text_edit.textCursor()
            full_text = text_edit.toPlainText().lower()
            idx = full_text.find(query)
            if idx >= 0:
                cursor.setPosition(idx)
                cursor.setPosition(idx + len(query), cursor.MoveMode.KeepAnchor)
                text_edit.setTextCursor(cursor)

    def _copy_current_transcript(self):
        selected_items = self.slides_view.selectedItems()
        if not selected_items:
            return

        selected_cands = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        selected_cands.sort(key=lambda c: c.get("timestamp_seconds", 0.0))
        cand = selected_cands[0]
        start = cand.get("timestamp_seconds", 0.0)
        
        video_duration = 0.0
        if self.current_job and self.current_job.source:
            video_duration = self.current_job.source.get("duration", 0.0)

        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        accepted_slides = [c for c in candidates if c.get("decision") == "accepted"]
        accepted_slides.sort(key=lambda s: s.get("timestamp_seconds", 0.0))
        
        end = video_duration
        for acc in accepted_slides:
            if acc.get("timestamp_seconds", 0.0) > start:
                end = acc.get("timestamp_seconds", 0.0)
                break
                
        text_lines = []
        for seg in self.raw_segments:
            seg_start = seg["start"]
            seg_end = seg["end"]
            overlap = max(0.0, min(seg_end, end) - max(seg_start, start))
            if overlap > 0.0 or (seg_start <= (start + end)/2.0 <= seg_end):
                text = self.edited_data.get(str(seg["id"]), seg["text"])
                t_part = ""
                if self.timestamps_chk.isChecked():
                    t1 = datetime_from_seconds(seg["start"])
                    t2 = datetime_from_seconds(seg["end"])
                    t_part = f"[{t1} -> {t2}] "
                text_lines.append(f"{t_part}{text}")

        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText("\n".join(text_lines))
        self.statusBar().showMessage("Current slide transcript copied to clipboard.", 2000)

    def _copy_selected_transcripts(self):
        selected_items = self.slides_view.selectedItems()
        if not selected_items:
            return

        selected_cands = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        selected_cands.sort(key=lambda c: c.get("timestamp_seconds", 0.0))
        
        video_duration = 0.0
        if self.current_job and self.current_job.source:
            video_duration = self.current_job.source.get("duration", 0.0)

        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        accepted_slides = [c for c in candidates if c.get("decision") == "accepted"]
        accepted_slides.sort(key=lambda s: s.get("timestamp_seconds", 0.0))
        
        intervals = []
        for cand in selected_cands:
            start = cand.get("timestamp_seconds", 0.0)
            end = video_duration
            for acc in accepted_slides:
                if acc.get("timestamp_seconds", 0.0) > start:
                    end = acc.get("timestamp_seconds", 0.0)
                    break
            intervals.append((start, max(start, end)))
            
        matched_segments = []
        seen_seg_ids = set()
        for start, end in intervals:
            for seg in self.raw_segments:
                seg_start = seg["start"]
                seg_end = seg["end"]
                overlap = max(0.0, min(seg_end, end) - max(seg_start, start))
                if overlap > 0.0 or (seg_start <= (start + end)/2.0 <= seg_end):
                    if seg["id"] not in seen_seg_ids:
                        seen_seg_ids.add(seg["id"])
                        matched_segments.append(seg)
                        
        matched_segments.sort(key=lambda s: s["start"])
        
        text_lines = []
        for seg in matched_segments:
            text = self.edited_data.get(str(seg["id"]), seg["text"])
            t_part = ""
            if self.timestamps_chk.isChecked():
                t1 = datetime_from_seconds(seg["start"])
                t2 = datetime_from_seconds(seg["end"])
                t_part = f"[{t1} -> {t2}] "
            text_lines.append(f"{t_part}{text}")

        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText("\n".join(text_lines))
        self.statusBar().showMessage("Selected slides' transcripts copied to clipboard.", 2000)

    def _copy_full_transcript(self):
        text_lines = []
        for seg in self.raw_segments:
            text = self.edited_data.get(str(seg["id"]), seg["text"])
            t_part = ""
            if self.timestamps_chk.isChecked():
                t1 = datetime_from_seconds(seg["start"])
                t2 = datetime_from_seconds(seg["end"])
                t_part = f"[{t1} -> {t2}] "
            text_lines.append(f"{t_part}{text}")

        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText("\n".join(text_lines))
        self.statusBar().showMessage("Full transcript copied to clipboard.", 2000)

    def _save_candidates_snapshot(self):
        if not self.current_job:
            return
        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        snapshot_path = os.path.join(self.current_job.paths["root"], "candidates.json.snapshot")
        if os.path.exists(candidates_path):
            try:
                shutil.copy2(candidates_path, snapshot_path)
            except Exception:
                pass

    def _push_undo_state(self):
        if not self.current_job:
            return
        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        import copy
        self.undo_stack.append(copy.deepcopy(candidates))

    def _undo_review_action(self):
        if not self.current_job or not self.undo_stack:
            self.statusBar().showMessage("Nothing to undo.", 2000)
            return
        
        previous_candidates = self.undo_stack.pop()
        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        FileManager.write_json_atomic(candidates_path, previous_candidates)
        
        self._load_review_data()
        self.statusBar().showMessage("Undo successful.", 2000)

    def _bulk_keep(self):
        selected_items = self.slides_view.selectedItems()
        if not selected_items:
            return

        if len(selected_items) > 20:
            reply = QMessageBox.question(self, "Confirm Bulk Keep", f"Keep selected {len(selected_items)} slides?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._save_candidates_snapshot()
        self._push_undo_state()

        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])

        selected_frames = [item.data(Qt.ItemDataRole.UserRole)["frame_number"] for item in selected_items]
        for c in candidates:
            if c["frame_number"] in selected_frames:
                c["decision"] = "accepted"

        FileManager.write_json_atomic(candidates_path, candidates)
        self._load_review_data()

    def _bulk_reject(self):
        selected_items = self.slides_view.selectedItems()
        if not selected_items:
            return

        if len(selected_items) > 20:
            reply = QMessageBox.question(self, "Confirm Bulk Reject", f"Reject selected {len(selected_items)} slides?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._save_candidates_snapshot()
        self._push_undo_state()

        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])

        selected_frames = [item.data(Qt.ItemDataRole.UserRole)["frame_number"] for item in selected_items]
        for c in candidates:
            if c["frame_number"] in selected_frames:
                c["decision"] = "rejected"

        FileManager.write_json_atomic(candidates_path, candidates)
        self._load_review_data()

    def _bulk_restore(self):
        selected_items = self.slides_view.selectedItems()
        if not selected_items:
            return

        if len(selected_items) > 20:
            reply = QMessageBox.question(self, "Confirm Bulk Restore", f"Restore selected {len(selected_items)} slides?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._save_candidates_snapshot()
        self._push_undo_state()

        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])

        selected_frames = [item.data(Qt.ItemDataRole.UserRole)["frame_number"] for item in selected_items]
        for c in candidates:
            if c["frame_number"] in selected_frames:
                c["decision"] = "accepted"

        FileManager.write_json_atomic(candidates_path, candidates)
        self._load_review_data()

    def _find_model_file(self, filename):
        paths = [
            os.path.join(self.config_manager.app_dir, "models", filename),
            os.path.join(os.path.dirname(self.config_manager.app_dir), "models", filename),
            os.path.join(self.config_manager.data_dir, "models", filename),
        ]
        for p in paths:
            if os.path.exists(p):
                return os.path.abspath(p)
        return None

    def _on_profile_changed(self, index):
        if index == 0:  # Fast
            self.threads_spin.setValue(4)
            rec_name = "ggml-base.en.bin"
            rec_path = self._find_model_file(rec_name)
            if rec_path:
                current_model = self.whisper_model_edit.text().strip()
                if not current_model or os.path.basename(current_model) != rec_name:
                    reply = QMessageBox.question(
                        self, "Select Recommended Model",
                        f"Fast profile recommends '{rec_name}'. A matching model file was found.\nWould you like to select it?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.whisper_model_edit.setText(rec_path)
            else:
                self.whisper_model_info_lbl.setText(
                    f"Recommendation: Please download and select '{rec_name}' for Fast profile."
                )
        elif index == 1:  # Accurate
            self.threads_spin.setValue(8)
            rec_name = "ggml-small.en.bin"
            rec_path = self._find_model_file(rec_name)
            if rec_path:
                current_model = self.whisper_model_edit.text().strip()
                if not current_model or os.path.basename(current_model) != rec_name:
                    reply = QMessageBox.question(
                        self, "Select Recommended Model",
                        f"Accurate profile recommends '{rec_name}'. A matching model file was found.\nWould you like to select it?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.whisper_model_edit.setText(rec_path)
            else:
                self.whisper_model_info_lbl.setText(
                    f"Recommendation: Please download and select '{rec_name}' for Accurate profile."
                )

    def closeEvent(self, event):
        self.whisper_detector.cancel()
        super().closeEvent(event)

    def _on_vad_toggled(self, checked):
        self.vad_model_label.setEnabled(checked)
        self.vad_model_edit.setEnabled(checked)
        self.vad_browse_btn.setEnabled(checked)
        self.advanced_vad_btn.setEnabled(checked)
        if not checked:
            self.vad_warning_lbl.setVisible(False)
        else:
            self._validate_vad_model()
        self._refresh_diagnostics()

    def _browse_vad_model(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select VAD Model", "", "Model files (*.bin)")
        if file_path:
            self.vad_model_edit.setText(file_path)

    def _validate_vad_model(self):
        if not self.vad_chk.isChecked():
            self.vad_warning_lbl.setVisible(False)
            return

        v_model = self.vad_model_edit.text().strip()
        if not v_model:
            self.vad_warning_lbl.setText("Missing VAD Model path.")
            self.vad_warning_lbl.setVisible(True)
        elif not os.path.exists(v_model):
            self.vad_warning_lbl.setText("VAD Model file not found.")
            self.vad_warning_lbl.setVisible(True)
        else:
            self.vad_warning_lbl.setVisible(False)

    def _toggle_advanced_vad(self, checked):
        self.advanced_vad_widget.setVisible(checked)
        self.advanced_vad_btn.setText("Hide Advanced VAD Settings" if checked else "Show Advanced VAD Settings")

    def _archive_current_job(self):
        if not self.current_job:
            return
        reply = QMessageBox.question(self, "Archive Job", f"Are you sure you want to archive job '{self.current_job.manifest.get('title')}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                FileManager.archive_job(self.config_manager.data_dir, self.current_job.job_id)
                self.current_job = None
                self.controller.set_job(None)
                self.video_path_edit.clear()
                self.glossary_edit.clear()
                self.metadata_lbl.setText("No video loaded.")
                self._reload_recent_jobs()
                self.recent_jobs_combo.setCurrentIndex(0)
                QMessageBox.information(self, "Archived", "Job archived successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to archive job: {str(e)}")

    def _restore_archived_job(self):
        dlg = RestoreDialog(self.config_manager.data_dir, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            job_id = dlg.get_selected_job_id()
            if job_id:
                try:
                    FileManager.restore_job(self.config_manager.data_dir, job_id)
                    self._reload_recent_jobs()
                    # Find and select the restored job
                    for i in range(self.recent_jobs_combo.count()):
                        data = self.recent_jobs_combo.itemData(i)
                        if data and data[0] == job_id:
                            self.recent_jobs_combo.setCurrentIndex(i)
                            break
                    QMessageBox.information(self, "Restored", "Job restored successfully.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to restore job: {str(e)}")

    def _export_job_archive(self):
        if not self.current_job:
            return
        default_name = self.current_job.manifest.get("title", "job_archive") + "_archive.zip"
        zip_path, _ = QFileDialog.getSaveFileName(self, "Export Job Archive", default_name, "Zip Files (*.zip)")
        if zip_path:
            try:
                FileManager.export_job_archive(self.current_job.paths["root"], zip_path)
                QMessageBox.information(self, "Success", "Job archive exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export archive: {str(e)}")

    def _retranscribe_only_workflow(self):
        if not self.current_job:
            return
            
        t_dir = self.current_job.paths["transcript"]
        edited_path = os.path.join(t_dir, "edited.json")
        
        if os.path.exists(edited_path):
            reply = QMessageBox.question(self, "Overwrite Transcript Corrections", 
                                         "An active corrected transcript exists. Overwriting it will replace it. Do you want to continue?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Versioned backup
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                shutil.copy2(edited_path, os.path.join(t_dir, f"edited.bak.{timestamp}.json"))
                os.remove(edited_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to backup existing transcript: {str(e)}")
                return
                
        raw_json_path = os.path.join(t_dir, "raw.json")
        if os.path.exists(raw_json_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                shutil.copy2(raw_json_path, os.path.join(t_dir, f"raw.bak.{timestamp}.json"))
            except Exception:
                pass
                
        # Switch to processing screen and run retranscribe only
        self.log_text.clear()
        self.stack.setCurrentIndex(1)
        self.controller.run_retranscribe_only()

    def _export_outputs(self):
        if not self.current_job:
            return

        self.log_text.clear()
        self.stack.setCurrentIndex(1)
        
        self.controller.stage_started.connect(self._on_stage_started)
        self.controller.export_now()
        self.controller.stage_finished.connect(self._on_export_stage_finished)

    def _on_export_stage_finished(self, stage, success, error_msg):
        if stage == STAGE_EXPORT:
            try:
                self.controller.stage_finished.disconnect(self._on_export_stage_finished)
            except Exception:
                pass
            
            if success:
                QMessageBox.information(self, "Export Successful", "All outputs exported successfully.")
            else:
                QMessageBox.critical(self, "Export Failed", f"Failed to export: {error_msg}")
            
            self.stack.setCurrentIndex(2)

    def _open_output_folder(self):
        if self.current_job:
            exports_dir = self.current_job.paths["exports"]
            os.startfile(exports_dir)


class DetectionPreviewDialog(QDialog):
    def __init__(self, parent, video_path, crop_region, ignore_masks, current_preset, job_paths):
        super().__init__(parent)
        self.setWindowTitle("Preview Detection")
        self.resize(750, 600)
        self.setMinimumSize(600, 500)
        
        self.video_path = video_path
        self.crop_region = crop_region
        self.ignore_masks = ignore_masks
        self.current_preset = current_preset
        self.job_paths = job_paths
        self.worker = None

        layout = QVBoxLayout(self)

        # Time range selection layout
        inputs_layout = QHBoxLayout()
        inputs_layout.addWidget(QLabel("Start (s):"))
        self.start_edit = QLineEdit("1758.0")
        self.start_edit.setToolTip("Start time in seconds or MM:SS format")
        inputs_layout.addWidget(self.start_edit)
        
        inputs_layout.addWidget(QLabel("End (s):"))
        self.end_edit = QLineEdit("2121.0")
        self.end_edit.setToolTip("End time in seconds or MM:SS format")
        inputs_layout.addWidget(self.end_edit)
        
        inputs_layout.addWidget(QLabel("Sensitivity:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Conservative", "Balanced", "Detailed"])
        idx = self.preset_combo.findText(current_preset.title())
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        else:
            self.preset_combo.setCurrentIndex(1)
        inputs_layout.addWidget(self.preset_combo)

        self.run_btn = QPushButton("Run Preview")
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.run_btn.clicked.connect(self.run_preview)
        inputs_layout.addWidget(self.run_btn)
        
        layout.addLayout(inputs_layout)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        from PySide6.QtWidgets import QTableWidget, QHeaderView
        
        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Thumbnail", "Timestamp", "Reason", "Confidence", "Changed Ratio"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        # Summary label
        self.summary_lbl = QLabel("Total candidates: 0")
        self.summary_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.summary_lbl)

    def run_preview(self):
        try:
            start_str = self.start_edit.text().strip()
            end_str = self.end_edit.text().strip()
            
            def parse_time(s):
                if ":" in s:
                    parts = s.split(":")
                    if len(parts) == 2:
                        return float(parts[0]) * 60 + float(parts[1])
                    elif len(parts) == 3:
                        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                return float(s)
            
            start_val = parse_time(start_str) if start_str else 0.0
            end_val = parse_time(end_str) if end_str else None
        except Exception:
            QMessageBox.critical(self, "Invalid Time Format", "Please enter valid times in seconds or HH:MM:SS format.")
            return

        self.run_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.progress.setValue(0)

        from lecturepack.constants import PRESETS
        preset_name = self.preset_combo.currentText().lower()
        preset_settings = PRESETS.get(preset_name, PRESETS["balanced"])

        from lecturepack.infrastructure.cv_engine import SlideDetectorWorker
        
        # Create a preview candidates subdirectory
        import os
        preview_candidates_dir = os.path.join(self.job_paths["root"], "preview_candidates")
        os.makedirs(preview_candidates_dir, exist_ok=True)
        preview_job_paths = self.job_paths.copy()
        preview_job_paths["candidates"] = preview_candidates_dir
        
        self.worker = SlideDetectorWorker(
            video_path=self.video_path,
            crop_region=self.crop_region,
            ignore_masks=self.ignore_masks,
            preset_settings=preset_settings,
            job_paths=preview_job_paths,
            start_time=start_val,
            end_time=end_val
        )
        
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(lambda success, error, candidates: self.on_detection_finished(success, error, candidates, preview_candidates_dir))
        self.worker.start()

    def on_detection_finished(self, success, error, candidates, preview_candidates_dir):
        self.run_btn.setEnabled(True)
        if not success:
            QMessageBox.critical(self, "Preview Failed", f"Slide detection failed: {error}")
            return

        self.table.setRowCount(len(candidates))
        self.summary_lbl.setText(f"Total candidates: {len(candidates)}")

        for i, c in enumerate(candidates):
            self.table.setRowHeight(i, 90)
            
            # 1. Thumbnail
            img_path = os.path.join(preview_candidates_dir, c["image_filename"])
            pm = QPixmap(img_path)
            if not pm.isNull():
                pm_scaled = pm.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                lbl_img = QLabel()
                lbl_img.setPixmap(pm_scaled)
                lbl_img.setAlignment(Qt.AlignCenter)
                self.table.setCellWidget(i, 0, lbl_img)
            else:
                self.table.setItem(i, 0, QTableWidgetItem("No Image"))
                
            # 2. Timestamp
            self.table.setItem(i, 1, QTableWidgetItem(f"{c['timestamp_formatted']}\n({c['timestamp_seconds']:.2f}s)"))
            
            # 3. Reason
            self.table.setItem(i, 2, QTableWidgetItem(f"{c['detector_path']}\n({c['decision_reason']})"))
            
            # 4. Confidence / Combined Score
            self.table.setItem(i, 3, QTableWidgetItem(f"Score: {c.get('combined_score', 0.0):.3f}\nBaseline: {c.get('rolling_baseline_score', 0.0):.3f}"))
            
            # 5. Changed Area Ratio
            self.table.setItem(i, 4, QTableWidgetItem(f"{c.get('changed_area_ratio', 0.0)*100:.1f}%"))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
            
        import shutil
        preview_candidates_dir = os.path.join(self.job_paths["root"], "preview_candidates")
        if os.path.exists(preview_candidates_dir):
            try:
                shutil.rmtree(preview_candidates_dir, ignore_errors=True)
            except Exception:
                pass
        super().closeEvent(event)

