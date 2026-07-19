"""
Phase 4/5 fault-isolation tests: the Ollama client and the Context Repair
worker must survive every failure mode without crashing anything, and the
deterministic fallback must always be available.

A controllable in-process HTTP server plays the role of Ollama so the tests
cover: healthy schema-constrained responses, connection refused, request
timeouts, malformed JSON, mid-stream disconnection ("model unloaded"),
user cancellation mid-stream, repeated-request cache hits, and large chunks.
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lecturepack.infrastructure.ollama_client import (
    OllamaClient, OllamaRepairProvider, OllamaError, OllamaUnavailable,
    OllamaTimeout, OllamaBadResponse, OllamaCancelled, REPAIR_SCHEMA,
)
from lecturepack.services import transcript_service as ts


# --------------------------------------------------------------------------- #
# fake Ollama server
# --------------------------------------------------------------------------- #

class FakeOllama:
    def __init__(self):
        self.mode = "ok"          # ok | slow | malformed | drop_midstream | http_error
        self.requests = 0
        self.server = None
        self.thread = None

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/api/version":
                    body = json.dumps({"version": "0.32.0-test"}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/api/tags":
                    body = json.dumps({"models": [
                        {"name": "test:1b", "size": 1000,
                         "details": {"parameter_size": "1B", "quantization_level": "Q4"}},
                    ]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                fake.requests += 1
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                if self.path != "/api/chat":
                    self.send_response(404)
                    self.end_headers()
                    return
                if fake.mode == "http_error":
                    self.send_response(500)
                    body = b'{"error":"boom"}'
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if fake.mode == "slow":
                    time.sleep(5.0)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                content = json.dumps({"corrections": [
                    {"segment_id": 0,
                     "corrected_text": "Today we discuss Tutankhamun and Abu Simbel.",
                     "reason": "misheard names", "confidence": 0.9}]})
                if fake.mode == "malformed":
                    self.wfile.write(b"this is not json\n")
                    return
                pieces = [content[i:i + 20] for i in range(0, len(content), 20)]
                for i, piece in enumerate(pieces):
                    chunk = {"message": {"content": piece}, "done": False}
                    self.wfile.write((json.dumps(chunk) + "\n").encode())
                    self.wfile.flush()
                    if fake.mode == "drop_midstream" and i == 2:
                        # simulate ollama crash / model unload mid-generation
                        self.connection.close()
                        return
                    if fake.mode == "slow_stream":
                        time.sleep(0.15)
                final = {"message": {"content": ""}, "done": True,
                         "done_reason": "stop", "eval_count": 30,
                         "eval_duration": int(1e9), "load_duration": 0,
                         "total_duration": int(1e9)}
                self.wfile.write((json.dumps(final) + "\n").encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture()
def fake_ollama():
    f = FakeOllama()
    f.base_url = f.start()
    yield f
    f.stop()


def _norm():
    raw = ts.parse_raw_whisper_json({"result": {"language": "en", "transcription": [
        {"offsets": {"from": 0, "to": 3000}, "text": " Today we discuss Tuten Common and Aboo Simbel."},
        {"offsets": {"from": 3000, "to": 6000}, "text": " The pharaoh ruled for many years."},
    ]}})
    return ts.normalize_transcript(raw)


# --------------------------------------------------------------------------- #
# client-level behaviour
# --------------------------------------------------------------------------- #

def test_healthy_schema_constrained_chat(fake_ollama):
    client = OllamaClient(fake_ollama.base_url)
    probe = client.is_available()
    assert probe["available"] and probe["version"] == "0.32.0-test"
    models = client.list_models()
    assert models and models[0]["name"] == "test:1b"
    res = client.chat_structured("test:1b", "sys", "user", REPAIR_SCHEMA)
    data = json.loads(res["content"])
    assert data["corrections"][0]["segment_id"] == 0


def test_connection_refused_is_unavailable():
    client = OllamaClient("http://127.0.0.1:1")  # nothing listens here
    probe = client.is_available()
    assert not probe["available"]
    with pytest.raises(OllamaUnavailable):
        client.chat_structured("m", "s", "u", REPAIR_SCHEMA)


def test_request_timeout(fake_ollama):
    fake_ollama.mode = "slow"
    client = OllamaClient(fake_ollama.base_url)
    client_timeout = 1.0
    t0 = time.time()
    with pytest.raises((OllamaTimeout, OllamaUnavailable)):
        # stall timeout: the server sleeps 5s before responding
        import lecturepack.infrastructure.ollama_client as oc
        old = oc.STREAM_STALL_TIMEOUT
        oc.STREAM_STALL_TIMEOUT = client_timeout
        try:
            client.chat_structured("m", "s", "u", REPAIR_SCHEMA, timeout=2.0)
        finally:
            oc.STREAM_STALL_TIMEOUT = old
    assert time.time() - t0 < 10.0


def test_malformed_json_stream(fake_ollama):
    fake_ollama.mode = "malformed"
    client = OllamaClient(fake_ollama.base_url)
    with pytest.raises(OllamaBadResponse):
        client.chat_structured("m", "s", "u", REPAIR_SCHEMA)


def test_model_unload_mid_generation(fake_ollama):
    fake_ollama.mode = "drop_midstream"
    client = OllamaClient(fake_ollama.base_url)
    with pytest.raises((OllamaUnavailable, OllamaBadResponse)):
        client.chat_structured("m", "s", "u", REPAIR_SCHEMA)


def test_http_error_is_bad_response(fake_ollama):
    fake_ollama.mode = "http_error"
    client = OllamaClient(fake_ollama.base_url)
    with pytest.raises(OllamaBadResponse):
        client.chat_structured("m", "s", "u", REPAIR_SCHEMA)


def test_user_cancellation_mid_stream(fake_ollama):
    fake_ollama.mode = "slow_stream"
    client = OllamaClient(fake_ollama.base_url)
    cancel = threading.Event()

    def cancel_soon():
        time.sleep(0.2)
        cancel.set()

    threading.Thread(target=cancel_soon, daemon=True).start()
    with pytest.raises(OllamaCancelled):
        client.chat_structured("m", "s", "u", REPAIR_SCHEMA, cancel_event=cancel)


def test_repeated_request_cache_hit(fake_ollama):
    client = OllamaClient(fake_ollama.base_url)
    cache = {}
    provider = OllamaRepairProvider(client, "test:1b", cache=cache)
    r1 = provider.complete("sys", "user prompt")
    before = fake_ollama.requests
    r2 = provider.complete("sys", "user prompt")
    assert r1 == r2
    assert fake_ollama.requests == before, "second identical request must be served from cache"
    assert provider.cache_hits == 1


# --------------------------------------------------------------------------- #
# repair-engine integration
# --------------------------------------------------------------------------- #

def test_engine_with_ollama_provider_validates_and_proposes(fake_ollama):
    client = OllamaClient(fake_ollama.base_url)
    provider = OllamaRepairProvider(client, "test:1b")
    engine = ts.ContextRepairEngine(provider=provider,
                                    approved_names=["Tutankhamun", "Abu Simbel"])
    corr_set, stats = engine.propose_detailed(_norm())
    assert stats["chunks_failed"] == 0
    assert corr_set.corrections, "expected the name fix proposal"
    c = corr_set.corrections[0]
    assert "Tutankhamun" in c.corrected_text


def test_engine_survives_provider_failure_per_chunk(fake_ollama):
    fake_ollama.mode = "http_error"
    client = OllamaClient(fake_ollama.base_url)
    provider = OllamaRepairProvider(client, "test:1b")
    engine = ts.ContextRepairEngine(provider=provider, approved_names=["Tutankhamun"])
    corr_set, stats = engine.propose_detailed(_norm())
    assert stats["chunks_failed"] == stats["chunks_total"]
    assert stats["errors"]
    assert corr_set.corrections == []


def test_large_transcript_chunking(fake_ollama):
    client = OllamaClient(fake_ollama.base_url)
    provider = OllamaRepairProvider(client, "test:1b")
    engine = ts.ContextRepairEngine(provider=provider, approved_names=["Tutankhamun"])
    segs = [{"offsets": {"from": i * 1000, "to": i * 1000 + 900},
             "text": f" Segment number {i} talks about history."} for i in range(60)]
    raw = ts.parse_raw_whisper_json({"result": {"language": "en", "transcription": segs}})
    norm = ts.normalize_transcript(raw)
    progress = []
    corr_set, stats = engine.propose_detailed(
        norm, on_progress=lambda d, t: progress.append((d, t)))
    assert stats["chunks_total"] > 1
    assert progress[-1][0] == stats["chunks_total"]


def test_cancellation_between_chunks(fake_ollama):
    client = OllamaClient(fake_ollama.base_url)
    provider = OllamaRepairProvider(client, "test:1b")
    engine = ts.ContextRepairEngine(provider=provider, approved_names=["X"])
    segs = [{"offsets": {"from": i * 1000, "to": i * 1000 + 900},
             "text": f" Segment number {i}."} for i in range(60)]
    raw = ts.parse_raw_whisper_json({"result": {"language": "en", "transcription": segs}})
    norm = ts.normalize_transcript(raw)
    calls = {"n": 0}

    def cancel_after_two():
        calls["n"] += 1
        return calls["n"] > 2

    corr_set, stats = engine.propose_detailed(norm, cancel_check=cancel_after_two)
    assert stats["cancelled"] is True
    assert stats["chunks_done"] < stats["chunks_total"]


# --------------------------------------------------------------------------- #
# worker-level fault isolation (Qt)
# --------------------------------------------------------------------------- #

def _make_job_dirs(tmp_path, norm):
    td = tmp_path / "transcript"
    td.mkdir(parents=True)
    return str(td)


def test_worker_reports_unavailable_not_crash(qtbot, tmp_path):
    """Ollama down -> failed signal with recoverable kind; app alive."""
    from lecturepack.services.ai_repair_service import AiRepairWorker
    norm = _norm()
    worker = AiRepairWorker(
        transcript_dir=str(tmp_path), approved_names=["Tutankhamun"],
        norm_dict=norm.to_dict(),
        ollama_settings={"enabled": True, "model": "test:1b",
                         "base_url": "http://127.0.0.1:1"})
    with qtbot.waitSignal(worker.failed, timeout=30000) as blocker:
        worker.start()
    kind = blocker.args[0]
    assert kind in ("unavailable", "timeout")
    worker.detach_and_stop()


def test_worker_completes_and_persists_cache(qtbot, tmp_path, fake_ollama):
    from lecturepack.services.ai_repair_service import AiRepairWorker, load_ai_cache
    norm = _norm()
    worker = AiRepairWorker(
        transcript_dir=str(tmp_path), approved_names=["Tutankhamun", "Abu Simbel"],
        norm_dict=norm.to_dict(),
        ollama_settings={"enabled": True, "model": "test:1b",
                         "base_url": fake_ollama.base_url})
    with qtbot.waitSignal(worker.finished_ok, timeout=30000) as blocker:
        worker.start()
    result = blocker.args[0]
    assert result["provider_kind"] == "ollama"
    assert result["corrections"], "proposals expected"
    cache = load_ai_cache(str(tmp_path))
    assert cache["responses"], "disk cache written"
    worker.detach_and_stop()


def test_worker_detach_mid_request_is_safe(qtbot, tmp_path, fake_ollama):
    """Simulates closing the dialog / app mid-stream: detach must not hang or
    crash even while a request is in flight."""
    fake_ollama.mode = "slow_stream"
    from lecturepack.services.ai_repair_service import AiRepairWorker
    norm = _norm()
    worker = AiRepairWorker(
        transcript_dir=str(tmp_path), approved_names=["Tutankhamun"],
        norm_dict=norm.to_dict(),
        ollama_settings={"enabled": True, "model": "test:1b",
                         "base_url": fake_ollama.base_url})
    worker.start()
    qtbot.wait(150)
    worker.detach_and_stop()  # must return promptly and leave no live thread
    assert worker.cancel_event.is_set()


def test_deterministic_fallback_without_ollama(qtbot, tmp_path):
    from lecturepack.services.ai_repair_service import AiRepairWorker
    norm = _norm()
    worker = AiRepairWorker(
        transcript_dir=str(tmp_path), approved_names=["Tutankhamun", "Abu Simbel"],
        norm_dict=norm.to_dict(), ollama_settings=None)
    with qtbot.waitSignal(worker.finished_ok, timeout=30000) as blocker:
        worker.start()
    result = blocker.args[0]
    assert result["provider_kind"] == "offline"
    assert result["corrections"], "deterministic provider must propose the name fixes"
    worker.detach_and_stop()
