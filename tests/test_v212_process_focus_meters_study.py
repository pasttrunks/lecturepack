"""2.1.2 — the things reported against the shipped 2.1.1 build.

Reported after installing 2.1.1 on a second, previously-unused laptop.

Two of these are the SAME shape as bugs already in the ledger, arriving back
because the earlier fix landed on a narrower surface than the report:

* BUG-63 re-opens BUG-62. Process does follow the running lecture -- but only
  through the code path that CHANGES screen. The student who is already on
  Process (because clicking a queue row put them there) clicks the Process nav
  and gets nothing, because ``setScreen`` returns immediately when the screen
  is unchanged.
* BUG-65 re-opens BUG-08. The workspace does snapshot and restore per lecture
  -- but the Ask feed was never part of the workspace, and the thing being
  cleared on a lecture switch (``LP.state.chat``) belongs to the chat surface
  Study V2 replaced. The fix was applied to a surface that stopped being used.

The UI half is asserted against app.js source, which IS the shipped artifact
(no build step). The engine half is driven for real.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")


def block(text: str, start: str, end: str) -> str:
    assert start in text, start
    rest = text.split(start, 1)[1]
    assert end in rest, end
    return rest.split(end, 1)[0]


# --------------------------------------------------------------------------- #
# BUG-63 — Process ignored the nav button when it was already the open screen
# --------------------------------------------------------------------------- #
def test_bug63_reselecting_process_still_follows_the_running_lecture() -> None:
    """Fails against 2.1.1, whose setScreen opened with a bare
    ``if (LP.state.screen === name) return;`` -- so the follow ran on entry to
    Process and never again."""
    guard = block(JS, "function setScreen(name) {", "LP.motion.nav")
    assert "if (LP.state.screen === name) return;" not in guard, (
        "the bare early return is back; the Process nav is a dead click for "
        "anyone already on Process"
    )
    assert "followActiveProcessingJob()" in guard


def test_bug63_a_carried_lecture_is_still_never_overridden() -> None:
    """The BUG-62 contract survives: clicking a queue row lands on THAT
    lecture, including on the re-selection path added here."""
    guard = block(JS, "function setScreen(name) {", "LP.motion.nav")
    assert "!_screenChangeCarriesJob" in guard
    # Both the entry path and the re-selection path are guarded.
    assert JS.count("!_screenChangeCarriesJob) followActiveProcessingJob();") == 2


def test_bug63_entrance_motion_still_does_not_replay() -> None:
    """The reason the early return existed at all."""
    guard = block(JS, "function setScreen(name) {", "LP.motion.nav")
    assert "return;" in guard


# --------------------------------------------------------------------------- #
# BUG-64 — every Study answer repainted the whole screen
# --------------------------------------------------------------------------- #
def test_bug64_recording_an_answer_does_not_reload_the_whole_study_screen() -> None:
    """Fails against 2.1.1: both record calls chained into studyV2Load(),
    which rebuilds the scope header, the generation state, the overview AND
    the active pane -- wiping the "Correct" feedback written a line earlier
    and repainting it a moment later. That is the flash."""
    import re

    sites = [m for m in re.finditer(
        r"lpBridge\.call\('(study_v2_record_quiz|study_v2_record_flashcard)'", JS)]
    assert len(sites) == 5, "record call sites moved; re-check every one"
    refreshing = 0
    for site in sites:
        tail = JS[site.end():site.end() + 700]
        body = tail.split("catch", 1)[0]
        assert "studyV2Load()" not in body, (
            "%s reloads all Study content again; recording an answer changes "
            "progress, never content" % site.group(1)
        )
        if "studyV2RefreshProgress()" in body:
            refreshing += 1
    # The two graded surfaces (quiz, flashcards) refresh mastery; the three
    # Quick Study sites already recorded fire-and-forget and still do.
    assert refreshing == 2


def test_bug64_the_progress_refresh_leaves_the_active_pane_alone() -> None:
    fn = block(JS, "function studyV2RefreshProgress()", "\n  }\n")
    assert "studyV2.progress = res.progress" in fn
    assert "if (studyV2.mode === 'overview') renderStudyV2Overview();" in fn, (
        "the pane the student is mid-interaction with must not be rebuilt "
        "under their click"
    )
    for pane in ("renderStudyQuiz()", "renderStudyFlashcards()", "renderStudyTeach()"):
        assert pane not in fn, pane


def test_bug64_the_refresh_keeps_the_in_flight_owner_guard() -> None:
    """A late response for the previous lecture must not repaint this one --
    the same guard studyV2Load carries."""
    fn = block(JS, "function studyV2RefreshProgress()", "\n  }\n")
    assert "LP.state.jobId !== requestedJobId" in fn
    assert "res.job_id !== requestedJobId" in fn


# --------------------------------------------------------------------------- #
# BUG-65 — Ask showed the previous lecture's conversation
# --------------------------------------------------------------------------- #
def test_bug65_the_ask_feed_is_snapshotted_and_restored_per_lecture() -> None:
    """Fails against 2.1.1, where setActiveJob cleared LP.state.chat (the
    superseded chat surface) and never touched #study-ask-feed at all."""
    fn = block(JS, "function setActiveJob(id, title) {", "renderJobSwitcher();")
    assert "askFeedSnapshot()" in fn, "the outgoing lecture's Ask history is discarded"
    assert "restoreAskFeed(" in fn, "the incoming lecture's Ask history is never restored"


def test_bug65_a_lecture_with_no_history_opens_blank() -> None:
    fn = block(JS, "function restoreAskFeed(html, hasLecture) {", "\n  }")
    assert "feed.innerHTML = html || '';" in fn
    assert "hasLecture &&" in fn, (
        "suggestion chips inviting 'Explain this lecture simply' with NO "
        "lecture loaded is BUG-58 again"
    )


def test_bug65_an_interrupted_stream_is_not_frozen_into_the_snapshot() -> None:
    """Coming back an hour later, that answer is never arriving."""
    fn = block(JS, "function askFeedSnapshot() {", "\n  }")
    assert "study-ask-thinking" in fn
    assert "interrupted" in fn


def test_bug65_a_stream_in_flight_does_not_follow_the_student() -> None:
    fn = block(JS, "function setActiveJob(id, title) {", "renderJobSwitcher();")
    assert "studyV2.askStreaming = false;" in fn


def test_bug65_the_ask_feed_has_no_per_element_listeners_to_lose() -> None:
    """restoreAskFeed reinstates markup, so everything inside the feed must be
    bound by delegation. If this ever fails, the snapshot has to become a real
    message model instead of markup."""
    fn = block(JS, "function studyAskSend()", "\n  }")
    assert "addEventListener" not in fn
    fn = block(JS, "function appendStudyAskSources(sources, provenance) {", "\n  }")
    assert "addEventListener" not in fn


# --------------------------------------------------------------------------- #
# BUG-66 — the meters did not correspond to the live log
# --------------------------------------------------------------------------- #
def _stub_controller(source):
    from lecturepack.controllers.job_controller import JobController

    seen = []
    ctl = JobController.__new__(JobController)
    ctl._transcribe_pct = 0
    ctl.job = type("J", (), {"source": source})()
    ctl.stage_progress = type("S", (), {"emit": staticmethod(
        lambda name, pct: seen.append((name, pct)))})()
    return ctl, seen


def test_bug66_transcribe_reports_progress_from_real_segment_timestamps() -> None:
    """Transcribe emitted NO stage_progress at all in 2.1.1: only Detect
    Slides and Export were wired to a worker progress signal, so the meter sat
    at 0 for the whole run while the transcript log streamed."""
    from lecturepack.controllers.job_controller import STAGE_TRANSCRIBE

    ctl, seen = _stub_controller({"duration": 600.0})

    ctl._emit_transcribe_progress({"end_ms": 60_000})
    ctl._emit_transcribe_progress({"end_ms": 300_000})
    assert seen == [(STAGE_TRANSCRIBE, 10), (STAGE_TRANSCRIBE, 50)]

    # Out-of-order segments (the chunked online backend uploads slices
    # concurrently) must not run the bar backwards.
    ctl._emit_transcribe_progress({"end_ms": 120_000})
    assert seen == [(STAGE_TRANSCRIBE, 10), (STAGE_TRANSCRIBE, 50)]

    # Never claims completion; _on_stage_finished writes the 100.
    ctl._emit_transcribe_progress({"end_ms": 10_000_000})
    assert seen[-1] == (STAGE_TRANSCRIBE, 99)


@pytest.mark.parametrize("source", [{"duration": 0.0}, {"duration": None}, {}])
def test_bug66_no_duration_means_no_invented_percent(source) -> None:
    """A guessed bar is worse than a still one: it reports work not done."""
    ctl, seen = _stub_controller(source)
    ctl._emit_transcribe_progress({"end_ms": 60_000})
    assert seen == []


def test_bug66_a_segment_with_no_timestamp_is_ignored() -> None:
    ctl, seen = _stub_controller({"duration": 600.0})
    ctl._emit_transcribe_progress({"text": "hello"})
    ctl._emit_transcribe_progress(None)
    assert seen == []


def test_bug66_the_relay_still_forwards_every_segment_unchanged() -> None:
    """Deriving progress must not filter or mutate the transcript stream."""
    ctl, _seen = _stub_controller({"duration": 600.0})
    relayed = []
    ctl.transcript_segment = type("S", (), {"emit": staticmethod(relayed.append)})()
    seg = {"end_ms": 60_000, "text": "hello"}
    ctl._handle_transcript_segment(seg)
    ctl._handle_transcript_segment(seg)          # duplicate pct, still relayed
    assert relayed == [seg, seg]


def test_bug66_slide_detection_keeps_headroom_for_its_untimed_tail() -> None:
    """The sampling scan used to reach 100% and then dedup + full-resolution
    capture ran on, streaming log lines beside a pinned meter."""
    from lecturepack.infrastructure import cv_engine

    assert cv_engine.SCAN_PCT < cv_engine.DEDUP_PCT < 100
    src = (ROOT / "lecturepack" / "infrastructure" / "cv_engine.py").read_text(
        encoding="utf-8")
    # The scan loops scale to SCAN_PCT, not to 100.
    assert src.count("* SCAN_PCT)") == 2, "a scan loop still runs the bar to 100"
    # The tail reports too, on both decode paths.
    assert src.count("self.progress.emit(DEDUP_PCT") >= 1
    assert src.count("self.progress.emit(100)") == 2, (
        "100 belongs at the END of detection, once per decode path"
    )


# --------------------------------------------------------------------------- #
# BUG-67 — the installer's task checkbox was clipped on a scaled display
# --------------------------------------------------------------------------- #
def test_bug67_the_wizard_is_not_sized_to_the_millimetre() -> None:
    """Inno's Setup binary is SYSTEM DPI aware only (its manifest carries
    <dpiAware>true</dpiAware> and no PerMonitorV2), so on a scaled display the
    fonts stop fitting the control rectangles measured for them. The .iss
    cannot change that manifest; it can stop the page being sized exactly to
    the captions it happens to contain.

    Not confirmed on the reporting machine -- see BUG-67 in BUG_LIST.md.
    """
    iss = (ROOT / "app" / "packaging" / "lecturepack.iss").read_text(encoding="utf-8")
    assert "WizardSizePercent=120" in iss, (
        "captions are back to having no headroom over their measured width"
    )
    # WizardResizable was tried and removed: this Inno version compiles it to
    # "obsolete and ignored". A directive that only produces a build warning is
    # worse than none, because it reads like a mitigation that is in place.
    directives = [ln for ln in iss.splitlines() if ln and not ln.startswith(";")]
    assert not any("WizardResizable" in ln for ln in directives)


def test_bug67_the_wizard_artwork_is_supplied_at_every_dpi_size() -> None:
    """The same system-DPI-awareness limit that clips captions also resamples
    the banner. Inno picks the closest supplied size, so supply them all."""
    packaging = ROOT / "app" / "packaging"
    iss = (packaging / "lecturepack.iss").read_text(encoding="utf-8")
    assert "WizardImageFile=" in iss and "WizardSmallImageFile=" in iss
    assert "WizardImageStretch=no" in iss, "stretching can only soften artwork"
    assert "DisableWelcomePage=no" in iss, (
        "modern style hides the welcome page, which is where the banner lives"
    )
    for name in iss.split("WizardImageFile=", 1)[1].split("\n", 1)[0].split(","):
        assert (packaging / name.strip()).is_file(), name
    small = iss.split("WizardSmallImageFile=", 1)[1].split("\n", 1)[0]
    for name in small.split(","):
        assert (packaging / name.strip()).is_file(), name
    assert len(small.split(",")) == 6
