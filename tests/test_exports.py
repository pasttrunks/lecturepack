import os
import json
import pytest
from lecturepack.models.job import Job
from lecturepack.services.export_service import ExportService
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.constants import STAGE_TRANSCRIBE, STAGE_EXPORT

def test_exports(tmp_path):
    data_dir = tmp_path / "data"
    video_path = tmp_path / "lecture.mp4"
    video_path.touch()

    # 1. Create and setup mock job state
    job = Job(str(data_dir), video_path=str(video_path))
    
    # Create fake candidate image
    import cv2
    import numpy as np
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    img_filename = "slide_0_0.png"
    img_path = os.path.join(job.paths["candidates"], img_filename)
    cv2.imwrite(img_path, dummy_img)

    # Write mock candidates.json
    candidates = [{
        "frame_number": 0,
        "timestamp_seconds": 0.0,
        "timestamp_formatted": "00:00:00.000",
        "decision": "accepted",
        "image_filename": img_filename
    }]
    FileManager.write_json_atomic(os.path.join(job.paths["root"], "candidates.json"), candidates)

    # Write mock raw transcript JSON
    raw_transcript = {
        "result": {
            "transcription": [
                {
                    "offsets": { "from": 0, "to": 5000 },
                    "text": "Hello world"
                }
            ]
        }
    }
    transcript_dir = job.paths["transcript"]
    os.makedirs(transcript_dir, exist_ok=True)
    FileManager.write_json_atomic(os.path.join(transcript_dir, "raw.json"), raw_transcript)

    # Set stages completed up to Align
    job.set_stage_status(STAGE_TRANSCRIBE, "completed")
    job.save()

    # 2. Run Export Service
    service = ExportService(job)
    service.align_and_export()

    # 3. Assertions
    exports_dir = job.paths["exports"]
    assert os.path.exists(os.path.join(exports_dir, "slides.pdf")), "slides.pdf not created"
    assert os.path.exists(os.path.join(exports_dir, "study-pack.html")), "study-pack.html not created"
    assert os.path.exists(os.path.join(exports_dir, "transcript.srt")), "transcript.srt not created"
    assert os.path.exists(os.path.join(exports_dir, "transcript.txt")), "transcript.txt not created"
    assert os.path.exists(os.path.join(exports_dir, "transcript.json")), "transcript.json not created"

    # Verify slides.pdf starts with %PDF header
    with open(os.path.join(exports_dir, "slides.pdf"), "rb") as f:
        header = f.read(4)
        assert header == b"%PDF", "Invalid PDF format"

    # Verify study-pack.html contains base64 slide image
    with open(os.path.join(exports_dir, "study-pack.html"), "r", encoding="utf-8") as f:
        html = f.read()
        assert "data:image/png;base64," in html, "HTML pack did not embed base64 image"
        assert "Hello world" in html, "HTML pack did not include transcript text"

    # Verify re-exporting does not touch transcription stage status
    assert job.get_stage_status(STAGE_TRANSCRIBE) == "completed"
