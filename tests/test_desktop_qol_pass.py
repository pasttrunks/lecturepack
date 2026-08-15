"""Focused regression coverage for the desktop QoL polish pass."""
from __future__ import annotations

import importlib.util
import re
import threading
from pathlib import Path
from types import SimpleNamespace

from lecturepack import electron_backend
from lecturepack.models.job import Job
from lecturepack.services.job_ops import clean_display_title


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
MAIN = (ROOT / "electron-spike" / "production-main.js").read_text(encoding="utf-8")
SIDECAR_PATH = ROOT / "electron-spike" / "python-sidecar.py"


def _function_source(name: str) -> str:
    match = re.search(rf"function {name}\([^)]*\) \{{[\s\S]*?\n  \}}", APP)
    assert match, name
    return match.group(0)


def _sidecar_module():
    spec = importlib.util.spec_from_file_location("lecturepack_qol_sidecar", SIDECAR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clean_title_and_rename_preserve_source_identity(tmp_path: Path):
    source = tmp_path / "CL100_Day_04_Egypt_2026-08-09_FINAL_recording.mp4"
    source.write_bytes(b"original bytes")
    data_dir = tmp_path / "data"

    job = Job(str(data_dir), video_path=str(source))
    assert clean_display_title(source.name) == "CL100 Day 04 Egypt"
    assert job.manifest["title"] == "CL100 Day 04 Egypt"
    assert job.manifest["source"] == {
        "original_path": str(source.resolve()),
        "filename": source.name,
    }

    electron_backend.rename_job(str(data_dir), job.job_id, "Egypt and Archaeology")
    reopened = Job(str(data_dir), job_id=job.job_id)
    assert reopened.manifest["title"] == "Egypt and Archaeology"
    assert reopened.manifest["source"]["original_path"] == str(source.resolve())
    assert source.read_bytes() == b"original bytes"


def test_switcher_changes_viewed_job_without_mutating_processing_slot():
    select_source = _function_source("selectJob")
    switcher_source = _function_source("renderLectureSwitcher")
    assert "setActiveJob(jobId" in select_source
    assert "lpBridge.call('view_job', jobId)" in select_source
    assert "activeJobId =" not in select_source
    assert "selectJob(job.id, { screen: sensibleJobScreen(job) })" in APP
    assert "LP.state.activeJobId, LP.state.jobId" in switcher_source
    assert "12 - pinned.length" in switcher_source


def test_eta_and_queue_strip_use_authoritative_job_state():
    eta_source = _function_source("recordProcessingEta")
    strip_source = _function_source("renderProcessingStrip")
    assert "Number(pct)" in eta_source and "elapsed * (100 - state.lastPct) / state.lastPct" in eta_source
    assert "state.lastPct < 8 || elapsed < 20" in eta_source
    assert "running.pct" in strip_source
    assert "LP.data.queue" in strip_source and "queued" in strip_source
    assert "Math.random" not in eta_source + strip_source


def test_update_dialog_accepts_github_release_notes_string():
    source = _function_source("showWhatsNew")
    assert "Array.isArray(info.notes)" in source
    assert ".split(/\\r?\\n+/)" in source
    assert "noteItems" in source
    assert "(info.notes || []).map" not in source


def test_context_menu_routes_through_existing_actions():
    source = _function_source("lectureContextActions")
    for label in ("Open Review", "Open Transcript", "Open Study", "Export", "Rename",
                  "Reveal in Explorer", "Remove from Library", "Cancel Processing",
                  "Move Up", "Move Down", "Remove from Queue", "Retry", "View Error Details"):
        assert label in source
    for command in ("open_job_folder", "cancel_job", "reorder_queue", "remove_from_queue", "restart_job"):
        assert command in source


def test_window_and_session_restore_have_safe_guards():
    assert "screen.getAllDisplays()" in MAIN
    assert "visibleWindowBounds(state.bounds) ? state : null" in MAIN
    assert "getNormalBounds" in MAIN and "restoredWindow.maximized" in MAIN
    restore_source = _function_source("restoreAppSessionOnce")
    assert "saved.jobId" in restore_source and "saved.screen" in restore_source
    assert "pendingTranscriptJump" in _function_source("applyResumeState")
    assert "beforeunload" in APP and "captureResumeState" in APP


def test_home_continue_captures_the_screen_being_left():
    source = APP[APP.index("function setScreen(name)"):APP.index("function applyTheme", APP.index("function setScreen(name)"))]
    assert "captureResumeState(LP.state.jobId)" in source
    assert "renderContinueCard()" in source
    assert source.index("captureResumeState(LP.state.jobId)") < source.index("LP.state.screen = name")


def test_batch_url_entries_are_queued_without_waiting_for_download(tmp_path: Path):
    module = _sidecar_module()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._download_lock = threading.Lock()
    sidecar._downloads = {}
    sidecar._download_order = []
    sidecar.media_fetch = SimpleNamespace(looks_like_url=lambda value: value.startswith("https://"))
    sidecar._emit_downloads = lambda: None
    sidecar._start_download_worker = lambda: None
    responses = []
    sidecar._respond = lambda request_id, command, **payload: responses.append(payload)

    sidecar._import_media_url("request", "import_media_url", {"items": [
        {"url": "https://example.test/week-4", "title": "Week 4"},
        {"url": "https://example.test/week-5", "title": "Week 5"},
    ]})

    assert responses[-1]["count"] == 2
    assert [sidecar._downloads[item]["status"] for item in sidecar._download_order] == ["waiting", "waiting"]
    assert "linkProgressDialog(info.title" not in APP
    assert "function linkProgressDialog" not in APP
    assert "lpBridge.call('import_media_url', { items:" in APP


def test_completed_background_download_uses_normal_import_path(tmp_path: Path, monkeypatch):
    module = _sidecar_module()
    target = tmp_path / "Week 4.mp4"
    target.write_bytes(b"video")

    class Fetcher:
        def download(self, url, destination, progress_cb=None, cancel_check=None, title=None):
            assert not cancel_check()
            destinations.append(Path(destination))
            progress_cb({"status": "downloading", "pct": 42, "eta": 60})
            return str(target)

    class ImmediateTimer:
        @staticmethod
        def singleShot(delay, context, callback):
            callback()

    monkeypatch.setattr(module, "QTimer", ImmediateTimer)
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._shutting_down = False
    sidecar._poll_timer = object()
    sidecar._download_lock = threading.Lock()
    sidecar._download_order = ["download-1"]
    sidecar._downloads = {"download-1": {
        "id": "download-1", "url": "https://example.test/week-4", "title": "Week 4",
        "status": "waiting", "pct": 0, "eta": 0, "speed": 0, "error": "",
    }}
    sidecar._download_cancel = {}
    sidecar._download_worker_running = True
    sidecar.media_fetch = SimpleNamespace(MediaFetcher=Fetcher, MediaFetchCancelled=RuntimeError)
    sidecar._downloads_dir = lambda: str(tmp_path)
    events = []
    destinations = []
    imported = []
    sidecar._emit = events.append
    sidecar._emit_downloads = lambda: None
    sidecar._import_video = lambda request_id, command, payload: imported.append(payload)

    sidecar._download_worker()

    # The download hands over the media and its title exactly as before, plus
    # the directory the captions landed in. That extra key is what scopes
    # caption adoption to downloads: a local import never supplies it.
    assert len(imported) == 1
    assert imported[0]["path"] == str(target)
    assert imported[0]["title"] == "Week 4"
    assert imported[0]["captions_dir"], "the download must pass its captions directory"
    assert destinations == [tmp_path / "download-1"]
    assert sidecar._downloads["download-1"]["status"] == "complete"
    assert any(event.get("event") == "media_progress" and event.get("pct") == 42 for event in events)
    assert any(event.get("event") == "media_done" and event.get("ok") for event in events)
