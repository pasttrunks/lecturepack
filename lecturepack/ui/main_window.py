"""
lecturepack.ui.main_window
==========================

v1.1 application shell (Phase 1):

    left   narrow navigation rail  (Home · Process · Review · Transcript ·
                                    Exports · Settings)
    top    command bar             (job switcher, product mode, Save, Export,
                                    concise status)
    center page stack              (indices: 0 Home, 1 Process, 2 Review,
                                    3 Transcript, 4 Exports, 5 Settings --
                                    Review stays at index 2 for backward
                                    compatibility with tests/tools)
    bottom status bar              (stage · elapsed · progress · engine/model/
                                    backend · warnings)

Splitter positions, window geometry, last active page and list/grid modes are
persisted via QSettings. The public attribute surface used by the packaged
validation driver and the v1.0 tests (slides_view, transcript_table, stack,
recent_jobs_combo, crop_selector, _load_review_data, ...) is preserved as
aliases onto the new pages.
"""
from __future__ import annotations

import datetime
import os
import shutil

from PySide6.QtCore import QByteArray, QElapsedTimer, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QImage, QIcon, QKeySequence, QShortcut, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSizeGrip,
    QToolButton, QVBoxLayout, QWidget, QTableWidgetItem, QLineEdit, QTextEdit,
)

from lecturepack.constants import (
    DEFAULT_DATA_DIR, STAGES, STAGE_EXPORT, STAGE_REVIEW_READY, STAGE_TRANSCRIBE,
    SUPPORTED_VIDEO_EXTENSIONS, TRANSCRIPTION_BACKEND_LOCAL,
)
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.ui import theme
from lecturepack.ui.new_job_dialog import NewJobDialog
from lecturepack.ui.pages.exports_page import ExportsPage
from lecturepack.ui.pages.home_page import HomePage
from lecturepack.ui.pages.process_page import ProcessPage
from lecturepack.ui.pages.review_page import ReviewPage
from lecturepack.ui.pages.study_page import StudyPage
from lecturepack.ui.pages.transcript_page import TranscriptPage
from lecturepack.ui.pages.settings_page import SettingsPage
from lecturepack.ui.widgets.animated_stacked import AnimatedStackedWidget
from lecturepack.ui.widgets.title_bar import HeaderBarWidget

PAGES = ["Home", "Process", "Review", "Transcript", "Exports", "Settings", "Study"]
PAGE_ICONS = ["⌂", "▶", "▦", "¶", "⇩", "⚙", "◇"]
PAGE_HOME, PAGE_PROCESS, PAGE_REVIEW, PAGE_TRANSCRIPT, PAGE_EXPORTS, PAGE_SETTINGS, PAGE_STUDY = range(7)
NAV_PAGE_ORDER = [PAGE_HOME, PAGE_STUDY, PAGE_PROCESS, PAGE_REVIEW,
                  PAGE_TRANSCRIPT, PAGE_EXPORTS, PAGE_SETTINGS]

_NAV_SVG = {
    "Home": b'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/></svg>',
    "Process": b'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/></svg>',
    "Review": b'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18"/></svg>',
    "Transcript": b'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 12H3"/><path d="M17 18H3"/><path d="M21 6H3"/></svg>',
    "Study": b'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.42 10.92a1 1 0 0 0-.02-1.84L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.83l8.57 3.91a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/></svg>',
    "Exports": b'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3"/><path d="m7 10 5 5 5-5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/></svg>',
    "Settings": b'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',
}


def _nav_icon(name: str, dark: bool = False) -> QIcon:
    """Return a QIcon from the SVG data for a nav item, themed to light/dark."""
    svg_template = _NAV_SVG.get(name, b"")
    if not svg_template:
        return QIcon()
    color = "#F0E9DF" if dark else "#1D1915"
    svg = svg_template.replace(b"currentColor", color.encode())
    img = QImage.fromData(QByteArray(svg))
    if img.isNull():
        return QIcon()
    return QIcon(QPixmap.fromImage(img))


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
        if 0 <= row < len(self.archived_jobs):
            return self.archived_jobs[row]
        return None


def extract_preview(video_path, out_path):
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False
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
        self._pipeline_timer = QElapsedTimer()
        self._settings = QSettings("LecturePack", "LecturePack")

        # Async capability detection (kept from v1.0)
        from lecturepack.infrastructure.whisper_detector import WhisperCapabilityDetector
        self.whisper_detector = WhisperCapabilityDetector(self)
        self.whisper_detector.finished.connect(self._on_whisper_detection_finished)
        self.current_whisper_caps = None

        from lecturepack import __version__
        self.setWindowTitle(f"LecturePack v{__version__}")
        self.resize(1360, 860)
        self.setAcceptDrops(True)
        # Phase 2: frameless premium shell with a custom title bar.
        self.setWindowFlags(Qt.WindowType.Window
                            | Qt.WindowType.FramelessWindowHint)

        theme.apply_theme(
            __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.instance(),
            dark=bool(config_manager.get("dark_theme", False)))

        self._build_shell()
        self._init_shortcuts()
        self._connect_controller()

        self.config_manager.autodetect_ffmpeg()
        self.config_manager.autodetect_whisper()
        self._reload_recent_jobs()
        self.home_page.refresh_jobs()
        self._refresh_diagnostics()
        self._restore_ui_state()
        self._refresh_nav_icons()

    # ------------------------------------------------------------------ #
    # shell construction
    # ------------------------------------------------------------------ #
    def _build_shell(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Studio-style header bar (56px) ------------------------------- #
        self.header_bar = HeaderBarWidget(title=self.windowTitle())
        self.header_bar.minimize_clicked.connect(self.showMinimized)
        self.header_bar.toggle_maximize_clicked.connect(self._toggle_maximize)
        self.header_bar.close_clicked.connect(self.close)
        self.header_bar.theme_toggled.connect(self._on_theme_toggle)
        self.header_bar.save_clicked.connect(self._on_save_action)
        self.header_bar.export_clicked.connect(self._export_outputs)
        root.addWidget(self.header_bar)

        # ---- body: sidebar + stack ---------------------------------------- #
        body = QWidget()
        hb = QHBoxLayout(body)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("NavSidebar")
        self._nav_rail = sidebar  # keep alias for focus_mode compatibility
        sidebar.setFixedWidth(224)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(12, 14, 12, 14)
        sl.setSpacing(4)

        # -- job status card (hidden until a job is active) -- #
        self._job_card = QFrame()
        self._job_card.setObjectName("JobStatusCard")
        self._job_card.setFixedHeight(70)
        jc_layout = QHBoxLayout(self._job_card)
        jc_layout.setContentsMargins(10, 10, 10, 10)
        jc_layout.setSpacing(11)
        self._job_card_thumb = QFrame()
        self._job_card_thumb.setObjectName("JobCardThumb")
        self._job_card_thumb.setFixedSize(40, 30)
        jc_layout.addWidget(self._job_card_thumb)
        self._job_card_info = QVBoxLayout()
        self._job_card_info.setSpacing(2)
        self._job_card_title = QLabel("")
        self._job_card_title.setObjectName("JobCardTitle")
        self._job_card_status = QLabel("")
        self._job_card_status.setObjectName("JobCardStatus")
        self._job_card_info.addWidget(self._job_card_title)
        self._job_card_info.addWidget(self._job_card_status)
        jc_layout.addLayout(self._job_card_info, 1)
        self._job_card.hide()
        sl.addWidget(self._job_card)

        # -- Library section -- #
        lib_label = QLabel("Library")
        lib_label.setObjectName("SidebarSectionLabel")
        sl.addWidget(lib_label)
        self.nav_buttons = [None] * len(PAGES)

        home_btn = self._make_nav_btn(PAGE_HOME, "\u2302", "Home")
        sl.addWidget(home_btn)
        self.nav_buttons[PAGE_HOME] = home_btn

        # -- Workspace section -- #
        ws_label = QLabel("Workspace")
        ws_label.setObjectName("SidebarSectionLabel")
        sl.addWidget(ws_label)

        ws_nav = [
            (PAGE_PROCESS, "\u25B6", "Process"),
            (PAGE_REVIEW, "\u25A6", "Review"),
            (PAGE_TRANSCRIPT, "\u00B6", "Transcript"),
            (PAGE_STUDY, "\u25C7", "Study"),
        ]
        for page_idx, icon, name in ws_nav:
            btn = self._make_nav_btn(page_idx, icon, name)
            sl.addWidget(btn)
            self.nav_buttons[page_idx] = btn

        # -- Output section -- #
        out_label = QLabel("Output")
        out_label.setObjectName("SidebarSectionLabel")
        sl.addWidget(out_label)

        exports_btn = self._make_nav_btn(PAGE_EXPORTS, "\u2909", "Exports")
        sl.addWidget(exports_btn)
        self.nav_buttons[PAGE_EXPORTS] = exports_btn

        # -- spacer -- #
        sl.addStretch(1)

        # -- Settings (bottom) -- #
        settings_btn = self._make_nav_btn(PAGE_SETTINGS, "\u2699", "Settings")
        sl.addWidget(settings_btn)
        self.nav_buttons[PAGE_SETTINGS] = settings_btn

        hb.addWidget(sidebar)

        # -- page stack -- #
        self.stack = AnimatedStackedWidget()
        self.home_page = HomePage(self.config_manager)
        self.process_page = ProcessPage(self.config_manager)
        self.review_page = ReviewPage(self.config_manager)
        self.transcript_page = TranscriptPage(self.config_manager)
        self.exports_page = ExportsPage()
        self.settings_page = SettingsPage(self.config_manager)
        self.study_page = StudyPage(self.config_manager)
        for w in (self.home_page, self.process_page, self.review_page,
                  self.transcript_page, self.exports_page, self.settings_page,
                  self.study_page):
            self.stack.addWidget(w)
        self.stack.currentChanged.connect(self._on_page_changed)
        hb.addWidget(self.stack, 1)
        root.addWidget(body, 1)
        self.setCentralWidget(central)

        # ---- custom status footer (34px) ---------------------------------- #
        footer = QFrame()
        footer.setObjectName("AppStatusFooter")
        footer.setFixedHeight(40)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(18, 0, 18, 0)
        fl.setSpacing(15)
        self.sb_stage = QLabel("Idle")
        self.sb_stage.setObjectName("FooterStage")
        self.sb_elapsed = QLabel("")
        self.sb_elapsed.setObjectName("FooterElapsed")
        self.sb_progress = QProgressBar()
        self.sb_progress.setMaximumWidth(200)
        self.sb_progress.setMaximumHeight(7)
        self.sb_progress.setTextVisible(False)
        self.sb_progress.setObjectName("FooterProgress")
        fl.addWidget(self.sb_stage)
        fl.addWidget(self.sb_progress)
        fl.addWidget(self.sb_elapsed)
        fl.addStretch(1)
        self.sb_engine = QLabel("")
        self.sb_engine.setObjectName("FooterEngine")
        self.sb_warn = QLabel("")
        self.sb_warn.setObjectName("FooterWarn")
        fl.addWidget(self.sb_warn)
        fl.addWidget(self.sb_engine)
        fl.addWidget(QSizeGrip(self))  # resize handle for frameless
        root.addWidget(footer)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        # -- compat aliases for status bar access -- #
        self._status_footer = footer
        self._command_bar = None  # removed in Studio layout
        self._hidden_combo = QComboBox()
        self._hidden_combo.hide()
        self._hidden_mode_lbl = QLabel("")
        self._hidden_mode_lbl.hide()

        # ---- focus mode --------------------------------------------------- #
        from lecturepack.ui.widgets.focus_mode import FocusModeController
        chrome_widgets = [
            (self._nav_rail, "width"), (self.header_bar, "height"), (footer, "height"),
        ]
        self.focus_mode = FocusModeController(self, chrome_widgets, content_widget=self.stack)

        # ---- page wiring --------------------------------------------------- #
        self.home_page.new_job_requested.connect(self._open_new_job_dialog)
        self.home_page.job_selected.connect(self._on_home_job_selected)
        self.home_page.archive_requested.connect(self._archive_current_job)
        self.home_page.restore_requested.connect(self._restore_archived_job)
        self.home_page.export_archive_requested.connect(self._export_job_archive)

        self.process_page.video_chosen.connect(self._on_video_selected_from_ui)
        self.process_page.transcription_mode_combo.currentIndexChanged.connect(
            self._refresh_diagnostics)
        self.process_page.product_mode_combo.currentIndexChanged.connect(
            self._refresh_diagnostics)
        self.process_page.start_requested.connect(self._start_processing)
        self.process_page.retranscribe_requested.connect(self._retranscribe_only_workflow)
        self.process_page.cancel_requested.connect(self._cancel_processing)
        self.process_page.preview_detection_requested.connect(self._run_detection_preview)
        self.process_page.video_path_edit.editingFinished.connect(
            lambda: self._maybe_load_typed_video())

        self.review_page.status_message.connect(self._show_status)
        self.review_page.open_context_repair.connect(self._open_context_repair)
        self.review_page.study_data_changed.connect(self.study_page.refresh)
        self.review_page.position_changed.connect(
            lambda timestamp: self._save_study_position("review", timestamp))
        self.review_page.selection_count_changed.connect(lambda n: None)

        self.transcript_page.status_message.connect(self._show_status)
        self.transcript_page.seek_requested.connect(self._on_transcript_seek)
        self.transcript_page.study_data_changed.connect(self.study_page.refresh)
        self.transcript_page.position_changed.connect(
            lambda timestamp: self._save_study_position("transcript", timestamp))

        self.study_page.navigate_requested.connect(self._on_study_navigation)
        self.study_page.seek_requested.connect(self._on_transcript_seek)
        self.study_page.resume_requested.connect(self._resume_study_position)

        self.exports_page.export_requested.connect(self._export_outputs)

        self.settings_page.theme_changed.connect(self._on_theme_changed)
        self.settings_page.settings_changed.connect(self._refresh_diagnostics)

    # ---- compatibility aliases (v1.0 tests / packaged validation) -------- #
    @property
    def title_bar(self):
        return self.header_bar

    @property
    def bar_status_lbl(self):
        return self.sb_engine

    @property
    def mode_lbl(self):
        return self._hidden_mode_lbl

    @property
    def recent_jobs_combo(self):
        return self._hidden_combo

    @property
    def job_title_lbl(self):
        return self.header_bar.breadcrumb_lbl

    def _make_nav_btn(self, page_index, icon, name):
        btn = QToolButton()
        btn.setText(f"  {name}")
        btn.setCheckable(True)
        btn.setProperty("navButton", True)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setIconSize(QSize(19, 19))
        btn.setFixedHeight(38)
        btn.clicked.connect(
            lambda checked, idx=page_index: self.navigate_to(idx))
        return btn

    def _refresh_nav_icons(self):
        """Update all nav button SVG icons for the current theme."""
        dark = self.palette().window().color().lightness() < 128
        for idx, btn in enumerate(self.nav_buttons):
            if btn is not None:
                btn.setIcon(_nav_icon(PAGES[idx], dark=dark))
    @property
    def slides_view(self):
        return self.review_page.slides_view

    @property
    def selected_count_lbl(self):
        return self.review_page.selected_count_lbl

    @property
    def transcript_table(self):
        return self.review_page.transcript_table

    @property
    def search_input(self):
        return self.review_page.search_input

    @property
    def timestamps_chk(self):
        return self.review_page.timestamps_chk

    @property
    def copy_format_combo(self):
        return self.review_page.copy_format_combo

    @property
    def video_path_edit(self):
        return self.process_page.video_path_edit

    @property
    def preset_combo(self):
        return self.process_page.preset_combo

    @property
    def product_mode_combo(self):
        return self.process_page.product_mode_combo

    @property
    def glossary_edit(self):
        return self.process_page.glossary_edit

    @property
    def threads_spin(self):
        return self.process_page.threads_spin

    @property
    def profile_combo(self):
        return self.process_page.profile_combo

    @property
    def crop_selector(self):
        return self.process_page.crop_selector

    @property
    def stage_lbl(self):
        return self.process_page.stage_lbl

    @property
    def progress_bar(self):
        return self.process_page.progress_bar

    @property
    def log_text(self):
        return self.process_page.log_text

    @property
    def metadata_lbl(self):
        return self.process_page.metadata_lbl

    @property
    def retranscribe_btn(self):
        return self.process_page.retranscribe_btn

    @property
    def start_btn(self):
        return self.process_page.start_btn

    def _load_review_data(self):
        self.review_page.set_job(self.current_job)
        self.review_page.load_review_data()
        self.transcript_page.load_job(self.current_job)
        self.exports_page.set_job(self.current_job)
        self.study_page.load_job(self.current_job)

    def _save_corrections(self):
        self.review_page._save_corrections()

    def _bulk_reject(self):
        self.review_page._bulk_reject()

    def _bulk_keep(self):
        self.review_page._bulk_keep()

    def _bulk_restore(self):
        self.review_page._bulk_restore()

    def _undo_review_action(self):
        self.review_page.undo_review_action()

    def _copy_full_transcript(self):
        self.review_page._copy_full_transcript()

    def _copy_current_transcript(self):
        self.review_page._copy_current_transcript()

    def _copy_selected_transcripts(self):
        self.review_page._copy_selected_transcripts()

    # ------------------------------------------------------------------ #
    # navigation & persistence
    # ------------------------------------------------------------------ #
    def _update_job_card(self):
        """Show/hide and update the sidebar job status card."""
        if self.current_job is not None:
            title = self.current_job.manifest.get("title", "Job")
            status = "Active"
            stages = self.current_job.state.get("stages", {})
            for stage_name, stage_data in stages.items():
                s = stage_data.get("status", "pending")
                if s == "running":
                    status = f"{stage_name}..."
                    break
                elif s == "completed":
                    status = "Complete"
            self._job_card_title.setText(title)
            self._job_card_status.setText(status)
            self._job_card.show()
        else:
            self._job_card.hide()
    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.header_bar.set_maximized(self.isMaximized())

    def navigate_to(self, index):
        self.stack.setCurrentIndex(index)

    def _on_page_changed(self, index):
        for page_index, btn in enumerate(self.nav_buttons):
            if btn is not None:
                btn.setChecked(page_index == index)
        # Update breadcrumb
        page_name = PAGES[index] if 0 <= len(PAGES) else ""
        job_title = ""
        if self.current_job is not None:
            job_title = self.current_job.manifest.get("title", "")
        if job_title:
            self.header_bar.set_breadcrumb(f"{job_title}  \u203A  {page_name}")
        else:
            self.header_bar.set_breadcrumb(page_name)
        if index == PAGE_REVIEW and self.current_job is not None \
                and self.review_page.slides_view.count() == 0:
            self._load_review_data()
        if index == PAGE_EXPORTS:
            self.exports_page.refresh_artifacts()
        if index == PAGE_STUDY and self.current_job is not None:
            self.study_page.refresh()
        self._settings.setValue("lastPage", index)

    def _restore_ui_state(self):
        geo = self._settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        for key, splitter in (("reviewSplitter", self.review_page.splitter),
                              ("processSplitter", self.process_page.splitter),
                              ("segSplitter", self.transcript_page.seg_splitter)):
            st = self._settings.value(key)
            if st is not None:
                splitter.restoreState(st)
        mode = self._settings.value("slideListMode", "grid")
        self.review_page._set_mode(mode if mode in ("grid", "list") else "grid")
        try:
            last = int(self._settings.value("lastPage", PAGE_HOME))
        except (TypeError, ValueError):
            last = PAGE_HOME
        self.navigate_to(last if 0 <= last < len(PAGES) else PAGE_HOME)

    def _persist_ui_state(self):
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("reviewSplitter", self.review_page.splitter.saveState())
        self._settings.setValue("processSplitter", self.process_page.splitter.saveState())
        self._settings.setValue("segSplitter", self.transcript_page.seg_splitter.saveState())
        self._settings.setValue("slideListMode", self.review_page.slides_view.display_mode())

    def _on_theme_changed(self, dark):
        from PySide6.QtWidgets import QApplication
        theme.apply_theme(QApplication.instance(), dark)
        self.header_bar.set_theme_label(dark)
        self.header_bar.set_wordmark_theme(dark)
        self._refresh_nav_icons()
        # Job cards bake theme colors into per-instance stylesheets at
        # construction time, so they must be rebuilt on every theme toggle
        # to avoid stale (invisible) colors from the previous theme.
        if hasattr(self, "home_page"):
            self.home_page.refresh_jobs()

    def _on_theme_toggle(self):
        dark = not theme.is_dark()
        self.config_manager.set("dark_theme", dark)
        self._on_theme_changed(dark)
        self.settings_page._load_settings()

    def _show_status(self, msg):
        self.statusBar().showMessage(msg, 4000)

    # ------------------------------------------------------------------ #
    # drag & drop
    # ------------------------------------------------------------------ #
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS):
                self._open_new_job_dialog(initial_path=file_path)

    # ------------------------------------------------------------------ #
    # job lifecycle
    # ------------------------------------------------------------------ #
    def _open_new_job_dialog(self, initial_path=None):
        """Onboarding modal: confirm the video + output mode, then hand off
        to the Process page for real transcription/crop settings."""
        dlg = NewJobDialog(self.controller.ffmpeg_wrapper, initial_path=initial_path, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selected_path:
            return
        self._on_video_selected_from_ui(dlg.selected_path, product_mode=dlg.selected_mode)

    def _on_video_selected_from_ui(self, file_path, product_mode=None):
        self.process_page.video_path_edit.setText(file_path)
        self._on_video_selected(file_path)
        if product_mode is not None:
            idx = self.process_page.product_mode_combo.findData(product_mode)
            if idx >= 0:
                self.process_page.product_mode_combo.setCurrentIndex(idx)
        self.navigate_to(PAGE_PROCESS)

    def _maybe_load_typed_video(self):
        p = self.process_page.video_path_edit.text().strip()
        if p and os.path.exists(p) and (self.current_job is None or
                self.current_job.manifest.get("source", {}).get("original_path") != p):
            self._on_video_selected(p)

    def _on_video_selected(self, video_path):
        """Initializes a new job for the given video path."""
        if not os.path.exists(video_path):
            return
        self.current_job = Job(self.config_manager.data_dir, video_path=video_path)
        self.controller.set_job(self.current_job)
        self.study_page.load_job(self.current_job)
        title = self.current_job.manifest.get("title", "Job")
        self.header_bar.set_breadcrumb(f"{title}")
        self._update_job_card()

        try:
            self.controller.ffmpeg_wrapper.detect_binaries()
            meta = self.controller.ffmpeg_wrapper.inspect_video(video_path)
            self.current_job.source.update(meta)
            self.current_job.save()
            self.process_page.metadata_lbl.setText(
                f"{meta['width']}x{meta['height']}  ·  {meta['duration']:.1f}s  ·  "
                f"{meta['fps']:.2f} fps  ·  {meta['video_codec']}")
            preview_png = os.path.join(self.current_job.paths["logs"], "preview.png")
            if extract_preview(video_path, preview_png):
                self.process_page.crop_selector.set_preview_image(preview_png)
            else:
                self.process_page.crop_selector.clear_rects()
        except Exception as e:
            QMessageBox.critical(self, "Inspection Error", f"Failed to inspect video: {e}")
            self.process_page.metadata_lbl.setText("Failed to inspect video.")

        is_completed = self.current_job.get_stage_status(STAGE_REVIEW_READY) == "completed"
        self.process_page.retranscribe_btn.setEnabled(is_completed)

    def _reload_recent_jobs(self):
        self.recent_jobs_combo.blockSignals(True)
        self.recent_jobs_combo.clear()
        self.recent_jobs_combo.addItem("New Job / Select Video")
        jobs_dir = os.path.join(self.config_manager.data_dir, "jobs")
        if os.path.exists(jobs_dir):
            for job_id in os.listdir(jobs_dir):
                manifest_p = os.path.join(jobs_dir, job_id, "manifest.json")
                if os.path.exists(manifest_p):
                    man = FileManager.read_json_safe(manifest_p)
                    if isinstance(man, dict):
                        title = man.get("title", job_id)
                        source_path = man.get("source", {}).get("original_path", "")
                        self.recent_jobs_combo.addItem(
                            f"{title} ({job_id[:8]})", (job_id, source_path))
        self.recent_jobs_combo.blockSignals(False)
        if hasattr(self, "home_page"):
            self.home_page.refresh_jobs()

    def _on_home_job_selected(self, job_id, source_path):
        for i in range(self.recent_jobs_combo.count()):
            data = self.recent_jobs_combo.itemData(i)
            if data and data[0] == job_id:
                self.recent_jobs_combo.setCurrentIndex(i)
                return
        self._load_job(job_id, source_path)

    def _on_recent_job_changed(self, index):
        if index <= 0:
            self.process_page.retranscribe_btn.setEnabled(False)
            return
        job_id, source_path = self.recent_jobs_combo.itemData(index)
        self._load_job(job_id, source_path)

    def _load_job(self, job_id, source_path):
        self.current_job = Job(self.config_manager.data_dir, job_id=job_id)
        self.controller.set_job(self.current_job)
        self.review_page.set_job(self.current_job)
        self.study_page.load_job(self.current_job)
        title = self.current_job.manifest.get("title", "Job")
        self.header_bar.set_breadcrumb(f"{title}")
        self._update_job_card()
        pp = self.process_page
        pp.video_path_edit.setText(source_path)

        w_settings = self.current_job.settings.get("whisper", {})
        backend_idx = pp.transcription_mode_combo.findData(
            w_settings.get("transcription_backend", TRANSCRIPTION_BACKEND_LOCAL))
        pp.transcription_mode_combo.setCurrentIndex(max(0, backend_idx))
        pp.glossary_edit.setText(w_settings.get("glossary", ""))
        profile = w_settings.get("profile", "fast")
        p_idx = pp.profile_combo.findText(profile.title())
        if p_idx >= 0:
            pp.profile_combo.setCurrentIndex(p_idx)
        pp.threads_spin.setValue(w_settings.get("threads", 8))
        eng_idx = pp.engine_combo.findData(w_settings.get("engine",
                                           self.config_manager.get("engine", "auto")))
        if eng_idx >= 0:
            pp.engine_combo.setCurrentIndex(eng_idx)
        pp.vad_chk.setChecked(w_settings.get("vad_enabled", False))
        pp.vad_model_edit.setText(w_settings.get("vad_model", ""))
        pp.vad_thresh_spin.setValue(w_settings.get("vad_threshold", 0.50))
        pp.vad_spd_spin.setValue(w_settings.get("vad_min_speech_duration_ms", 250))
        pp.vad_sil_spin.setValue(w_settings.get("vad_min_silence_duration_ms", 100))
        pp.groq_concurrency_spin.setValue(int(w_settings.get(
            "groq_concurrency", self.config_manager.get("groq_concurrency", 2))))
        pp.online_fallback_chk.setChecked(bool(w_settings.get(
            "online_fallback_local",
            self.config_manager.get("online_fallback_local", True))))

        preset = self.current_job.settings.get("preset", "balanced")
        if preset in ["standard_lecture", "webcam_lecture", "whiteboard_lecture", "software_demo"]:
            preset = "balanced"
        idx = pp.preset_combo.findText(preset.title())
        pp.preset_combo.setCurrentIndex(idx if idx >= 0 else 1)

        mode = self.current_job.get_product_mode()
        m_idx = pp.product_mode_combo.findData(mode)
        if m_idx >= 0:
            pp.product_mode_combo.setCurrentIndex(m_idx)
        from lecturepack.constants import PRODUCT_MODE_LABELS
        self.mode_lbl.setText(PRODUCT_MODE_LABELS.get(mode, mode))

        sd = self.current_job.settings.get("slide_detection", {})
        crop = sd.get("crop_region", {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})
        pp.crop_selector.crop_rect = QRectF(crop["x"], crop["y"], crop["width"], crop["height"])
        ignores = sd.get("ignore_masks", [])
        pp.crop_selector.ignore_rects = [
            QRectF(i["x"], i["y"], i["width"], i["height"]) for i in ignores]

        preview_png = os.path.join(self.current_job.paths["logs"], "preview.png")
        if os.path.exists(preview_png):
            pp.crop_selector.set_preview_image(preview_png)
        elif os.path.exists(source_path):
            if extract_preview(source_path, preview_png):
                pp.crop_selector.set_preview_image(preview_png)
        else:
            pp.crop_selector.clear_rects()

        meta = self.current_job.source
        if meta:
            pp.metadata_lbl.setText(
                f"{meta.get('width', 0)}x{meta.get('height', 0)}  ·  "
                f"{meta.get('duration', 0.0):.1f}s")
        else:
            pp.metadata_lbl.setText("No metadata available.")

        is_completed = self.current_job.get_stage_status(STAGE_REVIEW_READY) == "completed"
        pp.retranscribe_btn.setEnabled(is_completed)

        if is_completed:
            self._load_review_data()
            self.navigate_to(PAGE_STUDY)
        else:
            self.navigate_to(PAGE_PROCESS)

    # ------------------------------------------------------------------ #
    # processing
    # ------------------------------------------------------------------ #
    def _collect_job_settings(self):
        pp = self.process_page
        job = self.current_job
        preset_name = pp.preset_combo.currentText().lower().replace(" / ", "_").replace(" ", "_")
        job.settings["preset"] = preset_name
        job.settings["product_mode"] = pp.product_mode_combo.currentData()

        w_settings = job.settings.setdefault("whisper", {})
        w_settings["glossary"] = pp.glossary_edit.text().strip()
        w_settings["model"] = self.config_manager.get("whisper_model", "")
        w_settings["profile"] = pp.profile_combo.currentText().lower()
        w_settings["engine"] = pp.engine_combo.currentData()
        w_settings["threads"] = pp.threads_spin.value()
        w_settings["vad_enabled"] = pp.vad_chk.isChecked()
        w_settings["vad_model"] = pp.vad_model_edit.text().strip()
        w_settings["vad_threshold"] = pp.vad_thresh_spin.value()
        w_settings["vad_min_speech_duration_ms"] = pp.vad_spd_spin.value()
        w_settings["vad_min_silence_duration_ms"] = pp.vad_sil_spin.value()
        w_settings["transcription_backend"] = pp.transcription_mode_combo.currentData()
        w_settings["groq_concurrency"] = pp.groq_concurrency_spin.value()
        w_settings["online_fallback_local"] = pp.online_fallback_chk.isChecked()

        # Profile-driven model recommendation (uses downloaded profile models
        # when present; never blocks).
        from lecturepack.infrastructure.transcription_engines import (
            model_search_dirs, resolve_profile_model)
        prof = pp.profile_combo.currentText().lower()
        if prof != "custom":
            found = resolve_profile_model(prof, model_search_dirs(self.config_manager))
            if found:
                w_settings["model"] = found
                self.config_manager.set("whisper_model", found)

        job.settings["slide_detection"]["crop_region"] = {
            "x": pp.crop_selector.crop_rect.x(),
            "y": pp.crop_selector.crop_rect.y(),
            "width": pp.crop_selector.crop_rect.width(),
            "height": pp.crop_selector.crop_rect.height(),
        }
        job.settings["slide_detection"]["ignore_masks"] = [
            {"x": r.x(), "y": r.y(), "width": r.width(), "height": r.height()}
            for r in pp.crop_selector.ignore_rects]
        job.save()

    def _start_processing(self):
        if not self.current_job:
            QMessageBox.warning(self, "No video", "Please select a lecture video first.")
            return
        w_exe = self.config_manager.get("whisper_exe", "")
        w_model = self.config_manager.get("whisper_model", "")
        mode = self.process_page.product_mode_combo.currentData()
        needs_whisper = mode != "slides_only"
        backend = self.process_page.transcription_mode_combo.currentData()
        local_selected = backend == TRANSCRIPTION_BACKEND_LOCAL
        if needs_whisper and local_selected and (not w_exe or not os.path.exists(w_exe)):
            QMessageBox.warning(self, "Whisper Executable",
                                "Configure a valid whisper-cli path in Settings.")
            return
        if needs_whisper and local_selected and (not w_model or not os.path.exists(w_model)):
            QMessageBox.warning(self, "Whisper Model",
                                "Configure a valid Whisper model in Settings.")
            return
        if needs_whisper and not local_selected:
            from lecturepack.infrastructure.secret_store import (
                SecretStoreError, WindowsCredentialStore,
            )
            try:
                if not WindowsCredentialStore().has_secret():
                    QMessageBox.warning(
                        self, "Groq API key",
                        "Store a Groq API key in Settings before using an online mode.")
                    return
            except SecretStoreError as exc:
                QMessageBox.warning(self, "Credential Manager", str(exc))
                return
            accepted = bool(self.current_job.settings.get("whisper", {}).get(
                "online_privacy_accepted", False))
            if not accepted:
                reply = QMessageBox.question(
                    self, "Online transcription privacy",
                    "LecturePack will upload only lossless 16 kHz mono audio chunks "
                    "to Groq for transcription. The lecture video, slide images, "
                    "existing transcripts, and job metadata are not uploaded.\n\n"
                    "Groq usage may be billed and is subject to your account limits. "
                    "Do you consent to this audio upload for this job?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    return
                self.current_job.settings.setdefault("whisper", {})[
                    "online_privacy_accepted"] = True
                self.current_job.save()
        if local_selected and self.process_page.vad_chk.isChecked():
            v_model = self.process_page.vad_model_edit.text().strip()
            if not v_model or not os.path.exists(v_model):
                QMessageBox.warning(self, "VAD Model",
                                    "VAD is enabled, but the VAD model file is missing.")
                return
        self._collect_job_settings()
        self.process_page.reset_progress()
        self._pipeline_timer.restart()
        self._elapsed_timer.start()
        self.navigate_to(PAGE_PROCESS)
        self.controller.run_pipeline()

    def _retranscribe_only_workflow(self):
        if not self.current_job:
            return
        t_dir = self.current_job.paths["transcript"]
        edited_path = os.path.join(t_dir, "edited.json")
        if os.path.exists(edited_path):
            reply = QMessageBox.question(
                self, "Overwrite Transcript Corrections",
                "An active corrected transcript exists. Overwriting it will replace it. "
                "Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                shutil.copy2(edited_path, os.path.join(t_dir, f"edited.bak.{timestamp}.json"))
                os.remove(edited_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to backup existing transcript: {e}")
                return
        raw_json_path = os.path.join(t_dir, "raw.json")
        if os.path.exists(raw_json_path):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                shutil.copy2(raw_json_path, os.path.join(t_dir, f"raw.bak.{timestamp}.json"))
            except Exception:
                pass
        self._collect_job_settings()
        self.process_page.reset_progress()
        self._pipeline_timer.restart()
        self._elapsed_timer.start()
        self.navigate_to(PAGE_PROCESS)
        self.controller.run_retranscribe_only()

    def _cancel_processing(self):
        self.controller.cancel()
        self._elapsed_timer.stop()
        self.sb_stage.setText("Cancelled")

    def _run_detection_preview(self):
        if not self.current_job:
            QMessageBox.warning(self, "No video", "Please select a lecture video first.")
            return
        pp = self.process_page
        crop_region = {
            "x": pp.crop_selector.crop_rect.x(), "y": pp.crop_selector.crop_rect.y(),
            "width": pp.crop_selector.crop_rect.width(),
            "height": pp.crop_selector.crop_rect.height(),
        }
        ignore_masks = [
            {"x": r.x(), "y": r.y(), "width": r.width(), "height": r.height()}
            for r in pp.crop_selector.ignore_rects]
        dialog = DetectionPreviewDialog(
            parent=self,
            video_path=self.current_job.manifest["source"]["original_path"],
            crop_region=crop_region, ignore_masks=ignore_masks,
            current_preset=pp.preset_combo.currentText().lower(),
            job_paths=self.current_job.paths)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # controller feedback
    # ------------------------------------------------------------------ #
    def _connect_controller(self):
        c = self.controller
        c.stage_started.connect(self._on_stage_started)
        c.stage_progress.connect(self._on_stage_progress)
        c.stage_log.connect(self.process_page.on_stage_log)
        c.transcript_segment.connect(self.process_page.on_transcript_segment)
        c.stage_finished.connect(self._on_stage_finished)
        c.stage_cached.connect(self.process_page.mark_stage_cached)
        c.pipeline_completed.connect(self._on_pipeline_completed)
        c.pipeline_failed.connect(self._on_pipeline_failed)
        c.backend_info.connect(self._on_backend_info)

    def _on_stage_started(self, stage):
        self.process_page.on_stage_started(stage)
        self.sb_stage.setText(stage)
        if not self._elapsed_timer.isActive():
            self._pipeline_timer.restart()
            self._elapsed_timer.start()

    def _on_stage_progress(self, stage, percent):
        self.process_page.on_stage_progress(stage, percent)
        self.sb_progress.setValue(percent)

    def _on_stage_finished(self, stage, success, error_msg):
        self.process_page.on_stage_finished(stage, success, error_msg)
        if not success and error_msg:
            self.sb_warn.setText("⚠ " + error_msg[:80])

    def _on_backend_info(self, info):
        self.sb_engine.setText(info)

    def _tick_elapsed(self):
        if self._pipeline_timer.isValid():
            secs = self._pipeline_timer.elapsed() / 1000.0
            m, s = divmod(int(secs), 60)
            self.sb_elapsed.setText(f"{m:d}:{s:02d}")

    def _on_pipeline_completed(self):
        self._elapsed_timer.stop()
        self.sb_stage.setText("Complete")
        self._load_review_data()
        self.navigate_to(PAGE_STUDY)
        self._reload_recent_jobs()
        self._show_status("Processing finished — your Study workspace is ready.")

    def _on_pipeline_failed(self, error_msg):
        self._elapsed_timer.stop()
        self.sb_stage.setText("Failed")
        self.sb_warn.setText("⚠ " + (error_msg or "")[:80])
        QMessageBox.critical(self, "Pipeline Error",
                             f"Processing failed: {error_msg}\nCheck the logs for details.")

    def _export_outputs(self):
        if not self.current_job:
            return
        self.navigate_to(PAGE_EXPORTS)
        self.controller.export_now()
        self.controller.stage_finished.connect(self._on_export_stage_finished)

    def _on_export_stage_finished(self, stage, success, error_msg):
        if stage == STAGE_EXPORT:
            try:
                self.controller.stage_finished.disconnect(self._on_export_stage_finished)
            except Exception:
                pass
            self.exports_page.refresh_artifacts()
            if success:
                self._show_status("All outputs exported successfully.")
            else:
                QMessageBox.critical(self, "Export Failed", f"Failed to export: {error_msg}")

    # ------------------------------------------------------------------ #
    # diagnostics / capability detection
    # ------------------------------------------------------------------ #
    def _refresh_diagnostics(self):
        diag = self.config_manager.check_diagnostics()

        def _fmt(key, label):
            e = diag[key]
            return f"{label}: {'OK' if e['valid'] else 'missing'}"

        text = " · ".join([_fmt("ffmpeg", "FFmpeg"), _fmt("ffprobe", "FFprobe"),
                           _fmt("whisper_cli", "whisper-cli"),
                           _fmt("whisper_model", "Model"), _fmt("data_dir", "Data")])
        self.process_page.set_diagnostics_text(text)

        from lecturepack.infrastructure.transcription_engines import EngineRegistry
        reg = EngineRegistry(self.config_manager)
        resolved = reg.resolve(self.config_manager.get("engine", "auto"))
        selected_backend = self.process_page.transcription_mode_combo.currentData()
        if selected_backend == TRANSCRIPTION_BACKEND_LOCAL:
            self.process_page.set_engine_status(
                f"Engine: {resolved.label} — {resolved.reason or 'default'}")
            self.sb_engine.setText(f"{resolved.key}")
        else:
            label = self.process_page.transcription_mode_combo.currentText()
            self.process_page.set_engine_status(
                f"Backend: {label} — credential status is shown in Settings")
            self.sb_engine.setText(label)

        w_exe = self.config_manager.get("whisper_exe", "")
        base_ok = diag["ffmpeg"]["valid"] and diag["ffprobe"]["valid"]
        needs_transcript = self.process_page.product_mode_combo.currentData() != "slides_only"
        local_selected = (self.process_page.transcription_mode_combo.currentData()
                          == TRANSCRIPTION_BACKEND_LOCAL)
        deps_ok = base_ok and (not needs_transcript or not local_selected or
                               (diag["whisper_cli"]["valid"] and
                                diag["whisper_model"]["valid"]))
        self.process_page.start_btn.setEnabled(bool(deps_ok))
        if selected_backend == TRANSCRIPTION_BACKEND_LOCAL and w_exe and os.path.exists(w_exe):
            self.whisper_detector.detect(w_exe)

    def _on_whisper_detection_finished(self, exe_path, caps):
        self.current_whisper_caps = caps
        if self.current_job is not None:
            actual = (self.current_job.state.get("stages", {})
                      .get(STAGE_TRANSCRIBE, {}).get("backend_used"))
            if actual:
                self.sb_engine.setText(f"loaded backend: {actual}")
                return
        backend = caps.get("backend", "CPU")
        version = caps.get("version", "?")
        model = os.path.basename(self.config_manager.get("whisper_model", "") or "—")
        self.sb_engine.setText(f"whisper.cpp v{version} · {backend} · {model}")

    # ------------------------------------------------------------------ #
    # shortcuts
    # ------------------------------------------------------------------ #
    def _init_shortcuts(self):
        def sc(seq, slot):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(slot)
            return s

        self.shortcut_delete = sc("Delete", self._on_delete_shortcut)
        self.shortcut_r = sc("R", self._on_r_shortcut)
        self.shortcut_undo = sc("Ctrl+Z", self._on_undo_shortcut)
        self.shortcut_redo = sc("Ctrl+Y", self._on_redo_shortcut)
        self.shortcut_copy = sc("Ctrl+C", self._on_ctrl_c_shortcut)
        self.shortcut_focus_search = sc("Ctrl+F", self._focus_search)
        self.shortcut_save = sc("Ctrl+S", self._on_save_action)
        self.shortcut_f3 = sc("F3", self._search_next)
        self.shortcut_shift_f3 = sc("Shift+F3", self._search_prev)
        self.shortcut_select_all = sc("Ctrl+A", self._on_select_all)
        self.shortcut_focus = sc("Ctrl+Shift+F", self.focus_mode.toggle)
        self.shortcut_escape = sc("Esc", self._on_escape)

    def _on_escape(self):
        if self.focus_mode.is_active():
            self.focus_mode.exit()

    def _on_delete_shortcut(self):
        if self.stack.currentIndex() == PAGE_REVIEW:
            self.review_page.handle_key_delete()

    def _on_r_shortcut(self):
        if self.stack.currentIndex() == PAGE_REVIEW:
            self.review_page.handle_key_restore()

    def _on_undo_shortcut(self):
        page = self.stack.currentIndex()
        if page == PAGE_REVIEW:
            self.review_page.undo_review_action()
        elif page == PAGE_TRANSCRIPT:
            self.transcript_page.undo()

    def _on_redo_shortcut(self):
        if self.stack.currentIndex() == PAGE_TRANSCRIPT:
            self.transcript_page.redo()

    def _on_ctrl_c_shortcut(self):
        page = self.stack.currentIndex()
        focused = self.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit)):
            if isinstance(focused, QLineEdit) and focused.hasSelectedText():
                return
            if isinstance(focused, QTextEdit) and focused.textCursor().hasSelection():
                return
        if page == PAGE_REVIEW:
            self.review_page._copy_current_transcript()
        elif page == PAGE_TRANSCRIPT:
            self.transcript_page.copy_selected_segments()

    def _focus_search(self):
        page = self.stack.currentIndex()
        if page == PAGE_REVIEW:
            self.review_page.focus_search()
        elif page == PAGE_TRANSCRIPT:
            self.transcript_page.focus_search()

    def _search_next(self):
        page = self.stack.currentIndex()
        if page == PAGE_REVIEW:
            self.review_page._search_next()
        elif page == PAGE_TRANSCRIPT:
            self.transcript_page.search_next()

    def _search_prev(self):
        page = self.stack.currentIndex()
        if page == PAGE_REVIEW:
            self.review_page._search_prev()
        elif page == PAGE_TRANSCRIPT:
            self.transcript_page.search_prev()

    def _on_select_all(self):
        if self.stack.currentIndex() == PAGE_REVIEW \
                and self.review_page.slides_view.hasFocus():
            self.review_page.select_all_slides()

    def _on_save_action(self):
        page = self.stack.currentIndex()
        if page == PAGE_TRANSCRIPT:
            self.transcript_page.save()
        else:
            self.review_page._save_corrections()

    # ------------------------------------------------------------------ #
    # cross-page sync
    # ------------------------------------------------------------------ #
    def _save_study_position(self, page, timestamp):
        if self.current_job is None:
            return
        from lecturepack.services import study_service
        study_service.save_position(
            self.current_job, page=page, timestamp_seconds=float(timestamp))

    def _on_study_navigation(self, destination):
        mapping = {
            "study": PAGE_STUDY,
            "review": PAGE_REVIEW,
            "transcript": PAGE_TRANSCRIPT,
            "corrections": PAGE_TRANSCRIPT,
            "exports": PAGE_EXPORTS,
        }
        self.navigate_to(mapping.get(destination, PAGE_STUDY))
        if destination == "corrections":
            self.transcript_page.tabs.setCurrentIndex(1)

    def _resume_study_position(self, page, timestamp):
        self._on_study_navigation(page)
        if page in ("review", "transcript", "corrections"):
            self.review_page.select_slide_near(float(timestamp))
        self._show_status(f"Resumed {page} at {timestamp:.0f}s.")

    def _on_transcript_seek(self, timestamp):
        self.review_page.select_slide_near(timestamp)
        self._show_status(f"Selected slide near {timestamp:.0f}s (see Review page).")

    def _open_context_repair(self):
        """From Review: open the Transcript page's Context Repair tab."""
        self.navigate_to(PAGE_TRANSCRIPT)
        if self.transcript_page.job is None and self.current_job is not None:
            self.transcript_page.load_job(self.current_job)
        self.transcript_page.tabs.setCurrentIndex(3)

    # ------------------------------------------------------------------ #
    # archive / restore
    # ------------------------------------------------------------------ #
    def _archive_current_job(self):
        if not self.current_job:
            return
        reply = QMessageBox.question(
            self, "Archive Job",
            f"Are you sure you want to archive job '{self.current_job.manifest.get('title')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                FileManager.archive_job(self.config_manager.data_dir, self.current_job.job_id)
                self.current_job = None
                self.controller.set_job(None)
                self.study_page.load_job(None)
                self.process_page.video_path_edit.clear()
                self.process_page.glossary_edit.clear()
                self.process_page.metadata_lbl.setText("No video loaded.")
                self.header_bar.set_breadcrumb("Home")
                self._reload_recent_jobs()
                self.recent_jobs_combo.setCurrentIndex(0)
                self._show_status("Job archived (nothing was deleted).")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to archive job: {e}")

    def _restore_archived_job(self):
        dlg = RestoreDialog(self.config_manager.data_dir, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            job_id = dlg.get_selected_job_id()
            if job_id:
                try:
                    FileManager.restore_job(self.config_manager.data_dir, job_id)
                    self._reload_recent_jobs()
                    for i in range(self.recent_jobs_combo.count()):
                        data = self.recent_jobs_combo.itemData(i)
                        if data and data[0] == job_id:
                            self.recent_jobs_combo.setCurrentIndex(i)
                            break
                    self._show_status("Job restored successfully.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to restore job: {e}")

    def _export_job_archive(self):
        if not self.current_job:
            return
        default_name = self.current_job.manifest.get("title", "job_archive") + "_archive.zip"
        zip_path, _ = QFileDialog.getSaveFileName(self, "Export Job Archive",
                                                  default_name, "Zip Files (*.zip)")
        if zip_path:
            try:
                FileManager.export_job_archive(self.current_job.paths["root"], zip_path)
                self._show_status("Job archive exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export archive: {e}")

    # ------------------------------------------------------------------ #
    def _open_output_folder(self):
        if self.current_job:
            exports_dir = self.current_job.paths["exports"]
            os.startfile(exports_dir)

    def closeEvent(self, event):
        self.controller.cancel()
        self.whisper_detector.cancel()
        self.transcript_page.shutdown()
        self.review_page.slides_view.shutdown()
        self.study_page.slides_grid.shutdown()
        self.study_page.shutdown()
        self._persist_ui_state()
        super().closeEvent(event)


class DetectionPreviewDialog(QDialog):
    def __init__(self, parent, video_path, crop_region, ignore_masks, current_preset, job_paths):
        super().__init__(parent)
        self.setWindowTitle("Preview Detection")
        self.resize(760, 620)
        self.setMinimumSize(600, 500)

        self.video_path = video_path
        self.crop_region = crop_region
        self.ignore_masks = ignore_masks
        self.current_preset = current_preset
        self.job_paths = job_paths
        self.worker = None

        layout = QVBoxLayout(self)

        inputs_layout = QHBoxLayout()
        inputs_layout.addWidget(QLabel("Start (s):"))
        self.start_edit = QLineEdit("0.0")
        self.start_edit.setToolTip("Start time in seconds or MM:SS format")
        inputs_layout.addWidget(self.start_edit)
        inputs_layout.addWidget(QLabel("End (s):"))
        self.end_edit = QLineEdit("120.0")
        self.end_edit.setToolTip("End time in seconds or MM:SS format")
        inputs_layout.addWidget(self.end_edit)
        inputs_layout.addWidget(QLabel("Sensitivity:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Conservative", "Balanced", "Detailed"])
        idx = self.preset_combo.findText(current_preset.title())
        self.preset_combo.setCurrentIndex(idx if idx >= 0 else 1)
        inputs_layout.addWidget(self.preset_combo)
        self.run_btn = QPushButton("Run Preview")
        self.run_btn.setProperty("primary", True)
        self.run_btn.clicked.connect(self.run_preview)
        inputs_layout.addWidget(self.run_btn)
        layout.addLayout(inputs_layout)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        from PySide6.QtWidgets import QTableWidget, QHeaderView
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Thumbnail", "Timestamp", "Reason", "Confidence", "Changed Ratio"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self.summary_lbl = QLabel("Total candidates: 0")
        self.summary_lbl.setProperty("h2", True)
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
            QMessageBox.critical(self, "Invalid Time Format",
                                 "Please enter valid times in seconds or HH:MM:SS format.")
            return

        self.run_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.progress.setValue(0)

        from lecturepack.constants import PRESETS
        preset_name = self.preset_combo.currentText().lower()
        preset_settings = PRESETS.get(preset_name, PRESETS["balanced"])

        from lecturepack.infrastructure.cv_engine import SlideDetectorWorker
        preview_candidates_dir = os.path.join(self.job_paths["root"], "preview_candidates")
        os.makedirs(preview_candidates_dir, exist_ok=True)
        preview_job_paths = self.job_paths.copy()
        preview_job_paths["candidates"] = preview_candidates_dir

        self.worker = SlideDetectorWorker(
            video_path=self.video_path, crop_region=self.crop_region,
            ignore_masks=self.ignore_masks, preset_settings=preset_settings,
            job_paths=preview_job_paths, start_time=start_val, end_time=end_val)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(
            lambda success, error, candidates: self.on_detection_finished(
                success, error, candidates, preview_candidates_dir))
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
            self.table.setItem(i, 1, QTableWidgetItem(
                f"{c['timestamp_formatted']}\n({c['timestamp_seconds']:.2f}s)"))
            self.table.setItem(i, 2, QTableWidgetItem(
                f"{c['detector_path']}\n({c['decision_reason']})"))
            self.table.setItem(i, 3, QTableWidgetItem(
                f"Score: {c.get('combined_score', 0.0):.3f}\n"
                f"Baseline: {c.get('rolling_baseline_score', 0.0):.3f}"))
            self.table.setItem(i, 4, QTableWidgetItem(
                f"{c.get('changed_area_ratio', 0.0) * 100:.1f}%"))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        preview_candidates_dir = os.path.join(self.job_paths["root"], "preview_candidates")
        if os.path.exists(preview_candidates_dir):
            try:
                shutil.rmtree(preview_candidates_dir, ignore_errors=True)
            except Exception:
                pass
        super().closeEvent(event)
