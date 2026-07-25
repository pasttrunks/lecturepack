"""Adapter/bridge surface for "Import from a link".

Fake backend + fake fetcher; no network, no real yt-dlp calls. Guards the
contract the UI depends on: capability reporting, probe/progress/done payload
shapes, one-at-a-time, cancel, and that the finished file reaches import_video.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    _SIGNALS = ("log_line", "jobs_changed", "media_link_state", "media_probe",
                "media_progress", "media_done", "status_changed")

    def __init__(self):
        for n in self._SIGNALS:
            setattr(self, n, _Signal())

    def last(self, name):
        em = getattr(self, name).emissions
        return json.loads(em[-1]) if em else None


# --------------------------------------------------------------- signal wiring

def test_bridge_signals_match_ui_signal_list():
    """bridge.py signals MUST stay in sync with app/ui/bridge.js SIGNALS."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "app", "ui", "bridge.js"), encoding="utf-8").read()
    py = open(os.path.join(root, "app", "desktop", "bridge.py"), encoding="utf-8").read()
    for name in ("media_link_state", "media_probe", "media_progress", "media_done"):
        assert f"'{name}'" in js, f"{name} missing from bridge.js SIGNALS"
        assert f"{name} = Signal(str)" in py, f"{name} missing from bridge.py"


def test_bridge_exposes_link_slots():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = open(os.path.join(root, "app", "desktop", "bridge.py"), encoding="utf-8").read()
    for slot in ("def media_link_support", "def probe_media_url",
                 "def import_media_url", "def cancel_media_url"):
        assert slot in py


# ------------------------------------------------------------- base/demo adapter

def test_base_adapter_reports_capability_without_crashing():
    b = _FakeBackend()
    ea.EngineAdapter(b).media_link_support()
    state = b.last("media_link_state")
    assert set(state) == {"available", "version"}
    assert isinstance(state["available"], bool)


def test_base_adapter_link_calls_fail_gracefully():
    b = _FakeBackend()
    a = ea.EngineAdapter(b)
    a.probe_media_url("https://e.com/x")
    a.import_media_url("https://e.com/x", "t")
    a.cancel_media_url()                        # must not raise
    assert b.last("media_probe")["ok"] is False
    assert b.last("media_done")["ok"] is False


def test_capability_helpers_never_raise(monkeypatch):
    monkeypatch.setitem(sys.modules, "lecturepack.services.media_fetch", None)
    assert ea._media_fetch_available() in (True, False)
    assert isinstance(ea._media_fetch_version(), str)


# --------------------------------------------------------- real adapter methods
# The real adapter is heavyweight, so exercise the link methods on a minimal
# stand-in that reuses them unbound — the behaviour under test is entirely in
# these methods plus the injected fetcher.

class _Stub:
    """Minimal host for the LecturePackAdapter link methods."""

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
    # Run queued main-thread callbacks immediately, and run the download worker
    # inline -- otherwise assertions race the background thread.
    # NOTE (BUG-09): this stub replaces the very call that was broken in
    # production -- `QTimer.singleShot` from a worker thread never fired -- so
    # every test in this file passed while link import was completely dead.
    # A stub that swallows the arity difference cannot detect that class of
    # bug; `tests/test_emit_soon_threading.py` exercises the REAL call instead.
    # Accept both the (ms, fn) and (ms, context, fn) overloads so this fixture
    # never again dictates which one production code is allowed to use.
    def _immediate_single_shot(ms, *args):
        args[-1]()

    monkeypatch.setattr(ea.QTimer, "singleShot",
                        staticmethod(_immediate_single_shot))
    monkeypatch.setattr(ea.threading, "Thread", _ImmediateThread)
    return _Stub(_FakeBackend(), tmp_path)


def test_downloads_dir_lives_inside_the_data_dir(stub, tmp_path):
    d = stub._downloads_dir()
    assert d == os.path.join(str(tmp_path), "downloads")
    assert os.path.isdir(d)


def test_emit_soon_serialises_payload(stub):
    stub._emit_soon(stub.backend.media_progress, {"pct": 42})
    assert stub.backend.last("media_progress") == {"pct": 42}


def test_probe_emits_metadata(stub, monkeypatch):
    class FakeFetcher:
        def probe(self, url):
            return {"title": "Lec", "duration": 60, "uploader": "P",
                    "extractor": "X", "is_live": False, "webpage_url": url}
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.probe_media_url("https://e.com/x")
    got = stub.backend.last("media_probe")
    assert got["ok"] is True and got["title"] == "Lec"


def test_probe_reports_friendly_error(stub, monkeypatch):
    from lecturepack.services.media_fetch import MediaFetchError

    class FakeFetcher:
        def probe(self, url):
            raise MediaFetchError("That video is unavailable.")
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.probe_media_url("https://e.com/x")
    got = stub.backend.last("media_probe")
    assert got["ok"] is False and "unavailable" in got["error"]


def test_probe_survives_unexpected_exception(stub, monkeypatch):
    class FakeFetcher:
        def probe(self, url):
            raise ValueError("kaboom" * 200)
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.probe_media_url("https://e.com/x")
    got = stub.backend.last("media_probe")
    assert got["ok"] is False and len(got["error"]) <= 300


def test_successful_download_hands_file_to_import_video(stub, tmp_path, monkeypatch):
    target = tmp_path / "downloads" / "lec.mp4"

    class FakeFetcher:
        def download(self, url, dest, progress_cb=None, cancel_check=None, title=None):
            os.makedirs(dest, exist_ok=True)
            target.write_bytes(b"v")
            if progress_cb:
                progress_cb({"status": "downloading", "pct": 50})
            return str(target)
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.import_media_url("https://e.com/x", "Lec")
    done = stub.backend.last("media_done")
    assert done["ok"] is True and done["name"] == "lec.mp4"
    assert stub.imported == [str(target)]
    assert stub.backend.last("media_progress")["pct"] == 50


def test_cancelled_download_reports_cancelled_and_does_not_import(stub, monkeypatch):
    from lecturepack.services.media_fetch import MediaFetchCancelled

    class FakeFetcher:
        def download(self, url, dest, progress_cb=None, cancel_check=None, title=None):
            raise MediaFetchCancelled()
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.import_media_url("https://e.com/x", "Lec")
    done = stub.backend.last("media_done")
    assert done["cancelled"] is True and done["ok"] is False
    assert stub.imported == []


def test_failed_download_reports_error_and_does_not_import(stub, monkeypatch):
    from lecturepack.services.media_fetch import MediaFetchError

    class FakeFetcher:
        def download(self, url, dest, progress_cb=None, cancel_check=None, title=None):
            raise MediaFetchError("That video is private or needs a sign-in.")
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub.import_media_url("https://e.com/x", "Lec")
    done = stub.backend.last("media_done")
    assert done["ok"] is False and "private" in done["error"]
    assert stub.imported == []


def test_only_one_download_at_a_time(stub, monkeypatch):
    class FakeFetcher:
        def download(self, url, dest, progress_cb=None, cancel_check=None, title=None):
            raise AssertionError("should not start a second transfer")
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    stub._media_busy = True
    stub.import_media_url("https://e.com/x", "Lec")
    done = stub.backend.last("media_done")
    assert done["ok"] is False and "already running" in done["error"]


def test_cancel_sets_the_event(stub):
    import threading
    ev = threading.Event()
    stub._media_cancel = ev
    stub.cancel_media_url()
    assert ev.is_set()


def test_cancel_without_active_download_is_a_noop(stub):
    stub.cancel_media_url()          # no _media_cancel attribute at all
    assert stub.backend.media_done.emissions == []


def test_cancel_check_passed_to_fetcher_reflects_the_event(stub, monkeypatch):
    seen = {}

    class FakeFetcher:
        def download(self, url, dest, progress_cb=None, cancel_check=None, title=None):
            seen["before"] = cancel_check()
            stub._media_cancel.set()
            seen["after"] = cancel_check()
            return os.path.join(dest, "x.mp4")
    monkeypatch.setattr("lecturepack.services.media_fetch.MediaFetcher", FakeFetcher)
    os.makedirs(os.path.join(stub.config.data_dir, "downloads"), exist_ok=True)
    open(os.path.join(stub.config.data_dir, "downloads", "x.mp4"), "wb").close()
    stub.import_media_url("https://e.com/x", "")
    assert seen == {"before": False, "after": True}


# ------------------------------------------------------------------- packaging

def test_spec_collects_ytdlp_submodules():
    """Extractors are imported by name -- without collect_submodules every URL
    fails in the packaged build."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = open(os.path.join(root, "app", "packaging", "lecturepack.spec"),
                encoding="utf-8").read()
    assert 'collect_submodules("yt_dlp")' in spec
    assert "ytdlp_hiddenimports" in spec.split("hiddenimports=[", 1)[1][:400]


def test_requirements_pins_ytdlp():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    req = open(os.path.join(root, "requirements.txt"), encoding="utf-8").read()
    assert "yt-dlp" in req


def test_downloads_dir_never_bundled():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build = open(os.path.join(root, "app", "packaging", "build.py"),
                 encoding="utf-8").read()
    forbidden = build.split("forbidden_dir_names = {", 1)[1].split("}", 1)[0]
    assert "downloads" in forbidden
