"""Provider-neutral transcription contract without enabling online access."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, Signal

from lecturepack.constants import STAGE_TRANSCRIBE
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.transcription_engines import EngineInfo, ENGINE_CPU
from lecturepack.models.job import Job
from lecturepack.services.transcription_backends import (
    BACKEND_LOCAL_WHISPERCPP, BackendCapabilities, BackendRegistry,
    LocalWhisperCppBackend, TranscriptionBackend, TranscriptionRequest,
    TranscriptionResult,
)
from lecturepack.infrastructure.whisper_wrapper import WhisperWrapper


class FakeWhisperWrapper(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)
    backend_detected = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.cancelled = False
        self.whisper_exe_path = ""

    def start_transcription(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def cancel(self):
        self.cancelled = True


class FakeEngineRegistry:
    def resolve(self, requested):
        return EngineInfo(
            key=ENGINE_CPU, label="Local CPU", exe_path="mock-whisper.py",
            available=True, backend="CPU", reason="test")


def _request(tmp_path):
    return TranscriptionRequest(
        audio_path=str(tmp_path / "lecture.wav"),
        output_prefix=str(tmp_path / "transcript" / "raw"),
        model="ggml-base.en.bin", language="en", prompt="Giza, Khufu",
        threads=6,
        vad={"enabled": False, "model_path": "", "threshold": 0.5},
        local_engine=ENGINE_CPU,
    )


def test_capability_contract_is_explicit_and_json_safe():
    caps = BackendCapabilities(
        key=BACKEND_LOCAL_WHISPERCPP, label="Private Local", provider="whisper.cpp",
        is_local=True, requires_secret=False, uploads_audio=False,
        supports_segment_timestamps=True, supports_word_timestamps=True,
        supports_prompt=True, supports_vad=True, supports_resume=False,
    )
    payload = caps.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["is_local"] is True
    assert payload["uploads_audio"] is False
    assert payload["requires_secret"] is False


def test_registry_contains_only_private_local_backend_and_safe_fallback():
    wrapper = FakeWhisperWrapper()
    registry = BackendRegistry(
        config_manager=None, local_wrapper=wrapper,
        local_engine_registry=FakeEngineRegistry())

    assert registry.keys() == [BACKEND_LOCAL_WHISPERCPP]
    local, reason = registry.resolve(BACKEND_LOCAL_WHISPERCPP)
    assert isinstance(local, LocalWhisperCppBackend)
    assert local.capabilities().is_local
    assert not local.capabilities().uploads_audio
    assert reason == "explicitly selected"

    fallback, reason = registry.resolve("future-online-provider")
    assert fallback is local
    assert "unavailable" in reason.lower()
    assert registry.any_network_enabled() is False


def test_local_adapter_preserves_arguments_progress_backend_result_and_cancel(qtbot, tmp_path):
    wrapper = FakeWhisperWrapper()
    backend = LocalWhisperCppBackend(wrapper, FakeEngineRegistry())
    request = _request(tmp_path)
    progress = []
    detected = []
    results = []
    backend.progress.connect(progress.append)
    backend.backend_detected.connect(detected.append)
    backend.finished.connect(results.append)

    backend.start(request)
    assert len(wrapper.calls) == 1
    args, kwargs = wrapper.calls[0]
    assert args == (request.audio_path, request.model, request.output_prefix)
    assert kwargs == {
        "glossary": request.prompt,
        "threads": request.threads,
        "vad_settings": request.vad,
        "engine_exe": "mock-whisper.py",
        "extra_args": [],
    }

    wrapper.progress.emit("25%\n")
    wrapper.backend_detected.emit("CPU AVX2")
    wrapper.finished.emit(True, "")
    assert progress == ["25%\n"]
    assert detected == ["CPU AVX2"]
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, TranscriptionResult)
    assert result.success and result.backend_key == BACKEND_LOCAL_WHISPERCPP
    assert result.actual_backend == "CPU AVX2"
    assert result.raw_json_path == request.output_prefix + ".json"
    assert result.raw_srt_path == request.output_prefix + ".srt"
    assert result.raw_txt_path == request.output_prefix + ".txt"

    backend.cancel()
    assert wrapper.cancelled
    assert request.cancel_token.is_cancelled()


def test_local_adapter_failure_is_structured_and_does_not_expose_request_paths(qtbot, tmp_path):
    wrapper = FakeWhisperWrapper()
    backend = LocalWhisperCppBackend(wrapper, FakeEngineRegistry())
    request = _request(tmp_path)
    results = []
    backend.finished.connect(results.append)
    backend.start(request)
    wrapper.finished.emit(False, "whisper-cli exited with code 9")

    result = results[0]
    assert not result.success
    assert result.error_code == "local_process_failed"
    assert result.retryable is True
    assert result.fallback_allowed is False
    assert request.audio_path not in result.error_message


def test_controller_local_cache_fingerprint_is_unchanged_by_explicit_backend(tmp_path):
    data_dir = str(tmp_path / "data")
    config = ConfigManager(data_dir)
    job = Job(data_dir, video_path=os.path.abspath("tests/fixtures/synthetic_lecture.mp4"))
    controller = JobController(config)
    controller.set_job(job)

    job.settings["whisper"].pop("transcription_backend", None)
    legacy = controller._stage_fingerprint(STAGE_TRANSCRIBE)
    job.settings["whisper"]["transcription_backend"] = BACKEND_LOCAL_WHISPERCPP
    explicit = controller._stage_fingerprint(STAGE_TRANSCRIBE)
    assert explicit == legacy
    job.settings["whisper"]["transcription_backend"] = "test-provider"
    assert controller._stage_fingerprint(STAGE_TRANSCRIBE) != legacy


class FakeProviderBackend(TranscriptionBackend):
    def __init__(self):
        super().__init__()
        self.request = None
        self.cancelled = False

    def capabilities(self):
        return BackendCapabilities(
            key="test-provider", label="Test Provider", provider="test",
            is_local=False, requires_secret=True, uploads_audio=True,
            supports_segment_timestamps=True, supports_word_timestamps=True,
            supports_prompt=True, supports_vad=False, supports_resume=True,
            accepted_audio_formats=("flac",), max_upload_bytes=1024)

    def start(self, request):
        self.request = request

    def cancel(self):
        self.cancelled = True
        if self.request:
            self.request.cancel_token.cancel()


def test_controller_accepts_injected_backend_without_provider_logic(tmp_path):
    data_dir = str(tmp_path / "data")
    config = ConfigManager(data_dir)
    job = Job(data_dir, video_path=os.path.abspath("tests/fixtures/synthetic_lecture.mp4"))
    job.source["duration"] = 65.0
    job.settings["whisper"]["transcription_backend"] = "test-provider"
    job.settings["whisper"]["language"] = "en"
    job.settings["whisper"]["glossary"] = "Khufu"
    controller = JobController(config)
    controller.set_job(job)
    fake = FakeProviderBackend()
    unavailable_fingerprint = controller._stage_fingerprint(STAGE_TRANSCRIBE)
    controller.transcription_backends.register(fake)
    assert controller._stage_fingerprint(STAGE_TRANSCRIBE) != unavailable_fingerprint

    controller._run_transcribe()
    assert controller.transcription_backend is fake
    assert fake.request.job_id == job.job_id
    assert fake.request.language == "en"
    assert fake.request.prompt == "Khufu"
    assert fake.request.source_duration_seconds == 65.0
    assert fake.request.output_prefix.endswith(os.path.join("transcript", "raw"))

    controller.current_stage = STAGE_TRANSCRIBE
    controller._active_stages.add(STAGE_TRANSCRIBE)
    controller.cancel()
    assert fake.cancelled
    assert fake.request.cancel_token.is_cancelled()


def test_cpu_backend_is_recorded_only_from_runtime_output(qtbot):
    wrapper = WhisperWrapper()
    detected = []
    wrapper.backend_detected.connect(detected.append)
    wrapper._probe_backend("whisper_backend_init: loaded CPU backend\n")
    assert detected == ["CPU"]


def test_local_pipeline_keeps_canonical_raw_output_and_provider_provenance(qtbot, tmp_path):
    data_dir = str(tmp_path / "data")
    config = ConfigManager(data_dir)
    config.set("whisper_exe", os.path.abspath("tests/fixtures/mock_whisper.py"))
    config.set("whisper_model", "ggml-base.bin")
    controller = JobController(config)
    controller.ffmpeg_wrapper.ffmpeg_path = os.path.abspath(
        "tests/fixtures/mock_ffmpeg.py")
    controller.ffmpeg_wrapper.ffprobe_path = os.path.abspath(
        "tests/fixtures/mock_ffprobe.py")
    job = Job(data_dir, video_path=os.path.abspath(
        "tests/fixtures/synthetic_lecture.mp4"))
    controller.set_job(job)

    with qtbot.waitSignal(controller.pipeline_completed, timeout=20000):
        controller.run_pipeline()

    with open(os.path.join(job.paths["transcript"], "raw.json"),
              encoding="utf-8") as handle:
        raw = json.load(handle)
    segments = raw["result"]["transcription"]
    assert raw["systeminfo"] == "mock-whisper-cpp"
    assert segments[0] == {
        "offsets": {"from": 0, "to": 5000},
        "text": " Welcome to CS101 Lecture 3.",
    }
    assert segments[-1]["offsets"] == {"from": 60000, "to": 65000}
    stage = job.state["stages"][STAGE_TRANSCRIBE]
    assert stage["transcription_backend"] == BACKEND_LOCAL_WHISPERCPP
    assert stage["transcription_backend_requested"] == BACKEND_LOCAL_WHISPERCPP
    assert stage["transcription_provider"] == "whisper.cpp"
    assert stage["engine_used"] == ENGINE_CPU
    assert "backend_used" not in stage, \
        "selected CPU is not proof of what the process actually loaded"


def test_old_job_defaults_to_local_and_controller_records_provider_metadata(tmp_path):
    data_dir = str(tmp_path / "data")
    job = Job(data_dir, video_path=os.path.abspath("tests/fixtures/synthetic_lecture.mp4"))
    job.settings["whisper"].pop("transcription_backend", None)
    job.save()
    settings_before = open(job.settings_path, encoding="utf-8").read()

    reopened = Job(data_dir, job_id=job.job_id)
    assert "transcription_backend" not in reopened.settings["whisper"]

    config = ConfigManager(data_dir)
    controller = JobController(config)
    controller.set_job(reopened)
    resolved, _ = controller.transcription_backends.resolve(
        reopened.settings["whisper"].get(
            "transcription_backend", BACKEND_LOCAL_WHISPERCPP))
    assert resolved.capabilities().key == BACKEND_LOCAL_WHISPERCPP
    assert open(reopened.settings_path, encoding="utf-8").read() == settings_before
    controller._handle_transcription_result(TranscriptionResult(
        success=False, backend_key=BACKEND_LOCAL_WHISPERCPP,
        provider="whisper.cpp", error_code="local_process_failed",
        error_message="test failure", retryable=True, fallback_allowed=False))
    stage = reopened.state["stages"][STAGE_TRANSCRIBE]
    assert stage["transcription_backend"] == BACKEND_LOCAL_WHISPERCPP
    assert stage["transcription_backend_requested"] == BACKEND_LOCAL_WHISPERCPP
    assert stage["transcription_provider"] == "whisper.cpp"
    persisted_text = open(reopened.state_path, encoding="utf-8").read()
    assert "api_key" not in persisted_text.lower()
