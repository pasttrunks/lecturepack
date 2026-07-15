import os
from lecturepack.models.job import Job
from lecturepack.constants import STAGE_INSPECT, STAGE_EXTRACT_AUDIO

def test_job_persistence(tmp_path):
    # Test path with spaces
    data_dir = tmp_path / "Lecture Pack Data"
    video_path = tmp_path / "test lecture video.mp4"
    
    # Touch a dummy video file
    video_path.touch()

    # 1. Create a new job
    job = Job(str(data_dir), video_path=str(video_path))
    job_id = job.job_id
    
    # Check that directories were created
    assert os.path.exists(job.paths["root"])
    assert "Lecture Pack Data" in job.paths["root"]
    
    # Save settings and stage states
    job.settings["preset"] = "whiteboard_lecture"
    job.set_stage_status(STAGE_INSPECT, "completed")
    job.save()

    # Check files exist
    assert os.path.exists(job.manifest_path)
    assert os.path.exists(job.settings_path)
    assert os.path.exists(job.state_path)

    # 2. Reopen the job
    reopened_job = Job(str(data_dir), job_id=job_id)
    assert reopened_job.job_id == job_id
    assert reopened_job.settings.get("preset") == "whiteboard_lecture"
    assert reopened_job.get_stage_status(STAGE_INSPECT) == "completed"
    assert reopened_job.get_stage_status(STAGE_EXTRACT_AUDIO) == "pending"

    # Test completed stage caching behavior
    # Reopened job should still contain the "completed" inspect stage status
    assert reopened_job.state["stages"][STAGE_INSPECT]["status"] == "completed"
