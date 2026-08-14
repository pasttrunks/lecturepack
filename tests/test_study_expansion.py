"""A ready Study pack grows across small calls instead of one large one.

A single study_material_generation call returns close to the schema minimum --
measured live: 2 flashcards and 3 questions for a five-concept lecture. That is
not a revision pack, and it is why Quick Study's 5/10/20-minute sessions all
returned the same handful of items: the pool was smaller than the smallest
target.

Asking the generator for more in ONE call is not available. Its route budget is
fixed (50s NVIDIA inside a 175s client deadline) and raising the ask past it
produced provider_timeout, then provider_invalid_shape from truncated JSON, and
Study AI failed outright in production.

So the pack grows across SEPARATE small requests after it is already ready.
The first attempt reused regenerate_concept and added nothing -- measured live,
five concepts, +0 and +0 -- because that task only rewrites the dependents it
is handed. A dedicated expand_concept_material task replaced it. Measured live
against the deployed gateway: 2 -> 18 flashcards, 3 -> 13 questions, each call
4.5-8.5s, with one concept correctly returning nothing rather than padding.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from lecturepack.services import ai_study_service as svc


ROOT = Path(__file__).resolve().parents[1]
TASKS_JS = (ROOT / "ai-gateway" / "src" / "tasks.js").read_text(encoding="utf-8")
WRANGLER = (ROOT / "ai-gateway" / "wrangler.toml").read_text(encoding="utf-8")
SERVICE = Path(svc.__file__).read_text(encoding="utf-8")


def _fn(name: str) -> str:
    body = SERVICE.split(f"def {name}(", 1)[1]
    return body.split("\ndef ", 1)[0]


def test_expansion_runs_after_the_pack_is_already_usable():
    """A failure here must cost the student nothing they already had."""
    gen = SERVICE.split('"status": study_v2.STUDY_READY', 1)[1]
    assert "_expand_material(" in gen.split("except GatewayError", 1)[0], (
        "expansion must follow the ready emit, not precede it"
    )
    fn = _fn("_expand_material")
    # Every error class, not just the gateway's: after the ready emit, the only
    # thing a failure here can achieve is removing material already earned.
    assert "except Exception:" in fn
    assert "continue" in fn, "one bad concept must not abort the pass"


def test_expansion_uses_its_own_task_not_regenerate_concept():
    fn = _fn("_expand_material")
    assert '"expand_concept_material"' in fn
    assert "_regenerate_one" not in fn, (
        "regenerate_concept only rewrites dependents; with none it returns none"
    )
    # It must tell the model what already exists, or it repeats itself.
    assert "existing_flashcards" in fn and "existing_quiz" in fn


def test_the_new_task_is_registered_and_routed():
    assert "'expand_concept_material'," in TASKS_JS
    assert "expand_concept_material: object({" in TASKS_JS
    assert "expand_concept_material:" in TASKS_JS.split("const taskInstructions", 1)[1]
    # Without this the task falls off the NVIDIA-first route order.
    first = re.search(r'NVIDIA_FIRST_TASKS = "([^"]+)"', WRANGLER)
    assert first and "expand_concept_material" in first.group(1).split(",")


def test_each_expansion_call_stays_far_inside_the_route_budget():
    ceiling = re.search(
        r"if \(task === 'expand_concept_material'\) return (\d+);", TASKS_JS)
    assert ceiling is not None
    assert int(ceiling.group(1)) <= 4000, (
        "a large per-concept call reintroduces the timeout that broke generation"
    )
    instruction = TASKS_JS.split("  expand_concept_material: '", 1)[1].split("',\n", 1)[0]
    assert "up to 4 flashcards" in instruction
    assert "do not repeat" in instruction.lower()
    assert "padding" in instruction.lower(), "a short pack beats near-duplicates"


def test_appended_items_are_validated_like_generated_ones():
    """An appended card must not carry a citation the lecture cannot support."""
    fn = _fn("_normalize_expansion")
    assert "normalize_generated_content(" in fn
    assert "concept_ids" in fn


def test_duplicates_are_rejected_on_meaning_not_exact_bytes():
    assert svc._dedup_key({"front": "  What  IS  Troy? "}, "front") == "what is troy?"
    assert (svc._dedup_key({"front": "What is Troy?"}, "front")
            == svc._dedup_key({"front": "WHAT IS   troy?"}, "front"))


@pytest.mark.parametrize("cap,minimum", [
    ("EXPAND_MAX_CARDS", 12), ("EXPAND_MAX_QUIZ", 10),
])
def test_the_pack_is_capped_but_big_enough_for_a_real_session(cap, minimum):
    """Quick Study offers 5/10/20-item sessions; below ~20 they collapse."""
    assert getattr(svc, cap) >= minimum


def test_expansion_stops_when_the_job_is_cancelled():
    fn = _fn("_expand_material")
    assert "cancelled and cancelled()" in fn
    # Checked inside the per-concept loop, not only once up front.
    assert fn.index("for index, concept_id") < fn.index("cancelled and cancelled()")
