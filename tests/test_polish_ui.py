"""Focused renderer regressions for the LecturePack 2.0.1 polish pass."""

import json
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
    assert "late animation callback" in start
    assert "startGuidedTour(true)" not in start
    assert "guidedDemoFlow.beginAttempt();" in start
    assert "renderGuidedTour();\n      return;" in start

    # Both Home entry points now open the self-contained demo SCREEN. The
    # spotlight tour they used to open measured the live UI at runtime, which
    # is the coupling every demo bug came from (AD-47).
    load_jobs = function_block(JS, "$('btn-load-jobs').addEventListener", "var ONB_ACTIVE_STYLE")
    assert "openDemo(" in load_jobs
    assert "startGuidedTour(true)" not in load_jobs
    assert "flyDemoTileToDropzone" not in load_jobs

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


def test_spotlight_dim_regions_tile_the_viewport_without_overlapping() -> None:
    """The four static rects must TILE, never overlap.

    `right` used to span the full viewport height while `top`/`bottom` already
    spanned the full width, so both right-hand corners were painted twice
    (.65 over .65 = .878) and the left-hand corners once. That asymmetry was
    the hard vertical seam at `left + width` of every target, and it is why the
    highlighted control read as dim rather than lit.

    The fix keeps four static rects on purpose: AD-20 removed the spread-shadow
    spotlight and its geometry transitions because they caused confirmed
    flicker on a clean-install Windows machine.
    """
    for region in ("tour-dim-top", "tour-dim-right", "tour-dim-bottom", "tour-dim-left"):
        assert f'id="{region}"' in HTML
        assert f"setTourDimRect('{region}'" in JS

    geometry = function_block(JS, "function positionTourSpotlight()", "function renderGuidedTour")
    # top/bottom own the full width, so left/right own only the height band.
    assert "setTourDimRect('tour-dim-top', 0, 0, viewportWidth, top)" in geometry
    assert "setTourDimRect('tour-dim-bottom', 0, top + height, viewportWidth, bottomHeight)" in geometry
    assert "setTourDimRect('tour-dim-left', 0, top, left, height)" in geometry
    assert (
        "setTourDimRect('tour-dim-right', left + width, top, viewportWidth - left - width, height)"
        in geometry
    ), "the right region must span only the target's height band, not the full viewport"

    spotlight_css = CSS.split("#tour-spotlight-box", 1)[1].split("#guided-tour-card", 1)[0]
    assert "border:" in spotlight_css
    assert "border-radius:" in spotlight_css
    assert "mask" not in spotlight_css.lower()
    assert "clip-path" not in spotlight_css.lower()
    # AD-20 guards, restated where the geometry lives.
    assert "9999px" not in spotlight_css
    assert "100vmax" not in spotlight_css
    assert "transition:" not in spotlight_css
    assert "will-change" not in spotlight_css


def test_dim_regions_tile_exactly_for_real_target_geometry() -> None:
    """Execute the real rect math and assert the four regions tile the viewport.

    A string check cannot prove the arithmetic; this one covers every pixel
    exactly once, which is what "no seam" actually means.
    """
    geometry = function_block(JS, "function positionTourSpotlight()", "function renderGuidedTour")
    calls = re.findall(
        r"setTourDimRect\('tour-dim-(\w+)', ([^;]+?)\);", geometry
    )
    assert len(calls) == 4, f"expected 4 dim rects, found {len(calls)}"
    args = {name: expr for name, expr in calls}

    program = """
    var out = [];
    [
      {vw:1920, vh:1080, r:{left:975, top:578, width:158, height:46}},
      {vw:1920, vh:1080, r:{left:245, top:930, width:265, height:40}},
      {vw:1280, vh:800,  r:{left:0,   top:0,   width:200, height:60}},
      {vw:1280, vh:800,  r:{left:1100,top:740, width:180, height:60}}
    ].forEach(function (c) {
      var viewportWidth = c.vw, viewportHeight = c.vh, pad = 7;
      var left = Math.max(0, Math.min(Math.round(c.r.left - pad), viewportWidth));
      var top = Math.max(0, Math.min(Math.round(c.r.top - pad), viewportHeight));
      var width = Math.max(0, Math.min(Math.round(c.r.width + pad*2), viewportWidth - left));
      var height = Math.max(0, Math.min(Math.round(c.r.height + pad*2), viewportHeight - top));
      var bottomHeight = viewportHeight - top - height;
      out.push({vw:c.vw, vh:c.vh, hole:{l:left,t:top,w:width,h:height}, rects:{
        top: [%s], right: [%s], bottom: [%s], left: [%s]
      }});
    });
    console.log(JSON.stringify(out));
    """ % (args["top"], args["right"], args["bottom"], args["left"])
    proc = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    for case in json.loads(proc.stdout):
        vw, vh, hole = case["vw"], case["vh"], case["hole"]
        rects = []
        for name, (x, y, w, h) in case["rects"].items():
            assert w >= 0 and h >= 0, f"{name} has negative extent"
            if w and h:
                rects.append((name, x, y, x + w, y + h))

        # No two dim rects may overlap -- overlap is the double-paint seam.
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                overlap = not (a[1] >= b[3] or a[3] <= b[1] or a[2] >= b[4] or a[4] <= b[2])
                assert not overlap, f"{a[0]} overlaps {b[0]}: double-painted corner"

        # Total dim area + hole must equal the viewport: every pixel covered once.
        dim_area = sum((r[3] - r[1]) * (r[4] - r[2]) for r in rects)
        assert dim_area + hole["w"] * hole["h"] == vw * vh, (
            f"regions do not tile {vw}x{vh}: "
            f"{dim_area} dim + {hole['w'] * hole['h']} hole != {vw * vh}"
        )


def _run_card_placement(cases: str) -> list:
    """Execute the real positionTourCard() under Node against a stub DOM.

    Placement is pure geometry, so it can be checked exactly rather than
    eyeballed in a screenshot -- which is how the card ended up sitting on top
    of the control it was describing in DEMO-IMPORT and DEMO-EXPORTS.
    """
    fn = "function positionTourCard" + function_block(
        JS, "function positionTourCard", "\n  function "
    )
    harness = """
    var __card = {offsetWidth: 360, offsetHeight: 132, dataset: {}, style: {props: {},
      setProperty: function (k, v) { this.props[k] = v; }},
      attrs: {}, setAttribute: function (k, v) { this.attrs[k] = v; },
      removeAttribute: function (k) { delete this.attrs[k]; }};
    var $ = function (id) { return id === 'guided-tour-card' ? __card : null; };
    var window = {innerWidth: 0, innerHeight: 0};
    // The keep-clear lookup is exercised separately; here we isolate placement.
    var currentTourPhase = function () { return {}; };   // default 'card' presentation
    var document = {querySelector: function () { return null; }};
    """
    program = harness + fn + f"""
    var out = [];
    {cases}
    console.log(JSON.stringify(out));
    """
    proc = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_tour_card_is_anchored_beside_the_target_and_never_covers_it() -> None:
    cases = """
    [
      {n:'small button, room below', vw:1920, vh:1080, r:{left:900,top:200,width:120,height:40}},
      {n:'target low on screen',     vw:1920, vh:1080, r:{left:245,top:930,width:265,height:40}},
      {n:'full-width dropzone',      vw:1920, vh:1080, r:{left:270,top:290,width:1060,height:96}},
      {n:'bottom-right corner',      vw:1920, vh:1080, r:{left:1780,top:1010,width:120,height:50}},
      {n:'tall target, narrow win',  vw:900,  vh:700,  r:{left:40,top:60,width:820,height:560}}
    ].forEach(function (c) {
      window.innerWidth = c.vw; window.innerHeight = c.vh;
      var r = c.r;
      r.right = r.left + r.width; r.bottom = r.top + r.height;
      positionTourCard(r, 7);
      var x = parseInt(__card.style.props['--tour-card-x'], 10);
      var y = parseInt(__card.style.props['--tour-card-y'], 10);
      out.push({n: c.n, x: x, y: y, vw: c.vw, vh: c.vh, r: r,
                anchored: '' in __card.attrs || 'data-anchored' in __card.attrs});
    });
    """
    for case in _run_card_placement(cases):
        cw, ch, pad, g = 360, 132, 7, 16
        name = case["n"]
        r = case["r"]
        assert case["anchored"], f"{name}: card was never marked anchored"

        # Always fully on-screen.
        assert 0 <= case["x"] <= case["vw"] - cw, f"{name}: card overflows horizontally"
        assert 0 <= case["y"] <= case["vh"] - ch, f"{name}: card overflows vertically"

        hole = (r["left"] - pad, r["top"] - pad, r["right"] + pad, r["bottom"] + pad)
        card = (case["x"], case["y"], case["x"] + cw, case["y"] + ch)
        overlaps = not (card[0] >= hole[2] or card[2] <= hole[0]
                        or card[1] >= hole[3] or card[3] <= hole[1])

        # Does any side actually have room for the card plus both gutters?
        fits_somewhere = any([
            hole[3] + g + ch + g <= case["vh"],   # below
            hole[1] - g - ch >= g,                # above
            hole[2] + g + cw + g <= case["vw"],   # right
            hole[0] - g - cw >= g,                # left
        ])

        if fits_somewhere:
            # Never overlaps -- the whole point of anchoring.
            assert not overlaps, f"{name}: card covers the control it describes"
            # And stays adjacent, not flung to the far side of the window.
            gap = min(abs(card[0] - hole[2]), abs(hole[0] - card[2]),
                      abs(card[1] - hole[3]), abs(hole[1] - card[3]))
            assert gap <= g + 1, f"{name}: card drifted {gap}px from the target"
        else:
            # Target nearly fills the window, so some overlap is unavoidable.
            # Require only that the card docks against the roomiest edge
            # instead of burying the target from a corner.
            room = {
                "below": case["vh"] - hole[3], "above": hole[1],
                "right": case["vw"] - hole[2], "left": hole[0],
            }
            best = max(room, key=room.get)
            docked = {
                "below": card[3] >= case["vh"] - g - 1,
                "above": card[1] <= g + 1,
                "right": card[2] >= case["vw"] - g - 1,
                "left": card[0] <= g + 1,
            }[best]
            assert docked, f"{name}: card should dock to the '{best}' edge"


def test_stacked_review_column_has_a_definite_height() -> None:
    """Below 1220px the slide list collapsed to zero height.

    '#slide-list' is `flex:1` with a 0 basis inside '.lp-review-col-slides'.
    Against an auto-height container that resolves to ZERO, so the stacked
    layout rendered the Keep/Reject row with no thumbnails above it -- the
    student was asked to keep or reject slides they could not see. `max-height`
    does not make a height definite; `height` does. Measured in the packaged
    app: listH 0 -> 134 at 1200x720, 1100x680, 1000x640 and 900x600.
    """
    block = CSS.split("@media (max-width:1220px)", 1)[1].split(chr(10) + "}", 1)[0]
    assert ".lp-review-col-slides{height:230px}" in block.replace(" ", ""), (
        "the stacked slides column needs a definite height, not max-height"
    )
    assert ".lp-review-col-slides{max-height" not in block.replace(" ", "")

    # The decision controls need clearance from the footer: the guided tour's
    # spotlight ring carries a 22px glow that otherwise bleeds over it.
    assert "#demo-review-actions{margin-bottom:" in CSS.replace(" ", "")


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
