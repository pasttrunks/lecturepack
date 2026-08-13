"""Focused tests for the job-view-switching pass: viewing one job while
another processes, per-job Home progress, Previous/Next source navigation,
and the two explicit Transcript copy options.

The renderer keeps two concepts separate: the ACTIVE processing job (driven by
the backend active_job signal and the job list) and the VIEWED job (the
workspace owner). These tests pin that separation at the source level, plus
the view_job sidecar command that fetches a job's payloads without disturbing
the running pipeline, and the copy formatting helpers executed in Node.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
APP = UI / "app.js"
HTML = UI / "index.html"
BRIDGE = ROOT / "electron-spike" / "electron-bridge.js"
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"
CONTRACT = ROOT / "electron-spike" / "contracts" / "electron-bridge-contract.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def extract_function(source: str, name: str) -> str:
    """Extract one top-level function declaration (brace-balanced) from app.js."""
    start = source.index(f"function {name}")
    brace = source.index("{", start)
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"function {name} not closed")


# --------------------------------------------------------------------------- #
# 1. Selecting a completed job while another job processes does not change
#    the active processing job.
# --------------------------------------------------------------------------- #
def test_viewed_job_is_separate_from_active_processing_job() -> None:
    app = read(APP)
    assert re.search(r"activeJobId:\s*''", app)
    # selectJob changes the VIEWED job only; it must never touch the active
    # processing slot.
    select = block(app, "function selectJob(jobId, opts) {", "function selectAdjacentJob")
    assert "setActiveJob(jobId" in select
    assert "activeJobId" not in select.replace("lpBridge.call('view_job'", "")
    # The active_job handler auto-follows only a genuinely NEW active job, so a
    # running job cannot re-yank the view after the user opens an older job.
    active = block(app, "lpBridge.on('active_job'", "lpBridge.on('pipeline_changed'")
    assert "a.id !== autoSelectedActiveId" in active
    assert "selectJob(a.id, { silent: true })" in active


def test_view_job_never_swaps_the_sidecar_current_job() -> None:
    sidecar = read(SIDECAR)
    view = block(sidecar, "def _view_job(", "def _get_slides")
    assert "job = self._job_for(payload)" in view
    # Fetching a job's payloads must not re-point current_job or clear the
    # running pipeline's stage marker.
    assert "self.current_job =" not in view
    assert "self.current_stage =" not in view
    assert "_emit_pipeline(job)" in view
    assert "_emit_study_changed(job)" in view


# --------------------------------------------------------------------------- #
# 2. A progress event updates the correct Home job card by job_id.
# --------------------------------------------------------------------------- #
def test_progress_updates_home_card_by_job_id() -> None:
    app = read(APP)
    status = block(app, "lpBridge.on('status_changed'", "lpBridge.on('slides_changed'")
    assert "BY JOB ID" in status
    assert "applyJobLive(owner, patch)" in status
    assert "updateJobCardDom(owner)" in status
    assert "listEntry = _jobById(owner)" in status
    # The card patch target is the job named by the event, never only the
    # viewed job.
    assert "owner === LP.state.jobId" in status
    # Progress-only updates patch in place; structural changes rebuild.
    live = block(app, "function updateJobCardDom(jobId) {", "// Process screen banner")
    assert "card.dataset.status !== job.status" in live
    assert "card.dataset.status" in live


def test_pipeline_events_accumulate_for_non_viewed_jobs() -> None:
    app = read(APP)
    pipe = block(app, "lpBridge.on('pipeline_changed'", "lpBridge.on('log_line'")
    assert "routeJobPayload(p, function (data)" in pipe
    assert "workspaceFor(owner)" in pipe or "routeJobPayload(" in pipe
    log = block(app, "lpBridge.on('log_line'", "lpBridge.on('status_changed'")
    assert "routeJobPayload(line, function (data)" in log


# --------------------------------------------------------------------------- #
# 3. Completed jobs immediately settle to Complete and 100%.
# --------------------------------------------------------------------------- #
def test_terminal_status_settles_card_and_readouts() -> None:
    app = read(APP)
    status = block(app, "lpBridge.on('status_changed'", "lpBridge.on('slides_changed'")
    assert "patch.pct = patch.status === 'done' ? 100 : 0" in status
    assert "patch.status = " in status
    assert "settleTerminalStatus(" in status
    assert "terminalLabel === 'cancelled'" in status
    # A replay of a live status for a job the list already calls terminal is
    # ignored entirely (sidebar AND card stay settled).
    assert "listTerminal && !incomingTerminal" in status


# --------------------------------------------------------------------------- #
# 4. Previous/Next changes the selected job.
# --------------------------------------------------------------------------- #
def test_prev_next_switcher_changes_selected_job() -> None:
    app = read(APP)
    html = read(HTML)
    switcher = block(app, "function renderJobSwitcher() {", "// Process screen banner")
    assert "data-jdir" in switcher
    assert "prevDisabled = idx <= 0" in switcher
    assert "nextDisabled = idx === -1 || idx >= jobs.length - 1" in switcher
    assert "selectAdjacentJob(parseInt(sw.dataset.jdir, 10) || 0)" in app
    # The same shared switcher host is present in every workspace screen.
    for host in ("process", "review", "transcript", "study", "exports"):
        assert f'data-jsw="{host}"' in html, f"missing switcher host: {host}"


# --------------------------------------------------------------------------- #
# 5/6. Transcript copy: plain excludes timestamps, stamped includes them.
# --------------------------------------------------------------------------- #
_COPY_BLOCKS = [
    {"t": "00:42", "html": "The great pyramid originally rose 146 meters tall."},
    {"t": "00:55", "html": "Its base is level to less than two centimeters."},
]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_copy_text_excludes_timestamps(tmp_path) -> None:
    harness = tmp_path / "copy-plain.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
function extract(src, name) {
  const start = src.indexOf('function ' + name);
  const brace = src.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  throw new Error(name + ' not found');
}
const blocks = JSON.parse(process.argv[3]);
const context = {
  document: {
    createElement() {
      return { set innerHTML(v) { this._v = v; }, get textContent() { return this._v || ''; } };
    }
  },
  result: null
};
vm.createContext(context);
vm.runInContext(extract(source, 'transcriptBlockText') + '\n' + extract(source, 'formatTranscriptPlain') + '\nresult = formatTranscriptPlain(' + JSON.stringify(blocks) + ');', context);
const text = context.result;
assert.ok(typeof text === 'string' && text.length > 0, 'empty copy');
assert.ok(!text.includes('00:42') && !text.includes('00:55'), 'plain copy must not contain timestamps');
assert.ok(text.includes('great pyramid') && text.includes('centimeters'), 'plain copy lost words');
assert.strictEqual(text.split('\n\n').length, 2, 'one paragraph per block');
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(harness), str(APP), json.dumps(_COPY_BLOCKS)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_copy_with_timestamps_includes_timestamps(tmp_path) -> None:
    harness = tmp_path / "copy-stamped.js"
    harness.write_text(
        r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
function extract(src, name) {
  const start = src.indexOf('function ' + name);
  const brace = src.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  throw new Error(name + ' not found');
}
const blocks = JSON.parse(process.argv[3]);
const context = {
  document: {
    createElement() {
      return { set innerHTML(v) { this._v = v; }, get textContent() { return this._v || ''; } };
    }
  },
  result: null
};
vm.createContext(context);
vm.runInContext(extract(source, 'transcriptBlockText') + '\n' + extract(source, 'formatTranscriptStamped') + '\nresult = formatTranscriptStamped(' + JSON.stringify(blocks) + ');', context);
const text = context.result;
assert.ok(typeof text === 'string' && text.length > 0, 'empty copy');
assert.ok(text.includes('00:42') && text.includes('00:55'), 'stamped copy must include timestamps');
assert.ok(text.indexOf('00:42') < text.indexOf('great pyramid'), 'timestamp precedes its words');
assert.strictEqual(text.split('\n\n').length, 2, 'one paragraph per block');
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(harness), str(APP), json.dumps(_COPY_BLOCKS)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# view_job transport: bridge mapping + contract + copy buttons in markup
# --------------------------------------------------------------------------- #
def test_bridge_maps_view_job_to_the_sidecar_command() -> None:
    bridge = read(BRIDGE)
    assert "name === 'view_job'" in bridge
    assert "command: 'view_job'" in bridge
    assert "job_id: jobIdPayload(first)" in bridge


def test_contract_lists_view_job_as_implemented() -> None:
    data = json.loads(read(CONTRACT))
    ops = {op["name"]: op for op in data["operations"]}
    assert "view_job" in ops
    op = ops["view_job"]
    assert op["direction"] == "command"
    assert op["production_core"] is True
    assert op["status"] == "IMPLEMENTED"
    assert "job_id" in op["request_fields"]


def test_transcript_copy_markup_has_both_actions() -> None:
    html = read(HTML)
    assert 'id="btn-copy-text"' in html
    assert 'id="btn-copy-stamped"' in html
    assert 'id="btn-copy-transcript"' not in html
    app = read(APP)
    assert "formatTranscriptPlain(LP.data.transcript.blocks)" in app
    assert "formatTranscriptStamped(LP.data.transcript.blocks)" in app
    assert "copyText(formatTranscriptPlain" in app
    assert "copyText(formatTranscriptStamped" in app


def test_sidecar_derives_live_transcribe_progress_from_segments() -> None:
    """During a long transcription the engine streams segment timestamps but
    no stage-percent events, which left Home stuck at the pre-transcribe value
    (43% in the reported bug). The sidecar must turn the latest segment's end
    time into a real, monotonic Transcribe percent without touching the
    transcription engine."""
    sidecar = read(SIDECAR)
    seg = block(sidecar, "def _on_transcript_segment", "def _on_pipeline_completed")
    assert '"end_ms"' in seg
    assert '"duration"' in seg
    assert 'self.stage_percent["Transcribe"]' in seg
    assert "_emit_status(" in seg and '"Processing"' in seg
    assert "never changes the transcription engine" in seg
    # The gate is MEMBERSHIP of the running set, not the primary-stage scalar.
    # Detect Slides runs concurrently and emits real stage-progress events
    # while whisper emits none, so a `current_stage == "Transcribe"` test lost
    # the scalar to Detect Slides and could never win it back -- the row sat at
    # 0% for the whole lecture. See tests/test_parallel_stage_reporting.py,
    # which drives this end to end rather than reading the source.
    assert '"Transcribe" in self.active_stages' in seg
    assert 'self.current_stage == "Transcribe"' not in seg


def test_pipeline_stages_never_light_a_stale_stage() -> None:
    """A persisted 'running' status must not keep a finished stage's bar lit.

    This originally read "never show two active stages", which was too strong:
    Transcribe and Detect Slides genuinely DO run at the same time, and drawing
    only one of them as active left the other as a grey, bar-less row while it
    was working. What must never happen is a STALE row -- a leftover "running"
    status from a previous stage lit next to the real one, which froze the
    perceived percent during stage transitions.

    So the fallback stays conditional on there being no live stage at all, and
    only genuinely running stages (tracked in active_stages) light up. See
    tests/test_parallel_stage_reporting.py for the concurrent-group behaviour.
    """
    sidecar = read(SIDECAR)
    stages = block(sidecar, "def _pipeline_stages(", "def _slides(")
    assert "stage == active" in stages
    assert "stage in live" in stages
    assert '(not active and status == "running")' in stages
    # The live set is only trusted for the job actually processing -- another
    # job must never borrow it.
    assert "live = self.active_stages if active_stage is None else set()" in stages


def test_queued_position_banner_is_one_based() -> None:
    """The backend reports 0-based queue positions, so the first queued job
    carries position 0; the Process banner must normalize to the visible
    1-based wording ("Position 1") and never drop a valid 0."""
    app = read(APP)
    state = block(app, "function renderProcessJobState() {", "// Completion card stats")
    assert "Waiting to process" in state
    assert "Number(pos) + 1" in state
    assert "pos = i + 1" in state
    assert 'pos === null || pos === undefined || pos === \'\'' in state
