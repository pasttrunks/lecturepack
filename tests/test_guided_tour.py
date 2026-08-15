"""Behavioral checks for the self-contained demo and real-demo contract.

The session and slide-preset reducers in ``app.js`` are deliberately DOM-free.
These tests execute that same JavaScript with Node so cleanup, retries, and
stale-event rejection are verified as behavior rather than source-shaped mocks.
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
    start = source.index("function GuidedDemoSessionModel")
    end = source.index("/* ===================== demo session model end ===================== */")
    return source[start:end]


def _run_model(script: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the shared demo reducers")
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


def test_slide_detection_preset_model_maps_labels_and_backend_values() -> None:
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


def test_runtime_study_and_export_projections_use_live_content() -> None:
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
    assert result["empty"] == "A study overview will appear here after your lecture is ready."
    assert result["zero"] == "0 accepted slides, one per page, full resolution."
    assert result["one"] == "1 accepted slide, one per page, full resolution."
    assert result["two"] == "2 accepted slides, one per page, full resolution."


def test_demo_event_identity_rejects_stale_and_late_events() -> None:
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
    assert result["live"]["state"]["progress"] == 42
    assert result["cleaned"]["accepted"] is True
    assert result["late"]["accepted"] is False
    assert result["final"]["status"] == "ended"
    assert result["final"]["active"] is False


def test_delayed_start_result_cannot_resurrect_terminal_session() -> None:
    result = _run_model(
        """
        const ok = {ok:true, operation_id:'op-current', session_id:'session-current'};
        const wrong = {ok:true, operation_id:'op-stale', session_id:'session-stale'};
        const cleaned = GuidedDemoSessionModel();
        cleaned.starting(); cleaned.started(ok);
        cleaned.event({operation_id:'op-current', session_id:'session-current', status:'cleaned'});
        const afterCleaned = cleaned.started(ok);
        const running = GuidedDemoSessionModel();
        running.starting(); running.started(ok);
        running.event({operation_id:'op-current', session_id:'session-current', status:'running', stage:'detect_slides', progress:61});
        const duplicate = running.started(ok);
        const mismatch = running.started(wrong);
        console.log(JSON.stringify({afterCleaned, duplicate, mismatch, running:running.snapshot()}));
        """
    )
    assert result["afterCleaned"]["terminal"] is True
    assert result["afterCleaned"]["status"] == "ended"
    assert result["duplicate"]["stage"] == "detect_slides"
    assert result["duplicate"]["progress"] == 61
    assert result["mismatch"] == result["duplicate"]


def test_demo_end_acknowledgements_settle_only_when_terminal() -> None:
    result = _run_model(
        """
        const ok = {ok:true, operation_id:'op-current', session_id:'session-current'};
        const alreadyGone = GuidedDemoSessionModel();
        alreadyGone.starting(); alreadyGone.started(ok); alreadyGone.cancelling();
        const notRunning = alreadyGone.settleEndResult({ok:true, status:'not_running'});
        const delayedStart = alreadyGone.started(ok);
        const pending = GuidedDemoSessionModel();
        pending.starting(); pending.started(ok); pending.cancelling();
        const cancelling = pending.settleEndResult({ok:true, status:'cancelling'});
        const cleaned = pending.event({operation_id:'op-current', session_id:'session-current', status:'cleaned'});
        const rejected = GuidedDemoSessionModel();
        rejected.starting(); rejected.started(ok); rejected.cancelling();
        const rejectedResponse = rejected.settleEndResult({ok:false, error:'bridge unavailable'});
        console.log(JSON.stringify({notRunning, delayedStart, cancelling, cleaned, rejectedResponse}));
        """
    )
    assert result["notRunning"]["status"] == "ended"
    assert result["notRunning"]["terminal"] is True
    assert result["delayedStart"] == result["notRunning"]
    assert result["cancelling"]["status"] == "cancelling"
    assert result["cancelling"]["terminal"] is False
    assert result["cleaned"]["accepted"] is True
    assert result["rejectedResponse"]["status"] == "error"
    assert result["rejectedResponse"]["error"] == "bridge unavailable"


def test_demo_retry_generation_ignores_old_callbacks_and_stop_results() -> None:
    result = _run_model(
        """
        const old = {ok:true, operation_id:'op-old', session_id:'session-old'};
        const fresh = {ok:true, operation_id:'op-new', session_id:'session-new'};
        const demo = GuidedDemoSessionModel();
        const oldAttempt = demo.starting().attempt;
        demo.started(old, oldAttempt);
        demo.event({operation_id:'op-old', session_id:'session-old', status:'cleaned'});
        const newAttempt = demo.starting().attempt;
        const oldSuccess = demo.started(old, oldAttempt);
        const newSuccess = demo.started(fresh, newAttempt);
        const oldStop = demo.settleEndResult({ok:true, status:'not_running'}, oldAttempt, 'op-old', 'session-old');
        console.log(JSON.stringify({oldAttempt, newAttempt, oldSuccess, newSuccess, oldStop, final:demo.snapshot()}));
        """
    )
    assert result["newAttempt"] > result["oldAttempt"]
    assert result["oldSuccess"]["operationId"] == ""
    assert result["newSuccess"]["operationId"] == "op-new"
    assert result["oldStop"]["operationId"] == "op-new"
    assert result["final"]["active"] is True


def test_spotlight_renderer_is_fully_removed() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    for token in (
        "GuidedTourModel",
        "GuidedDemoFlowModel",
        "positionTourSpotlight",
        "positionTourCard",
        "renderGuidedTour",
        "flyDemoTileToDropzone",
    ):
        assert token not in js
    for token in ("guided-tour-overlay", "tour-spotlight-box", "tour-dim-"):
        assert token not in html
        assert token not in css


def test_self_contained_demo_screen_and_durable_state_are_wired() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    assert '<section data-screen="demo"' in html
    assert html.count('class="lp-demo-ch"') == 5
    for control in ("btn-demo-next", "btn-demo-back", "btn-demo-skip", "btn-demo-run", "btn-demo-own"):
        assert f'id="{control}"' in html
    assert "window.LP_DEMO_DATA" in js
    assert "function renderDemoChapter" in js
    assert "function openDemo" in js
    assert "function closeDemo" in js
    assert "persistGuidedTourState(status || 'completed')" in js
    assert "lpBridge.call('replay_guided_tour')" in js
    assert "lpBridge.call('set_guided_tour_state'" in js
    open_demo = js[js.index("function openDemo"):js.index("function closeDemo")]
    assert "fetch('../assets/demo" not in open_demo
    assert "window.LP_DEMO_DATA" in open_demo


def test_real_demo_bridge_contract_and_retry_cleanup_are_wired() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    assert "'demo_event'" in bridge
    assert "startDemoJob" in bridge and "endDemoJob" in bridge
    assert "lpBridge.on('demo_event', receiveDemoEvent)" in js
    assert "lpBridge.startDemoJob()" in js
    assert "lpBridge.endDemoJob(reason || 'ended')" in js
    assert "isCurrentAttempt(attempt)" in js
    assert "operation_id" in js and "session_id" in js
    run = js[js.index("function runDemoForReal"):js.index("function bindDemoScreen")]
    assert run.index("demoCleanupRequested = false") < run.index("guidedDemo.starting()")
    assert run.index("demoCleanupConfirmed = false") < run.index("guidedDemo.starting()")
    assert "setTimeout" not in run
    assert 'id="glowing-demo-card"' in html
    assert "Polar Bears 10s Demo.mp4" in html
    assert 'draggable="true"' in html
    thumbnail = ROOT / "app" / "assets" / "demo" / "polar_bears_thumbnail.jpg"
    assert thumbnail.is_file() and thumbnail.stat().st_size > 0
    from PySide6.QtGui import QImage

    image = QImage(str(thumbnail))
    assert not image.isNull()
    assert (image.width(), image.height()) == (960, 540)


def test_model_tooltip_handles_hover_focus_and_safe_empty_values() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    assert "function setModelValue(value)" in js
    assert "String(value || '')" in js
    assert "showModelTooltip" in js and "hideModelTooltip" in js
    assert "mouseenter" in js and "mouseleave" in js
    assert "focus" in js and "blur" in js


def test_healthy_runtime_markup_has_no_stale_design_content() -> None:
    html = HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    overview_markup = html.split('id="study-overview"', 1)[1].split("</p>", 1)[0]
    export_markup = html.split('id="export-pdf-desc"', 1)[1].split("</div>", 1)[0]
    assert "Great Pyramid" not in overview_markup
    assert "14 accepted slides" not in export_markup
    assert "overview.textContent = studyOverviewText(st)" in js
    assert "updateExportPdfDescription();" in js


def test_slide_sensitivity_controls_are_semantic_persistent_and_demo_safe() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    controls = html.split('id="proc-sensitivity"', 1)[1].split("</div>", 1)[0]
    assert controls.count("<button") == 3
    assert 'role="group"' in controls
    assert 'aria-pressed="true"' in controls
    assert "$('proc-sensitivity').addEventListener('click'" in js
    assert "lpBridge.call('set_setting', 'slide_detection_preset', state.preset)" in js
    assert "slideDetectionPreset.reflect(s.slide_detection_preset)" in js
    assert "guidedDemoSensitivityLocked()" in js
    assert "button.disabled = locked" in js
    assert "Guided demo uses its fixed reliable setting." in html
