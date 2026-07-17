"""Provider-neutral transcription contracts and the private local adapter.

This module deliberately enables *only* the existing whisper.cpp path.  It
defines the stable boundary future opt-in providers must implement without
placing provider logic, secrets, HTTP, chunking, or retries in JobController.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import Event
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from lecturepack.constants import TRANSCRIPTION_BACKEND_LOCAL
from lecturepack.infrastructure.transcription_engines import (
    ENGINE_AUTO, EngineRegistry,
)


BACKEND_LOCAL_WHISPERCPP = TRANSCRIPTION_BACKEND_LOCAL


@dataclass(frozen=True)
class BackendCapabilities:
    key: str
    label: str
    provider: str
    is_local: bool
    requires_secret: bool
    uploads_audio: bool
    supports_segment_timestamps: bool
    supports_word_timestamps: bool
    supports_prompt: bool
    supports_vad: bool
    supports_resume: bool
    accepted_audio_formats: tuple[str, ...] = ("wav",)
    max_upload_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        # JSON has arrays rather than tuples; make the contract explicit.
        payload["accepted_audio_formats"] = list(self.accepted_audio_formats)
        return payload


class CancellationToken:
    """Thread-safe cooperative cancellation shared by all backend types."""

    def __init__(self):
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class TranscriptionRequest:
    audio_path: str
    output_prefix: str
    model: str
    language: str = "en"
    prompt: str = ""
    threads: int = 8
    vad: Dict[str, Any] = field(default_factory=dict)
    local_engine: str = ENGINE_AUTO
    job_id: str = ""
    source_duration_seconds: float = 0.0
    cancel_token: CancellationToken = field(default_factory=CancellationToken,
                                             compare=False, repr=False)


@dataclass(frozen=True)
class TranscriptionResult:
    success: bool
    backend_key: str
    provider: str
    actual_backend: str = ""
    engine_key: str = ""
    raw_json_path: str = ""
    raw_srt_path: str = ""
    raw_txt_path: str = ""
    error_code: str = ""
    error_message: str = ""
    retryable: bool = False
    fallback_allowed: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)


class TranscriptionBackend(QObject):
    """Qt-safe async backend interface used by JobController."""

    progress = Signal(str)
    backend_detected = Signal(str)
    finished = Signal(object)  # TranscriptionResult

    def capabilities(self) -> BackendCapabilities:  # pragma: no cover - interface
        raise NotImplementedError

    def start(self, request: TranscriptionRequest) -> None:  # pragma: no cover
        raise NotImplementedError

    def cancel(self) -> None:  # pragma: no cover
        raise NotImplementedError


def _safe_error(message: str, request: Optional[TranscriptionRequest]) -> str:
    """Keep persisted/provider-facing failures useful without leaking paths."""
    text = str(message or "Transcription failed.").replace("\r", " ").replace("\n", " ")
    if request is not None:
        for value in (request.audio_path, request.output_prefix, request.model):
            if value:
                text = text.replace(str(value), "[local path]")
    return text[:1000]


class LocalWhisperCppBackend(TranscriptionBackend):
    """Adapter preserving the verified WhisperWrapper/QProcess behavior."""

    def __init__(self, wrapper, engine_registry: EngineRegistry, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.engine_registry = engine_registry
        self._request: Optional[TranscriptionRequest] = None
        self._engine = None
        self._actual_backend = ""
        wrapper.progress.connect(self.progress.emit)
        wrapper.backend_detected.connect(self._on_backend_detected)
        wrapper.finished.connect(self._on_finished)

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            key=BACKEND_LOCAL_WHISPERCPP,
            label="Private Local",
            provider="whisper.cpp",
            is_local=True,
            requires_secret=False,
            uploads_audio=False,
            supports_segment_timestamps=True,
            supports_word_timestamps=True,
            supports_prompt=True,
            supports_vad=True,
            supports_resume=False,
            accepted_audio_formats=("wav",),
        )

    def start(self, request: TranscriptionRequest) -> None:
        self._request = request
        self._actual_backend = ""
        self._engine = self.engine_registry.resolve(request.local_engine)
        engine_exe = self._engine.exe_path or getattr(
            self.wrapper, "whisper_exe_path", "")
        self.wrapper.start_transcription(
            request.audio_path, request.model, request.output_prefix,
            glossary=request.prompt, threads=request.threads,
            vad_settings=request.vad, engine_exe=engine_exe,
            extra_args=list(self._engine.extra_args))

    def cancel(self) -> None:
        if self._request is not None:
            self._request.cancel_token.cancel()
        self.wrapper.cancel()

    def _on_backend_detected(self, backend: str) -> None:
        self._actual_backend = str(backend)
        self.backend_detected.emit(self._actual_backend)

    def _on_finished(self, success: bool, error_message: str) -> None:
        request = self._request
        engine = self._engine
        if request is None:
            return
        result = TranscriptionResult(
            success=bool(success),
            backend_key=BACKEND_LOCAL_WHISPERCPP,
            provider="whisper.cpp",
            # Only runtime output proves what loaded. The selected engine's
            # advertised backend is recorded separately as ``engine_key``.
            actual_backend=self._actual_backend,
            engine_key=engine.key if engine is not None else "",
            raw_json_path=request.output_prefix + ".json" if success else "",
            raw_srt_path=request.output_prefix + ".srt" if success else "",
            raw_txt_path=request.output_prefix + ".txt" if success else "",
            error_code="" if success else "local_process_failed",
            error_message="" if success else _safe_error(error_message, request),
            retryable=not success,
            fallback_allowed=False,
        )
        self.finished.emit(result)


class BackendRegistry:
    """Holds provider adapters; unknown selections fail closed to local."""

    def __init__(self, config_manager, local_wrapper,
                 local_engine_registry: Optional[EngineRegistry] = None):
        self.config_manager = config_manager
        local_engines = local_engine_registry or EngineRegistry(config_manager)
        local = LocalWhisperCppBackend(local_wrapper, local_engines)
        self._backends: Dict[str, TranscriptionBackend] = {
            BACKEND_LOCAL_WHISPERCPP: local,
        }

    def register(self, backend: TranscriptionBackend) -> None:
        caps = backend.capabilities()
        if not caps.key:
            raise ValueError("backend capability key is required")
        self._backends[caps.key] = backend

    def keys(self) -> list[str]:
        return list(self._backends)

    def capabilities(self) -> list[BackendCapabilities]:
        return [backend.capabilities() for backend in self._backends.values()]

    def resolve(self, requested: str) -> tuple[TranscriptionBackend, str]:
        key = requested or BACKEND_LOCAL_WHISPERCPP
        backend = self._backends.get(key)
        if backend is not None:
            return backend, "explicitly selected"
        return (self._backends[BACKEND_LOCAL_WHISPERCPP],
                f"Backend '{key}' unavailable; using Private Local")

    def any_network_enabled(self) -> bool:
        return any(not caps.is_local for caps in self.capabilities())
