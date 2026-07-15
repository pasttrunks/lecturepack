import os
import sys
import pytest
from PySide6.QtCore import QEventLoop, QTimer
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.controllers.job_controller import JobController
from lecturepack.constants import STAGES, STAGE_EXPORT

def test_integration(qtbot, tmp_path):
    print("\n--- Starting test_integration ---")
    
    # Setup test configuration
    data_dir = tmp_path / "data"
    config = ConfigManager(str(data_dir))
    
    # Configure mock executables
    mock_whisper = os.path.abspath("tests/fixtures/mock_whisper.py")
    mock_ffmpeg = os.path.abspath("tests/fixtures/mock_ffmpeg.py")
    mock_ffprobe = os.path.abspath("tests/fixtures/mock_ffprobe.py")
    
    assert os.path.exists(mock_whisper)
    assert os.path.exists(mock_ffmpeg)
    assert os.path.exists(mock_ffprobe)

    config.set("whisper_exe", mock_whisper)
    config.set("whisper_model", "ggml-base.bin")
    
    # Override wrapper paths
    controller = JobController(config)
    controller.ffmpeg_wrapper.ffmpeg_path = mock_ffmpeg
    controller.ffmpeg_wrapper.ffprobe_path = mock_ffprobe

    # Hook up live console logging for diagnostics
    controller.stage_started.connect(lambda stage: print(f"\n>> STAGE STARTED: {stage}"))
    controller.stage_log.connect(lambda stage, msg: print(f"[{stage}] {msg}", end=""))
    controller.stage_progress.connect(lambda stage, p: print(f"[{stage}] Progress: {p}%"))
    controller.stage_finished.connect(lambda stage, success, err: print(f">> STAGE FINISHED: {stage} (Success={success}, Err={err})"))

    video_path = os.path.abspath("tests/fixtures/synthetic_lecture.mp4")
    assert os.path.exists(video_path)

    # Initialize Job
    job = Job(str(data_dir), video_path=video_path)
    controller.set_job(job)

    # Wait for the pipeline_completed signal with 20 seconds timeout using qtbot
    print("Running pipeline...")
    with qtbot.waitSignal(controller.pipeline_completed, timeout=20000):
        controller.run_pipeline()
        
    print("Pipeline completed successfully.")

    # Verify stages up to Align are completed
    for stage in STAGES:
        if stage != STAGE_EXPORT:
            assert job.get_stage_status(stage) == "completed", f"Stage {stage} was not completed"

    # Now verify that trigger export works
    print("Running export...")
    # Wait for stage_finished signal for STAGE_EXPORT
    def check_export_finished(stage, success, err):
        return stage == STAGE_EXPORT

    with qtbot.waitSignal(controller.stage_finished, timeout=15000, check_params_cb=check_export_finished):
        controller.export_now()
        
    print("Export completed successfully.")
    assert job.get_stage_status(STAGE_EXPORT) == "completed"

    # Check that output files were created
    exports_dir = job.paths["exports"]
    assert os.path.exists(os.path.join(exports_dir, "slides.pdf"))
    assert os.path.exists(os.path.join(exports_dir, "study-pack.html"))
    assert os.path.exists(os.path.join(exports_dir, "transcript.srt"))
    print("All exports verified. test_integration finished.")
