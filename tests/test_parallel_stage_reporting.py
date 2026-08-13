"""Transcribe and Detect Slides run concurrently; the sidecar must report both.

`job_controller.py` runs transcription and slide detection in parallel once
audio has been extracted. The sidecar reported progress through a single
`current_stage` scalar, so the two stages raced for it several times a second.
That one defect produced three separate user-visible symptoms:

1. The footer alternated between "Transcribe - 43%" and "Detect Slides - 29%"
   on every event, which reads as flicker.
2. `_on_transcript_segment` derived its live percent only while
   `current_stage == "Transcribe"`. Detect Slides emits real stage-progress
   events and whisper emits none, so Detect Slides took the scalar and
   Transcribe could never take it back -- a permanent dead row.
3. `_pipeline_stages` marked a stage active only when it equalled the scalar,
   so the other member of the parallel group was drawn as *pending*: a grey,
   bar-less checklist row for a stage that was actually running.

These tests drive the real handlers, so they fail if the scalar returns.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"


def _sidecar(name: str):
    """A Sidecar with only the stage-reporting state wired up.

    `__new__` avoids constructing the Qt application, controller and job store
    that the real __init__ builds; every attribute the stage handlers touch is
    supplied explicitly below.
    """
    spec = importlib.util.spec_from_file_location(name, SIDECAR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    obj = module.Sidecar.__new__(module.Sidecar)
    obj.active_stages = set()
    obj._current_stage = ""
    obj.stage_percent = {}
    obj.current_job = None
    obj.backend_label = "whisper.cpp"
    obj.auto_export = False
    obj.emitted: list[dict] = []
    obj.statuses: list[str] = []

    obj._emit = lambda payload: obj.emitted.append(payload)
    obj._emit_pipeline = lambda job=None: None
    obj._emit_job_payloads = lambda *a, **k: None
    obj._promote_next = lambda *a, **k: None

    def _emit_status(label, *, job=None, detail=""):
        obj.statuses.append(detail)

    obj._emit_status = _emit_status
    return module, obj


class _Job:
    """Minimal stand-in for a job: stage statuses plus a source duration."""

    def __init__(self, statuses: dict[str, str], duration: float = 600.0):
        self.job_id = "job-parallel"
        self._statuses = statuses
        self.source = {"duration": duration}

    def get_stage_status(self, stage: str) -> str:
        return self._statuses.get(stage, "pending")


def _enter_parallel_group(sidecar):
    """Reach the real state: both stages started, only Detect Slides ticking."""
    sidecar._on_stage_started("Transcribe")
    sidecar._on_stage_started("Detect Slides")
    for percent in (5, 12, 29):
        sidecar._on_stage_progress("Detect Slides", percent)


def test_footer_label_does_not_alternate_between_parallel_stages():
    """Symptom 1: the flicker. One stable label, not whichever ticked last."""
    _, sidecar = _sidecar("lp_sidecar_stage_footer")
    _enter_parallel_group(sidecar)

    assert sidecar.current_stage == "Transcribe", (
        "Detect Slides progress must not steal the footer from Transcribe"
    )
    # Every status line emitted during the group names the same stage, so the
    # footer text cannot oscillate no matter how fast Detect Slides ticks.
    during_group = [detail for detail in sidecar.statuses if detail]
    assert during_group, "the parallel group emitted no status at all"
    assert all(detail.startswith("Transcribe") for detail in during_group), (
        f"footer alternated between stages: {during_group}"
    )


def test_transcribe_percent_still_advances_after_detect_slides_ticks():
    """Symptom 2: the deadlock. Whisper progress must survive the parallel group."""
    _, sidecar = _sidecar("lp_sidecar_stage_transcribe")
    sidecar.current_job = _Job({}, duration=600.0)
    _enter_parallel_group(sidecar)

    # 150s into a 600s lecture == 25%.
    sidecar._on_transcript_segment({"text": "a line", "end_ms": 150_000})
    assert sidecar.stage_percent["Transcribe"] == 25

    sidecar._on_transcript_segment({"text": "another", "end_ms": 300_000})
    assert sidecar.stage_percent["Transcribe"] == 50, (
        "Transcribe percent froze once Detect Slides had emitted progress"
    )


def test_transcribe_percent_is_ignored_once_the_stage_has_finished():
    """The gate is membership, so a late segment cannot revive a done stage."""
    _, sidecar = _sidecar("lp_sidecar_stage_late")
    sidecar.current_job = _Job({}, duration=600.0)
    _enter_parallel_group(sidecar)
    sidecar._on_stage_finished("Transcribe", True, "")

    sidecar._on_transcript_segment({"text": "late", "end_ms": 570_000})
    assert sidecar.stage_percent.get("Transcribe") == 100


def test_both_concurrent_stages_render_as_active_on_the_checklist():
    """Symptom 3: the grey bar-less row for a stage that is in fact running."""
    _, sidecar = _sidecar("lp_sidecar_stage_checklist")
    job = _Job({"Inspect": "completed", "Extract Audio": "completed"})
    sidecar.current_job = job
    _enter_parallel_group(sidecar)
    sidecar._on_transcript_segment({"text": "x", "end_ms": 60_000})

    rows = {row["label"]: row for row in sidecar._pipeline_stages(job)}
    assert rows["Transcribe"]["state"] == "active"
    assert rows["Detect Slides"]["state"] == "active", (
        "the non-primary member of the parallel group was drawn as pending"
    )
    # Both carry a real percentage, so neither row is a bar-less placeholder.
    assert rows["Transcribe"]["pct"] == 10
    assert rows["Detect Slides"]["pct"] == 29
    # Stages that have not begun are still pending -- the fix must not light
    # up the whole checklist.
    assert rows["Align"]["state"] == "pending"
    assert rows["Export"]["state"] == "pending"


def test_finishing_one_stage_hands_the_footer_to_the_survivor():
    _, sidecar = _sidecar("lp_sidecar_stage_handoff")
    _enter_parallel_group(sidecar)
    sidecar._on_stage_finished("Detect Slides", True, "")

    assert sidecar.active_stages == {"Transcribe"}
    assert sidecar.current_stage == "Transcribe"

    sidecar._on_stage_finished("Transcribe", True, "")
    assert sidecar.active_stages == set()
    assert sidecar.current_stage == ""


@pytest.mark.parametrize("terminal", ["", "Queued"])
def test_a_finished_job_cannot_leak_its_running_stages_into_the_next(terminal):
    """The invariant is structural: ~20 sites assign current_stage directly.

    Idle and Queued both mean "nothing is running", so either assignment has
    to clear the set -- otherwise a stale Transcribe from a cancelled job
    lights up the next job's checklist.
    """
    _, sidecar = _sidecar("lp_sidecar_stage_leak_" + (terminal or "idle"))
    _enter_parallel_group(sidecar)
    assert sidecar.active_stages

    sidecar.current_stage = terminal
    assert sidecar.active_stages == set()

    job = _Job({})
    rows = {row["label"]: row for row in sidecar._pipeline_stages(job)}
    assert all(row["state"] == "pending" for row in rows.values())
