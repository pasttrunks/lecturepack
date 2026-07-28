"""CPU-first bootstrap admission policy for the bundled runtime contract."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from lecturepack.infrastructure.runtime_inventory import inventory_for_root, payload_identity, resolve_inventory
from lecturepack.infrastructure.runtime_validation import RuntimeValidator


@dataclass(frozen=True)
class RuntimeBootstrapResult:
    """Immutable outcome used by later startup composition and diagnostics."""

    state: str
    validation_mode: str
    components: Mapping[str, Mapping[str, Any]]
    fallback_notice: Mapping[str, str] | None = None


class RuntimeBootstrapService:
    """Admit only a fully validated canonical CPU payload.

    Optional engines are intentionally resolved after CPU admission, preventing
    driver or optional-DLL failures from becoming a startup dependency.
    """

    def __init__(
        self,
        config_manager,
        *,
        runtime_root: Path | str | None = None,
        inventory_resolver: Callable[[Path], Mapping[str, Path]] | None = None,
        identity_provider: Callable[[Path], str] | None = None,
        full_validator: Callable[[Mapping[str, Path]], Mapping[str, Mapping[str, Any]]] | None = None,
        optional_resolver: Callable[[str], tuple[str, str]] | None = None,
    ):
        self.config = config_manager
        self.runtime_root = Path(runtime_root or config_manager.resource_dir)
        self.inventory_resolver = inventory_resolver or resolve_inventory
        self.identity_provider = identity_provider or payload_identity
        self.full_validator = full_validator or self._validate_full
        self.optional_resolver = optional_resolver or self._resolve_optional

    def assess(self, *, trigger: str = "startup") -> RuntimeBootstrapResult:
        """Assess the canonical CPU payload and persist only complete facts."""
        try:
            paths = dict(self.inventory_resolver(self.runtime_root))
            identity = self.identity_provider(self.runtime_root)
        except Exception as error:
            return RuntimeBootstrapResult("SETUP_REQUIRED", "light", {"inventory": {"healthy": False, "reason": str(error)}})

        previous = self.config.get("runtime_health")
        full = self._requires_full(previous, identity, paths, trigger)
        evidence: dict[str, Mapping[str, Any]] = {
            name: {"healthy": path.is_file() and path.stat().st_size > 0, "path": str(path)}
            for name, path in paths.items()
        }
        if not all(item["healthy"] for item in evidence.values()):
            return RuntimeBootstrapResult("SETUP_REQUIRED", "light", evidence)

        mode = "full" if full else "light"
        if full:
            try:
                full_evidence = self.full_validator(paths)
            except Exception as error:
                evidence = {
                    name: {**item, "healthy": False, "reason": f"full validation failed: {error}"}
                    for name, item in evidence.items()
                }
                return RuntimeBootstrapResult("SETUP_REQUIRED", mode, evidence)
            evidence = {
                name: {
                    **evidence[name],
                    **dict(full_evidence.get(name, {"healthy": False, "reason": "missing full validation evidence"})),
                }
                for name in paths
            }
            if not all(item.get("healthy") is True for item in evidence.values()):
                return RuntimeBootstrapResult("SETUP_REQUIRED", mode, evidence)

        bundled_model = str(paths["models/ggml-base.en.bin"]) if "models/ggml-base.en.bin" in paths else ""
        runtime_health = {"identity": identity, "components": evidence, "validation_mode": mode}
        self.config.persist_runtime_health(runtime_health, bundled_model=bundled_model)
        notice = self._resolve_post_health_optional()
        return RuntimeBootstrapResult("HEALTHY", mode, evidence, notice)

    @staticmethod
    def _requires_full(previous, identity: str, paths: Mapping[str, Path], trigger: str) -> bool:
        if trigger in {"update", "repair"} or not isinstance(previous, dict):
            return True
        if previous.get("identity") != identity:
            return True
        components = previous.get("components")
        return not isinstance(components, dict) or set(components) != set(paths)

    @staticmethod
    def _validate_full(paths: Mapping[str, Path]) -> Mapping[str, Mapping[str, Any]]:
        """Run bounded local executable checks; model/DLL facts stay inventory-bound."""
        validator = RuntimeValidator()
        results: dict[str, Mapping[str, Any]] = {}
        for name, path in paths.items():
            if name == "bin/ffmpeg.exe" or name == "bin/ffprobe.exe":
                smoke = validator.run(str(path), ["-version"])
                results[name] = {"healthy": smoke.ok, "reason": smoke.reason, "exit_code": smoke.exit_code}
            elif name == "bin/whisper-cli.exe":
                smoke = validator.run(str(path), ["--help"])
                results[name] = {"healthy": smoke.ok, "reason": smoke.reason, "exit_code": smoke.exit_code}
            else:
                results[name] = {"healthy": True, "reason": "inventory readable"}
        return results

    def _resolve_optional(self, requested: str) -> tuple[str, str]:
        from lecturepack.infrastructure.transcription_engines import EngineRegistry

        resolved = EngineRegistry(self.config).resolve(requested)
        return resolved.key, resolved.reason

    def _resolve_post_health_optional(self) -> Mapping[str, str] | None:
        requested = self.config.get("engine", "auto")
        resolved, reason = self.optional_resolver(requested)
        if requested in {"cuda", "vulkan", "whispercpp-cuda", "whispercpp-vulkan"} and resolved == "whispercpp-cpu":
            self.config.set("engine", "cpu")
            return {"requested": requested, "resolved": resolved, "reason": reason}
        return None
