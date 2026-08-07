"""Focused contracts for the Beta 15 invalid-state hardening pass (Round 2 audit).

Each check targets one Round-2 defect without a live window: source-level
assertions at the renderer boundary, in the same style as
test_beta15_pc_polish.py. Covered: the Review Keep/Reject crash (N-1), raw
no-job errors (N-2), the dead sample-jobs button (N-3), phantom export
progress (N-4), unsettled terminal status (F-3), job-card navigation (F-4),
toast discipline (N-5), yt-dlp error mapping (N-6), Esc on the tour (N-7),
spotlight orphaning (N-8), the Study empty state (N-9), shortcuts (N-11),
the narrow-width clip (N-12), the runtime overlay's stale repair copy (F-6),
and the tour completion card + group-modal guard (§6/F-2).
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
APP = UI / "app.js"
HTML = UI / "index.html"
CSS = UI / "app.css"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


# --------------------------------------------------------------------------- #
# N-1 (P0): Review controls with no slide must not crash
# --------------------------------------------------------------------------- #
def test_review_keep_reject_are_null_guarded() -> None:
    app = read(APP)
    keep = block(app, "$('btn-keep').addEventListener('click', function () {", "$('btn-reject')")
    reject = block(app, "$('btn-reject').addEventListener('click', function () {", "$('btn-save-corrections')")
    assert "var s = LP.data.slides[LP.state.viewingSlide];" in keep
    assert "if (!s) return;" in keep
    assert "var s = LP.data.slides[LP.state.viewingSlide];" in reject
    assert "if (!s) return;" in reject


def test_review_paging_and_actions_guard_empty_deck() -> None:
    app = read(APP)
    prev = block(app, "$('btn-prev-slide').addEventListener('click', function () {", "$('btn-next-slide')")
    nxt = block(app, "$('btn-next-slide').addEventListener('click', function () {", "$('btn-keep')")
    assert "if (!LP.data.slides.length) return;" in prev
    assert "if (!LP.data.slides.length) return;" in nxt
    save = block(app, "$('btn-save-corrections').addEventListener('click', function () {", "$('btn-repair')")
    repair = block(app, "$('btn-repair').addEventListener('click', function () {", "// transcript")
    assert "if (!LP.state.jobId)" in save
    assert "if (!LP.state.jobId)" in repair


def test_unhandled_rejection_safety_net_toasts_friendly() -> None:
    app = read(APP)
    assert "window.addEventListener('unhandledrejection'" in app
    assert "toast(friendlyErrorMessage(msg));" in app
    assert "window.addEventListener('error'" in app


# --------------------------------------------------------------------------- #
# N-2 (P1): job-dependent controls disable with no job + friendly errors
# --------------------------------------------------------------------------- #
def test_refresh_control_states_disables_job_dependent_controls() -> None:
    app = read(APP)
    refresh = block(app, "function refreshControlStates()", "/* Terminal job states")
    for ctl in ("btn-keep", "btn-reject", "btn-prev-slide", "btn-next-slide",
                "btn-save-corrections", "btn-repair"):
        assert f"setCtl('{ctl}', hasSlides" in refresh
    for ctl in ("btn-export-all", "btn-export-pdf", "btn-export-html"):
        assert f"setCtl('{ctl}', hasJob" in refresh
    for ctl in ("btn-pause-job", "btn-cancel-job"):
        assert f"setCtl('{ctl}', processing" in refresh
    assert "function setCtl(id, enabled, disabledTip)" in app
    assert "el.disabled = !enabled;" in app
    # Re-renderers keep the states current.
    assert app.count("refreshControlStates();") >= 4


def test_no_job_errors_map_to_friendly_messages() -> None:
    app = read(APP)
    mapper = block(app, "function friendlyErrorMessage(raw, command)", "/* yt-dlp stderr")
    assert "no job is loaded" in mapper
    assert "Load a lecture first — there is nothing to process yet." in mapper
    assert "Load a lecture before repairing slide selections." in mapper
    assert "Load a lecture first — there is nothing to export yet." in mapper
    assert "Error invoking remote method" in mapper  # transport wrapper stripped
    # The bridge error channel routes through the mapper, never raw.
    err = block(app, "lpBridge.on('error', function (json) {", "lpBridge.on('diagnostics'")
    assert "toast(friendlyErrorMessage(raw, d.command));" in err
    assert "toast(message)" not in err
    # Process pause/cancel guard the invalid state.
    pause = block(app, "$('btn-cancel-job').addEventListener('click', function () {", "$('btn-resume-job'")
    assert "No lecture is processing right now." in pause


# --------------------------------------------------------------------------- #
# N-4 (P1): failed export clears the progress panel
# --------------------------------------------------------------------------- #
def test_export_does_not_enter_running_until_real_progress() -> None:
    app = read(APP)
    start = block(app, "function startExport()", "/* ======================= updates")
    assert "if (!LP.state.jobId)" in start
    assert "Load a lecture first — there is nothing to export yet." in start
    # No optimistic running phase before the bridge answers.
    assert start.index("lpBridge.call('export_all'") < start.index("LP.state.exportPhase = 'idle'; renderExportPhase();")
    # The error channel resets a failed export to idle.
    err = block(app, "lpBridge.on('error', function (json) {", "lpBridge.on('diagnostics'")
    assert "LP.state.exportPhase === 'running'" in err
    assert "d.command === 'export' || d.stage === 'Export'" in err
    assert "LP.state.exportPhase = 'idle'; renderExportPhase();" in err
    # export_progress remains the only path INTO the running state.
    prog = block(app, "lpBridge.on('export_progress'", "lpBridge.on('export_done'")
    assert "LP.state.exportPhase = 'running'; renderExportPhase();" in prog


# --------------------------------------------------------------------------- #
# F-3 (P1): terminal status settles from one place
# --------------------------------------------------------------------------- #
def test_terminal_status_settles_complete_ready() -> None:
    app = read(APP)
    settle = block(app, "function settleTerminalStatus(kind)", "// Main slide preview")
    assert "label.textContent = 'Complete'" in settle
    assert "right.textContent = 'Ready'" in settle
    assert "setFill('status-bar', 100)" in settle
    assert "'Complete', 'var(--green)'" in settle or "hasJob ? 'Complete' : 'Idle'" in settle
    # status_changed terminal branch paints the settled state directly.
    status = block(app, "lpBridge.on('status_changed'", "lpBridge.on('slides_changed'")
    assert "settleTerminalStatus(terminalLabel === 'failed' || s.label === 'Failed' ? 'failed' :" in status
    assert "pendingProcessingStatus = {};" in status
    assert "lastStatusRenderKey = null;" in status
    assert "statusLabel.textContent = 'Idle'" in status
    # job_completed settles too.
    done = block(app, "lpBridge.on('job_completed'", "lpBridge.on('notification_prefs'")
    assert "settleTerminalStatus('complete');" in done
    # Restored/switched jobs settle from their stored status.
    active = block(app, "function setActiveJob(id, title)", "/* Reject a payload")
    assert "restored.status === 'done') settleTerminalStatus('complete')" in active
    assert "restored.status === 'failed') settleTerminalStatus('failed')" in active
    assert "restored.status === 'cancelled') settleTerminalStatus('cancelled')" in active


def test_jobs_changed_settles_active_terminal_job() -> None:
    """On relaunch active_job legitimately arrives BEFORE jobs_changed, so the
    setActiveJob settle alone cannot fire — the list handler must settle once
    it can confirm the active job's terminal state (verified packaged:
    'Processing - 100%' stuck on a restored completed job without this)."""
    app = read(APP)
    jobs = block(app, "lpBridge.on('jobs_changed'", "// ---- import from a link ----")
    assert "activeEntry.status === 'done') settleTerminalStatus('complete')" in jobs
    assert "activeEntry.status === 'failed') settleTerminalStatus('failed')" in jobs
    assert "activeEntry.status === 'cancelled') settleTerminalStatus('cancelled')" in jobs
    assert "activeEntry.status === 'interrupted') settleTerminalStatus('interrupted')" in jobs


def test_status_changed_ignores_stale_live_replay_for_terminal_job() -> None:
    """The backend replays the restored job's last LIVE status on relaunch and
    no terminal event ever follows. A non-terminal status for a lecture the
    job list already calls terminal is that replay: ignore it and re-settle."""
    app = read(APP)
    status = block(app, "lpBridge.on('status_changed'", "lpBridge.on('slides_changed'")
    gate = status.split("pendingProcessingStatus = Object.assign", 1)[0]
    assert "listEntry.status === 'done' || listEntry.status === 'failed' ||" in gate
    assert "if (listTerminal && !incomingTerminal) {" in gate
    assert "settleTerminalStatus(listTerminal === 'done' ? 'complete' : listTerminal);" in gate
    assert "return;" in gate


# --------------------------------------------------------------------------- #
# F-4 (P1): recent-job cards navigate by job state
# --------------------------------------------------------------------------- #
def test_job_card_click_navigates_by_job_status() -> None:
    app = read(APP)
    grid = block(app, "var card = e.target.closest('[data-job]');", "// Processing queue controls")
    assert "cardJob && cardJob.status === 'done' ? 'review' : 'process'" in grid
    # Selecting is local-first: selectJob switches the workspace and screen
    # synchronously, then fetches payloads via view_job -- so navigation can
    # never hang on the bridge, and opening one job never disturbs another
    # job that is still processing.
    assert "selectJob(jobId, { screen:" in grid


# --------------------------------------------------------------------------- #
# N-3 (P1): the empty-state recovery action runs the guided demo
# --------------------------------------------------------------------------- #
def test_load_sample_jobs_is_now_try_the_demo_lecture() -> None:
    html = read(HTML)
    assert "Try the demo lecture" in html
    assert "Load sample jobs" not in html
    app = read(APP)
    load = block(app, "$('btn-load-jobs').addEventListener('click', function () {", "// Home grid:")
    assert "startGuidedDemo" in load
    assert "setJobsEmpty(false)" not in load


# --------------------------------------------------------------------------- #
# N-5 (P2): toast discipline
# --------------------------------------------------------------------------- #
def test_toasts_auto_dismiss_and_clear_on_navigation() -> None:
    app = read(APP)
    assert "_toastT = setTimeout(dismissToast, 5000);" in app
    assert "function dismissToast()" in app
    screen = block(app, "function setScreen(name) {", "function applyTheme(")
    assert "dismissToast();" in screen


# --------------------------------------------------------------------------- #
# N-6 (P2): yt-dlp errors map to friendly copy with details kept
# --------------------------------------------------------------------------- #
def test_ytdlp_errors_map_friendly() -> None:
    app = read(APP)
    mapper = block(app, "function friendlyLinkError(raw)", "function looksLikeJobId")
    assert "getaddrinfo" in mapper
    assert "We could not reach that link. Check the URL and your internet connection." in mapper
    assert "unsupported url" in mapper.lower()
    assert "That site is not supported. Try a direct video file or a supported video link." in mapper
    assert "sign in" in mapper
    assert "That video requires a sign-in and cannot be imported." in mapper
    probe = block(app, "lpBridge.on('media_probe'", "lpBridge.on('media_progress'")
    assert "friendlyLinkError(info.error)" in probe
    done = block(app, "lpBridge.on('media_done'", "lpBridge.on('job_deleted'")
    assert "friendlyLinkError(r.error)" in done
    assert "<details" in done  # raw technical text behind a Details section


# --------------------------------------------------------------------------- #
# N-7 (P2): Escape dismisses the guided tour
# --------------------------------------------------------------------------- #
def test_escape_dismisses_tour() -> None:
    app = read(APP)
    esc_key = block(app, "if (e.key === 'Escape') {", "var overlay = topOverlay();")
    assert "exitGuidedTour();" in esc_key
    assert "!anyModalOpen()" in esc_key


# --------------------------------------------------------------------------- #
# N-8 (P2): the spotlight hides for absent targets and follows navigation
# --------------------------------------------------------------------------- #
def test_spotlight_hides_when_target_missing() -> None:
    app = read(APP)
    spot = block(app, "function positionTourSpotlight()", "function renderGuidedTour()")
    assert "target.closest('[hidden]')" in spot
    assert "demoFlowPhase() === 'finished'" in spot
    # Minimum fallback box for visible-but-zero-height targets is preserved.
    assert "minW = 120, minH = 40" in spot
    assert "Math.max(minW, r.width)" in spot
    assert "Math.max(minH, r.height)" in spot


def test_tour_advances_when_student_reaches_next_screen() -> None:
    app = read(APP)
    screen = block(app, "function setScreen(name) {", "function applyTheme(")
    assert "phaseNow === 'review' && name === 'study'" in screen
    assert "guidedDemoFlow.reviewDecision();" in screen
    assert "phaseNow === 'study' && name === 'exports'" in screen
    assert "scheduleTourGeometry();" in screen


# --------------------------------------------------------------------------- #
# §6 (P2): the tour ends on a celebration with two real destinations
# --------------------------------------------------------------------------- #
def test_tour_completion_card() -> None:
    html = read(HTML)
    assert 'id="tour-finish-actions"' in html
    assert "Open my study pack" in html
    assert "Import my own lecture" in html
    app = read(APP)
    render = block(app, "function renderGuidedTour()", "function offerGuidedTour")
    assert "Your first study pack is ready" in render
    assert "$('tour-finish-actions').hidden = !finished;" in render
    move = block(app, "function moveGuidedTour(direction)", "// The completion card's")
    assert "flow.phase === 'exports') { guidedDemoFlow.next(); renderGuidedTour(); return; }" in move
    finish = block(app, "function finishGuidedTour(destination)", "function parseBridgeResult")
    assert "destination === 'pack'" in finish
    assert "setScreen('exports');" in finish
    assert "lpBridge.call('browse_video');" in finish
    wire = block(app, "function wireGuidedTour()", "function flyDemoTileToDropzone")
    assert "btn-tour-open-pack" in wire
    assert "btn-tour-import-own" in wire
    # The demo card no longer claims the demo's files were removed.
    card = block(app, "function renderDemoCard()", "function demoFlowPhase()")
    assert "stay available to explore" in card
    assert "temporary files were removed" not in card


# --------------------------------------------------------------------------- #
# F-2 (P2): the group modal never stacks over the tour
# --------------------------------------------------------------------------- #
def test_group_modal_never_stacks_over_tour() -> None:
    app = read(APP)
    group = block(app, "function setJobGroup(job) {", "lpModal({")
    assert "guidedTour.snapshot().active || guidedTour.snapshot().prompt" in group
    bulk = block(app, "function bulkGroup() {", "lpModal({")
    assert "guidedTour.snapshot().active || guidedTour.snapshot().prompt" in bulk
    start = block(app, "function startGuidedTour(replay)", "function exitGuidedTour")
    assert "closeAllModals();" in start
    offer = block(app, "function offerGuidedTour()", "function startGuidedTour")
    assert "closeAllModals();" in offer


# --------------------------------------------------------------------------- #
# N-9 (P3): Study assistant shows a neutral empty state with no job
# --------------------------------------------------------------------------- #
def test_study_chat_empty_state_is_neutral() -> None:
    app = read(APP)
    chat = block(app, "function renderChat()", "/* ======================= quiz")
    assert "Ask about your lecture once it is ready." in chat
    boot = block(app, "function boot() {", "if (document.readyState")
    assert "LP.state.chat = [];" in boot


# --------------------------------------------------------------------------- #
# N-11 (P3): the two documented shortcuts
# --------------------------------------------------------------------------- #
def test_ctrl_o_and_ctrl_e_shortcuts() -> None:
    app = read(APP)
    keys = block(app, "// N-11: the two documented app shortcuts.", "var map = {")
    assert "sk === 'o'" in keys
    assert "lpBridge.call('browse_video');" in keys
    assert "sk === 'e'" in keys
    assert "exportJob.status === 'done'" in keys
    assert "setScreen('exports');" in keys


# --------------------------------------------------------------------------- #
# N-12 (P3): narrow-width CTA row wraps instead of clipping
# --------------------------------------------------------------------------- #
def test_narrow_dropzone_cta_wraps() -> None:
    html = read(HTML)
    assert 'class="lp-drop-cta"' in html
    css = read(CSS)
    assert "#dropzone{flex-wrap:wrap !important;row-gap:16px}" in css
    assert "#dropzone .lp-drop-cta{flex-wrap:wrap;justify-content:flex-end}" in css


# --------------------------------------------------------------------------- #
# F-6 (P2): the hidden runtime overlay parks on the healthy panel
# --------------------------------------------------------------------------- #
def test_runtime_overlay_parks_neutral_after_healthy_bootstrap() -> None:
    app = read(APP)
    gate = block(app, "function neutralPanels()", "function closeReady()")
    assert "panel.dataset.runtimeState !== 'ready'" in gate
    close = block(app, "function closeOverlay()", "function closeReady()")
    assert close.count("neutralPanels();") >= 2


# --------------------------------------------------------------------------- #
# F-7/N-10 (P3): Focus mode is a real distraction-free layout
# --------------------------------------------------------------------------- #
def test_focus_mode_hides_chrome() -> None:
    css = read(CSS)
    assert '[data-focus="true"] .lp-chrome{opacity:0;pointer-events:none}' in css
    app = read(APP)
    assert "$('btn-focus').addEventListener('click', function () { setFocus(!LP.state.focus); });" in app
    assert "function setFocus(on)" in app


# --------------------------------------------------------------------------- #
# Model details stay collapsed by default with the path inside
# --------------------------------------------------------------------------- #
def test_model_details_collapsed_by_default() -> None:
    html = read(HTML)
    details = html.split('id="setting-model-details"', 1)[1].split("</details>", 1)[0]
    assert "Advanced model details" in details
    assert "setting-model-path" in details
    tag = html.split('<details id="setting-model-details"', 1)[1].split(">", 1)[0]
    assert "open" not in tag
