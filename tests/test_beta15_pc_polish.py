"""Focused contracts for the Beta 15 PC polish fixes.

Each check targets one of the eight PC-tested defects without requiring a live
window: source-level assertions at the renderer/host boundary plus geometry
contracts that the CDP/UIA gates can exercise against the real app.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
APP = UI / "app.js"
HTML = UI / "index.html"
CSS = UI / "app.css"
MAIN = ROOT / "electron-spike" / "production-main.js"
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"
PACKAGE_WIN = ROOT / "electron-spike" / "package-win.mjs"
SIDECAR_SPEC = ROOT / "electron-spike" / "sidecar.spec"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


# --------------------------------------------------------------------------- #
# 1. Instant video thumbnails
# --------------------------------------------------------------------------- #
def test_sidecar_generates_poster_at_import() -> None:
    sidecar = read(SIDECAR)
    assert "def _generate_poster" in sidecar
    assert "poster.webp" in sidecar
    assert "self._generate_poster(job, source)" in sidecar
    # A thumbnail failure must never prevent the import.
    assert "thumbnail failure must not block import" in sidecar


# --------------------------------------------------------------------------- #
# Demo lecture provenance
# --------------------------------------------------------------------------- #
def test_bundled_demo_matches_attested_polar_bears_lecture() -> None:
    """The demo the app bundles must be the attested Polar Bears lecture
    (PROVENANCE.md in app/assets/demo). A stale or swapped demo file fails here
    rather than shipping a wrong guided-demo video."""
    import hashlib
    demo = ROOT / "electron-spike" / "assets" / "demo-lecture.mp4"
    thumb = ROOT / "app" / "assets" / "demo" / "polar_bears_thumbnail.jpg"
    mp4_sha = hashlib.sha256(demo.read_bytes()).hexdigest()
    jpg_sha = hashlib.sha256(thumb.read_bytes()).hexdigest()
    assert mp4_sha == "24957e863c477cd7ad2ef9228f3bbe943f5038e5ccd18ef7ab92efefee13f55f"
    assert jpg_sha == "6120e615b8f5d3006be9bb786b856c15ae1b6ae9c0a80b106d5f48280556795f"


def test_electron_serves_lpasset_poster_protocol() -> None:
    main = read(MAIN)
    assert "protocol.handle('lpasset'" in main
    assert "url.hostname !== 'poster'" in main
    assert "poster.webp" in main
    assert "registerAssetProtocol();" in main


def test_renderer_requests_poster_through_lpasset() -> None:
    app = read(APP)
    assert "lpasset://poster/" in app
    assert "function posterSrc" in app


def test_packaged_demo_thumbnail_asset_is_attested() -> None:
    import hashlib
    thumbnail = ROOT / "electron-spike" / "assets" / "demo" / "polar_bears_thumbnail.jpg"
    assert thumbnail.is_file()
    assert hashlib.sha256(thumbnail.read_bytes()).hexdigest() == (
        "6120e615b8f5d3006be9bb786b856c15ae1b6ae9c0a80b106d5f48280556795f"
    )


# --------------------------------------------------------------------------- #
# 2. False "Transcribing audio" idle status
# --------------------------------------------------------------------------- #
def test_terminal_status_clears_stale_processing_text() -> None:
    app = read(APP)
    status = block(app, "lpBridge.on('status_changed'", "lpBridge.on('slides_changed'")
    assert "pendingProcessingStatus = {};" in status
    assert "lastStatusRenderKey = null;" in status
    assert "statusLabel.textContent = 'Idle'" in status
    assert "terminalLabel === 'cancelled'" in status


def test_idle_status_never_says_transcribing_without_active_job() -> None:
    app = read(APP)
    # The friendly label only maps a raw backend stage to "Transcribing audio";
    # the terminal-status path above clears it. The idle default is "Idle".
    # #status-label became #status-state when the two bottom bars were merged:
    # it carries the STATE WORD only now, and #status-detail owns the stage
    # text. Both bars used to print the stage, which is what made them clash.
    assert "status-state\">Idle" in read(HTML)
    assert "friendlyProcessingLabel(s.label) || 'Idle'" in app


# --------------------------------------------------------------------------- #
# 3. Default Electron taskbar icon
# --------------------------------------------------------------------------- #
def test_packaged_icon_configuration_uses_lecturepack_icon() -> None:
    package = read(PACKAGE_WIN)
    assert "lecturepack.ico" in package
    assert "icon," in package
    main = read(MAIN)
    assert "function applicationIcon()" in main
    assert "lecturepack.ico" in main
    assert "icon ? { icon } : {}" in main


# --------------------------------------------------------------------------- #
# 4. Dragging moves only the thumbnail
# --------------------------------------------------------------------------- #
def test_demo_card_drag_restricted_to_thumbnail() -> None:
    html = read(HTML)
    # The outer card is no longer draggable; only the <img> is.
    assert re.search(r'id="glowing-demo-card"[^>]*type="button"[^>]*>', html)
    assert "draggable=\"true\"" in html
    assert re.search(r'<img[^>]*draggable="true"[^>]*>', html)
    app = read(APP)
    drag = block(app, "demoCard.addEventListener('dragstart'", "demoCard.addEventListener('dragend'")
    assert "e.target.tagName !== 'IMG'" in drag
    assert "e.preventDefault(); return;" in drag


def test_only_queueable_job_cards_are_draggable() -> None:
    """Draggable now means "the pipeline can run on this": never-processed
    lectures AND finished ones (which re-run). A lecture that is running,
    paused or already in the queue stays undraggable."""
    app = read(APP)
    card = block(app, "function _jobCardHtml", "/* ==================== import from a link")
    # One conditional gates every drag attribute, so an ineligible card cannot
    # acquire one of them by accident. The native draggable="true" was dropped
    # when the pointer-driven drag layer took over: leaving it on would let
    # Chromium start its own unstyleable drag for the same press.
    assert "draggable ? 'data-existing-job-drag=\"true\" data-lp-drag=\"lecture\" ' : ''" in card
    assert "cursor:' + (draggable ? 'grab' : 'pointer')" in card
    assert "var draggable = _jobIsDraggable(j);" in card
    # The grip is the resting affordance, and its ABSENCE is the honest signal
    # on a card that could never lift.
    assert "var grip = draggable" in card
    # The Start/Options button row must stay on _jobIsReady: a finished lecture
    # becoming draggable must not also grow a Start button.
    assert "if (j.id && ready) {" in card


# --------------------------------------------------------------------------- #
# 5. yt-dlp / Paste Link restored
# --------------------------------------------------------------------------- #
def test_paste_link_control_restored_when_runtime_available() -> None:
    app = read(APP)
    media = block(app, "lpBridge.on('media_link_state'", "lpBridge.on('media_probe'")
    assert "btn.hidden = false;" in media
    assert "btn.disabled = !mediaLink.available;" in media
    assert "bundled yt-dlp runtime could not load" in media
    assert "lpBridge.call('media_link_support')" in app
    main = read(MAIN)
    # The production scope no longer hides the Paste Link control.
    scope = main.split("const productionScope", 1)[1].split("</style>", 1)[0]
    assert "#btn-paste-link" not in scope


def test_sidecar_bundles_yt_dlp_extractors() -> None:
    spec = read(SIDECAR_SPEC)
    assert "collect_submodules(\"yt_dlp\")" in spec
    assert "yt-dlp resolves extractors by name at runtime" in spec


def test_media_fetch_uses_normal_import_path() -> None:
    sidecar = read(SIDECAR)
    assert "def _import_media_url" in sidecar
    # The call is wrapped across lines now that it also carries captions_dir,
    # so assert the parts rather than one contiguous string.
    assert "self._import_video(" in sidecar
    assert '"import_media_url"' in sidecar
    assert '"captions_dir": d' in sidecar, (
        "only the download path may hand captions to the importer"
    )
    assert "QTimer.singleShot(0, self._poll_timer" in sidecar
    assert "MediaFetchCancelled" in sidecar
    assert "cancel_check=cancel.is_set" in sidecar


# --------------------------------------------------------------------------- #
# 6. Demo processing closes onboarding before the real run
# --------------------------------------------------------------------------- #
def test_demo_start_hides_new_job_overlay() -> None:
    app = read(APP)
    demo = block(app, "function runDemoForReal()", "function bindDemoScreen")
    assert "setOnb(null);" in demo
    assert "closeDemo('process');" in demo
    assert "lpBridge.startDemoJob()" in demo


def test_demo_onboarding_event_does_not_restore_new_job_overlay() -> None:
    app = read(APP)
    onboarding = block(app, "lpBridge.on('onboarding'", "lpBridge.on('update_available'")
    assert "guidedDemo.snapshot().active" in onboarding
    assert "if (demoIsActive)" in onboarding
    assert "setOnb(null);" in onboarding
    # Normal imports (no active demo session) must show the pre-processing
    # setup panel; only an active guided-demo session suppresses it. The old
    # `demoFlowPhase() !== 'import'` clause also swallowed NORMAL imports
    # because the flow phase is 'idle' outside the tour.
    assert "demoFlowPhase() !== 'import'" not in onboarding
    assert "setOnb('detected');" in onboarding


# --------------------------------------------------------------------------- #
# 7. The legacy live-screen spotlight cannot return
# --------------------------------------------------------------------------- #
def test_demo_has_no_live_screen_spotlight_geometry() -> None:
    app = read(APP)
    for token in ("positionTourSpotlight", "positionTourCard", "scheduleTourGeometry"):
        assert token not in app


def test_demo_is_a_real_screen_in_normal_navigation() -> None:
    app = read(APP)
    html = read(HTML)
    assert '<section data-screen="demo"' in html
    assert "function openDemo(startAt)" in app
    assert "setScreen('demo');" in block(app, "function openDemo(startAt)", "function closeDemo")


# --------------------------------------------------------------------------- #
# 8. Transcript text does not overlap timestamps
# --------------------------------------------------------------------------- #
def test_transcript_row_uses_fixed_timestamp_column() -> None:
    app = read(APP)
    review = block(app, "function renderReviewTranscript()", "function renderTranscript()")
    transcript = block(app, "function renderTranscript()", "function renderStudy()")
    assert "width:104px;flex:none;min-width:104px;white-space:nowrap" in review
    assert "width:104px;flex:none;text-align:right;min-width:104px;white-space:nowrap" in transcript
    assert "overflow-wrap:anywhere" in review
    assert "flex:1;min-width:0" in transcript


def test_transcript_geometry_contract() -> None:
    """The transcript text's left edge must be right of the timestamp's right
    edge. This is a geometry assertion the CDP gate runs against the real app;
    the source-level contract here guarantees the flex columns exist."""
    app = read(APP)
    transcript = block(app, "function renderTranscript()", "function renderStudy()")
    assert "display:flex;gap:18px" in transcript
    assert "flex:none" in transcript
    assert "min-width:104px" in transcript
    assert "min-width:0" in transcript
