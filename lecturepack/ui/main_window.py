import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QComboBox, QRadioButton, QButtonGroup,
    QStackedWidget, QProgressBar, QTextEdit, QListWidget, QListWidgetItem,
    QCheckBox, QMessageBox, QGroupBox, QSplitter
)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QSize, QRectF

from lecturepack.constants import (
    STAGE_INSPECT, STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE,
    STAGE_DETECT_SLIDES, STAGE_ALIGN, STAGE_REVIEW_READY, STAGE_EXPORT,
    STAGES, DEFAULT_DATA_DIR
)
from lecturepack.models.job import Job
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.file_manager import FileManager

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

        self.setWindowTitle("Lecture Pack - MVP")
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        # Setup Main Stacked Widget
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._init_setup_view()
        self._init_processing_view()
        self._init_review_view()

        # Connect controller signals
        self.controller.stage_started.connect(self._on_stage_started)
        self.controller.stage_progress.connect(self._on_stage_progress)
        self.controller.stage_log.connect(self._on_stage_log)
        self.controller.stage_finished.connect(self._on_stage_finished)
        self.controller.pipeline_completed.connect(self._on_pipeline_completed)
        self.controller.pipeline_failed.connect(self._on_pipeline_failed)

        # Scan for existing jobs
        self._reload_recent_jobs()

    # Drag and drop support
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
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
        whisper_grp = QGroupBox("Whisper Settings")
        whisper_layout = QVBoxLayout(whisper_grp)
        
        exe_layout = QHBoxLayout()
        exe_layout.addWidget(QLabel("Whisper Exe:"))
        self.whisper_exe_edit = QLineEdit(self.config_manager.get("whisper_exe", ""))
        self.whisper_exe_edit.textChanged.connect(lambda t: self.config_manager.set("whisper_exe", t))
        browse_exe_btn = QPushButton("Browse")
        browse_exe_btn.clicked.connect(self._browse_whisper_exe)
        exe_layout.addWidget(self.whisper_exe_edit)
        exe_layout.addWidget(browse_exe_btn)
        whisper_layout.addLayout(exe_layout)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model Path:"))
        self.whisper_model_edit = QLineEdit(self.config_manager.get("whisper_model", ""))
        self.whisper_model_edit.textChanged.connect(lambda t: self.config_manager.set("whisper_model", t))
        browse_model_btn = QPushButton("Browse")
        browse_model_btn.clicked.connect(self._browse_whisper_model)
        model_layout.addWidget(self.whisper_model_edit)
        model_layout.addWidget(browse_model_btn)
        whisper_layout.addLayout(model_layout)
        
        glossary_layout = QHBoxLayout()
        glossary_layout.addWidget(QLabel("Course Glossary:"))
        self.glossary_edit = QLineEdit()
        self.glossary_edit.setPlaceholderText("Comma separated key terms, acronyms...")
        whisper_layout.addLayout(glossary_layout)

        left_layout.addWidget(whisper_grp)

        # Preset group
        preset_grp = QGroupBox("Slide Change Preset")
        preset_layout = QVBoxLayout(preset_grp)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Standard Lecture Slides", "Slides with Webcam", "Handwritten / Whiteboard", "Software Demonstration"])
        preset_layout.addWidget(self.preset_combo)
        left_layout.addWidget(preset_grp)

        # Action Buttons
        self.start_btn = QPushButton("Start Processing")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px; padding: 10px;")
        self.start_btn.clicked.connect(self._start_processing)
        left_layout.addWidget(self.start_btn)

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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left pane: accepted slides list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Accepted Slides (Timeline)"))
        self.accepted_list = QListWidget()
        self.accepted_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.accepted_list.setIconSize(QSize(160, 120))
        self.accepted_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.accepted_list.itemClicked.connect(self._on_accepted_clicked)
        left_layout.addWidget(self.accepted_list)
        splitter.addWidget(left_widget)

        # Center pane: Large preview & controls
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        self.preview_lbl = QLabel("Select a slide to preview")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("background: #222; border: 1px solid #555;")
        center_layout.addWidget(self.preview_lbl, 1)

        self.slide_info_lbl = QLabel("Timestamp: -")
        self.slide_info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slide_info_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        center_layout.addWidget(self.slide_info_lbl)

        self.keep_reject_btn = QPushButton("Reject Slide")
        self.keep_reject_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px;")
        self.keep_reject_btn.clicked.connect(self._toggle_slide_decision)
        center_layout.addWidget(self.keep_reject_btn)
        splitter.addWidget(center_widget)

        # Right pane: Rejected candidates list
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("Rejected Candidates"))
        self.rejected_list = QListWidget()
        self.rejected_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.rejected_list.setIconSize(QSize(160, 120))
        self.rejected_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.rejected_list.itemClicked.connect(self._on_rejected_clicked)
        right_layout.addWidget(self.rejected_list)
        
        self.restore_btn = QPushButton("Restore Slide")
        self.restore_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        self.restore_btn.clicked.connect(self._restore_slide)
        right_layout.addWidget(self.restore_btn)
        splitter.addWidget(right_widget)

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
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Lecture Video", "", "Video Files (*.mp4 *.avi *.mkv *.mov *.webm)")
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
        
        # Instantiate new job
        self.current_job = Job(self.config_manager.data_dir, video_path=video_path)
        self.controller.set_job(self.current_job)

        # Inspect video using ffprobe synchronously for metadata & generate preview
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
            
            # Extract preview frame
            preview_png = os.path.join(self.current_job.paths["logs"], "preview.png")
            if extract_preview(video_path, preview_png):
                self.crop_selector.set_preview_image(preview_png)
            else:
                self.crop_selector.clear_rects()

        except Exception as e:
            QMessageBox.critical(self, "Inspection Error", f"Failed to inspect video: {str(e)}")
            self.metadata_lbl.setText("Failed to inspect video.")

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
            return
        
        job_id, source_path = self.recent_jobs_combo.itemData(index)
        self.current_job = Job(self.config_manager.data_dir, job_id=job_id)
        self.controller.set_job(self.current_job)
        
        # Load source path to edit
        self.video_path_edit.setText(source_path)
        self.glossary_edit.setText(self.current_job.settings.get("whisper", {}).get("glossary", ""))
        
        # Load presets
        preset = self.current_job.settings.get("preset", "standard_lecture")
        idx = self.preset_combo.findText(preset.replace("_", " ").title())
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)

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

        # If already review ready, jump directly to Review view!
        if self.current_job.get_stage_status(STAGE_REVIEW_READY) == "completed":
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

        # Save settings first
        preset_name = self.preset_combo.currentText().lower().replace(" / ", "_").replace(" ", "_")
        self.current_job.settings["preset"] = preset_name
        self.current_job.settings["whisper"]["glossary"] = self.glossary_edit.text().strip()
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

        # Switch to processing stack
        self.log_text.clear()
        self.stack.setCurrentIndex(1)
        
        # Start pipeline
        self.controller.run_pipeline()

    def _cancel_processing(self):
        self.controller.cancel()
        self.stack.setCurrentIndex(0)

    # 5. CONTROLLER SIGNAL HANDLERS
    def _on_stage_started(self, stage):
        self.stage_lbl.setText(f"Stage: {stage}")
        # Reset color highlight
        for s, lbl in self.stages_labels.items():
            if s == stage:
                lbl.setStyleSheet("color: #2196F3; font-weight: bold; margin: 5px;") # Active blue
            else:
                lbl.setStyleSheet("color: #777; font-weight: bold; margin: 5px;")
        self.progress_bar.setValue(0)

    def _on_stage_progress(self, stage, percent):
        self.progress_bar.setValue(percent)

    def _on_stage_log(self, stage, msg):
        self.log_text.insertPlainText(msg)
        # Scroll to bottom
        self.log_text.ensureCursorVisible()

    def _on_stage_finished(self, stage, success, error_msg):
        lbl = self.stages_labels.get(stage)
        if lbl:
            if success:
                lbl.setStyleSheet("color: #4CAF50; font-weight: bold; margin: 5px;") # Completed Green
            else:
                lbl.setStyleSheet("color: #f44336; font-weight: bold; margin: 5px;") # Failed Red

    def _on_pipeline_completed(self):
        QMessageBox.information(self, "Success", "Slide detection & transcription finished successfully.")
        self._load_review_data()
        self.stack.setCurrentIndex(2)
        # Refresh combo
        self._reload_recent_jobs()

    def _on_pipeline_failed(self, error_msg):
        QMessageBox.critical(self, "Pipeline Error", f"Processing failed: {error_msg}\nCheck logs for more details.")
        self.stack.setCurrentIndex(0)

    # 6. REVIEW & EXPORT VIEWS SLOTS
    def _load_review_data(self):
        self.accepted_list.clear()
        self.rejected_list.clear()
        self.preview_lbl.setText("Select a slide to preview")
        self.slide_info_lbl.setText("Timestamp: -")

        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])

        candidates_dir = self.current_job.paths["candidates"]

        for cand in candidates:
            img_filename = cand.get("image_filename", "")
            img_p = os.path.join(candidates_dir, img_filename)
            
            icon = QIcon()
            if os.path.exists(img_p):
                icon = QIcon(img_p)

            ts_sec = cand.get("timestamp_seconds", 0.0)
            ts_formatted = cand.get("timestamp_formatted", "00:00:00.000")
            item = QListWidgetItem(icon, f"@{ts_formatted}")
            item.setData(Qt.ItemDataRole.UserRole, cand)

            if cand.get("decision") == "accepted":
                self.accepted_list.addItem(item)
            else:
                self.rejected_list.addItem(item)

    def _on_accepted_clicked(self, item):
        self.rejected_list.clearSelection()
        cand = item.data(Qt.ItemDataRole.UserRole)
        self._show_slide_preview(cand)
        self.keep_reject_btn.setText("Reject Slide")
        self.keep_reject_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px;")

    def _on_rejected_clicked(self, item):
        self.accepted_list.clearSelection()
        cand = item.data(Qt.ItemDataRole.UserRole)
        self._show_slide_preview(cand)
        self.keep_reject_btn.setText("Keep Slide")
        self.keep_reject_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")

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

    def _toggle_slide_decision(self):
        # Determine which list has selection
        ac_items = self.accepted_list.selectedItems()
        rj_items = self.rejected_list.selectedItems()

        if not ac_items and not rj_items:
            return

        candidates_path = os.path.join(self.current_job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])

        if ac_items:
            item = ac_items[0]
            cand = item.data(Qt.ItemDataRole.UserRole)
            target_decision = "rejected"
        else:
            item = rj_items[0]
            cand = item.data(Qt.ItemDataRole.UserRole)
            target_decision = "accepted"

        # Update in candidate metadata
        for c in candidates:
            if c["frame_number"] == cand["frame_number"]:
                c["decision"] = target_decision
                break

        FileManager.write_json_atomic(candidates_path, candidates)
        
        # Reload UI lists and restore selection
        self._load_review_data()

    def _restore_slide(self):
        # Alias helper for Restore button in rejected pane
        self._toggle_slide_decision()

    def _export_outputs(self):
        if not self.current_job:
            return

        # Trigger re-alignment & exports using controller
        self.log_text.clear()
        self.stack.setCurrentIndex(1) # Switch to processing stack
        
        self.controller.stage_started.connect(self._on_stage_started)
        self.controller.export_now()
        
        # Connect finished signal to return to review view
        self.controller.stage_finished.connect(self._on_export_stage_finished)

    def _on_export_stage_finished(self, stage, success, error_msg):
        if stage == STAGE_EXPORT:
            # Disconnect so it doesn't trigger multiple times
            try:
                self.controller.stage_finished.disconnect(self._on_export_stage_finished)
            except Exception:
                pass
            
            if success:
                QMessageBox.information(self, "Export Successful", "All outputs exported successfully.")
            else:
                QMessageBox.critical(self, "Export Failed", f"Failed to export: {error_msg}")
            
            self.stack.setCurrentIndex(2) # Return to Review/Export view

    def _open_output_folder(self):
        if self.current_job:
            exports_dir = self.current_job.paths["exports"]
            os.startfile(exports_dir)
