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

    def _forward_service_event(self, payload: dict) -> None:
        """Relay each service event immediately from the worker thread."""
        outgoing = dict(payload)
        if outgoing.get("kind") == "metadata_ready":
            offer = self._service.active_offer(self._operation_id)
            if offer is not None:
                outgoing.update({
                    "app_version": str(offer.app_version),
                    "official_source": str(offer.official_source),
                    "affected_components": [str(item) for item in offer.affected_components],
                    "download_size_bytes": int(offer.download_size_bytes),
                })
        self.repair_event.emit(outgoing)

    def run(self):
        self._service.set_event_sink(self._operation_id, self._forward_service_event)
        try:
            self._service.perform_repair(self._operation_id) if self._confirm else self._service.begin_repair_offer(self._operation_id)
        except Exception as error:
            if not any(event.operation_id == self._operation_id and event.kind in {"failed", "cancelled"} for event in self._service.events):
                self.repair_event.emit({"operation_id": self._operation_id, "kind": "failed", "detail": self._safe_detail(error)})
        finally:
            self._service.set_event_sink(self._operation_id, None)
