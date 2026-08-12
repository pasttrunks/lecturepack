"""Focused renderer regressions for the LecturePack 2.0.1 polish pass."""

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
    assert "checklistReady" in JS
    assert "lpBridge.call('acknowledge_setup')" in JS

    assert "title: 'Reset LecturePack?'" in JS
    assert "This will permanently remove LecturePack jobs, Study progress, downloaded" in JS
    assert "LecturePack media, settings, and app history." in JS
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


def test_guided_tour_uses_authoritative_eligibility_and_cleans_demo() -> None:
    assert 'id="glowing-demo-card"' in HTML
    assert "Polar Bears 10s Demo.mp4" in HTML
    assert "guided_tour" in JS
    assert "setEligibility" in JS
    availability = function_block(JS, "function renderDemoHomeAvailability()", "function stageLabel")
    assert "jobsEmpty" not in availability
    assert "firstRun" not in availability

    assert "endGuidedDemo('tour_exit')" in JS
    assert "endGuidedDemo('tour_complete')" in JS
    replay = function_block(JS, "$('btn-replay-tour').addEventListener", "var demoCard")
    assert "startGuidedTour(true)" in replay
    assert "startGuidedDemo()" not in replay
    assert "set_guided_tour_state" in JS
    assert "markTourSeen('skipped')" in JS
    assert "markTourSeen('completed')" in JS
    assert "replay_guided_tour" in JS


def test_guided_demo_waits_for_import_action_and_handles_hidden_card() -> None:
    start = function_block(JS, "function startGuidedDemo()", "function endGuidedDemo")
    assert "Opening the tour is not consent" in start
    assert "startGuidedTour(true);" in start
    assert "guidedDemoFlow.beginAttempt();" in start
    assert "renderGuidedTour();\n      return;" in start

    load_jobs = function_block(JS, "$('btn-load-jobs').addEventListener", "var ONB_ACTIVE_STYLE")
    assert "startGuidedTour(true); return;" in load_jobs
    assert "flyDemoTileToDropzone(startGuidedDemo)" in load_jobs

    drop = function_block(JS, "function useDroppedDemo()", "/* ======================= Smart Study")
    assert "startGuidedTour(true)" in drop
    assert "if (started) useDroppedDemo();" in drop
    assert "guidedDemoFlow.imported()" not in drop

    fly = function_block(JS, "function flyDemoTileToDropzone(done)", "function hasDemoDrag")
    assert "closest('[hidden]')" in fly
    assert "!from.width || !from.height || !to.width || !to.height" in fly
    assert "animationend" in fly


def test_guided_demo_cleanup_dismisses_stale_tour_overlay() -> None:
    cleanup = function_block(JS, "function dismissGuidedDemoAfterCleanup()", "function receiveDemoEvent")
    assert "guidedTour.exit()" in cleanup
    assert "guidedDemoFlow.exit()" in cleanup
    assert "setScreen('home')" in cleanup

    receive = function_block(JS, "function receiveDemoEvent(value)", "function isTourFormInput")
    assert "event.status === 'cleaned'" in receive
    assert "event.status === 'cleaned' || event.status === 'failed'" in receive
    assert "dismissGuidedDemoAfterCleanup();" in receive

    jobs = function_block(JS, "lpBridge.on('jobs_changed'", "lpBridge.on('active_job'")
    assert "demoTourActive" in jobs
    assert "dismissGuidedDemoAfterCleanup()" in jobs


def test_spotlight_is_a_stable_four_region_hole() -> None:
    for region in ("tour-dim-top", "tour-dim-right", "tour-dim-bottom", "tour-dim-left"):
        assert f'id="{region}"' in HTML
        assert f"setTourDimRect('{region}'" in JS
    spotlight_css = CSS.split("#tour-spotlight-box", 1)[1].split("#guided-tour-card", 1)[0]
    assert "border:" in spotlight_css
    assert "border-radius:" in spotlight_css
    assert "box-shadow:" in spotlight_css
    assert "mask" not in spotlight_css.lower()
    assert "clip-path" not in spotlight_css.lower()


def test_existing_lecture_drag_queues_ids_without_reimporting() -> None:
    assert 'data-existing-job-drag="true"' in JS
    assert "application/x-lecturepack-job-ids" in JS
    assert "createInternalDragGhost" in JS
    assert "queueExistingJobIds" in JS
    assert "lpBridge.call('queue_jobs', { job_ids: unique })" in JS
    assert "lpBridge.call('enqueue_job', id)" in JS
    assert 'id="process-queue-target"' in HTML
    assert 'data-existing-job-drop-target="true"' in HTML


def test_downloads_review_and_timeline_polish_hooks_are_present() -> None:
    assert 'id="downloads-indicator"' in HTML
    assert 'class="lp-download-popover"' in HTML
    assert "positionDownloadsPanel" in JS
    assert "normalizedDownloadStatus" in JS
    assert "download_id" in JS
    assert "legacy_status" in JS
    assert "document.addEventListener('pointerdown'" in JS
    assert 'aria-expanded' in HTML

    assert 'data-view' in JS
    assert ".lp-slide-card" in CSS
    assert "text-overflow:ellipsis" in CSS
    assert "repeat(auto-fill,minmax(min(100%,128px),1fr))" in CSS

    assert "setPointerCapture" in JS
    assert "releasePointerCapture" in JS
    assert "pointerdown" in JS and "pointermove" in JS and "pointerup" in JS
    assert "LP.state.viewingSlide = nearest.slide._i" in JS
    assert "transcriptTimestampSeconds" in JS
    assert "scrollIntoView({ block: 'center' })" in JS


def test_runtime_checklist_render_has_a_defensive_readiness_guard() -> None:
    runtime_render = function_block(JS, "function render(dataChanged, forceCheckingOpen)", "function neutralPanels")
    checklist_render = function_block(JS, "function renderChecklist()", "function renderOffer")
    assert "view.state === 'checklist' && !view.checklistReady" in runtime_render
    assert "eventModel.waitForChecklist()" in runtime_render
    assert "empty.hidden = ready" in checklist_render
