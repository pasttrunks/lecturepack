"""Study workspace: the Phase 2 spatial reading room.

Layout: a ``QSplitter`` with the accepted-slide timeline (existing
``SlideGridWidget``) on the left and the working transcript on the right,
rendered as lazily-materialized ``TranscriptBlockWidget`` cards. The v1.2
overview (summary, key terms, topics, bookmarks, quick actions) lives in a
collapsible card above the transcript; every v1.2 public attribute, object
name and signal is preserved.

Studio 3-column layout:
  - Left (210px): topics list
  - Center: overview card + assistant / transcript
  - Right (240px): bookmarks + stats

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
    QScrollArea, QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from lecturepack.constants import STAGE_REVIEW_READY
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import study_service
from lecturepack.services import transcript_store as store
from lecturepack.services.transcript_formats import fmt_clock
from lecturepack.ui import theme
from lecturepack.ui.widgets.slide_grid import CAND_ROLE, SlideGridWidget
from lecturepack.ui.widgets.study_assistant_panel import StudyAssistantPanel
from lecturepack.ui.widgets.timeline_spine import TopicTimeline
from lecturepack.ui.widgets.transcript_block import (
    TranscriptStreamView, find_segment_index, find_slide_index,
)


class StudyPage(QWidget):
    navigate_requested = Signal(str)
    seek_requested = Signal(float)
    resume_requested = Signal(str, float)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.job = None
        self.overview = None
        self._candidates = []
        self._segments = []
        self._sync_guard = False
        self._programmatic_scroll = False
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(44, 30, 44, 52)
        cl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        wrapper = QWidget()
        wrapper.setMaximumWidth(1140)
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(16)

        title_row = QHBoxLayout()
        self.title_lbl = QLabel("Study")
        self.title_lbl.setStyleSheet("font-size: 30px; font-weight: 700; letter-spacing: -0.02em;")
        self.title_lbl.setObjectName("studyTitle")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch(1)
        self.resume_btn = QPushButton("Resume where I left off")
        self.resume_btn.setProperty("primary", True)
        self.resume_btn.setObjectName("studyResumeButton")
        self.resume_btn.clicked.connect(self._resume)
        title_row.addWidget(self.resume_btn)
        wl.addLayout(title_row)

        self.empty_lbl = QLabel(
            "No completed lecture is open. Process a lecture or choose one from Home.")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setProperty("muted", True)
        self.empty_lbl.setStyleSheet("font-size: 15px;")
        self.empty_lbl.setWordWrap(True)
        self.empty_lbl.setObjectName("studyEmptyState")
        wl.addWidget(self.empty_lbl, 1)

        self.timeline_card = QFrame()
        self.timeline_card.setProperty("card", True)
        theme.add_card_shadow(self.timeline_card)
        tc_lay = QVBoxLayout(self.timeline_card)
        tc_lay.setContentsMargins(18, 13, 18, 13)
        tc_lay.setSpacing(0)

        tc_head = QHBoxLayout()
        tc_head.setSpacing(12)
        tc_title = QLabel("Study timeline")
        tc_title.setStyleSheet(
            f"font:500 10px '{theme.FONT_MONO}';letter-spacing:0.12em;"
            f"text-transform:uppercase;color:{theme.c('secondary')};border:none;background:transparent;")
        tc_head.addWidget(tc_title)
        self._study_timeline_meta_lbl = QLabel("0 topics · 0 slides")
        self._study_timeline_meta_lbl.setProperty("muted", True)
        self._study_timeline_meta_lbl.setStyleSheet(
            f"font:500 11px '{theme.FONT_MONO}';border:none;background:transparent;")
        tc_head.addWidget(self._study_timeline_meta_lbl)
        tc_head.addStretch(1)
        self._study_bookmarks_count_lbl = QLabel("0 bookmarks")
        self._study_bookmarks_count_lbl.setStyleSheet(
            f"font:500 11px '{theme.FONT_MONO}';color:{theme.c('primary_ink')};border:none;background:transparent;")
        tc_head.addWidget(self._study_bookmarks_count_lbl)
        tc_lay.addLayout(tc_head)
        tc_lay.addSpacing(9)

        self.topic_timeline = TopicTimeline()
        self.topic_timeline.topic_clicked.connect(self._on_topic_timeline_clicked)
        tc_lay.addWidget(self.topic_timeline)
        tc_lay.addSpacing(5)

        self._topic_labels_row = QHBoxLayout()
        tc_lay.addLayout(self._topic_labels_row)
        wl.addWidget(self.timeline_card)

        self.content = QSplitter(Qt.Orientation.Horizontal)
        self.content.setObjectName("studySplitter")

        # ---- left: slide timeline ------------------------------------- #
        slides_panel = QWidget()
        slides_panel.setMinimumWidth(200)
        slides_panel.setMaximumWidth(260)
        slides_layout = QVBoxLayout(slides_panel)
        slides_layout.setContentsMargins(0, 0, 0, 0)
        slides_layout.setSpacing(8)
        slides_title = QLabel("Slides")
        slides_title.setStyleSheet("font-weight: 700; font-size: 16px;")
        slides_layout.addWidget(slides_title)
        self.slides_grid = SlideGridWidget()
        self.slides_grid.setObjectName("studySlidesGrid")
        slides_layout.addWidget(self.slides_grid, 1)
        self.content.addWidget(slides_panel)

        # ---- center: overview + transcript ---------------------------- #
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(14, 0, 14, 0)
        center_layout.setSpacing(10)

        self.overview_card = QFrame()
        self.overview_card.setProperty("card", True)
        self.overview_card.setObjectName("studyOverviewCard")
        theme.add_card_shadow(self.overview_card)
        card_layout = QVBoxLayout(self.overview_card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(8)
        self.overview_toggle = QToolButton()
        self.overview_toggle.setObjectName("studyOverviewToggle")
        self.overview_toggle.setText("Overview")
        self.overview_toggle.setCheckable(True)
        self.overview_toggle.setChecked(True)
        self.overview_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.overview_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.overview_toggle.setStyleSheet("font-weight: 700; font-size: 15px;")
        self.overview_toggle.toggled.connect(self._on_overview_toggled)
        card_layout.addWidget(self.overview_toggle)

        self.overview_body = QWidget()
        body = QVBoxLayout(self.overview_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        self.meta_lbl = QLabel()
        self.meta_lbl.setObjectName("studyMetadata")
        self.meta_lbl.setWordWrap(True)
        self.meta_lbl.setProperty("muted", True)
        self.meta_lbl.setStyleSheet("font-size: 12px;")
        body.addWidget(self.meta_lbl)

        summary_title = QLabel("Lecture overview")
        summary_title.setStyleSheet("font-weight: 700; font-size: 15px;")
        body.addWidget(summary_title)
        self.summary_lbl = QLabel()
        self.summary_lbl.setObjectName("studySummary")
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(self.summary_lbl)
        self.summary_source_lbl = QLabel()
        self.summary_source_lbl.setProperty("muted", True)
        self.summary_source_lbl.setStyleSheet("font-size: 12px;")
        body.addWidget(self.summary_source_lbl)

        terms_title = QLabel("Key terms")
        terms_title.setStyleSheet("font-weight: 700; font-size: 15px;")
        body.addWidget(terms_title)
        self.terms_lbl = QLabel()
        self.terms_lbl.setObjectName("studyKeyTerms")
        self.terms_lbl.setWordWrap(True)
        body.addWidget(self.terms_lbl)

        actions_title = QLabel("Continue studying")
        actions_title.setStyleSheet("font-weight: 700; font-size: 15px;")
        body.addWidget(actions_title)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        for text, target, object_name in (
            ("Read transcript", "transcript", "studyReadTranscript"),
            ("Review slides", "review", "studyReviewSlides"),
            ("Review corrections", "corrections", "studyReviewCorrections"),
            ("Export study pack", "exports", "studyExportPack"),
        ):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setProperty("softPanel", True)
            button.setStyleSheet("font: 600 13px sans-serif; padding: 7px 14px; border-radius: 7px;")
            button.clicked.connect(
                lambda checked=False, destination=target:
                self.navigate_requested.emit(destination))
            actions.addWidget(button)
        actions.addStretch(1)
        body.addLayout(actions)
        card_layout.addWidget(self.overview_body)
        center_layout.addWidget(self.overview_card)

        self.center_tabs = QTabWidget()
        self.center_tabs.setObjectName("studyCenterTabs")

        transcript_tab = QWidget()
        tt_lay = QVBoxLayout(transcript_tab)
        tt_lay.setContentsMargins(0, 8, 0, 0)
        self.transcript_view = TranscriptStreamView()
        tt_lay.addWidget(self.transcript_view, 1)
        self.center_tabs.addTab(transcript_tab, "Transcript")

        self.assistant_panel = StudyAssistantPanel(self.config_manager)
        self.assistant_panel.status_message.connect(self._on_assistant_status)
        self.center_tabs.addTab(self.assistant_panel, "Study assistant")

        center_layout.addWidget(self.center_tabs, 1)
        self.content.addWidget(center)

        # ---- right: bookmarks + stats --------------------------------- #
        right_panel = QWidget()
        right_panel.setMinimumWidth(200)
        right_panel.setMaximumWidth(280)
        rp_layout = QVBoxLayout(right_panel)
        rp_layout.setContentsMargins(0, 0, 0, 0)
        rp_layout.setSpacing(12)

        topics_title = QLabel("Topics")
        topics_title.setStyleSheet("font-weight: 700; font-size: 15px;")
        rp_layout.addWidget(topics_title)
        self.topics_list = QListWidget()
        self.topics_list.setObjectName("studyTopicsList")
        self.topics_list.setMinimumHeight(120)
        self.topics_list.itemActivated.connect(self._open_topic)
        rp_layout.addWidget(self.topics_list)

        bookmarks_title = QLabel("Bookmarks")
        bookmarks_title.setStyleSheet("font-weight: 700; font-size: 15px;")
        rp_layout.addWidget(bookmarks_title)

        self.slides_bookmarks_lbl = QLabel("Slide bookmarks")
        self.slides_bookmarks_lbl.setProperty("muted", True)
        self.slides_bookmarks_lbl.setStyleSheet("font-size: 12px;")
        rp_layout.addWidget(self.slides_bookmarks_lbl)
        self.slide_bookmarks = QListWidget()
        self.slide_bookmarks.setObjectName("studySlideBookmarks")
        self.slide_bookmarks.setMinimumHeight(80)
        self.slide_bookmarks.itemActivated.connect(self._open_bookmark)
        rp_layout.addWidget(self.slide_bookmarks)

        self.section_bookmarks_lbl = QLabel("Section bookmarks")
        self.section_bookmarks_lbl.setProperty("muted", True)
        self.section_bookmarks_lbl.setStyleSheet("font-size: 12px;")
        rp_layout.addWidget(self.section_bookmarks_lbl)
        self.section_bookmarks = QListWidget()
        self.section_bookmarks.setObjectName("studySectionBookmarks")
        self.section_bookmarks.setMinimumHeight(80)
        self.section_bookmarks.itemActivated.connect(self._open_bookmark)
        rp_layout.addWidget(self.section_bookmarks)

        rp_layout.addStretch(1)
        self.content.addWidget(right_panel)

        self.content.setStretchFactor(0, 2)
        self.content.setStretchFactor(1, 3)
        self.content.setStretchFactor(2, 2)
        wl.addWidget(self.content, 1)

        cl.addWidget(wrapper)
        scroll.setWidget(container)
        root.addWidget(scroll)

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
        self.timeline_card.setVisible(not empty)

    def load_job(self, job):
        self.job = job
        self.refresh()

    def shutdown(self):
        self.assistant_panel.shutdown()

    def _clear_workspace(self):
        self._candidates = []
        self._segments = []
        self.slides_grid.shutdown()
        self.slides_grid.clear()
        self.transcript_view.clear()
        self.assistant_panel.load_job(None, [])

    def _load_workspace(self):
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, []) or []
        accepted = [c for c in candidates if c.get("decision") != "rejected"]
        accepted.sort(key=lambda c: float(c.get("timestamp_seconds", 0.0)))
        self._candidates = accepted
        self.slides_grid.load_candidates(accepted, self.job.paths)
        self._segments = store.load_working(self.job.paths) or []
        self.transcript_view.set_segments(self._segments)
        self.assistant_panel.load_job(self.job, self._segments)

    def _on_assistant_status(self, message: str):
        pass

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
            f"{duration}  \u00b7  {overview['accepted_slide_count']} accepted slides  \u00b7  "
            f"{overview['transcript_segment_count']} transcript segments\n"
            f"Mode: {overview['product_mode']}  \u00b7  Loaded backend: {overview['backend']}  \u00b7  "
            f"Needs review: {overview['needs_review_count']}")
        self.summary_lbl.setText(overview["summary"])
        self.summary_source_lbl.setText(f"Source: {overview['summary_source']}")
        self.terms_lbl.setText("  \u00b7  ".join(overview["key_terms"]) or "No key terms yet.")

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

        sections = overview["sections"]
        self.topic_timeline.set_topics(
            [{"start": float(s["start"]), "label": s["heading"]} for s in sections],
            overview["duration_seconds"])
        self._study_timeline_meta_lbl.setText(
            f"{len(sections)} topics · {overview['accepted_slide_count']} slides")
        bookmark_count = sum(
            1 for e in overview["bookmarked_slides"].values() if e.get("bookmarked")
        ) + len(overview["bookmarked_sections"])
        self._study_bookmarks_count_lbl.setText(
            f"{bookmark_count} bookmark{'s' if bookmark_count != 1 else ''}")
        while self._topic_labels_row.count():
            item = self._topic_labels_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for section in sections[:5]:
            lbl = QLabel(str(section["heading"]))
            lbl.setProperty("muted", True)
            lbl.setStyleSheet(f"font:500 10px '{theme.FONT_MONO}';border:none;background:transparent;")
            self._topic_labels_row.addWidget(lbl)
            self._topic_labels_row.addStretch(1)
        if sections:
            self._topic_labels_row.takeAt(self._topic_labels_row.count() - 1)

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
                label = "\u2605 " + label
            if note:
                label += f" \u2014 {note}"
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
                f"\u2605 {fmt_clock(float(entry.get('start', 0.0)))}  "
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

    def _on_topic_timeline_clicked(self, index: int):
        if self.overview is None:
            return
        sections = self.overview.get("sections") or []
        if 0 <= index < len(sections):
            self.navigate_requested.emit("transcript")
            self.seek_requested.emit(float(sections[index]["start"]))

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
