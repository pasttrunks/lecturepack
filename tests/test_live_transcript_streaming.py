"""Phase 1 incremental streaming: live transcript segments from whisper.cpp.

Covers the pure-Python line parser (no Qt), the WhisperWrapper signal path,
the provider-neutral backend relay, the JobController relay + log throttle,
and an end-to-end QProcess run against a streaming mock whisper binary.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QProcess, Signal

from lecturepack.constants import STAGE_TRANSCRIBE
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.transcription_engines import (
    EngineInfo, ENGINE_CPU,
)
from lecturepack.infrastructure.whisper_wrapper import (
    LiveSegmentParser, WhisperWrapper, _segment_timestamp_to_ms,
)
from lecturepack.models.job import Job
from lecturepack.services.transcription_backends import (
    BACKEND_LOCAL_WHISPERCPP, LocalWhisperCppBackend, TranscriptionRequest,
    TranscriptionResult,
)

SEGMENT_1 = "[00:00:00.000 --> 00:00:05.000]   Welcome to CS101 Lecture 3.\n"
SEGMENT_2 = "[00:00:05.000 --> 00:00:15.000]   Today we cover Topic A.\n"


# ---------------------------------------------------------------------- #
# LiveSegmentParser (pure Python, no Qt)                                  #
# ---------------------------------------------------------------------- #
def test_timestamp_conversion():
    assert _segment_timestamp_to_ms("00:00:00.000") == 0
    assert _segment_timestamp_to_ms("00:01:05.250") == 65250
    assert _segment_timestamp_to_ms("01:00:00.000") == 3600000


def test_parser_emits_complete_segment_lines():
    segments = LiveSegmentParser().feed((SEGMENT_1 + SEGMENT_2).encode("utf-8"))
    assert segments == [
        {"start_ms": 0, "end_ms": 5000, "text": "Welcome to CS101 Lecture 3.",
         "seq": 1},
        {"start_ms": 5000, "end_ms": 15000, "text": "Today we cover Topic A.",
         "seq": 2},
    ]


def test_parser_handles_segment_split_across_chunks():
    parser = LiveSegmentParser()
    payload = SEGMENT_1.encode("utf-8")
    assert parser.feed(payload[:17]) == []  # partial line: nothing yet
    segments = parser.feed(payload[17:])
    assert [s["text"] for s in segments] == ["Welcome to CS101 Lecture 3."]


def test_parser_ignores_carriage_return_progress_pollution():
    parser = LiveSegmentParser()
    payload = ("whisper_print_progress: progress =  42%\r" + SEGMENT_1).encode("utf-8")
    segments = parser.feed(payload)
    assert [s["text"] for s in segments] == ["Welcome to CS101 Lecture 3."]


def test_parser_decodes_multibyte_utf8_split_across_chunks():
    line = "[00:00:05.000 --> 00:00:15.000]   Café au lait économie.\n"
    payload = line.encode("utf-8")
    split = payload.index("é".encode("utf-8")) + 1  # inside a 2-byte sequence
    parser = LiveSegmentParser()
    assert parser.feed(payload[:split]) == []
    segments = parser.feed(payload[split:])
    assert len(segments) == 1
    assert segments[0]["text"] == "Café au lait économie."


def test_parser_ignores_non_segment_lines():
    parser = LiveSegmentParser()
    payload = (
        "whisper_init_from_file_with_params_no_state: loading model\n"
        "whisper_print_timings: total time = 1234.56 ms\n"
        "\n"
        "[00:00:00.000 --> 00:00:05.000]   \n"  # empty text: skipped
    ).encode("utf-8")
    assert parser.feed(payload) == []


def test_parser_flush_emits_trailing_unterminated_segment():
    parser = LiveSegmentParser()
    unterminated = SEGMENT_1.rstrip("\n").encode("utf-8")
    assert parser.feed(unterminated) == []
    segments = parser.flush()
    assert [s["text"] for s in segments] == ["Welcome to CS101 Lecture 3."]
    assert parser.flush() == []


def test_parser_seq_is_monotonic_across_feeds_and_reset():
    parser = LiveSegmentParser()
    first = parser.feed(SEGMENT_1.encode("utf-8"))
    second = parser.feed(SEGMENT_2.encode("utf-8"))
    assert [s["seq"] for s in first + second] == [1, 2]
    parser.reset()
    third = parser.feed(SEGMENT_1.encode("utf-8"))
    assert third[0]["seq"] == 1


# ---------------------------------------------------------------------- #
# WhisperWrapper signal path                                              #
# ---------------------------------------------------------------------- #
class _FakeProcess:
    """Minimal stand-in for QProcess: queued stdout chunks."""

    def __init__(self):
        self._chunks = []

    def push(self, data):
        self._chunks.append(data)

    def readAllStandardOutput(self):
        data = b"".join(self._chunks)
        self._chunks = []

        class _Buffer:
            def __init__(self, payload):
                self._payload = payload

            def data(self):
                return self._payload

        return _Buffer(data)


def test_wrapper_emits_segment_ready_from_process_output(qtbot):
    wrapper = WhisperWrapper()
    wrapper.process = _FakeProcess()
    segments, logs = [], []
    wrapper.segment_ready.connect(segments.append)
    wrapper.progress.connect(logs.append)

    wrapper.process.push("loading model\n".encode("utf-8"))
    wrapper._handle_ready_read()
    assert segments == []
    assert logs == ["loading model\n"]

    wrapper.process.push((SEGMENT_1 + SEGMENT_2).encode("utf-8"))
    wrapper._handle_ready_read()
    assert [s["text"] for s in segments] == [
        "Welcome to CS101 Lecture 3.", "Today we cover Topic A."]


def test_wrapper_flushes_trailing_segment_on_finished(qtbot):
    wrapper = WhisperWrapper()
    wrapper.process = _FakeProcess()
    segments, finished = [], []
    wrapper.segment_ready.connect(segments.append)
    wrapper.finished.connect(lambda *args: finished.append(args))

    wrapper.process.push(SEGMENT_1.rstrip("\n").encode("utf-8"))
    wrapper._handle_ready_read()
    assert segments == []
    wrapper._handle_finished(0, QProcess.ExitStatus.NormalExit)
    assert [s["text"] for s in segments] == ["Welcome to CS101 Lecture 3."]
    assert finished == [(True, "")]


# ---------------------------------------------------------------------- #
# Backend relay                                                           #
# ---------------------------------------------------------------------- #
class _FakeWrapper(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)
    backend_detected = Signal(str)
    segment_ready = Signal(dict)

    whisper_exe_path = ""

    def start_transcription(self, *args, **kwargs):
        pass

    def cancel(self):
        pass


class _FakeEngineRegistry:
    def resolve(self, requested):
        return EngineInfo(
            key=ENGINE_CPU, label="Local CPU", exe_path="mock-whisper.py",
            available=True, backend="CPU", reason="test")


def test_local_backend_relays_segment_ready_and_advertises_it(qtbot):
    wrapper = _FakeWrapper()
    backend = LocalWhisperCppBackend(wrapper, _FakeEngineRegistry())
    assert backend.capabilities().supports_live_segments is True

    segments = []
    backend.segment_ready.connect(segments.append)
    payload = {"start_ms": 0, "end_ms": 5000, "text": "Hello", "seq": 1}
    wrapper.segment_ready.emit(payload)
    assert segments == [payload]


def test_local_backend_tolerates_wrapper_without_segment_signal(qtbot):
    class _LegacyWrapper(QObject):
        progress = Signal(str)
        finished = Signal(bool, str)
        backend_detected = Signal(str)
        whisper_exe_path = ""

        def start_transcription(self, *args, **kwargs):
            pass

        def cancel(self):
            pass

    # Must construct without AttributeError even though the wrapper lacks
    # the optional live-streaming signal.
    backend = LocalWhisperCppBackend(_LegacyWrapper(), _FakeEngineRegistry())
    assert backend.capabilities().supports_live_segments is True


# ---------------------------------------------------------------------- #
# JobController relay + log throttle                                      #
# ---------------------------------------------------------------------- #
def test_controller_relays_transcript_segment(qtbot, tmp_path):
    config = ConfigManager(str(tmp_path / "data"))
    controller = JobController(config)
    segments = []
    controller.transcript_segment.connect(segments.append)
    payload = {"start_ms": 1000, "end_ms": 2000, "text": "Relayed", "seq": 1}
    controller.transcription_backend.segment_ready.emit(payload)
    assert segments == [payload]


def test_controller_throttles_transcribe_log(qtbot, tmp_path):
    controller = JobController(ConfigManager(str(tmp_path / "data")))
    logs = []
    controller.stage_log.connect(lambda stage, msg: logs.append((stage, msg)))

    controller._handle_whisper_log("chunk-1\n")
    controller._handle_whisper_log("chunk-2\n")
    assert logs == []  # buffered, nothing emitted synchronously

    controller._flush_transcribe_log()
    assert logs == [(STAGE_TRANSCRIBE, "chunk-1\nchunk-2\n")]
    assert not controller._transcribe_log_timer.isActive()


def test_controller_result_flushes_pending_log_before_completion(qtbot, tmp_path):
    data_dir = str(tmp_path / "data")
    config = ConfigManager(data_dir)
    job = Job(data_dir, video_path=os.path.abspath(
        "tests/fixtures/synthetic_lecture.mp4"))
    controller = JobController(config)
    controller.set_job(job)

    logs = []
    controller.stage_log.connect(lambda stage, msg: logs.append(msg))
    controller._handle_whisper_log("pending-whisper-output\n")
    controller._handle_transcription_result(TranscriptionResult(
        success=False, backend_key=BACKEND_LOCAL_WHISPERCPP,
        provider="whisper.cpp", error_code="local_process_failed",
        error_message="boom", retryable=True, fallback_allowed=False))

    assert logs[0] == "pending-whisper-output\n"
    assert any("Transcription failed" in msg for msg in logs[1:])


# ---------------------------------------------------------------------- #
# End-to-end: real QProcess against the streaming mock whisper binary     #
# ---------------------------------------------------------------------- #
def test_end_to_end_live_segments_from_streaming_mock(qtbot, tmp_path):
    config = ConfigManager(str(tmp_path / "data"))
    config.set("whisper_exe", os.path.abspath(
        "tests/fixtures/mock_whisper_streaming.py"))
    config.set("whisper_model", "ggml-base.bin")
    controller = JobController(config)
    # The controller's finished handler drives the stage machine, so a job
    # must be loaded; mark all sibling stages completed so finishing the
    # transcription branch spawns no further work.
    job = Job(str(tmp_path / "data"), video_path=os.path.abspath(
        "tests/fixtures/synthetic_lecture.mp4"))
    for stage in ("Inspect", "Extract Audio", "Detect Slides", "Align",
                  "Review Ready"):
        job.set_stage_status(stage, "completed")
    controller.set_job(job)
    backend = controller.transcription_backend

    segments, results = [], []
    backend.segment_ready.connect(segments.append)
    backend.finished.connect(results.append)

    request = TranscriptionRequest(
        audio_path=str(tmp_path / "lecture.wav"),
        output_prefix=str(tmp_path / "transcript" / "raw"),
        model="ggml-base.bin", language="en",
        local_engine=ENGINE_CPU)
    with qtbot.waitSignal(backend.finished, timeout=20000):
        backend.start(request)

    result = results[0]
    assert result.success is True
    texts = [s["text"] for s in segments]
    assert texts == [
        "Welcome to CS101 Lecture 3.",
        "Today we cover café au lait economics.",
        "Thank you for attending.",
    ]
    assert segments[0]["start_ms"] == 0
    assert segments[1]["end_ms"] == 15000
    assert [s["seq"] for s in segments] == [1, 2, 3]
    # Canonical artifacts are still produced by the process, unchanged.
    assert os.path.exists(result.raw_json_path)
