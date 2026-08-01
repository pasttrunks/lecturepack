"""Phase 2 Plan 3 regression guards: D-08 (sensitivity lock during normal
processing) and D-09 (Paste Link / yt-dlp wiring verification).

D-08: the slide sensitivity preset must be locked while a NORMAL job is
processing, not just during the guided demo -- otherwise a user can click a
different preset mid-run, see it render "active", and the already-running
job silently ignores it because its preset was snapshotted at
start_processing() time. Tests (a)/(b) are structural (parse app.js) because
the lock lives entirely in JS with no Python-observable side effect.

D-09: the Paste Link probe/download/import chain (media_link_support ->
probe_media_url -> media_probe -> import_media_url -> download -> import_video)
was already fully wired in current code (RESEARCH.md Q5); tests (c)-(g) prove
it and guard the BUG-18 cancel regression. Follows the fake-backend + fake-
fetcher pattern from tests/test_media_link_adapter.py -- no network, no real
yt-dlp calls.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402

JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()


# --------------------------------------------------------------- D-08 (a)/(b)

def _function_body(js: str, name: str) -> str:
    """Best-effort extraction of a top-level ``function name() { ... }`` body
    by brace counting, so the structural asserts below are robust to
    reformatting inside the function."""
    m = re.search(r"function\s+%s\s*\([^)]*\)\s*\{" % re.escape(name), js)
    assert m, f"function {name} not found in app.js"
    start = m.end()
    depth = 1
    i = start
    while depth > 0:
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
        i += 1
    return js[start:i - 1]  # exclude the matching closing brace itself


def test_sensitivity_lock_function_checks_pipeline_running():
    """renderSlideDetectionPreset's locked computation must reference the
    normal-processing flag in addition to the guided-demo lock (D-08)."""
    body = _function_body(JS, "renderSlideDetectionPreset")
    assert "guidedDemoSensitivityLocked()" in body
    assert "LP.state.pipelineRunning" in body
    # Both must feed the same `locked` boolean via a boolean OR (not two
    # independent, possibly-inconsistent checks) -- allow an intermediate
    # variable (e.g. `demoLocked = guidedDemoSensitivityLocked()`) as long as
    # the final `locked = ... || ... pipelineRunning` line uses it.
    locked_line = next(line for line in body.splitlines() if "locked =" in line
                        and "pipelineRunning" in line)
    assert "||" in locked_line
    demo_var = locked_line.split("||")[0].strip().split("=")[-1].strip()
    assert demo_var in body, f"could not resolve {demo_var!r} back to guidedDemoSensitivityLocked() in body"
    assert re.search(re.escape(demo_var) + r"\s*=\s*guidedDemoSensitivityLocked\(\)", body), \
        "the locked line's demo-check operand must trace back to guidedDemoSensitivityLocked()"


def test_set_slide_detection_preset_guards_against_pipeline_running():
    """setSlideDetectionPreset's early-return guard must also check the
    normal-processing flag, or a click during processing would persist a
    setting change even though the button renders disabled (D-08)."""
    body = _function_body(JS, "setSlideDetectionPreset")
    guard_line = next(line for line in body.splitlines() if "return;" in line)
    assert "guidedDemoSensitivityLocked()" in guard_line
    assert "LP.state.pipelineRunning" in guard_line


def test_guided_demo_lock_function_is_unchanged():
    """The demo-path lock itself must remain untouched -- this plan adds a
    parallel check for normal processing, not a rewrite of the demo lock."""
    body = _function_body(JS, "guidedDemoSensitivityLocked")
    assert body.strip() == "return guidedTour.snapshot().active && demoFlowPhase() !== 'idle';"


def test_pipeline_running_flag_declared_in_state():
    assert "pipelineRunning" in JS
    assert re.search(r"pipelineRunning:\s*false", JS), \
        "LP.state.pipelineRunning must default to false"


# --------------------------------------------------------------- D-09 fakes

class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    _SIGNALS = ("log_line", "jobs_changed", "storage_changed", "media_link_state",
                "media_probe", "media_progress", "media_done", "status_changed")

    def __init__(self):
        for n in self._SIGNALS:
            setattr(self, n, _Signal())

    def last(self, name):
        em = getattr(self, name).emissions
        return json.loads(em[-1]) if em else None


class _Stub:
    """Minimal host for the LecturePackAdapter link methods (same shape as
    tests/test_media_link_adapter.py's _Stub) so these tests exercise the
    REAL production methods, not a re-implementation of them."""

    media_link_support = ea.LecturePackAdapter.media_link_support
    probe_media_url = ea.LecturePackAdapter.probe_media_url
    import_media_url = ea.LecturePackAdapter.import_media_url
    cancel_media_url = ea.LecturePackAdapter.cancel_media_url
    _downloads_dir = ea.LecturePackAdapter._downloads_dir
    _emit_soon = ea.LecturePackAdapter._emit_soon

    def __init__(self, backend, data_dir):
        self.backend = backend
        self.config = type("C", (), {"data_dir": str(data_dir)})()
        self.imported = []
        self.logs = []

    def _log(self, tag, text, kind):
        self.logs.append((tag, text))

    def import_video(self, path):
        self.imported.append(path)


class _ImmediateThread:
    """Runs the target on .start() so tests are deterministic, not racy."""

    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


@pytest.fixture()
def stub(tmp_path, monkeypatch):
    def _immediate_single_shot(ms, *args):
        args[-1]()

    monkeypatch.setattr(ea.QTimer, "singleShot", staticmethod(_immediate_single_shot))
    monkeypatch.setattr(ea.threading, "Thread", _ImmediateThread)
    return _Stub(_FakeBackend(), tmp_path)


# ------------------------------------------------------------------- (c)

def test_media_fetch_available_returns_true_when_yt_dlp_importable():
    try:
        import yt_dlp  # noqa: F401
    except Exception:
        pytest.skip("yt_dlp is not installed in this test environment")
    assert ea._media_fetch_available() is True


# ------------------------------------------------------------------- (d)

def test_probe_media_url_emits_media_probe_signal(stub, monkeypatch):
    class FakeFetcher:
        def probe(self, url):
            return {"title": "Test Lecture", "duration": 120, "uploader": "Prof",
                     "extractor": "generic", "is_live": False, "webpage_url": url}

    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.probe_media_url("https://example.com/lecture")
    got = stub.backend.last("media_probe")
    assert got is not None, "media_probe was never emitted"
    assert got["ok"] is True
    assert got["title"] == "Test Lecture"


# ------------------------------------------------------------------- (e)

def test_import_media_url_on_success_calls_import_video(stub, tmp_path, monkeypatch):
    target = tmp_path / "downloads" / "lecture.mp4"

    class FakeFetcher:
        def download(self, url, dest, progress_cb=None, cancel_check=None, title=None):
            os.makedirs(dest, exist_ok=True)
            target.write_bytes(b"video-bytes")
            return str(target)

    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.import_media_url("https://example.com/lecture", "Test Lecture")

    done = stub.backend.last("media_done")
    assert done["ok"] is True
    assert stub.imported == [str(target)], "download success did not hand the file to import_video"


# ------------------------------------------------------------------- (f)

def test_import_media_url_on_cancel_does_not_import(stub, monkeypatch):
    """BUG-18 regression guard: a cancel that lands after the transfer
    completes must not still become a job."""
    from lecturepack.services.media_fetch import MediaFetchCancelled

    class FakeFetcher:
        def download(self, url, dest, progress_cb=None, cancel_check=None, title=None):
            raise MediaFetchCancelled()

    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.import_media_url("https://example.com/lecture", "Test Lecture")

    done = stub.backend.last("media_done")
    assert done["ok"] is False
    assert done.get("cancelled") is True
    assert stub.imported == [], "a cancelled download must never reach import_video"


# ------------------------------------------------------------------- (g)

def test_media_link_state_hides_button_when_unavailable(monkeypatch):
    backend = _FakeBackend()
    adapter = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    adapter.backend = backend
    monkeypatch.setattr(ea, "_media_fetch_available", lambda: False)
    monkeypatch.setattr(ea, "_media_fetch_version", lambda: "")

    ea.LecturePackAdapter.media_link_support(adapter)

    state = backend.last("media_link_state")
    assert state == {"available": False, "version": ""}


def test_media_link_state_js_handler_hides_button():
    """Structural guard: the JS handler must hide #btn-paste-link when
    media_link_state reports unavailable (D-04 discretion)."""
    m = re.search(r"lpBridge\.on\('media_link_state',\s*function[^{]*\{(.*?)\}\);",
                  JS, re.S)
    assert m, "media_link_state handler not found in app.js"
    body = m.group(1)
    assert "btn-paste-link" in body
    assert "hidden" in body
