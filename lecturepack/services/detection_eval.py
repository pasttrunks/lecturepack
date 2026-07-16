"""
lecturepack.services.detection_eval
====================================

Ground-truth evaluation for the slide detector. Pure standard library (no numpy
/ OpenCV) so the *metric* logic is unit-testable anywhere; only the harness that
produces candidates needs OpenCV.

Ground truth is expressed as a list of *meaningful slide states*, each with an
acceptance window ``[t_min, t_max]`` (seconds). A candidate matches a ground
truth event if its timestamp falls inside that window. Matching is greedy and
one-to-one, so duplicate captures of the same state count as false positives.

Ground truth also lists *distractor windows* (mouse pointer, fade transitions,
webcam overlays, captions, rapid progressive-build steps). A false positive that
lands in a distractor window is additionally reported so regressions in motion /
overlay filtering are visible, not just the aggregate precision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class GroundTruthEvent:
    id: str
    nominal_sec: float      # when the underlying change occurs
    t_min: float            # earliest acceptable capture time
    t_max: float            # latest acceptable capture time (allows stabilisation)
    label: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GroundTruthEvent":
        return GroundTruthEvent(
            id=str(d["id"]), nominal_sec=float(d["nominal_sec"]),
            t_min=float(d["t_min"]), t_max=float(d["t_max"]),
            label=d.get("label", ""))


@dataclass
class DistractorWindow:
    id: str
    t_min: float
    t_max: float
    label: str = ""
    max_allowed: int = 0   # candidates tolerated in this window before penalising

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DistractorWindow":
        return DistractorWindow(
            id=str(d["id"]), t_min=float(d["t_min"]), t_max=float(d["t_max"]),
            label=d.get("label", ""), max_allowed=int(d.get("max_allowed", 0)))


@dataclass
class GroundTruth:
    name: str
    events: List[GroundTruthEvent] = field(default_factory=list)
    distractors: List[DistractorWindow] = field(default_factory=list)

    @staticmethod
    def load(path: str) -> "GroundTruth":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return GroundTruth.from_dict(d)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GroundTruth":
        return GroundTruth(
            name=d.get("name", ""),
            events=[GroundTruthEvent.from_dict(e) for e in d.get("events", [])],
            distractors=[DistractorWindow.from_dict(x) for x in d.get("distractors", [])],
        )


@dataclass
class EvalResult:
    name: str
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    candidate_count: int
    meaningful_state_count: int
    mean_timestamp_error: float
    matched: List[Dict[str, Any]] = field(default_factory=list)
    missed: List[str] = field(default_factory=list)
    spurious: List[float] = field(default_factory=list)
    distractor_hits: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"{self.name}: P={self.precision:.3f} R={self.recall:.3f} "
            f"F1={self.f1:.3f} | TP={self.true_positives} FP={self.false_positives} "
            f"FN={self.false_negatives} | candidates={self.candidate_count} "
            f"vs states={self.meaningful_state_count} | "
            f"ts_err={self.mean_timestamp_error:.2f}s"
        )


def evaluate(candidate_seconds: List[float], gt: GroundTruth) -> EvalResult:
    """Greedy one-to-one matching of candidates to ground-truth events.

    A candidate matches the *earliest still-unmatched* event whose window it
    falls in. Unmatched events are false negatives; unmatched candidates are
    false positives.
    """
    cands = sorted(float(c) for c in candidate_seconds)
    events = sorted(gt.events, key=lambda e: e.nominal_sec)
    matched_event = {e.id: None for e in events}
    matched: List[Dict[str, Any]] = []
    used = [False] * len(cands)

    for e in events:
        for i, c in enumerate(cands):
            if used[i]:
                continue
            if e.t_min <= c <= e.t_max:
                used[i] = True
                matched_event[e.id] = c
                matched.append({"event": e.id, "candidate_sec": c,
                                "error_sec": abs(c - e.nominal_sec),
                                "label": e.label})
                break

    tp = sum(1 for v in matched_event.values() if v is not None)
    missed = [e.id for e in events if matched_event[e.id] is None]
    spurious = [cands[i] for i in range(len(cands)) if not used[i]]
    fp = len(spurious)
    fn = len(missed)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    mean_err = (sum(m["error_sec"] for m in matched) / len(matched)) if matched else 0.0

    distractor_hits: Dict[str, int] = {}
    for d in gt.distractors:
        hits = sum(1 for s in spurious if d.t_min <= s <= d.t_max)
        if hits:
            distractor_hits[d.id] = hits

    return EvalResult(
        name=gt.name, true_positives=tp, false_positives=fp, false_negatives=fn,
        precision=precision, recall=recall, f1=f1,
        candidate_count=len(cands), meaningful_state_count=len(events),
        mean_timestamp_error=mean_err, matched=matched, missed=missed,
        spurious=spurious, distractor_hits=distractor_hits,
    )


def meets_targets(result: EvalResult, min_recall: float = 0.95,
                  min_precision: float = 0.85,
                  candidate_tolerance: float = 0.20) -> Dict[str, bool]:
    """Check a result against the project's acceptance targets."""
    states = max(1, result.meaningful_state_count)
    count_ratio = abs(result.candidate_count - states) / states
    return {
        "recall_ok": result.recall >= min_recall,
        "precision_ok": result.precision >= min_precision,
        "candidate_count_ok": count_ratio <= candidate_tolerance,
        "no_missed_majors": result.false_negatives == 0,
    }
