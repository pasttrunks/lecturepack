"""Controller boundary for runtime-health diagnostics."""
from __future__ import annotations


class RuntimeDiagnosticsController:
    """Delegate the canonical runtime snapshot without constructing inventory."""

    def __init__(self, runtime_diagnostics_service):
        self._service = runtime_diagnostics_service

    def runtime_health_snapshot(self) -> dict:
        return self._service.runtime_health_snapshot()
