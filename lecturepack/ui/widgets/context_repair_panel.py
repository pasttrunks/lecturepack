"""
lecturepack.ui.widgets.context_repair_panel
===========================================

Context Repair workspace (v1.1, Phases 4+6).

Fault isolation contract:
  * The deterministic (offline) provider runs synchronously -- it is pure
    local CPU and cannot fail on I/O.
  * The Ollama provider ALWAYS runs in an AiRepairWorker QThread; it is never
    called on the GUI thread, never auto-runs, and its proposals are never
    auto-accepted.
  * Every failure surfaces as an inline, recoverable error bar offering
    Retry / Use deterministic repair only / Open Ollama settings / Copy
    diagnostic details. An Ollama crash can never take LecturePack down.

Layer separation is unchanged from v1.0.1: raw.json and normalized.json are
never written here; corrections.json is a reversible CorrectionSet and
corrected.json contains only accepted corrections.
"""
from __future__ import annotations

import os
import re
import difflib

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import transcript_service as ts
from lecturepack.services.ai_repair_service import AiRepairWorker

_CAP = re.compile(r"\b([A-Z][A-Za-z'\-]+)\b")
_NUMLIKE = re.compile(r"\d")

FILTERS = ["all", "pending", "accepted", "rejected", "low confidence",
           "proper names", "dates/numbers", "spelling"]

HIGH_CONFIDENCE = 0.75


def _escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def changed_words_html(original: str, proposed: str, approved_names):
    """HTML diff of the proposed text: changed words underlined; proper names
    (capitalized or approved) in purple, other edits in red."""
    approved_lower = {n.lower() for n in approved_names}
    o_words = original.split()
    p_words = proposed.split()
    sm = difflib.SequenceMatcher(None, [w.lower() for w in o_words],
                                 [w.lower() for w in p_words])
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.extend(_escape(w) for w in p_words[j1:j2])
        else:
            for w in p_words[j1:j2]:
                is_name = bool(_CAP.match(w)) or w.lower() in approved_lower
                colour = "#8E24AA" if is_name else "#C62828"
                out.append(f'<span style="color:{colour};font-weight:bold;'
                           f'text-decoration:underline">{_escape(w)}</span>')
    return " ".join(out)


def classify(correction) -> str:
    """proper_name | number_date | spelling -- for filtering."""
    orig, prop = correction.original_text, correction.corrected_text
    changed = set(prop.split()) - set(orig.split())
    for w in changed:
        if _CAP.match(w):
            return "proper_name"
    if _NUMLIKE.search(prop) and _NUMLIKE.search(orig) and \
            re.findall(r"\d+", prop) != re.findall(r"\d+", orig):
        return "number_date"
    return "spelling"


class ContextRepairPanel(QWidget):
    corrections_saved = Signal()

    def __init__(self, job, config_manager=None, parent=None):
        super().__init__(parent)
        self.job = job
        self.config_manager = config_manager

        self.raw = None
        self.norm = None
        self.correction_set = ts.CorrectionSet()
        self.approved_names = self._load_approved_names()
        self._undo_stack = []
        self._worker = None
        self._seg_times = {}

        self._build_ui()
        self._load_layers()
        self._load_or_generate_initial()
        self._refresh_table()

    # ------------------------------------------------------------------ #
    # persistence helpers
    # ------------------------------------------------------------------ #
    def _transcript_dir(self):
        return self.job.paths["transcript"]

    def _load_approved_names(self):
        names = self.job.settings.get("context_names")
        if isinstance(names, list) and names:
            return [str(n) for n in names]
        glossary = self.job.settings.get("whisper", {}).get("glossary", "")
        return [t.strip() for t in re.split(r"[,\n]", glossary) if t.strip()]

    def _save_approved_names(self):
        self.job.settings["context_names"] = list(self.approved_names)
        # Mirror into the whisper glossary so retranscription uses the same context.
        self.job.settings.setdefault("whisper", {})["glossary"] = ", ".join(self.approved_names)
        self.job.save()

    def _ollama_settings(self):
        s = self.job.settings.get("ollama")
        if not isinstance(s, dict):
            s = {}
        defaults = {}
        if self.config_manager is not None:
            defaults = self.config_manager.get("ollama", {}) or {}
        merged = dict(defaults)
        merged.update(s)
        return merged

    def ollama_enabled(self):
        o = self._ollama_settings()
        return bool(o.get("enabled")) and bool(o.get("model"))

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("Context Repair — raw Whisper output is never overwritten; "
                        "every correction is reversible. AI proposals are never auto-accepted.")
        header.setProperty("muted", True)
        header.setWordWrap(True)
        layout.addWidget(header)

        # Inline recoverable error bar (hidden by default)
        self.error_bar = QFrame()
        self.error_bar.setProperty("card", True)
        eb = QHBoxLayout(self.error_bar)
        self.error_lbl = QLabel("")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setProperty("chip", "err")
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.clicked.connect(self._generate_ai)
        self.deterministic_btn = QPushButton("Use deterministic repair only")
        self.deterministic_btn.clicked.connect(self._generate_deterministic)
        self.open_settings_btn = QPushButton("Open Ollama settings")
        self.copy_diag_btn = QPushButton("Copy diagnostic details")
        self.copy_diag_btn.clicked.connect(self._copy_diagnostics)
        for w in (self.error_lbl,):
            eb.addWidget(w, 1)
        for w in (self.retry_btn, self.deterministic_btn, self.open_settings_btn,
                  self.copy_diag_btn):
            eb.addWidget(w)
        self.error_bar.setVisible(False)
        self._last_diagnostics = ""
        layout.addWidget(self.error_bar)

        body = QHBoxLayout()

        # Context & Names editor (left)
        names_grp = QGroupBox("Context && Names")
        names_layout = QVBoxLayout(names_grp)
        names_layout.addWidget(QLabel("Approved terms feed whisper prompting and proposals:"))
        self.names_list = QListWidget()
        self.names_list.addItems(self.approved_names)
        names_layout.addWidget(self.names_list, 1)
        add_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Tutankhamun, Abu Simbel")
        self.name_input.returnPressed.connect(self._add_name)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_name)
        rm_btn = QPushButton("Remove")
        rm_btn.clicked.connect(self._remove_name)
        add_row.addWidget(self.name_input)
        add_row.addWidget(add_btn)
        add_row.addWidget(rm_btn)
        names_layout.addLayout(add_row)

        self.regen_deterministic_btn = QPushButton("Regenerate (deterministic)")
        self.regen_deterministic_btn.clicked.connect(self._generate_deterministic)
        names_layout.addWidget(self.regen_deterministic_btn)
        self.generate_ai_btn = QPushButton("Generate proposals with AI (Ollama)")
        self.generate_ai_btn.setProperty("primary", True)
        self.generate_ai_btn.clicked.connect(self._generate_ai)
        names_layout.addWidget(self.generate_ai_btn)
        self.cancel_ai_btn = QPushButton("Cancel AI generation")
        self.cancel_ai_btn.clicked.connect(self._cancel_ai)
        self.cancel_ai_btn.setVisible(False)
        names_layout.addWidget(self.cancel_ai_btn)
        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 100)
        self.ai_progress.setVisible(False)
        names_layout.addWidget(self.ai_progress)
        names_grp.setMaximumWidth(330)
        body.addWidget(names_grp)

        # Proposals table (right)
        right = QWidget()
        right_layout = QVBoxLayout(right)

        filt_row = QHBoxLayout()
        filt_row.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(FILTERS)
        self.filter_combo.currentIndexChanged.connect(self._refresh_table)
        filt_row.addWidget(self.filter_combo)
        filt_row.addStretch(1)
        self.summary_lbl = QLabel("")
        filt_row.addWidget(self.summary_lbl)
        right_layout.addLayout(filt_row)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["Seg", "Time", "Original (normalized)", "Proposed (editable)",
             "Changes", "Why", "Conf", "Source", "Status"])
        hdr = self.table.horizontalHeader()
        for col in (2, 3, 4, 5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        right_layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for label, slot in [("Accept", self._accept_selected),
                            ("Reject", self._reject_selected),
                            ("Apply Edit", self._apply_edit_selected),
                            ("Revert", self._revert_selected)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            actions.addWidget(b)
        actions.addStretch(1)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self._undo)
        accept_hi = QPushButton("Accept high-confidence deterministic")
        accept_hi.clicked.connect(self._accept_all_high_deterministic)
        reject_all = QPushButton("Reject all")
        reject_all.clicked.connect(self._reject_all)
        actions.addWidget(self.undo_btn)
        actions.addWidget(accept_hi)
        actions.addWidget(reject_all)
        right_layout.addLayout(actions)

        body.addWidget(right, 1)
        layout.addLayout(body, 1)

        foot = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setProperty("chip", "ok")
        foot.addWidget(self.status_lbl)
        foot.addStretch(1)
        save_btn = QPushButton("Save corrections")
        save_btn.setProperty("primary", True)
        save_btn.clicked.connect(self._save)
        foot.addWidget(save_btn)
        layout.addLayout(foot)

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def _load_layers(self):
        td = self._transcript_dir()
        raw_path = os.path.join(td, "raw.json")
        norm_path = os.path.join(td, "normalized.json")
        try:
            if os.path.exists(raw_path):
                import json
                with open(raw_path, encoding="utf-8") as f:
                    self.raw = ts.parse_raw_whisper_json(json.load(f))
            if os.path.exists(norm_path):
                self.norm = ts.NormalizedTranscript.from_dict(
                    FileManager.read_json_safe(norm_path, {}))
            elif self.raw is not None:
                self.norm = ts.normalize_transcript(self.raw)
        except Exception as e:
            self._show_error("bad_layers", f"Could not load transcript layers: {e}", str(e))
        if self.norm is not None:
            self._seg_times = {s.id: s.t0_ms / 1000.0 for s in self.norm.segments}

    def _load_or_generate_initial(self):
        corr_path = os.path.join(self._transcript_dir(), "corrections.json")
        if os.path.exists(corr_path):
            self.correction_set = ts.CorrectionSet.from_dict(
                FileManager.read_json_safe(corr_path, {}))
            if self.correction_set.corrections:
                self.status_lbl.setText(
                    f"Loaded {len(self.correction_set.corrections)} saved proposal(s).")
                return
        # Deterministic pass is safe to run synchronously (pure local CPU).
        # The Ollama pass NEVER runs automatically.
        self._generate_deterministic(save=False)

    # ------------------------------------------------------------------ #
    # generation
    # ------------------------------------------------------------------ #
    def _push_undo(self):
        self._undo_stack.append(self.correction_set.to_dict())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _generate_deterministic(self, save=True):
        self.error_bar.setVisible(False)
        if self.norm is None:
            self.status_lbl.setText("No transcript available yet.")
            return
        self._push_undo()
        provider = ts.DeterministicNameProvider(self.approved_names)
        engine = ts.ContextRepairEngine(provider=provider, approved_names=self.approved_names)
        try:
            new_set = engine.propose(self.norm)
        except Exception as e:
            self._show_error("internal", f"Proposal generation failed: {e}", str(e))
            return
        for c in new_set.corrections:
            c.source = "deterministic"
        self._merge_proposals(new_set.corrections)
        self.status_lbl.setText(
            f"Deterministic pass proposed {len(new_set.corrections)} correction(s).")
        self._refresh_table()
        if save:
            self._save(quiet=True)

    def _generate_ai(self):
        """Ollama proposals -- ALWAYS via the fault-isolated worker thread."""
        self.error_bar.setVisible(False)
        if self.norm is None:
            self.status_lbl.setText("No transcript available yet.")
            return
        if self._worker is not None:
            return  # already running
        o = self._ollama_settings()
        if not o.get("model"):
            self._show_error(
                "unavailable",
                "No Ollama model is configured. Pick one in Settings → AI (Ollama).",
                "job.settings['ollama']['model'] is empty")
            return
        o = dict(o)
        o["enabled"] = True

        self._worker = AiRepairWorker(
            transcript_dir=self._transcript_dir(),
            approved_names=self.approved_names,
            norm_dict=self.norm.to_dict(),
            ollama_settings=o,
            course_title=self.job.manifest.get("title", ""),
            glossary=self.job.settings.get("whisper", {}).get("glossary", ""))
        self._worker.progress.connect(self._on_ai_progress)
        self._worker.status.connect(self.status_lbl.setText)
        self._worker.finished_ok.connect(self._on_ai_finished)
        self._worker.failed.connect(self._on_ai_failed)
        self.generate_ai_btn.setEnabled(False)
        self.cancel_ai_btn.setVisible(True)
        self.ai_progress.setVisible(True)
        self.ai_progress.setValue(0)
        self._worker.start()

    def _cancel_ai(self):
        if self._worker is not None:
            self._worker.cancel()
            self.status_lbl.setText("Cancelling…")

    def _teardown_worker(self):
        self.generate_ai_btn.setEnabled(True)
        self.cancel_ai_btn.setVisible(False)
        self.ai_progress.setVisible(False)
        self._worker = None

    def _on_ai_progress(self, done, total):
        self.ai_progress.setMaximum(max(1, total))
        self.ai_progress.setValue(done)
        self.status_lbl.setText(f"AI proposals: chunk {done}/{total}…")

    def _on_ai_finished(self, result):
        self._push_undo()
        corrections = [ts.Correction.from_dict(d) for d in result.get("corrections", [])]
        kind = result.get("provider_kind", "ollama")
        for c in corrections:
            c.source = kind
        self._merge_proposals(corrections)
        stats = result.get("stats", {})
        note = f"AI pass proposed {len(corrections)} correction(s)"
        if stats.get("chunks_failed"):
            note += f" ({stats['chunks_failed']} of {stats.get('chunks_total', '?')} chunks failed)"
        if stats.get("cache_hits"):
            note += f" [{stats['cache_hits']} cached]"
        if stats.get("cancelled"):
            note += " — cancelled early; partial results kept"
        self.status_lbl.setText(note + ".")
        self._teardown_worker()
        self._refresh_table()
        self._save(quiet=True)

    def _on_ai_failed(self, kind, message, details):
        self._teardown_worker()
        self._show_error(kind, message, details)

    def _merge_proposals(self, new_corrections):
        """Merge newly generated proposals into the existing set WITHOUT
        touching corrections the user already resolved (accepted/rejected)."""
        resolved = {c.segment_id: c for c in self.correction_set.corrections
                    if c.status in ("accepted", "rejected")}
        merged = dict(resolved)
        for c in new_corrections:
            if c.segment_id not in resolved:
                merged[c.segment_id] = c
        self.correction_set = ts.CorrectionSet(
            sorted(merged.values(), key=lambda c: c.segment_id))

    def _show_error(self, kind, message, details):
        self._last_diagnostics = f"[{kind}] {message}\n\n{details}"
        self.error_lbl.setText(message)
        self.error_bar.setVisible(True)

    def _copy_diagnostics(self):
        QGuiApplication.clipboard().setText(self._last_diagnostics)
        self.status_lbl.setText("Diagnostics copied to clipboard.")

    # ------------------------------------------------------------------ #
    # table rendering
    # ------------------------------------------------------------------ #
    def _norm_text_for(self, seg_id):
        if self.norm:
            for s in self.norm.segments:
                if s.id == seg_id:
                    return s.text
        return ""

    def _visible_corrections(self):
        f = self.filter_combo.currentText()
        out = []
        for c in self.correction_set.corrections:
            cls = classify(c)
            if f == "all":
                out.append(c)
            elif f == "pending" and c.status in ("proposed", "needs_review"):
                out.append(c)
            elif f == "accepted" and c.status == "accepted":
                out.append(c)
            elif f == "rejected" and c.status == "rejected":
                out.append(c)
            elif f == "low confidence" and c.confidence < HIGH_CONFIDENCE:
                out.append(c)
            elif f == "proper names" and cls == "proper_name":
                out.append(c)
            elif f == "dates/numbers" and cls == "number_date":
                out.append(c)
            elif f == "spelling" and cls == "spelling":
                out.append(c)
        return out

    def _refresh_table(self):
        rows = self._visible_corrections()
        self.table.setRowCount(len(rows))
        self._row_corrections = rows
        for r, c in enumerate(rows):
            norm_t = self._norm_text_for(c.segment_id) or c.original_text
            t = self._seg_times.get(c.segment_id)
            t_str = ""
            if t is not None:
                m, s = divmod(int(t), 60)
                h, m = divmod(m, 60)
                t_str = f"{h:d}:{m:02d}:{s:02d}"
            self.table.setItem(r, 0, QTableWidgetItem(str(c.segment_id)))
            self.table.setItem(r, 1, QTableWidgetItem(t_str))
            self.table.setItem(r, 2, QTableWidgetItem(norm_t))
            edit = QLineEdit(c.corrected_text)
            self.table.setCellWidget(r, 3, edit)
            diff = QLabel()
            diff.setTextFormat(Qt.TextFormat.RichText)
            diff.setText(changed_words_html(norm_t, c.corrected_text, self.approved_names))
            self.table.setCellWidget(r, 4, diff)
            self.table.setItem(r, 5, QTableWidgetItem(c.reason))
            self.table.setItem(r, 6, QTableWidgetItem(f"{c.confidence:.2f}"))
            src = c.source if c.source not in ("context_repair",) else "deterministic"
            self.table.setItem(r, 7, QTableWidgetItem(src))
            status_item = QTableWidgetItem(c.status)
            colour = {"accepted": QColor("#D3F0DF"), "rejected": QColor("#FADAD5"),
                      "needs_review": QColor("#FBEDC6")}.get(c.status)
            if colour:
                status_item.setBackground(colour)
                status_item.setForeground(QColor("#1C1A16"))
            self.table.setItem(r, 8, status_item)
            self.table.setRowHeight(r, 44)
        self._update_summary()

    def _update_summary(self):
        cs = self.correction_set.corrections
        acc = sum(1 for c in cs if c.status == "accepted")
        rej = sum(1 for c in cs if c.status == "rejected")
        pend = sum(1 for c in cs if c.status in ("proposed", "needs_review"))
        self.summary_lbl.setText(
            f"{len(cs)} proposals · {acc} accepted · {rej} rejected · {pend} pending")

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def _selected_corrections(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        cs = getattr(self, "_row_corrections", [])
        picked = [cs[r] for r in rows if 0 <= r < len(cs)]
        if not picked and 0 <= self.table.currentRow() < len(cs):
            picked = [cs[self.table.currentRow()]]
        return picked

    def _accept_selected(self):
        picked = self._selected_corrections()
        if picked:
            self._push_undo()
            for c in picked:
                self.correction_set.accept(c.segment_id)
            self._refresh_table()

    def _reject_selected(self):
        picked = self._selected_corrections()
        if picked:
            self._push_undo()
            for c in picked:
                self.correction_set.reject(c.segment_id)
            self._refresh_table()

    def _revert_selected(self):
        """Back to 'proposed' -- undoes an accept/reject decision per row."""
        picked = self._selected_corrections()
        if picked:
            self._push_undo()
            for c in picked:
                c.status = "proposed"
            self._refresh_table()

    def _apply_edit_selected(self):
        r = self.table.currentRow()
        cs = getattr(self, "_row_corrections", [])
        if not (0 <= r < len(cs)):
            return
        c = cs[r]
        edit = self.table.cellWidget(r, 3)
        if edit:
            new_text = edit.text().strip()
            if new_text:
                self._push_undo()
                c.corrected_text = new_text
                c.source = "user_edit"
                c.status = "accepted"  # a manual edit is an explicit approval
        self._refresh_table()

    def _accept_all_high_deterministic(self):
        """Bulk-accept ONLY high-confidence deterministic proposals; AI
        proposals always require individual review (never auto-accepted)."""
        self._push_undo()
        n = 0
        for c in self.correction_set.corrections:
            if (c.status in ("proposed", "needs_review")
                    and c.confidence >= HIGH_CONFIDENCE
                    and c.source in ("deterministic", "context_repair")):
                c.status = "accepted"
                n += 1
        self.status_lbl.setText(f"Accepted {n} high-confidence deterministic proposal(s).")
        self._refresh_table()

    def _reject_all(self):
        self._push_undo()
        self.correction_set.reject_all()
        self._refresh_table()

    def _undo(self):
        if not self._undo_stack:
            self.status_lbl.setText("Nothing to undo.")
            return
        self.correction_set = ts.CorrectionSet.from_dict(self._undo_stack.pop())
        self._refresh_table()
        self.status_lbl.setText("Undo applied.")

    def _add_name(self):
        term = self.name_input.text().strip()
        if term and term not in self.approved_names:
            self.approved_names.append(term)
            self.names_list.addItem(term)
            self.name_input.clear()
            self._save_approved_names()

    def _remove_name(self):
        for item in self.names_list.selectedItems():
            term = item.text()
            if term in self.approved_names:
                self.approved_names.remove(term)
            self.names_list.takeItem(self.names_list.row(item))
        self._save_approved_names()

    def _save(self, quiet=False):
        td = self._transcript_dir()
        FileManager.write_json_atomic(os.path.join(td, "corrections.json"),
                                      self.correction_set.to_dict())
        if self.norm is not None:
            reviewed = self.correction_set.reviewed_segments(self.norm)
            FileManager.write_json_atomic(
                os.path.join(td, "corrected.json"),
                {"raw_content_hash": self.norm.raw_content_hash,
                 "segments": [s.to_dict() for s in reviewed]})
        self._save_approved_names()
        if not quiet:
            self.status_lbl.setText("Corrections saved (raw Whisper output unchanged).")
        self.corrections_saved.emit()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def shutdown(self):
        """Called when the hosting dialog/page closes: cancel or detach any
        in-flight AI request safely."""
        if self._worker is not None:
            self._worker.detach_and_stop()
            self._worker = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
