"""Tests for the pure-Python detection ground-truth evaluator. No OpenCV needed:
these verify the *metric* logic against hand-constructed candidate lists."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lecturepack.services import detection_eval as de

GT_PATH = os.path.join(os.path.dirname(__file__),
                       "fixtures", "ground_truth", "synthetic_lecture.json")


def _gt():
    return de.GroundTruth.load(GT_PATH)


def test_ground_truth_loads():
    gt = _gt()
    assert gt.name == "synthetic_lecture"
    assert len(gt.events) == 8
    assert len(gt.distractors) == 5
    # Slide 2 appears twice as distinct events.
    ids = [e.id for e in gt.events]
    assert "s2_bullets_ab" in ids and "s2_repeat" in ids


def test_perfect_detection_scores_1():
    gt = _gt()
    # One candidate inside each event window.
    cands = [1.0, 6.0, 21.0, 26.0, 34.0, 51.0, 56.0, 61.0]
    r = de.evaluate(cands, gt)
    assert r.true_positives == 8
    assert r.false_positives == 0 and r.false_negatives == 0
    assert r.precision == 1.0 and r.recall == 1.0 and r.f1 == 1.0
    targets = de.meets_targets(r)
    assert all(targets.values())


def test_missed_major_is_false_negative():
    gt = _gt()
    cands = [1.0, 6.0, 21.0, 26.0, 34.0, 51.0, 56.0]  # missing final slide
    r = de.evaluate(cands, gt)
    assert r.false_negatives == 1
    assert "s7_final" in r.missed
    assert r.recall < 1.0
    assert de.meets_targets(r)["no_missed_majors"] is False


def test_duplicate_capture_counts_as_false_positive():
    gt = _gt()
    # Two candidates inside the slide-2 window -> one TP, one FP.
    cands = [1.0, 6.0, 6.5, 21.0, 26.0, 34.0, 51.0, 56.0, 61.0]
    r = de.evaluate(cands, gt)
    assert r.true_positives == 8
    assert r.false_positives == 1
    assert r.precision < 1.0


def test_distractor_false_positive_is_attributed():
    gt = _gt()
    cands = [1.0, 6.0, 21.0, 26.0, 34.0, 51.0, 56.0, 61.0, 42.0]  # 42s = webcam window
    r = de.evaluate(cands, gt)
    assert r.false_positives == 1
    assert r.distractor_hits.get("webcam_overlay") == 1


def test_timestamp_error_reported():
    gt = _gt()
    cands = [2.5, 7.5, 22.5, 27.5, 36.5, 52.5, 57.5, 62.5]  # near window ends
    r = de.evaluate(cands, gt)
    assert r.true_positives == 8
    assert r.mean_timestamp_error > 1.0  # captured late but within window


def test_candidate_explosion_flagged_by_targets():
    gt = _gt()
    # 8 correct + 20 spurious progressive-build candidates.
    cands = [1.0, 6.0, 21.0, 26.0, 34.0, 51.0, 56.0, 61.0]
    cands += [50.5 + i * 0.2 for i in range(20)]
    r = de.evaluate(cands, gt)
    t = de.meets_targets(r)
    assert t["candidate_count_ok"] is False   # count far exceeds 8 states
    assert r.distractor_hits.get("ink_build_steps", 0) >= 1
