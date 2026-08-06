"""Focused tests for the import-queue-fix pass, commit 2: pre-job options and
the usable queue.

Covers: start_job receiving the selected quality/output (with a job id),
options persisted with the job and exposed in summaries, queue ordering and
removal, queue persistence across restarts, and the one-active-job invariant.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "electron-spike"


# --------------------------------------------------------------------------- #
# Pre-job options reach start_job with the selected quality and output
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_start_processing_sends_selected_quality_and_output(tmp_path):
    harness = tmp_path / "start-options.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert');
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
  await context.window.lpBridge.call('start_processing', { mode: 'transcript', preset: 'high', job_id: 'job-7' });
  assert.strictEqual(calls.length, 1);
  const call = calls[0];
  assert.strictEqual(call.command, 'start_job');
  assert.strictEqual(call.payload.mode, 'transcript');
  assert.strictEqual(call.payload.preset, 'high');
  assert.strictEqual(call.payload.auto_export, true);
  assert.strictEqual(call.payload.job_id, 'job-7');
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


# --------------------------------------------------------------------------- #
# Sidecar: options are saved with the job and shown in summaries
# --------------------------------------------------------------------------- #
def test_sidecar_saves_options_with_job_and_exposes_queue_position():
    sidecar = (SPIKE / "python-sidecar.py").read_text(encoding="utf-8")
    assert 'job.settings["product_mode"] = self._product_mode(payload.get("mode"))' in sidecar
    assert 'job.settings["preset"] = self._preset(payload.get("preset"))' in sidecar
    assert '"preset": str(settings.get("preset", "balanced") or "balanced")' in sidecar
    assert '"product_mode": str(settings.get("product_mode", "study_pack") or "study_pack")' in sidecar
    assert '"queue_position": queue_position' in sidecar
    assert '"waiting": queue_position is not None' in sidecar


def test_sidecar_start_job_enqueues_when_another_job_is_active():
    sidecar = (SPIKE / "python-sidecar.py").read_text(encoding="utf-8")
    assert "position = self.electron_backend.enqueue_job(self.queue, job.job_id)" in sidecar
    assert 'self._respond(request_id, command, job_id=job.job_id, queued=True, position=position)' in sidecar
    assert "self.electron_backend.start_or_enqueue(self.queue, job.job_id)" in sidecar
    assert 'self._emit({"event": "job_queued", "job_id": job.job_id, "position": position})' in sidecar


def test_sidecar_emits_queue_prunes_terminal_jobs_and_resumes():
    sidecar = (SPIKE / "python-sidecar.py").read_text(encoding="utf-8")
    assert "self._push_queue()" in sidecar
    assert "def _prune_queue" in sidecar
    assert '"done", "failed", "cancelled", "interrupted"' in sidecar
    assert "def _maybe_resume_queue" in sidecar
    assert "def _drain_previous_run" in sidecar
    assert "self._promote_next()" in sidecar


# --------------------------------------------------------------------------- #
# Queue model (Python): one active job, ordering, removal, persistence
# --------------------------------------------------------------------------- #
def _job_queue_factory():
    from lecturepack.services.job_queue import JobQueue
    return JobQueue


def test_start_or_enqueue_keeps_one_active_job(tmp_path):
    from lecturepack import electron_backend as eb

    queue = _job_queue_factory()(str(tmp_path))
    action, position = eb.start_or_enqueue(queue, "job-a")
    assert action == "started"
    assert queue.active == "job-a"

    action, position = eb.start_or_enqueue(queue, "job-b")
    assert action == "queued"
    assert position == 0
    assert queue.active == "job-a"  # one active job invariant
    assert queue.queued() == ["job-b"]

    # A second job cannot claim the slot while job-a is active.
    action, position = eb.start_or_enqueue(queue, "job-c")
    assert action == "queued"
    assert queue.active == "job-a"


def test_queue_release_and_promotion_starts_next_in_order(tmp_path):
    from lecturepack import electron_backend as eb

    queue = _job_queue_factory()(str(tmp_path))
    eb.start_or_enqueue(queue, "job-a")
    eb.start_or_enqueue(queue, "job-b")
    eb.start_or_enqueue(queue, "job-c")

    assert queue.queued() == ["job-b", "job-c"]
    queue.finish_active("job-a")
    assert queue.promote_next() == "job-b"
    assert queue.active == "job-b"
    assert queue.queued() == ["job-c"]


def test_queue_reorder_and_removal(tmp_path):
    from lecturepack import electron_backend as eb

    queue = _job_queue_factory()(str(tmp_path))
    queue.enqueue("job-a")
    queue.enqueue("job-b")
    queue.enqueue("job-c")

    assert eb.reorder_queue(queue, "job-c", 0) is True
    assert queue.queued() == ["job-c", "job-a", "job-b"]
    assert eb.remove_from_queue(queue, "job-a") is True
    assert queue.queued() == ["job-c", "job-b"]


def test_queue_order_survives_restart(tmp_path):
    from lecturepack import electron_backend as eb

    queue = _job_queue_factory()(str(tmp_path))
    queue.enqueue("job-a")
    queue.enqueue("job-b")
    queue.enqueue("job-c")
    eb.reorder_queue(queue, "job-c", 0)

    restored = _job_queue_factory()(str(tmp_path))
    assert restored.queued() == ["job-c", "job-a", "job-b"]
