"""Behavioral checks for the guided-tour and real-demo UI contract.

The two small reducers in ``app.js`` are deliberately DOM-free.  These tests
execute that same JavaScript with Node instead of treating source substrings as
proof that Next, Back, cleanup, and stale-event handling work.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "app" / "ui" / "app.js"
HTML = ROOT / "app" / "ui" / "index.html"
CSS = ROOT / "app" / "ui" / "app.css"
BRIDGE = ROOT / "app" / "ui" / "bridge.js"


def _model_javascript() -> str:
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("function GuidedTourModel")
    end = source.index("/* ===================== guided tour models end ===================== */")
    return source[start:end]


def _run_model(script: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the shared guided-tour reducers")
    complete = "'use strict';\n" + _model_javascript() + "\n" + script
    result = subprocess.run(
        [node, "-e", complete],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def _projection_javascript() -> str:
    source = APP_JS.read_text(encoding="utf-8")
    study_start = source.index("function studyOverviewText")
    study_end = source.index("function renderChat", study_start)
    export_start = source.index("function exportPdfDescription")
    export_end = source.index("function renderExportPhase", export_start)
    return source[study_start:study_end] + "\n" + source[export_start:export_end]


def _run_projection(script: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute shared UI projection helpers")
    result = subprocess.run(
        [node, "-e", "'use strict';\n" + _projection_javascript() + "\n" + script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_tour_reducer_moves_back_next_exits_and_replays():
    """DEMO-02/03: the four-step user-controlled tour is an executable state machine."""
    result = _run_model(
        """
        const tour = GuidedTourModel(false);
        const offered = tour.offer();
        const started = tour.start();
        const afterNext = tour.next(4);
        const afterBack = tour.back();
        tour.next(4); tour.next(4); tour.next(4);
        const exited = tour.exit();
        const replay = tour.replay();
        console.log(JSON.stringify({offered, started, afterNext, afterBack, exited, replay}));
        """
    )
    assert result["offered"] == {"active": False, "prompt": True, "step": -1, "completed": False}
    assert result["started"]["step"] == 0
    assert result["afterNext"]["step"] == 1
    assert result["afterBack"]["step"] == 0
    assert result["exited"] == {"active": False, "prompt": False, "step": -1, "completed": True}
    assert result["replay"]["active"] is True
    assert result["replay"]["step"] == 0


def test_action_led_demo_flow_waits_for_real_import_processing_and_review_choice():
    """DEMO-02/03: Next never advances the live stages; real actions do."""
    result = _run_model(
        """
        const flow = GuidedDemoFlowModel();
        const started = flow.start();
        const importNext = flow.next();
        const imported = flow.imported();
        const processingNext = flow.next();
        const review = flow.reviewReady();
        const reviewNext = flow.next();
        const study = flow.reviewDecision();
        const exports = flow.next();
        const back = flow.back();
        const exited = flow.exit();
        console.log(JSON.stringify({started, importNext, imported, processingNext, review, reviewNext, study, exports, back, exited}));
        """
    )
    assert result["started"]["phase"] == "import"
    assert result["importNext"]["phase"] == "import"
    assert result["imported"]["phase"] == "processing"
    assert result["processingNext"]["phase"] == "processing"
    assert result["review"]["phase"] == "review"
    assert result["reviewNext"]["phase"] == "review"
    assert result["study"]["phase"] == "study"
    assert result["study"]["nextEnabled"] is True
    assert result["exports"]["phase"] == "exports"
    assert result["back"]["phase"] == "study"
    assert result["exited"]["phase"] == "idle"


def test_slide_detection_preset_model_maps_labels_and_backend_values():
    """The UI labels map to the backend's persisted detector presets."""
    result = _run_model(
        """
        const preset = SlideDetectionPresetModel();
        const initial = preset.snapshot();
        const low = preset.select('low');
        const high = preset.select('high');
        const reflected = preset.reflect('conservative');
        const invalid = preset.reflect('unknown');
        console.log(JSON.stringify({initial, low, high, reflected, invalid}));
        """
    )
    assert result["initial"] == {"label": "balanced", "preset": "balanced"}
    assert result["low"] == {"label": "low", "preset": "conservative"}
    assert result["high"] == {"label": "high", "preset": "detailed"}
    assert result["reflected"] == {"label": "low", "preset": "conservative"}
    assert result["invalid"] == {"label": "balanced", "preset": "balanced"}


def test_new_demo_attempt_resets_review_or_exports_before_live_events_arrive():
    """A cleaned demo never lets a retry inherit its prior Study/Export phase."""
    result = _run_model(
        """
        function reachStudy(flow) {
          flow.start(); flow.imported(); flow.running(); flow.reviewReady(); flow.reviewDecision();
        }
        const fromStudy = GuidedDemoFlowModel();
        reachStudy(fromStudy);
        const studyBeforeRetry = fromStudy.snapshot();
        const studyReset = fromStudy.beginAttempt();
        fromStudy.imported(); fromStudy.running();
        const studyReviewReady = fromStudy.reviewReady();

        const fromExports = GuidedDemoFlowModel();
        reachStudy(fromExports); fromExports.next();
        const exportsBeforeRetry = fromExports.snapshot();
        const exportsReset = fromExports.beginAttempt();
        fromExports.imported(); fromExports.running();
        const exportsReviewReady = fromExports.reviewReady();
        console.log(JSON.stringify({studyBeforeRetry, studyReset, studyReviewReady, exportsBeforeRetry, exportsReset, exportsReviewReady}));
        """
    )
    assert result["studyBeforeRetry"]["phase"] == "study"
    assert result["studyReset"]["phase"] == "import"
    assert result["studyReviewReady"]["phase"] == "review"
    assert result["exportsBeforeRetry"]["phase"] == "exports"
    assert result["exportsReset"]["phase"] == "import"
    assert result["exportsReviewReady"]["phase"] == "review"


def test_runtime_study_and_export_projections_replace_design_time_copy():
    """Healthy payloads use their source-derived summary and exact kept-slide count."""
    result = _run_projection(
        """
        const polar = studyOverviewText({summary:'Polar bears conserve heat with dense fur and blubber.'});
        const empty = studyOverviewText({});
        const zero = exportPdfDescription([]);
        const one = exportPdfDescription([{state:'accepted'}, {state:'rejected'}]);
        const two = exportPdfDescription([{state:'accepted'}, {state:'accepted'}, {state:'rejected'}]);
        console.log(JSON.stringify({polar, empty, zero, one, two}));
        """
    )
    assert result["polar"] == "Polar bears conserve heat with dense fur and blubber."
    assert "Pyramid" not in result["polar"]
    assert result["empty"] == "A study overview will appear here after your lecture is ready."
    assert result["zero"] == "0 accepted slides, one per page, full resolution."
    assert result["one"] == "1 accepted slide, one per page, full resolution."
    assert result["two"] == "2 accepted slides, one per page, full resolution."


def test_demo_event_identity_rejects_stale_and_late_events():
    """DEMO-06: only the current real demo session may repaint its status card."""
    result = _run_model(
        """
        const demo = GuidedDemoSessionModel();
        demo.starting();
        demo.started({ok:true, operation_id:'op-current', session_id:'session-current'});
        const stale = demo.event({operation_id:'op-old', session_id:'session-old', status:'running', stage:'transcribe', progress:88});
        const live = demo.event({operation_id:'op-current', session_id:'session-current', status:'running', stage:'transcribe', progress:42});
        const cleaned = demo.event({operation_id:'op-current', session_id:'session-current', status:'cleaned'});
        const late = demo.event({operation_id:'op-current', session_id:'session-current', status:'running', stage:'export', progress:99});
        console.log(JSON.stringify({stale, live, cleaned, late, final:demo.snapshot()}));
        """
    )
    assert result["stale"]["accepted"] is False
    assert result["live"]["accepted"] is True
    assert result["live"]["state"]["stage"] == "transcribe"
    assert result["live"]["state"]["progress"] == 42
    assert result["cleaned"]["accepted"] is True
    assert result["late"]["accepted"] is False
    assert result["final"]["active"] is False
    assert result["final"]["status"] == "ended"


def test_delayed_demo_slot_result_cannot_resurrect_or_overwrite_live_session():
    """A live signal can beat the QWebChannel slot result without losing cleanup safety."""
    result = _run_model(
        """
        const ok = {ok:true, operation_id:'op-current', session_id:'session-current'};
        const wrong = {ok:true, operation_id:'op-stale', session_id:'session-stale'};

        const cleaned = GuidedDemoSessionModel();
        cleaned.starting();
        cleaned.started(ok); // identity adopted by an early `started` signal
        cleaned.event({operation_id:'op-current', session_id:'session-current', status:'running', stage:'transcribe', progress:37});
        cleaned.event({operation_id:'op-current', session_id:'session-current', status:'cleaned'});
        const afterCleanedDelayedSuccess = cleaned.started(ok);

        const cancelling = GuidedDemoSessionModel();
        cancelling.starting(); cancelling.started(ok); cancelling.cancelling();
        const afterCancellingDelayedSuccess = cancelling.started(ok);
        cancelling.event({operation_id:'op-current', session_id:'session-current', status:'cleaned'});
        const afterCancelCleanedDelayedSuccess = cancelling.started(ok);

        const running = GuidedDemoSessionModel();
        running.starting(); running.started(ok);
        running.event({operation_id:'op-current', session_id:'session-current', status:'running', stage:'detect_slides', progress:61});
        const duplicateSame = running.started(ok);
        const mismatch = running.started(wrong);
        console.log(JSON.stringify({afterCleanedDelayedSuccess, afterCancellingDelayedSuccess, afterCancelCleanedDelayedSuccess, duplicateSame, mismatch, running:running.snapshot()}));
        """
    )
    assert result["afterCleanedDelayedSuccess"]["terminal"] is True
    assert result["afterCleanedDelayedSuccess"]["status"] == "ended"
    assert result["afterCancellingDelayedSuccess"]["status"] == "cancelling"
    assert result["afterCancelCleanedDelayedSuccess"]["terminal"] is True
    assert result["duplicateSame"]["status"] == "running"
    assert result["duplicateSame"]["stage"] == "detect_slides"
    assert result["duplicateSame"]["progress"] == 61
    assert result["mismatch"] == result["duplicateSame"]
    assert result["running"]["operationId"] == "op-current"


def test_demo_end_slot_acknowledgements_settle_only_when_terminal():
    """Idempotent stop replies release the card; a live cancellation waits for cleanup."""
    result = _run_model(
        """
        const ok = {ok:true, operation_id:'op-current', session_id:'session-current'};

        const alreadyGone = GuidedDemoSessionModel();
        alreadyGone.starting(); alreadyGone.started(ok); alreadyGone.cancelling();
        const notRunning = alreadyGone.settleEndResult({ok:true, status:'not_running'});
        const delayedStart = alreadyGone.started(ok);

        const pendingCleanup = GuidedDemoSessionModel();
        pendingCleanup.starting(); pendingCleanup.started(ok); pendingCleanup.cancelling();
        const cancelling = pendingCleanup.settleEndResult({ok:true, status:'cancelling'});
        const cleaned = pendingCleanup.event({operation_id:'op-current', session_id:'session-current', status:'cleaned'});

        const malformed = GuidedDemoSessionModel();
        malformed.starting(); malformed.started(ok); malformed.cancelling();
        const malformedResponse = malformed.settleEndResult(null);
        const rejected = GuidedDemoSessionModel();
        rejected.starting(); rejected.started(ok); rejected.cancelling();
        const rejectedResponse = rejected.settleEndResult({ok:false, error:'bridge unavailable'});
        console.log(JSON.stringify({notRunning, delayedStart, cancelling, cleaned, malformedResponse, rejectedResponse}));
        """
    )
    assert result["notRunning"]["status"] == "ended"
    assert result["notRunning"]["active"] is False
    assert result["notRunning"]["terminal"] is True
    assert result["delayedStart"] == result["notRunning"]
    assert result["cancelling"]["status"] == "cancelling"
    assert result["cancelling"]["terminal"] is False
    assert result["cleaned"]["accepted"] is True
    assert result["cleaned"]["state"]["status"] == "ended"
    assert result["malformedResponse"]["status"] == "error"
    assert result["malformedResponse"]["terminal"] is True
    assert result["rejectedResponse"]["status"] == "error"
    assert result["rejectedResponse"]["error"] == "bridge unavailable"


def test_demo_retry_attempt_generation_ignores_old_callbacks_and_stop_results():
    """A retry is cleanly isolated from late promises belonging to its predecessor."""
    result = _run_model(
        """
        const old = {ok:true, operation_id:'op-old', session_id:'session-old'};
        const fresh = {ok:true, operation_id:'op-new', session_id:'session-new'};

        const completed = GuidedDemoSessionModel();
        const firstAttempt = completed.starting().attempt;
        completed.started(old, firstAttempt);
        completed.event({operation_id:'op-old', session_id:'session-old', status:'cleaned'});
        const retryAttempt = completed.starting().attempt;
        const retryStarted = completed.started(fresh, retryAttempt);
        const retryEvent = completed.event({operation_id:'op-new', session_id:'session-new', status:'running', stage:'detect_slides', progress:54});

        const failed = GuidedDemoSessionModel();
        const failedAttempt = failed.starting().attempt;
        failed.started(old, failedAttempt);
        failed.event({operation_id:'op-old', session_id:'session-old', status:'failed', error:'temporary failure'});
        const failedRetryAttempt = failed.starting().attempt;
        const failedRetry = failed.started(fresh, failedRetryAttempt);

        const racy = GuidedDemoSessionModel();
        const oldAttempt = racy.starting().attempt;
        const newAttempt = racy.starting().attempt;
        const oldSuccess = racy.started(old, oldAttempt);
        const oldFailure = racy.started({ok:false, error:'old rejected'}, oldAttempt);
        const beforeCurrent = racy.snapshot();
        const currentSuccess = racy.started(fresh, newAttempt);

        const staleStop = GuidedDemoSessionModel();
        const stopAttempt = staleStop.starting().attempt;
        staleStop.started(old, stopAttempt); staleStop.cancelling();
        const replacementAttempt = staleStop.starting().attempt;
        staleStop.started(fresh, replacementAttempt);
        const oldStopResult = staleStop.settleEndResult({ok:true, status:'not_running'}, stopAttempt, 'op-old', 'session-old');
        console.log(JSON.stringify({firstAttempt, retryAttempt, retryStarted, retryEvent, failedRetryAttempt, failedRetry, oldSuccess, oldFailure, beforeCurrent, currentSuccess, oldStopResult, staleStop:staleStop.snapshot()}));
        """
    )
    assert result["retryAttempt"] > result["firstAttempt"]
    assert result["retryStarted"]["operationId"] == "op-new"
    assert result["retryEvent"]["accepted"] is True
    assert result["retryEvent"]["state"]["stage"] == "detect_slides"
    assert result["failedRetryAttempt"] > result["firstAttempt"]
    assert result["failedRetry"]["operationId"] == "op-new"
    assert result["oldSuccess"] == result["beforeCurrent"]
    assert result["oldFailure"] == result["beforeCurrent"]
    assert result["currentSuccess"]["operationId"] == "op-new"
    assert result["oldStopResult"]["operationId"] == "op-new"
    assert result["oldStopResult"]["status"] == "started"
    assert result["staleStop"]["active"] is True
    assert result["staleStop"]["attempt"] > result["firstAttempt"]


def test_css_spotlight_is_pointer_transparent_and_uses_a_static_scrim():
    """QtWebEngine-safe spotlight: static scrim, cheap geometry, no SVG hit surface."""
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert 'id="guided-tour-overlay"' in html
    assert 'id="tour-spotlight-box"' in html
    assert "<mask" not in html.lower()
    assert "<svg id=\"tour" not in html.lower()
    # The overlay is a transparent positioning root; the four static dim rects
    # carry the scrim (see test_spotlight_dim_regions_tile_the_viewport...).
    assert "#guided-tour-overlay{position:fixed;inset:0;z-index:200;pointer-events:none;background:transparent}" in css
    assert "#tour-spotlight-box" in css
    spotlight = css.split("#guided-tour-overlay", 1)[1].split("#guided-tour-card", 1)[0]
    # AD-20: a 9999px/100vmax spread shadow, a drop-shadow filter on the arrow,
    # geometry transitions and will-change were CONFIRMED causes of flicker and
    # lag on a clean-install Windows machine. None of them may come back.
    assert "9999px" not in spotlight
    assert "100vmax" not in spotlight
    assert "filter:drop-shadow" not in spotlight
    assert "transition:" not in spotlight
    assert "will-change" not in spotlight
    assert "backdrop-filter" not in spotlight

    # z-order must be internally ordered AND clear of the app's own layers:
    # downloads popover 49, model tooltip 180, drag ghost 300.
    def z_of(selector: str) -> int:
        # A selector may be split across several rules; find the one with z-index.
        for chunk in css.split(selector)[1:]:
            block = chunk.split("}", 1)[0]
            if "z-index:" in block:
                return int(block.split("z-index:", 1)[1].split(";", 1)[0].strip())
        raise AssertionError(f"{selector} declares no z-index")

    scrim = z_of("#guided-tour-overlay")
    ring = z_of("#tour-spotlight-box")
    arrow_z = z_of("#tour-arrow")
    card_z = z_of("#guided-tour-card{")
    assert scrim < ring < arrow_z < card_z, "tour layers are out of order"
    assert scrim > 180, "tour scrim must sit above the model tooltip (180)"
    assert card_z < 300, "tour card must sit below the drag ghost (300)"
    assert "#guided-tour-card" in css and "pointer-events:auto" in css
    assert "#glowing-demo-card.lp-demo-tour-lifted" in css
    assert "pointer-events:auto!important" in css


def test_first_run_prompt_controls_keyboard_guards_and_replay_are_wired():
    """Prompt policy is separate from job data; arrows never steal typing input."""
    js = APP_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")

    assert "lecturepack.guided-tour.seen.v1" in js
    assert "tourRuntimeHealthy" in js and "offerGuidedTour();" in js
    assert "isTourFormInput(e.target)" in js
    assert "e.key === 'ArrowRight'" in js and "e.key === 'ArrowLeft'" in js
    assert "window.addEventListener('resize', scheduleTourGeometry)" in js
    assert "window.addEventListener('scroll', scheduleTourGeometry, true)" in js
    assert "target: '#pipeline-stages'" in js
    assert "target: '#demo-review-actions'" in js
    # Study V2 owns the visible Study workspace; '#demo-study-actions' lives
    # inside '#study-legacy[hidden]', so targeting it collapsed the spotlight
    # and the step rendered with no dim and no ring at all.
    assert "target: '#demo-study-actions-v2'" in js
    assert "target: '#btn-export-all'" in js
    assert 'id="btn-replay-tour"' in html
    assert '<section id="home-demo"' in html and 'id="home-demo"' in html.split('>', 1)[1]
    home_demo = html.split('<section id="home-demo"', 1)[1].split('>', 1)[0]
    onboarding = html.split('<div id="settings-onboarding"', 1)[1].split('>', 1)[0]
    assert 'hidden' in home_demo
    assert 'hidden' in onboarding
    assert "Replay guided tour" in html
    assert "Take guided tour" in html
    assert "Skip to app" in html
    assert 'id="btn-tour-exit"' in html
    exit_start = js.index("function exitGuidedTour")
    exit_end = js.index("function moveGuidedTour", exit_start)
    exit_block = js[exit_start:exit_end]
    assert "guidedTour.exit()" in exit_block
    assert "setScreen('home')" in exit_block
    assert "endGuidedDemo('tour_exit')" in exit_block
    admission_start = js.index("function setDemoAdmissionAvailable")
    admission_end = js.index("function stageLabel", admission_start)
    admission_block = js[admission_start:admission_end]
    assert "demoAdmissionAvailable = next" in admission_block
    assert "renderDemoHomeAvailability();" in admission_block
    assert "onboarding.hidden = !next" in admission_block
    assert "if (!wasAvailable) offerGuidedTour();" in admission_block
    assert "setTourOverlayHidden(!demoAdmissionAvailable ||" in js
    start_tour = js[js.index("function startGuidedTour"):js.index("function exitGuidedTour")]
    start_demo = js[js.index("function startGuidedDemo"):js.index("function endGuidedDemo")]
    assert "if (!demoAdmissionAvailable) return;" in start_tour
    assert "if (!demoAdmissionAvailable) return;" in start_demo
    gate = js[js.index("var RuntimeSetupGate ="):js.index("/* Clears", js.index("var RuntimeSetupGate ="))]
    assert "syncDemoAdmission(view);" in gate
    assert "setDemoAdmissionAvailable(!!(view && view.healthy" in gate
    assert "var demoHomeDismissed = tourSeen();" in js
    assert "function renderDemoHomeAvailability()" in js
    assert "demoHomeDismissed && !guidedTour.snapshot().active" in js
    assert "markTourSeen(); demoHomeDismissed = true;" in exit_block


def test_model_tooltip_handles_hover_focus_and_safe_empty_values():
    js = APP_JS.read_text(encoding="utf-8")
    assert "function setModelValue(value)" in js
    assert "String(value || '')" in js
    assert "showModelTooltip" in js and "hideModelTooltip" in js
    assert "mouseenter" in js and "mouseleave" in js
    assert "focus" in js and "blur" in js


def test_every_tour_target_exists_and_is_not_inside_a_hidden_ancestor():
    """Regression: the study step pointed at markup Study V2 had superseded.

    '#demo-study-actions' sits inside '<div id="study-legacy" hidden>'. The
    spotlight collapses on `target.closest('[hidden]')`, so that step rendered
    with no dim, no ring and no arrow -- while its card still told the user to
    use a chat box that was not on screen. A target that no step can ever
    illuminate is a broken step, so assert it statically for all five.
    """
    js = APP_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")

    phases = js.split("var TOUR_PHASES = {", 1)[1].split("\n  };", 1)[0]
    steps = {}
    for screen, raw in re.findall(r"screen: '(\w+)', target: (\[[^\]]*\]|'#[A-Za-z0-9_-]+')", phases):
        for sel in re.findall(r"'#([A-Za-z0-9_-]+)'", raw):
            steps[sel] = screen
    targets = list(steps)
    assert len(targets) == 6, (
        f"expected 6 targets across 5 steps (import is a union of two), found {targets}")

    # Track the real open-element stack; counting <div> substrings misreads
    # void elements and comments.
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}
    found: dict[str, list[str]] = {}

    class Ancestry(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.stack: list = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            a = dict(attrs)
            node = (tag, a.get("id"), "hidden" in a, a.get("data-screen"))
            if a.get("id") in targets:
                # A hidden ancestor is fine if it is the very screen this step
                # activates -- setScreen() unhides it. It is a bug only when
                # nothing in the step's own flow will ever reveal it.
                found[a["id"]] = [
                    s[1] for s in self.stack
                    if s[2] and s[1] and s[3] != steps[a["id"]]
                ]
            if tag not in void:
                self.stack.append(node)

        def handle_endtag(self, tag: str) -> None:
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

    Ancestry().feed(html)

    # Containers a step explicitly guarantees revealed before it runs.
    revealed = set(re.findall(r"reveals: \[([^\]]*)\]", phases))
    revealed = {sel for group in revealed for sel in re.findall(r"'#([A-Za-z0-9_-]+)'", group)}

    for target in targets:
        assert target in found, f"tour target #{target} is not in the markup"
        found[target] = [c for c in found[target] if c not in revealed]
        assert not found[target], (
            f"tour target #{target} is inside hidden container(s) "
            f"{found[target]}; the spotlight will collapse and the step will "
            "render with no dim, no ring and no arrow"
        )


def test_tour_geometry_is_rAF_coalesced_revealed_remeasured_and_clamped():
    """VIS-05: resize/scroll/DPI changes update the real CSS spotlight once per frame."""
    js = APP_JS.read_text(encoding="utf-8")
    start = js.index("function positionTourSpotlight")
    end = js.index("function renderGuidedTour", start)
    geometry = js[start:end]
    assert "function scheduleTourGeometry()" in js
    assert "requestAnimationFrame" in js
    assert "tourGeometryFrame !== null" in js
    assert "scrollIntoView({block: 'nearest', inline: 'nearest'})" in js
    # Measurement goes through tourTargetRect(), which returns the bounding
    # union for multi-element steps and the plain rect otherwise.
    assert geometry.count("tourTargetRect(target)") >= 2
    assert "function tourTargetRect(" in js
    # The rect is clamped into the viewport on both axes so the spotlight can
    # never be drawn off-screen or with a negative extent.
    assert "viewportWidth = window.innerWidth" in geometry
    assert "viewportHeight = window.innerHeight" in geometry
    assert "viewportWidth - left" in geometry
    assert "viewportHeight - top" in geometry
    assert "visualViewport" in js


def test_tour_focus_is_scoped_to_real_target_and_card_controls_with_exit_reachable():
    js = APP_JS.read_text(encoding="utf-8")
    assert "function tourFocusable()" in js
    assert "function trapTourFocus(e)" in js
    assert "btn-tour-exit" in js
    assert "trapTourFocus(e)" in js
    assert "tourTarget.contains(item)" in js


def test_healthy_runtime_markup_has_no_stale_pyramid_or_export_count():
    """The static shell starts friendly; real projections provide lecture-specific text."""
    html = HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    overview_markup = html.split('id="study-overview"', 1)[1].split('</p>', 1)[0]
    export_markup = html.split('id="export-pdf-desc"', 1)[1].split('</div>', 1)[0]
    assert "Great Pyramid" not in overview_markup
    assert "14 accepted slides" not in export_markup
    assert 'id="study-overview"' in html
    assert 'id="export-pdf-desc"' in html
    assert "overview.textContent = studyOverviewText(st)" in js
    assert "updateExportPdfDescription();" in js
    slides_handler = js[js.index("lpBridge.on('slides_changed'"):js.index("lpBridge.on('transcript_changed'")]
    assert "updateExportPdfDescription();" in slides_handler


def test_real_demo_bridge_contract_and_card_are_wired_without_timers():
    """The card consumes backend identity-bearing events; it does not simulate work."""
    js = APP_JS.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")

    assert "'demo_event'" in bridge
    assert "startDemoJob" in bridge and "endDemoJob" in bridge
    assert "lpBridge.on('demo_event', receiveDemoEvent)" in js
    assert "lpBridge.startDemoJob()" in js
    assert "lpBridge.endDemoJob(reason || 'ended')" in js
    assert "settleEndResult" in js
    assert "isCurrentAttempt(startedAttempt)" in js
    assert "isCurrentAttempt(endingAttempt, endingOperationId, endingSessionId)" in js
    assert "operation_id" in js and "session_id" in js
    assert 'id="glowing-demo-card"' in html
    assert "Polar Bears 10s Demo.mp4" in html
    assert 'draggable="true"' in html
    assert 'polar_bears_thumbnail.jpg' in html
    thumbnail = ROOT / "app" / "assets" / "demo" / "polar_bears_thumbnail.jpg"
    assert thumbnail.is_file()
    assert thumbnail.stat().st_size > 0
    # QImage is supplied by the app runtime and confirms the packaged browser
    # asset is an actual decodable JPEG rather than a placeholder text file.
    from PySide6.QtGui import QImage
    image = QImage(str(thumbnail))
    assert not image.isNull()
    assert image.width() == 960 and image.height() == 540
    assert "application/x-lecturepack-demo" in js
    assert "flyDemoTileToDropzone" in js
    assert "hasDemoDrag(e)" in js
    assert "eventStage === 'review_ready'" in js
    assert "guidedDemoFlow.reviewDecision()" in js
    assert "guidedDemoFlow.beginAttempt()" in js
    assert "See export options" in js
    assert "own processed lecture" in js
    css = CSS.read_text(encoding="utf-8")
    assert "#glowing-demo-card.lp-demo-fly" in css
    assert "#glowing-demo-card.lp-demo-tour-active" in css
    assert "@keyframes lpdemoprompt" in css
    assert "animation:none!important" in css
    spotlight_glow = "0 0 25px rgba(255,122,0,.6)"
    assert spotlight_glow in css
    assert "#glowing-demo-card.lp-demo-tour-active{border-color:var(--orange);box-shadow:var(--shadow-hard)," + spotlight_glow in css
    assert "setDemoTourInteraction(state.active && flow.phase === 'import')" in js
    assert "function liftDemoCardAboveTourScrim()" in js
    assert "overlay.appendChild(card)" in js
    assert "function restoreDemoCardBelowTourScrim()" in js
    assert "positionLiftedDemoCard();" in js
    assert "setTimeout" not in js[js.index("function startGuidedDemo"):js.index("function isTourFormInput")]


def test_slide_sensitivity_controls_are_semantic_persistent_and_demo_safe():
    """Low/Balanced/High is usable before normal processing but locked for the demo."""
    js = APP_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    controls = html.split('id="proc-sensitivity"', 1)[1].split('</div>', 1)[0]
    assert controls.count('<button') == 3
    assert '<span data-sens=' not in controls
    assert 'role="group"' in controls
    assert 'aria-pressed="true"' in controls
    assert "$('proc-sensitivity').addEventListener('click'" in js
    assert "lpBridge.call('set_setting', 'slide_detection_preset', state.preset)" in js
    assert "s.slide_detection_preset !== undefined" in js
    assert "slideDetectionPreset.reflect(s.slide_detection_preset)" in js
    assert "guidedDemoSensitivityLocked()" in js
    assert "button.disabled = locked" in js
    assert "Guided demo uses its fixed reliable setting." in html
