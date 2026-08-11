"""Focused renderer regressions for the LecturePack 2.0.1 polish pass."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
HTML = (UI / "index.html").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "app.css").read_text(encoding="utf-8")


def function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


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
    assert "startGuidedDemo()" in replay
    assert "set_guided_tour_state" in JS
    assert "markTourSeen('skipped')" in JS
    assert "markTourSeen('completed')" in JS
    assert "replay_guided_tour" in JS


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
