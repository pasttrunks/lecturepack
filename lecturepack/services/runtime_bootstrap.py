"""CPU-first bootstrap admission policy for the bundled runtime contract."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from lecturepack.infrastructure.runtime_inventory import inventory_for_root, payload_identity, resolve_inventory
from lecturepack.infrastructure.runtime_generation import resolve_active_runtime_root
from lecturepack.infrastructure.runtime_validation import RuntimeValidator
from lecturepack.infrastructure.whisper_path_staging import WhisperPathStaging


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

    _FULL_SUCCESS_EVIDENCE_FIELDS = frozenset({
        "healthy", "reason", "exit_code", "argv", "stdout", "stderr",
        "duration_ms", "timed_out",
    })

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
        self._root_resolution_error = ""
        if runtime_root is None:
            resolution = resolve_active_runtime_root(config_manager)
            self.runtime_root = resolution.root
            self._root_resolution_error = resolution.reason if not resolution.ok else ""
        else:
            # Explicit roots are a test/packaging seam; normal startup always
            # reaches this service through the one canonical active resolver.
            self.runtime_root = Path(runtime_root)
        self.inventory_resolver = inventory_resolver or resolve_inventory
        self.identity_provider = identity_provider or payload_identity
        self.full_validator = full_validator or self._validate_full
        self.optional_resolver = optional_resolver or self._resolve_optional

    def assess(self, *, trigger: str = "startup") -> RuntimeBootstrapResult:
        """Assess the canonical CPU payload and persist only complete facts."""
        if self.runtime_root is None:
            return RuntimeBootstrapResult(
                "SETUP_REQUIRED", "light",
                {"active_runtime": {"healthy": False, "reason": self._root_resolution_error or "runtime root unavailable"}},
            )
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
        # D-01: seed the exe paths ConfigManager needs for normal processing
        # (start_processing()'s whisper gate, _kick_poster's ffmpeg lookup) from
        # this same resolved+validated inventory. Guarded individually so a
        # missing inventory entry never aborts the whole assessment.
        exe_paths = {}
        _exe_key_map = (
            ("whisper_exe", "bin/whisper-cli.exe"),
            ("ffmpeg_exe", "bin/ffmpeg.exe"),
            ("ffprobe_exe", "bin/ffprobe.exe"),
        )
        for config_key, inventory_key in _exe_key_map:
            candidate = paths.get(inventory_key)
            if candidate is not None:
                exe_paths[config_key] = str(candidate)
        runtime_health = {"identity": identity, "components": evidence, "validation_mode": mode}
        self.config.persist_runtime_health(runtime_health, bundled_model=bundled_model, exe_paths=exe_paths)
        notice = self._resolve_post_health_optional()
        return RuntimeBootstrapResult("HEALTHY", mode, evidence, notice)

    @staticmethod
    def _requires_full(previous, identity: str, paths: Mapping[str, Path], trigger: str) -> bool:
        if trigger in {"update", "repair"} or not isinstance(previous, dict):
            return True
        if previous.get("identity") != identity:
            return True
        components = previous.get("components")
        if not isinstance(components, dict) or set(components) != set(paths):
            return True
        # A matching payload identity proves only that the files are the same.
        # Light validation is safe exclusively after a complete successful full
        # admission; failed or partial evidence must be re-proven by the smoke.
        return not all(
            isinstance(component, Mapping)
            and component.get("healthy") is True
            and RuntimeBootstrapService._FULL_SUCCESS_EVIDENCE_FIELDS <= component.keys()
            for component in components.values()
        )

    @staticmethod
    def _validate_full(paths: Mapping[str, Path]) -> Mapping[str, Mapping[str, Any]]:
        """Prove canonical CPU usability with one bounded staged transcription.

        Per D-10, the three independent probes (ffmpeg -version, ffprobe
        -version, and the staged whisper transcription) run concurrently in
        a ``ThreadPoolExecutor(max_workers=3)`` — parallelization only, never
        a weaker liveness check in place of the real staged transcription.
        ``RuntimeValidator.run()`` is stateless per call (a fresh
        ``subprocess.Popen`` plus local variables only, no shared mutable
        state), so a single instance is constructed once and shared across
        workers rather than one per worker. Every field of the ``evidence()``
        closure and the exact per-probe 30s bound are unchanged.
        """
        validator = RuntimeValidator()
        results: dict[str, Mapping[str, Any]] = {}

        def evidence(smoke, *, healthy: bool | None = None, reason: str | None = None) -> dict[str, Any]:
            return {
                "healthy": smoke.ok if healthy is None else healthy,
                "reason": reason or smoke.reason,
                "exit_code": smoke.exit_code,
                "argv": list(smoke.argv),
                "stdout": smoke.stdout,
                "stderr": smoke.stderr,
                "duration_ms": smoke.duration_ms,
                "timed_out": smoke.timed_out,
            }

        def _probe_version(path: Path):
            return validator.run(str(path), ["-version"])

        def _probe_whisper():
            try:
                staging = WhisperPathStaging(
                    paths["models/ggml-base.en.bin"],
                    paths["smoke/runtime-smoke.wav"],
                    paths["smoke/runtime-smoke.wav"].parent / "admission-output" / "transcript",
                )
                staged_model, staged_wav, _ = staging.prepare()
                try:
                    return validator.run(
                        str(paths["bin/whisper-cli.exe"]),
                        ["-m", staged_model, "-f", staged_wav, "-t", "1", "-nt"],
                    )
                finally:
                    staging.cleanup()
            except Exception as error:
                # ``assess`` will reject this complete failed evidence; do not turn a
                # readable model or WAV into a health claim when staging cannot run.
                from lecturepack.infrastructure.runtime_validation import SmokeEvidence

                return SmokeEvidence([], None, "", str(error), 0, "admission preparation failed", False)

        version_probe_names = [name for name in ("bin/ffmpeg.exe", "bin/ffprobe.exe") if name in paths]

        with ThreadPoolExecutor(max_workers=3) as pool:
            version_futures = {
                pool.submit(_probe_version, paths[name]): name for name in version_probe_names
            }
            whisper_future = pool.submit(_probe_whisper)

            # ``future.result()`` re-raises any exception the worker raised,
            # rather than letting it vanish into an unexamined future.
            for future, name in version_futures.items():
                results[name] = evidence(future.result())

            whisper_smoke = whisper_future.result()

        for name in paths:
            if name not in results:
                results[name] = evidence(whisper_smoke)
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
