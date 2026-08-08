"""Regression coverage for the Electron QOL/productivity stabilization pass."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "ui" / "app.js"
HTML = ROOT / "app" / "ui" / "index.html"
MAIN = ROOT / "electron-spike" / "production-main.js"
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_global_search_is_reachable_focus_trapped_and_consumes_timestamp_jump() -> None:
    app = _source(APP)
    html = _source(HTML)

    assert 'id="btn-global-search"' in html
    assert "globalSearchButton.addEventListener('click', openGlobalSearch)" in app
    assert "{ label: 'Search all transcripts', run: function () { openGlobalSearch(); } }" in app
    assert "'batch-overlay', 'search-overlay', 'palette-overlay'" in app
    assert 'data-transcript-time="' in app
    assert "applyPendingTranscriptJump();" in app
    assert "target.scrollIntoView({ block: 'center', inline: 'nearest' })" in app


def test_batch_queue_applies_selected_settings_before_starting() -> None:
    app = _source(APP)
    batch = app[app.index("function batchQueueAll()") : app.index("// ---- Feature 2")]

    assert "lpBridge.call('apply_job_settings', settings)" in batch
    assert "return lpBridge.call('queue_jobs', { job_ids: ids })" in batch
    assert "processing started" in batch


def test_queue_all_promotes_first_job_when_slot_is_idle() -> None:
    spec = importlib.util.spec_from_file_location("lecturepack_qol_sidecar", SIDECAR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sidecar = module.Sidecar.__new__(module.Sidecar)
    queued: list[str] = []
    calls: list[str] = []
    sidecar.queue = object()
    sidecar.electron_backend = SimpleNamespace(
        enqueue_job=lambda _queue, job_id: queued.append(job_id) or (len(queued) - 1)
    )
    sidecar._push_queue = lambda: calls.append("push")
    sidecar._emit_job_payloads = lambda: calls.append("jobs")
    sidecar._respond = lambda *_args, **_kwargs: calls.append("respond")
    sidecar._maybe_resume_queue = lambda: calls.append("resume")

    sidecar._queue_jobs("request-1", "queue_jobs", {"job_ids": ["job-a", "job-b"]})

    assert queued == ["job-a", "job-b"]
    assert calls[-2:] == ["respond", "resume"]


def test_processing_strip_and_taskbar_keep_live_determinate_progress() -> None:
    app = _source(APP)
    main = _source(MAIN)

    status = app[app.index("lpBridge.on('status_changed'") : app.index("lpBridge.on('slides_changed'")]
    assert "renderProcessingStrip();" in status
    assert "session.taskbarProgressJob = String(message.job || session.activeJobId || '')" in main
    assert "session.taskbarProgressJob !== String(message.job || session.activeJobId || '')" in main
    assert "setProgressBar(0.15" not in main


def test_resume_uses_scroll_container_and_persists_on_close() -> None:
    app = _source(APP)

    assert "function transcriptScrollHost()" in app
    assert "document.querySelector('main [data-screen=\"transcript\"]')" in app
    assert "var transcriptEl = transcriptScrollHost();" in app
    assert "window.addEventListener('beforeunload'" in app


def test_palette_opens_completed_lectures_in_review() -> None:
    app = _source(APP)

    assert "status === 'done' ? 'review' : 'process'" in app
    assert "'done' in { id: true }" not in app


def test_new_batch_controls_and_processing_strip_are_keyboard_native() -> None:
    html = _source(HTML)

    assert '<button id="proc-strip" type="button"' in html
    assert '<button type="button" data-bq="balanced"' in html
    assert '<button type="button" data-bo="study"' in html
    assert 'aria-labelledby="batch-title"' in html
    assert 'aria-labelledby="search-title"' in html
    assert 'aria-labelledby="palette-title"' in html
