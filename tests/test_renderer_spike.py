from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import queue
import shutil
import subprocess
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "electron-spike"


def test_production_package_has_release_identity_and_isolated_dependencies():
    package = json.loads((SPIKE / "package.json").read_text(encoding="utf-8"))
    assert package["private"] is True
    assert package["name"] == "lecturepack"
    assert package["main"] == "production-main.js"
    assert package["productName"] == "LecturePack"
    assert package["version"] == "0.9.0-beta.15"
    assert {"start", "validate", "package:sidecar", "package:win"}.issubset(package["scripts"])
    assert "electron" in package["devDependencies"]
    assert "PySide6" not in json.dumps(package)


def test_production_host_is_single_real_app_entry_point():
    source = (SPIKE / "production-main.js").read_text(encoding="utf-8")
    preload = (SPIKE / "production-preload.js").read_text(encoding="utf-8")
    package_script = (SPIKE / "package-win.mjs").read_text(encoding="utf-8")
    assert "lecturepack-production:command" in source
    assert "lecturepack-production:message" in preload
    assert "production-preload.js" in source
    assert "function browseVideo" in source
    assert "function restoreJob" in source
    assert "taskkill.exe" in source
    assert "shell: false" in source
    assert "MODES" not in source
    assert "startMigrationSidecar" not in source
    assert "name: 'LecturePack'" in package_script
    assert "demoVideo" not in package_script
    assert "^main\\.js$" in package_script


def test_production_ui_keeps_real_sections_and_hardens_bridge_payloads():
    host = (SPIKE / "production-main.js").read_text(encoding="utf-8")
    preload = (SPIKE / "production-preload.js").read_text(encoding="utf-8")
    adapter = (SPIKE / "electron-bridge.js").read_text(encoding="utf-8")
    ui = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
    assert "data-nav=\"study\"" not in host
    assert "data-nav=\"settings\"" not in host
    assert "path.join(app.getPath('home'), 'LecturePackData')" in host
    assert "app.requestSingleInstanceLock()" in host
    assert "getPathForFile(file)" in preload
    assert "pathForFile" in adapter
    assert "importDroppedVideo" in ui
    assert "function parseBridgePayload" in ui
    assert "localStorage.getItem('lecturepack.electron.theme')" in ui


def test_diagnostic_modes_and_migration_mode_are_declared():
    source = (SPIKE / "main.js").read_text(encoding="utf-8")
    launcher = (SPIKE / "launcher.html").read_text(encoding="utf-8")
    for mode in ("static", "mock", "python", "migration"):
        assert mode in source
        assert f'data-mode="{mode}"' in launcher


def test_static_theme_has_no_workload_or_backend_hooks():
    source = (SPIKE / "static-theme.js").read_text(encoding="utf-8")
    assert "lpBridge" not in source
    assert "setTimeout" not in source
    assert "setInterval" not in source
    assert "requestAnimationFrame" not in source
    assert "addEventListener('click'" in source


def test_static_mode_uses_a_local_file_document_for_existing_assets():
    source = (SPIKE / "main.js").read_text(encoding="utf-8")
    assert "function writeStaticDocument(uiDir)" in source
    assert "window.loadFile(staticFile.file)" in source
    assert "data:text/html" not in source


def test_external_process_boundary_uses_argument_array():
    source = (SPIKE / "main.js").read_text(encoding="utf-8")
    assert "spawn(python, [script, '--repo-root', REPO_ROOT]" in source
    assert "process.resourcesPath, 'python-sidecar.py'" in source
    package_script = (SPIKE / "package-win.mjs").read_text(encoding="utf-8")
    assert "const engine = path.join(repoRoot, 'lecturepack')" in package_script
    assert "shell: false" in source
    assert "shell=True" not in source


def test_mock_workload_covers_required_signal_load():
    source = (SPIKE / "mock-workload.js").read_text(encoding="utf-8")
    for signal in (
        "bootstrap_progress",
        "bootstrap_complete",
        "demo_event",
        "pipeline_changed",
        "log_line",
        "slides_changed",
        "transcript_changed",
    ):
        assert f"emit('{signal}'" in source
    assert "logIndex >= 500" in source
    assert "setInterval" in source


def test_python_sidecar_imports_existing_engine_without_network_or_shell():
    source = (SPIKE / "python-sidecar.py").read_text(encoding="utf-8")
    assert "lecturepack.controllers.job_controller" in source
    assert "subprocess" not in source
    assert "shell=True" not in source
    assert "QCoreApplication" in source
    for command in (
        "health_check", "list_jobs", "import_video", "start_job", "cancel_job",
        "get_job", "get_slides", "get_transcript", "set_slide_state",
        "save_corrections", "export", "set_setting", "shutdown",
    ):
        assert f'command == "{command}"' in source
    for event in (
        "ready", "bootstrap_progress", "bootstrap_complete", "jobs_changed",
        "pipeline_changed", "status_changed", "log_line", "slides_changed",
        "transcript_changed", "export_progress", "error",
    ):
        assert f'"event": "{event}"' in source
    assert "request_id" in source


def test_migration_bridge_maps_existing_ui_without_requiring_qt_webchannel():
    bridge = (SPIKE / "electron-bridge.js").read_text(encoding="utf-8")
    for command in (
        "health_check", "list_jobs", "import_video", "start_job", "cancel_job",
        "get_job", "get_slides", "get_transcript", "set_slide_state",
        "save_corrections", "export", "set_setting", "shutdown",
    ):
        assert command in bridge
    assert "lecturePackElectron" in bridge
    assert "__LECTUREPACK_ELECTRON__" in bridge
    assert "qwebchannel" not in bridge.lower()
    assert "event === 'jobs_changed'" in bridge
    assert "isLocalThemeSetting" in bridge
    for deferred in (
        "exit_application", "list_ollama_models", "run_diagnostics",
        "set_notification_prefs", "start_demo_job", "validate_vulkan",
    ):
        assert f"{deferred}: true" in bridge


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_migration_bridge_delivers_jobs_array_and_keeps_theme_local(tmp_path):
    harness = tmp_path / "bridge-contract-check.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(process.argv[2], 'utf8');
let requests = 0;
let apiMessage = null;
const received = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request() { requests += 1; return Promise.resolve({}); },
      onMessage(callback) { apiMessage = callback; }
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
context.window.lpBridge.on('jobs_changed', (json) => received.push(JSON.parse(json)));

const jobs = [{ id: 'job-1', status: 'running' }];
apiMessage({ event: 'jobs_changed', jobs });
context.window.__LECTUREPACK_ELECTRON__.onSidecar({ event: 'jobs_changed', jobs });

(async () => {
  const result = await context.window.lpBridge.call('set_setting', 'theme', 'dark');
  if (requests !== 0) throw new Error(`theme made ${requests} sidecar requests`);
  if (received.length !== 2) throw new Error(`received ${received.length} jobs events`);
  for (const value of received) {
    if (!Array.isArray(value) || value.length !== 1 || value[0].id !== 'job-1') {
      throw new Error(`jobs_changed was not an array: ${JSON.stringify(value)}`);
    }
  }
  if (!result || result.local !== true) throw new Error('theme was not handled locally');
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_production_bridge_maps_mode_preset_import_and_folder_calls(tmp_path):
    harness = tmp_path / "bridge-production-check.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) { calls.push({ command, payload }); return Promise.resolve({}); },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  await context.window.lpBridge.call('set_setting', 'slide_detection_preset', 'detailed');
  await context.window.lpBridge.call('start_processing', 'slides');
  await context.window.lpBridge.call('browse_video');
  await context.window.lpBridge.call('open_export_folder');
  if (calls[0].command !== 'set_setting' || calls[0].payload.value !== 'detailed') throw new Error('preset was not forwarded');
  if (calls[1].command !== 'start_job' || calls[1].payload.mode !== 'slides' || calls[1].payload.preset !== 'detailed') throw new Error('processing options were not forwarded');
  if (calls[2].command !== 'browse_video') throw new Error('browse_video stayed a no-op');
  if (calls[3].command !== 'open_export_folder') throw new Error('folder command was not forwarded');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_production_bridge_maps_phase9_jobs_and_url_calls(tmp_path):
    harness = tmp_path / "bridge-phase9-check.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) { calls.push({ command, payload }); return Promise.resolve({}); },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  await context.window.lpBridge.call('delete_job', 'job-1');
  await context.window.lpBridge.call('delete_jobs', JSON.stringify(['job-1', 'job-2']));
  await context.window.lpBridge.call('enqueue_job', 'job-1');
  await context.window.lpBridge.call('reorder_queue', 'job-1', 2);
  await context.window.lpBridge.call('run_now', 'job-1');
  await context.window.lpBridge.call('remove_from_queue', 'job-1');
  await context.window.lpBridge.call('schedule_job', 'job-1', '2026-08-03T12:00', 'local', 'ask');
  await context.window.lpBridge.call('unschedule_job', 'job-1');
  await context.window.lpBridge.call('pause_job');
  await context.window.lpBridge.call('resume_job', 'job-1');
  await context.window.lpBridge.call('restart_job', 'job-1');
  await context.window.lpBridge.call('retry_stage', 'job-1', 'Transcribe');
  await context.window.lpBridge.call('set_job_group', 'job-1', 'Physics');
  await context.window.lpBridge.call('set_jobs_group', JSON.stringify(['job-1', 'job-2']), 'Physics');
  await context.window.lpBridge.call('rename_job', 'job-1', 'Lecture 1');
  await context.window.lpBridge.call('media_link_support');
  await context.window.lpBridge.call('probe_media_url', 'https://example.test/lecture');
  await context.window.lpBridge.call('import_media_url', 'https://example.test/lecture', 'Lecture 1');
  await context.window.lpBridge.call('cancel_media_url');
  const expected = [
    ['delete_job', { job_id: 'job-1' }],
    ['delete_jobs', { ids: ['job-1', 'job-2'] }],
    ['enqueue_job', { job_id: 'job-1' }],
    ['reorder_queue', { job_id: 'job-1', index: 2 }],
    ['run_now', { job_id: 'job-1' }],
    ['remove_from_queue', { job_id: 'job-1' }],
    ['schedule_job', { job_id: 'job-1', when: '2026-08-03T12:00', tz: 'local', missed_policy: 'ask' }],
    ['unschedule_job', { job_id: 'job-1' }],
    ['pause_job', {}],
    ['resume_job', { job_id: 'job-1' }],
    ['restart_job', { job_id: 'job-1' }],
    ['retry_stage', { job_id: 'job-1', stage: 'Transcribe' }],
    ['set_job_group', { job_id: 'job-1', group: 'Physics' }],
    ['set_jobs_group', { ids: ['job-1', 'job-2'], group: 'Physics' }],
    ['rename_job', { job_id: 'job-1', title: 'Lecture 1' }],
    ['media_link_support', {}],
    ['probe_media_url', { url: 'https://example.test/lecture' }],
    ['import_media_url', { url: 'https://example.test/lecture', title: 'Lecture 1' }],
    ['cancel_media_url', {}]
  ];
  if (calls.length !== expected.length) throw new Error(`expected ${expected.length} calls, got ${calls.length}`);
  expected.forEach(([command, payload], index) => {
    if (calls[index].command !== command || JSON.stringify(calls[index].payload) !== JSON.stringify(payload)) {
      throw new Error(`call ${index} mismatch: ${JSON.stringify(calls[index])}`);
    }
  });
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_production_bridge_maps_review_commands(tmp_path):
    harness = tmp_path / "bridge-review-check.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command, payload) { calls.push({ command, payload }); return Promise.resolve({}); },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  await context.window.lpBridge.call('set_slide_state', 2, 'rejected');
  await context.window.lpBridge.call('save_corrections', JSON.stringify(['edited one', 'edited two']));
  await context.window.lpBridge.call('export_all', JSON.stringify(['pdf', 'html']));
  await context.window.lpBridge.call('export_one', 'pdf');
  if (calls[0].command !== 'set_slide_state' || calls[0].payload.index !== 2 || calls[0].payload.state !== 'rejected') {
    throw new Error('slide review command was not mapped');
  }
  if (Object.prototype.hasOwnProperty.call(calls[0].payload, 'job_id')) {
    throw new Error('slide review command leaked an inferred job_id');
  }
  if (calls[1].command !== 'save_corrections' || calls[1].payload.texts.length !== 2 || calls[1].payload.texts[0] !== 'edited one') {
    throw new Error('transcript correction command was not mapped');
  }
  if (Object.prototype.hasOwnProperty.call(calls[1].payload, 'job_id')) {
    throw new Error('transcript correction command leaked an inferred job_id');
  }
  for (const call of calls.slice(2)) {
    if (call.command !== 'export' || Object.keys(call.payload).length !== 0) {
      throw new Error(`export mapping was not contract-shaped: ${JSON.stringify(call)}`);
    }
  }
  await context.window.lpBridge.call('start_demo_job');
  await context.window.lpBridge.call('list_ollama_models');
  await context.window.lpBridge.call('media_link_support');
  await context.window.lpBridge.call('get_settings');
  await context.window.lpBridge.call('exit_application');
  if (calls.length !== 6) throw new Error('a deferred command crossed the sidecar boundary');
  if (calls[5].command !== 'get_settings' || Object.keys(calls[5].payload).length !== 0) {
    throw new Error(`get_settings was not forwarded: ${JSON.stringify(calls[5])}`);
  }
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
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


def test_sidecar_summary_keeps_active_job_running_until_export_done():
    module_path = SPIKE / "python-sidecar.py"
    spec = importlib.util.spec_from_file_location("lecturepack_electron_sidecar", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FakeJob:
        job_id = "job-1"
        manifest = {"title": "Demo", "source": {"filename": "demo.mp4"}}
        source = {"duration": 24.0}
        state = {"lifecycle": "completed", "overall_status": "completed", "last_updated": ""}

        def __init__(self):
            self.export_done = False

        def get_stage_status(self, stage):
            return "completed" if stage == "Export" and self.export_done else "pending"

    job = FakeJob()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.current_job = job
    sidecar.current_stage = "Transcribe"
    sidecar.stage_percent = {}

    listed_job = FakeJob()
    assert sidecar._summary(listed_job)["status"] == "running"
    listed_job.state["lifecycle"] = "interrupted"
    listed_job.state["overall_status"] = "interrupted"
    assert sidecar._summary(listed_job)["status"] == "running"
    listed_job.state["lifecycle"] = "completed"
    listed_job.state["overall_status"] = "completed"
    listed_job.export_done = True
    assert sidecar._summary(listed_job)["status"] == "done"


def test_migration_transport_text_has_no_replacement_or_mojibake_markers():
    for file_name in ("electron-bridge.js", "main.js", "python-sidecar.py"):
        source = (SPIKE / file_name).read_text(encoding="utf-8")
        assert "\ufffd" not in source
        assert "Â" not in source
        assert "â" not in source
    assert "ensure_ascii=True" in (SPIKE / "python-sidecar.py").read_text(encoding="utf-8")


def test_sidecar_spec_is_cpu_only_and_headless():
    spec = (SPIKE / "sidecar.spec").read_text(encoding="utf-8").lower()
    assert "console=true" in spec
    assert "ffmpeg.exe" in spec
    assert "ffprobe.exe" in spec
    assert "whisper-cli.exe" in spec
    assert "ggml-base.en.bin" in spec
    assert "collect_submodules(\"yt_dlp\")" in spec
    assert '"send2trash"' in spec
    assert "bin/vulkan" not in spec
    assert "bin/cuda" not in spec
    assert "qtwidgets" not in (SPIKE / "python-sidecar.py").read_text(encoding="utf-8").lower()
    assert "qtwebengine" not in (SPIKE / "python-sidecar.py").read_text(encoding="utf-8").lower()


@pytest.mark.skipif(
    not (ROOT / ".venv" / "Scripts" / "python.exe").is_file(),
    reason="locked project Python is not available",
)
def test_source_sidecar_jsonl_health_list_and_shutdown(tmp_path):
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    sidecar = SPIKE / "python-sidecar.py"
    data_dir = tmp_path / "data"
    demo = SPIKE / "assets" / "demo-lecture.mp4"
    process = subprocess.Popen(
        [
            str(python), "-u", str(sidecar),
            "--repo-root", str(ROOT),
            "--resources-root", str(ROOT),
            "--data-dir", str(data_dir),
            "--demo-video", str(demo),
        ],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    messages = queue.Queue()

    def read_stdout():
        for line in process.stdout:
            messages.put(line)

    threading.Thread(target=read_stdout, daemon=True).start()

    def next_message(timeout=30):
        return json.loads(messages.get(timeout=timeout))

    def send(request_id, command):
        process.stdin.write(json.dumps({
            "request_id": request_id,
            "command": command,
            "payload": {},
        }) + "\n")
        process.stdin.flush()

    try:
        ready = None
        while ready is None:
            candidate = next_message()
            if candidate.get("event") == "ready":
                ready = candidate
        assert ready["engine_loaded"] is True

        send("health", "health_check")
        while True:
            health = next_message()
            if health.get("response_to") == "health":
                assert health["ok"] is True
                assert health["healthy"] is True
                break

        send("jobs", "list_jobs")
        while True:
            listed = next_message()
            if listed.get("response_to") == "jobs":
                assert listed["ok"] is True
                assert listed["jobs"] == []
                break

        send("shutdown", "shutdown")
        while True:
            stopped = next_message()
            if stopped.get("response_to") == "shutdown":
                break
        process.wait(timeout=15)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_node_sources_parse():
    for file_name in (
        "main.js", "preload.js", "electron-bridge.js", "mock-workload.js",
        "python-mode.js", "static-theme.js", "production-main.js",
        "production-preload.js", "package-sidecar.mjs", "package-win.mjs",
    ):
        result = subprocess.run(
            [shutil.which("node"), "--check", str(SPIKE / file_name)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
