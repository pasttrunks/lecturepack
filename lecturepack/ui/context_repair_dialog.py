"""
Context Repair dialog (v1.1): a thin modal host around
``widgets.context_repair_panel.ContextRepairPanel``.

The panel is the real workspace (it is also embedded as a tab of the
Transcript page). This wrapper preserves the v1.0.1 public surface used by
tests and the packaged acceptance driver: ``correction_set``,
``approved_names``, ``names_list``, ``name_input``, ``filter_combo``,
``table``, ``status_lbl``, ``_add_name``, ``_remove_name``, ``_save``.

Crash-isolation (Phase 4): constructing this dialog performs NO network I/O.
Only the deterministic offline provider may run synchronously; Ollama
generation happens exclusively in the panel's worker thread and closing the
dialog cancels/detaches it safely.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout

from lecturepack.ui.widgets.context_repair_panel import ContextRepairPanel


class ContextRepairDialog(QDialog):
    def __init__(self, job, config_manager=None, parent=None):
        super().__init__(parent)
        self.job = job
        self.config_manager = config_manager
        self.setWindowTitle("Context Repair — review proposed corrections")
        self.resize(1200, 740)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.panel = ContextRepairPanel(job, config_manager, self)
        layout.addWidget(self.panel)

    # ---- v1.0.1 compatibility surface (delegates to the panel) ---------- #
    @property
    def correction_set(self):
        return self.panel.correction_set

    @correction_set.setter
    def correction_set(self, value):
        self.panel.correction_set = value

    @property
    def approved_names(self):
        return self.panel.approved_names

    @property
    def names_list(self):
        return self.panel.names_list

    @property
    def name_input(self):
        return self.panel.name_input

    @property
    def filter_combo(self):
        return self.panel.filter_combo

    @property
    def table(self):
        return self.panel.table

    @property
    def status_lbl(self):
        return self.panel.status_lbl

    def _add_name(self):
        self.panel._add_name()

    def _remove_name(self):
        self.panel._remove_name()

    def _save(self, quiet=False):
        self.panel._save(quiet=quiet)

    def closeEvent(self, event):
        self.panel.shutdown()
        super().closeEvent(event)

    def done(self, result):
        self.panel.shutdown()
        super().done(result)
