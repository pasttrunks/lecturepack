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
    assert "operation_id" in js and "session_id" in js
    assert 'id="glowing-demo-card"' in html
    assert "Polar Bears 10s Demo.mp4" in html
    assert "setTimeout" not in js[js.index("function startGuidedDemo"):js.index("function isTourFormInput")]
