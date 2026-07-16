"""
lecturepack.infrastructure.ollama_client
========================================

Minimal, fault-isolated client for a local Ollama server (v1.1, Phase 5).

Design rules (Phase 4):
  * Pure standard library (urllib) -- no Qt, no third-party deps, importable
    in the frozen bundle and in unit tests without a server.
  * Every request has finite connect and read timeouts.
  * Generation uses the streaming NDJSON endpoint so a ``cancel_event`` can
    abort mid-generation instead of blocking until the model finishes.
  * All failures raise typed exceptions; callers (the AI repair worker)
    translate them into recoverable UI states. Nothing here ever terminates
    the application.

API facts (verified against Ollama v0.32 docs, July 2026):
  * ``format`` accepts a full JSON-schema object; the constrained output is in
    ``message.content`` (a JSON *string* to parse).
  * ``think: false`` disables thinking on qwen3-family models and works with
    ``format`` on servers >= 0.30.11.
  * ``keep_alive: 0`` unloads the model after the response.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

DEFAULT_BASE_URL = "http://localhost:11434"
CONNECT_TIMEOUT = 4.0          # seconds -- availability probes
GENERATION_TIMEOUT = 180.0     # seconds -- hard cap for one chat request
STREAM_STALL_TIMEOUT = 60.0    # seconds without any streamed byte -> timeout


class OllamaError(Exception):
    """Base class; ``kind`` is a stable machine-readable failure category."""
    kind = "error"


class OllamaUnavailable(OllamaError):
    """Server not reachable (connection refused, DNS, service stopped)."""
    kind = "unavailable"


class OllamaTimeout(OllamaError):
    """Connect/read/total-generation timeout."""
    kind = "timeout"


class OllamaBadResponse(OllamaError):
    """HTTP error status or malformed/unparseable server payload."""
    kind = "bad_response"


class OllamaCancelled(OllamaError):
    """The caller's cancel_event was set mid-request."""
    kind = "cancelled"


class OllamaClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 connect_timeout: float = CONNECT_TIMEOUT,
                 generation_timeout: float = GENERATION_TIMEOUT):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.connect_timeout = connect_timeout
        self.generation_timeout = generation_timeout

    # ------------------------------------------------------------------ #
    # Plumbing
    # ------------------------------------------------------------------ #
    def _request(self, path: str, payload: Optional[dict] = None,
                 timeout: Optional[float] = None):
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data, method="POST" if data is not None else "GET",
            headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=timeout or self.connect_timeout)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")[:500]
            except Exception:
                pass
            raise OllamaBadResponse(f"HTTP {e.code} from {path}: {body}") from e
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise OllamaTimeout(f"timeout connecting to {url}") from e
            raise OllamaUnavailable(f"cannot reach Ollama at {self.base_url}: {reason}") from e
        except TimeoutError as e:
            raise OllamaTimeout(f"timeout connecting to {url}") from e

    def _json(self, path: str, payload: Optional[dict] = None,
              timeout: Optional[float] = None) -> dict:
        with self._request(path, payload, timeout) as resp:
            raw = resp.read()
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise OllamaBadResponse(f"malformed JSON from {path}") from e

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def version(self) -> str:
        return str(self._json("/api/version").get("version", "unknown"))

    def is_available(self) -> Dict[str, Any]:
        """Never raises. Returns {available, version?, error?}."""
        try:
            return {"available": True, "version": self.version()}
        except OllamaError as e:
            return {"available": False, "error": str(e), "kind": e.kind}
        except Exception as e:  # absolute boundary
            return {"available": False, "error": str(e), "kind": "error"}

    def list_models(self) -> List[Dict[str, Any]]:
        """Installed models from /api/tags, normalized for the model picker."""
        data = self._json("/api/tags")
        out = []
        for m in data.get("models", []) or []:
            details = m.get("details", {}) or {}
            out.append({
                "name": m.get("name", ""),
                "size_bytes": int(m.get("size", 0) or 0),
                "parameter_size": details.get("parameter_size", ""),
                "quantization_level": details.get("quantization_level", ""),
                "family": details.get("family", ""),
                "modified_at": m.get("modified_at", ""),
            })
        out.sort(key=lambda m: m["name"])
        return out

    def show_model(self, name: str) -> Dict[str, Any]:
        data = self._json("/api/show", {"model": name})
        return {
            "capabilities": data.get("capabilities", []) or [],
            "details": data.get("details", {}) or {},
        }

    def unload(self, model: str) -> None:
        """Best-effort immediate unload (keep_alive: 0). Never raises."""
        try:
            self._json("/api/chat", {"model": model, "messages": [], "keep_alive": 0},
                       timeout=15.0)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Structured chat
    # ------------------------------------------------------------------ #
    def chat_structured(self, model: str, system: str, user: str,
                        schema: dict,
                        temperature: float = 0.0,
                        num_ctx: int = 8192,
                        num_predict: int = 1500,
                        keep_alive: Any = "10m",
                        think: Any = False,
                        cancel_event: Optional[threading.Event] = None,
                        on_progress: Optional[Callable[[int], None]] = None,
                        timeout: Optional[float] = None) -> Dict[str, Any]:
        """One schema-constrained chat call, streamed so it can be cancelled.

        Returns {content, eval_count, eval_duration_s, load_duration_s,
        total_s}. Raises OllamaCancelled / OllamaTimeout / OllamaUnavailable /
        OllamaBadResponse.
        """
        payload = {
            "model": model,
            "stream": True,
            "format": schema,
            "think": think,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        deadline = time.monotonic() + (timeout or self.generation_timeout)
        if cancel_event is not None and cancel_event.is_set():
            raise OllamaCancelled("cancelled before request")

        resp = self._request("/api/chat", payload, timeout=STREAM_STALL_TIMEOUT)
        content_parts: List[str] = []
        stats: Dict[str, Any] = {}
        tokens_seen = 0
        try:
            for line in resp:
                if cancel_event is not None and cancel_event.is_set():
                    raise OllamaCancelled("cancelled during generation")
                if time.monotonic() > deadline:
                    raise OllamaTimeout(
                        f"generation exceeded {timeout or self.generation_timeout:.0f}s")
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as e:
                    raise OllamaBadResponse("malformed stream chunk from /api/chat") from e
                if chunk.get("error"):
                    raise OllamaBadResponse(f"server error: {chunk['error']}")
                msg = chunk.get("message", {}) or {}
                piece = msg.get("content", "")
                if piece:
                    content_parts.append(piece)
                    tokens_seen += 1
                    if on_progress is not None:
                        try:
                            on_progress(tokens_seen)
                        except Exception:
                            pass
                if chunk.get("done"):
                    stats = chunk
                    break
        except OSError as e:  # socket-level failure mid-stream (model unloaded, crash)
            if isinstance(e, OllamaError):
                raise
            if "timed out" in str(e).lower():
                raise OllamaTimeout("stream stalled (no data from Ollama)") from e
            raise OllamaUnavailable(f"connection lost mid-generation: {e}") from e
        finally:
            try:
                resp.close()
            except Exception:
                pass

        content = "".join(content_parts)
        if not stats.get("done"):
            raise OllamaBadResponse("stream ended without a done chunk")
        return {
            "content": content,
            "eval_count": int(stats.get("eval_count", 0) or 0),
            "eval_duration_s": (stats.get("eval_duration", 0) or 0) / 1e9,
            "load_duration_s": (stats.get("load_duration", 0) or 0) / 1e9,
            "total_s": (stats.get("total_duration", 0) or 0) / 1e9,
            "done_reason": stats.get("done_reason", ""),
        }


# ---------------------------------------------------------------------- #
# Context Repair integration
# ---------------------------------------------------------------------- #

# Version this string whenever the repair prompt or schema changes -- it is
# part of the response cache key.
REPAIR_PROMPT_VERSION = "v1.1.0-a"

REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "integer"},
                    "corrected_text": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["segment_id", "corrected_text", "reason", "confidence"],
            },
        }
    },
    "required": ["corrections"],
}


class OllamaRepairProvider:
    """Adapter exposing the ContextRepairEngine ``complete(system, user)``
    interface over a schema-constrained Ollama chat call.

    All validation guardrails still run in ``ContextRepairEngine
    .parse_and_validate`` -- this class only transports text. A response cache
    (keyed by model + prompt version + exact prompt content) makes repeated
    requests instant and offline-replayable.
    """

    def __init__(self, client: OllamaClient, model: str,
                 cancel_event: Optional[threading.Event] = None,
                 cache: Optional[dict] = None,
                 keep_alive: Any = "10m",
                 num_predict: int = 1500,
                 on_chunk_stats: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.client = client
        self.model = model
        self.cancel_event = cancel_event
        self.cache = cache if cache is not None else {}
        self.keep_alive = keep_alive
        self.num_predict = num_predict
        self.on_chunk_stats = on_chunk_stats
        self.cache_hits = 0
        self.requests_made = 0

    def cache_key(self, system: str, user: str) -> str:
        import hashlib
        payload = json.dumps(
            [REPAIR_PROMPT_VERSION, self.model, system, user], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def complete(self, system: str, user: str) -> str:
        key = self.cache_key(system, user)
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]
        result = self.client.chat_structured(
            self.model, system, user, REPAIR_SCHEMA,
            temperature=0.0, num_predict=self.num_predict,
            keep_alive=self.keep_alive, think=False,
            cancel_event=self.cancel_event)
        self.requests_made += 1
        if self.on_chunk_stats is not None:
            try:
                self.on_chunk_stats(result)
            except Exception:
                pass
        content = result["content"]
        # Only cache parseable JSON so a transient bad generation is retried.
        try:
            json.loads(content)
            self.cache[key] = content
        except ValueError:
            pass
        return content
