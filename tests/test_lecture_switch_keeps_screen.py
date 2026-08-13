"""Changing WHICH lecture you view must not change WHAT you are looking at.

Reported: "changing source somewhere changes source but also moves me to a
different tab, which is not good."

`selectJob` calls `applyResumeState`, which restores the INCOMING lecture's
last-viewed screen. Every caller passes an explicit `opts.screen` except the
header switcher (`selectJob(jobs[next].id, {})` in selectAdjacentJob), so
switching lecture while reading Study dropped the student into whatever screen
that other lecture was last left on -- Review, Transcript, Process.

The resume behaviour itself is wanted: opening a lecture from Home should
return you where you left it. So the restore is now conditional on not already
being in a workspace screen, rather than removed.
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    body = APP_JS.split("function " + name + "(", 1)[1]
    return body.split("\n  function ", 1)[0]


def test_resume_does_not_renavigate_while_already_in_a_workspace_screen():
    fn = _fn("applyResumeState")
    assert "alreadyInWorkspace" in fn
    assert "!alreadyInWorkspace" in fn, (
        "the screen restore must be gated on not already working in a lecture"
    )
    # Guarded on the CURRENT screen, not the incoming state's screen.
    assert "var current = LP.state.screen" in fn


@pytest.mark.parametrize("screen", ["home", "settings"])
def test_opening_a_lecture_from_outside_the_workspace_still_resumes(screen):
    """The feature this guard must not break: Continue, from Home."""
    fn = _fn("applyResumeState")
    assert f"current !== '{screen}'" in fn, (
        f"{screen} is not a workspace screen, so resume must still apply there"
    )


def test_the_other_resume_state_still_applies_on_every_switch():
    """Only the SCREEN is suppressed; slide, study tab and scroll still restore."""
    fn = _fn("applyResumeState")
    for restored in ("state.studyTab", "state.viewingSlide", "state.transcriptScroll"):
        assert restored in fn
        # None of these may be inside the alreadyInWorkspace guard, which closes
        # immediately after setScreen.
        assert fn.index(restored) > fn.index("setScreen(state.screen)")


def test_the_switcher_is_still_the_only_caller_without_an_explicit_screen():
    """If a new caller omits opts.screen, it inherits this behaviour silently.

    Pinning the count makes that a decision rather than an accident.
    """
    calls = [line for line in APP_JS.splitlines()
             if "selectJob(" in line and "function selectJob" not in line]
    implicit = [line.strip() for line in calls
                if "screen:" not in line]
    # selectAdjacentJob's `{}` and the silent auto-follow.
    assert len(implicit) == 2, f"unexpected implicit-screen selectJob calls: {implicit}"
    assert any("{}" in line for line in implicit)
    assert any("silent: true" in line for line in implicit)
