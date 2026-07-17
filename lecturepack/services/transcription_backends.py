"""Provider-neutral transcription contracts and the private local adapter.

This module deliberately enables *only* the existing whisper.cpp path.  It
defines the stable boundary future opt-in providers must implement without
placing provider logic, secrets, HTTP, chunking, or retries in JobController.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from threading import Event
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal, QThread

from lecturepack.constants import (
    TRANSCRIPTION_BACKEND_LOCAL, TRANSCRIPTION_BACKEND_GROQ_FAST,
    TRANSCRIPTION_BACKEND_GROQ_ACCURATE,
)
from lecturepack.infrastructure.transcription_engines import (
    ENGINE_AUTO, EngineRegistry,
)


BACKEND_LOCAL_WHISPERCPP = TRANSCRIPTION_BACKEND_LOCAL
BACKEND_GROQ_FAST = TRANSCRIPTION_BACKEND_GROQ_FAST
BACKEND_GROQ_ACCURATE = TRANSCRIPTION_BACKEND_GROQ_ACCURATE


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
    provider_options: Dict[str, Any] = field(default_factory=dict)
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


class _GroqWorker(QThread):
    progress = Signal(str)
    result_ready = Signal(object)

    def __init__(self, request, backend_key, model, config_manager,
                 secret_store, client_factory, encoder_factory):
        super().__init__()
        self.request = request
        self.backend_key = backend_key
        self.model = model
        self.config_manager = config_manager
        self.secret_store = secret_store
        self.client_factory = client_factory
        self.encoder_factory = encoder_factory
        self.encoder = None
        self.clients = []

    def cancel(self):
        self.request.cancel_token.cancel()
        if self.encoder is not None:
            self.encoder.cancel()
        for client in list(self.clients):
            cancel = getattr(client, "cancel", None)
            if cancel:
                cancel()

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from lecturepack.infrastructure.file_manager import FileManager
        from lecturepack.services.groq_transcription import (
            DEFAULT_MAX_UPLOAD_BYTES, AudioChunk, FfmpegFlacEncoder, GroqError,
            GroqHttpClient, cache_fingerprint, merge_verbose_chunks,
            plan_audio_chunks, write_canonical_outputs,
        )
        request = self.request
        options = request.provider_options or {}
        started = __import__("time").monotonic()
        try:
            if not options.get("privacy_accepted", False):
                raise GroqError("Online audio upload requires privacy acknowledgement.",
                                kind="privacy_required", retryable=False)
            api_key = self.secret_store.get()
            if not api_key:
                raise GroqError("No Groq API key is stored in Windows Credential Manager.",
                                kind="missing_secret", retryable=False)
            duration = float(request.source_duration_seconds or 0.0)
            if duration <= 0:
                import wave
                with wave.open(request.audio_path, "rb") as wav:
                    duration = wav.getnframes() / float(wav.getframerate())
            max_bytes = int(options.get("max_upload_bytes") or
                            (self.config_manager.get("groq_max_upload_bytes",
                                                     DEFAULT_MAX_UPLOAD_BYTES)
                             if self.config_manager else DEFAULT_MAX_UPLOAD_BYTES))
            concurrency = max(1, min(4, int(options.get("concurrency") or
                                             (self.config_manager.get("groq_concurrency", 2)
                                              if self.config_manager else 2))))
            chunks = plan_audio_chunks(duration, max_bytes)
            fingerprint = cache_fingerprint(
                request.audio_path, self.model, request.language, request.prompt,
                duration, max_bytes)
            root = os.path.join(os.path.dirname(request.output_prefix),
                                "groq-cache", fingerprint)
            audio_dir = os.path.join(root, "audio")
            response_dir = os.path.join(root, "responses")
            os.makedirs(audio_dir, exist_ok=True)
            os.makedirs(response_dir, exist_ok=True)
            ffmpeg = options.get("ffmpeg_path") or (
                self.config_manager.get("ffmpeg_exe", "") if self.config_manager else "")
            self.encoder = (self.encoder_factory(ffmpeg) if self.encoder_factory
                            else FfmpegFlacEncoder(ffmpeg))
            encoded: list[tuple[AudioChunk, str, str]] = []
            resumed = 0
            for chunk in chunks:
                if request.cancel_token.is_cancelled():
                    raise GroqError("Online transcription cancelled.", kind="cancelled",
                                    retryable=False)
                audio_path = os.path.join(audio_dir, f"chunk-{chunk.index:04d}.flac")
                response_path = os.path.join(
                    response_dir, f"chunk-{chunk.index:04d}.json")
                if not os.path.exists(response_path):
                    if not os.path.exists(audio_path):
                        self.progress.emit(
                            f"Preparing online audio chunk {chunk.index + 1}/{len(chunks)}...\n")
                        self.encoder.encode(request.audio_path, chunk, audio_path,
                                            request.cancel_token.is_cancelled)
                    if os.path.getsize(audio_path) >= max_bytes:
                        raise GroqError(
                            "Prepared audio chunk exceeds the configured upload limit.",
                            kind="chunk_too_large", status=413, retryable=False)
                else:
                    resumed += 1
                encoded.append((chunk, audio_path, response_path))

            client = self.client_factory() if self.client_factory else GroqHttpClient()
            self.clients.append(client)

            def upload(item):
                chunk, audio_path, response_path = item
                if os.path.exists(response_path):
                    return chunk, FileManager.read_json_safe(response_path, {})
                payload = client.transcribe(
                    audio_path, api_key=api_key, model=self.model,
                    language=request.language, prompt="",
                    cancelled=request.cancel_token.is_cancelled)
                FileManager.write_json_atomic(response_path, payload)
                return chunk, payload

            results = []
            with ThreadPoolExecutor(max_workers=concurrency,
                                    thread_name_prefix="LecturePackGroq") as pool:
                futures = {pool.submit(upload, item): item[0] for item in encoded}
                completed = 0
                for future in as_completed(futures):
                    if request.cancel_token.is_cancelled():
                        for pending in futures:
                            pending.cancel()
                        raise GroqError("Online transcription cancelled.", kind="cancelled",
                                        retryable=False)
                    results.append(future.result())
                    completed += 1
                    self.progress.emit(
                        f"Online transcription chunk {completed}/{len(chunks)} complete.\n")
            # Drop the only explicit secret reference before merge/persistence.
            api_key = ""
            merged = merge_verbose_chunks(results)
            paths = write_canonical_outputs(merged, request.output_prefix)
            self.result_ready.emit(TranscriptionResult(
                success=True, backend_key=self.backend_key, provider="Groq",
                actual_backend=f"Groq {self.model}", raw_json_path=paths[0],
                raw_srt_path=paths[1], raw_txt_path=paths[2],
                metrics={"chunks": len(chunks), "resumed_chunks": resumed,
                         "elapsed_seconds": round(__import__("time").monotonic() - started, 3)}))
        except Exception as exc:
            api_key = ""
            if isinstance(exc, GroqError):
                kind, message, retryable = exc.kind, str(exc), exc.retryable
            else:
                kind, message, retryable = "online_internal", str(exc), False
            self.result_ready.emit(TranscriptionResult(
                success=False, backend_key=self.backend_key, provider="Groq",
                actual_backend=f"Groq {self.model}", error_code=kind,
                error_message=_safe_error(message, request), retryable=retryable,
                fallback_allowed=kind not in ("cancelled", "privacy_required")))


class GroqTranscriptionBackend(TranscriptionBackend):
    """Opt-in Groq adapter; all work occurs outside the GUI thread."""

    def __init__(self, key, model, config_manager, secret_store=None,
                 client_factory=None, encoder_factory=None, parent=None):
        super().__init__(parent)
        from lecturepack.infrastructure.secret_store import WindowsCredentialStore
        self.key = key
        self.model = model
        self.config_manager = config_manager
        self.secret_store = secret_store or WindowsCredentialStore()
        self.client_factory = client_factory
        self.encoder_factory = encoder_factory
        self.worker = None

    def capabilities(self) -> BackendCapabilities:
        from lecturepack.services.groq_transcription import DEFAULT_MAX_UPLOAD_BYTES
        return BackendCapabilities(
            key=self.key,
            label="Online Fast (Groq)" if self.key == BACKEND_GROQ_FAST
            else "Online Accurate (Groq)",
            provider="Groq", is_local=False, requires_secret=True,
            uploads_audio=True, supports_segment_timestamps=True,
            supports_word_timestamps=True, supports_prompt=False,
            supports_vad=False, supports_resume=True,
            accepted_audio_formats=("flac",),
            max_upload_bytes=DEFAULT_MAX_UPLOAD_BYTES)

    def start(self, request: TranscriptionRequest) -> None:
        if self.worker is not None and self.worker.isRunning():
            raise RuntimeError("Groq transcription is already running.")
        self.worker = _GroqWorker(
            request, self.key, self.model, self.config_manager,
            self.secret_store, self.client_factory, self.encoder_factory)
        self.worker.progress.connect(self.progress.emit)
        self.worker.result_ready.connect(self._finished)
        self.worker.start()

    def _finished(self, result):
        if result.success:
            self.backend_detected.emit(result.actual_backend)
        self.finished.emit(result)

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            # Keep QObject/QThread lifetime safe on application close without
            # turning cancellation into a long blocking wait.
            self.worker.wait(750)


class BackendRegistry:
    """Holds provider adapters; unknown selections fail closed to local."""

    def __init__(self, config_manager, local_wrapper,
                 local_engine_registry: Optional[EngineRegistry] = None,
                 secret_store=None):
        from lecturepack.services.groq_transcription import (
            GROQ_ACCURATE_MODEL, GROQ_FAST_MODEL,
        )
        self.config_manager = config_manager
        local_engines = local_engine_registry or EngineRegistry(config_manager)
        local = LocalWhisperCppBackend(local_wrapper, local_engines)
        self._backends: Dict[str, TranscriptionBackend] = {
            BACKEND_LOCAL_WHISPERCPP: local,
            BACKEND_GROQ_FAST: GroqTranscriptionBackend(
                BACKEND_GROQ_FAST, GROQ_FAST_MODEL, config_manager, secret_store),
            BACKEND_GROQ_ACCURATE: GroqTranscriptionBackend(
                BACKEND_GROQ_ACCURATE, GROQ_ACCURATE_MODEL, config_manager, secret_store),
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
