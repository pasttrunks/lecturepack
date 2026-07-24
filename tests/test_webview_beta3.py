"""Adapter-level tests for beta.3 bridge surface: notification prefs, queue
ops, scheduling, diagnostics redaction, and pause-state relay. Uses a fake
backend + fake controller against a temp data dir (never real LecturePackData)."""

from __future__ import annotations

import json
import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from desktop.win_integration import WindowsIntegration  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402
from lecturepack.services.job_queue import JobQueue  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []
    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    _SIGNALS = ("log_line", "jobs_changed", "job_deleted", "queue_changed",
                "pause_state", "notification_prefs", "diagnostics",
                "job_completed", "post_completion", "status_changed")
    def __init__(self):
        for n in self._SIGNALS:
            setattr(self, n, _Signal())
    def last(self, name):
        em = getattr(self, name).emissions
        return json.loads(em[-1]) if em else None


class _FakePower:
    def __init__(self): self._a = False
    def set_awake(self, on): self._a = on
    @property
    def active(self): return self._a

class _FakeTaskbar:
    def __init__(self): self.state = "none"
    def set_state(self, state, progress=0): self.state = state

class _FakeNotifier:
    def __init__(self): self.shown = []
    def available(self): return True
    def show(self, note): self.shown.append(note); return True


class _FakeController:
    def __init__(self):
        self.paused = False
        self.resumed = False
        self.retried = None
    def request_pause(self): self.paused = True; return True
    def resume(self): self.resumed = True
    def retry_stage(self, stage): self.retried = stage
    def set_job(self, job): pass
    class _FF:  ffmpeg_path = "C:/x/bin/ffmpeg.exe"
    ffmpeg_wrapper = _FF()


def _adapter(tmp_path, prefs=None):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    a.current_job = None
    a._session_id = "sess-test"
    a.controller = _FakeController()
    a.win = WindowsIntegration(power=_FakePower(), taskbar=_FakeTaskbar(),
                               notifier=_FakeNotifier(), prefs=prefs or {})
    a.queue = JobQueue(str(tmp_path))
    return a


# --- notification prefs ---------------------------------------------------- #
def test_set_notification_prefs_persists_and_emits(tmp_path):
    a = _adapter(tmp_path)
    a.set_notification_prefs(json.dumps({"notify_complete": False, "play_sound": True}))
    assert a.win.prefs["notify_complete"] is False
    assert a.win.prefs["play_sound"] is True
    # persisted to engine config
    assert a.config.get("notifications", {}).get("notify_complete") is False
    # emitted back to the UI
    assert a.backend.last("notification_prefs")["notify_complete"] is False


def test_get_notification_prefs_emits_current(tmp_path):
    a = _adapter(tmp_path)
    a.get_notification_prefs()
    assert "notify_complete" in a.backend.last("notification_prefs")


def test_test_notification_fires(tmp_path):
    a = _adapter(tmp_path)
    a.test_notification()
    assert len(a.win.notifier.shown) == 1


# --- queue --------------------------------------------------------------- #
def test_enqueue_reorder_runnow_remove_emit_queue(tmp_path):
    a = _adapter(tmp_path)
    a.enqueue_job("j1"); a.enqueue_job("j2"); a.enqueue_job("j3")
    q = a.backend.last("queue_changed")
    assert [r["id"] for r in q["queue"]] == ["j1", "j2", "j3"]
    a.run_now("j3")
    assert [r["id"] for r in a.backend.last("queue_changed")["queue"]][0] == "j3"
    a.reorder_queue("j3", 2)
    assert [r["id"] for r in a.backend.last("queue_changed")["queue"]][-1] == "j3"
    a.remove_from_queue("j1")
    assert "j1" not in [r["id"] for r in a.backend.last("queue_changed")["queue"]]


def test_schedule_and_unschedule(tmp_path):
    a = _adapter(tmp_path)
    a.schedule_job("j1", "2026-08-01T09:00:00", "America/New_York", "ask")
    assert a.backend.last("queue_changed")["schedules"]["j1"]["missed_policy"] == "ask"
    a.unschedule_job("j1")
    assert "j1" not in a.backend.last("queue_changed")["schedules"]


# --- diagnostics (redaction) ---------------------------------------------- #
def test_run_diagnostics_redacts(tmp_path):
    a = _adapter(tmp_path)
    # a job with a failed stage carrying a secret in its error
    from lecturepack.models.job import Job
    v = tmp_path / "lec.mp4"; v.write_bytes(b"x")
    job = Job(str(tmp_path), video_path=str(v))
    from lecturepack import constants
    job.set_stage_status(constants.STAGE_TRANSCRIBE, "failed",
                         error="boom gsk_ABCDEFGHIJKLMNOP1234")
    a._app_version = lambda: "0.9.0-beta.3"
    a.run_diagnostics(job.job_id)
    diag = a.backend.last("diagnostics")
    assert diag["app_version"] == "0.9.0-beta.3"
    assert "gsk_" not in json.dumps(diag)
    # no transcript/content keys
    assert set(diag.keys()) == {"app_version", "job_id", "stage", "status",
                                "error_summary", "exit_code", "timestamp",
                                "runtime_paths"}


# --- startup reconciliation sweep + lifecycle-aware listing ---------------- #
def _seed_job(data_dir, job_id, lifecycle=None, overall="pending", stages=None,
              session=None, title="CL100 - Day 1"):
    root = os.path.join(data_dir, "jobs", job_id)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "manifest.json"), "w") as fh:
        json.dump({"schema_version": 1, "job_id": job_id, "created_at": "2026-01-01T00:00:00",
                   "title": title, "source": {"filename": "lec.mp4"}}, fh)
    st = {"job_id": job_id, "overall_status": overall,
          "stages": stages or {"Transcribe": {"status": "running"}}}
    if lifecycle is not None:
        st["lifecycle"] = lifecycle
    if session is not None:
        st["session"] = session
    with open(os.path.join(root, "state.json"), "w") as fh:
        json.dump(st, fh)
    with open(os.path.join(root, "source.json"), "w") as fh:
        json.dump({"duration": 60.0}, fh)


def test_startup_sweep_reconciles_orphan_running_to_interrupted(tmp_path):
    a = _adapter(tmp_path)
    # a pre-beta.3 job left 'running' by a dead session (no lifecycle field)
    _seed_job(str(tmp_path), "orphan", overall="running",
              stages={"Transcribe": {"status": "running"}})
    a._reconcile_jobs_on_startup()
    # persisted state is now interrupted; the running stage was flipped too
    st = json.load(open(os.path.join(str(tmp_path), "jobs", "orphan", "state.json")))
    assert st["lifecycle"] == "interrupted"
    assert st["stages"]["Transcribe"]["status"] == "interrupted"


def test_list_jobs_surfaces_interrupted_not_running(tmp_path):
    a = _adapter(tmp_path)
    _seed_job(str(tmp_path), "orphan", overall="running",
              stages={"Transcribe": {"status": "running"}})
    a._reconcile_jobs_on_startup()
    rows = a._list_jobs()
    row = next(r for r in rows if r["id"] == "orphan")
    assert row["status"] == "interrupted"  # NOT "running"


def test_list_jobs_lifecycle_status_mapping(tmp_path):
    a = _adapter(tmp_path)
    _seed_job(str(tmp_path), "q", lifecycle="queued", stages={})
    _seed_job(str(tmp_path), "p", lifecycle="paused", stages={})
    _seed_job(str(tmp_path), "c", lifecycle="completed", stages={})
    rows = {r["id"]: r["status"] for r in a._list_jobs()}
    assert rows["q"] == "queued"
    assert rows["p"] == "paused"
    assert rows["c"] == "done"


# --- one-active-job: enqueue when busy ------------------------------------- #
def test_start_processing_enqueues_when_busy(tmp_path):
    from lecturepack.models.job import Job
    a = _adapter(tmp_path)
    # a running job holds the slot
    rv = tmp_path / "r.mp4"; rv.write_bytes(b"x")
    running = Job(str(tmp_path), video_path=str(rv))
    a.current_job = running
    a.controller._active_stages = {"Transcribe"}  # is_processing() -> True
    # a second job is started
    nv = tmp_path / "n.mp4"; nv.write_bytes(b"x")
    newjob = Job(str(tmp_path), video_path=str(nv))
    a._pending_job = newjob
    a.start_processing("study")
    # it was queued, not run
    assert newjob.job_id in a.queue.queued()
    assert newjob.get_lifecycle() == "queued"


def test_is_processing_reflects_active_stages(tmp_path):
    a = _adapter(tmp_path)
    a.controller._active_stages = set()
    assert a.is_processing() is False
    a.controller._active_stages = {"Transcribe"}
    assert a.is_processing() is True


# --- pause-state relay ----------------------------------------------------- #
def test_pause_state_relay(tmp_path):
    a = _adapter(tmp_path)
    a.pause_job()
    assert a.controller.paused is True
    a._on_pause_state("pause_requested")
    assert a.win.taskbar.state == "paused"
    a._on_pause_state("paused")
    assert a.backend.last("pause_state")["state"] == "paused"
