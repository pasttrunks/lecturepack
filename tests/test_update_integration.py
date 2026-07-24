"""Updater integration against a LOCAL injected release feed (§15).

Serves a fake release JSON + Setup.exe + SHA256SUMS from an in-process HTTP
server (via the LECTUREPACK_UPDATE_FEED / LECTUREPACK_UPDATE_HOSTS test-only
env overrides) and drives the real Qt Updater: discovery, verified download,
checksum-mismatch rejection, active-job install block, visible installer
handoff flags, and portable no-self-replace. No real GitHub, no real install.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import sys
import threading
import types

import pytest
from PySide6.QtCore import QObject, QSettings, Signal

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import updater as up_mod  # noqa: E402

INSTALLER_BYTES = b"LECTUREPACK-FAKE-INSTALLER-PAYLOAD" * 64
GOOD_DIGEST = hashlib.sha256(INSTALLER_BYTES).hexdigest()
SETUP_NAME = "LecturePack-0.9.0-beta.2-Setup.exe"
SUMS_NAME = "LecturePack-0.9.0-beta.2-SHA256SUMS.txt"


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/octet-stream", clen=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(clen if clen is not None else len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        st = self.server.state
        port = self.server.server_address[1]
        base = f"http://127.0.0.1:{port}"
        if self.path.startswith("/releases"):
            rel = {
                "tag_name": "v0.9.0-beta.2", "name": "Public Beta 2",
                "draft": False, "prerelease": True,
                "published_at": "2026-07-22T10:00:00Z",
                "html_url": "https://github.com/pasttrunks/lecturepack/releases/tag/v0.9.0-beta.2",
                "body": "## Improvements\n- Faster slides\n## Fixes\n- Export fix\n",
                "assets": [
                    {"name": SETUP_NAME, "size": len(INSTALLER_BYTES), "state": "uploaded",
                     "digest": f"sha256:{GOOD_DIGEST}",
                     "browser_download_url": f"{base}/dl/{SETUP_NAME}"},
                    {"name": "LecturePack-0.9.0-beta.2-Portable.zip",
                     "size": len(INSTALLER_BYTES), "state": "uploaded",
                     "browser_download_url": f"{base}/dl/LecturePack-0.9.0-beta.2-Portable.zip"},
                    {"name": SUMS_NAME, "size": 200, "state": "uploaded",
                     "browser_download_url": f"{base}/dl/{SUMS_NAME}"},
                ],
            }
            self._send(200, json.dumps([rel]).encode(), "application/json")
        elif self.path.endswith(SUMS_NAME):
            digest = "0" * 64 if st.get("mismatch") else GOOD_DIGEST
            body = f"{digest}  {SETUP_NAME}\n".encode()
            self._send(200, body, "text/plain")
        elif self.path.endswith(SETUP_NAME):
            if st.get("truncate"):
                # Claim the full length but send only half, then close: the
                # partial file must fail verification and never be launchable.
                half = INSTALLER_BYTES[: len(INSTALLER_BYTES) // 2]
                self._send(200, half, clen=len(INSTALLER_BYTES))
            else:
                self._send(200, INSTALLER_BYTES)
        else:
            self._send(404, b"nope")


@pytest.fixture
def feed(tmp_path, monkeypatch):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.state = {"mismatch": False, "truncate": False}
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    port = srv.server_address[1]
    monkeypatch.setenv("LECTUREPACK_UPDATE_FEED", f"http://127.0.0.1:{port}/releases")
    monkeypatch.setenv("LECTUREPACK_UPDATE_HOSTS", "127.0.0.1")
    # Redirect the update cache + QSettings to the temp dir.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "qs"))
    yield srv
    srv.shutdown()


class _Backend(QObject):
    update_available = Signal(str)
    update_progress = Signal(float)
    update_ready = Signal()
    update_error = Signal(str)
    update_state = Signal(str)
    whatsnew = Signal(str)
    settings_changed = Signal(str)

    def __init__(self, processing=False):
        super().__init__()
        self._adapter = types.SimpleNamespace(
            is_processing=lambda: self._processing,
            save_project=lambda: None)
        self._processing = processing


def _make(qtbot, monkeypatch, installed=True, processing=False):
    monkeypatch.setattr(up_mod.version, "__version__", "0.9.0-beta.1")
    backend = _Backend(processing=processing)
    up = up_mod.Updater(backend)
    up._settings.setValue("update_channel", "beta")
    if installed:
        monkeypatch.setattr(up, "is_portable", lambda: False)
    return backend, up


def test_discovery_download_verify_ready(qtbot, feed, monkeypatch):
    backend, up = _make(qtbot, monkeypatch, installed=True)
    with qtbot.waitSignal(backend.update_available, timeout=6000) as blk:
        up.check(manual=True)
    ov = json.loads(blk.args[0])
    assert ov["available"] == "0.9.0-beta.2" and ov["channel"] == "Beta"
    with qtbot.waitSignal(backend.update_ready, timeout=8000):
        up.start_download()
    assert up._verified_path and os.path.exists(up._verified_path)
    assert up_mod.us.sha256_file(up._verified_path) == GOOD_DIGEST


def test_checksum_mismatch_blocks_and_deletes(qtbot, feed, monkeypatch):
    feed.state["mismatch"] = True
    backend, up = _make(qtbot, monkeypatch, installed=True)
    states = []
    backend.update_state.connect(lambda j: states.append(json.loads(j)))
    ready = {"hit": False}
    backend.update_ready.connect(lambda: ready.__setitem__("hit", True))
    with qtbot.waitSignal(backend.update_available, timeout=6000):
        up.check(manual=True)
    up.start_download()
    qtbot.waitUntil(lambda: any(s.get("phase") == "error" for s in states), timeout=8000)
    assert ready["hit"] is False                       # never marked ready
    assert up._verified_path is None
    updates = up_mod._updates_dir()
    left = [n for n in os.listdir(updates) if n.endswith((".exe", ".partial"))]
    assert left == []                                  # partial/unverified deleted


def test_truncated_download_fails_verification(qtbot, feed, monkeypatch):
    feed.state["truncate"] = True
    backend, up = _make(qtbot, monkeypatch, installed=True)
    states = []
    backend.update_state.connect(lambda j: states.append(json.loads(j)))
    with qtbot.waitSignal(backend.update_available, timeout=6000):
        up.check(manual=True)
    up.start_download()
    qtbot.waitUntil(lambda: any(s.get("phase") == "error" for s in states), timeout=8000)
    assert up._verified_path is None
    updates = up_mod._updates_dir()
    assert [n for n in os.listdir(updates) if n.endswith((".exe", ".partial"))] == []


def test_active_job_blocks_install(qtbot, feed, monkeypatch, tmp_path):
    backend, up = _make(qtbot, monkeypatch, installed=True, processing=True)
    fake = tmp_path / SETUP_NAME
    fake.write_bytes(INSTALLER_BYTES)
    up._verified_path = str(fake)
    popen_calls = []
    monkeypatch.setattr(up_mod.subprocess, "Popen", lambda *a, **k: popen_calls.append(a))
    states = []
    backend.update_state.connect(lambda j: states.append(json.loads(j)))
    up.install_downloaded()
    assert any(s.get("phase") == "blocked" for s in states)
    assert popen_calls == []                            # installer never launched


def test_install_handoff_uses_visible_flags(qtbot, feed, monkeypatch, tmp_path):
    backend, up = _make(qtbot, monkeypatch, installed=True, processing=False)
    fake = tmp_path / SETUP_NAME
    fake.write_bytes(INSTALLER_BYTES)
    up._verified_path = str(fake)

    class _Stop(BaseException):
        pass  # BaseException so the updater's `except Exception` won't swallow it

    recorded = {}

    def fake_popen(args, *a, **k):
        recorded["args"] = args
        raise _Stop()                                   # stop before sys.exit

    monkeypatch.setattr(up_mod.subprocess, "Popen", fake_popen)
    with pytest.raises(_Stop):
        up.install_downloaded()
    assert recorded["args"][0].endswith(".exe")
    assert "/CLOSEAPPLICATIONS" in recorded["args"]
    assert "/NORESTART" in recorded["args"]
    assert "/VERYSILENT" not in recorded["args"] and "/SILENT" not in recorded["args"]


def test_portable_mode_does_not_self_replace(qtbot, feed, monkeypatch):
    # installed=False -> is_portable() stays True (source/portable run).
    backend, up = _make(qtbot, monkeypatch, installed=False)
    states = []
    backend.update_state.connect(lambda j: states.append(json.loads(j)))
    with qtbot.waitSignal(backend.update_available, timeout=6000):
        up.check(manual=True)
    up.start_download()
    qtbot.waitUntil(lambda: any(s.get("phase") == "portable" for s in states), timeout=4000)
    assert up._verified_path is None                    # nothing downloaded/installed
