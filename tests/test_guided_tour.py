"""Behavioral checks for the guided-tour and real-demo UI contract.

The two small reducers in ``app.js`` are deliberately DOM-free.  These tests
execute that same JavaScript with Node instead of treating source substrings as
proof that Next, Back, cleanup, and stale-event handling work.
"""

from __future__ import annotations

import json
import shutil
import subprocess
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


def test_css_spotlight_is_pointer_transparent_and_has_no_svg_mask():
    """QtWebEngine-safe spotlight: CSS box-shadow dimmer, never an SVG hit surface."""
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    assert 'id="guided-tour-overlay"' in html
    assert 'id="tour-spotlight-box"' in html
    assert "<mask" not in html.lower()
    assert "<svg id=\"tour" not in html.lower()
    assert "#guided-tour-overlay{position:fixed;inset:0;z-index:170;pointer-events:none}" in css
    assert "#tour-spotlight-box" in css
    assert "box-shadow:0 0 0 9999px rgba(8,10,14,.65)" in css
    assert "#guided-tour-card" in css and "pointer-events:auto" in css


def test_first_run_prompt_controls_keyboard_guards_and_replay_are_wired():
    """Prompt policy is separate from job data; arrows never steal typing input."""
    js = APP_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")

    assert "lecturepack.guided-tour.seen.v1" in js
    assert "tourRuntimeHealthy" in js and "offerGuidedTour();" in js
    assert "isTourFormInput(e.target)" in js
    assert "e.key === 'ArrowRight'" in js and "e.key === 'ArrowLeft'" in js
    assert "window.addEventListener('resize', positionTourSpotlight)" in js
    assert "window.addEventListener('scroll', positionTourSpotlight, true)" in js
    assert "target: '#pipeline-stages'" in js
    assert "target: '#demo-review-actions'" in js
    assert "target: '#demo-study-actions'" in js
    assert "target: '#btn-export-all'" in js
    assert 'id="btn-replay-tour"' in html
    assert "Replay guided tour" in html
    assert "Take guided tour" in html
    assert "Skip to app" in html
    assert 'id="btn-tour-exit"' in html


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
    assert "#glowing-demo-card.lp-demo-fly" in CSS.read_text(encoding="utf-8")
    assert "setTimeout" not in js[js.index("function startGuidedDemo"):js.index("function isTourFormInput")]
