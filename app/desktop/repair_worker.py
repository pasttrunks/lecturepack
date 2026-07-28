"""Qt boundary for the otherwise Qt-free runtime repair coordinator."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class RuntimeRepairWorker(QThread):
    """Run one repair command and emit only JSON-safe operation events."""

    repair_event = Signal(dict)

    def __init__(self, service, operation_id: str, *, confirm: bool = False, parent=None):
        super().__init__(parent)
        self._service, self._operation_id, self._confirm = service, operation_id, confirm
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self._service.cancel(self._operation_id)

    def run(self):
        start = len(self._service.events)
        try:
            result = self._service.perform_repair(self._operation_id) if self._confirm else self._service.begin_repair_offer(self._operation_id)
            for event in self._service.events[start:]:
                self.repair_event.emit(event.payload())
            if not self._confirm and not self._cancelled:
                self.repair_event.emit({"operation_id": result.operation_id, "kind": "metadata_ready", "app_version": result.app_version, "official_source": result.official_source, "affected_components": list(result.affected_components), "download_size_bytes": result.download_size_bytes})
        except Exception as error:
            emitted = self._service.events[start:]
            for event in emitted:
                self.repair_event.emit(event.payload())
            if not any(event.kind in {"failed", "cancelled"} for event in emitted):
                self.repair_event.emit({"operation_id": self._operation_id, "kind": "failed", "detail": str(error)})
