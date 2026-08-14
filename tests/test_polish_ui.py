"""Focused renderer regressions for LecturePack's production UI polish."""

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
HTML = (UI / "index.html").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "app.css").read_text(encoding="utf-8")


def function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def run_runtime_reducer(body: str) -> subprocess.CompletedProcess[str]:
    constants = JS.split("var FIRST_RUN_ROWS = [", 1)[1].rsplit(
        "function RuntimeSetupGateModel()", 1
    )[0]
    reducer = function_block(JS, "function RuntimeSetupGateModel()", "var RuntimeSetupGate")
    program = "var FIRST_RUN_ROWS = [" + constants + "function RuntimeSetupGateModel()" + reducer + body
    return subprocess.run(["node", "-e", program], capture_output=True, text=True)


def test_runtime_setup_is_green_only_and_reset_is_backend_owned() -> None:
    assert 'id="btn-runtime-done"' in HTML
    assert re.search(r'id="btn-runtime-done"[^>]*\bdisabled\b', HTML)
    assert 'id="btn-runtime-exit"' not in HTML
    assert 'id="btn-runtime-continue"' not in HTML
    assert 'id="btn-runtime-skip"' not in HTML
    assert "requiredChecklistReady" in JS
    for check_id in (
        "windows_version",
        "ffmpeg_ffprobe",
        "whisper_runtime",
        "bundled_model",
        "data_directory",
    ):
        assert check_id in JS
    assert "lpBridge.call('acknowledge_setup')" in JS
    assert "title: 'Reset LecturePack?'" in JS
    assert "Original lecture/video files outside LecturePack will not be deleted." in JS
    assert "lpBridge.call('reset_lecturepack')" in JS


def test_healthy_incomplete_bootstrap_waits_before_exposing_checklist() -> None:
    result = run_runtime_reducer(
        r'''
        const gate = RuntimeSetupGateModel();
        let view = gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false, checklist: []});
        if (view.state !== 'checking' || view.checklistReady) process.exit(1);
        if (Object.keys(view.checkProgress).length !== 5) process.exit(2);
        const ready = [
          {id: 'windows_version', verdict: 'ready'},
          {id: 'ffmpeg_ffprobe', verdict: 'ready'},
          {id: 'whisper_runtime', verdict: 'ready'},
          {id: 'bundled_model', verdict: 'ready'},
          {id: 'data_directory', verdict: 'ready'}
        ];
        view = gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false, checklist: ready});
        if (view.state !== 'checklist' || !view.checklistReady) process.exit(3);
        const malformed = RuntimeSetupGateModel();
        malformed.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false, checklist: ready.slice(0, 4)});
        if (malformed.toChecklist().state !== 'checking') process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_demo_uses_authoritative_eligibility_and_self_contained_screen() -> None:
    assert 'id="glowing-demo-card"' in HTML
    assert '<section data-screen="demo"' in HTML
    availability = function_block(JS, "function renderDemoHomeAvailability()", "function stageLabel")
    assert "demoAdmissionAvailable && tourEligibilityAllowsOffer()" in availability
    assert "jobsEmpty" not in availability
    assert "firstRun" not in availability
    assert "function applyGuidedTourEligibility" in JS
    assert "set_guided_tour_state" in JS
    assert "replay_guided_tour" in JS
    replay = function_block(JS, "function replayDemoScreen()", "function endGuidedDemo")
    assert "openDemo(1)" in replay
    assert "runDemoForReal" not in replay
    empty_action = function_block(JS, "$('btn-load-jobs').addEventListener", "var ONB_ACTIVE_STYLE")
    assert "var savedDemo = demoState()" in empty_action
    assert "savedDemo.completed === true ? 1 : (savedDemo.chapter || 1)" in empty_action
    assert "runDemoForReal" not in empty_action


def test_demo_processing_is_real_identity_safe_and_retryable() -> None:
    run = function_block(JS, "function runDemoForReal()", "function bindDemoScreen")
    assert "setOnb(null);" in run
    assert "guidedDemo.starting().attempt" in run
    assert "lpBridge.startDemoJob()" in run
    assert "guidedDemo.isCurrentAttempt(attempt)" in run
    assert run.index("demoCleanupRequested = false") < run.index("guidedDemo.starting()")
    assert run.index("demoCleanupConfirmed = false") < run.index("guidedDemo.starting()")
    receive = function_block(JS, "function receiveDemoEvent(value)", "function wireDemoLifecycle")
    assert "guidedDemo.event(event)" in receive
    assert "if (!handled.accepted) return" in receive
    assert "eventStage === 'review_ready' && LP.state.screen === 'process'" in receive


def test_stacked_review_column_has_a_definite_height() -> None:
    block = CSS.split("@media (max-width:1220px)", 1)[1].split(chr(10) + "}", 1)[0]
    assert ".lp-review-col-slides{height:230px}" in block.replace(" ", "")
    assert ".lp-review-col-slides{max-height" not in block.replace(" ", "")


def test_existing_lecture_drag_queues_ids_without_reimporting() -> None:
    assert 'data-existing-job-drag="true"' in JS
    assert "application/x-lecturepack-job-ids" in JS
    assert "createInternalDragGhost" in JS
    assert "queueExistingJobIds" in JS
    # The request is built up now that a drop can also carry the reprocess
    # opt-in, but it is still one queue_jobs call over the existing IDs --
    # never a re-import.
    assert "var request = { job_ids: unique };" in JS
    assert "lpBridge.call('queue_jobs', request)" in JS
    assert "import_video" not in JS.split("function queueExistingJobIds", 1)[1][:900]
    assert "lpBridge.call('enqueue_job', id)" in JS
    assert 'id="process-queue-target"' in HTML
    assert 'data-existing-job-drop-target="true"' in HTML


def test_downloads_review_and_timeline_polish_hooks_are_present() -> None:
    assert 'id="downloads-indicator"' in HTML
    assert 'class="lp-download-popover"' in HTML
    assert "positionDownloadsPanel" in JS
    assert "normalizedDownloadStatus" in JS
    assert "document.addEventListener('pointerdown'" in JS
    assert 'aria-expanded' in HTML

    # The Compact/Roomy density toggle is gone: the two modes differed by a
    # 22px thumbnail and neither size was legible. A three-stop size control in
    # the All slides overlay replaces it, and the rail auto-fits its columns.
    # See tests/test_slide_viewer_layout.py.
    assert 'data-slide-size' in JS
    assert ".lp-slide-card" in CSS
    assert 'id="btn-all-slides"' in HTML
    assert 'id="all-slides-overlay"' in HTML
    assert "repeat(auto-fill," in CSS
    assert 'data-state="' in JS and 'data-selected="' in JS
    assert "s.state = 'accepted'; s.sel = true" in JS
    selected_rule = CSS.split('.lp-slide-check[data-checked="true"]', 1)[1].split("}", 1)[0]
    assert "background" not in selected_rule, "selection is a checkbox, not a filled card"
    rejected_rule = CSS.split('.lp-slide-card[data-state="rejected"]', 1)[1].split("}", 1)[0]
    assert "var(--red-soft)" in rejected_rule and "var(--red)" in rejected_rule

    assert "setPointerCapture" in JS
    assert "releasePointerCapture" in JS
    assert "LP.state.viewingSlide = nearest.slide._i" in JS
    assert "transcriptTimestampSeconds" in JS
    assert "scrollIntoView({ block: 'center' })" in JS


def test_runtime_checklist_render_has_a_defensive_readiness_guard() -> None:
    runtime_render = function_block(JS, "function render(dataChanged, forceCheckingOpen)", "function neutralPanels")
    checklist_render = function_block(JS, "function renderChecklist()", "function renderOffer")
    assert "view.state === 'checklist' && !view.checklistReady" in runtime_render
    assert "eventModel.waitForChecklist()" in runtime_render
    assert "empty.hidden = ready" in checklist_render
