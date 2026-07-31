"""First-run checklist contract: the persisted acknowledgement flag (D-16)
and the five-item verdict service (D-13, D-14).
"""
from __future__ import annotations

import json

import pytest

from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.runtime_inventory import canonical_inventory
from lecturepack.services.first_run_checklist import (
    FIRST_RUN_CHECKLIST_ITEMS,
    VERDICT_NEEDS_ATTENTION,
    VERDICT_READY,
    build_first_run_checklist,
    checklist_group_for,
    data_directory_writable,
    supported_windows_version,
)


# ---------------------------------------------------------------------------
# Task 1: setup_acknowledged / persist_setup_acknowledged
# ---------------------------------------------------------------------------


def test_setup_acknowledged_is_false_on_fresh_profile(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    assert cfg.setup_acknowledged() is False


def test_persist_setup_acknowledged_flips_flag_true_in_memory(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    cfg.persist_setup_acknowledged()
    assert cfg.setup_acknowledged() is True


def test_persist_setup_acknowledged_round_trips_to_disk_via_new_instance(tmp_path):
    """A newly constructed ConfigManager over the same data dir must also read True.

    An in-memory-only check would pass against a broken writer, so this test
    forces a fresh instance to prove the disk round-trip.
    """
    cfg = ConfigManager(str(tmp_path))
    cfg.persist_setup_acknowledged()

    second = ConfigManager(str(tmp_path))
    assert second.setup_acknowledged() is True


def test_persist_setup_acknowledged_writes_valid_json_config(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    cfg.persist_setup_acknowledged()

    with open(cfg.config_path, "r", encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["setup_acknowledged"] is True


def test_persist_setup_acknowledged_preserves_existing_runtime_health(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    runtime_health = {"identity": "payload-v1", "components": {"bin/ffmpeg.exe": {"healthy": True}}}
    cfg.persist_runtime_health(runtime_health, bundled_model="models/ggml-base.en.bin")

    cfg.persist_setup_acknowledged()

    assert cfg.get("runtime_health") == runtime_health


def test_persist_setup_acknowledged_preserves_whisper_model_and_migration_marker(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    cfg.set("whisper_model", "D:/models/manual.bin")
    cfg.settings["migration_versions"] = {"runtime_contract": 1}
    cfg.save()

    cfg.persist_setup_acknowledged()

    assert cfg.get("whisper_model") == "D:/models/manual.bin"
    assert cfg.get("migration_versions") == {"runtime_contract": 1}


def test_persist_setup_acknowledged_is_idempotent(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    cfg.persist_setup_acknowledged()
    cfg.persist_setup_acknowledged()  # must not raise
    assert cfg.setup_acknowledged() is True


def test_setup_acknowledged_returns_false_for_corrupted_non_boolean_value(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    cfg.settings["setup_acknowledged"] = "true"  # hand-edited / corrupted
    cfg.save()

    reloaded = ConfigManager(str(tmp_path))
    assert reloaded.setup_acknowledged() is False


def test_setup_acknowledged_returns_false_for_truthy_int(tmp_path):
    cfg = ConfigManager(str(tmp_path))
    cfg.settings["setup_acknowledged"] = 1
    assert cfg.setup_acknowledged() is False


def test_default_settings_declares_setup_acknowledged_key():
    assert ConfigManager.DEFAULT_SETTINGS["setup_acknowledged"] is False


# ---------------------------------------------------------------------------
# Task 2: first-run checklist verdict service (D-13, D-14)
# ---------------------------------------------------------------------------


def _complete_success_evidence(components):
    """Mirror tests/test_runtime_bootstrap.py's helper shape field-for-field."""
    return {
        key: {
            "healthy": True,
            "reason": "success",
            "exit_code": 0,
            "argv": [key, "-version"],
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
            "timed_out": False,
        }
        for key in components
    }


def _canonical_components_all_healthy():
    entries = canonical_inventory(("ggml-cpu-haswell.dll",))
    return _complete_success_evidence(entries)


def test_first_run_checklist_items_is_exactly_five_in_canonical_order():
    assert len(FIRST_RUN_CHECKLIST_ITEMS) == 5
    assert FIRST_RUN_CHECKLIST_ITEMS == (
        "windows_version",
        "ffmpeg_ffprobe",
        "whisper_runtime",
        "bundled_model",
        "data_directory",
    )


def test_verdict_literals_set_has_exactly_two_members():
    assert {VERDICT_READY, VERDICT_NEEDS_ATTENTION} != {VERDICT_READY}
    assert len({VERDICT_READY, VERDICT_NEEDS_ATTENTION}) == 2


@pytest.mark.parametrize(
    "version_info,expect_supported",
    [
        ((10, 0, 17763), True),
        ((10, 0, 17134), False),
        ((10, 0, 22631), True),
    ],
)
def test_supported_windows_version_injected_tuple(version_info, expect_supported):
    result = supported_windows_version(version_info)
    assert result["supported"] is expect_supported
    assert str(version_info[2]) in result["detail"]


def test_supported_windows_version_none_on_non_windows_reports_platform(monkeypatch):
    monkeypatch.setattr("lecturepack.services.first_run_checklist.sys.platform", "linux")
    result = supported_windows_version(None)
    assert result["supported"] is False
    assert "linux" in result["detail"]


def test_data_directory_writable_reports_writable_and_leaves_no_probe_file(tmp_path):
    before = set(tmp_path.iterdir())
    result = data_directory_writable(tmp_path)
    after = set(tmp_path.iterdir())
    assert result["writable"] is True
    assert before == after


def test_data_directory_writable_reports_false_on_unwritable_path_without_raising(tmp_path):
    blocked = tmp_path / "not_a_directory"
    blocked.write_bytes(b"x")  # a file, not a directory -- mkdir must fail cleanly

    result = data_directory_writable(blocked)

    assert result["writable"] is False
    assert isinstance(result["detail"], str)


def test_build_first_run_checklist_all_healthy_yields_five_ready_items(tmp_path):
    components = _canonical_components_all_healthy()
    items = build_first_run_checklist(
        components, windows_version=(10, 0, 22631), data_dir=tmp_path
    )
    assert len(items) == 5
    assert [item["id"] for item in items] == list(FIRST_RUN_CHECKLIST_ITEMS)
    assert all(item["verdict"] == VERDICT_READY for item in items)


def test_build_first_run_checklist_mixed_windows_only_needs_attention(tmp_path):
    components = _canonical_components_all_healthy()
    items = build_first_run_checklist(
        components, windows_version=(10, 0, 17134), data_dir=tmp_path
    )
    by_id = {item["id"]: item for item in items}
    assert by_id["windows_version"]["verdict"] == VERDICT_NEEDS_ATTENTION
    for item_id in ("ffmpeg_ffprobe", "whisper_runtime", "bundled_model", "data_directory"):
        assert by_id[item_id]["verdict"] == VERDICT_READY


def test_build_first_run_checklist_whisper_dll_failure_isolated_to_whisper_group(tmp_path):
    components = _canonical_components_all_healthy()
    components["bin/whisper.dll"] = {**components["bin/whisper.dll"], "healthy": False, "reason": "smoke failed"}

    items = build_first_run_checklist(components, windows_version=(10, 0, 22631), data_dir=tmp_path)
    by_id = {item["id"]: item for item in items}
    assert by_id["whisper_runtime"]["verdict"] == VERDICT_NEEDS_ATTENTION
    assert by_id["ffmpeg_ffprobe"]["verdict"] == VERDICT_READY


def test_build_first_run_checklist_dynamic_cpu_dll_failure_is_inside_whisper_group(tmp_path):
    components = _canonical_components_all_healthy()
    components["bin/ggml-cpu-haswell.dll"] = {
        **components["bin/ggml-cpu-haswell.dll"], "healthy": False, "reason": "smoke failed",
    }

    items = build_first_run_checklist(components, windows_version=(10, 0, 22631), data_dir=tmp_path)
    by_id = {item["id"]: item for item in items}
    assert by_id["whisper_runtime"]["verdict"] == VERDICT_NEEDS_ATTENTION


def test_build_first_run_checklist_smoke_fixture_failure_is_inside_whisper_group(tmp_path):
    components = _canonical_components_all_healthy()
    components["smoke/runtime-smoke.wav"] = {
        **components["smoke/runtime-smoke.wav"], "healthy": False, "reason": "smoke failed",
    }

    items = build_first_run_checklist(components, windows_version=(10, 0, 22631), data_dir=tmp_path)
    by_id = {item["id"]: item for item in items}
    assert by_id["whisper_runtime"]["verdict"] == VERDICT_NEEDS_ATTENTION


def test_build_first_run_checklist_items_expose_only_id_verdict_detail(tmp_path):
    components = _canonical_components_all_healthy()
    items = build_first_run_checklist(components, windows_version=(10, 0, 22631), data_dir=tmp_path)
    for item in items:
        assert set(item.keys()) == {"id", "verdict", "detail"}


def test_d14_no_item_carries_remediation_action_url_download_or_repair_key(tmp_path):
    components = _canonical_components_all_healthy()
    components["bin/whisper.dll"] = {**components["bin/whisper.dll"], "healthy": False, "reason": "smoke failed"}
    items = build_first_run_checklist(components, windows_version=(10, 0, 17134), data_dir=tmp_path)
    forbidden_keys = {"remediation", "action", "url", "download", "repair"}
    for item in items:
        assert not (set(item.keys()) & forbidden_keys)


def test_build_first_run_checklist_output_is_json_serializable(tmp_path):
    components = _canonical_components_all_healthy()
    items = build_first_run_checklist(components, windows_version=(10, 0, 22631), data_dir=tmp_path)
    serialized = json.dumps(items)
    assert "ready" in serialized


def test_checklist_group_for_covers_every_canonical_inventory_entry_without_raising():
    entries = canonical_inventory(("ggml-cpu-haswell.dll",))
    for entry in entries:
        assert checklist_group_for(entry) in ("ffmpeg_ffprobe", "whisper_runtime", "bundled_model")


def test_checklist_group_for_raises_for_unrecognized_entry():
    with pytest.raises(ValueError):
        checklist_group_for("unknown/entry.exe")
