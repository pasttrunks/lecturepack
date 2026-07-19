"""
Ground-truth acceptance test for the slide detector (v1.0).

Runs the REAL cv_engine detector over the synthetic fixture (no ignore masks --
the algorithm must reject the mouse pointer, fade transition, webcam noise and
live-caption distractors on its own) and asserts it meets the project's
precision/recall targets. This locks in the v1.0 precision guards
(overlay-band rejection + major-change persistence) as a regression test.

Requires OpenCV + numpy + scikit-image and the fixture video, so it is skipped
automatically if any are unavailable.
"""
import os
import tempfile
import pytest

pytest.importorskip("cv2")
pytest.importorskip("skimage")

from lecturepack.constants import PRESETS
from lecturepack.services import detection_eval as de

VIDEO = os.path.abspath("tests/fixtures/synthetic_lecture.mp4")
GT = os.path.abspath("tests/fixtures/ground_truth/synthetic_lecture.json")


def _run(preset_key):
    from lecturepack.infrastructure.cv_engine import SlideDetectorWorker
    preset = PRESETS[preset_key]
    with tempfile.TemporaryDirectory() as tmp:
        worker = SlideDetectorWorker(
            VIDEO,
            {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
            [],  # no masks: intrinsic robustness only
            preset,
            {"candidates": os.path.join(tmp, "candidates")},
        )
        captured = {}
        worker.finished.connect(lambda ok, err, cands: captured.update(cands=cands or []))
        worker.run()
        cands = captured.get("cands", [])
        return [c["timestamp_seconds"] for c in cands]


@pytest.mark.skipif(not os.path.exists(VIDEO), reason="fixture video missing")
def test_balanced_meets_targets():
    gt = de.GroundTruth.load(GT)
    result = de.evaluate(_run("balanced"), gt)
    targets = de.meets_targets(result)
    assert all(targets.values()), f"balanced failed targets: {targets} | {result.summary()}"
    # Default preset is expected to be clean on this fixture.
    assert result.recall == 1.0, result.summary()
    assert result.false_negatives == 0, result.summary()


@pytest.mark.skipif(not os.path.exists(VIDEO), reason="fixture video missing")
def test_detailed_meets_targets():
    gt = de.GroundTruth.load(GT)
    result = de.evaluate(_run("detailed"), gt)
    targets = de.meets_targets(result)
    assert all(targets.values()), f"detailed failed targets: {targets} | {result.summary()}"


@pytest.mark.skipif(not os.path.exists(VIDEO), reason="fixture video missing")
def test_no_fade_or_caption_false_positive():
    """The fade transition (30-33s) and caption band (45-50s) must not produce
    their own slide candidates under the balanced preset."""
    ts = _run("balanced")
    fade_fps = [t for t in ts if 30.5 <= t <= 32.9]
    caption_fps = [t for t in ts if 45.5 <= t <= 49.9]
    assert not fade_fps, f"fade transition produced candidates at {fade_fps}"
    assert not caption_fps, f"caption band produced candidates at {caption_fps}"
