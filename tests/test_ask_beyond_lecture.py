"""Ask may answer lecture-adjacent questions, and must say when it did.

The shipped behaviour was a dead end: asked "when was Schliemann born?" about a
lecture that discusses Schliemann at length, Ask replied "The birth date of
Heinrich Schliemann is not mentioned in the provided lecture context" -- and
then attached three "From lecture · Slide" chips to that non-answer, because
`_grounding` borrowed the retrieved concept's citations whenever the model
returned none of its own.

Both halves are wrong and both are fixed here:

* the gateway now tells the model to answer such questions from its own
  knowledge of the subject, marked provenance "extra_context"; and
* a claim declared as extra_context no longer inherits lecture citations, so
  the UI can label it honestly instead of dressing it up as lecture evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lecturepack.services import ai_study_service


ROOT = Path(__file__).resolve().parents[1]
TASKS_JS = (ROOT / "ai-gateway" / "src" / "tasks.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
APP_CSS = (ROOT / "app" / "ui" / "app.css").read_text(encoding="utf-8")
SIDECAR = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")


# A retrieved concept always carries citations; that is what used to be
# borrowed. Segments/slides stay empty so nothing the model returns validates,
# which is exactly the "model cited nothing" case.
INHERITED = {
    "lecture_sources": [
        {"segment_id": "seg-1", "slide_id": "", "quote": "Schliemann excavated Troy"},
    ],
}


def _ground(provenance: str) -> dict:
    return ai_study_service._grounding(
        {"answer": "He was born in 1822.", "provenance": provenance,
         "lecture_sources": [], "web_sources": []},
        [], [], inherited=INHERITED,
    )


def test_a_background_answer_does_not_borrow_lecture_citations():
    grounded = _ground("extra_context")
    assert grounded["lecture_sources"] == [], (
        "an answer the lecture does not support was given lecture citations"
    )
    assert grounded["sources"] == []
    assert grounded["provenance"] == "extra_context"


def test_a_lecture_answer_still_inherits_the_concept_citations():
    """The inheritance is load-bearing for real lecture answers -- keep it."""
    grounded = _ground("lecture")
    assert grounded["lecture_sources"] == INHERITED["lecture_sources"]
    assert grounded["provenance"] == "lecture"


@pytest.mark.parametrize("declared", ["", "mixed", "web_verified", "nonsense"])
def test_only_an_explicit_extra_context_declaration_suppresses_inheritance(declared):
    """Fail safe: anything other than an explicit declaration keeps the old path."""
    assert _ground(declared)["lecture_sources"] == INHERITED["lecture_sources"]


def test_the_gateway_permits_and_bounds_a_background_answer():
    instruction = TASKS_JS.split("  ask: '", 1)[1].split("',\n", 1)[0]
    lowered = instruction.lower()
    # It must grant permission...
    assert "your own knowledge" in lowered
    assert "extra_context" in instruction
    # ...require the honest empty citation list...
    assert "empty lecture_sources" in lowered
    # ...and still forbid inventing lecture evidence.
    assert "never attach lecture citations" in lowered


def test_the_answer_scope_reaches_the_renderer():
    """provenance must survive the sidecar -> ai_sources -> renderer hop.

    Without it the renderer sees an empty source list and draws nothing, so a
    background answer is indistinguishable from a broken one.
    """
    assert '"provenance": str(result.get("provenance") or "")' in SIDECAR
    assert "function appendStudyAskSources(sources, provenance)" in APP_JS
    assert "payload ? payload.provenance : ''" in APP_JS
    assert "'extra_context'" in APP_JS
    assert ".study-source-beyond" in APP_CSS
    # The marker must not be styled as a lecture (blue) or web (green) chip.
    beyond = APP_CSS.split(".study-source-beyond{", 1)[1].split("}", 1)[0]
    assert "var(--blue" not in beyond and "var(--green" not in beyond
