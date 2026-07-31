"""Contract coverage for Phase 1 Plan 7: the `checking`/`checklist` first-run
overlay states layered onto `RuntimeSetupGateModel`/`RuntimeSetupGate`.

Follows `tests/test_setup_gate_repair.py`'s own conventions: static source
assertions for the wiring contracts, and a real Node subprocess execution of
the extracted reducer for behavioral/transition contracts, so the reducer is
proven without a JS test-runner dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from lecturepack.services.first_run_checklist import FIRST_RUN_CHECKLIST_ITEMS

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"


def read_ui(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


def reducer_source() -> str:
    source = read_ui("app.js")
    return source.split("function RuntimeSetupGateModel()", 1)[1].split("var RuntimeSetupGate", 1)[0]


def constants_source() -> str:
    """FIRST_RUN_ROWS/FIRST_RUN_VERDICT_STATES live above the reducer function
    and are referenced by it -- the Node harness needs them in scope too."""
    source = read_ui("app.js")
    return source.split("var FIRST_RUN_ROWS = [", 1)[1].rsplit(
        "function RuntimeSetupGateModel()", 1
    )[0]


def run_node(body: str) -> subprocess.CompletedProcess:
    program = (
        "var FIRST_RUN_ROWS = ["
        + constants_source()
        + "function RuntimeSetupGateModel()"
        + reducer_source()
        + "\n"
        + body
    )
    return subprocess.run(["node", "-e", program], capture_output=True, text=True)


# ------------------------------------------------------------------ Task 1 --


def test_first_run_rows_and_verdict_states_have_the_locked_cardinality() -> None:
    app = read_ui("app.js")
    rows_block = app.split("var FIRST_RUN_ROWS = [", 1)[1].split("];", 1)[0]
    row_count = rows_block.count("{ id:")
    assert row_count == 5

    verdict_block = app.split("var FIRST_RUN_VERDICT_STATES = {", 1)[1].split("};", 1)[0]
    verdict_count = len([p for p in verdict_block.split(",") if p.strip()])
    assert verdict_count == 2


def test_first_run_rows_ids_match_backend_canonical_order() -> None:
    app = read_ui("app.js")
    rows_block = app.split("var FIRST_RUN_ROWS = [", 1)[1].split("];", 1)[0]
    ui_ids = re.findall(r"id:\s*'([a-z_]+)'", rows_block)
    assert ui_ids == list(FIRST_RUN_CHECKLIST_ITEMS)


def test_states_array_gains_checking_and_checklist() -> None:
    app = read_ui("app.js")
    states_line = app.split("var STATES = [", 1)[1].split("];", 1)[0]
    assert "'checking'" in states_line
    assert "'checklist'" in states_line


def test_reducer_exposes_progress_acknowledge_and_to_checklist() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        if (typeof gate.progress !== 'function') process.exit(1);
        if (typeof gate.acknowledge !== 'function') process.exit(2);
        if (typeof gate.toChecklist !== 'function') process.exit(3);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_pending_full_path_payload_enters_checking_state() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        const view = gate.bootstrap({bootstrap_pending: true, validation_path: 'full'});
        if (view.state !== 'checking') process.exit(1);
        if (view.healthy !== false) process.exit(2);
        if (view.terminal !== false) process.exit(3);
        if (view.bootstrapPending !== true) process.exit(4);
        for (const id of ''' + json.dumps(list(FIRST_RUN_CHECKLIST_ITEMS)) + r''') {
          if (view.checkProgress[id] !== 'pending') process.exit(5);
        }
        '''
    )
    assert result.returncode == 0, result.stderr


def test_pending_light_path_payload_leaves_state_unchanged() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        const before = gate.snapshot().state;
        const view = gate.bootstrap({bootstrap_pending: true, validation_path: 'light'});
        if (view.state !== before) process.exit(1);
        if (view.bootstrapPending !== true) process.exit(2);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_pending_bootstrap_does_not_hijack_an_active_repair() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        gate.begin('op-1', 'repairing');
        const view = gate.bootstrap({bootstrap_pending: true, validation_path: 'full'});
        if (view.state !== 'repairing') process.exit(1);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_healthy_unacknowledged_reaches_checklist_and_acknowledged_does_not() -> None:
    result = run_node(
        r'''
        const gateA = RuntimeSetupGateModel();
        const a = gateA.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false});
        if (a.state !== 'checklist') process.exit(1);
        if (a.healthy !== true) process.exit(2);

        const gateB = RuntimeSetupGateModel();
        const b = gateB.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: true});
        if (b.state === 'checklist') process.exit(3);
        if (b.healthy !== true) process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_progress_ignored_outside_checking_and_for_unknown_ids() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        // Not in checking state yet (default state is 'gate') -- ignored.
        let view = gate.progress({id: 'windows_version', state: 'resolved'});
        if (view.checkProgress.windows_version) process.exit(1);

        gate.bootstrap({bootstrap_pending: true, validation_path: 'full'});
        view = gate.progress({id: 'not_a_real_id', state: 'resolved'});
        if (view.checkProgress.not_a_real_id) process.exit(2);

        view = gate.progress({id: 'windows_version', state: 'checking'});
        if (view.checkProgress.windows_version !== 'checking') process.exit(3);
        view = gate.progress({id: 'windows_version', state: 'resolved'});
        if (view.checkProgress.windows_version !== 'resolved') process.exit(4);
        // The other four rows are untouched.
        if (view.checkProgress.data_directory !== 'pending') process.exit(5);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_acknowledge_sets_flag_and_refreshes_checklist_leaving_state_at_checklist() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false});
        const refreshed = {checklist: [{id: 'windows_version', verdict: 'ready', detail: ''}]};
        const view = gate.acknowledge(refreshed);
        if (view.acknowledged !== true) process.exit(1);
        if (view.state !== 'checklist') process.exit(2);
        if (!Array.isArray(view.checklist) || view.checklist.length !== 1) process.exit(3);

        // An empty-resolution acknowledge still advances the flag locally.
        const gate2 = RuntimeSetupGateModel();
        gate2.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false});
        const view2 = gate2.acknowledge(null);
        if (view2.acknowledged !== true) process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_reset_preserves_acknowledged_flag_while_clearing_operation_state() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false});
        gate.acknowledge(null);
        gate.begin('some-op');
        const view = gate.reset();
        if (view.acknowledged !== true) process.exit(1);
        if (view.activeOperation !== null) process.exit(2);
        if (view.state !== 'gate') process.exit(3);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_to_checklist_is_a_no_op_unless_healthy_and_unacknowledged() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        // Not healthy yet -- no-op.
        let view = gate.toChecklist();
        if (view.state === 'checklist') process.exit(1);

        gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: true});
        // Healthy but already acknowledged -- no-op.
        view = gate.toChecklist();
        if (view.state === 'checklist') process.exit(2);

        const gate2 = RuntimeSetupGateModel();
        gate2.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false});
        // Reset the transient checklist auto-transition to prove toChecklist
        // itself is what moves it (simulate an already-closed overlay by
        // beginning and resetting an operation first).
        gate2.begin('op'); gate2.abandon();
        view = gate2.toChecklist();
        if (view.state !== 'checklist') process.exit(3);
        if (view.healthy !== true) process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_pre_existing_reducer_payload_shapes_preserve_old_pending_and_healthy_semantics() -> None:
    """Replays the exact two payload shapes from
    test_setup_gate_repair.py::test_executable_reducer_seam_covers_the_authoritative_gate_lifecycle
    and asserts the D-11 failure-gate behaviour is byte-identical, and that the
    HEALTHY payload's `bootstrapPending`/`healthy` fields are byte-identical.
    (Its `state` is intentionally allowed to advance to 'checklist' per D-12 --
    that is this plan's whole point, not a regression.)"""
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        const a = gate.bootstrap({runtime_health_state: 'SETUP_REQUIRED'});
        if (a.state !== 'gate') process.exit(1);
        if (a.bootstrapPending !== false) process.exit(2);

        const b = gate.bootstrap({runtime_health_state: 'HEALTHY'});
        if (b.bootstrapPending !== false) process.exit(3);
        if (b.healthy !== true) process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_no_pending_no_path_no_acknowledged_no_checklist_key_defaults_safely() -> None:
    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        const view = gate.bootstrap({});
        if (view.bootstrapPending !== false) process.exit(1);
        if (view.validationPath !== null) process.exit(2);
        if (view.acknowledged !== false) process.exit(3);
        if (!Array.isArray(view.checklist) || view.checklist.length !== 0) process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr
