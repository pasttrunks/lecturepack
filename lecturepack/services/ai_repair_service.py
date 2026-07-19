"""
lecturepack.services.ai_repair_service
======================================

Fault-isolated Context Repair worker (v1.1, Phase 4).

The v1.0.1 crash class: the Context Repair dialog generated proposals
synchronously in its constructor on the GUI thread; a configured provider
meant blocking network calls (60 s timeout each) with no exception boundary.

This worker fixes that architecturally:

  * Proposal generation always runs on a QThread, never the GUI thread.
  * Every failure mode (server down, refused, timeout, malformed JSON, model
    unloaded mid-generation, user cancellation, dialog/app closed) is caught
    at the worker boundary and reported as a typed, recoverable signal.
  * Cancellation is cooperative (checked between streamed tokens and between
    chunks) and closing the owner detaches safely.
  * Responses are cached on disk keyed by transcript hash + context + model +
    prompt version, so a repeated request costs no generation.
  * The deterministic (offline) provider is always available as a fallback.
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import QObject, QThread, Signal

from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.infrastructure.ollama_client import (
    OllamaClient, OllamaRepairProvider, OllamaError, REPAIR_PROMPT_VERSION,
)
from lecturepack.services import transcript_service as ts

AI_CACHE_FILENAME = "ai_cache.json"

# A closing panel relinquishes its worker immediately so the GUI never waits
# on a network timeout.  Detached workers remain strongly owned here until
# their QThread really exits, preventing "QThread destroyed while running".
_DETACHED_WORKERS = set()


def load_ai_cache(transcript_dir: str) -> dict:
    """Disk cache of model responses. Entries are keyed by
    sha256(prompt_version + model + system + user) -- the user prompt embeds
    the segment texts and approved context, and the normalized layer embeds
    the raw transcript hash, so the key covers transcript + context + model +
    prompt version as required by Phase 4."""
    path = os.path.join(transcript_dir, AI_CACHE_FILENAME)
    data = FileManager.read_json_safe(path, {})
    if not isinstance(data, dict) or data.get("prompt_version") != REPAIR_PROMPT_VERSION:
        return {"prompt_version": REPAIR_PROMPT_VERSION, "responses": {}}
    if not isinstance(data.get("responses"), dict):
        data["responses"] = {}
    return data


def save_ai_cache(transcript_dir: str, cache: dict) -> None:
    try:
        FileManager.write_json_atomic(
            os.path.join(transcript_dir, AI_CACHE_FILENAME), cache)
    except Exception:
        pass  # cache persistence is best-effort


class AiRepairWorker(QObject):
    """Runs one proposal pass in a QThread. Construct, connect, start().

    Signals (all queued to the GUI thread):
        progress(done, total)      -- chunk progress
        status(str)                -- human-readable status line
        finished_ok(object)        -- {"corrections": [...], "stats": {...},
                                       "provider_kind": "ollama"|"offline"}
        failed(str, str, str)      -- (kind, message, diagnostic_details)
    """
    progress = Signal(int, int)
    status = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str, str, str)

    def __init__(self, transcript_dir: str, approved_names: list,
                 norm_dict: dict,
                 ollama_settings: dict | None = None,
                 course_title: str = "", glossary: str = ""):
        super().__init__()
        self.transcript_dir = transcript_dir
        self.approved_names = list(approved_names or [])
        self.norm_dict = norm_dict
        self.ollama = dict(ollama_settings or {})
        self.course_title = course_title
        self.glossary = glossary
        self.cancel_event = threading.Event()
        self._thread: QThread | None = None

    # ---- lifecycle ------------------------------------------------------ #
    def start(self):
        """Spawn the worker thread and run. Safe to call once."""
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)
        self._thread.start()
        return self._thread

    def cancel(self):
        """Cooperative cancel; also called when the owning view closes."""
        self.cancel_event.set()

    def detach_and_stop(self):
        """Owner is going away: cancel and let the thread wind down on its
        own. The worker holds no UI references, so closing is non-blocking."""
        self.cancel()
        thread = self._thread
        if thread is None or thread.isFinished():
            return
        _DETACHED_WORKERS.add(self)

        def release():
            _DETACHED_WORKERS.discard(self)

        thread.finished.connect(release)
        thread.requestInterruption()
        thread.quit()

    # ---- worker body ----------------------------------------------------- #
    def _run(self):
        try:
            self._run_inner()
        except Exception as e:  # absolute boundary: never let anything escape
            import traceback
            self.failed.emit("internal", str(e), traceback.format_exc())
        finally:
            if self._thread is not None:
                self._thread.quit()

    def _provider(self, cache: dict):
        use_ollama = bool(self.ollama.get("enabled")) and self.ollama.get("model")
        if use_ollama:
            client = OllamaClient(self.ollama.get("base_url") or None
                                  or "http://localhost:11434")
            probe = client.is_available()
            if not probe.get("available"):
                return None, probe.get("error", "Ollama unavailable")
            provider = OllamaRepairProvider(
                client, self.ollama["model"],
                cancel_event=self.cancel_event,
                cache=cache["responses"],
                keep_alive=self.ollama.get("keep_alive", "10m"))
            return provider, None
        return ts.DeterministicNameProvider(self.approved_names), None

    def _run_inner(self):
        norm = ts.NormalizedTranscript.from_dict(self.norm_dict)
        if not norm.segments:
            self.failed.emit("no_transcript", "No normalized transcript available.", "")
            return

        cache = load_ai_cache(self.transcript_dir)
        provider, err = self._provider(cache)
        provider_kind = "ollama" if isinstance(provider, OllamaRepairProvider) else "offline"

        if provider is None:
            self.failed.emit(
                "unavailable",
                "Ollama is not reachable. You can retry, use deterministic "
                "repair only, or check Ollama settings.",
                str(err))
            return

        engine = ts.ContextRepairEngine(
            provider=provider, approved_names=self.approved_names,
            course_title=self.course_title, glossary=self.glossary)

        self.status.emit(
            f"Generating proposals via {provider_kind} provider"
            + (f" ({self.ollama.get('model')})" if provider_kind == "ollama" else "")
            + "…")

        try:
            corr_set, stats = engine.propose_detailed(
                norm,
                on_progress=lambda done, total: self.progress.emit(done, total),
                cancel_check=self.cancel_event.is_set)
        except OllamaError as e:
            self.failed.emit(e.kind, self._friendly(e), str(e))
            return

        if provider_kind == "ollama":
            save_ai_cache(self.transcript_dir, cache)
            stats["cache_hits"] = provider.cache_hits
            stats["requests_made"] = provider.requests_made

        if self.cancel_event.is_set():
            stats["cancelled"] = True

        self.finished_ok.emit({
            "corrections": [c.to_dict() for c in corr_set.corrections],
            "stats": stats,
            "provider_kind": provider_kind,
        })

    @staticmethod
    def _friendly(e: OllamaError) -> str:
        return {
            "unavailable": "Ollama is not reachable (is the service running?).",
            "timeout": "The Ollama request timed out.",
            "bad_response": "Ollama returned an invalid response.",
            "cancelled": "The request was cancelled.",
        }.get(e.kind, str(e))
