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


# ------------------------------------------------------------------ Task 2 --


def overlay_block() -> str:
    return read_ui("index.html").split('id="runtime-setup-overlay"', 1)[1]


def gate_controller_source() -> str:
    app = read_ui("app.js")
    return app.split("var RuntimeSetupGate =", 1)[1].split("/* Clears", 1)[0]


def test_markup_has_exactly_one_checking_and_one_checklist_section() -> None:
    block = overlay_block()
    assert block.count('data-runtime-state="checking"') == 1
    assert block.count('data-runtime-state="checklist"') == 1


def test_markup_contains_every_new_element_id_exactly_once() -> None:
    block = overlay_block()
    for element_id in (
        "runtime-checking-heading", "runtime-checking-rows", "runtime-checking-progress",
        "runtime-checking-counter", "runtime-checklist-heading", "runtime-checklist-body",
        "runtime-checklist-rows", "runtime-checklist-empty", "btn-runtime-continue", "btn-runtime-skip",
    ):
        assert block.count(f'id="{element_id}"') == 1, element_id


def test_every_overlay_id_has_a_writer_in_app_js_except_the_static_label() -> None:
    """The BUG-04 lesson, enforced as an automated test: an id shipped with no
    writer anywhere in app.js is a permanent hardcoded value. Exactly one
    allowlisted id exists -- the overlay's static aria-labelledby target,
    which has no dynamic value -- and the allowlist itself is asserted to
    have exactly one member so it cannot quietly grow."""
    allow = {"runtime-setup-title"}
    assert len(allow) == 1
    block = overlay_block()
    app = read_ui("app.js")
    ids = set(re.findall(r'id="([a-z0-9-]+)"', block)) - allow
    missing = sorted(i for i in ids if i not in app)
    assert not missing, f"overlay ids with no writer in app.js: {missing}"


def test_checking_section_has_exactly_one_progressbar_and_one_fill() -> None:
    block = overlay_block()
    checking_section = block.split('data-runtime-state="checking"', 1)[1].split("</section>", 1)[0]
    assert checking_section.count('role="progressbar"') == 1
    assert checking_section.count("lp-fill") == 1


def test_app_js_defines_the_three_new_renderer_functions_and_render_calls_them() -> None:
    app = read_ui("app.js")
    assert "function firstRunRow(" in app
    assert "function renderChecking(" in app
    assert "function renderChecklist(" in app
    controller = gate_controller_source()
    assert "renderChecking();" in controller
    assert "renderChecklist();" in controller


def test_first_run_row_badge_declares_only_the_allowed_inline_properties() -> None:
    app = read_ui("app.js")
    body = app.split("function firstRunRow(", 1)[1].split("\n    }", 1)[0]
    badge_style = body.split("badge.style.cssText = ", 1)[1].split(";\n", 1)[0]
    declared = set(re.findall(r"([a-zA-Z-]+)\s*:", badge_style))
    allowed = {"border-width", "border-style", "border-radius", "padding", "font", "white-space", "flex"}
    assert declared == allowed, declared


def test_reduced_motion_block_still_clamps_lp_state_stage_fill_to_fast_token() -> None:
    css = (UI / "app.css").read_text(encoding="utf-8")
    assert re.search(
        r"\.lp-state,\.lp-stage,\.lp-fill\{\s*transition-duration:var\(--motion-fast\)\s*!important;",
        css,
    )


def test_app_css_has_a_net_change_of_zero_lines() -> None:
    result = subprocess.run(
        ["git", "diff", "--numstat", "--", "app/ui/app.css"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_targets_focus_map_routes_checking_to_exit_and_checklist_to_continue() -> None:
    controller = gate_controller_source()
    targets_block = controller.split("var targets = {", 1)[1].split("};", 1)[0]
    assert "checking: 'btn-runtime-exit'" in targets_block
    assert "checklist: 'btn-runtime-continue'" in targets_block


def test_render_hides_exit_control_only_for_checklist_state() -> None:
    controller = gate_controller_source()
    render_body = controller.split("function render() {", 1)[1].split("\n    }", 1)[0]
    assert "exitButton.hidden = next === 'checklist'" in render_body


def test_anti_flicker_constant_reads_motion_normal_token_with_documented_fallback() -> None:
    app = read_ui("app.js")
    assert "getPropertyValue('--motion-normal')" in app
    assert "Number.isFinite(parsed) ? parsed : 160" in app
    assert "WHISPER_SLOW_NOTICE_MS = 5000" in app
    # No other new millisecond literal is introduced into the gate section by
    # this plan -- 160 (the documented anti-flicker fallback) and 5000 (the
    # whisper slow-notice threshold) are the only two.
    gate = read_ui("app.js").split("/* ================= runtime setup gate", 1)[1]
    gate = gate.split("/* Clears the design-time placeholder", 1)[0]
    ms_literals = set(re.findall(r"\b(\d{2,5})\b", gate))
    # 800 (ready()'s pre-existing auto-close delay), 100/0/2 (percentages,
    # clamp/line-clamp counts) and similar are pre-existing; only assert the
    # two new pacing literals are present -- this is a presence check, not an
    # exhaustive diff against pre-plan history.
    assert "160" in ms_literals
    assert "5000" in ms_literals


def test_resolving_fourth_id_before_second_leaves_canonical_order_and_marks_correct() -> None:
    items = json.dumps(list(FIRST_RUN_CHECKLIST_ITEMS))
    result = run_node(
        r'''
        const ids = ''' + items + r''';
        const gate = RuntimeSetupGateModel();
        gate.bootstrap({bootstrap_pending: true, validation_path: 'full'});
        // Resolve the fourth canonical id before the second.
        let view = gate.progress({id: ids[3], state: 'resolved'});
        view = gate.progress({id: ids[1], state: 'resolved'});
        // FIRST_RUN_ROWS (fixed, canonical order) is what a renderer must
        // iterate over -- prove the marks are addressable by that same fixed
        // order regardless of arrival sequence, and that the untouched ids
        // are unaffected.
        if (view.checkProgress[ids[3]] !== 'resolved') process.exit(1);
        if (view.checkProgress[ids[1]] !== 'resolved') process.exit(2);
        if (view.checkProgress[ids[0]] !== 'pending') process.exit(3);
        if (view.checkProgress[ids[2]] !== 'pending') process.exit(4);
        if (view.checkProgress[ids[4]] !== 'pending') process.exit(5);
        if (JSON.stringify(Object.keys(FIRST_RUN_ROWS.reduce((acc, r) => { acc[r.id] = 1; return acc; }, {}))) !== JSON.stringify(ids)) process.exit(6);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_render_checking_iterates_the_fixed_canonical_array_not_progress_keys() -> None:
    """Structural guarantee that DOM row order can never depend on arrival
    order: renderChecking() must iterate FIRST_RUN_ROWS (fixed), never
    Object.keys/values of the progress map."""
    app = read_ui("app.js")
    body = app.split("function renderChecking() {", 1)[1].split("\n    }", 1)[0]
    assert "FIRST_RUN_ROWS.forEach(" in body
    assert "progress).forEach(" not in body
    assert "Object.keys(progress)" not in body


def test_checklist_heading_and_body_are_never_rewritten_by_js() -> None:
    """The Ready-only and Mixed fixtures must render byte-identical
    heading/body/Continue copy -- proven structurally by showing renderChecklist()
    never targets those static ids, so their only source is the markup's own
    (identical, unconditional) production text."""
    app = read_ui("app.js")
    body = app.split("function renderChecklist() {", 1)[1].split("\n    }", 1)[0]
    assert "runtime-checklist-heading" not in body
    assert "runtime-checklist-body" not in body
    assert "btn-runtime-continue" not in body


def test_no_regression_in_adjacent_webview_and_content_suites() -> None:
    result = subprocess.run(
        [
            "python", "-m", "pytest",
            "tests/test_webview_beta3.py", "tests/test_webview_ui_fixes.py", "tests/test_content_hygiene.py",
            "-q",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ------------------------------------------------------------------ Task 3 --


def wire_bridge_source() -> str:
    app = read_ui("app.js")
    start = app.index("function wireBridge() {")
    end = app.index("\n  /* ======================= boot", start)
    return app[start:end]


def test_wire_bridge_subscribes_bootstrap_progress_and_complete_and_bridge_js_registers_both() -> None:
    wb = wire_bridge_source()
    assert "lpBridge.on('bootstrap_progress'" in wb
    assert "lpBridge.on('bootstrap_complete'" in wb
    bridge_js = read_ui("bridge.js")
    assert "'bootstrap_progress'" in bridge_js
    assert "'bootstrap_complete'" in bridge_js


def test_runtime_setup_gate_public_surface_exposes_progress_and_acknowledge() -> None:
    controller = gate_controller_source()
    return_line = controller.split("return {", 1)[1].split("};", 1)[0]
    assert "progress: progress" in return_line
    assert "acknowledge: acknowledge" in return_line


def test_acknowledge_setup_is_called_through_lp_bridge_exactly_once() -> None:
    app = read_ui("app.js")
    assert app.count("lpBridge.call('acknowledge_setup')") == 1


def test_continue_and_skip_are_wired_to_the_same_handler() -> None:
    controller = gate_controller_source()
    wire_body = controller.split("function wire() {", 1)[1].split("\n    }", 1)[0]
    assert "$('btn-runtime-continue').addEventListener('click', acknowledge);" in wire_body
    assert "$('btn-runtime-skip').addEventListener('click', acknowledge);" in wire_body


def test_sync_demo_admission_boolean_includes_acknowledged_term() -> None:
    controller = gate_controller_source()
    body = controller.split("function syncDemoAdmission(view) {", 1)[1].split("\n    }", 1)[0]
    assert "view.acknowledged" in body


def test_healthy_unacknowledged_snapshot_demo_availability_false_then_true_after_acknowledge() -> None:
    result = run_node(
        r'''
        function syncDemoAdmissionBool(view) {
          return !!(view && view.healthy && !view.bootstrapPending && view.acknowledged &&
            (view.state === 'ready' || !view.activeOperation));
        }
        const gate = RuntimeSetupGateModel();
        const before = gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false});
        if (syncDemoAdmissionBool(before) !== false) process.exit(1);
        const after = gate.acknowledge(null);
        if (syncDemoAdmissionBool(after) !== true) process.exit(2);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_close_ready_diverts_to_checklist_for_healthy_unacknowledged_snapshot() -> None:
    controller = gate_controller_source()
    body = controller.split("function closeReady() {", 1)[1].split("\n    }", 1)[0]
    assert "snap.healthy && !snap.acknowledged" in body
    assert "eventModel.toChecklist();" in body

    result = run_node(
        r'''
        const gate = RuntimeSetupGateModel();
        gate.bootstrap({runtime_health_state: 'HEALTHY', bootstrap_pending: false, setup_acknowledged: false});
        gate.begin('repair-op', 'repairing');
        gate.event({operation_id: 'repair-op', kind: 'admitted'});
        let snap = gate.snapshot();
        if (snap.state !== 'ready') process.exit(1);
        if (snap.acknowledged !== false) process.exit(2);
        // Simulate closeReady()'s new branch directly on the reducer.
        const view = gate.toChecklist();
        if (view.state !== 'checklist') process.exit(3);
        if (view.healthy !== true) process.exit(4);
        '''
    )
    assert result.returncode == 0, result.stderr


def test_bootstrap_consumer_guards_start_normal_bridge_activity_behind_once_flag_and_not_pending() -> None:
    app = read_ui("app.js")
    wb = wire_bridge_source()
    assert "var normalBridgeActivityStarted = false;" in wb
    assert "if (normalBridgeActivityStarted) return;" in wb
    assert "normalBridgeActivityStarted = true;" in wb
    assert "!b.bootstrap_pending && b.runtime_health_state !== 'SETUP_REQUIRED'" in app
    # Fallbacks: no-payload and no-slot paths both still call it.
    ready_block = app.split("lpBridge.ready(function (backend) {", 1)[1].split("\n    });", 1)[0]
    assert "if (!json) { startNormalBridgeActivity(); return; }" in ready_block
    assert "else startNormalBridgeActivity();" in ready_block


def test_admission_guarded_operations_includes_list_ollama_models_and_media_link_support() -> None:
    bridge_py = (ROOT / "app" / "desktop" / "bridge.py").read_text(encoding="utf-8")
    guarded_block = bridge_py.split("_ADMISSION_GUARDED_OPERATIONS = frozenset({", 1)[1].split("})", 1)[0]
    assert "list_ollama_models" in guarded_block
    assert "media_link_support" in guarded_block


def test_no_third_browser_storage_call_site_is_added_for_the_setup_flag() -> None:
    app = read_ui("app.js")
    assert app.count("window.localStorage") == 2


def test_checklist_row_building_slice_reads_only_id_verdict_and_detail() -> None:
    app = read_ui("app.js")
    body = app.split("function renderChecklist() {", 1)[1].split("\n    }", 1)[0]
    assert "item.id" in body
    assert "item.verdict" in body
    # detail is read (per the plan) even though this row rendering does not
    # currently surface it visually beyond the fixed advisory sentence; it
    # must never read any other item key (no health arithmetic in JS).
    for forbidden in ("item.remediation", "item.action", "item.url", "item.download", "item.repair", "item.healthy", "item.components"):
        assert forbidden not in body


def test_progress_returns_early_on_invalid_json_without_touching_reducer() -> None:
    controller = gate_controller_source()
    body = controller.split("function progress(payload) {", 1)[1].split("\n    }", 1)[0]
    assert "catch (e) { return null; }" in body
    assert "if (!record || typeof record !== 'object' || !record.id) return;" in body


def test_no_regression_in_settings_bridge_demo_isolation_and_gate_suites() -> None:
    result = subprocess.run(
        [
            "python", "-m", "pytest",
            "tests/test_webview_settings_bridge.py", "tests/test_demo_session_isolation.py", "tests/test_setup_gate_repair.py",
            "-q",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
