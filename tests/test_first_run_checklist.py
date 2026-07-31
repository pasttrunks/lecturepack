"""First-run checklist contract: the persisted acknowledgement flag (D-16)
and the five-item verdict service (D-13, D-14).
"""
from __future__ import annotations

import json

from lecturepack.infrastructure.config_manager import ConfigManager


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
