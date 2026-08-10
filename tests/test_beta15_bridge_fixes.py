"""Focused regression tests for the Beta 15 bridge no-op repairs (D-2, D-6, D-7, D-9, D-10, D-15).

These tests prove the audited visible controls no longer silently return null:
- D-2  start_demo_job uses the normal import_video path with the bundled demo
- D-6  check_updates resolves immediately with a structured result
- D-7  validate_vulkan / validate_cuda resolve through the sidecar
- D-9  CUDA capability is reported honestly (GPU vs supported vs installable)
- D-10 test_endpoint produces visible-result data
- D-15 test_notification routes to an Electron-side event, never Python
- Visible no-op commands return a structured FEATURE_UNAVAILABLE response
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "electron-spike"
BRIDGE = SPIKE / "electron-bridge.js"
SIDECAR = SPIKE / "python-sidecar.py"
DEMO = SPIKE / "assets" / "demo-lecture.mp4"


def _run_node_harness(tmp_path: Path, name: str, script: str) -> subprocess.CompletedProcess:
    harness = tmp_path / name
    harness.write_text(script.strip() + "\n", encoding="utf-8")
    return subprocess.run(
        [shutil.which("node"), str(harness), str(BRIDGE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_d2_demo_uses_normal_import_path(tmp_path):
    """D-2: start_demo_job maps to import_video with bundled_demo, not a fake pipeline."""
    result = _run_node_harness(tmp_path, "d2-demo-import.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const events = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) {
        calls.push({ command, payload });
        if (command === 'import_video') return Promise.resolve({ ok: true, job_id: 'demo-1' });
        if (command === 'start_job') return Promise.resolve({ ok: true, job_id: 'demo-1', started: true });
        return Promise.resolve({});
      },
      onMessage(callback) { context._message = callback; }
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
context.window.lpBridge.on('demo_event', (json) => events.push(JSON.parse(json)));
(async () => {
  const value = await context.window.lpBridge.startDemoJob();
  if (calls.length !== 2) throw new Error(`expected 2 calls, got ${calls.length}`);
  if (calls[0].command !== 'import_video') throw new Error(`demo did not use import_video: ${calls[0].command}`);
  if (calls[0].payload.bundled_demo !== true) throw new Error(`demo did not set bundled_demo: ${JSON.stringify(calls[0].payload)}`);
  if (calls[1].command !== 'start_job') throw new Error(`demo did not start processing: ${calls[1].command}`);
  if (!value || value.ok !== true) throw new Error(`demo result was not structured: ${JSON.stringify(value)}`);
  if (!value.operation_id || !value.session_id) throw new Error(`demo result missing operation_id/session_id: ${JSON.stringify(value)}`);
  if (events.length !== 1 || events[0].status !== 'started' || !events[0].operation_id || !events[0].session_id) {
    throw new Error(`demo_event was not emitted: ${JSON.stringify(events)}`);
  }
  // The normal pipeline lifecycle must translate into demo_event signals so
  // the guided tour can advance to review_ready and exports.
  context._message({ event: 'pipeline_changed', stages: [
    { label: 'Inspect', state: 'done' },
    { label: 'Review Ready', state: 'done' }
  ] });
  context._message({ event: 'job_completed', job_id: 'demo-1' });
  const review = events.find((e) => e.stage === 'review_ready');
  const done = events.find((e) => e.stage === 'exports');
  if (!review || review.status !== 'running' || !review.operation_id || !review.session_id) {
    throw new Error(`review_ready demo_event was not emitted: ${JSON.stringify(events)}`);
  }
  if (!done || done.status !== 'cleaned') {
    throw new Error(`exports demo_event was not emitted: ${JSON.stringify(events)}`);
  }
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_d2_demo_start_processing_failure_propagates(tmp_path):
    """D-2: a start_processing failure must not return a false {ok: true}."""
    result = _run_node_harness(tmp_path, "d2-demo-failure.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) {
        if (command === 'import_video') return Promise.resolve({ ok: true, job_id: 'demo-1' });
        if (command === 'start_job') return Promise.resolve({ ok: false, error: 'engine not loaded' });
        return Promise.resolve({});
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  const value = await context.window.lpBridge.startDemoJob();
  if (!value || value.ok !== false) throw new Error(`start_processing failure was masked: ${JSON.stringify(value)}`);
  if (!value.error) throw new Error(`start_processing failure had no error: ${JSON.stringify(value)}`);
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_d6_update_check_routes_to_main_process(tmp_path):
    """D-6/Phase 6: check_updates routes to the Electron main updater, never
    resolves to a null or hangs. The main process owns the stable GitHub feed;
    the bridge must forward the call (one request) and return its result."""
    result = _run_node_harness(tmp_path, "d6-updates.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
let requests = 0;
const events = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request() { requests += 1; return Promise.resolve({ ok: true, status: 'uptodate' }); },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
context.window.lpBridge.on('update_state', (json) => events.push(JSON.parse(json)));
(async () => {
  const value = await context.window.lpBridge.call('check_updates');
  if (value === null || value === undefined) throw new Error('check_updates returned null');
  if (requests !== 1) throw new Error(`check_updates did not forward to the main process (${requests} requests)`);
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_d7_compute_check_resolves_through_sidecar(tmp_path):
    """D-7: validate_vulkan / validate_cuda are forwarded to the sidecar and resolve."""
    result = _run_node_harness(tmp_path, "d7-compute.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) {
        calls.push({ command, payload });
        return Promise.resolve({ ok: true, state: 'unavailable', available: false, message: 'CPU only' });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  const vulkan = await context.window.lpBridge.call('validate_vulkan');
  const cuda = await context.window.lpBridge.call('validate_cuda');
  if (calls.length !== 2) throw new Error(`expected 2 calls, got ${calls.length}`);
  if (calls[0].command !== 'validate_vulkan' || calls[1].command !== 'validate_cuda') {
    throw new Error(`compute commands were not forwarded: ${JSON.stringify(calls)}`);
  }
  if (vulkan === null || cuda === null) throw new Error('compute check returned null');
  if (vulkan.ok !== true || cuda.ok !== true) throw new Error('compute check did not resolve ok');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_d9_cuda_install_not_advertised_incorrectly(tmp_path):
    """D-9: cuda_pack_status reports GPU/supported/installable separately and honestly."""
    result = _run_node_harness(tmp_path, "d9-cuda.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) {
        calls.push({ command, payload });
        if (command === 'cuda_pack_status') {
          return Promise.resolve({ ok: true, state: 'idle', gpu_present: true, installed: false, size_label: '~2.1 GB' });
        }
        return Promise.resolve({ ok: true });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  const status = await context.window.lpBridge.call('cuda_pack_status');
  if (status === null) throw new Error('cuda_pack_status returned null');
  if (status.gpu_present !== true) throw new Error('NVIDIA GPU detection was not reported');
  if (status.installed !== false) throw new Error('CUDA install was advertised incorrectly');
  if (calls[0].command !== 'cuda_pack_status') throw new Error('cuda_pack_status was not forwarded');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_d10_endpoint_test_produces_visible_result(tmp_path):
    """D-10: test_endpoint is forwarded and produces visible-result data."""
    result = _run_node_harness(tmp_path, "d10-endpoint.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) {
        calls.push({ command, payload });
        return Promise.resolve({ ok: true, available: false, label: 'Built-in Study', model: '' });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  const value = await context.window.lpBridge.call('test_endpoint');
  if (value === null) throw new Error('test_endpoint returned null');
  if (value.ok !== true || value.available !== false || value.label !== 'Built-in Study') {
    throw new Error(`test_endpoint did not produce visible-result data: ${JSON.stringify(value)}`);
  }
  if (calls[0].command !== 'test_endpoint') throw new Error('test_endpoint was not forwarded');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_d15_notification_routes_to_electron(tmp_path):
    """D-15: test_notification routes to the Electron main process, never Python."""
    result = _run_node_harness(tmp_path, "d15-notification.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) {
        calls.push({ command, payload });
        return Promise.resolve({ ok: true, sent: true });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  const value = await context.window.lpBridge.call('test_notification');
  if (value === null) throw new Error('test_notification returned null');
  if (value.ok !== true || value.sent !== true) throw new Error(`test_notification did not resolve: ${JSON.stringify(value)}`);
  // The request must reach the Electron main process (Luna's
  // testDesktopNotification), not the Python sidecar.
  if (calls.length !== 1 || calls[0].command !== 'test_notification') {
    throw new Error(`test_notification did not route to Electron main: ${JSON.stringify(calls)}`);
  }
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_study_ask_object_payload_preserves_prompt(tmp_path):
    """Study Ask maps its object payload to the actual prompt string."""
    result = _run_node_harness(tmp_path, "study-ask-payload.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) {
        calls.push({ command, payload });
        return Promise.resolve({ ok: true });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  await context.window.lpBridge.call('ask_ai', { prompt: 'Explain this lecture simply' });
  if (calls.length !== 1 || calls[0].command !== 'ask_ai') {
    throw new Error(`ask_ai was not forwarded: ${JSON.stringify(calls)}`);
  }
  if (calls[0].payload.prompt !== 'Explain this lecture simply') {
    throw new Error(`ask_ai prompt was mangled: ${JSON.stringify(calls[0].payload)}`);
  }
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_visible_noop_commands_do_not_return_null(tmp_path):
    """Visible no-op commands return a structured FEATURE_UNAVAILABLE response, never null."""
    result = _run_node_harness(tmp_path, "visible-noops.js", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request() { return Promise.resolve({}); },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  const commands = [
    'save_project', 'browse_model', 'open_release_page', 'exit_application',
    'install_update', 'set_auto_check',
    'clear_skipped_version',
    'acknowledge_setup', 'get_post_completion', 'whatsnew_seen', 'log_tour_trace'
  ];
  for (const name of commands) {
    const value = await context.window.lpBridge.call(name);
    if (value === null || value === undefined) throw new Error(`${name} returned null`);
    if (value.ok !== false || value.available !== false || value.code !== 'FEATURE_UNAVAILABLE') {
      throw new Error(`${name} was not a structured unavailable result: ${JSON.stringify(value)}`);
    }
  }
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""")
    assert result.returncode == 0, result.stderr


def test_sidecar_resolves_bundled_demo_video():
    """D-2: the sidecar resolves the bundled demo video for the normal import path."""
    spec = importlib.util.spec_from_file_location("lecturepack_electron_sidecar_demo", SIDECAR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.demo_video = None
    sidecar.runtime_root = SPIKE
    sidecar.repo_root = ROOT

    resolved = sidecar._resolve_demo_video()
    assert resolved is not None
    assert resolved.is_file()
    assert resolved.name == "demo-lecture.mp4"


def test_sidecar_demo_import_uses_normal_path():
    """D-2: bundled_demo import resolves the demo and copies it, not a fake pipeline."""
    spec = importlib.util.spec_from_file_location("lecturepack_electron_sidecar_demo2", SIDECAR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.demo_video = None
    sidecar.runtime_root = SPIKE
    sidecar.repo_root = ROOT
    sidecar.data_dir = ROOT / "tests" / "scratch" / "beta15-demo-data"

    source = sidecar._resolve_demo_video()
    assert source is not None
    copied = sidecar._copy_demo_if_needed(source)
    assert copied.is_file()
    assert "demo-inputs" in str(copied)
