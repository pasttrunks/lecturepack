"""Focused tests for the import-queue-fix pass, commit 1: native import paths.

Covers the import guarantees: dropped File objects resolve through the preload
helper, Browse and drop share one native import function, a valid native path
reaches the sidecar unchanged (spaces/unicode preserved), the host blocks
drop navigation, and friendly structured import failure codes.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "electron-spike"
UI = ROOT / "app" / "ui"


# --------------------------------------------------------------------------- #
# Static: one shared native import path
# --------------------------------------------------------------------------- #
def test_browse_and_drop_converge_on_the_same_import_function():
    main = (SPIKE / "production-main.js").read_text(encoding="utf-8")
    ui = (UI / "app.js").read_text(encoding="utf-8")
    # The native dialog and the drop interceptor both call importLocalVideo.
    assert "return importLocalVideo(session, result.filePaths[0]);" in main
    assert "return importLocalVideo(session, payload.path, payload);" in main
    # The renderer drop path resolves the File through the preload helper and
    # sends the same import_video command the dialog path uses.
    assert "lpBridge.call('import_video', { path: path })" in ui
    assert "var path = lpBridge.pathForFile ? lpBridge.pathForFile(file) : '';" in ui


def test_browse_dialog_allows_unfamiliar_containers():
    main = (SPIKE / "production-main.js").read_text(encoding="utf-8")
    assert "{ name: 'All files', extensions: ['*'] }" in main


def test_host_blocks_drop_navigation():
    main = (SPIKE / "production-main.js").read_text(encoding="utf-8")
    assert "will-navigate" in main
    assert "event.preventDefault();" in main


# --------------------------------------------------------------------------- #
# Native-path validation (shared by Browse and drop)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_validate_local_video_path_returns_native_path_unchanged(tmp_path):
    video = tmp_path / "my lecture (ü) - 01.mp4"
    video.write_bytes(b"fake-video-bytes")
    harness = tmp_path / "validate-path.js"
    harness.write_text(
        r"""
const assert = require('node:assert');
const { validateLocalVideoPath } = require(process.argv[2]);

const video = process.argv[3];
const ok = validateLocalVideoPath(video);
assert.strictEqual(ok.ok, true, JSON.stringify(ok));
// The absolute native path passes through unchanged (spaces, unicode, dashes).
assert.strictEqual(ok.path, video);

const missing = validateLocalVideoPath(require('node:path').join(video, '..', 'gone.mp4'));
assert.strictEqual(missing.ok, false);
assert.strictEqual(missing.code, 'NOT_FOUND');

const empty = validateLocalVideoPath('');
assert.strictEqual(empty.ok, false);
assert.strictEqual(empty.code, 'RESOLVE_FAILED');

const directory = validateLocalVideoPath(process.argv[4]);
assert.strictEqual(directory.ok, false);
assert.strictEqual(directory.code, 'NOT_FOUND');
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            shutil.which("node"),
            str(harness),
            str(SPIKE / "import-path.js"),
            str(video),
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------- #
# Dropped File -> preload webUtils helper
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_dropped_file_resolves_through_preload_helper(tmp_path):
    harness = tmp_path / "drop-path.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert');
const source = fs.readFileSync(process.argv[2], 'utf8');

const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request() { return Promise.resolve({}); },
      onMessage() {},
      getPathForFile(file) { return 'C:\\Users\\demo\\Lecture One (F22).mp4'; }
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });

// The dropped File object resolves through webUtils.getPathForFile, never via
// a renderer-owned filesystem API or a file:// URL.
const path = context.window.lpBridge.pathForFile({ name: 'Lecture One (F22).mp4', path: undefined });
assert.strictEqual(path, 'C:\\Users\\demo\\Lecture One (F22).mp4');

// Fallback without the preload helper: older File objects that still carry
// `path` keep working (browser preview / older adapters).
const legacy = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request() { return Promise.resolve({}); },
      onMessage() {}
    }
  }
};
vm.createContext(legacy);
vm.runInContext(source, legacy, { filename: 'electron-bridge-legacy.js' });
const fallback = legacy.window.lpBridge.pathForFile({ name: 'a.mkv', path: 'C:\\old\\a.mkv' });
assert.strictEqual(fallback, 'C:\\old\\a.mkv');
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("node"), str(harness), str(SPIKE / "electron-bridge.js")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
