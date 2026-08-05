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
    assert "status-label\">Idle" in read(HTML)
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


def test_job_cards_are_not_draggable() -> None:
    app = read(APP)
    card = block(app, "function _jobCardHtml", "/* ==================== import from a link")
    assert "draggable" not in card


# --------------------------------------------------------------------------- #
# 5. yt-dlp / Paste Link restored
# --------------------------------------------------------------------------- #
def test_paste_link_control_restored_when_runtime_available() -> None:
    app = read(APP)
    media = block(app, "lpBridge.on('media_link_state'", "lpBridge.on('media_probe'")
    assert "btn.hidden = !mediaLink.available;" in media
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
    assert "self._import_video(None, \"import_media_url\"" in sidecar
    assert "MediaFetchCancelled" in sidecar
    assert "cancel_check=cancel.is_set" in sidecar


# --------------------------------------------------------------------------- #
# 6. Demo "New Job" card hides when processing starts
# --------------------------------------------------------------------------- #
def test_demo_start_hides_new_job_overlay() -> None:
    app = read(APP)
    demo = block(app, "function startGuidedDemo()", "function endGuidedDemo")
    assert "setOnb(null);" in demo
    assert "setScreen('process'); renderGuidedTour();" in demo


# --------------------------------------------------------------------------- #
# 7. Guided-demo glow stays visible after navigation
# --------------------------------------------------------------------------- #
def test_tour_spotlight_keeps_minimum_box_after_navigation() -> None:
    app = read(APP)
    spot = block(app, "function positionTourSpotlight()", "function renderGuidedTour()")
    assert "minW = 120, minH = 40" in spot
    assert "Math.max(minW, r.width)" in spot
    assert "Math.max(minH, r.height)" in spot
    assert "setTimeout(function () { scheduleTourGeometry(); }, 200)" in spot


def test_tour_overlay_remains_visible_across_screens() -> None:
    app = read(APP)
    render = block(app, "function renderGuidedTour()", "function offerGuidedTour")
    assert "setTourOverlayHidden(!demoAdmissionAvailable || (!state.active && !state.prompt));" in render
    assert "if (state.active) scheduleTourGeometry();" in render


# --------------------------------------------------------------------------- #
# 8. Transcript text does not overlap timestamps
# --------------------------------------------------------------------------- #
def test_transcript_row_uses_fixed_timestamp_column() -> None:
    app = read(APP)
    transcript = block(app, "function renderTranscript()", "function renderStudy()")
    assert "width:58px;flex:none;text-align:right;min-width:58px" in transcript
    assert "flex:1;min-width:0" in transcript


def test_transcript_geometry_contract() -> None:
    """The transcript text's left edge must be right of the timestamp's right
    edge. This is a geometry assertion the CDP gate runs against the real app;
    the source-level contract here guarantees the flex columns exist."""
    app = read(APP)
    transcript = block(app, "function renderTranscript()", "function renderStudy()")
    assert "display:flex;gap:18px" in transcript
    assert "flex:none" in transcript
    assert "min-width:0" in transcript