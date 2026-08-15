"""Groups persist, and a stacked Home can be folded down.

GROUP MEMORY. Reported as "it resets a lot", and it was a real bug with a
one-line cause: `set_job_group` wrote the group into manifest.json atomically,
but the sidecar's `_summary` -- the payload every `jobs_changed` refresh hands
the renderer -- never included it. So the renderer saw a job with no group,
`jobGroup()` fell through to inferring one from the title, and the student's
grouping reverted itself on the next refresh. Written and never read.

COLLAPSE. A library that has grown past a screenful needs to be foldable. State
is keyed by group NAME rather than by job id, because the student collapses
"CL100", not a set of lectures -- adding a lecture to a collapsed course must
not silently reopen it. Collapsed groups drop their cards from the DOM rather
than hiding them, which is the point of collapsing a long list.

Verified live in the packaged app: 10 cards -> 0 on collapse, state persisted,
still collapsed after a reload, and 0 -> 10 on re-expand.
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")
APP_JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "ui" / "app.css").read_text(encoding="utf-8")


def _summary_payload() -> str:
    body = SIDECAR.split("def _summary(", 1)[1]
    return body.split("@staticmethod", 1)[0]


def test_the_jobs_payload_carries_the_saved_group():
    """The whole "groups reset" bug: written to disk, never sent back."""
    payload = _summary_payload()
    assert '"group": str(job.manifest.get("group", "") or "")' in payload, (
        "without this the renderer re-infers a group from the title every refresh"
    )


def test_the_group_is_read_from_the_same_key_set_job_group_writes():
    writer = (ROOT / "lecturepack" / "electron_backend.py").read_text(encoding="utf-8")
    fn = writer.split("def set_job_group(", 1)[1].split("\ndef ", 1)[0]
    assert 'man["group"] = group' in fn
    # Clearing a group must fall back to the derived default, not persist "".
    assert 'man.pop("group", None)' in fn
    assert '"group"' in _summary_payload()


def test_an_explicit_group_wins_over_the_inferred_one():
    fn = APP_JS.split("function jobGroup(", 1)[1].split("\n  }", 1)[0]
    assert "job.group" in fn
    assert fn.index("job.group") < fn.index("inferredJobGroup")


# ------------------------------------------------------------------ collapse

def _fn(name: str) -> str:
    body = APP_JS.split("function " + name + "(", 1)[1]
    return body.split("\n  function ", 1)[0]


def test_collapse_state_is_keyed_by_group_name_not_by_job():
    """Adding a lecture to a collapsed course must not reopen it."""
    fn = _fn("toggleGroupCollapsed")
    assert "state[name]" in fn
    assert "COLLAPSED_GROUPS_KEY" in fn
    assert "renderJobs()" in fn, "the toggle must repaint, not wait for a refresh"


def test_collapse_survives_a_restart():
    assert "lecturepack.home.collapsedGroups" in APP_JS
    fn = _fn("collappsedGroups") if "collappsedGroups" in APP_JS else _fn("collapsedGroups")
    assert "browserStorage().getItem" in fn
    # A corrupt or missing value must not blank Home.
    assert "catch (e) { return {}; }" in fn


def test_a_collapsed_group_drops_its_cards_rather_than_hiding_them():
    render = APP_JS.split("var collapsed = collapsedGroups();", 1)[1]
    render = render.split("data-group-toggle]", 1)[0]
    assert "shut ? '' :" in render, (
        "hiding with CSS keeps ~50 cards in layout, defeating the purpose"
    )
    assert 'data-collapsed="true"' in render


def test_the_toggle_is_reachable_and_announced():
    render = APP_JS.split("var collapsed = collapsedGroups();", 1)[1]
    assert "<button" in render, "a real button, so it is in the tab order"
    assert "aria-expanded=" in render
    assert "aria-label=" in render, "a glyph-only control needs a name"
    rule = CSS.split(".lib-group-toggle{", 1)[1].split("}", 1)[0]
    assert "cursor:pointer" in rule
    focus = CSS.split(".lib-group-toggle:focus-visible{", 1)[1].split("}", 1)[0]
    assert "var(--blue)" in focus, "app-wide focus convention"


@pytest.mark.parametrize("banned", ["transition", "animation", "will-change"])
def test_the_toggle_obeys_AD_20(banned):
    rule = CSS.split(".lib-group-toggle{", 1)[1].split("\n.lib-group[data-collapsed", 1)[0]
    assert banned not in rule
