"""Regression cover for the 2.0.9 adversarial stress test (F-01 .. F-38).

Most of these are static-source assertions in the established style: the
shipped UI has no build step, so app.js / app.css / index.html ARE the
artifact and asserting against them is asserting against what ships. The
behavioural ones (job lifecycle, transcript corrections) drive the real
Python objects instead.

Every test names the finding it covers and states the failure it prevents,
because the value here is not "this string exists" -- it is "this specific
lie cannot be told again".
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
HTML = (UI / "index.html").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "app.css").read_text(encoding="utf-8")
SIDECAR = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")
MAIN = (ROOT / "electron-spike" / "production-main.js").read_text(encoding="utf-8")
TASKS = (ROOT / "ai-gateway" / "src" / "tasks.js").read_text(encoding="utf-8")


def block(text: str, start: str, end: str) -> str:
    assert start in text, start
    rest = text.split(start, 1)[1]
    assert end in rest, end
    return rest.split(end, 1)[0]


# --------------------------------------------------------------------------- #
# F-01 / F-02 / F-08 -- the breadcrumb
# --------------------------------------------------------------------------- #
def test_f01_breadcrumb_hides_the_lecture_segment_when_there_is_no_lecture() -> None:
    """"Home > Home": the left segment fell back to the literal "Home"."""
    setter = block(JS, "function setCrumbJob(name)", "\n  }")
    assert "btn.hidden = !has" in setter
    assert "sep.hidden = !has" in setter
    # The reset path must clear it, not write another screen name into it.
    assert "setCrumbJob('')" in JS
    # Both segments start hidden so the design-time value never flashes.
    assert 'id="lecture-switcher-toggle" type="button" hidden' in HTML
    assert 'id="crumb-sep" hidden' in HTML


def test_f02_every_screen_has_a_capitalised_crumb() -> None:
    """`demo` was missing from CRUMBS and rendered as its own route id."""
    crumbs = block(JS, "var CRUMBS = {", "};")
    screens = set()
    for chunk in HTML.split('data-screen="')[1:]:
        screens.add(chunk.split('"', 1)[0])
    for screen in screens:
        assert "%s:" % screen in crumbs, "screen %r has no breadcrumb label" % screen
    # Labels are prose, never a bare lowercase route id.
    for part in crumbs.split(","):
        if ":" not in part:
            continue
        label = part.split(":", 1)[1].strip().strip("'")
        if label:
            assert label[0].isupper(), label


# --------------------------------------------------------------------------- #
# F-04 / F-05 -- scrollable regions must not read as clipped
# --------------------------------------------------------------------------- #
def test_f04_f05_scrollbar_thumb_is_visible_at_rest() -> None:
    """A fully transparent thumb made every overflow look like a clip."""
    thumb = block(CSS, "::-webkit-scrollbar-thumb{", "}")
    assert "background:transparent" not in thumb, (
        "the resting thumb is invisible again, so below-fold content reads as cut off"
    )
    assert "background:var(--line)" in thumb


def test_f04_cheat_sheet_scrolls_its_list_not_its_panel() -> None:
    assert "max-height:calc(100vh - 80px);display:flex;flex-direction:column" in HTML
    body = block(CSS, "#shortcuts-body{", "}")
    assert "overflow-y:auto" in body
    assert "min-height:0" in body
    assert "scrollbar-gutter:stable" in body


# --------------------------------------------------------------------------- #
# F-03 -- Study with no lecture
# --------------------------------------------------------------------------- #
def test_f03_study_has_a_real_empty_state() -> None:
    """studyV2Load() returns early with no job, so the design-time chrome
    ("Ready to study", "Your progress 0%", two live CTAs) stayed on screen."""
    assert 'id="study-empty"' in HTML
    assert "Nothing to study yet" in HTML
    load = block(JS, "function studyV2Load() {", "lpBridge.call('study_v2_status'")
    assert load.count("studyV2ShowEmpty(true)") == 2, (
        "both no-bridge and no-job returns must paint the empty state"
    )
    assert "studyV2ShowEmpty(false)" in load
    empty = block(JS, "function studyV2ShowEmpty(empty)", "\n  }")
    assert "b.disabled = !!empty" in empty


# --------------------------------------------------------------------------- #
# F-06 -- a disabled control must look and sound disabled
# --------------------------------------------------------------------------- #
def test_f06_disabled_controls_lose_their_signal_fill() -> None:
    """45%-opacity orange is still the loudest thing on the screen."""
    off = block(CSS, ".lp-ctl-off{", "}")
    assert "background:var(--secondary-surface) !important" in off
    assert "pointer-events:none" in off
    assert "el.classList.toggle('lp-ctl-off', !enabled)" in JS


def test_f06_a_disabled_control_says_why_when_clicked() -> None:
    """Chromium does not dispatch click on a disabled button, and never shows
    its title either -- so the reason was unreachable by any route."""
    speech = block(JS, "function wireDisabledControlSpeech()", "\n   }")
    assert "data-ctl-tip" in speech
    assert "toast(hit.title" in speech
    # Must not answer for a control something else is covering.
    assert "top.contains(hit)" in speech
    assert "wireDisabledControlSpeech();" in JS


# --------------------------------------------------------------------------- #
# F-10 -- the footer's right slot belongs to the runtime
# --------------------------------------------------------------------------- #
def test_f10_a_finished_stage_gives_the_right_slot_back() -> None:
    """Review sat at "Ready to export" with "Detecting slides" pinned beside it."""
    assert "function restoreStatusRight()" in JS
    assert "if (!running) restoreStatusRight();" in JS
    # A late status payload must not re-pin the stage name.
    guard = block(JS, "if (s.right !== undefined) {", "\n      }")
    assert "LP.state.pipelineRunning" in guard


# --------------------------------------------------------------------------- #
# F-12 -- the cheat sheet must not misstate its own bindings
# --------------------------------------------------------------------------- #
def test_f12_cheat_sheet_says_j_and_k_advance() -> None:
    review = block(JS, "{ title: 'Review', items: [", "] }")
    assert "{ keys: ['J'], what: 'Keep the slide and move on' }" in review
    assert "{ keys: ['K'], what: 'Reject the slide and move on' }" in review


# --------------------------------------------------------------------------- #
# F-13 / F-14 -- import feedback
# --------------------------------------------------------------------------- #
def test_f13_the_banner_does_not_claim_an_import_during_file_selection() -> None:
    begin = block(JS, "function beginBrowseImport()", "\n    }")
    assert "'Waiting for you to choose'" in begin
    assert "Import cancelled" in begin


def test_f14_rejected_files_are_reported_not_swallowed() -> None:
    """expandImportPaths knows exactly why each path was refused; that array
    used to be destructured away."""
    assert "const { mediaFiles, failures } = expandImportPaths(paths);" in MAIN
    assert "Object.assign({}, result, { skipped: failures })" in MAIN
    # Both vocabularies reach the modal: the host's `skipped` and the
    # sidecar's own per-file `failures`.
    assert "(d.failures || []).concat(d.skipped || [])" in JS
    assert "batchSkipped" in JS


# --------------------------------------------------------------------------- #
# F-15 -- multi-link import
# --------------------------------------------------------------------------- #
def test_f15_links_separated_by_any_whitespace_are_separate_links() -> None:
    """"https://a https://b" passed the old regex as ONE url, and the second
    lecture was discarded without a word."""
    fn = block(JS, "function mediaUrls(text)", "\n  }")
    assert "split(/\\s+/)" in fn
    check = block(JS, "{ label: 'Check link', primary: true", "keep the dialog open")
    assert "/^https?:\\/\\/\\S+$/i" in check, "the validity test still spans whitespace"
    # The sidecar must agree, or a string payload re-merges them.
    assert "raw_urls = raw_urls.split()" in SIDECAR


def test_f15_a_slow_probe_is_visible_and_bounded() -> None:
    check = block(JS, "{ label: 'Check link', primary: true", "keep the dialog open")
    assert "if (mediaLink.probing) return true;" in check
    assert "setLinkChecking(true)" in check
    assert "did not answer in time" in check


# --------------------------------------------------------------------------- #
# F-16 / F-19 -- job status
# --------------------------------------------------------------------------- #
def test_f16_running_means_a_stage_is_actually_active() -> None:
    """"not every stage is done" is true of a job that never started, which is
    how one lecture showed Processing, Queued and IDLE at the same time."""
    assert "var stageActive = Array.isArray(p.stages)" in JS
    assert "state === 'running' || state === 'active'" in JS
    assert "var running = stageActive && !terminalByList;" in JS
    assert "p.stages.some(function (st) { return st && st.state !== 'done'; })" not in JS


def test_f19_process_has_a_state_for_jobs_that_stopped() -> None:
    """renderProcessJobState fell through to hiding its banner for
    interrupted/failed/cancelled, so the switcher looked like it refused to
    land on them."""
    fn = block(JS, "function renderProcessJobState()", "\n  }")
    for status in ("interrupted", "failed", "cancelled"):
        assert "'%s'" % status in fn, status
    assert 'id="btn-proc-restart"' in HTML


# --------------------------------------------------------------------------- #
# F-18 -- no raw errno reaches the student
# --------------------------------------------------------------------------- #
def test_f18_ffmpeg_exit_codes_are_translated() -> None:
    wrapper = (ROOT / "lecturepack" / "infrastructure" / "ffmpeg_wrapper.py").read_text(
        encoding="utf-8"
    )
    # _handle_finished is the last method in the file.
    finished = wrapper.split("def _handle_finished(self, exit_code, exit_status):", 1)[1]
    assert "self._source_has_audio" in finished
    assert "no audio track" in finished
    assert 'self.finished.emit(False, message)' in finished
    # The raw text is kept, but for the log rather than the pill.
    assert "self.last_error_detail = detail" in finished
    # Defence in depth for jobs that failed under an older build.
    assert "ffmpeg exited with status" in JS


# --------------------------------------------------------------------------- #
# F-20 -- the demo lecture is temporary and must say so
# --------------------------------------------------------------------------- #
def test_f20_the_demo_lecture_announces_that_it_is_temporary() -> None:
    assert '"is_demo": bool(self._is_demo_job(job))' in SIDECAR
    assert "j.is_demo ?" in JS
    assert "Demo \\u00b7 temporary" in JS or "Demo · temporary" in JS
    handler = block(JS, "lpBridge.on('demo_session', function (json)", "});")
    assert "d.status !== 'cleaned'" in handler
    assert "temporary sample" in handler


def test_f20_demo_session_is_a_declared_contract_signal() -> None:
    contract = json.loads(
        (ROOT / "electron-spike" / "contracts" / "electron-bridge-contract.json").read_text(
            encoding="utf-8"
        )
    )
    ops = {op["name"]: op for op in contract["operations"]}
    assert "demo_session" in ops
    assert ops["demo_session"]["direction"] == "event"


# --------------------------------------------------------------------------- #
# F-29 / F-30 -- subjects
# --------------------------------------------------------------------------- #
def test_f29_entering_a_subject_drops_the_previous_lecture_content() -> None:
    """Only the res.ok branch replaced studyV2.content, so a failed prepare
    left the last LECTURE's material under the SUBJECT's header."""
    fn = block(JS, "function studyV2GroupLoad(groupName, opts)", "lpBridge.call('study_v2_group_prepare'")
    assert "studyV2.content = { concepts: [], flashcards: [], quiz: []" in fn
    assert "studyV2.progress = { concepts: {}" in fn
    assert "renderStudyV2Overview();" in fn


def test_f29_rebuild_map_reports_both_outcomes() -> None:
    assert "Subject map rebuilt from" in JS
    assert "The subject map could not be rebuilt." in JS


def test_f30_bulk_group_write_updates_the_loaded_job_too() -> None:
    """_set_job_group did this and _set_jobs_group did not, so the open
    lecture's stale in-memory manifest was flushed back over the disk write."""
    fn = block(SIDECAR, "def _set_jobs_group(self", "\n    def ")
    assert 'self.current_job.manifest["group"] = group' in fn
    assert "requested=len(requested)" in fn


def test_f30_the_rename_toast_reports_what_happened() -> None:
    fn = block(JS, "function handleGroupRename(titleEl, oldGroup, fontCss)", "\n  }")
    assert "function announce(moved)" in fn
    assert "moved < asked" in fn
    assert "typeof res.count === 'number' ? res.count : asked" in fn


# --------------------------------------------------------------------------- #
# F-31 + A1 -- the comprehension check
# --------------------------------------------------------------------------- #
def test_f31_a_comprehension_check_can_be_retried() -> None:
    """Grading disabled the field AND the button and wiped the answer, so one
    accidental Enter burned the only attempt for that concept."""
    card = block(JS, "'<div class=\"study-teach-card\">'", "'</div></div>';")
    assert "(grade ? ' disabled' : '')" not in card
    assert "studyV2.teachAnswer" in card
    assert "'Check again'" in card


def test_a1_the_grader_may_not_contradict_its_own_ideal_answer() -> None:
    instruction = block(TASKS, "grade_short_answer: '", "',\n")
    assert "must not contradict your own `ideal_answer`" in instruction
    assert "it is CORRECT and must be credited" in instruction


# --------------------------------------------------------------------------- #
# F-33 -- the export panel must describe what it writes
# --------------------------------------------------------------------------- #
def test_f33_no_format_is_offered_that_is_never_written() -> None:
    """DOCX and TSV were offered; export_service.py has never written either."""
    exporter = (ROOT / "lecturepack" / "services" / "export_service.py").read_text(
        encoding="utf-8"
    )
    formats = block(JS, "exportFormats: [", "],")
    for dead in ("DOCX", "TSV"):
        assert dead not in formats, "%s is offered but never written" % dead
    for key in ("TXT", "SRT", "VTT", "MD", "JSON", "JSONL", "CSV"):
        assert "'%s'" % key in formats, key
        suffix = ".%s" % key.lower()
        assert suffix in exporter, "%s is advertised but %s is never written" % (key, suffix)


def test_f33_the_format_list_does_not_pretend_to_be_a_picker() -> None:
    """align_and_export writes its whole set and never reads the selection."""
    handler = block(JS, "$('export-formats').addEventListener('click'", "});")
    assert "f.sel = !f.sel" not in handler
    assert "Every export writes all of these" in handler
    assert "every export writes all of these" in HTML


# --------------------------------------------------------------------------- #
# F-34 -- the updater
# --------------------------------------------------------------------------- #
def test_f34_the_check_reads_the_contract_the_host_actually_speaks() -> None:
    """checkForUpdates answers {ok, status}; the renderer tested .available
    and .phase, both always undefined, and fell through to
    "Updates are not available in this build." on every outcome."""
    handler = block(JS, "$('btn-check-updates').addEventListener('click'", "\n    });")
    assert "String(result.status || result.phase || '')" in handler
    assert "state === 'uptodate'" in handler
    assert "You’re up to date." in handler


def test_f34_no_timer_may_overwrite_an_answer_that_already_arrived() -> None:
    handler = block(JS, "$('btn-check-updates').addEventListener('click'", "\n    });")
    assert "if (settled || token !== updateCheckToken) return;" in handler
    assert "settled = true;" in handler
    assert "}, 4000);" not in handler, "the 4s timeout that broke the updater is back"
    assert "timed out" in handler


# --------------------------------------------------------------------------- #
# F-36 -- Validate must produce a verdict
# --------------------------------------------------------------------------- #
def test_f36_validate_always_produces_a_verdict() -> None:
    apply_fn = block(JS, "function applyComputeResponse(kind, value)", "\n    }")
    assert "check returned no result." in apply_fn
    assert "not yet benchmarked on this machine" in apply_fn


# --------------------------------------------------------------------------- #
# F-37 -- light-theme contrast
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "needle",
    [
        '<span style="color:var(--orange-ink)">Pack</span>',
        "color:var(--orange-ink);margin-bottom:4px\">Continue</div>",
        "color:var(--blue-ink)\">Lecture timeline</span>",
        "color:var(--blue-ink);margin-bottom:5px\">Transcript",
    ],
)
def test_f37_text_uses_ink_tokens_not_fill_tokens(needle: str) -> None:
    """--orange measures 3.41:1 and --blue 2.15:1 on the light background.
    --orange-ink and --blue-ink measure 4.94 and 5.81 and exist for text."""
    assert needle in HTML


# --------------------------------------------------------------------------- #
# F-38 -- drag auto-scroll
# --------------------------------------------------------------------------- #
def test_f38_auto_scroll_survives_the_pointer_leaving_the_container() -> None:
    """The edge zone reaches 72px past the container, which puts the pointer
    over the status footer -- containerAt returned null and scrolling stopped
    exactly where it was needed."""
    update = block(JS, "update: function (clientX, clientY) {", "ensureRunning();")
    assert "if (!el && target) el = target;" in update


# --------------------------------------------------------------------------- #
# F-32 -- the host must not die silently
# --------------------------------------------------------------------------- #
def test_f32_the_main_process_logs_instead_of_vanishing() -> None:
    """An unhandled rejection terminates the process on modern Node, which is
    exactly the shape of an unreproducible whole-app disappearance."""
    assert "process.on('unhandledRejection'" in MAIN
    assert "process.on('uncaughtException'" in MAIN
    assert "unhandled_rejection" in MAIN
    assert "uncaught_exception" in MAIN


# --------------------------------------------------------------------------- #
# F-17 -- behavioural: a terminal verdict survives recomputation and restart
# --------------------------------------------------------------------------- #
def _new_job(tmp_path, session=None):
    from lecturepack.models.job import Job

    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake")
    return Job(str(tmp_path / "data"), video_path=str(video), current_session_id=session)


def test_f17_a_failure_on_review_ready_is_not_recomputed_away(tmp_path) -> None:
    """The exact shape of the bug.

    all_statuses in set_stage_status deliberately EXCLUDES STAGE_REVIEW_READY.
    So failing there set overall_status='failed' on that call, and the very
    next stage write recomputed over a table in which nothing had failed and
    landed in the else branch: 'pending'. The failure was gone, and after a
    restart the job presented as a fresh 'Queued' that was doomed to fail the
    same way.
    """
    from lecturepack.models.job import STAGES, STAGE_REVIEW_READY

    job = _new_job(tmp_path, session="s1")
    job.set_stage_status(STAGE_REVIEW_READY, "failed", error="ffmpeg said no")
    assert job.state["overall_status"] == "failed"

    other = next(s for s in STAGES if s != STAGE_REVIEW_READY)
    job.set_stage_status(other, "pending")
    assert job.state["overall_status"] == "failed", (
        "a recomputation erased the terminal verdict again"
    )


def test_f17_the_erased_failure_does_not_survive_a_reload(tmp_path) -> None:
    from lecturepack.models.job import Job, STAGES, STAGE_REVIEW_READY

    job = _new_job(tmp_path, session="s1")
    job.set_stage_status(STAGE_REVIEW_READY, "failed", error="ffmpeg said no")
    job.set_stage_status(next(s for s in STAGES if s != STAGE_REVIEW_READY), "pending")
    job_id = job.job_id

    reopened = Job(str(tmp_path / "data"), job_id=job_id, current_session_id="s2")
    assert reopened.state["overall_status"] == "failed", (
        "the job came back from a restart looking like it had never run"
    )


def test_f17_a_cancelled_job_is_equally_sticky(tmp_path) -> None:
    from lecturepack.models.job import STAGES, STAGE_REVIEW_READY

    job = _new_job(tmp_path, session="s1")
    job.set_stage_status(STAGE_REVIEW_READY, "cancelled")
    assert job.state["overall_status"] == "cancelled"
    job.set_stage_status(next(s for s in STAGES if s != STAGE_REVIEW_READY), "pending")
    assert job.state["overall_status"] == "cancelled"


def test_f17_an_explicit_retry_can_still_leave_a_terminal_state(tmp_path) -> None:
    """Stickiness must not trap a job forever: real progress overrides it."""
    from lecturepack.models.job import STAGES, STAGE_REVIEW_READY

    job = _new_job(tmp_path, session="s1")
    job.set_stage_status(STAGE_REVIEW_READY, "failed")
    other = next(s for s in STAGES if s != STAGE_REVIEW_READY)
    job.set_stage_status(other, "running")
    assert job.state["overall_status"] == "running"


def test_f17_the_sidecar_persists_the_failure_before_announcing_it() -> None:
    fn = block(SIDECAR, "def _on_pipeline_failed(self, error: str)", "\n    #")
    assert 'set_lifecycle("failed")' in fn
    assert fn.index("set_lifecycle") < fn.index('"event": "job_failed"'), (
        "the failure is announced before it is recorded"
    )


# --------------------------------------------------------------------------- #
# F-35 -- a save that cannot land must not report success
# --------------------------------------------------------------------------- #
def test_f35_saving_into_an_empty_transcript_raises() -> None:
    """zip() stops at the shorter side: with no saved segments the loop made
    ZERO pairs, save_working rewrote the empties, and the response still said
    saved=true."""
    fn = block(SIDECAR, "def _save_corrections(self", "\n    def ")
    assert "if texts and not segments:" in fn
    assert "if len(texts) != len(segments):" in fn
    # Both guards must precede the zip that silently truncates.
    assert fn.index("if texts and not segments:") < fn.index("zip(segments, texts)")
    assert fn.index("if len(texts) != len(segments):") < fn.index("zip(segments, texts)")


def test_f35_the_caret_is_not_offered_without_a_saved_transcript() -> None:
    fn = block(JS, "function renderReviewTranscript()", "\n  }")
    assert "var editable = !!(LP.data.transcript && LP.data.transcript.segments > 0)" in fn
    assert "contenteditable=\"' + (editable ? 'true' : 'false') + '\"" in fn
    assert "hasSlides && hasTranscript" in JS
