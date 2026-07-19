"""Study workspace: the Phase 2 spatial reading room.

Layout: a ``QSplitter`` with the accepted-slide timeline (existing
``SlideGridWidget``) on the left and the working transcript on the right,
rendered as lazily-materialized ``TranscriptBlockWidget`` cards. The v1.2
overview (summary, key terms, topics, bookmarks, quick actions) lives in a
collapsible card above the transcript; every v1.2 public attribute, object
name and signal is preserved.

Bidirectional sync: clicking a slide smooth-scrolls the transcript to the
containing segment; scrolling the transcript (debounced inside
``TranscriptStreamView``) selects the nearest slide. Feedback loops are
prevented by two guards: ``_sync_guard`` while the transcript drives the
slide grid, and ``_programmatic_scroll`` while the smooth-scroll animation
runs after a slide-driven seek.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from lecturepack.constants import STAGE_REVIEW_READY
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import study_service
from lecturepack.services import transcript_store as store
from lecturepack.services.transcript_formats import fmt_clock
from lecturepack.ui import theme
from lecturepack.ui.widgets.slide_grid import CAND_ROLE, SlideGridWidget
from lecturepack.ui.widgets.transcript_block import (
    TranscriptStreamView, find_segment_index, find_slide_index,
)


class StudyPage(QWidget):
    navigate_requested = Signal(str)
    seek_requested = Signal(float)
    resume_requested = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.job = None
        self.overview = None
        self._candidates = []
        self._segments = []
        self._sync_guard = False
        self._programmatic_scroll = False
        self._build_ui()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
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

        # ---- left: slide timeline ------------------------------------- #
        slides_panel = QWidget()
        slides_layout = QVBoxLayout(slides_panel)
        slides_layout.setContentsMargins(0, 0, 0, 0)
        slides_title = QLabel("Slides")
        slides_title.setProperty("h2", True)
        slides_layout.addWidget(slides_title)
        self.slides_grid = SlideGridWidget()
        self.slides_grid.setObjectName("studySlidesGrid")
        slides_layout.addWidget(self.slides_grid, 1)
        self.content.addWidget(slides_panel)

        # ---- right: overview card + transcript ------------------------- #
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        self.overview_card = QFrame()
        self.overview_card.setProperty("card", True)
        self.overview_card.setObjectName("studyOverviewCard")
        card_layout = QVBoxLayout(self.overview_card)
        self.overview_toggle = QToolButton()
        self.overview_toggle.setObjectName("studyOverviewToggle")
        self.overview_toggle.setText("Overview")
        self.overview_toggle.setCheckable(True)
        self.overview_toggle.setChecked(True)
        self.overview_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.overview_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.overview_toggle.toggled.connect(self._on_overview_toggled)
        card_layout.addWidget(self.overview_toggle)

        self.overview_body = QWidget()
        body = QVBoxLayout(self.overview_body)
        body.setContentsMargins(0, 0, 0, 0)

        self.meta_lbl = QLabel()
        self.meta_lbl.setObjectName("studyMetadata")
        self.meta_lbl.setWordWrap(True)
        self.meta_lbl.setProperty("muted", True)
        body.addWidget(self.meta_lbl)

        summary_title = QLabel("Lecture overview")
        summary_title.setProperty("h2", True)
        body.addWidget(summary_title)
        self.summary_lbl = QLabel()
        self.summary_lbl.setObjectName("studySummary")
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(self.summary_lbl)
        self.summary_source_lbl = QLabel()
        self.summary_source_lbl.setProperty("muted", True)
        body.addWidget(self.summary_source_lbl)

        terms_title = QLabel("Key terms")
        terms_title.setProperty("h2", True)
        body.addWidget(terms_title)
        self.terms_lbl = QLabel()
        self.terms_lbl.setObjectName("studyKeyTerms")
        self.terms_lbl.setWordWrap(True)
        body.addWidget(self.terms_lbl)

        actions_title = QLabel("Continue studying")
        actions_title.setProperty("h2", True)
        body.addWidget(actions_title)
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
        actions.addStretch(1)
        body.addLayout(actions)

        nav_row = QHBoxLayout()
        topics_col = QVBoxLayout()
        topics_title = QLabel("Topics")
        topics_title.setProperty("h2", True)
        topics_col.addWidget(topics_title)
        self.topics_list = QListWidget()
        self.topics_list.setObjectName("studyTopicsList")
        self.topics_list.setMaximumHeight(130)
        self.topics_list.itemActivated.connect(self._open_topic)
        topics_col.addWidget(self.topics_list)
        nav_row.addLayout(topics_col, 1)

        bookmarks_col = QVBoxLayout()
        self.slides_bookmarks_lbl = QLabel("Slide bookmarks")
        self.slides_bookmarks_lbl.setProperty("muted", True)
        bookmarks_col.addWidget(self.slides_bookmarks_lbl)
        self.slide_bookmarks = QListWidget()
        self.slide_bookmarks.setObjectName("studySlideBookmarks")
        self.slide_bookmarks.setMaximumHeight(60)
        self.slide_bookmarks.itemActivated.connect(self._open_bookmark)
        bookmarks_col.addWidget(self.slide_bookmarks)
        self.section_bookmarks_lbl = QLabel("Section bookmarks")
        self.section_bookmarks_lbl.setProperty("muted", True)
        bookmarks_col.addWidget(self.section_bookmarks_lbl)
        self.section_bookmarks = QListWidget()
        self.section_bookmarks.setObjectName("studySectionBookmarks")
        self.section_bookmarks.setMaximumHeight(60)
        self.section_bookmarks.itemActivated.connect(self._open_bookmark)
        bookmarks_col.addWidget(self.section_bookmarks)
        nav_row.addLayout(bookmarks_col, 1)
        body.addLayout(nav_row)

        card_layout.addWidget(self.overview_body)
        theme.add_card_shadow(self.overview_card)
        right_layout.addWidget(self.overview_card)

        transcript_title = QLabel("Transcript")
        transcript_title.setProperty("h2", True)
        right_layout.addWidget(transcript_title)
        self.transcript_view = TranscriptStreamView()
        right_layout.addWidget(self.transcript_view, 1)
        self.content.addWidget(right)

        self.content.setStretchFactor(0, 2)
        self.content.setStretchFactor(1, 3)
        root.addWidget(self.content, 1)

        # ---- bidirectional sync wiring ---------------------------------- #
        self.slides_grid.currentItemChanged.connect(
            self._on_slide_current_changed)
        self.transcript_view.viewed_index_changed.connect(
            self._on_transcript_viewed)
        self.transcript_view.block_activated.connect(self._select_slide_near)

        self._set_empty(True)

    def _on_overview_toggled(self, checked: bool):
        self.overview_body.setVisible(checked)
        self.overview_toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    # ------------------------------------------------------------------ #
    # state
    # ------------------------------------------------------------------ #
    def _set_empty(self, empty: bool):
        self.empty_lbl.setVisible(empty)
        self.content.setVisible(not empty)
        self.resume_btn.setVisible(not empty)

    def load_job(self, job):
        self.job = job
        self.refresh()

    def _clear_workspace(self):
        self._candidates = []
        self._segments = []
        self.slides_grid.shutdown()
        self.slides_grid.clear()
        self.transcript_view.clear()

    def _load_workspace(self):
        """Populate slides + transcript blocks for the spatial workspace."""
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, []) or []
        accepted = [c for c in candidates if c.get("decision") != "rejected"]
        accepted.sort(key=lambda c: float(c.get("timestamp_seconds", 0.0)))
        self._candidates = accepted
        self.slides_grid.load_candidates(accepted, self.job.paths)
        self._segments = store.load_working(self.job.paths) or []
        self.transcript_view.set_segments(self._segments)

    def refresh(self):
        if self.job is None:
            self.overview = None
            self.title_lbl.setText("Study")
            self._clear_workspace()
            self._set_empty(True)
            return
        if self.job.get_stage_status(STAGE_REVIEW_READY) != "completed":
            self.overview = None
            self.title_lbl.setText(self.job.manifest.get("title", "Study"))
            self.empty_lbl.setText(
                "The Study workspace will be ready when lecture processing completes.")
            self._clear_workspace()
            self._set_empty(True)
            return
        self.empty_lbl.setText(
            "No completed lecture is open. Process a lecture or choose one from Home.")
        self.overview = study_service.build_overview(self.job)
        overview = self.overview
        self._set_empty(False)
        self._load_workspace()
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

    # ------------------------------------------------------------------ #
    # bidirectional slide <-> transcript sync
    # ------------------------------------------------------------------ #
    def _on_slide_current_changed(self, current, _previous):
        if self._sync_guard or current is None:
            return
        candidate = current.data(CAND_ROLE)
        if isinstance(candidate, dict):
            self._seek_transcript(float(candidate.get("timestamp_seconds", 0.0)))

    def _on_transcript_viewed(self, index: int):
        if self._programmatic_scroll:
            return
        segment = self.transcript_view.segment_at(index)
        if segment:
            self._select_slide_near(float(segment.get("start", 0.0)))

    def _select_slide_near(self, timestamp: float):
        index = find_slide_index(self._candidates, timestamp)
        if index < 0 or index == self.slides_grid.currentRow():
            return
        self._sync_guard = True
        try:
            self.slides_grid.setCurrentRow(index)
        finally:
            self._sync_guard = False

    def _seek_transcript(self, timestamp: float):
        index = find_segment_index(self._segments, timestamp)
        if index < 0:
            return
        self._programmatic_scroll = True
        self.transcript_view.select_index(index)
        animation = self.transcript_view.scroll_to_index(index, smooth=True)
        if animation is not None:
            animation.finished.connect(self._release_programmatic_scroll)
        else:
            self._programmatic_scroll = False

    def _release_programmatic_scroll(self):
        self._programmatic_scroll = False

    # ------------------------------------------------------------------ #
    # v1.2 navigation behavior (unchanged)
    # ------------------------------------------------------------------ #
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
