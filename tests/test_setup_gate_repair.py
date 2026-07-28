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
