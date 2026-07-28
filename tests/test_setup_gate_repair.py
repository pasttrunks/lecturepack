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


def test_executable_reducer_seam_covers_the_authoritative_gate_lifecycle() -> None:
    """Execute the exact reducer the DOM controller renders from, without a JS dependency."""
    source = read_ui("app.js")
    model = source.split("function RuntimeSetupGateModel()", 1)[1].split("var RuntimeSetupGate", 1)[0]
    program = "function RuntimeSetupGateModel()" + model + "\n" + r'''
      const gate = RuntimeSetupGateModel();
      const fail = (n) => process.exit(n);
      const state = () => gate.snapshot().state;
      const offer = (id) => ({operation_id:id,app_version:'v',source:'official',affected_components:'Media tools',download_size_bytes:4});

      gate.bootstrap({runtime_health_state:'SETUP_REQUIRED'}); if (state() !== 'gate' || gate.snapshot().bootstrapPending) fail(1);
      gate.bootstrap({runtime_health_state:'HEALTHY'}); if (!gate.snapshot().healthy) fail(2);

      gate.begin('confirm'); if (state() !== 'gate') fail(3);
      gate.event({operation_id:'confirm',kind:'metadata_ready',offer:offer('confirm')}); if (state() !== 'confirm') fail(4);
      gate.confirm(); if (state() !== 'repairing') fail(5);
      gate.event({operation_id:'confirm',kind:'progress'}); gate.event({operation_id:'confirm',kind:'retrying'}); gate.event({operation_id:'confirm',kind:'activated'});
      if (state() !== 'repairing') fail(6);
      gate.event({operation_id:'confirm',kind:'cancel_requested'}); if (!gate.snapshot().cancelPending) fail(7);
      gate.event({operation_id:'confirm',kind:'cancelled'}); if (state() !== 'gate' || !gate.snapshot().terminal) fail(8);

      gate.begin('retry', 'repairing'); if (state() !== 'repairing') fail(9);
      gate.retry(); if (!gate.snapshot().retryPending) fail(10);
      gate.retryResult({runtime_health_state:'SETUP_REQUIRED'}); if (gate.snapshot().retryPending) fail(11);

      gate.begin('offline'); gate.event({operation_id:'offline',kind:'failed',classification:'offline'}); if (state() !== 'offline') fail(12);
      gate.begin('failed'); gate.event({operation_id:'failed',kind:'failed'}); if (state() !== 'failed') fail(13);
      gate.diagnostics(); if (state() !== 'diagnostics') fail(14);
      gate.back(); if (state() !== 'failed') fail(15);

      gate.begin('ready'); gate.event({operation_id:'stale',kind:'admitted'}); if (state() !== 'gate') fail(16);
      gate.event({operation_id:'ready',kind:'admitted'}); if (state() !== 'ready' || !gate.snapshot().terminal) fail(17);
      gate.event({operation_id:'ready',kind:'failed'}); if (state() !== 'ready') fail(18);
      if (gate.accept({operation_id:'ready',kind:'admitted'})) fail(19);
    '''
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_gate_audit_contract_covers_inert_focus_offline_and_diagnostics_feedback() -> None:
    app = read_ui("app.js")
    markup = read_ui("index.html")

    assert "if (inertCaptured) return" in app
    assert "isNormalFocusable(candidate)" in app and "fallbackFocus" in app
    assert "classification === 'offline'" in app
    assert "Could not copy details." in app and "Could not save report." in app
    assert "bootstrapPending = true" in app and "beginBootstrap" in app
    for target in ("btn-runtime-repair", "btn-runtime-confirm", "btn-runtime-cancel", "btn-runtime-offline-retry", "btn-runtime-failed-retry", "runtime-diagnostics-heading", "runtime-ready-heading"):
        assert target in app
    assert "overflow-wrap:anywhere" in app and "-webkit-line-clamp:2" in app
    assert 'aria-live="assertive"' in markup and 'aria-live="polite"' in markup


def test_dom_controller_renders_the_same_model_that_node_executes() -> None:
    app = read_ui("app.js")
    controller = app.split("var RuntimeSetupGate =", 1)[1].split("/* Clears", 1)[0]

    assert "var state =" not in controller
    assert "var returnState =" not in controller
    assert "var activeOperation =" not in controller
    assert "var terminal =" not in controller
    assert "var offer =" not in controller
    assert "var retryPending =" not in controller
    assert "var cancelPending =" not in controller
    assert "eventModel.snapshot()" in controller
    for transition in ("bootstrap(", "begin(", "confirm()", "diagnostics()", "back()", "retry()", "retryResult(", "requestCancel()", "event("):
        assert transition in controller
