"""Study material has to be shapeable, and Regenerate has to report failure.

Three separate complaints, one theme -- the Study pack was take-it-or-leave-it:

1. Regenerate looked like a dead button. The sidecar's partial-refresh worker
   swallowed GatewayError and StudyContentError with a bare `pass`, which are
   the two likeliest ways a regeneration fails. The student got an optimistic
   "Refreshing…" toast and then silence.

2. The generated pack was tiny, so 5/10/20-minute Quick Study all returned the
   same handful of items: the pool was smaller than the smallest target. The
   gateway asked for "at least two flashcards" and an 8B model duly returned
   about two.

3. There was no way to make the quiz harder, easier, longer or shorter.

The quiz controls filter the ALREADY generated pack rather than re-requesting:
instant, free, offline, and it cannot fail halfway through a revision session.
That only works if the generator spreads difficulty, which is asserted here too.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
APP_CSS = (ROOT / "app" / "ui" / "app.css").read_text(encoding="utf-8")
TASKS_JS = (ROOT / "ai-gateway" / "src" / "tasks.js").read_text(encoding="utf-8")
SIDECAR = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- regenerate

def test_a_failed_regeneration_is_reported_instead_of_swallowed():
    worker = SIDECAR.split("def _start_partial_study_refresh", 1)[1]
    worker = worker.split("def _start_ai_interaction", 1)[0]
    handler = worker.split("except (self.ai_gateway.GatewayError,", 1)[1]
    handler = handler.split("except Exception:", 1)[0]
    assert "pass" not in handler, (
        "gateway/content failures during Regenerate are swallowed again"
    )
    assert '"refresh_status": "failed"' in handler
    assert "str(exc)" in handler, "the real reason must reach the UI"


def test_the_renderer_corrects_its_optimistic_toast_on_failure():
    handler = APP_JS.split("lpBridge.on('study_generation'", 1)[1]
    handler = handler.split("lpBridge.on(", 1)[0]
    assert "payload.refresh_status === 'failed'" in handler
    assert "toast(" in handler.split("refresh_status === 'failed'", 1)[1][:200]


# ------------------------------------------------------------- pack richness

def test_the_generator_is_asked_for_a_pack_sized_to_the_lecture():
    instruction = TASKS_JS.split("  study_material_generation: '", 1)[1]
    instruction = instruction.split("',\n", 1)[0]
    lowered = instruction.lower()
    # A per-concept target, not a floor of two.
    assert "per concept" in lowered
    assert "bare minimum" in lowered
    # Padding is worse than a short pack -- both must be stated.
    assert "never pad" in lowered
    assert "return fewer" in lowered
    # And it must not be allowed to blow the token ceiling into invalid JSON.
    assert "truncated" in lowered


def test_the_output_ceiling_leaves_room_for_the_larger_pack():
    ceiling = re.search(
        r"if \(task === 'study_material_generation'\) return (\d+);", TASKS_JS)
    assert ceiling is not None
    assert int(ceiling.group(1)) >= 16000, (
        "a 20-card / 16-question pack does not fit the old 12k ceiling"
    )


def test_difficulty_is_spread_so_the_filter_has_something_to_filter():
    """The controls are useless if every item comes back the same difficulty."""
    instruction = TASKS_JS.split("  study_material_generation: '", 1)[1]
    instruction = instruction.split("',\n", 1)[0]
    assert "SPREAD THE DIFFICULTY" in instruction
    for level in ('"easy"', '"medium"', '"hard"'):
        assert level in instruction
    assert "lowercase" in instruction


# ------------------------------------------------------------ quiz shaping

def _fn(name: str) -> str:
    body = APP_JS.split("function " + name + "(", 1)[1]
    return body.split("\n  function ", 1)[0]


def test_shaping_filters_the_generated_pack_and_never_calls_the_backend():
    pool = _fn("quizPool")
    assert "studyV2.content" in pool and "quiz" in pool
    for banned in ("lpBridge", "fetch(", "study_v2_regenerate"):
        assert banned not in pool, (
            f"shaping the quiz must not {banned} -- it has to work offline"
        )


def test_an_unrecognised_difficulty_is_not_dropped_from_every_view():
    """A model that writes "Moderate" must not make the question unreachable."""
    fn = _fn("quizDifficultyOf")
    assert "toLowerCase()" in fn
    assert "'medium'" in fn, "unknown difficulties must fall back, not vanish"


def test_reshaping_resets_the_run_it_invalidates():
    fn = _fn("setQuizShape")
    for field in ("quizIndex = 0", "quizCorrect = 0",
                  "quizAnswers = []", "quizPicks = {}"):
        assert field in fn, (
            f"reshaping must clear {field}: the index refers to a different set"
        )
    assert "studyV2PersistView()" in fn


@pytest.mark.parametrize("consumer", [
    "var idx = Number(btn.dataset.opt);",          # answering a choice
    "var input = $('study-quiz-short-answer');",   # grading a short answer
    "var index = questions.findIndex(",            # recording the grade
])
def test_every_quiz_consumer_reads_the_same_shaped_pool(consumer):
    """quizIndex indexes the SHAPED run.

    A consumer that reads the full pack instead would answer, grade or score a
    different question than the one on screen -- silently, and only once a
    filter is active.
    """
    window = APP_JS.split(consumer, 1)
    assert len(window) == 2, f"anchor not found: {consumer}"
    before, after = window[0][-400:], window[1][:400]
    assert "quizPool()" in before + after, (
        "this quiz consumer still reads the unfiltered studyV2.content.quiz"
    )


def test_the_shape_row_survives_a_narrow_window_and_obeys_AD_20():
    # Match the shaping rules themselves rather than a line range: the section
    # has no trailing marker, and its own comment prose ("no transitions") and
    # the later reduced-motion overrides are not declarations of this row.
    rules = "\n".join(re.findall(r"\.lp-quiz-shape[^{}]*\{[^}]*\}", APP_CSS))
    assert ".lp-quiz-shape-btn" in rules, "the shaping rules were not found"
    assert "flex-wrap:wrap" in rules, "the row must wrap, not overflow, at 640px"
    for banned in ("transition", "animation", "will-change", "backdrop-filter"):
        assert banned not in rules, f"AD-20: {banned} must not appear here"


def test_the_selected_shape_is_exposed_to_assistive_tech():
    html = _fn("quizShapeControlsHtml")
    assert "aria-pressed=" in html
    # An unavailable difficulty is disabled with a reason, not silently inert.
    assert "disabled" in html
    assert "title=" in html
