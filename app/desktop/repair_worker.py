"""Qt boundary for the otherwise Qt-free runtime repair coordinator."""
from __future__ import annotations

import re

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

    @staticmethod
    def _safe_detail(value: object) -> str:
        """Keep an unexpected worker exception safe for the JSON bridge."""
        return re.sub(r"(?i)(authorization|token|password|secret)=[^\s&]+", r"\1=[redacted]", str(value))[:1000]

    def _emit_new_events(self, start: int, result=None) -> list:
        """Forward the service sequence once, enriching the one offer event."""
        events = self._service.events[start:]
        for event in events:
            payload = event.payload()
            if event.kind == "metadata_ready" and result is not None:
                payload.update({
                    "app_version": str(result.app_version),
                    "official_source": str(result.official_source),
                    "affected_components": [str(item) for item in result.affected_components],
                    "download_size_bytes": int(result.download_size_bytes),
                })
            self.repair_event.emit(payload)
        return events

    def run(self):
        start = len(self._service.events)
        try:
            result = self._service.perform_repair(self._operation_id) if self._confirm else self._service.begin_repair_offer(self._operation_id)
            self._emit_new_events(start, result)
        except Exception as error:
            emitted = self._emit_new_events(start)
            if not any(event.kind in {"failed", "cancelled"} for event in emitted):
                self.repair_event.emit({"operation_id": self._operation_id, "kind": "failed", "detail": self._safe_detail(error)})
