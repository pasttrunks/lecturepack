"""
Context Repair workspace (Layer 3 review UI).

Presents, for each proposed correction, the original raw Whisper segment, the
deterministically normalized segment, the proposed correction with changed words
highlighted (proper-name changes highlighted separately), an explanation, and a
confidence. The user can Accept, Reject, or Edit each proposal, Accept-all
high-confidence, or Reject-all, and filter the list. A Context & Names editor
feeds both whisper prompting (on retranscription) and the proposals.

The four layers are kept strictly separate and every action is reversible:

    raw.json          Layer 1  (immutable -- never written here)
    normalized.json   Layer 2  (deterministic -- never written here)
    corrections.json  Layer 3  (this dialog; reversible CorrectionSet)
    corrected.json    user-approved transcript (accepted corrections only)

Raw Whisper output is never silently overwritten.
"""
from __future__ import annotations

import os
import re
import difflib

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QLineEdit, QComboBox, QGroupBox, QListWidget, QMessageBox,
    QHeaderView, QWidget, QAbstractItemView,
)

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.services import transcript_service as ts

_CAP = re.compile(r"\b([A-Z][A-Za-z'\-]+)\b")
_NUMLIKE = re.compile(r"\d")

FILTERS = ["all", "low confidence", "proper names", "numbers/dates",
           "unresolved", "accepted", "rejected"]

HIGH_CONFIDENCE = 0.75


def _changed_words_html(original: str, proposed: str, approved_names):
    """Return HTML for the proposed text with changed words highlighted; proper
    names (capitalized or approved) highlighted in a distinct colour."""
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
                colour = "#8e24aa" if is_name else "#c62828"  # purple names / red edits
                weight = "bold"
                out.append(f'<span style="color:{colour};font-weight:{weight};'
                           f'text-decoration:underline">{_escape(w)}</span>')
    return " ".join(out)


def _escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _classify(correction) -> str:
    """proper_name | number_date | other -- for filtering."""
    orig, prop = correction.original_text, correction.corrected_text
    changed = set(prop.split()) - set(orig.split())
    for w in changed:
        if _CAP.match(w):
            return "proper_name"
    if _NUMLIKE.search(prop) and _NUMLIKE.search(orig) and \
            re.findall(r"\d+", prop) != re.findall(r"\d+", orig):
        return "number_date"
    return "other"


class ContextRepairDialog(QDialog):
    def __init__(self, job, config_manager=None, parent=None):
        super().__init__(parent)
        self.job = job
        self.config_manager = config_manager
        self.setWindowTitle("Context Repair — review proposed corrections")
        self.resize(1150, 720)

        self.raw = None
        self.norm = None
        self.correction_set = ts.CorrectionSet()
        self.approved_names = self._load_approved_names()

        self._build_ui()
        self._load_layers()
        self._generate_or_load_proposals()
        self._refresh_table()

    # ---- persistence helpers ------------------------------------------- #
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

    # ---- UI ------------------------------------------------------------- #
    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Layer 3 · Context Repair — raw Whisper output is never "
                        "overwritten; every correction is reversible.")
        header.setStyleSheet("font-weight:bold;padding:4px;")
        layout.addWidget(header)

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
        regen_btn = QPushButton("Regenerate proposals from these terms")
        regen_btn.clicked.connect(self._regenerate)
        names_layout.addWidget(regen_btn)
        names_grp.setMaximumWidth(320)
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
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Seg", "Raw (Layer 1)", "Normalized (Layer 2)", "Proposed (editable)",
             "Changes", "Why", "Conf", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        right_layout.addWidget(self.table, 1)

        # Per-row + bulk actions
        actions = QHBoxLayout()
        for label, slot in [("Accept", self._accept_selected),
                            ("Reject", self._reject_selected),
                            ("Apply Edit", self._apply_edit_selected)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            actions.addWidget(b)
        actions.addStretch(1)
        accept_hi = QPushButton("Accept all high-confidence")
        accept_hi.clicked.connect(self._accept_all_high)
        reject_all = QPushButton("Reject all")
        reject_all.clicked.connect(self._reject_all)
        actions.addWidget(accept_hi)
        actions.addWidget(reject_all)
        right_layout.addLayout(actions)

        body.addWidget(right, 1)
        layout.addLayout(body, 1)

        # Save / close
        foot = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color:#2e7d32;font-weight:bold;")
        foot.addWidget(self.status_lbl)
        foot.addStretch(1)
        save_btn = QPushButton("Save corrections")
        save_btn.setStyleSheet("background:#2196F3;color:white;font-weight:bold;padding:6px;")
        save_btn.clicked.connect(self._save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        foot.addWidget(save_btn)
        foot.addWidget(close_btn)
        layout.addLayout(foot)

    # ---- data ----------------------------------------------------------- #
    def _load_layers(self):
        td = self._transcript_dir()
        raw_path = os.path.join(td, "raw.json")
        norm_path = os.path.join(td, "normalized.json")
        if os.path.exists(raw_path):
            import json
            with open(raw_path, encoding="utf-8") as f:
                self.raw = ts.parse_raw_whisper_json(json.load(f))
        if os.path.exists(norm_path):
            self.norm = ts.NormalizedTranscript.from_dict(
                FileManager.read_json_safe(norm_path, {}))
        elif self.raw is not None:
            self.norm = ts.normalize_transcript(self.raw)

    def _provider(self):
        """LLM provider if one is configured, else the deterministic offline
        name-matching provider (never invents names)."""
        base = self.job.settings.get("context_repair", {}).get("base_url") if isinstance(
            self.job.settings.get("context_repair"), dict) else None
        if base:
            model = self.job.settings["context_repair"].get("model", "local-model")
            return ts.OpenAICompatibleProvider(base, model), "LLM"
        return ts.DeterministicNameProvider(self.approved_names), "offline"

    def _generate_or_load_proposals(self):
        # Prefer an existing saved correction set (preserves prior accept/reject).
        corr_path = os.path.join(self._transcript_dir(), "corrections.json")
        if os.path.exists(corr_path):
            self.correction_set = ts.CorrectionSet.from_dict(
                FileManager.read_json_safe(corr_path, {}))
            if self.correction_set.corrections:
                return
        self._regenerate(save=False)

    def _regenerate(self, save=True):
        if self.norm is None:
            return
        provider, kind = self._provider()
        engine = ts.ContextRepairEngine(provider=provider, approved_names=self.approved_names)
        try:
            self.correction_set = engine.propose(self.norm)
        except Exception as e:
            QMessageBox.warning(self, "Context Repair", f"Proposal generation failed: {e}")
            self.correction_set = ts.CorrectionSet()
        self.status_lbl.setText(
            f"Generated {len(self.correction_set.corrections)} proposal(s) via {kind} provider.")
        self._refresh_table()
        if save:
            self._save(quiet=True)

    # ---- table rendering ------------------------------------------------ #
    def _raw_text_for(self, seg_id):
        if self.raw:
            for s in self.raw.segments:
                if s.id == seg_id:
                    return s.text.strip()
        return ""

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
            cls = _classify(c)
            if f == "all":
                out.append(c)
            elif f == "low confidence" and c.confidence < HIGH_CONFIDENCE:
                out.append(c)
            elif f == "proper names" and cls == "proper_name":
                out.append(c)
            elif f == "numbers/dates" and cls == "number_date":
                out.append(c)
            elif f == "unresolved" and c.status in ("proposed", "needs_review"):
                out.append(c)
            elif f == "accepted" and c.status == "accepted":
                out.append(c)
            elif f == "rejected" and c.status == "rejected":
                out.append(c)
        return out

    def _refresh_table(self):
        from PySide6.QtWidgets import QLabel as _QLabel
        rows = self._visible_corrections()
        self.table.setRowCount(len(rows))
        self._row_corrections = rows
        for r, c in enumerate(rows):
            raw_t = self._raw_text_for(c.segment_id)
            norm_t = self._norm_text_for(c.segment_id) or c.original_text
            self.table.setItem(r, 0, QTableWidgetItem(str(c.segment_id)))
            self.table.setItem(r, 1, QTableWidgetItem(raw_t))
            self.table.setItem(r, 2, QTableWidgetItem(norm_t))
            edit = QLineEdit(c.corrected_text)
            self.table.setCellWidget(r, 3, edit)
            diff = _QLabel()
            diff.setTextFormat(Qt.TextFormat.RichText)
            diff.setText(_changed_words_html(norm_t, c.corrected_text, self.approved_names))
            self.table.setCellWidget(r, 4, diff)
            self.table.setItem(r, 5, QTableWidgetItem(c.reason))
            self.table.setItem(r, 6, QTableWidgetItem(f"{c.confidence:.2f}"))
            status_item = QTableWidgetItem(c.status)
            colour = {"accepted": QColor("#c8e6c9"), "rejected": QColor("#ffcdd2"),
                      "needs_review": QColor("#fff9c4")}.get(c.status)
            if colour:
                status_item.setBackground(colour)
            self.table.setItem(r, 7, status_item)
            self.table.setRowHeight(r, 48)
        self._update_summary()

    def _update_summary(self):
        cs = self.correction_set.corrections
        acc = sum(1 for c in cs if c.status == "accepted")
        rej = sum(1 for c in cs if c.status == "rejected")
        pend = sum(1 for c in cs if c.status in ("proposed", "needs_review"))
        self.summary_lbl.setText(f"{len(cs)} proposals · {acc} accepted · {rej} rejected · {pend} pending")

    # ---- actions -------------------------------------------------------- #
    def _selected_correction(self):
        r = self.table.currentRow()
        if 0 <= r < len(getattr(self, "_row_corrections", [])):
            return self._row_corrections[r]
        return None

    def _accept_selected(self):
        c = self._selected_correction()
        if c:
            self.correction_set.accept(c.segment_id)
            self._refresh_table()

    def _reject_selected(self):
        c = self._selected_correction()
        if c:
            self.correction_set.reject(c.segment_id)
            self._refresh_table()

    def _apply_edit_selected(self):
        r = self.table.currentRow()
        c = self._selected_correction()
        if not c:
            return
        edit = self.table.cellWidget(r, 3)
        if edit:
            new_text = edit.text().strip()
            if new_text:
                c.corrected_text = new_text
                c.source = "user_edit"
                c.status = "accepted"  # a manual edit is an explicit approval
        self._refresh_table()

    def _accept_all_high(self):
        for c in self.correction_set.corrections:
            if c.status in ("proposed", "needs_review") and c.confidence >= HIGH_CONFIDENCE:
                c.status = "accepted"
        self._refresh_table()

    def _reject_all(self):
        self.correction_set.reject_all()
        self._refresh_table()

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
        # Layer 3: reversible correction set (raw & normalized untouched).
        FileManager.write_json_atomic(os.path.join(td, "corrections.json"),
                                      self.correction_set.to_dict())
        # User-approved corrected transcript layer (accepted corrections only).
        if self.norm is not None:
            reviewed = self.correction_set.reviewed_segments(self.norm)
            FileManager.write_json_atomic(
                os.path.join(td, "corrected.json"),
                {"raw_content_hash": self.norm.raw_content_hash,
                 "segments": [s.to_dict() for s in reviewed]})
        self._save_approved_names()
        if not quiet:
            self.status_lbl.setText("Corrections saved (raw Whisper output unchanged).")
