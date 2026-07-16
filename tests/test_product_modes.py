"""
v1.0 product modes + layered transcript wiring, exercised through the REAL
JobController pipeline with the mock ffmpeg/whisper fixtures (same harness as
test_integration).

Covers:
  * transcript_only  -> Detect Slides skipped; transcript exports written;
                        no slides.pdf / study-pack.html; normalized layer produced.
  * slides_only      -> Extract Audio + Transcribe skipped; slides.pdf written;
                        no transcript exports.
  * study_pack default is already covered by test_integration.
"""
import os
import pytest
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.controllers.job_controller import JobController
from lecturepack.constants import (
    STAGE_DETECT_SLIDES, STAGE_EXTRACT_AUDIO, STAGE_TRANSCRIBE, STAGE_ALIGN,
    PRODUCT_MODE_TRANSCRIPT_ONLY, PRODUCT_MODE_SLIDES_ONLY,
)

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


def _run(controller, qtbot):
    with qtbot.waitSignal(controller.pipeline_completed, timeout=60000):
        controller.run_pipeline()


def test_transcript_only_mode(qtbot, tmp_path):
    data_dir = tmp_path / "data"
    controller = _make_controller(data_dir)
    job = Job(str(data_dir), video_path=VIDEO)
    job.settings["product_mode"] = PRODUCT_MODE_TRANSCRIPT_ONLY
    job.save()
    controller.set_job(job)

    _run(controller, qtbot)

    # Detect Slides was skipped but still marked completed by the state machine.
    assert job.get_stage_status(STAGE_DETECT_SLIDES) == "completed"
    assert job.get_stage_status(STAGE_TRANSCRIBE) == "completed"

    transcript_dir = job.paths["transcript"]
    # Layered transcript wiring produced real artifacts from the raw whisper JSON.
    assert os.path.exists(os.path.join(transcript_dir, "normalized.json")), "normalized.json missing"
    assert os.path.exists(os.path.join(transcript_dir, "context_candidates.json")), "context_candidates.json missing"

    exports_dir = job.paths["exports"]
    assert os.path.exists(os.path.join(exports_dir, "transcript.txt"))
    assert os.path.exists(os.path.join(exports_dir, "transcript.srt"))
    assert os.path.exists(os.path.join(exports_dir, "transcript.normalized.txt"))
    # No slide artifacts in transcript-only mode.
    assert not os.path.exists(os.path.join(exports_dir, "slides.pdf")), "slides.pdf should not exist in transcript_only"
    assert not os.path.exists(os.path.join(exports_dir, "study-pack.html")), "study-pack.html should not exist in transcript_only"


def test_slides_only_mode(qtbot, tmp_path):
    data_dir = tmp_path / "data"
    controller = _make_controller(data_dir)
    job = Job(str(data_dir), video_path=VIDEO)
    job.settings["product_mode"] = PRODUCT_MODE_SLIDES_ONLY
    job.save()
    controller.set_job(job)

    _run(controller, qtbot)

    # Audio + transcription skipped, detection ran.
    assert job.get_stage_status(STAGE_EXTRACT_AUDIO) == "completed"
    assert job.get_stage_status(STAGE_TRANSCRIBE) == "completed"
    assert job.get_stage_status(STAGE_DETECT_SLIDES) == "completed"

    exports_dir = job.paths["exports"]
    assert os.path.exists(os.path.join(exports_dir, "slides.pdf")), "slides.pdf missing in slides_only"
    # No transcript artifacts.
    assert not os.path.exists(os.path.join(exports_dir, "transcript.txt")), "transcript.txt should not exist in slides_only"
    assert not os.path.exists(os.path.join(exports_dir, "study-pack.html")), "study-pack.html should not exist in slides_only"


def test_normalized_matches_service(qtbot, tmp_path):
    """The pipeline's normalized.json must equal a direct transcript_service run
    over the same raw.json (proves it is the real layer, not an ad-hoc copy)."""
    import json
    from lecturepack.services import transcript_service as ts

    data_dir = tmp_path / "data"
    controller = _make_controller(data_dir)
    job = Job(str(data_dir), video_path=VIDEO)
    job.settings["product_mode"] = PRODUCT_MODE_TRANSCRIPT_ONLY
    job.save()
    controller.set_job(job)
    _run(controller, qtbot)

    transcript_dir = job.paths["transcript"]
    with open(os.path.join(transcript_dir, "raw.json"), encoding="utf-8") as f:
        raw_data = json.load(f)
    with open(os.path.join(transcript_dir, "normalized.json"), encoding="utf-8") as f:
        produced = json.load(f)

    raw = ts.parse_raw_whisper_json(raw_data)
    expected = ts.normalize_transcript(raw).to_dict()
    assert produced["segments"] == expected["segments"]
    # raw content hash recorded and stable
    assert produced["raw_content_hash"] == raw.content_hash()
