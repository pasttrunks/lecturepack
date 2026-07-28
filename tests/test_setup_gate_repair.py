"""Contract coverage for the Phase 2 runtime setup and signed-repair gate."""

from pathlib import Path


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
