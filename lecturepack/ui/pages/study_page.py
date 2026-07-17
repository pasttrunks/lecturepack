"""Study workspace: a deterministic landing page for completed lectures."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from lecturepack.services import study_service
from lecturepack.services.transcript_formats import fmt_clock
from lecturepack.constants import STAGE_REVIEW_READY


class StudyPage(QWidget):
    navigate_requested = Signal(str)
    seek_requested = Signal(float)
    resume_requested = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.job = None
        self.overview = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)

        title_row = QHBoxLayout()
        self.title_lbl = QLabel("Study")
        self.title_lbl.setProperty("h1", True)
        self.title_lbl.setObjectName("studyTitle")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch(1)
        self.resume_btn = QPushButton("Resume where I left off")
        self.resume_btn.setProperty("primary", True)
        self.resume_btn.setObjectName("studyResumeButton")
        self.resume_btn.clicked.connect(self._resume)
        title_row.addWidget(self.resume_btn)
        root.addLayout(title_row)

        self.empty_lbl = QLabel(
            "No completed lecture is open. Process a lecture or choose one from Home.")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setProperty("muted", True)
        self.empty_lbl.setWordWrap(True)
        self.empty_lbl.setObjectName("studyEmptyState")
        root.addWidget(self.empty_lbl, 1)

        self.content = QSplitter(Qt.Orientation.Horizontal)
        self.content.setObjectName("studySplitter")

        # Topics
        topics = QWidget()
        topics_layout = QVBoxLayout(topics)
        topics_layout.setContentsMargins(0, 0, 0, 0)
        topics_title = QLabel("Topics")
        topics_title.setProperty("h2", True)
        topics_layout.addWidget(topics_title)
        self.topics_list = QListWidget()
        self.topics_list.setObjectName("studyTopicsList")
        self.topics_list.itemActivated.connect(self._open_topic)
        topics_layout.addWidget(self.topics_list, 1)
        self.content.addWidget(topics)

        # Overview
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(8, 0, 8, 0)
        self.meta_lbl = QLabel()
        self.meta_lbl.setObjectName("studyMetadata")
        self.meta_lbl.setWordWrap(True)
        center_layout.addWidget(self.meta_lbl)

        summary_card = QFrame()
        summary_card.setFrameShape(QFrame.Shape.StyledPanel)
        summary_layout = QVBoxLayout(summary_card)
        summary_title = QLabel("Lecture overview")
        summary_title.setProperty("h2", True)
        summary_layout.addWidget(summary_title)
        self.summary_lbl = QLabel()
        self.summary_lbl.setObjectName("studySummary")
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_layout.addWidget(self.summary_lbl)
        self.summary_source_lbl = QLabel()
        self.summary_source_lbl.setProperty("muted", True)
        summary_layout.addWidget(self.summary_source_lbl)
        center_layout.addWidget(summary_card)

        terms_card = QFrame()
        terms_card.setFrameShape(QFrame.Shape.StyledPanel)
        terms_layout = QVBoxLayout(terms_card)
        terms_title = QLabel("Key terms")
        terms_title.setProperty("h2", True)
        terms_layout.addWidget(terms_title)
        self.terms_lbl = QLabel()
        self.terms_lbl.setObjectName("studyKeyTerms")
        self.terms_lbl.setWordWrap(True)
        terms_layout.addWidget(self.terms_lbl)
        center_layout.addWidget(terms_card)

        actions_title = QLabel("Continue studying")
        actions_title.setProperty("h2", True)
        center_layout.addWidget(actions_title)
        actions = QHBoxLayout()
        for text, target, object_name in (
            ("Read transcript", "transcript", "studyReadTranscript"),
            ("Review slides", "review", "studyReviewSlides"),
            ("Review corrections", "corrections", "studyReviewCorrections"),
            ("Export study pack", "exports", "studyExportPack"),
        ):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.clicked.connect(
                lambda checked=False, destination=target:
                self.navigate_requested.emit(destination))
            actions.addWidget(button)
        center_layout.addLayout(actions)
        center_layout.addStretch(1)
        scroll.setWidget(center)
        self.content.addWidget(scroll)

        # Bookmarks
        bookmarks = QWidget()
        bookmarks_layout = QVBoxLayout(bookmarks)
        bookmarks_layout.setContentsMargins(0, 0, 0, 0)
        bookmarks_title = QLabel("Bookmarks & notes")
        bookmarks_title.setProperty("h2", True)
        bookmarks_layout.addWidget(bookmarks_title)
        self.slides_bookmarks_lbl = QLabel("Slides")
        self.slides_bookmarks_lbl.setProperty("muted", True)
        bookmarks_layout.addWidget(self.slides_bookmarks_lbl)
        self.slide_bookmarks = QListWidget()
        self.slide_bookmarks.setObjectName("studySlideBookmarks")
        self.slide_bookmarks.itemActivated.connect(self._open_bookmark)
        bookmarks_layout.addWidget(self.slide_bookmarks, 1)
        self.section_bookmarks_lbl = QLabel("Sections")
        self.section_bookmarks_lbl.setProperty("muted", True)
        bookmarks_layout.addWidget(self.section_bookmarks_lbl)
        self.section_bookmarks = QListWidget()
        self.section_bookmarks.setObjectName("studySectionBookmarks")
        self.section_bookmarks.itemActivated.connect(self._open_bookmark)
        bookmarks_layout.addWidget(self.section_bookmarks, 1)
        self.content.addWidget(bookmarks)

        self.content.setStretchFactor(0, 2)
        self.content.setStretchFactor(1, 5)
        self.content.setStretchFactor(2, 3)
        root.addWidget(self.content, 1)
        self._set_empty(True)

    def _set_empty(self, empty: bool):
        self.empty_lbl.setVisible(empty)
        self.content.setVisible(not empty)
        self.resume_btn.setVisible(not empty)

    def load_job(self, job):
        self.job = job
        self.refresh()

    def refresh(self):
        if self.job is None:
            self.overview = None
            self.title_lbl.setText("Study")
            self._set_empty(True)
            return
        if self.job.get_stage_status(STAGE_REVIEW_READY) != "completed":
            self.overview = None
            self.title_lbl.setText(self.job.manifest.get("title", "Study"))
            self.empty_lbl.setText(
                "The Study workspace will be ready when lecture processing completes.")
            self._set_empty(True)
            return
        self.empty_lbl.setText(
            "No completed lecture is open. Process a lecture or choose one from Home.")
        self.overview = study_service.build_overview(self.job)
        overview = self.overview
        self._set_empty(False)
        self.title_lbl.setText(overview["title"])
        duration = fmt_clock(overview["duration_seconds"])
        self.meta_lbl.setText(
            f"{duration}  ·  {overview['accepted_slide_count']} accepted slides  ·  "
            f"{overview['transcript_segment_count']} transcript segments\n"
            f"Mode: {overview['product_mode']}  ·  Loaded backend: {overview['backend']}  ·  "
            f"Needs review: {overview['needs_review_count']}")
        self.summary_lbl.setText(overview["summary"])
        self.summary_source_lbl.setText(f"Source: {overview['summary_source']}")
        self.terms_lbl.setText("  ·  ".join(overview["key_terms"]) or "No key terms yet.")

        self.topics_list.clear()
        for section in overview["sections"]:
            source = " (AI)" if section.get("heading_source") == "ai" else ""
            item = QListWidgetItem(
                f"{fmt_clock(section['start'])}  {section['heading']}{source}")
            item.setData(Qt.ItemDataRole.UserRole, float(section["start"]))
            self.topics_list.addItem(item)
        if not overview["sections"]:
            item = QListWidgetItem("No aligned topics yet")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.topics_list.addItem(item)

        self.slide_bookmarks.clear()
        slide_entries = sorted(
            overview["bookmarked_slides"].values(),
            key=lambda entry: float(entry.get("timestamp_seconds", 0.0)))
        for entry in slide_entries:
            if not (entry.get("bookmarked") or entry.get("note")):
                continue
            note = str(entry.get("note") or "").strip()
            label = f"{fmt_clock(float(entry.get('timestamp_seconds', 0.0)))}"
            if entry.get("bookmarked"):
                label = "★ " + label
            if note:
                label += f" — {note}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole,
                         float(entry.get("timestamp_seconds", 0.0)))
            self.slide_bookmarks.addItem(item)
        if self.slide_bookmarks.count() == 0:
            item = QListWidgetItem("No slide bookmarks or notes")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.slide_bookmarks.addItem(item)

        self.section_bookmarks.clear()
        section_entries = sorted(
            overview["bookmarked_sections"].values(),
            key=lambda entry: float(entry.get("start", 0.0)))
        for entry in section_entries:
            item = QListWidgetItem(
                f"★ {fmt_clock(float(entry.get('start', 0.0)))}  "
                f"{entry.get('heading', 'Untitled section')}")
            item.setData(Qt.ItemDataRole.UserRole, float(entry.get("start", 0.0)))
            self.section_bookmarks.addItem(item)
        if self.section_bookmarks.count() == 0:
            item = QListWidgetItem("No section bookmarks")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.section_bookmarks.addItem(item)

        position = overview["last_position"]
        self.resume_btn.setEnabled(bool(position))
        if position:
            self.resume_btn.setText(
                f"Resume {position.get('page', 'study')} at "
                f"{fmt_clock(float(position.get('timestamp_seconds', 0.0)))}")
        else:
            self.resume_btn.setText("Resume where I left off")

    def _open_topic(self, item: QListWidgetItem):
        value = item.data(Qt.ItemDataRole.UserRole)
        if value is not None:
            self.navigate_requested.emit("transcript")
            self.seek_requested.emit(float(value))

    def _open_bookmark(self, item: QListWidgetItem):
        value = item.data(Qt.ItemDataRole.UserRole)
        if value is not None:
            self.navigate_requested.emit("review")
            self.seek_requested.emit(float(value))

    def _resume(self):
        if not self.overview:
            return
        position = self.overview.get("last_position") or {}
        if position:
            self.resume_requested.emit(
                str(position.get("page") or "review"),
                float(position.get("timestamp_seconds", 0.0)))
