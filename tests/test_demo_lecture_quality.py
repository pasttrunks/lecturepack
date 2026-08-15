"""The guided demo shows the whole bundled lecture, and shows it quickly.

Two defects, both invisible from the code alone:

* The demo detected 2 slides for a 4-slide lecture. PRESETS["demo"] was written
  and calibrated for exactly this video, but _preset() whitelists the three
  student-facing names and silently returns "balanced" for anything else --
  and balanced enforces min_time_between_slides=5.0 on a 10-second video.
* Its Study pack was built live, costing a gateway round trip while a student
  is being shown around an app they have not chosen yet.

The slide test runs the REAL detector over the REAL bundled video, because the
whole failure was a plausible-looking config that never took effect.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from lecturepack.services import demo_study_cache


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "electron-spike" / "assets" / "demo-lecture.mp4"
CACHE = ROOT / "app" / "assets" / "demo" / "study-content-v2.json"
SIDECAR = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------- slides

def test_the_bundled_demo_is_imported_with_the_preset_written_for_it():
    """_preset() cannot return "demo", so the demo branch must set it."""
    assert 'job.settings["preset"] = "demo" if bundled_demo else self._preset(preset)' in SIDECAR
    whitelist = SIDECAR.split("def _preset(value: Any) -> str:", 1)[1][:400]
    assert '"demo"' not in whitelist, "demo must stay unselectable as an ordinary option"


def test_starting_the_demo_does_not_overwrite_its_preset():
    """Setting it at import is not enough.

    The bridge always sends a preset with start_processing (the payload's, or
    the current setting), and _start_job applied it unconditionally -- so the
    calibrated "demo" preset was replaced with "balanced" the instant the job
    started, while the import code that chose it still looked correct. Measured
    in the packaged app before the guard: 2 slides.
    """
    start = SIDECAR.split("def _start_job", 1)[1][:1200]
    assert 'if payload.get("preset") and not self._is_demo_job(job):' in start


@pytest.mark.skipif(not DEMO.is_file(), reason="bundled demo video missing")
def test_the_demo_preset_finds_every_slide_in_the_bundled_lecture():
    """Ground truth: the bundled lecture has four slides in ten seconds."""
    pytest.importorskip("cv2")
    pytest.importorskip("skimage")
    import tempfile

    from lecturepack.constants import PRESETS
    from lecturepack.infrastructure.cv_engine import SlideDetectorWorker

    def run(preset_key: str) -> list[float]:
        with tempfile.TemporaryDirectory() as tmp:
            worker = SlideDetectorWorker(
                str(DEMO), {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}, [],
                PRESETS[preset_key], {"candidates": os.path.join(tmp, "candidates")})
            got: dict = {}
            worker.finished.connect(lambda ok, err, c: got.update(c=c or []))
            worker.run()
            return [round(float(c["timestamp_seconds"]), 2) for c in got.get("c", [])]

    demo = run("demo")
    assert len(demo) == 4, f"expected one slide each, got {demo}"
    # One per quarter of the video: the slides change roughly every 2.5s.
    assert [int(t // 2.5) for t in demo] == [0, 1, 2, 3], demo

    # The regression this locks in: the default preset cannot do this, which is
    # why the demo must not be allowed to fall back to it.
    assert len(run("balanced")) == 2


# -------------------------------------------------------------- study cache

def test_the_shipped_cache_describes_the_bundled_lecture():
    assert CACHE.is_file(), "the demo Study pack must ship"
    cache = demo_study_cache.load_cache(str(CACHE))
    assert cache is not None
    digest = hashlib.sha256(DEMO.read_bytes()).hexdigest()
    assert cache["demo_video_sha256"] == digest == demo_study_cache.DEMO_VIDEO_SHA256, (
        "the cache must be regenerated when the bundled lecture changes: "
        "scripts/capture_demo_study_cache.py"
    )
    assert cache["expects"]["slide_count"] == 4, (
        "captured against the demo preset, not the balanced fallback"
    )


def test_the_shipped_cache_is_a_real_ready_pack():
    content = demo_study_cache.load_cache(str(CACHE))["content"]
    assert content["schema_version"] == 3, "an older schema is auto-migrated to Basic"
    assert content["study_status"] == "ready"
    assert content.get("provider") not in (None, "", "builtin"), (
        "a builtin provider would be re-read as a Basic pack"
    )
    for key in ("concepts", "flashcards", "quiz", "study_guide"):
        assert content.get(key), f"the demo pack must actually contain {key}"
    assert content.get("lecture_summary")


def test_every_citation_in_the_cache_resolves():
    """Citations are positional. A pack whose refs point past the transcript
    would show a student a source that jumps nowhere."""
    cache = demo_study_cache.load_cache(str(CACHE))
    segments = int(cache["expects"]["segment_count"])
    slides = int(cache["expects"]["slide_count"])
    content = cache["content"]
    seen = 0
    for key in ("concepts", "flashcards", "quiz", "study_guide", "teach_me_foundations"):
        for item in content.get(key) or []:
            for ref in (item.get("lecture_sources") or []) + (item.get("sources") or []):
                seg = ref.get("segment_id")
                if seg is not None and str(seg).isdigit():
                    assert int(seg) < segments, f"{key}: segment {seg} does not exist"
                    seen += 1
                slide = ref.get("slide_id")
                if slide is not None and str(slide).isdigit():
                    assert int(slide) < slides, f"{key}: slide {slide} does not exist"
                    seen += 1
    assert seen, "a demo pack with no citations at all would not show the feature"


# --------------------------------------------------------------- guardrails

def test_a_swapped_demo_video_disables_the_cache(tmp_path):
    """Otherwise the demo would describe a lecture nobody is watching."""
    other = tmp_path / "other.mp4"
    other.write_bytes(b"not the demo")
    cache = demo_study_cache.load_cache(str(CACHE))
    assert not demo_study_cache.matches(cache, str(other), 2, 4)


@pytest.mark.parametrize("segments,slides", [(1, 4), (2, 3), (99, 99)])
@pytest.mark.skipif(not DEMO.is_file(), reason="bundled demo video missing")
def test_a_differently_shaped_run_disables_the_cache(segments, slides):
    """Positional citations are only correct for the shape they were captured
    against, so a transcript or slide list of a different size must not adopt
    them -- half-matching is worse than any wait."""
    cache = demo_study_cache.load_cache(str(CACHE))
    assert not demo_study_cache.matches(cache, str(DEMO), segments, slides)


@pytest.mark.skipif(not DEMO.is_file(), reason="bundled demo video missing")
def test_the_matching_run_adopts_the_cache():
    cache = demo_study_cache.load_cache(str(CACHE))
    expects = cache["expects"]
    assert demo_study_cache.matches(
        cache, str(DEMO), expects["segment_count"], expects["slide_count"])


@pytest.mark.parametrize("junk", ["", "{", "[]", '{"content": 5}', "null"])
def test_a_damaged_cache_is_treated_as_absent(tmp_path, junk):
    path = tmp_path / "study-content-v2.json"
    path.write_text(junk, encoding="utf-8")
    assert demo_study_cache.load_cache(str(path)) is None
    assert demo_study_cache.find_cache(tmp_path / "nowhere") == ""


def test_the_cache_is_only_consulted_for_the_demo_and_never_on_regenerate():
    body = SIDECAR.split("def _adopt_demo_study_cache", 1)[1].split("def _start_ai_study", 1)[0]
    assert "if not self._is_demo_job(job):" in body
    assert "return False" in body
    start = SIDECAR.split("def _start_ai_study", 1)[1][:1600]
    assert "if not force and self._adopt_demo_study_cache(job):" in start, (
        "Regenerate must always be able to reach a real build"
    )


def test_the_persisted_pack_is_labelled_as_a_cache():
    """So a support bundle never reads a shipped pack as a live build."""
    content = demo_study_cache.content_for(demo_study_cache.load_cache(str(CACHE)))
    assert content["generation_metadata"]["demo_cache"] is True
    assert content["generation_metadata"]["progress_percent"] == 100
    assert "basic_reason" not in content["generation_metadata"]


@pytest.mark.skipif(not DEMO.is_file(), reason="bundled demo video missing")
def test_a_real_demo_job_adopts_the_pack_and_reads_back_as_ready(tmp_path):
    """End to end over the real function, a real Job and the shipped file.

    The unit checks above prove the guards; this proves the wiring -- that the
    adopted document is one study_v2 loads back as a finished pack, which is
    what makes the Study screen open instantly instead of building.
    """
    import importlib.util

    from lecturepack.models.job import Job
    from lecturepack.services import study_v2

    cache = demo_study_cache.load_cache(str(CACHE))
    expects = cache["expects"]

    job = Job(str(tmp_path), video_path=str(DEMO))
    job.manifest["is_demo"] = True
    job.manifest["bundled_demo"] = True
    job.save()

    # The exact shapes the pipeline leaves behind.
    transcript = Path(job.paths["transcript"])
    transcript.mkdir(parents=True, exist_ok=True)
    (transcript / "raw.json").write_text(json.dumps({"transcription": [
        {"offsets": {"from": i * 1000, "to": (i + 1) * 1000}, "text": f" segment {i}"}
        for i in range(expects["segment_count"])]}), encoding="utf-8")
    (Path(job.paths["root"]) / "candidates.json").write_text(json.dumps([
        {"timestamp_seconds": float(i), "image_filename": f"slide_{i:03d}.png",
         "decision": "accepted"} for i in range(expects["slide_count"])]),
        encoding="utf-8")

    spec = importlib.util.spec_from_file_location(
        "lp_sidecar_democache", ROOT / "electron-spike" / "python-sidecar.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.study_v2 = study_v2
    sidecar.runtime_root = ROOT
    sidecar.repo_root = ROOT
    emitted: list = []
    sidecar._emit_study_generation = emitted.append

    assert sidecar._adopt_demo_study_cache(job) is True
    loaded = study_v2.load_content(job)
    assert loaded["study_status"] == study_v2.STUDY_READY
    assert loaded["concepts"] and loaded["flashcards"] and loaded["quiz"]
    assert emitted and emitted[0]["progress_percent"] == 100

    # A lecture of a different shape must build normally.
    (Path(job.paths["root"]) / "candidates.json").write_text("[]", encoding="utf-8")
    assert sidecar._adopt_demo_study_cache(job) is False


@pytest.mark.skipif(not DEMO.is_file(), reason="bundled demo video missing")
def test_an_ordinary_lecture_never_adopts_the_demo_pack(tmp_path):
    import importlib.util

    from lecturepack.models.job import Job
    from lecturepack.services import study_v2

    job = Job(str(tmp_path), video_path=str(DEMO))  # same bytes, NOT flagged demo
    job.save()
    spec = importlib.util.spec_from_file_location(
        "lp_sidecar_democache2", ROOT / "electron-spike" / "python-sidecar.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.study_v2 = study_v2
    sidecar.runtime_root = ROOT
    sidecar.repo_root = ROOT
    sidecar._emit_study_generation = lambda payload: None
    assert sidecar._adopt_demo_study_cache(job) is False


def test_the_capture_script_is_the_documented_way_to_regenerate():
    script = ROOT / "scripts" / "capture_demo_study_cache.py"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert 'PRESETS["demo"]' in text, "the fixture must be captured with the demo preset"
    assert "if slide_count < 3:" in text, (
        "capturing against the balanced fallback would ship a 2-slide pack"
    )
    assert str(demo_study_cache.CACHE_FILENAME) in text
