"""Focused regression coverage for the 2.0.1 backend/state polish pass."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import threading
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


def test_cancelled_study_worker_cannot_recreate_deleted_demo_job(tmp_path):
    """A late provider response must not resurrect a cleaned demo folder."""
    from lecturepack.services import ai_gateway, ai_study_service, study_v2

    module = _sidecar_module()
    data_root = tmp_path / "data"
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"demo")
    job = Job(str(data_root), video_path=str(source))
    job.manifest.update({
        "is_demo": True,
        "bundled_demo": True,
        "demo_session_id": "demo-cancel-race",
    })
    job.save()

    entered = threading.Event()
    release = threading.Event()

    def late_prepare(target_job, _client, *, progress=None, cancelled=None):
        entered.set()
        assert release.wait(5)
        # Deliberately emulate a misbehaving/late persistence boundary. The
        # sidecar's final race guard must still remove this manifest-less root.
        content = study_v2.empty_content()
        content["study_status"] = study_v2.STUDY_READY
        study_v2.save_content(target_job, content)
        return content

    deleted = []

    def delete_job(root, job_id):
        target = Path(root) / "jobs" / job_id
        if not target.is_dir():
            return {"ok": False, "id": job_id, "error": "missing"}
        deleted.append({
            "job_id": job_id,
            "had_manifest": (target / "manifest.json").is_file(),
        })
        shutil.rmtree(target)
        return {"ok": True, "id": job_id}

    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._shutting_down = False
    sidecar.data_dir = data_root
    sidecar.study_v2 = study_v2
    sidecar.ai_gateway = ai_gateway
    sidecar.ai_study_service = SimpleNamespace(
        StudyContentError=ai_study_service.StudyContentError,
        prepare_ai_study=late_prepare,
    )
    sidecar.electron_backend = SimpleNamespace(delete_job=delete_job)
    sidecar._study_workers_lock = threading.Lock()
    sidecar._study_workers = {}
    sidecar._ai_interaction_workers = {}
    sidecar._ai_interaction_jobs = {}
    sidecar._study_job_epochs = {}
    sidecar._pending_study_refresh = {}
    sidecar._study_basic_opt_out = set()
    sidecar._ai_gateway_client = object()
    sidecar._emit = lambda _payload: None

    assert sidecar._start_ai_study(job) is True
    assert entered.wait(5)
    worker = sidecar._study_workers[job.job_id]
    sidecar._cancel_study_jobs([job.job_id])
    shutil.rmtree(job.paths["root"])
    release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert not Path(job.paths["root"]).exists()
    assert deleted == [{"job_id": job.job_id, "had_manifest": False}]


def test_chained_partial_refresh_rejects_a_cancelled_epoch(tmp_path):
    """A queued follow-up may not adopt the post-delete epoch as new work."""
    module = _sidecar_module()
    job_id = "study-epoch-job"
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._shutting_down = False
    sidecar._study_workers_lock = threading.Lock()
    sidecar._study_workers = {}
    sidecar._study_job_epochs = {job_id: 2}
    sidecar._pending_study_refresh = {}

    started = sidecar._start_partial_study_refresh(
        SimpleNamespace(job_id=job_id),
        ["segment-1"],
        expected_epoch=1,
    )

    assert started is False
    assert sidecar._study_workers == {}
    assert sidecar._pending_study_refresh == {}


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


def test_sidecar_health_response_exposes_canonical_first_run_checklist():
    module = _sidecar_module()
    checklist = [
        {"id": "windows_version", "verdict": "ready", "detail": "ok"},
        {"id": "ffmpeg_ffprobe", "verdict": "ready", "detail": "ok"},
        {"id": "whisper_runtime", "verdict": "ready", "detail": "ok"},
        {"id": "bundled_model", "verdict": "ready", "detail": "ok"},
        {"id": "data_directory", "verdict": "ready", "detail": "ok"},
    ]
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._engine_error = ""
    sidecar._packaged_self_test = lambda include_sidecar=False: {
        "passed": True,
        "startup_ok": True,
        "checks": [
            {"id": "ffmpeg", "ok": True, "detail": "ok", "fatal_at_startup": True},
            {"id": "ffprobe", "ok": True, "detail": "ok", "fatal_at_startup": True},
        ],
        "checklist": checklist,
    }
    sidecar._emit = lambda _payload: None
    responses = []
    sidecar._respond = lambda *_args, **kwargs: responses.append(kwargs)

    sidecar._health_check("req-health", "health_check")

    assert responses[-1]["checklist"] == checklist


def test_sidecar_self_test_preserves_packaged_health_checklist():
    module = _sidecar_module()
    checklist = [{"id": "windows_version", "verdict": "ready", "detail": "ok"}]
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.packaged_health = SimpleNamespace()
    sidecar._packaged_self_test = module.Sidecar._packaged_self_test.__get__(sidecar)
    sidecar._engine_error = ""
    sidecar.args = SimpleNamespace(self_test=False, self_test_fault="")
    sidecar.runtime_root = Path("C:/runtime")
    sidecar.repo_root = None
    sidecar.data_dir = Path("C:/data")
    sidecar.controller = object()
    sidecar.study_v2 = SimpleNamespace(study_core_info=lambda: {})
    sidecar.media_fetch = SimpleNamespace(
        is_available=lambda: False,
        version=lambda: "",
        youtube_support=lambda: {},
    )

    sidecar.packaged_health.run_packaged_health = lambda **_kwargs: {
        "passed": True,
        "startup_ok": True,
        "checks": [{"id": "controller", "ok": True, "required": True, "fatal_at_startup": True}],
        "checklist": checklist,
    }

    health = sidecar._packaged_self_test(include_sidecar=False)

    assert health["checklist"] == checklist


def test_bridge_health_adapter_normalizes_raw_packaged_checks_to_five_rows(tmp_path):
    node = shutil.which("node")
    if node is None:
        return
    harness = tmp_path / "bridge-checklist-contract.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const rawChecks = [
  { id: 'data_directory', ok: true, detail: 'ok' },
  { id: 'ffmpeg', ok: true, detail: 'ok' },
  { id: 'ffprobe', ok: true, detail: 'ok' },
  { id: 'whisper_runtime', ok: true, detail: 'ok' },
  { id: 'whisper_smoke', ok: true, detail: 'ok' },
  { id: 'bundled_model', ok: true, detail: 'ok' },
  { id: 'study_core', ok: true, detail: 'ok' }
];
const context = {
  console: { error() {} },
  window: {
    localStorage: { setItem() {} },
    lecturePackElectron: {
      request(command) {
        if (command === 'health_check') return Promise.resolve({
          startup_ok: true, healthy: true, engine_loaded: true,
          passed: true, checks: rawChecks
        });
        return Promise.resolve({ ok: true });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  const assessment = JSON.parse(await context.window.lpBridge.retryRuntimeAssessment());
  const expected = ['windows_version', 'ffmpeg_ffprobe', 'whisper_runtime', 'bundled_model', 'data_directory'];
  if (JSON.stringify(assessment.checklist.map((item) => item.id)) !== JSON.stringify(expected)) throw new Error('wrong checklist ids');
  if (assessment.checklist[0].verdict !== 'needs_attention') throw new Error('missing Windows evidence must not look ready');
  if (assessment.checklist.slice(1).some((item) => item.verdict !== 'ready')) throw new Error('grouped checks were not ready');
  if (assessment.checklist.some((item) => Object.keys(item).sort().join(',') !== 'detail,id,verdict')) throw new Error('checklist leaked fields');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""".strip() + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [node, str(harness), str(ROOT / "electron-spike" / "electron-bridge.js")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_demo_exit_reason_persists_durable_tour_state_without_renderer_storage(tmp_path):
    module = _sidecar_module()
    config = ConfigManager(str(tmp_path))
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar.config = config
    sidecar.onboarding_state = onboarding_state
    sidecar._demo_session = None
    sidecar._guided_tour_state = None
    sidecar._emit = lambda _payload: None
    responses = []
    sidecar._respond = lambda *_args, **kwargs: responses.append(kwargs)

    sidecar._end_demo_job("req-skip", "end_demo_job", {"reason": "tour_exit"})
    assert responses[-1]["ok"] is True
    assert responses[-1]["guided_tour"]["status"] == "skipped"
    assert onboarding_state.guided_tour_state(config.settings)["eligible"] is False

    sidecar._end_demo_job("req-complete", "end_demo_job", {"reason": "tour_complete"})
    assert responses[-1]["guided_tour"]["status"] == "completed"
    assert onboarding_state.guided_tour_state(config.settings)["completed"] is True


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


def _create_test_job(
    data_root: Path,
    job_id: str,
    title: str,
    *,
    group: str = "",
    status: str = "ready",
    concepts: list[str] | None = None,
) -> None:
    job_dir = data_root / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "job_id": job_id,
        "title": title,
        "created_at": "2026-08-15T00:00:00Z",
    }
    if group:
        manifest["group"] = group
    (job_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (job_dir / "state.json").write_text(
        json.dumps({"overall_status": "completed", "lifecycle": "completed"}),
        encoding="utf-8",
    )

    concept_list = concepts or ["c1", "c2"]
    content = {
        "study_status": status,
        "generated_at": "2026-08-15T00:00:00Z",
        "lecture_analysis": {
            "lecture_summary": f"Summary of {title}",
            "concepts": [{"id": cid, "title": cid} for cid in concept_list],
        },
        "concepts": [{"id": cid, "title": cid} for cid in concept_list],
    }
    (job_dir / "study-content-v2.json").write_text(json.dumps(content), encoding="utf-8")


def _setup_group_study_sidecar(data_root: Path, *, mock_gateway_fn=None):
    from lecturepack import electron_backend
    from lecturepack.services import ai_gateway, group_study, study_v2

    module = _sidecar_module()
    sidecar = module.Sidecar.__new__(module.Sidecar)
    sidecar._engine_error = ""
    sidecar.data_dir = data_root
    sidecar.session_id = "test-session"
    sidecar.current_job = None
    sidecar.Job = Job
    sidecar.electron_backend = electron_backend
    sidecar.group_study = group_study
    sidecar.study_v2 = study_v2
    sidecar.ai_gateway = ai_gateway

    emitted = []
    responses = []
    sidecar._emit = lambda event: emitted.append(event)
    sidecar._respond = lambda request_id, command, **kwargs: responses.append({
        "event": "response",
        "response_to": request_id,
        "command": command,
        **kwargs,
    })

    client = SimpleNamespace()
    if mock_gateway_fn is not None:
        client.request = mock_gateway_fn
    else:
        client.request = lambda task, payload: {
            "group_summary": "Synthesized summary",
            "concepts": [
                {
                    "id": "gc1",
                    "title": "Global Concept 1",
                    "job_ids": [m["job_id"] for m in payload.get("lectures", [])],
                },
            ],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }
    sidecar._ai_gateway_client = client
    sidecar._study_workers_lock = threading.Lock()
    sidecar._gateway_client = lambda: client

    sidecar._job_objects = module.Sidecar._job_objects.__get__(sidecar)
    sidecar._study_v2_group_prepare = module.Sidecar._study_v2_group_prepare.__get__(sidecar)
    sidecar._handle_command = module.Sidecar._handle_command.__get__(sidecar)

    return sidecar, emitted, responses, client


def test_sidecar_study_v2_group_prepare_success_uncached(tmp_path):
    _create_test_job(tmp_path, "job-1", "History 101: Intro", group="History")
    _create_test_job(tmp_path, "job-2", "History 102: Rome", group="History")
    _create_test_job(tmp_path, "job-3", "Physics 101: Mechanics", group="Physics")

    sidecar, emitted, responses, _ = _setup_group_study_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-1",
        "command": "study_v2_group_prepare",
        "payload": {"group": "History", "force": False},
    })

    assert len(responses) == 1
    resp = responses[0]
    assert resp["response_to"] == "req-1"
    assert resp["command"] == "study_v2_group_prepare"
    assert resp["ok"] is True
    assert resp["group"] == "History"
    assert resp["cached"] is False
    assert len(resp["members"]) == 2
    assert {m["job_id"] for m in resp["members"]} == {"job-1", "job-2"}
    assert resp["analysis"]["group_summary"] == "Synthesized summary"
    assert resp["reason"] is None

    # Check progress events emitted
    assert any(
        e.get("event") == "group_study_progress"
        and e.get("group") == "History"
        and e.get("status") == "preparing"
        and e.get("total_jobs") == 2
        for e in emitted
    )
    assert any(
        e.get("event") == "group_study_progress"
        and e.get("group") == "History"
        and e.get("status") == "ready"
        and e.get("cached") is False
        and e.get("members_count") == 2
        for e in emitted
    )

    # Check disk cache created
    from lecturepack.services.group_study import analysis_path
    cache_file = Path(analysis_path(str(tmp_path), "History"))
    assert cache_file.is_file()
    cached_doc = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cached_doc["group"] == "History"
    assert cached_doc["analysis"]["group_summary"] == "Synthesized summary"


def test_sidecar_study_v2_group_prepare_success_cached(tmp_path):
    _create_test_job(tmp_path, "job-1", "History 101: Intro", group="History")
    _create_test_job(tmp_path, "job-2", "History 102: Rome", group="History")

    gateway_calls = []

    def mock_gw(task, payload):
        gateway_calls.append((task, payload))
        return {
            "group_summary": "Initial summary",
            "concepts": [
                {
                    "id": "gc1",
                    "title": "Global 1",
                    "job_ids": [m["job_id"] for m in payload.get("lectures", [])],
                }
            ],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }

    sidecar, emitted, responses, client = _setup_group_study_sidecar(
        tmp_path, mock_gateway_fn=mock_gw
    )

    # First call: builds cache
    sidecar._handle_command({
        "request_id": "req-1",
        "command": "study_v2_group_prepare",
        "payload": {"group": "History"},
    })
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert len(gateway_calls) == 1

    # Second call: hits cache without gateway request
    def exploding_gw(_task, _payload):
        raise AssertionError("Gateway must not be called on cache hit")

    client.request = exploding_gw

    sidecar._handle_command({
        "request_id": "req-2",
        "command": "study_v2_group_prepare",
        "payload": {"group": "History"},
    })
    assert responses[-1]["response_to"] == "req-2"
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is True
    assert responses[-1]["analysis"]["group_summary"] == "Initial summary"
    assert len(responses[-1]["members"]) == 2

    assert any(
        e.get("event") == "group_study_progress"
        and e.get("group") == "History"
        and e.get("status") == "ready"
        and e.get("cached") is True
        for e in emitted
    )


def test_sidecar_study_v2_group_prepare_force_bypass(tmp_path):
    _create_test_job(tmp_path, "job-1", "History 101: Intro", group="History")

    call_count = 0

    def mock_gw(task, payload):
        nonlocal call_count
        call_count += 1
        return {
            "group_summary": f"Summary call {call_count}",
            "concepts": [{"id": "gc1", "title": "Global 1", "job_ids": ["job-1"]}],
            "relationships": [],
            "through_lines": [],
            "gaps": [],
        }

    sidecar, _, responses, _ = _setup_group_study_sidecar(
        tmp_path, mock_gateway_fn=mock_gw
    )

    # First call: populates cache
    sidecar._handle_command({
        "request_id": "req-1",
        "command": "study_v2_group_prepare",
        "payload": {"group": "History"},
    })
    assert responses[-1]["cached"] is False
    assert responses[-1]["analysis"]["group_summary"] == "Summary call 1"
    assert call_count == 1

    # Force bypass call: re-generates
    sidecar._handle_command({
        "request_id": "req-2",
        "command": "study_v2_group_prepare",
        "payload": {"group": "History", "force": True},
    })
    assert responses[-1]["response_to"] == "req-2"
    assert responses[-1]["ok"] is True
    assert responses[-1]["cached"] is False
    assert responses[-1]["analysis"]["group_summary"] == "Summary call 2"
    assert call_count == 2


def test_sidecar_study_v2_group_prepare_missing_group_error(tmp_path):
    sidecar, _, responses, _ = _setup_group_study_sidecar(tmp_path)

    # Empty string
    sidecar._handle_command({
        "request_id": "req-empty",
        "command": "study_v2_group_prepare",
        "payload": {"group": "  "},
    })
    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "missing_group"
    assert "group is required" in responses[-1]["error"]

    # Missing group field
    sidecar._handle_command({
        "request_id": "req-missing",
        "command": "study_v2_group_prepare",
        "payload": {},
    })
    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "missing_group"


def test_sidecar_study_v2_group_prepare_no_ready_lectures(tmp_path):
    # Job exists in group, but has status preparing
    _create_test_job(tmp_path, "job-prep", "Math 101", group="Math", status="preparing")

    sidecar, emitted, responses, _ = _setup_group_study_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-no-ready",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Math"},
    })

    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "no_ready_lectures"
    assert responses[-1]["members"] == []
    assert any(
        e.get("event") == "group_study_progress"
        and e.get("group") == "Math"
        and e.get("status") == "failed"
        and e.get("reason") == "no_ready_lectures"
        for e in emitted
    )


def test_sidecar_study_v2_group_prepare_derive_group_matching(tmp_path):
    # No explicit group in manifest, but title has colon delimiter
    _create_test_job(tmp_path, "job-cs", "CS 101: Introduction to Python")

    sidecar, _, responses, _ = _setup_group_study_sidecar(tmp_path)

    sidecar._handle_command({
        "request_id": "req-derived",
        "command": "study_v2_group_prepare",
        "payload": {"group": "CS 101"},
    })

    assert responses[-1]["ok"] is True
    assert responses[-1]["group"] == "CS 101"
    assert len(responses[-1]["members"]) == 1
    assert responses[-1]["members"][0]["job_id"] == "job-cs"


def test_sidecar_study_v2_group_prepare_gateway_error_resilience(tmp_path):
    _create_test_job(tmp_path, "job-1", "Bio 101", group="Biology")

    def failing_gw(_task, _payload):
        raise RuntimeError("Cloudflare rate limit")

    sidecar, emitted, responses, _ = _setup_group_study_sidecar(
        tmp_path, mock_gateway_fn=failing_gw
    )

    sidecar._handle_command({
        "request_id": "req-fail",
        "command": "study_v2_group_prepare",
        "payload": {"group": "Biology"},
    })

    assert responses[-1]["ok"] is False
    assert responses[-1]["reason"] == "prepare_failed"
    assert "Cloudflare rate limit" in responses[-1]["error"]
    assert any(
        e.get("event") == "group_study_progress"
        and e.get("group") == "Biology"
        and e.get("status") == "failed"
        for e in emitted
    )


def test_bridge_map_call_study_v2_group_prepare(tmp_path):
    node = shutil.which("node")
    if node is None:
        return
    harness = tmp_path / "bridge-group-study-contract.js"
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
        return Promise.resolve({ ok: true });
      },
      onMessage() {}
    }
  }
};
vm.createContext(context);
vm.runInContext(source, context, { filename: 'electron-bridge.js' });
(async () => {
  // Test 1: Positional args (group, force)
  await context.window.lpBridge.call('study_v2_group_prepare', 'CL100', true);
  if (calls[0].command !== 'study_v2_group_prepare' || calls[0].payload.group !== 'CL100' || calls[0].payload.force !== true) {
    throw new Error('positional group and force failed: ' + JSON.stringify(calls[0]));
  }

  // Test 2: Positional arg (group only)
  await context.window.lpBridge.call('study_v2_group_prepare', 'CL100');
  if (calls[1].command !== 'study_v2_group_prepare' || calls[1].payload.group !== 'CL100' || calls[1].payload.force !== false) {
    throw new Error('positional group only failed: ' + JSON.stringify(calls[1]));
  }

  // Test 3: Object payload { group, force }
  await context.window.lpBridge.call('study_v2_group_prepare', { group: 'CS101', force: true });
  if (calls[2].command !== 'study_v2_group_prepare' || calls[2].payload.group !== 'CS101' || calls[2].payload.force !== true) {
    throw new Error('object payload group and force failed: ' + JSON.stringify(calls[2]));
  }

  // Test 4: Object payload { group }
  await context.window.lpBridge.call('study_v2_group_prepare', { group: 'CS101' });
  if (calls[3].command !== 'study_v2_group_prepare' || calls[3].payload.group !== 'CS101' || calls[3].payload.force !== false) {
    throw new Error('object payload group only failed: ' + JSON.stringify(calls[3]));
  }

  // Test 5: Empty call
  await context.window.lpBridge.call('study_v2_group_prepare');
  if (calls[4].command !== 'study_v2_group_prepare' || calls[4].payload.group !== '' || calls[4].payload.force !== false) {
    throw new Error('empty call failed: ' + JSON.stringify(calls[4]));
  }
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
""".strip() + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [node, str(harness), str(ROOT / "electron-spike" / "electron-bridge.js")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

