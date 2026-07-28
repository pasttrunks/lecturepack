"""Read-only diagnostics projection of the admitted runtime contract."""
from __future__ import annotations

from copy import deepcopy


class RuntimeDiagnosticsService:
    """Project immutable bootstrap evidence without re-discovering runtime files."""

    def __init__(self, config_manager, bootstrap_result):
        self._config = config_manager
        self._result = bootstrap_result

    def runtime_health_snapshot(self) -> dict:
        persisted = self._config.get("runtime_health", {})
        if not isinstance(persisted, dict):
            persisted = {}
        return {
            "inventory_identity": persisted.get("identity"),
            "admission_state": self._result.state,
            "validation_mode": self._result.validation_mode,
            "components": deepcopy(dict(self._result.components)),
            "fallback_notice": deepcopy(self._result.fallback_notice),
        }
