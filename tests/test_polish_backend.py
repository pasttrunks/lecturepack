"""Focused regression coverage for the 2.0.1 backend/state polish pass."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.models.job import Job
from lecturepack.services import onboarding_state, reset_service
from lecturepack.services.job_queue import JobQueue


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"


def _sidecar_module():
    spec = importlib.util.spec_from_file_location("lecturepack_polish_sidecar", SIDECAR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_user_gets_current_tour_without_empty_library(tmp_path):
    config = ConfigManager(str(tmp_path))
    config.settings.update({
        "guided_tour_version": 1,
        "guided_tour_seen_version": 1,
        "guided_tour_status": "completed",
    })
    config.save()
    (tmp_path / "jobs" / "real-lecture").mkdir(parents=True)

    state = onboarding_state.ensure_guided_tour_state(config)

    assert state["current_version"] == onboarding_state.CURRENT_GUIDED_TOUR_VERSION
    assert state["seen_version"] == 1
    assert state["status"] == "not_seen"
    assert state["eligible"] is True

    skipped = onboarding_state.set_guided_tour_status(config, "skipped")
    assert skipped["status"] == "skipped"
    assert skipped["eligible"] is False
    replay = onboarding_state.set_guided_tour_status(config, "not_seen")
    assert replay["eligible"] is True


def test_reset_removes_owned_state_but_preserves_model_and_external_source(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    external = tmp_path / "Videos" / "Lecture 4.mp4"
    external.parent.mkdir()
    external.write_bytes(b"source lecture bytes")
    before = hashlib.sha256(external.read_bytes()).hexdigest()

    (data_root / "jobs" / "real-job").mkdir(parents=True)
    (data_root / "jobs" / "real-job" / "manifest.json").write_text(
        json.dumps({"source": {"original_path": str(external)}}), encoding="utf-8"
    )
    (data_root / "downloads" / "owned.mp4").parent.mkdir(parents=True)
    (data_root / "downloads" / "owned.mp4").write_bytes(b"owned")
    for filename in reset_service.OWNED_FILES:
        (data_root / filename).write_text("old state", encoding="utf-8")
    (data_root / "models").mkdir()
    (data_root / "models" / "ggml-base.en.bin").write_bytes(b"model")
    (data_root / "keep-me.txt").write_text("unknown data is not broad-deleted", encoding="utf-8")

    result = reset_service.reset_data_root(data_root)

    assert result["ok"] is True
    assert not (data_root / "jobs").exists()
    assert not (data_root / "downloads").exists()
    assert not (data_root / "config.json").exists()
    assert (data_root / "models" / "ggml-base.en.bin").read_bytes() == b"model"
    assert (data_root / "keep-me.txt").exists()
    assert hashlib.sha256(external.read_bytes()).hexdigest() == before


def test_demo_reconciliation_removes_marked_demo_only(tmp_path):
    module = _sidecar_module()
    data_root = tmp_path / "data"
    demo_id = "demo-job-1"
    real_id = "real-job-1"
    for job_id, marked in ((demo_id, True), (real_id, False)):
        job_root = data_root / "jobs" / job_id
        job_root.mkdir(parents=True)
        manifest = {"job_id": job_id, "title": "Polar Bears" if marked else "Real lecture"}
        if marked:
            manifest.update({"is_demo": True, "bundled_demo": True, "demo_session_id": "demo-session-1"})
        (job_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (data_root / "demo-inputs").mkdir(parents=True)
    (data_root / "demo-inputs" / "demo.mp4").write_bytes(b"demo")
    (data_root / "demo-session.json").write_text(
        json.dumps({"session_id": "demo-session-1", "job_id": demo_id}), encoding="utf-8"
    )

    class Backend:
        @staticmethod
        def delete_job(root, job_id):
            target = Path(root) / "jobs" / job_id
            if not target.is_dir():
                return {"ok": False, "error": "missing"}
            import shutil
            shutil.rmtree(target)
            return {"ok": True, "id": job_id}

    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._engine_error = ""
    sidecar.data_dir = data_root
    sidecar.electron_backend = Backend()
    sidecar.queue = JobQueue(str(data_root))
    sidecar._emit = lambda _payload: None
    sidecar._push_queue = lambda: None

    sidecar._reconcile_demo_session_on_startup()

    assert not (data_root / "jobs" / demo_id).exists()
    assert (data_root / "jobs" / real_id).exists()
    assert not (data_root / "demo-inputs").exists()
    assert not (data_root / "demo-session.json").exists()


def test_queue_existing_jobs_is_ordered_and_idempotent(tmp_path):
    module = _sidecar_module()
    ready_a = Job(str(tmp_path), video_path=str(tmp_path / "a.mp4"))
    ready_b = Job(str(tmp_path), video_path=str(tmp_path / "b.mp4"))
    completed = Job(str(tmp_path), video_path=str(tmp_path / "done.mp4"))
    completed.state["overall_status"] = "completed"
    completed.state["lifecycle"] = "completed"
    completed.save()
    queue = JobQueue(str(tmp_path))

    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.queue = queue
    sidecar.data_dir = tmp_path
    sidecar.electron_backend = SimpleNamespace(enqueue_job=lambda q, job_id: q.enqueue(job_id))
    sidecar._job_objects = lambda: [ready_a, ready_b, completed]
    sidecar._job_status = module.Sidecar._job_status.__get__(sidecar)
    sidecar._push_queue = lambda: None
    sidecar._emit_job_payloads = lambda: None
    sidecar._maybe_resume_queue = lambda: None
    responses = []
    sidecar._respond = lambda *_args, **kwargs: responses.append(kwargs)

    sidecar._queue_jobs(
        "req-1",
        "queue_jobs",
        {"job_ids": [ready_b.job_id, ready_a.job_id, ready_b.job_id, completed.job_id, "missing"]},
    )
    sidecar._queue_existing_jobs(
        "req-2", "queue_existing_jobs", {"job_ids": [ready_a.job_id, ready_b.job_id]}
    )

    assert queue.queued() == [ready_b.job_id, ready_a.job_id]
    assert responses[0]["queued"] == [ready_b.job_id, ready_a.job_id]
    assert {row["reason"] for row in responses[0]["skipped"]} >= {
        "duplicate_request", "done", "not_found"
    }
    assert responses[1]["queued"] == []
    assert {row["reason"] for row in responses[1]["skipped"]} == {"already_queued"}


def test_download_public_contract_has_stable_id_progress_and_normalized_state():
    module = _sidecar_module()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    public = sidecar._download_public({
        "id": "download-1",
        "url": "https://example.invalid/lecture",
        "title": "Marine mammals",
        "status": "downloading",
        "pct": 42,
        "eta": 18,
    })

    assert public["download_id"] == "download-1"
    assert public["status"] == "running"
    assert public["progress"] == 42
    assert public["eta_seconds"] == 18
    assert public["title"] == "Marine mammals"


def test_setup_acknowledgement_requires_current_passing_health():
    module = _sidecar_module()
    config = SimpleNamespace(
        setup_acknowledged=lambda: False,
        persist_setup_acknowledged=lambda: setattr(config, "persisted", True),
    )
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._last_health = {"startup_ok": False}
    sidecar.config = config
    responses = []
    sidecar._respond = lambda *_args, **kwargs: responses.append(kwargs)
    sidecar._acknowledge_setup("req-1", "acknowledge_setup")
    assert responses[-1]["ok"] is False
    assert not hasattr(config, "persisted")

    sidecar._last_health = {"startup_ok": True}
    sidecar._acknowledge_setup("req-2", "acknowledge_setup")
    assert responses[-1]["setup_acknowledged"] is True
    assert config.persisted is True


def test_bridge_keeps_demo_identity_and_bootstrap_state_on_real_boundary(tmp_path):
    if shutil.which("node") is None:
        return
    harness = tmp_path / "bridge-polish-contract.js"
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
      request(command, payload) {
        calls.push({ command, payload });
        if (command === 'import_video') return Promise.resolve({ ok: true, job_id: 'demo-job', demo_session_id: 'demo-session' });
        if (command === 'start_job') return Promise.resolve({ ok: true, job_id: 'demo-job', started: true });
        if (command === 'end_demo_job') return Promise.resolve({ ok: true, status: 'cleaned', job_id: 'demo-job', session_id: 'demo-session' });
        if (command === 'get_bootstrap') return Promise.resolve({ ok: true, guided_tour: { version: '2.0.1', eligible: true } });
        return Promise.resolve({ ok: true });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  await context.window.lpBridge.startDemoJob();
  await context.window.lpBridge.endDemoJob('tour_skip');
  const bootstrap = await context.window.lpBridge.call('get_bootstrap');
  if (calls[0].command !== 'import_video' || calls[0].payload.bundled_demo !== true) throw new Error('demo import mapping changed');
  if (calls[1].command !== 'start_job' || calls[1].payload.job_id !== 'demo-job') throw new Error('demo start lost explicit job identity');
  if (calls[2].command !== 'end_demo_job' || calls[2].payload.job_id !== 'demo-job' || calls[2].payload.reason !== 'tour_skip') throw new Error('demo end was not identity-safe');
  if (calls[3].command !== 'get_bootstrap' || !bootstrap.guided_tour) throw new Error('bootstrap state did not cross host');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("node"), str(harness), str(ROOT / "electron-spike" / "electron-bridge.js")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
