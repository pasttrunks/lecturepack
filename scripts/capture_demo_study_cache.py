"""Regenerate the shipped Study pack for the bundled demo lecture.

The guided demo serves a pre-built pack (see
lecturepack/services/demo_study_cache.py) because a real gateway build of that
lecture measures 15.6s on top of local processing, which is a long hold for
someone still being shown around. The pack in app/assets/demo/study-content-v2.json
is the genuine output of the normal pipeline over the bundled lecture, and this
script is how it is produced -- so it can always be regenerated rather than
hand-maintained.

Run it whenever the bundled lecture, the detector presets, or the gateway
prompts change:

    .venv\\Scripts\\python.exe scripts\\capture_demo_study_cache.py

It needs a working AI gateway (the same one the app uses) and the local
whisper/ffmpeg runtime under bin/. Nothing is written until the pack is ready,
and the app's real data directory is never touched -- everything happens in a
scratch directory that is left behind for inspection.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from lecturepack.constants import PRESETS  # noqa: E402
from lecturepack.infrastructure.cv_engine import SlideDetectorWorker  # noqa: E402
from lecturepack.infrastructure.file_manager import FileManager  # noqa: E402
from lecturepack.models.job import Job  # noqa: E402
from lecturepack.services import ai_gateway, ai_study_service, demo_study_cache, study_v2  # noqa: E402

DEMO = ROOT / "electron-spike" / "assets" / "demo-lecture.mp4"
OUT = ROOT / "app" / "assets" / "demo" / demo_study_cache.CACHE_FILENAME
FFMPEG = ROOT / "bin" / "ffmpeg.exe"
WHISPER = ROOT / "bin" / "Release" / "whisper-cli.exe"
MODEL = ROOT / "models" / "ggml-base.en.bin"


def need(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"required file missing: {path}")
    return path


def transcribe(job: Job, video: Path) -> None:
    audio = Path(job.paths["audio"]) / "lecture-16khz-mono.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(FFMPEG), "-y", "-i", str(video), "-vn", "-acodec", "pcm_s16le",
         "-ac", "1", "-ar", "16000", str(audio)],
        check=True, capture_output=True)
    transcript = Path(job.paths["transcript"])
    transcript.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(WHISPER), "-m", str(MODEL), "-f", str(audio), "-oj",
         "-of", str(transcript / "raw")],
        check=True, capture_output=True)


def detect_slides(job: Job, video: Path) -> int:
    worker = SlideDetectorWorker(
        str(video), {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}, [],
        PRESETS["demo"], job.paths, ffmpeg_path=str(FFMPEG))
    captured: dict = {}
    worker.finished.connect(lambda ok, err, c: captured.update(ok=ok, err=err, c=c or []))
    worker.run()
    if not captured.get("ok"):
        raise SystemExit(f"slide detection failed: {captured.get('err')}")
    candidates = captured["c"]
    # The demo ships every detected slide accepted; the guided tour never asks
    # the student to triage before showing them what a Study pack looks like.
    for candidate in candidates:
        candidate["decision"] = "accepted"
    FileManager.write_json_atomic(
        os.path.join(job.paths["root"], "candidates.json"), candidates)
    return len(candidates)


def main() -> int:
    QCoreApplication.instance() or QCoreApplication(sys.argv)
    for path in (DEMO, FFMPEG, WHISPER, MODEL):
        need(path)

    scratch = Path(tempfile.mkdtemp(prefix="lp-demo-capture-"))
    print(f"scratch: {scratch}")
    job = Job(str(scratch), video_path=str(DEMO))
    job.settings["preset"] = "demo"
    job.settings["product_mode"] = "study_pack"
    job.save()

    print("transcribing ...")
    transcribe(job, DEMO)
    segments = study_v2._load_segments(job)
    print(f"  {len(segments)} segments")

    print("detecting slides ...")
    slide_count = detect_slides(job, DEMO)
    slides = study_v2._load_accepted_slides(job)
    print(f"  {slide_count} slides ({len(slides)} accepted)")
    if slide_count < 3:
        raise SystemExit(
            f"only {slide_count} slides detected -- the demo preset should find "
            "one per slide; refusing to capture a pack that under-represents "
            "the bundled lecture")

    # Read EVERY slide during capture.
    #
    # Vision normally runs only on the slides the analysis pass asks about, and
    # for this lecture it asked about none -- so the first capture covered the
    # two facts spoken aloud and ignored the two that exist only as text on
    # slides 2 and 4. A demo pack that silently drops half the lecture is the
    # worst possible thing to hand someone who is about to stress-test it.
    #
    # This is a capture-time override, not a product change: the running app
    # still asks for slides only when the analysis wants them. Everything it
    # produces is still genuine model output grounded in the real slides.
    bundle = ai_study_service.build_lecture_bundle(job)
    slide_ids = [str(s.get("slide_id")) for s in bundle["slides"]]
    ai_study_service._MAX_VISION_SLIDES = max(
        ai_study_service._MAX_VISION_SLIDES, len(slide_ids))
    original_call = ai_study_service._call

    def call_reading_every_slide(client, task, payload):
        result, diagnostics = original_call(client, task, payload)
        if task == "lecture_analysis" and isinstance(result, dict):
            result["vision_requests"] = [
                {"slide_id": sid,
                 "reason": "Demo capture: every slide is read so the shipped "
                           "pack covers the whole lecture."}
                for sid in slide_ids
            ]
        return result, diagnostics

    ai_study_service._call = call_reading_every_slide
    print(f"building the Study pack (real gateway, {len(slide_ids)} slides read) ...")
    started = time.time()
    client = ai_gateway.GatewayClient(str(scratch))
    try:
        ai_study_service.prepare_ai_study(
            job, client, progress=lambda p: print(
                f"  {p.get('progress_percent', 0):3}% {p.get('stage', '')}"))
    finally:
        ai_study_service._call = original_call
    print(f"  built in {time.time() - started:.1f}s")

    content = study_v2.load_content(job)
    if content.get("study_status") != study_v2.STUDY_READY:
        raise SystemExit(f"pack is not ready: {content.get('study_status')}")
    if not content.get("concepts"):
        raise SystemExit("pack has no concepts")

    cache = {
        "_comment": (
            "Pre-built Study pack for the bundled demo lecture. Generated by "
            "scripts/capture_demo_study_cache.py from a real pipeline run over "
            "electron-spike/assets/demo-lecture.mp4. Do not hand-edit: "
            "regenerate."
        ),
        "demo_video_sha256": demo_study_cache.sha256_of(str(DEMO)),
        "expects": {
            "segment_count": len(segments),
            "slide_count": len(slides),
        },
        "content": content,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} "
          f"({len(content.get('concepts') or [])} concepts, "
          f"{len(content.get('flashcards') or [])} flashcards, "
          f"{len(content.get('quiz') or [])} quiz questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
