"""Contracts for the single canonical bundled-runtime inventory."""

from pathlib import Path

import pytest

from lecturepack.infrastructure.runtime_inventory import (
    RuntimeInventoryError,
    canonical_inventory,
    payload_identity,
    resolve_inventory,
)


def _make_payload(root: Path) -> None:
    for relative in canonical_inventory(cpu_dll_names=("ggml-cpu-test.dll",)):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload:" + relative.encode("utf-8"))


def test_inventory_is_ordered_relative_and_excludes_optional_engines():
    inventory = canonical_inventory(cpu_dll_names=("ggml-cpu-z.dll", "ggml-cpu-a.dll"))
    assert inventory == tuple(sorted(inventory, key=lambda item: (item.split("/")[0], item)))
    assert "smoke/runtime-smoke.wav" in inventory
    assert not any("cuda" in item.lower() or "vulkan" in item.lower() for item in inventory)
    assert all(not Path(item).is_absolute() and ".." not in Path(item).parts for item in inventory)


def test_resolve_inventory_requires_all_nonempty_files_and_root_containment(tmp_path):
    _make_payload(tmp_path)
    resolved = resolve_inventory(tmp_path)
    assert resolved["smoke/runtime-smoke.wav"] == tmp_path / "smoke" / "runtime-smoke.wav"

    (tmp_path / "bin" / "ffprobe.exe").write_bytes(b"")
    with pytest.raises(RuntimeInventoryError, match="missing or empty"):
        resolve_inventory(tmp_path)


def test_inventory_rejects_traversal_absolute_and_duplicate_entries(tmp_path):
    _make_payload(tmp_path)
    for entries in (("../escape",), ("C:/escape",), ("bin/ffmpeg.exe", "bin/ffmpeg.exe")):
        with pytest.raises(RuntimeInventoryError):
            resolve_inventory(tmp_path, entries=entries)


def test_payload_identity_changes_when_a_required_payload_changes(tmp_path):
    _make_payload(tmp_path)
    first = payload_identity(tmp_path)
    (tmp_path / "models" / "ggml-base.en.bin").write_bytes(b"changed")
    assert payload_identity(tmp_path) != first
