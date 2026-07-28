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
        try:
            result = self._service.confirm_repair(self._operation_id) if self._confirm else self._service.begin_repair_offer(self._operation_id)
            if not self._cancelled:
                payload = {"operation_id": result.operation_id, "kind": "confirmed" if self._confirm else "metadata_ready"}
                if not self._confirm:
                    payload.update({"app_version": result.app_version, "official_source": result.official_source,
                                    "affected_components": list(result.affected_components), "download_size_bytes": result.download_size_bytes})
                self.repair_event.emit(payload)
        except Exception as error:
            self.repair_event.emit({"operation_id": self._operation_id, "kind": "failed", "detail": str(error)})
