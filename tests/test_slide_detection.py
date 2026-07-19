import os
import shutil
import pytest
from lecturepack.constants import PRESETS
from lecturepack.infrastructure.cv_engine import SlideDetectorWorker
from lecturepack.infrastructure.file_manager import FileManager

def test_slide_detection(tmp_path):
    video_path = os.path.abspath("tests/fixtures/synthetic_lecture.mp4")
    assert os.path.exists(video_path), "Synthetic video fixture missing"

    # Create temp job dirs
    job_paths = FileManager.init_job_dir(str(tmp_path), "test_job_detection")

    # Define crop and ignore masks
    # Webcam: (500, 380) to (620, 460) -> normalized x=500/640=0.78, y=380/480=0.79, w=120/640=0.19, h=80/480=0.17
    # Captions: (0, 430) to (640, 480) -> normalized x=0.0, y=430/480=0.89, w=1.0, h=50/480=0.11
    crop_region = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    ignore_masks = [
        {"x": 0.78, "y": 0.79, "width": 0.19, "height": 0.17},
        {"x": 0.0, "y": 0.89, "width": 1.0, "height": 0.11}
    ]

    preset = PRESETS["balanced"].copy()
    
    # Instantiate SlideDetectorWorker
    worker = SlideDetectorWorker(video_path, crop_region, ignore_masks, preset, job_paths)
    
    # Store output results
    results = []
    def on_finished(success, error, candidates):
        results.append((success, error, candidates))
        
    worker.finished.connect(on_finished)

    # Run synchronously
    worker.run()

    assert len(results) == 1
    success, error, candidates = results[0]
    
    assert success, f"Slide detector failed with error: {error}"
    assert len(candidates) > 0, "No slides detected at all"

    # Validate timestamps and types
    timestamps = [c["timestamp_seconds"] for c in candidates]
    print(f"DETECTED TIMESTAMPS: {timestamps}")
    
    # Check that we have a slide for Slide 1 (approx 0-2s)
    assert any(0.0 <= ts < 3.0 for ts in timestamps), "Slide 1 (Title) not detected"
    
    # Check Slide 2 (approx 5-7s)
    assert any(5.0 <= ts < 8.0 for ts in timestamps), "Slide 2 not detected"
    
    # Check that there are NO slide changes in the pointer motion range (15-20s)
    # The pointer is at 15-20s. Let's make sure no candidate is born strictly within [16.0, 19.5]
    pointer_candidates = [ts for ts in timestamps if 16.0 <= ts <= 19.5]
    assert len(pointer_candidates) == 0, f"Pointer movement caused false positive slides at {pointer_candidates}"

    # Check Slide 3 (progressive build at 20s) is preserved
    assert any(20.0 <= ts < 24.0 for ts in timestamps), "Progressive build at 20s not detected"

    # Check Slide 4 (diagram at 25s)
    assert any(25.0 <= ts < 29.0 for ts in timestamps), "Slide 4 (diagram) not detected"

    # Check that fake webcam noise (40-45s) and captions (45-50s) did NOT trigger slide changes
    noise_candidates = [ts for ts in timestamps if 41.0 <= ts <= 44.5]
    caption_candidates = [ts for ts in timestamps if 46.0 <= ts <= 49.5]
    assert len(noise_candidates) == 0, f"Webcam noise caused false positive slides at {noise_candidates}"
    assert len(caption_candidates) == 0, f"Caption updates caused false positive slides at {caption_candidates}"

    # Check Slide 6 (whiteboard digital ink strokes at 50s)
    assert any(50.0 <= ts < 54.0 for ts in timestamps), "Whiteboard ink strokes not detected"

    # Check that Slide 2 repeated at 55s remains available as a later occurrence with its later timestamp!
    repeated_candidates = [ts for ts in timestamps if 55.0 <= ts < 60.0]
    assert len(repeated_candidates) > 0, "Repeated slide occurrence at 55s was globally removed"

    # Check Slide 7 (final slide at 60s)
    assert any(60.0 <= ts <= 65.0 for ts in timestamps), "Final slide not detected"
