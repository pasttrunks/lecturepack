"""
Phase 7/8 tests: concurrent pipeline scheduler, stage cache keys, and the
transcription-engine registry (Vulkan detection + CPU fallback policy).
Uses the same mock ffmpeg/whisper harness as test_integration.
"""
import os
import time

import pytest

from lecturepack.constants import (
    STAGE_DETECT_SLIDES, STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE,
)
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.transcription_engines import (
    ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN, EngineRegistry,
)
from lecturepack.models.job import Job

MOCK_WHISPER = os.path.abspath("tests/fixtures/mock_whisper.py")
MOCK_FFMPEG = os.path.abspath("tests/fixtures/mock_ffmpeg.py")
MOCK_FFPROBE = os.path.abspath("tests/fixtures/mock_ffprobe.py")
VIDEO = os.path.abspath("tests/fixtures/synthetic_lecture.mp4")


def _make_controller(data_dir):
    config = ConfigManager(str(data_dir))
    config.set("whisper_exe", MOCK_WHISPER)
    config.set("whisper_model", "ggml-base.bin")
    controller = JobController(config)
    controller.ffmpeg_wrapper.ffmpeg_path = MOCK_FFMPEG
    controller.ffmpeg_wrapper.ffprobe_path = MOCK_FFPROBE
    return controller


def _run(controller, qtbot, timeout=120000):
    with qtbot.waitSignal(controller.pipeline_completed, timeout=timeout):
        controller.run_pipeline()


# --------------------------------------------------------------------------- #
# concurrent scheduler
# --------------------------------------------------------------------------- #

def test_transcribe_and_detect_run_concurrently(qtbot, tmp_path):
    controller = _make_controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)

    events = []
    controller.stage_started.connect(lambda s: events.append(("start", s, time.time())))
    controller.stage_finished.connect(lambda s, ok, e: events.append(("finish", s, time.time())))
    _run(controller, qtbot)

    starts = {s: t for kind, s, t in events if kind == "start"}
    finishes = {s: t for kind, s, t in events if kind == "finish"}
    assert STAGE_TRANSCRIBE in starts and STAGE_DETECT_SLIDES in starts
    # Both branches must start before EITHER finishes (true overlap).
    first_finish = min(finishes[STAGE_TRANSCRIBE], finishes[STAGE_DETECT_SLIDES])
    assert starts[STAGE_TRANSCRIBE] <= first_finish
    assert starts[STAGE_DETECT_SLIDES] <= first_finish
    assert job.get_stage_status(STAGE_TRANSCRIBE) == "completed"
    assert job.get_stage_status(STAGE_DETECT_SLIDES) == "completed"
    # Alignment products exist (transcript + candidates converged correctly)
    assert os.path.exists(os.path.join(job.paths["root"], "candidates.json"))
    assert os.path.exists(os.path.join(job.paths["transcript"], "raw.json"))


def test_parallel_disabled_runs_sequentially(qtbot, tmp_path):
    controller = _make_controller(tmp_path / "data")
    controller.config_manager.set("parallel_pipeline", False)
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)

    events = []
    controller.stage_started.connect(lambda s: events.append(("start", s, time.time())))
    controller.stage_finished.connect(lambda s, ok, e: events.append(("finish", s, time.time())))
    _run(controller, qtbot)

    starts = {s: t for kind, s, t in events if kind == "start"}
    finishes = {s: t for kind, s, t in events if kind == "finish"}
    assert starts[STAGE_DETECT_SLIDES] >= finishes[STAGE_TRANSCRIBE] - 0.05, \
        "with parallel disabled, detection must start after transcription finishes"


def test_cancellation_stops_both_branches(qtbot, tmp_path):
    controller = _make_controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)

    def cancel_when_parallel(stage):
        if stage == STAGE_DETECT_SLIDES:
            # Both branches have started; cancel everything.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, controller.cancel)

    controller.stage_started.connect(cancel_when_parallel)
    controller.run_pipeline()
    qtbot.wait(1500)
    assert job.get_stage_status(STAGE_TRANSCRIBE) in ("cancelled", "completed")
    assert job.get_stage_status(STAGE_DETECT_SLIDES) in ("cancelled", "completed")
    # no zombie: the slide worker thread must be stopped
    if controller.slide_worker is not None:
        controller.slide_worker.wait(5000)
        assert controller.slide_worker.isFinished()


# --------------------------------------------------------------------------- #
# stage cache keys
# --------------------------------------------------------------------------- #

def test_stage_cache_reused_when_settings_unchanged(qtbot, tmp_path):
    controller = _make_controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)
    _run(controller, qtbot)

    raw = os.path.join(job.paths["transcript"], "raw.json")
    sig_before = (os.path.getsize(raw), os.path.getmtime(raw))

    cached = []
    controller.stage_cached.connect(lambda s: cached.append(s))
    _run(controller, qtbot)
    assert STAGE_TRANSCRIBE in cached and STAGE_DETECT_SLIDES in cached
    sig_after = (os.path.getsize(raw), os.path.getmtime(raw))
    assert sig_before == sig_after, "unchanged settings must not rerun transcription"


def test_stage_cache_invalidated_by_setting_change(qtbot, tmp_path):
    controller = _make_controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)
    _run(controller, qtbot)

    raw = os.path.join(job.paths["transcript"], "raw.json")
    mtime_before = os.path.getmtime(raw)

    # Changing the glossary is part of the transcription cache key.
    job.settings["whisper"]["glossary"] = "Tutankhamun, Giza"
    job.save()
    time.sleep(0.05)
    _run(controller, qtbot)
    assert os.path.getmtime(raw) > mtime_before, \
        "glossary change must invalidate and rerun transcription"

    # ...but the detection cache key is unaffected by the glossary.
    fp = controller._stage_fingerprint(STAGE_DETECT_SLIDES)
    job.settings["whisper"]["glossary"] = "Different"
    assert controller._stage_fingerprint(STAGE_DETECT_SLIDES) == fp
    # crop change invalidates detection
    job.settings["slide_detection"]["crop_region"] = {"x": 0.1, "y": 0.0,
                                                      "width": 0.9, "height": 1.0}
    assert controller._stage_fingerprint(STAGE_DETECT_SLIDES) != fp


def test_legacy_job_without_fingerprints_is_trusted(qtbot, tmp_path):
    """Old jobs (pre-v1.1, no stage_fingerprints.json) must not rerun."""
    controller = _make_controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)
    _run(controller, qtbot)
    os.remove(os.path.join(job.paths["root"], "stage_fingerprints.json"))
    cached = []
    controller.stage_cached.connect(lambda s: cached.append(s))
    _run(controller, qtbot)
    assert STAGE_TRANSCRIBE in cached


# --------------------------------------------------------------------------- #
# engine registry
# --------------------------------------------------------------------------- #

def _fake_exe(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"MZ fake")
    return path


def test_engine_registry_cpu_only(tmp_path, monkeypatch):
    # isolate from the developer machine's real bin/vulkan build
    monkeypatch.setattr(
        "lecturepack.infrastructure.transcription_engines._app_root",
        lambda: str(tmp_path))
    config = ConfigManager(str(tmp_path / "data"))
    cpu = _fake_exe(str(tmp_path / "bin" / "whisper-cli.exe"))
    config.set("whisper_exe", cpu)
    reg = EngineRegistry(config)
    engines = reg.detect_engines()
    assert engines[ENGINE_CPU].available
    assert not engines[ENGINE_VULKAN].available
    resolved = reg.resolve(ENGINE_AUTO)
    assert resolved.key == ENGINE_CPU
    # Vulkan explicitly requested but unavailable -> degrade to CPU with reason
    resolved = reg.resolve(ENGINE_VULKAN)
    assert resolved.key == ENGINE_CPU
    assert "unavailable" in resolved.reason.lower() or "Vulkan requested" in resolved.reason


def test_engine_registry_vulkan_available_but_not_benchmarked(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lecturepack.infrastructure.transcription_engines._app_root",
        lambda: str(tmp_path))
    config = ConfigManager(str(tmp_path / "data"))
    cpu = _fake_exe(str(tmp_path / "bin" / "whisper-cli.exe"))
    vk = _fake_exe(str(tmp_path / "bin" / "vulkan" / "whisper-cli.exe"))
    _fake_exe(str(tmp_path / "bin" / "vulkan" / "ggml-vulkan.dll"))
    config.set("whisper_exe", cpu)
    config.set("whisper_vulkan_exe", vk)
    reg = EngineRegistry(config)
    monkeypatch.setattr(
        "lecturepack.infrastructure.transcription_engines.vulkan_runtime_present",
        lambda: True)
    engines = reg.detect_engines()
    assert engines[ENGINE_VULKAN].available
    # auto must NOT pick Vulkan until it is benchmarked faster on this machine
    resolved = reg.resolve(ENGINE_AUTO)
    assert resolved.key == ENGINE_CPU
    config.set("vulkan_benchmark_ok", True)
    resolved = reg.resolve(ENGINE_AUTO)
    assert resolved.key == ENGINE_VULKAN
    # explicit selection works
    assert reg.resolve(ENGINE_VULKAN).key == ENGINE_VULKAN
    assert reg.resolve(ENGINE_CPU).key == ENGINE_CPU


def test_engine_registry_vulkan_missing_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lecturepack.infrastructure.transcription_engines._app_root",
        lambda: str(tmp_path))
    config = ConfigManager(str(tmp_path / "data"))
    vk = _fake_exe(str(tmp_path / "bin" / "vulkan" / "whisper-cli.exe"))
    _fake_exe(str(tmp_path / "bin" / "vulkan" / "ggml-vulkan.dll"))
    config.set("whisper_vulkan_exe", vk)
    config.set("vulkan_benchmark_ok", True)
    monkeypatch.setattr(
        "lecturepack.infrastructure.transcription_engines.vulkan_runtime_present",
        lambda: False)
    reg = EngineRegistry(config)
    engines = reg.detect_engines()
    assert not engines[ENGINE_VULKAN].available
    assert "runtime" in engines[ENGINE_VULKAN].reason.lower()
    assert reg.resolve(ENGINE_AUTO).key == ENGINE_CPU
