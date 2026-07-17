"""Groq speech-to-text transport, lossless chunking, resume, and merge.

This module contains no UI and never persists credentials.  It can be tested
against a localhost mock server without spending provider credits.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import random
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.infrastructure.process_tree import terminate_owned_subprocess_tree


GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_FAST_MODEL = "whisper-large-v3-turbo"
GROQ_ACCURATE_MODEL = "whisper-large-v3"
# Safely below the documented 25 MB free-tier upload limit, including multipart.
DEFAULT_MAX_UPLOAD_BYTES = 23 * 1024 * 1024
DEFAULT_OVERLAP_SECONDS = 5.0
DEFAULT_MAX_CHUNK_SECONDS = 600.0


class GroqError(RuntimeError):
    def __init__(self, message: str, *, kind: str = "network", status: int = 0,
                 retryable: bool = True, retry_after: float = 0.0):
        super().__init__(message)
        self.kind = kind
        self.status = int(status or 0)
        self.retryable = bool(retryable)
        self.retry_after = max(0.0, float(retry_after or 0.0))


@dataclass(frozen=True)
class AudioChunk:
    index: int
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def plan_audio_chunks(duration_seconds: float, max_upload_bytes: int,
                      overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
                      max_chunk_seconds: float = DEFAULT_MAX_CHUNK_SECONDS
                      ) -> list[AudioChunk]:
    """Size-aware plan assuming worst-case 16 kHz mono signed-16-bit audio."""
    duration = max(0.01, float(duration_seconds))
    budget = max(320_000, int(max_upload_bytes * 0.85))
    by_size = budget / 32_000.0
    chunk_seconds = max(10.0, min(float(max_chunk_seconds), by_size))
    overlap = max(0.0, min(float(overlap_seconds), chunk_seconds / 4.0))
    chunks: list[AudioChunk] = []
    start = 0.0
    while start < duration:
        end = min(duration, start + chunk_seconds)
        chunks.append(AudioChunk(len(chunks), round(start, 3), round(end, 3)))
        if end >= duration:
            break
        start = end - overlap
    return chunks


def parse_retry_after(value: str | None, now: float | None = None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(value)
            return max(0.0, dt.timestamp() - (time.time() if now is None else now))
        except (TypeError, ValueError, OverflowError):
            return 0.0


def _safe_provider_message(raw: str, secret: str = "") -> str:
    text = re.sub(r"[\r\n]+", " ", str(raw or "Provider request failed."))
    if secret:
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+\-/=]+", "Bearer [redacted]", text)
    return text[:700]


class GroqHttpClient:
    def __init__(self, endpoint: str = GROQ_TRANSCRIPTIONS_URL,
                 timeout_seconds: float = 45.0, max_retries: int = 3,
                 sleep: Callable[[float], None] = time.sleep):
        self.endpoint = endpoint
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = max(0, int(max_retries))
        self.sleep = sleep
        self._active = set()
        self._active_lock = threading.Lock()

    def cancel(self) -> None:
        with self._active_lock:
            active = list(self._active)
        for response in active:
            try:
                response.close()
            except Exception:
                pass

    def _read_response(self, request):
        response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
        with self._active_lock:
            self._active.add(response)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            with self._active_lock:
                self._active.discard(response)
            response.close()

    def test_key(self, api_key: str) -> bool:
        endpoint = self.endpoint.split("/audio/transcriptions", 1)[0] + "/models"
        request = urllib.request.Request(
            endpoint, headers={"Authorization": f"Bearer {api_key}",
                               "User-Agent": "LecturePack/1.2"})
        try:
            with urllib.request.urlopen(request, timeout=min(15.0, self.timeout_seconds)) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return isinstance(payload.get("data"), list)
        except urllib.error.HTTPError as exc:
            raw = exc.read(2048).decode("utf-8", errors="replace")
            raise GroqError(_safe_provider_message(raw, api_key), kind="auth",
                            status=exc.code, retryable=False) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GroqError(_safe_provider_message(str(exc), api_key),
                            kind="network", retryable=True) from None

    def transcribe(self, audio_path: str, *, api_key: str, model: str,
                   language: str = "en", prompt: str = "",
                   cancelled: Callable[[], bool] = lambda: False) -> dict:
        boundary = "----LecturePack" + uuid.uuid4().hex
        fields = [("model", model), ("response_format", "verbose_json"),
                  ("timestamp_granularities[]", "segment")]
        if language:
            fields.append(("language", language))
        if prompt:
            fields.append(("prompt", prompt[:1600]))
        body = bytearray()
        for name, value in fields:
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))
        filename = os.path.basename(audio_path)
        mime = mimetypes.guess_type(filename)[0] or "audio/flac"
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8"))
        with open(audio_path, "rb") as fh:
            body.extend(fh.read())
        body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))

        for attempt in range(self.max_retries + 1):
            if cancelled():
                raise GroqError("Online transcription cancelled.", kind="cancelled",
                                retryable=False)
            request = urllib.request.Request(
                self.endpoint, data=bytes(body), method="POST",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": f"multipart/form-data; boundary={boundary}",
                         "User-Agent": "LecturePack/1.2"})
            try:
                return self._read_response(request)
            except urllib.error.HTTPError as exc:
                raw = exc.read(4096).decode("utf-8", errors="replace")
                retryable = exc.code in (408, 409, 429, 498) or exc.code >= 500
                kind = "rate_limit" if exc.code == 429 else (
                    "quota" if exc.code in (402, 403) else "http")
                delay = parse_retry_after(exc.headers.get("retry-after"))
                err = GroqError(_safe_provider_message(raw, api_key), kind=kind,
                                status=exc.code, retryable=retryable,
                                retry_after=delay)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                err = GroqError(_safe_provider_message(str(exc), api_key),
                                kind="network", retryable=True)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                err = GroqError(_safe_provider_message(str(exc), api_key),
                                kind="invalid_response", retryable=False)
            if not err.retryable or attempt >= self.max_retries:
                raise err
            delay = err.retry_after or min(8.0, (2 ** attempt) + random.random() * 0.25)
            # Keep Retry-After/backoff responsive to application close.
            remaining = delay
            while remaining > 0:
                if cancelled():
                    raise GroqError("Online transcription cancelled.", kind="cancelled",
                                    retryable=False)
                step = min(0.1, remaining)
                self.sleep(step)
                remaining -= step
        raise GroqError("Provider request failed.")  # pragma: no cover


class FfmpegFlacEncoder:
    def __init__(self, ffmpeg_path: str):
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self._process: subprocess.Popen | None = None

    def encode(self, source: str, chunk: AudioChunk, destination: str,
               cancelled: Callable[[], bool]) -> str:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        args = [self.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{chunk.start_seconds:.3f}", "-t", f"{chunk.duration_seconds:.3f}",
                "-i", source, "-map", "0:a:0", "-ar", "16000", "-ac", "1",
                "-c:a", "flac", destination]
        kwargs: dict[str, Any] = {"stdout": subprocess.DEVNULL,
                                  "stderr": subprocess.PIPE}
        if os.name == "nt":
            kwargs["creationflags"] = (getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                                       getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        else:
            kwargs["start_new_session"] = True
        self._process = subprocess.Popen(args, **kwargs)
        while self._process.poll() is None:
            if cancelled():
                terminate_owned_subprocess_tree(self._process)
                raise GroqError("Online transcription cancelled.", kind="cancelled",
                                retryable=False)
            time.sleep(0.05)
        stderr = (self._process.stderr.read() if self._process.stderr else b"")
        code = self._process.returncode
        self._process = None
        if code:
            raise GroqError(_safe_provider_message(stderr.decode("utf-8", "replace")),
                            kind="audio_encode", retryable=False)
        return destination

    def cancel(self) -> None:
        if self._process is not None and self._process.poll() is None:
            terminate_owned_subprocess_tree(self._process)


def _overlap_words(left: str, right: str, limit: int = 24) -> int:
    a, b = left.split(), right.split()
    for size in range(min(limit, len(a), len(b)), 0, -1):
        if [x.casefold().strip(".,;:!?") for x in a[-size:]] == [
                x.casefold().strip(".,;:!?") for x in b[:size]]:
            return size
    return 0


def merge_verbose_chunks(items: Iterable[tuple[AudioChunk, dict]]) -> dict:
    """Offset timestamps, sort chronologically, and remove overlap duplicates."""
    merged: list[dict] = []
    full_text = ""
    language = ""
    for chunk, payload in sorted(items, key=lambda item: item[0].index):
        language = language or str(payload.get("language", ""))
        for segment in payload.get("segments", []) or []:
            start = chunk.start_seconds + float(segment.get("start", 0.0) or 0.0)
            end = chunk.start_seconds + float(segment.get("end", start) or start)
            text = str(segment.get("text", "")).strip()
            if merged and end <= merged[-1]["end"] + 0.05:
                continue
            duplicate = _overlap_words(full_text, text)
            if duplicate:
                text = " ".join(text.split()[duplicate:]).strip()
            if not text:
                continue
            item = dict(segment)
            item.update({"id": len(merged), "start": start, "end": max(start, end),
                         "text": text})
            merged.append(item)
            full_text = (full_text + " " + text).strip()
    merged.sort(key=lambda seg: (seg["start"], seg["end"], seg["id"]))
    for idx, segment in enumerate(merged):
        segment["id"] = idx
    return {"language": language or "en", "text": full_text, "segments": merged}


def _srt_timestamp(seconds: float) -> str:
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_canonical_outputs(merged: dict, output_prefix: str) -> tuple[str, str, str]:
    transcription = []
    srt_blocks = []
    for idx, seg in enumerate(merged.get("segments", [])):
        start, end = float(seg["start"]), float(seg["end"])
        transcription.append({"text": seg["text"],
                              "offsets": {"from": round(start * 1000),
                                          "to": round(end * 1000)}})
        srt_blocks.append(f"{idx + 1}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{seg['text']}\n")
    raw = {"systeminfo": "Groq API", "model": "Groq Whisper",
           "result": {"language": merged.get("language", "en"),
                      "transcription": transcription}}
    json_path, srt_path, txt_path = (output_prefix + ext for ext in (".json", ".srt", ".txt"))
    FileManager.write_json_atomic(json_path, raw)
    _write_text_atomic(srt_path, "\n".join(srt_blocks))
    _write_text_atomic(txt_path, merged.get("text", "") + "\n")
    return json_path, srt_path, txt_path


def _write_text_atomic(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp-" + uuid.uuid4().hex
    with open(temp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)


def cache_fingerprint(audio_path: str, model: str, language: str, prompt: str,
                      duration: float, max_bytes: int) -> str:
    stat = os.stat(audio_path)
    payload = [os.path.abspath(audio_path), stat.st_size, stat.st_mtime_ns, model,
               language, prompt, round(duration, 3), int(max_bytes)]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()
