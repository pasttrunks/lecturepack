"""
lecturepack.ui.pages.review_page
================================

Slide review workspace (v1.1, Phases 1+2). Default layout:

    left    slide timeline (compact list / thumbnail grid, SlideGridWidget)
    center  large slide preview + navigation
    right   transcript for the current slide/selection (editable, searchable)

Selection is synchronized: slide grid <-> preview <-> transcript pane, and the
page reports selection to the shell toolbar. All decisions (keep / reject /
restore) are reversible; nothing is ever physically deleted.
"""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services.export_service import datetime_from_seconds
from lecturepack.services import transcript_formats as tf
from lecturepack.ui.widgets.slide_grid import SlideGridWidget, CAND_ROLE

_COPY_FORMAT_MAP = {
    "plain text": "txt", "markdown": "markdown", "json": "json",
    "jsonl": "jsonl", "csv": "csv", "srt": "srt", "vtt": "vtt",
}


class ReviewPage(QWidget):
    status_message = Signal(str)
    selection_count_changed = Signal(int)
    open_context_repair = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.job = None
        self.raw_segments = []
        self.edited_data = {}
        self.undo_stack = []
        self.current_search_match = -1
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- left: slide timeline -------------------------------------- #
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        lt = QHBoxLayout()
        lbl = QLabel("Slides")
        lbl.setProperty("h2", True)
        lt.addWidget(lbl)
        self.selected_count_lbl = QLabel("Selected: 0")
        self.selected_count_lbl.setStyleSheet("font-weight: bold; color: #2563eb;")
        lt.addWidget(self.selected_count_lbl)
        lt.addStretch(1)
        self.grid_mode_btn = QToolButton()
        self.grid_mode_btn.setText("Grid")
        self.grid_mode_btn.setCheckable(True)
        self.grid_mode_btn.setChecked(True)
        self.list_mode_btn = QToolButton()
        self.list_mode_btn.setText("List")
        self.list_mode_btn.setCheckable(True)
        self.grid_mode_btn.clicked.connect(lambda: self._set_mode("grid"))
        self.list_mode_btn.clicked.connect(lambda: self._set_mode("list"))
        lt.addWidget(self.grid_mode_btn)
        lt.addWidget(self.list_mode_btn)
        ll.addLayout(lt)

        self.slides_view = SlideGridWidget()
        self.slides_view.itemSelectionChanged.connect(self._on_slides_selection_changed)
        self.slides_view.decision_requested.connect(self._on_decision_requested)
        self.slides_view.export_selected_requested.connect(self.export_selected_images)
        self.slides_view.copy_image_requested.connect(self._copy_image)
        self.slides_view.open_timestamp_requested.connect(self._open_timestamp)
        self.slides_view.activate_preview_requested.connect(self._focus_preview)
        ll.addWidget(self.slides_view, 1)

        actions = QHBoxLayout()
        self.bulk_keep_btn = QPushButton("Keep")
        self.bulk_keep_btn.clicked.connect(self._bulk_keep)
        self.bulk_reject_btn = QPushButton("Reject (Del)")
        self.bulk_reject_btn.setProperty("danger", True)
        self.bulk_reject_btn.clicked.connect(self._bulk_reject)
        self.bulk_restore_btn = QPushButton("Restore (R)")
        self.bulk_restore_btn.clicked.connect(self._bulk_restore)
        actions.addWidget(self.bulk_keep_btn)
        actions.addWidget(self.bulk_reject_btn)
        actions.addWidget(self.bulk_restore_btn)
        ll.addLayout(actions)
        self.splitter.addWidget(left)

        # ---- center: preview -------------------------------------------- #
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        self.preview_lbl = QLabel("Select a slide to preview")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setMinimumHeight(240)
        self.preview_lbl.setStyleSheet(
            "background: #14161a; border: 1px solid #3a3f47; border-radius: 8px; color: #8b93a1;")
        cl.addWidget(self.preview_lbl, 1)
        nav = QHBoxLayout()
        prev_btn = QPushButton("◀ Prev")
        prev_btn.clicked.connect(lambda: self._step_selection(-1))
        self.slide_info_lbl = QLabel("Timestamp: —")
        self.slide_info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slide_info_lbl.setProperty("h2", True)
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(lambda: self._step_selection(1))
        nav.addWidget(prev_btn)
        nav.addWidget(self.slide_info_lbl, 1)
        nav.addWidget(next_btn)
        cl.addLayout(nav)
        self.splitter.addWidget(center)

        # ---- right: transcript for the selection ------------------------ #
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rt = QLabel("Transcript for selection")
        rt.setProperty("h2", True)
        rl.addWidget(rt)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search (Ctrl+F, F3/Shift+F3)…")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_prev_btn = QPushButton("Prev")
        self.search_prev_btn.clicked.connect(self._search_prev)
        self.search_next_btn = QPushButton("Next")
        self.search_next_btn.clicked.connect(self._search_next)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_prev_btn)
        search_layout.addWidget(self.search_next_btn)
        rl.addLayout(search_layout)

        copy_layout = QHBoxLayout()
        copy_layout.addWidget(QLabel("Copy as:"))
        self.copy_format_combo = QComboBox()
        self.copy_format_combo.addItems(list(_COPY_FORMAT_MAP.keys()))
        copy_layout.addWidget(self.copy_format_combo)
        self.timestamps_chk = QCheckBox("Timestamps")
        copy_layout.addWidget(self.timestamps_chk)
        self.copy_current_btn = QPushButton("Copy slide")
        self.copy_current_btn.clicked.connect(self._copy_current_transcript)
        self.copy_selected_btn = QPushButton("Copy selected")
        self.copy_selected_btn.clicked.connect(self._copy_selected_transcripts)
        self.copy_full_btn = QPushButton("Copy full")
        self.copy_full_btn.clicked.connect(self._copy_full_transcript)
        copy_layout.addWidget(self.copy_current_btn)
        copy_layout.addWidget(self.copy_selected_btn)
        copy_layout.addWidget(self.copy_full_btn)
        rl.addLayout(copy_layout)

        self.transcript_table = QTableWidget()
        self.transcript_table.setColumnCount(3)
        self.transcript_table.setHorizontalHeaderLabels(
            ["Time Range", "Segment Text (Editable)", "Action"])
        self.transcript_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.transcript_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.transcript_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self.transcript_table.verticalHeader().setVisible(False)
        rl.addWidget(self.transcript_table, 1)

        save_layout = QHBoxLayout()
        self.save_corrections_btn = QPushButton("Save corrections (Ctrl+S)")
        self.save_corrections_btn.setProperty("primary", True)
        self.save_corrections_btn.clicked.connect(self._save_corrections)
        self.context_repair_btn = QPushButton("Context Repair…")
        self.context_repair_btn.clicked.connect(self.open_context_repair.emit)
        self.transcript_status_lbl = QLabel("")
        self.transcript_status_lbl.setProperty("chip", "ok")
        save_layout.addWidget(self.save_corrections_btn)
        save_layout.addWidget(self.context_repair_btn)
        save_layout.addWidget(self.transcript_status_lbl)
        save_layout.addStretch(1)
        rl.addLayout(save_layout)
        self.splitter.addWidget(right)

        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setStretchFactor(2, 4)
        layout.addWidget(self.splitter, 1)

    # ------------------------------------------------------------------ #
    # loading
    # ------------------------------------------------------------------ #
    def set_job(self, job):
        self.job = job
        self.undo_stack = []

    def load_review_data(self):
        from lecturepack.services import transcript_store as store
        self.slides_view.shutdown()
        self.slides_view.clear()
        self.preview_lbl.setText("Select a slide to preview")
        self.preview_lbl.setPixmap(QPixmap())
        self.slide_info_lbl.setText("Timestamp: —")
        self.selected_count_lbl.setText("Selected: 0")
        self.transcript_table.setRowCount(0)
        if self.job is None:
            return

        self.raw_segments = store.load_raw_segments(self.job.paths)
        self.edited_data = store.load_edited_overrides(self.job.paths)

        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        self.slides_view.load_candidates(candidates, self.job.paths)

    # ------------------------------------------------------------------ #
    # selection + preview
    # ------------------------------------------------------------------ #
    def _set_mode(self, mode):
        self.grid_mode_btn.setChecked(mode == "grid")
        self.list_mode_btn.setChecked(mode == "list")
        self.slides_view.set_display_mode(mode)

    def _on_slides_selection_changed(self):
        selected_items = self.slides_view.selectedItems()
        self.selected_count_lbl.setText(f"Selected: {len(selected_items)}")
        self.selection_count_changed.emit(len(selected_items))
        if not selected_items:
            self.preview_lbl.setText("Select a slide to preview")
            self.preview_lbl.setPixmap(QPixmap())
            self.slide_info_lbl.setText("Timestamp: —")
            self.transcript_table.setRowCount(0)
            return
        primary_item = selected_items[0]
        cand = primary_item.data(CAND_ROLE)
        self._show_slide_preview(cand)
        self._update_transcript_for_selected_slides()

    def _show_slide_preview(self, cand):
        img_filename = cand.get("image_filename", "")
        img_p = os.path.join(self.job.paths["candidates"], img_filename)
        if os.path.exists(img_p):
            pix = QPixmap(img_p)
            scaled = pix.scaled(self.preview_lbl.size(), Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
            self.preview_lbl.setPixmap(scaled)
        else:
            self.preview_lbl.setText("Image missing.")
        self.slide_info_lbl.setText(
            f"{cand.get('timestamp_formatted', '00:00:00')}  ·  frame {cand.get('frame_number', 0)}")

    def _step_selection(self, delta):
        row = self.slides_view.currentRow()
        n = self.slides_view.count()
        if n == 0:
            return
        new = max(0, min(n - 1, (row if row >= 0 else 0) + delta))
        self.slides_view.setCurrentRow(new)

    def _focus_preview(self):
        self.preview_lbl.setFocus()

    def select_slide_near(self, timestamp: float):
        """Selection sync: pick the slide whose interval contains ``timestamp``."""
        best_row, best_dt = -1, None
        for r in range(self.slides_view.count()):
            cand = self.slides_view.item(r).data(CAND_ROLE)
            t = cand.get("timestamp_seconds", 0.0)
            if t <= timestamp and (best_dt is None or timestamp - t < best_dt):
                best_dt = timestamp - t
                best_row = r
        if best_row >= 0:
            self.slides_view.setCurrentRow(best_row)

    # ------------------------------------------------------------------ #
    # transcript pane (selection-scoped)
    # ------------------------------------------------------------------ #
    def _selected_intervals(self):
        selected_items = self.slides_view.selectedItems()
        selected_cands = [item.data(CAND_ROLE) for item in selected_items]
        selected_cands.sort(key=lambda c: c.get("timestamp_seconds", 0.0))
        video_duration = 0.0
        if self.job and self.job.source:
            video_duration = self.job.source.get("duration", 0.0)
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        accepted = sorted((c for c in candidates if c.get("decision") == "accepted"),
                          key=lambda s: s.get("timestamp_seconds", 0.0))
        intervals = []
        for cand in selected_cands:
            start = cand.get("timestamp_seconds", 0.0)
            end = video_duration
            for acc in accepted:
                if acc.get("timestamp_seconds", 0.0) > start:
                    end = acc.get("timestamp_seconds", 0.0)
                    break
            intervals.append((start, max(start, end)))
        return intervals

    def _matched_segments(self, intervals):
        matched, seen = [], set()
        for start, end in intervals:
            for seg in self.raw_segments:
                overlap = max(0.0, min(seg["end"], end) - max(seg["start"], start))
                if overlap > 0.0 or (seg["start"] <= (start + end) / 2.0 <= seg["end"]):
                    if seg["id"] not in seen:
                        seen.add(seg["id"])
                        matched.append(seg)
        matched.sort(key=lambda s: s["start"])
        return matched

    def _update_transcript_for_selected_slides(self):
        from lecturepack.services import transcript_store as store
        if not self.slides_view.selectedItems():
            self.transcript_table.setRowCount(0)
            return
        self.edited_data = store.load_edited_overrides(self.job.paths)
        matched = self._matched_segments(self._selected_intervals())
        self.transcript_table.setRowCount(len(matched))
        for row, seg in enumerate(matched):
            seg_id = seg["id"]
            t1 = datetime_from_seconds(seg["start"])
            t2 = datetime_from_seconds(seg["end"])
            self.transcript_table.setItem(row, 0, QTableWidgetItem(f"{t1} -> {t2}"))

            text_edit = QTextEdit()
            text_edit.setAcceptRichText(False)
            current_text = self.edited_data.get(str(seg_id), seg["text"])
            text_edit.setPlainText(current_text)
            text_edit.setMinimumHeight(40)
            text_edit.setMaximumHeight(80)
            text_edit.setProperty("segment_id", seg_id)
            self._style_segment_edit(text_edit, str(seg_id) in self.edited_data)
            text_edit.textChanged.connect(self._on_segment_text_changed)
            self.transcript_table.setCellWidget(row, 1, text_edit)

            reset_btn = QPushButton("Reset")
            reset_btn.setProperty("segment_id", seg_id)
            reset_btn.setProperty("text_edit", text_edit)
            reset_btn.clicked.connect(self._reset_segment_clicked)
            self.transcript_table.setCellWidget(row, 2, reset_btn)
        for r in range(len(matched)):
            self.transcript_table.setRowHeight(r, 60)

    def _style_segment_edit(self, widget, is_edited):
        if is_edited:
            widget.setStyleSheet("background-color: #e8f5e9; border: 1px solid #c8e6c9; "
                                 "color: #1b5e20; font-weight: bold;")
        else:
            widget.setStyleSheet("")

    def _on_segment_text_changed(self):
        text_edit = self.sender()
        if not text_edit:
            return
        seg_id = text_edit.property("segment_id")
        raw_text = next((s["text"] for s in self.raw_segments if s["id"] == seg_id), "")
        self._style_segment_edit(text_edit, text_edit.toPlainText().strip() != raw_text)

    def _reset_segment_clicked(self):
        btn = self.sender()
        if not btn:
            return
        seg_id = btn.property("segment_id")
        text_edit = btn.property("text_edit")
        if not text_edit:
            return
        raw_text = next((s["text"] for s in self.raw_segments if s["id"] == seg_id), "")
        text_edit.setPlainText(raw_text)
        self._style_segment_edit(text_edit, False)
        if str(seg_id) in self.edited_data:
            del self.edited_data[str(seg_id)]
            self._persist_edited()
            self.transcript_status_lbl.setText("Segment reset to original.")
            QTimer.singleShot(2000, self._clear_transcript_status)

    def _persist_edited(self):
        from lecturepack.services import transcript_store as store
        edited_path = os.path.join(self.job.paths["transcript"], "edited.json")
        FileManager.write_json_atomic(edited_path, self.edited_data)
        # write-through to the v1.1 working layer so the Transcript page and
        # exports stay in sync with review-pane edits
        try:
            working = store.load_working(self.job.paths)
            raw_by_id = {s["id"]: s for s in self.raw_segments}
            for seg in working:
                if len(seg.get("origin_ids", [])) == 1:
                    rid = seg["origin_ids"][0]
                    if str(rid) in self.edited_data:
                        seg["text"] = self.edited_data[str(rid)]
                        seg["edited"] = True
                    elif rid in raw_by_id and seg.get("edited"):
                        seg["text"] = raw_by_id[rid]["text"]
                        seg["edited"] = False
            store.save_working(self.job.paths, working)
        except Exception:
            pass

    def _save_corrections(self):
        if not self.job:
            return
        for row in range(self.transcript_table.rowCount()):
            text_edit = self.transcript_table.cellWidget(row, 1)
            if not text_edit:
                continue
            seg_id = text_edit.property("segment_id")
            text = text_edit.toPlainText().strip()
            raw_text = next((s["text"] for s in self.raw_segments if s["id"] == seg_id), "")
            if text != raw_text:
                self.edited_data[str(seg_id)] = text
            elif str(seg_id) in self.edited_data:
                del self.edited_data[str(seg_id)]
        self._persist_edited()
        self.transcript_status_lbl.setText("Corrections saved successfully.")
        QTimer.singleShot(3000, self._clear_transcript_status)

    def _clear_transcript_status(self):
        try:
            self.transcript_status_lbl.setText("")
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #
    def _on_search_text_changed(self):
        self.current_search_match = -1

    def _search_next(self):
        self._do_search(forward=True)

    def _search_prev(self):
        self._do_search(forward=False)

    def _do_search(self, forward=True):
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
            if not (0 <= self.current_search_match < len(matches)):
                self.current_search_match = 0
        else:
            self.current_search_match -= 1
            if not (0 <= self.current_search_match < len(matches)):
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

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    # ------------------------------------------------------------------ #
    # copy actions
    # ------------------------------------------------------------------ #
    def _seg_with_edit(self, seg):
        return {"id": seg["id"], "start": seg["start"], "end": seg["end"],
                "text": self.edited_data.get(str(seg["id"]), seg["text"])}

    def _put_segments_on_clipboard(self, segs, label):
        fmt_label = self.copy_format_combo.currentText()
        fmt = _COPY_FORMAT_MAP.get(fmt_label, "txt")
        include_ts = self.timestamps_chk.isChecked()
        try:
            text = tf.serialize(fmt, segs, include_timestamps=include_ts)
        except Exception:
            text = tf.to_plain(segs, include_timestamps=include_ts)
        QGuiApplication.clipboard().setText(text)
        self.status_message.emit(f"{label} copied to clipboard as {fmt_label}.")

    def _copy_current_transcript(self):
        intervals = self._selected_intervals()
        if not intervals:
            return
        segs = [self._seg_with_edit(s) for s in self._matched_segments(intervals[:1])]
        self._put_segments_on_clipboard(segs, "Current slide transcript")

    def _copy_selected_transcripts(self):
        intervals = self._selected_intervals()
        if not intervals:
            return
        segs = [self._seg_with_edit(s) for s in self._matched_segments(intervals)]
        self._put_segments_on_clipboard(segs, "Selected slides' transcript")

    def _copy_full_transcript(self):
        segs = [self._seg_with_edit(seg) for seg in self.raw_segments]
        self._put_segments_on_clipboard(segs, "Full transcript")

    def _copy_current_topic(self):
        self._copy_current_transcript()

    # ------------------------------------------------------------------ #
    # decisions (never physical deletion)
    # ------------------------------------------------------------------ #
    def _on_decision_requested(self, kind):
        if kind == "keep":
            self._bulk_keep()
        elif kind == "reject":
            self._bulk_reject()
        elif kind == "restore":
            self._bulk_restore()

    def _save_candidates_snapshot(self):
        if not self.job:
            return
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        snapshot_path = os.path.join(self.job.paths["root"], "candidates.json.snapshot")
        if os.path.exists(candidates_path):
            try:
                shutil.copy2(candidates_path, snapshot_path)
            except Exception:
                pass

    def _push_undo_state(self):
        if not self.job:
            return
        import copy
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        self.undo_stack.append(copy.deepcopy(candidates))

    def undo_review_action(self):
        if not self.job or not self.undo_stack:
            self.status_message.emit("Nothing to undo.")
            return
        previous = self.undo_stack.pop()
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        FileManager.write_json_atomic(candidates_path, previous)
        selected_rows = [self.slides_view.row(i) for i in self.slides_view.selectedItems()]
        self.load_review_data()
        for r in selected_rows:
            if 0 <= r < self.slides_view.count():
                self.slides_view.item(r).setSelected(True)
        self.status_message.emit("Undo successful.")

    def _apply_decision(self, decision, confirm_label):
        selected_items = self.slides_view.selectedItems()
        if not selected_items:
            return
        if len(selected_items) > 20:
            reply = QMessageBox.question(
                self, f"Confirm Bulk {confirm_label}",
                f"{confirm_label} selected {len(selected_items)} slides?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._save_candidates_snapshot()
        self._push_undo_state()
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        selected_frames = [item.data(CAND_ROLE)["frame_number"] for item in selected_items]
        selected_rows = [self.slides_view.row(i) for i in selected_items]
        for c in candidates:
            if c["frame_number"] in selected_frames:
                c["decision"] = decision
        FileManager.write_json_atomic(candidates_path, candidates)
        self.load_review_data()
        for r in selected_rows:
            if 0 <= r < self.slides_view.count():
                self.slides_view.item(r).setSelected(True)

    def _bulk_keep(self):
        self._apply_decision("accepted", "Keep")

    def _bulk_reject(self):
        self._apply_decision("rejected", "Reject")

    def _bulk_restore(self):
        self._apply_decision("accepted", "Restore")

    # ------------------------------------------------------------------ #
    # context-menu extras
    # ------------------------------------------------------------------ #
    def export_selected_images(self):
        items = self.slides_view.selectedItems()
        if not items or not self.job:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Export selected slides to…")
        if not out_dir:
            return
        n = 0
        for item in items:
            cand = item.data(CAND_ROLE)
            src = os.path.join(self.job.paths["candidates"], cand.get("image_filename", ""))
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(out_dir, os.path.basename(src)))
                n += 1
        self.status_message.emit(f"Exported {n} slide image(s) to {out_dir}.")

    def _copy_image(self, cand):
        img_p = os.path.join(self.job.paths["candidates"], cand.get("image_filename", ""))
        pix = QPixmap(img_p)
        if not pix.isNull():
            QGuiApplication.clipboard().setPixmap(pix)
            self.status_message.emit("Slide image copied to clipboard.")

    def _open_timestamp(self, cand):
        t = cand.get("timestamp_seconds", 0.0)
        video = self.job.manifest.get("source", {}).get("original_path", "")
        self.status_message.emit(
            f"Slide source: {os.path.basename(video)} @ {cand.get('timestamp_formatted', '')} "
            f"({t:.1f}s)")
        if os.path.exists(video):
            os.startfile(video)

    # ------------------------------------------------------------------ #
    def select_all_slides(self):
        self.slides_view.selectAll()

    def handle_key_delete(self):
        if self.slides_view.hasFocus():
            self._bulk_reject()

    def handle_key_restore(self):
        if self.slides_view.hasFocus():
            self._bulk_restore()
