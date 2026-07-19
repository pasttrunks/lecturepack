from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.services.groq_transcription import (
    AudioChunk, GroqError, GroqHttpClient, merge_verbose_chunks,
    parse_retry_after, plan_audio_chunks, write_canonical_outputs,
)
from lecturepack.services.transcription_backends import (
    BACKEND_GROQ_FAST, BACKEND_LOCAL_WHISPERCPP, BackendCapabilities,
    GroqTranscriptionBackend, TranscriptionBackend, TranscriptionRequest,
    TranscriptionResult,
)


class MemorySecretStore:
    def __init__(self, value="gsk_test_secret_value"):
        self.value = value

    def get(self):
        return self.value


class CopyEncoder:
    def __init__(self, _ffmpeg=""):
        self.cancelled = False

    def encode(self, source, chunk, destination, cancelled):
        assert not cancelled()
        with open(destination, "wb") as fh:
            fh.write(b"fLaC" + bytes([chunk.index]) * 128)
        return destination

    def cancel(self):
        self.cancelled = True


def test_size_aware_chunk_plan_has_overlap_and_stays_in_order():
    chunks = plan_audio_chunks(65.0, 400_000, overlap_seconds=2.0)
    assert len(chunks) > 1
    assert chunks[0].start_seconds == 0
    assert chunks[-1].end_seconds == 65.0
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[1].start_seconds < chunks[0].end_seconds
    assert max(c.duration_seconds for c in chunks) * 32_000 <= 400_000


def test_merge_offsets_sorts_and_deduplicates_overlap(tmp_path):
    merged = merge_verbose_chunks([
        (AudioChunk(1, 8.0, 18.0), {"language": "en", "segments": [
            {"start": 0, "end": 2, "text": "two three"},
            {"start": 2, "end": 5, "text": "three four"},
        ]}),
        (AudioChunk(0, 0, 10.0), {"language": "en", "segments": [
            {"start": 0, "end": 4, "text": "one two"},
            {"start": 4, "end": 10, "text": "two three"},
        ]}),
    ])
    assert [s["start"] for s in merged["segments"]] == sorted(
        s["start"] for s in merged["segments"])
    assert merged["text"].split().count("two") < 3
    paths = write_canonical_outputs(merged, str(tmp_path / "transcript" / "raw"))
    raw = json.loads(open(paths[0], encoding="utf-8").read())
    offsets = [x["offsets"]["from"] for x in raw["result"]["transcription"]]
    assert offsets == sorted(offsets)
    assert os.path.exists(paths[1]) and os.path.exists(paths[2])


def test_retry_after_seconds_and_http_date():
    assert parse_retry_after("2.5") == 2.5
    assert parse_retry_after("Thu, 01 Jan 1970 00:00:10 GMT", now=5) == 5
    assert parse_retry_after("bad") == 0


class _MockGroqHandler(BaseHTTPRequestHandler):
    calls = 0
    auth = []
    bodies = []
    fail_first = False

    def do_POST(self):
        type(self).calls += 1
        type(self).auth.append(self.headers.get("Authorization"))
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).bodies.append(body)
        if type(self).fail_first and type(self).calls == 1:
            self.send_response(429)
            self.send_header("retry-after", "0")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"rate limited"}}')
            return
        payload = {"language": "en", "text": "alpha beta",
                   "segments": [{"start": 0, "end": 1.5,
                                  "text": "alpha beta"}]}
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        pass


@pytest.fixture
def mock_groq_server():
    _MockGroqHandler.calls = 0
    _MockGroqHandler.auth = []
    _MockGroqHandler.bodies = []
    _MockGroqHandler.fail_first = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockGroqHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/openai/v1/audio/transcriptions"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_http_client_retries_429_redacts_key_and_uses_audio_only(
        tmp_path, mock_groq_server):
    audio = tmp_path / "chunk.flac"
    audio.write_bytes(b"fLaC-audio-only")
    _MockGroqHandler.fail_first = True
    client = GroqHttpClient(mock_groq_server, max_retries=1, sleep=lambda _s: None)
    result = client.transcribe(str(audio), api_key="gsk_super_secret",
                               model="whisper-large-v3-turbo")
    assert result["text"] == "alpha beta"
    assert _MockGroqHandler.calls == 2
    assert _MockGroqHandler.auth == ["Bearer gsk_super_secret"] * 2
    body = _MockGroqHandler.bodies[-1]
    assert b"fLaC-audio-only" in body
    assert b"slide" not in body and b"transcript" not in body


def test_provider_error_redacts_secret(monkeypatch, tmp_path):
    import urllib.error
    import urllib.request

    key = "gsk_must_never_escape"
    audio = tmp_path / "chunk.flac"
    audio.write_bytes(b"fLaC")

    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://api.groq.com", 401, "unauthorized", {},
            io.BytesIO(("bad key " + key).encode()))

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(GroqError) as caught:
        GroqHttpClient(max_retries=0).transcribe(
            str(audio), api_key=key, model="whisper-large-v3-turbo")
    assert key not in str(caught.value)
    assert "[redacted]" in str(caught.value)


def test_backend_requires_privacy_before_secret_or_upload(qtbot, tmp_path):
    class ExplodingStore:
        def get(self):
            raise AssertionError("secret must not be read before consent")

    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"wav")
    backend = GroqTranscriptionBackend(
        BACKEND_GROQ_FAST, "whisper-large-v3-turbo", None,
        secret_store=ExplodingStore(), client_factory=lambda: None,
        encoder_factory=CopyEncoder)
    results = []
    backend.finished.connect(results.append)
    backend.start(TranscriptionRequest(
        audio_path=str(audio), output_prefix=str(tmp_path / "raw"), model="",
        source_duration_seconds=10, provider_options={"privacy_accepted": False}))
    qtbot.waitUntil(lambda: bool(results), timeout=3000)
    assert results[0].error_code == "privacy_required"
    assert not results[0].fallback_allowed


def test_backend_mock_integration_resume_and_no_secret_persistence(
        qtbot, tmp_path, mock_groq_server):
    cfg = ConfigManager(str(tmp_path / "config"))
    cfg.set("groq_max_upload_bytes", 400_000)
    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"source-audio")

    def client_factory():
        return GroqHttpClient(mock_groq_server, max_retries=0)

    def run_once():
        backend = GroqTranscriptionBackend(
            BACKEND_GROQ_FAST, "whisper-large-v3-turbo", cfg,
            secret_store=MemorySecretStore(), client_factory=client_factory,
            encoder_factory=CopyEncoder)
        results = []
        backend.finished.connect(results.append)
        backend.start(TranscriptionRequest(
            audio_path=str(audio), output_prefix=str(tmp_path / "transcript" / "raw"),
            model="", prompt="PRIVATE_GLOSSARY_TERM", source_duration_seconds=22,
            provider_options={"privacy_accepted": True, "concurrency": 2,
                              "max_upload_bytes": 400_000}))
        qtbot.waitUntil(lambda: bool(results), timeout=5000)
        assert results[0].success
        return results[0]

    first = run_once()
    calls = _MockGroqHandler.calls
    second = run_once()
    assert _MockGroqHandler.calls == calls
    assert second.metrics["resumed_chunks"] == second.metrics["chunks"]
    assert first.metrics["chunks"] > 1
    assert all(b"PRIVATE_GLOSSARY_TERM" not in body
               for body in _MockGroqHandler.bodies)
    for path in tmp_path.rglob("*.json"):
        assert "gsk_test_secret_value" not in path.read_text(encoding="utf-8")
    assert "gsk_test_secret_value" not in cfg.config_path


def test_backend_cancel_is_fast_during_active_provider_work(qtbot, tmp_path):
    started = threading.Event()

    class WaitingClient:
        def transcribe(self, _path, *, cancelled, **_kwargs):
            started.set()
            while not cancelled():
                time.sleep(0.01)
            raise GroqError("cancelled", kind="cancelled", retryable=False)

        def cancel(self):
            pass

    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"source")
    backend = GroqTranscriptionBackend(
        BACKEND_GROQ_FAST, "whisper-large-v3-turbo", None,
        secret_store=MemorySecretStore(), client_factory=WaitingClient,
        encoder_factory=CopyEncoder)
    results = []
    backend.finished.connect(results.append)
    backend.start(TranscriptionRequest(
        audio_path=str(audio), output_prefix=str(tmp_path / "raw"), model="",
        source_duration_seconds=10,
        provider_options={"privacy_accepted": True, "max_upload_bytes": 400_000}))
    qtbot.waitUntil(started.is_set, timeout=2000)
    before = time.perf_counter()
    backend.cancel()
    qtbot.waitUntil(lambda: bool(results), timeout=2000)
    assert time.perf_counter() - before < 0.5
    assert results[0].error_code == "cancelled"


def test_online_selection_requires_per_job_privacy_and_persists_no_key(
        qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lecturepack.infrastructure.secret_store import WindowsCredentialStore
    from lecturepack.models.job import Job
    from lecturepack.ui.main_window import MainWindow

    config = ConfigManager(str(tmp_path / "data"))
    window = MainWindow(config)
    qtbot.addWidget(window)
    job = Job(config.data_dir, video_path=os.path.abspath(
        "tests/fixtures/synthetic_lecture.mp4"))
    window.current_job = job
    window.controller.set_job(job)
    index = window.process_page.transcription_mode_combo.findData(BACKEND_GROQ_FAST)
    window.process_page.transcription_mode_combo.setCurrentIndex(index)
    monkeypatch.setattr(WindowsCredentialStore, "has_secret", lambda _self: True)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k:
                        QMessageBox.StandardButton.Yes)
    runs = []
    monkeypatch.setattr(window.controller, "run_pipeline", lambda: runs.append(True))
    window._start_processing()
    assert runs == [True]
    assert job.settings["whisper"]["online_privacy_accepted"] is True
    settings_text = open(job.settings_path, encoding="utf-8").read()
    config_text = open(config.config_path, encoding="utf-8").read()
    assert "gsk_" not in settings_text + config_text
    window.close()


def test_controller_online_failure_falls_back_without_stopping_slide_branch(
        tmp_path, monkeypatch):
    from lecturepack.constants import STAGE_DETECT_SLIDES, STAGE_TRANSCRIBE
    from lecturepack.controllers.job_controller import JobController
    from lecturepack.models.job import Job

    class FailingOnline(TranscriptionBackend):
        def capabilities(self):
            return BackendCapabilities(
                key=BACKEND_GROQ_FAST, label="Online Fast (Groq)", provider="Groq",
                is_local=False, requires_secret=True, uploads_audio=True,
                supports_segment_timestamps=True, supports_word_timestamps=True,
                supports_prompt=True, supports_vad=False, supports_resume=True)

        def start(self, request):
            self.request = request

        def cancel(self):
            pass

    config = ConfigManager(str(tmp_path / "data"))
    job = Job(config.data_dir, video_path=os.path.abspath(
        "tests/fixtures/synthetic_lecture.mp4"))
    job.source["duration"] = 10
    job.settings["whisper"].update({
        "transcription_backend": BACKEND_GROQ_FAST,
        "online_privacy_accepted": True,
        "online_fallback_local": True,
    })
    transcript = os.path.join(job.paths["transcript"], "raw.json")
    with open(transcript, "w", encoding="utf-8") as fh:
        fh.write('{"existing": true}')
    before = open(transcript, "rb").read()
    controller = JobController(config)
    controller.set_job(job)
    online = FailingOnline()
    controller.transcription_backends.register(online)
    local, _ = controller.transcription_backends.resolve(BACKEND_LOCAL_WHISPERCPP)
    local_requests = []
    monkeypatch.setattr(local, "start", local_requests.append)
    controller._active_stages.update({STAGE_TRANSCRIBE, STAGE_DETECT_SLIDES})
    controller.current_stage = STAGE_TRANSCRIBE
    controller._run_transcribe(parallel=True)
    online.finished.emit(TranscriptionResult(
        success=False, backend_key=BACKEND_GROQ_FAST, provider="Groq",
        error_code="rate_limit", error_message="quota unavailable",
        retryable=True, fallback_allowed=True))
    assert len(local_requests) == 1
    assert STAGE_DETECT_SLIDES in controller._active_stages
    assert job.get_stage_status(STAGE_TRANSCRIBE) != "failed"
    assert open(transcript, "rb").read() == before
    assert job.state["stages"][STAGE_TRANSCRIBE]["online_failure"]["code"] == "rate_limit"
    pending_json = local_requests[0].output_prefix + ".json"
    with open(pending_json, "w", encoding="utf-8") as fh:
        fh.write('{"partial": true}')
    local.finished.emit(TranscriptionResult(
        success=False, backend_key=BACKEND_LOCAL_WHISPERCPP,
        provider="whisper.cpp", error_code="local_process_failed",
        error_message="local fallback failed", retryable=True))
    assert open(transcript, "rb").read() == before
    assert not os.path.exists(pending_json)


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree contract")
def test_groq_encoder_owned_tree_cleanup_does_not_kill_unrelated_process(tmp_path):
    from lecturepack.infrastructure.process_tree import terminate_owned_subprocess_tree

    child_file = tmp_path / "groq-encoder-child.pid"
    flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) |
             getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    owned = subprocess.Popen(
        [sys.executable, os.path.abspath("tests/fixtures/process_tree_parent.py"),
         str(child_file)], creationflags=flags)
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.time() + 5
        while not child_file.exists() and time.time() < deadline:
            time.sleep(0.02)
        assert child_file.exists()
        deadline = time.monotonic() + 3
        child_pid = 0
        while time.monotonic() < deadline:
            try:
                value = child_file.read_text(encoding="ascii").strip()
                if value.isdigit():
                    child_pid = int(value)
                    break
            except OSError:
                pass
            time.sleep(0.02)
        assert child_pid > 0
        report = terminate_owned_subprocess_tree(owned)
        assert report["root_pid"] == owned.pid
        assert report["finished"] is True
        assert unrelated.poll() is None
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(child_pid, 0)
            except OSError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("owned encoder child remained alive")
        print("groq_encoder_cleanup=" + json.dumps(
            {**report, "child_pid": child_pid,
             "unrelated_survived": unrelated.poll() is None}, sort_keys=True))
    finally:
        if owned.poll() is None:
            owned.kill()
        if unrelated.poll() is None:
            unrelated.kill()
        owned.wait(timeout=5)
        unrelated.wait(timeout=5)


def test_application_close_with_active_mock_provider_is_nonblocking(
        qtbot, tmp_path):
    from lecturepack.constants import STAGE_TRANSCRIBE
    from lecturepack.models.job import Job
    from lecturepack.ui.main_window import MainWindow

    started = threading.Event()

    class WaitingClient:
        def transcribe(self, _path, *, cancelled, **_kwargs):
            started.set()
            while not cancelled():
                time.sleep(0.01)
            raise GroqError("cancelled", kind="cancelled", retryable=False)

        def cancel(self):
            pass

    config = ConfigManager(str(tmp_path / "data"))
    window = MainWindow(config)
    qtbot.addWidget(window)
    job = Job(config.data_dir, video_path=os.path.abspath(
        "tests/fixtures/synthetic_lecture.mp4"))
    job.source["duration"] = 10
    job.settings["whisper"].update({
        "transcription_backend": BACKEND_GROQ_FAST,
        "online_privacy_accepted": True,
    })
    audio = os.path.join(job.paths["audio"], "lecture-16khz-mono.wav")
    with open(audio, "wb") as fh:
        fh.write(b"source")
    backend = GroqTranscriptionBackend(
        BACKEND_GROQ_FAST, "whisper-large-v3-turbo", config,
        secret_store=MemorySecretStore(), client_factory=WaitingClient,
        encoder_factory=CopyEncoder)
    window.controller.transcription_backends.register(backend)
    window.current_job = job
    window.controller.set_job(job)
    window.controller.current_stage = STAGE_TRANSCRIBE
    window.controller._active_stages = {STAGE_TRANSCRIBE}
    window.controller._run_transcribe()
    qtbot.waitUntil(started.is_set, timeout=2000)
    before = time.perf_counter()
    window.close()
    elapsed = time.perf_counter() - before
    assert elapsed < 1.0
    assert backend.worker.wait(1000)
    print(f"groq_active_app_close_seconds={elapsed:.6f}")
