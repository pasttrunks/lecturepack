"""Controller integration tests for beta.3 cooperative pause/resume and
stage-specific retry, driven by the mock ffmpeg/whisper subprocess harness."""

import os

from lecturepack.constants import (
    STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE, STAGE_DETECT_SLIDES, STAGES,
)
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
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


def test_pause_at_stage_boundary_then_resume(qtbot, tmp_path):
    controller = _make_controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)

    states = []
    controller.pause_state_changed.connect(states.append)

    # Request a pause as soon as audio extraction begins.
    paused_once = {"done": False}
    def on_started(stage):
        if stage == STAGE_EXTRACT_AUDIO and not paused_once["done"]:
            paused_once["done"] = True
            controller.request_pause()
    controller.stage_started.connect(on_started)

    controller.run_pipeline()
    qtbot.waitUntil(lambda: "paused" in states, timeout=30000)

    # We paused before advancing: downstream stages never ran.
    assert "pause_requested" in states and "paused" in states
    assert job.get_stage_status(STAGE_TRANSCRIBE) == "pending"
    assert job.get_stage_status(STAGE_DETECT_SLIDES) == "pending"

    # Resume runs to completion from the checkpoint. (EXPORT is triggered
    # post-review, not during the main pipeline, so it stays pending.)
    from lecturepack.constants import STAGE_EXPORT
    with qtbot.waitSignal(controller.pipeline_completed, timeout=60000):
        controller.resume()
    for stage in STAGES:
        if stage == STAGE_EXPORT:
            continue
        st = job.get_stage_status(stage)
        assert st == "completed", f"{stage} = {st}"


def test_resume_after_restart_continues(qtbot, tmp_path):
    data = str(tmp_path / "data")
    controller = _make_controller(tmp_path / "data")
    job = Job(data, video_path=VIDEO)
    jid = job.job_id
    controller.set_job(job)

    states = []
    controller.pause_state_changed.connect(states.append)
    done = {"v": False}
    def on_started(stage):
        if stage == STAGE_EXTRACT_AUDIO and not done["v"]:
            done["v"] = True
            controller.request_pause()
    controller.stage_started.connect(on_started)
    controller.run_pipeline()
    qtbot.waitUntil(lambda: "paused" in states, timeout=30000)

    # Simulate an app restart: brand-new controller + reloaded job from disk.
    controller2 = _make_controller(tmp_path / "data")
    job2 = Job(data, job_id=jid)
    controller2.set_job(job2)
    with qtbot.waitSignal(controller2.pipeline_completed, timeout=60000):
        controller2.resume()
    assert job2.get_stage_status(STAGE_TRANSCRIBE) == "completed"


def test_retry_failed_stage_preserves_completed(qtbot, tmp_path):
    controller = _make_controller(tmp_path / "data")
    job = Job(str(tmp_path / "data"), video_path=VIDEO)
    controller.set_job(job)

    # First, a full clean run.
    with qtbot.waitSignal(controller.pipeline_completed, timeout=60000):
        controller.run_pipeline()
    assert job.get_stage_status(STAGE_TRANSCRIBE) == "completed"

    # Simulate a downstream stage having failed; retry only it.
    job.set_stage_status(STAGE_DETECT_SLIDES, "failed")
    cached = []
    controller.stage_cached.connect(cached.append)

    with qtbot.waitSignal(controller.pipeline_completed, timeout=60000):
        controller.retry_stage(STAGE_DETECT_SLIDES)

    # Completed upstream transcription was preserved (served from cache),
    # while the retried stage re-ran and finished.
    assert STAGE_TRANSCRIBE in cached
    assert job.get_stage_status(STAGE_DETECT_SLIDES) == "completed"
