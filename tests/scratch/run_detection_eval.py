"""
Detector ground-truth evaluation harness.

Runs the REAL slide detector (lecturepack.infrastructure.cv_engine) over a short
fixture video and scores its candidates against human/construction-derived
ground truth using lecturepack.services.detection_eval.

Requires OpenCV + numpy + scikit-image (i.e. the app's runtime deps), so this is
intended to run on the developer/Windows machine, not in a dependency-free CI
sandbox. The metric logic itself is covered by tests/test_detection_eval.py.

Usage:
    python tests/scratch/run_detection_eval.py \
        --video tests/fixtures/synthetic_lecture.mp4 \
        --ground-truth tests/fixtures/ground_truth/synthetic_lecture.json \
        --preset balanced
"""

import os
import sys
import json
import argparse
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lecturepack.constants import PRESETS
from lecturepack.services import detection_eval as de


def run_detector(video_path, preset_key, crop=None, ignore=None):
    """Run SlideDetectorWorker synchronously and return candidate timestamps (s).

    Imported lazily so this file can be inspected without OpenCV/Qt present.
    """
    from lecturepack.infrastructure.cv_engine import SlideDetectorWorker

    preset = PRESETS.get(preset_key, PRESETS["balanced"])
    with tempfile.TemporaryDirectory() as tmp:
        job_paths = {"candidates": os.path.join(tmp, "candidates")}
        # Real signature: (video_path, crop_region, ignore_masks,
        #                  preset_settings, job_paths, start_time=0.0, end_time=None)
        worker = SlideDetectorWorker(
            video_path,
            crop or {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
            ignore or [],
            preset,
            job_paths,
        )

        captured = {"cands": []}

        def _done(ok, err, cands):
            captured["cands"] = cands or []

        # SlideDetectorWorker is a QThread; run() executes the pipeline directly.
        try:
            worker.finished.connect(_done)
        except Exception:
            pass
        worker.run()
        cands = captured["cands"] or getattr(worker, "last_candidates", [])
        return [c.get("timestamp_seconds", 0.0) for c in cands], cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="tests/fixtures/synthetic_lecture.mp4")
    ap.add_argument("--ground-truth",
                    default="tests/fixtures/ground_truth/synthetic_lecture.json")
    ap.add_argument("--preset", default="balanced")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    gt = de.GroundTruth.load(args.ground_truth)
    seconds, raw = run_detector(args.video, args.preset)
    result = de.evaluate(seconds, gt)

    print(result.summary())
    print("  matched: ", [(m["event"], round(m["candidate_sec"], 1)) for m in result.matched])
    print("  missed:  ", result.missed)
    print("  spurious:", [round(s, 1) for s in result.spurious])
    print("  distractor hits:", result.distractor_hits)
    print("  targets: ", de.meets_targets(result))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"result": result.to_dict(),
                       "targets": de.meets_targets(result),
                       "raw_candidates": raw}, f, indent=2)
        print("wrote", args.json_out)


if __name__ == "__main__":
    main()
