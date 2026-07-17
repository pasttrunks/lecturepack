"""
lecturepack.ui.pages.transcript_page
====================================

Dedicated Transcript workspace (v1.1, Phase 3), independent of slide review.

Views:
  1. Full Transcript -- continuous readable document with section headings,
     optional timestamps, search highlighting, timestamp links that select
     the related slide, one-click copy of everything.
  2. Segments -- editable grid (#, start, end, duration, confidence, status,
     text) with a separate editor for the active segment, split / merge /
     reset / undo, strong selected-row highlighting, sort/filter that never
     changes chronological export order.
  3. Sections / Topics -- conservative semantic sections derived from slide
     alignment; user can rename; AI headings are explicitly marked and
     editable.
  4. Context Repair -- the fault-isolated proposal panel.

The RAW whisper output is immutable; every edit lives in the working layer
(services.transcript_store) which mirrors legacy edited.json for old
consumers.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QTextCursor, QTextCharFormat, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import transcript_formats as tf
from lecturepack.services import transcript_store as store
from lecturepack.ui.widgets.context_repair_panel import ContextRepairPanel

COPY_FORMATS = ["plain text", "markdown", "json", "jsonl", "csv", "srt", "vtt"]
_FMT_MAP = {"plain text": "txt", "markdown": "markdown", "json": "json",
            "jsonl": "jsonl", "csv": "csv", "srt": "srt", "vtt": "vtt"}


def _fmt_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


_SORT_ROLE = Qt.ItemDataRole.UserRole + 7


class _NumericItem(QTableWidgetItem):
    """Table item that sorts by a numeric key while displaying formatted text
    (e.g. '0:01:05' sorted by 65.0 seconds; ids sorted as ints not strings)."""

    def __lt__(self, other):
        a = self.data(_SORT_ROLE)
        b = other.data(_SORT_ROLE)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


class TranscriptPage(QWidget):
    """Owns the working segment layer for the current job."""
    seek_requested = Signal(float)         # timestamp seconds -> select slide
    status_message = Signal(str)
    study_data_changed = Signal()
    position_changed = Signal(float)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.job = None
        self.segments = []          # working layer (plain dicts)
        self.confidence = {}        # raw id -> confidence
        self._undo = []
        self._redo = []
        self._search_hits = []
        self._search_pos = -1
        self._repair_panel = None
        self._sections = []
        self._active_seg_id = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        top = QHBoxLayout()
        title = QLabel("Transcript")
        title.setProperty("h1", True)
        top.addWidget(title)
        top.addSpacing(16)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search transcript (Ctrl+F, F3 / Shift+F3)…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self.search_next)
        self.search_edit.textChanged.connect(self._reset_search)
        top.addWidget(self.search_edit, 1)
        self.search_count_lbl = QLabel("")
        self.search_count_lbl.setProperty("muted", True)
        top.addWidget(self.search_count_lbl)

        self.timestamps_chk = QCheckBox("Timestamps")
        self.timestamps_chk.setChecked(True)
        self.timestamps_chk.toggled.connect(self._render_full)
        top.addWidget(self.timestamps_chk)

        top.addWidget(QLabel("Copy as:"))
        self.copy_format_combo = QComboBox()
        self.copy_format_combo.addItems(COPY_FORMATS)
        top.addWidget(self.copy_format_combo)
        self.copy_selected_btn = QPushButton("Copy selected")
        self.copy_selected_btn.clicked.connect(self.copy_selected_segments)
        top.addWidget(self.copy_selected_btn)
        self.copy_full_btn = QPushButton("Copy full transcript")
        self.copy_full_btn.setProperty("primary", True)
        self.copy_full_btn.clicked.connect(self.copy_full_transcript)
        top.addWidget(self.copy_full_btn)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # --- 1. Full transcript ------------------------------------------ #
        full_w = QWidget()
        fl = QVBoxLayout(full_w)
        fl.setContentsMargins(0, 6, 0, 0)
        self.full_view = QTextBrowser()
        self.full_view.setOpenLinks(False)
        self.full_view.anchorClicked.connect(self._on_anchor)
        fl.addWidget(self.full_view)
        self.tabs.addTab(full_w, "Full Transcript")

        # --- 2. Segments --------------------------------------------------- #
        seg_w = QWidget()
        sl = QVBoxLayout(seg_w)
        sl.setContentsMargins(0, 6, 0, 0)

        filt_row = QHBoxLayout()
        filt_row.addWidget(QLabel("Show:"))
        self.seg_filter_combo = QComboBox()
        self.seg_filter_combo.addItems(["all", "edited", "low confidence", "matches search"])
        self.seg_filter_combo.currentIndexChanged.connect(self._render_segments)
        filt_row.addWidget(self.seg_filter_combo)
        filt_row.addStretch(1)
        self.seg_info_lbl = QLabel("")
        self.seg_info_lbl.setProperty("muted", True)
        filt_row.addWidget(self.seg_info_lbl)
        sl.addLayout(filt_row)

        split = QSplitter(Qt.Orientation.Vertical)

        self.seg_table = QTableWidget()
        self.seg_table.setColumnCount(7)
        self.seg_table.setHorizontalHeaderLabels(
            ["#", "Start", "End", "Dur", "Conf", "Status", "Text"])
        hdr = self.seg_table.horizontalHeader()
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.seg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.seg_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.seg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.seg_table.setSortingEnabled(True)
        # default: chronological (Start ascending) -- split/merge ids are not
        # chronological, timestamps always are
        self.seg_table.horizontalHeader().setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        self.seg_table.setAlternatingRowColors(True)
        self.seg_table.itemSelectionChanged.connect(self._on_seg_selection)
        self.seg_table.currentCellChanged.connect(
            lambda *_: self._on_seg_selection())
        self.seg_table.itemDoubleClicked.connect(self._on_seg_double_clicked)
        split.addWidget(self.seg_table)

        editor_w = QWidget()
        el = QVBoxLayout(editor_w)
        el.setContentsMargins(0, 4, 0, 0)
        ed_hdr = QHBoxLayout()
        self.editor_lbl = QLabel("Active segment: —")
        self.editor_lbl.setProperty("h2", True)
        ed_hdr.addWidget(self.editor_lbl)
        ed_hdr.addStretch(1)
        for label, slot, tip in [
                ("Split at cursor", self.split_active_segment, "Split the active segment at the text cursor"),
                ("Merge selected", self.merge_selected_segments, "Merge the selected rows into one segment"),
                ("Reset", self.reset_active_segment, "Restore this segment's original text"),
                ("Undo", self.undo, "Ctrl+Z"), ("Redo", self.redo, "Ctrl+Y")]:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            ed_hdr.addWidget(b)
        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self.save)
        ed_hdr.addWidget(self.save_btn)
        el.addLayout(ed_hdr)
        self.seg_editor = QPlainTextEdit()
        self.seg_editor.setPlaceholderText("Select a segment to edit its text…")
        self.seg_editor.textChanged.connect(self._on_editor_changed)
        el.addWidget(self.seg_editor)
        split.addWidget(editor_w)
        split.setSizes([420, 140])
        self.seg_splitter = split
        sl.addWidget(split, 1)
        self.tabs.addTab(seg_w, "Segments")

        # --- 3. Sections ---------------------------------------------------- #
        sec_w = QWidget()
        scl = QVBoxLayout(sec_w)
        scl.setContentsMargins(0, 6, 0, 0)
        sec_actions = QHBoxLayout()
        self.rename_section_btn = QPushButton("Rename heading…")
        self.rename_section_btn.clicked.connect(self.rename_section)
        self.copy_section_btn = QPushButton("Copy section")
        self.copy_section_btn.clicked.connect(self.copy_current_section)
        self.bookmark_section_btn = QPushButton("☆ Bookmark section")
        self.bookmark_section_btn.setObjectName("sectionBookmarkButton")
        self.bookmark_section_btn.clicked.connect(self.toggle_section_bookmark)
        self.jump_section_btn = QPushButton("Jump to first slide")
        self.jump_section_btn.setObjectName("sectionJumpButton")
        self.jump_section_btn.clicked.connect(self.jump_to_current_section)
        self.ai_headings_btn = QPushButton("Suggest headings with AI (Ollama)")
        self.ai_headings_btn.clicked.connect(self.suggest_headings_ai)
        sec_actions.addWidget(self.rename_section_btn)
        sec_actions.addWidget(self.copy_section_btn)
        sec_actions.addWidget(self.bookmark_section_btn)
        sec_actions.addWidget(self.jump_section_btn)
        sec_actions.addStretch(1)
        sec_actions.addWidget(self.ai_headings_btn)
        scl.addLayout(sec_actions)
        self.sections_table = QTableWidget()
        self.sections_table.setColumnCount(5)
        self.sections_table.setHorizontalHeaderLabels(
            ["Heading", "Start", "End", "Segments", "Slide"])
        self.sections_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.sections_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sections_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sections_table.itemDoubleClicked.connect(
            lambda item: self.rename_section())
        self.sections_table.currentCellChanged.connect(
            lambda *_: self._on_section_selection())
        scl.addWidget(self.sections_table, 1)
        self.tabs.addTab(sec_w, "Sections")

        # --- 4. Context Repair ------------------------------------------- #
        self.repair_host = QWidget()
        self.repair_layout = QVBoxLayout(self.repair_host)
        self.repair_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs.addTab(self.repair_host, "Context Repair")

    # ------------------------------------------------------------------ #
    # job loading
    # ------------------------------------------------------------------ #
    def load_job(self, job):
        self.job = job
        self._undo.clear()
        self._redo.clear()
        self._active_seg_id = None
        if self._repair_panel is not None:
            self._repair_panel.shutdown()
            self._repair_panel.setParent(None)
            self._repair_panel.deleteLater()
            self._repair_panel = None
        if job is None:
            self.segments = []
            self.confidence = {}
            self._render_all()
            return
        self.segments = store.load_working(job.paths)
        self.confidence = store.load_segment_confidence(job.paths)
        if job is not None:
            self._repair_panel = ContextRepairPanel(job, self.config_manager, self)
            self.repair_layout.addWidget(self._repair_panel)
        self._load_sections()
        self._render_all()

    def shutdown(self):
        if self._repair_panel is not None:
            self._repair_panel.shutdown()

    def _load_sections(self):
        self._sections = []
        if self.job is None:
            return
        aligned = FileManager.read_json_safe(
            os.path.join(self.job.paths["root"], "transcript", "aligned.json"), [])
        try:
            self._sections = tf.build_sections(aligned or [])
        except Exception:
            self._sections = []
        overrides = FileManager.read_json_safe(self._sections_overrides_path(), {}) or {}
        for sec in self._sections:
            key = str(sec.get("index"))
            if key in overrides:
                ov = overrides[key]
                sec["heading"] = ov.get("heading", sec["heading"])
                sec["heading_source"] = ov.get("source", "user")

    def _sections_overrides_path(self):
        return os.path.join(self.job.paths["transcript"], "section_overrides.json")

    def _save_section_overrides(self):
        overrides = {}
        for sec in self._sections:
            if sec.get("heading_source") in ("user", "ai"):
                overrides[str(sec.get("index"))] = {
                    "heading": sec["heading"], "source": sec["heading_source"]}
        FileManager.write_json_atomic(self._sections_overrides_path(), overrides)

    # ------------------------------------------------------------------ #
    # rendering
    # ------------------------------------------------------------------ #
    def _render_all(self):
        self._render_full()
        self._render_segments()
        self._render_sections()

    def _render_full(self):
        if not self.segments:
            self.full_view.setHtml("<p style='color:#8b93a1'>No transcript yet. "
                                   "Process a lecture or open a job.</p>")
            return
        show_ts = self.timestamps_chk.isChecked()
        query = self.search_edit.text().strip().lower()
        # Section boundaries for headings
        sec_starts = {}
        for sec in self._sections:
            sec_starts.setdefault(round(sec["start"], 1), sec)
        parts = ["<style>a{text-decoration:none;color:#2563eb}"
                 "p{line-height:1.55;margin:0 0 10px 0;}"
                 "h3{margin:18px 0 6px 0;}</style>"]
        emitted_secs = set()
        buf = []

        def flush():
            if buf:
                parts.append("<p>" + " ".join(buf) + "</p>")
                buf.clear()

        for seg in self.segments:
            for st, sec in sec_starts.items():
                if sec.get("index") not in emitted_secs and seg["start"] >= sec["start"] \
                        and abs(seg["start"] - sec["start"]) < 15.0:
                    flush()
                    mark = " <span style='color:#8e24aa;font-size:80%'>(AI)</span>" \
                        if sec.get("heading_source") == "ai" else ""
                    parts.append(f"<h3>{tf.fmt_clock(sec['start'])} · "
                                 f"{_esc(sec['heading'])}{mark}</h3>")
                    emitted_secs.add(sec.get("index"))
            text = _esc(seg["text"])
            if query:
                text = _highlight(text, query)
            chunk = ""
            if show_ts:
                chunk += (f"<a href='seek:{seg['start']}' title='Select slide near "
                          f"{_fmt_time(seg['start'])}'>[{_fmt_time(seg['start'])}]</a> ")
            chunk += text
            buf.append(chunk)
            if seg["text"].strip().endswith((".", "!", "?")) and len(buf) >= 4:
                flush()
        flush()
        self.full_view.setHtml("".join(parts))

    def _visible_segment_rows(self):
        f = self.seg_filter_combo.currentText()
        query = self.search_edit.text().strip().lower()
        out = []
        for seg in self.segments:
            if f == "edited" and not seg.get("edited"):
                continue
            conf = self._conf_for(seg)
            if f == "low confidence" and not (conf is not None and conf < 0.6):
                continue
            if f == "matches search" and (not query or query not in seg["text"].lower()):
                continue
            out.append(seg)
        return out

    def _conf_for(self, seg):
        vals = [self.confidence.get(oid) for oid in seg.get("origin_ids", [])]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def _render_segments(self):
        rows = self._visible_segment_rows()
        self.seg_table.setSortingEnabled(False)
        self.seg_table.setRowCount(len(rows))
        for r, seg in enumerate(rows):
            conf = self._conf_for(seg)
            dur = max(0.0, seg["end"] - seg["start"])
            status = "edited" if seg.get("edited") else ""
            if len(seg.get("origin_ids", [])) > 1:
                status = (status + " merged").strip()
            vals = [str(seg["id"]), _fmt_time(seg["start"]), _fmt_time(seg["end"]),
                    f"{dur:.1f}s", f"{conf:.2f}" if conf is not None else "—",
                    status, seg["text"]]
            sort_keys = [seg["id"], seg["start"], seg["end"], dur,
                         conf if conf is not None else -1.0, None, None]
            for ccol, v in enumerate(vals):
                item = _NumericItem(v)
                if sort_keys[ccol] is not None:
                    item.setData(_SORT_ROLE, float(sort_keys[ccol]))
                if ccol == 0:
                    item.setData(Qt.ItemDataRole.UserRole, seg["id"])
                if ccol == 4 and conf is not None and conf < 0.6:
                    item.setForeground(QColor("#d97706"))
                self.seg_table.setItem(r, ccol, item)
        self.seg_table.setSortingEnabled(True)
        self.seg_info_lbl.setText(
            f"{len(rows)} of {len(self.segments)} segments · exports stay chronological")
        self._sync_editor()

    def _render_sections(self):
        from lecturepack.services import study_service
        bookmarks = study_service.load_study_data(self.job)["bookmarked_sections"] \
            if self.job is not None else {}
        self.sections_table.setRowCount(len(self._sections))
        for r, sec in enumerate(self._sections):
            head = sec["heading"]
            if study_service.section_key(sec) in bookmarks:
                head = "★ " + head
            if sec.get("heading_source") == "ai":
                head += "  (AI)"
            elif sec.get("heading_source") == "user":
                head += "  (edited)"
            vals = [head, tf.fmt_clock(sec["start"]), tf.fmt_clock(sec["end"]),
                    str(len(sec.get("segments", []))), str(sec.get("slide_index", "")) ]
            for ccol, v in enumerate(vals):
                self.sections_table.setItem(r, ccol, QTableWidgetItem(v))
        self._on_section_selection()

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #
    def focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _reset_search(self):
        self._search_pos = -1
        self._render_full()
        if self.seg_filter_combo.currentText() == "matches search":
            self._render_segments()
        q = self.search_edit.text().strip().lower()
        if q:
            hits = [s for s in self.segments if q in s["text"].lower()]
            self.search_count_lbl.setText(f"{len(hits)} matches")
        else:
            self.search_count_lbl.setText("")

    def search_next(self):
        self._step_search(1)

    def search_prev(self):
        self._step_search(-1)

    def _step_search(self, direction):
        q = self.search_edit.text().strip().lower()
        if not q:
            return
        hits = [i for i, s in enumerate(self.segments) if q in s["text"].lower()]
        if not hits:
            self.search_count_lbl.setText("0 matches")
            return
        self._search_pos = (self._search_pos + direction) % len(hits)
        self.search_count_lbl.setText(f"{self._search_pos + 1}/{len(hits)} matches")
        seg = self.segments[hits[self._search_pos]]
        if self.tabs.currentIndex() == 0:
            # scroll the full view to the match
            doc = self.full_view.document()
            cursor = doc.find(self.search_edit.text())
            for _ in range(self._search_pos):
                nxt = doc.find(self.search_edit.text(), cursor)
                if nxt.isNull():
                    break
                cursor = nxt
            if not cursor.isNull():
                self.full_view.setTextCursor(cursor)
                self.full_view.ensureCursorVisible()
        else:
            self._select_segment_row(seg["id"])
        self.seek_requested.emit(seg["start"])

    def _select_segment_row(self, seg_id):
        for r in range(self.seg_table.rowCount()):
            item = self.seg_table.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == seg_id:
                self.seg_table.selectRow(r)
                self.seg_table.scrollToItem(item)
                return

    # ------------------------------------------------------------------ #
    # segment editing
    # ------------------------------------------------------------------ #
    def _snapshot(self):
        import copy
        self._undo.append(copy.deepcopy(self.segments))
        if len(self._undo) > 100:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        if not self._undo:
            self.status_message.emit("Nothing to undo.")
            return
        import copy
        self._redo.append(copy.deepcopy(self.segments))
        self.segments = self._undo.pop()
        self._render_segments()
        self._render_full()
        self.status_message.emit("Undo applied (remember to Save).")

    def redo(self):
        if not self._redo:
            return
        import copy
        self._undo.append(copy.deepcopy(self.segments))
        self.segments = self._redo.pop()
        self._render_segments()
        self._render_full()

    def _selected_seg_ids(self):
        rows = sorted({i.row() for i in self.seg_table.selectedIndexes()})
        ids = []
        for r in rows:
            item = self.seg_table.item(r, 0)
            if item:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _on_seg_selection(self):
        ids = self._selected_seg_ids()
        self._active_seg_id = ids[0] if ids else None
        self._sync_editor()

    def _on_seg_double_clicked(self, item):
        row = item.row()
        id_item = self.seg_table.item(row, 0)
        if id_item:
            seg_id = id_item.data(Qt.ItemDataRole.UserRole)
            seg = self._seg_by_id(seg_id)
            if seg:
                self.seek_requested.emit(seg["start"])
        self.seg_editor.setFocus()

    def _seg_by_id(self, seg_id):
        for s in self.segments:
            if s["id"] == seg_id:
                return s
        return None

    def _sync_editor(self):
        seg = self._seg_by_id(self._active_seg_id) if self._active_seg_id else None
        self.seg_editor.blockSignals(True)
        if seg is None:
            self.editor_lbl.setText("Active segment: —")
            self.seg_editor.setPlainText("")
        else:
            self.editor_lbl.setText(
                f"Active segment #{seg['id']}  ·  {_fmt_time(seg['start'])} → "
                f"{_fmt_time(seg['end'])}")
            if self.seg_editor.toPlainText() != seg["text"]:
                self.seg_editor.setPlainText(seg["text"])
        self.seg_editor.blockSignals(False)

    def _on_editor_changed(self):
        seg = self._seg_by_id(self._active_seg_id) if self._active_seg_id else None
        if seg is None:
            return
        text = self.seg_editor.toPlainText()
        if text != seg["text"]:
            if not self._undo or self._undo[-1] is not None:
                self._snapshot()
                self._undo.append(None)  # marker: continuous typing session
            self.segments = store.edit_text(self.segments, seg["id"], text)
            # update just the visible row text without a full re-render
            for r in range(self.seg_table.rowCount()):
                item = self.seg_table.item(r, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == seg["id"]:
                    self.seg_table.item(r, 6).setText(text)
                    self.seg_table.item(r, 5).setText("edited")
                    break

    def split_active_segment(self):
        seg = self._seg_by_id(self._active_seg_id) if self._active_seg_id else None
        if seg is None:
            self.status_message.emit("Select a segment first.")
            return
        cursor = self.seg_editor.textCursor().position()
        self._snapshot()
        self.segments, new_id = store.split_segment(self.segments, seg["id"], cursor)
        if new_id is None:
            self._undo.pop()
            self.status_message.emit("Place the cursor inside the text to split.")
            return
        self._render_segments()
        self._render_full()
        self.status_message.emit(f"Split into #{seg['id']} and #{new_id} (remember to Save).")

    def merge_selected_segments(self):
        ids = self._selected_seg_ids()
        if len(ids) < 2:
            self.status_message.emit("Select two or more adjacent segments to merge.")
            return
        self._snapshot()
        self.segments = store.merge_segments(self.segments, ids)
        self._render_segments()
        self._render_full()
        self.status_message.emit(f"Merged {len(ids)} segments (remember to Save).")

    def reset_active_segment(self):
        seg = self._seg_by_id(self._active_seg_id) if self._active_seg_id else None
        if seg is None or self.job is None:
            return
        self._snapshot()
        raw = store.load_raw_segments(self.job.paths)
        self.segments = store.reset_segment(self.segments, seg["id"], raw)
        self._render_segments()
        self._render_full()
        self._sync_editor()

    def save(self):
        if self.job is None:
            return
        # drop typing-session markers from the undo stack
        self._undo = [s for s in self._undo if s is not None]
        store.save_working(self.job.paths, self.segments)
        self.status_message.emit("Transcript working layer saved (raw untouched).")

    # ------------------------------------------------------------------ #
    # sections actions
    # ------------------------------------------------------------------ #
    def rename_section(self):
        r = self.sections_table.currentRow()
        if not (0 <= r < len(self._sections)):
            return
        sec = self._sections[r]
        text, ok = QInputDialog.getText(self, "Rename section heading",
                                        "Heading:", text=sec["heading"])
        if ok and text.strip():
            sec["heading"] = text.strip()
            sec["heading_source"] = "user"
            self._save_section_overrides()
            self._render_sections()
            self._render_full()

    def copy_current_section(self):
        r = self.sections_table.currentRow()
        if not (0 <= r < len(self._sections)):
            return
        sec = self._sections[r]
        self._copy_segments(sec.get("segments", []), f"Section '{sec['heading']}'")

    def _current_section(self):
        row = self.sections_table.currentRow()
        return self._sections[row] if 0 <= row < len(self._sections) else None

    def _on_section_selection(self):
        from lecturepack.services import study_service
        sec = self._current_section()
        if sec is None or self.job is None:
            self.bookmark_section_btn.setEnabled(False)
            self.jump_section_btn.setEnabled(False)
            self.bookmark_section_btn.setText("☆ Bookmark section")
            return
        bookmarks = study_service.load_study_data(self.job)["bookmarked_sections"]
        marked = study_service.section_key(sec) in bookmarks
        self.bookmark_section_btn.setEnabled(True)
        self.jump_section_btn.setEnabled(True)
        self.bookmark_section_btn.setText(
            "★ Bookmarked section" if marked else "☆ Bookmark section")
        self.position_changed.emit(float(sec.get("start", 0.0)))

    def toggle_section_bookmark(self):
        from lecturepack.services import study_service
        sec = self._current_section()
        if sec is None or self.job is None:
            return
        bookmarks = study_service.load_study_data(self.job)["bookmarked_sections"]
        marked = study_service.section_key(sec) in bookmarks
        study_service.set_section_bookmark(self.job, sec, not marked)
        study_service.save_position(
            self.job, page="transcript", timestamp_seconds=float(sec.get("start", 0.0)),
            section=sec)
        self._render_sections()
        self.study_data_changed.emit()

    def jump_to_current_section(self):
        from lecturepack.services import study_service
        sec = self._current_section()
        if sec is None or self.job is None:
            return
        timestamp = float(sec.get("start", 0.0))
        study_service.save_position(
            self.job, page="review", timestamp_seconds=timestamp, section=sec)
        self.seek_requested.emit(timestamp)
        self.position_changed.emit(timestamp)

    def suggest_headings_ai(self):
        """AI-assigned section headings (Phase 5 scope). Runs in a worker via
        the panel's infrastructure; marked (AI) and editable; never silent."""
        if self.job is None or not self._sections:
            self.status_message.emit("No sections available yet (run a job first).")
            return
        o = self.job.settings.get("ollama") or (self.config_manager.get("ollama", {}) or {})
        if not (o.get("enabled") and o.get("model")):
            QMessageBox.information(
                self, "Ollama not configured",
                "Enable Ollama and pick a model in Settings → AI (Ollama) first.")
            return
        from lecturepack.infrastructure.ollama_client import OllamaClient, OllamaError
        client = OllamaClient(o.get("base_url") or "http://localhost:11434")
        schema = {
            "type": "object",
            "properties": {"headings": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "index": {"type": "integer"}, "heading": {"type": "string"}},
                    "required": ["index", "heading"]}}},
            "required": ["headings"],
        }
        lines = []
        for sec in self._sections[:40]:
            preview = " ".join(s.get("text", "") for s in sec.get("segments", []))[:300]
            lines.append(f"[{sec['index']}] {preview}")
        user = ("Give each numbered lecture section a concise 3-7 word heading "
                "based ONLY on its text. Do not invent facts.\n" + "\n".join(lines))
        self.ai_headings_btn.setEnabled(False)
        self.status_message.emit("Requesting section headings from Ollama…")
        # Short, single request -- run in a Python thread and marshal back.
        import threading
        import json as _json

        def work():
            try:
                res = client.chat_structured(o["model"], "You title lecture sections.",
                                             user, schema, num_predict=600)
                return ("ok", res["content"])
            except OllamaError as e:
                return (e.kind, str(e))
            except Exception as e:
                return ("internal", str(e))

        def done(result):
            self.ai_headings_btn.setEnabled(True)
            kind, payload = result
            if kind != "ok":
                self.status_message.emit(f"AI headings failed ({kind}): {payload}")
                return
            try:
                data = _json.loads(payload)
                by_index = {int(h["index"]): str(h["heading"]).strip()
                            for h in data.get("headings", []) if str(h.get("heading", "")).strip()}
            except Exception:
                self.status_message.emit("AI headings failed: malformed response.")
                return
            n = 0
            for sec in self._sections:
                h = by_index.get(int(sec.get("index", -1)))
                if h and sec.get("heading_source") != "user":
                    sec["heading"] = h[:80]
                    sec["heading_source"] = "ai"
                    n += 1
            self._save_section_overrides()
            self._render_sections()
            self._render_full()
            self.status_message.emit(f"AI suggested {n} heading(s) — marked (AI), editable.")

        from PySide6.QtCore import QTimer

        holder = {}

        def runner():
            holder["result"] = work()

        th = threading.Thread(target=runner, daemon=True)
        th.start()

        def poll():
            if th.is_alive():
                QTimer.singleShot(200, poll)
            else:
                done(holder.get("result", ("internal", "no result")))

        QTimer.singleShot(200, poll)

    # ------------------------------------------------------------------ #
    # copy actions
    # ------------------------------------------------------------------ #
    def _copy_segments(self, segs, label):
        fmt = _FMT_MAP.get(self.copy_format_combo.currentText(), "txt")
        include_ts = self.timestamps_chk.isChecked()
        try:
            text = tf.serialize(fmt, segs, include_timestamps=include_ts)
        except Exception:
            text = tf.to_plain(segs, include_timestamps=include_ts)
        QGuiApplication.clipboard().setText(text)
        self.status_message.emit(f"{label} copied as {self.copy_format_combo.currentText()}.")

    def copy_full_transcript(self):
        self._copy_segments(self.segments, "Full transcript")

    def copy_selected_segments(self):
        ids = set(self._selected_seg_ids())
        if not ids:
            seg = self._seg_by_id(self._active_seg_id) if self._active_seg_id else None
            if seg is None:
                self.copy_full_transcript()
                return
            ids = {seg["id"]}
        segs = [s for s in self.segments if s["id"] in ids]
        self._copy_segments(segs, f"{len(segs)} segment(s)")

    def copy_current_segment(self):
        seg = self._seg_by_id(self._active_seg_id) if self._active_seg_id else None
        if seg is not None:
            self._copy_segments([seg], "Current segment")

    # ------------------------------------------------------------------ #
    def _on_anchor(self, url):
        s = url.toString()
        if s.startswith("seek:"):
            try:
                self.seek_requested.emit(float(s[5:]))
            except ValueError:
                pass


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _highlight(escaped_text: str, query: str) -> str:
    import re as _re
    return _re.sub(f"({_re.escape(query)})",
                   r"<span style='background:#fde68a;color:#111827'>\1</span>",
                   escaped_text, flags=_re.IGNORECASE)
