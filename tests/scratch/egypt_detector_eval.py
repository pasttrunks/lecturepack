"""
Real-material detector evaluation helper.

Runs the REAL cv_engine detector (balanced) over a lecture excerpt, saves the
candidate frames, and builds annotated contact sheets of both the detector's
candidates and a dense uniform sampling of the excerpt -- so a human (or the
agent, by reading the sheets) can visually label ground-truth slide states
independently of the detector output, then score with detection_eval.

Usage:
    python tests/scratch/egypt_detector_eval.py <video> <outdir> [preset] [sample_every_sec]
"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import cv2
import numpy as np
from lecturepack.constants import PRESETS


def annotate(frame, label):
    f = frame.copy()
    cv2.rectangle(f, (0, 0), (f.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(f, label, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return f


def contact_sheet(frames_labeled, cols=5, thumb_w=320):
    thumbs = []
    for frame, label in frames_labeled:
        h, w = frame.shape[:2]
        tw = thumb_w
        th = int(h * tw / w)
        t = cv2.resize(frame, (tw, th))
        t = annotate(t, label)
        thumbs.append(t)
    if not thumbs:
        return None
    th, tw = thumbs[0].shape[:2]
    rows = (len(thumbs) + cols - 1) // cols
    sheet = np.full((rows * th, cols * tw, 3), 40, dtype=np.uint8)
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        if t.shape[:2] != (th, tw):
            t = cv2.resize(t, (tw, th))
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
    return sheet


def fmt(t):
    m, s = divmod(int(t), 60)
    return f"{m:d}:{s:02d}"


def run(video, outdir, preset_key="balanced", sample_every=3.0, offset=0.0):
    os.makedirs(outdir, exist_ok=True)
    from lecturepack.infrastructure.cv_engine import SlideDetectorWorker

    # 1) Run the real detector.
    cand_dir = os.path.join(outdir, "candidates")
    os.makedirs(cand_dir, exist_ok=True)
    worker = SlideDetectorWorker(video, {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                                 [], PRESETS[preset_key], {"candidates": cand_dir})
    captured = {}
    worker.finished.connect(lambda ok, err, c: captured.update(ok=ok, err=err, cands=c or []))
    worker.run()
    cands = captured.get("cands", [])
    cand_times = [c["timestamp_seconds"] for c in cands]
    with open(os.path.join(outdir, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(cands, f, indent=2)

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps

    # 2) Candidate contact sheet (label = wall-clock time within full lecture).
    cand_frames = []
    for c in cands:
        t = c["timestamp_seconds"]
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ret, fr = cap.read()
        if ret:
            cand_frames.append((fr, f"CAND {fmt(t + offset)} ({c.get('detector_path','')[:4]})"))
    sheet = contact_sheet(cand_frames, cols=5)
    if sheet is not None:
        cv2.imwrite(os.path.join(outdir, "sheet_candidates.png"), sheet)

    # 3) Dense uniform sampling contact sheets (for independent ground truth).
    sample_times = list(np.arange(0.0, duration, sample_every))
    per_sheet = 30
    sheet_idx = 0
    for i in range(0, len(sample_times), per_sheet):
        batch = sample_times[i:i + per_sheet]
        frames = []
        for t in batch:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, fr = cap.read()
            if ret:
                frames.append((fr, fmt(t + offset)))
        s = contact_sheet(frames, cols=6, thumb_w=240)
        if s is not None:
            cv2.imwrite(os.path.join(outdir, f"sheet_dense_{sheet_idx:02d}.png"), s)
            sheet_idx += 1
    cap.release()

    summary = {
        "video": video, "preset": preset_key, "duration_sec": round(duration, 1),
        "candidate_count": len(cands),
        "candidate_times_sec": [round(t, 1) for t in cand_times],
        "candidate_times_clock": [fmt(t + offset) for t in cand_times],
        "dense_sheets": sheet_idx, "sample_every": sample_every, "offset": offset,
    }
    with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    video = sys.argv[1]
    outdir = sys.argv[2]
    preset = sys.argv[3] if len(sys.argv) > 3 else "balanced"
    every = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0
    offset = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
    run(video, outdir, preset, every, offset)
