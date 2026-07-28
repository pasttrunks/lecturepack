"""Contract coverage for the Phase 2 runtime setup and signed-repair gate."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"


def read_ui(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


def test_runtime_setup_overlay_has_the_required_modal_surface() -> None:
    markup = read_ui("index.html")

    assert 'id="runtime-setup-overlay"' in markup
    assert 'role="dialog"' in markup
    assert 'aria-modal="true"' in markup
    assert 'id="runtime-setup-progress"' in markup
    assert 'role="progressbar"' in markup
    assert markup.count('id="runtime-setup-progress"') == 1
    for state in ("gate", "diagnostics", "confirm", "repairing", "offline", "failed", "ready"):
        assert f'data-runtime-state="{state}"' in markup
    assert "@media (max-width:820px)" in markup
    assert "lp-fill" in markup and "scaleX(0)" in markup


def test_repair_event_is_a_registered_ui_bridge_signal() -> None:
    bridge = read_ui("bridge.js")

    assert "'repair_event'" in bridge
    for operation in (
        "beginRuntimeRepairOffer",
        "confirmRuntimeRepair",
        "retryRuntimeAssessment",
        "cancelRuntimeRepair",
        "copyRuntimeRepairDiagnostics",
        "saveRuntimeRepairDiagnostics",
    ):
        assert operation in bridge


def test_gate_uses_canonical_slots_and_authenticated_offer_fields() -> None:
    app = read_ui("app.js")
    bridge = read_ui("bridge.js")

    for slot in (
        "start_runtime_repair",
        "confirm_runtime_repair",
        "cancel_runtime_repair",
        "retry_runtime_assessment",
        "copy_runtime_repair_diagnostics",
        "save_runtime_repair_diagnostics",
    ):
        assert slot in bridge
    for field in (
        "official_source",
        "affected_components",
        "download_size_bytes",
        "metadata_ready",
        "RuntimeSetupGate",
        "runtime_health_state",
    ):
        assert field in app
    gate = app.split("var RuntimeSetupGate", 1)[1].split("/* Clears", 1)[0]
    assert "scaleX(" in gate
    assert "style.width" not in gate
    for control in ("trapFocus", "setUnderlyingInert", "stopImmediatePropagation", "LP.motion.reduced"):
        assert control in gate


def test_executable_reducer_seam_filters_stale_and_terminal_events() -> None:
    """Run the same event filter the browser gate calls, without a new JS dependency."""
    source = read_ui("app.js")
    model = source.split("function RuntimeSetupGateModel()", 1)[1].split("var RuntimeSetupGate", 1)[0]
    program = "function RuntimeSetupGateModel()" + model + "\n" + r'''
      const gate = RuntimeSetupGateModel(), offer = {operation_id:'current',app_version:'v',source:'official',affected_components:'Media tools',download_size_bytes:4};
      gate.begin('current'); if (gate.offer(offer) !== 'confirm') process.exit(1);
      if (gate.confirm() !== 'repairing') process.exit(2);
      gate.event({operation_id:'current',kind:'cancel_requested'}); if (!gate.snapshot().cancelling) process.exit(3);
      if (gate.event({operation_id:'current',kind:'cancelled'}) !== 'gate') process.exit(4);
      gate.begin('offline'); if (gate.event({operation_id:'offline',kind:'failed',classification:'offline'}) !== 'offline') process.exit(5);
      gate.begin('failed'); if (gate.event({operation_id:'failed',kind:'failed'}) !== 'failed') process.exit(6);
      gate.diagnostics(); if (gate.back() !== 'failed') process.exit(7);
      gate.begin('ready'); if (gate.event({operation_id:'stale',kind:'admitted'}) !== 'gate') process.exit(8);
      if (gate.event({operation_id:'ready',kind:'admitted'}) !== 'ready') process.exit(9);
      if (gate.accept({operation_id:'ready',kind:'admitted'})) process.exit(10);
      gate.begin('retry'); if (!gate.retry() || !gate.snapshot().retryPending) process.exit(11);
    '''
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_gate_audit_contract_covers_inert_focus_offline_and_diagnostics_feedback() -> None:
    app = read_ui("app.js")
    markup = read_ui("index.html")

    assert "if (inertCaptured) return" in app
    assert "classification === 'offline'" in app
    assert "Could not copy details." in app and "Could not save report." in app
    assert "bootstrapPending = true" in app and "beginBootstrap" in app
    for target in ("btn-runtime-repair", "btn-runtime-confirm", "btn-runtime-cancel", "btn-runtime-offline-retry", "btn-runtime-failed-retry", "runtime-diagnostics-heading", "runtime-ready-heading"):
        assert target in app
    assert "overflow-wrap:anywhere" in app and "-webkit-line-clamp:2" in app
    assert 'aria-live="assertive"' in markup and 'aria-live="polite"' in markup
