"""Transactional writable-runtime generation contracts."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import zipfile

import pytest

from lecturepack.infrastructure.runtime_inventory import canonical_inventory


def _payload(root: Path, *, marker: bytes = b"runtime") -> dict[str, Path]:
    """Create the smallest complete canonical payload, including a CPU DLL."""
    paths: dict[str, Path] = {}
    for entry in canonical_inventory(("ggml-cpu-test.dll",)):
        path = root / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(marker + entry.encode("ascii"))
        paths[entry] = path
    return paths


def _archive(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    return path


def _config(bundle_root: Path, writable_root: Path):
    return type(
        "Config",
        (),
        {"resource_dir": bundle_root, "resolve_data_dir": lambda self: str(writable_root)},
    )()


def test_absent_pointer_uses_immutable_bundle_but_malformed_state_fails_closed(tmp_path: Path) -> None:
    from lecturepack.infrastructure.runtime_generation import resolve_active_runtime_root

    bundle = tmp_path / "portable bundle"
    writable = tmp_path / "profile data"
    _payload(bundle)
    config = _config(bundle, writable)

    absent = resolve_active_runtime_root(config)
    assert absent.ok is True
    assert absent.source == "bundle"
    assert absent.root == bundle

    state_dir = writable / "runtime-generations"
    state_dir.mkdir(parents=True)
    (state_dir / "active.json").write_text("{not json", encoding="utf-8")
    malformed = resolve_active_runtime_root(config)
    assert malformed.ok is False
    assert malformed.root is None
    assert "active" in malformed.reason.lower()


@pytest.mark.parametrize("member", ("../escape.exe", "bin/FFMPEG.EXE", "folder/"))
def test_safe_extract_rejects_unsafe_or_noncanonical_members(tmp_path: Path, member: str) -> None:
    from lecturepack.infrastructure.runtime_generation import GenerationError, safe_extract_verified_archive

    archive = _archive(tmp_path / "bad.zip", {member: b"bad"})
    with pytest.raises(GenerationError):
        safe_extract_verified_archive(
            archive,
            tmp_path / "staging",
            expected_members=("bin/ffmpeg.exe",),
            expected_hashes={"bin/ffmpeg.exe": sha256(b"good").hexdigest()},
        )


def test_safe_extract_streams_exact_hashed_members_without_extractall(tmp_path: Path) -> None:
    from lecturepack.infrastructure.runtime_generation import safe_extract_verified_archive

    contents = b"ffmpeg bytes"
    archive = _archive(tmp_path / "ffmpeg.zip", {"bin/ffmpeg.exe": contents})
    extracted = safe_extract_verified_archive(
        archive,
        tmp_path / "generation staging",
        expected_members=("bin/ffmpeg.exe",),
        expected_hashes={"bin/ffmpeg.exe": sha256(contents).hexdigest()},
    )

    assert extracted == {"bin/ffmpeg.exe": tmp_path / "generation staging" / "bin" / "ffmpeg.exe"}
    assert extracted["bin/ffmpeg.exe"].read_bytes() == contents


def test_publish_is_atomic_and_restores_previous_pointer_after_post_activation_failure(tmp_path: Path) -> None:
    from lecturepack.infrastructure.runtime_generation import RuntimeGenerationStore

    bundle = tmp_path / "bundle"
    writable = tmp_path / "writable root"
    _payload(bundle, marker=b"bundle-")
    store = RuntimeGenerationStore(writable)
    previous = store.publish_from_directory(_payload(tmp_path / "old source", marker=b"old-"), admit=lambda root: True)
    previous_bytes = {path.relative_to(previous.root).as_posix(): path.read_bytes() for path in previous.root.rglob("*") if path.is_file()}

    with pytest.raises(RuntimeError, match="admission"):
        store.publish_from_directory(_payload(tmp_path / "new source", marker=b"new-"), admit=lambda root: False)

    active = store.read_active()
    assert active is not None
    assert active.generation_id == previous.generation_id
    assert {path.relative_to(previous.root).as_posix(): path.read_bytes() for path in previous.root.rglob("*") if path.is_file()} == previous_bytes


def test_first_install_failure_leaves_no_pointer_and_cancel_before_boundary_is_idempotent(tmp_path: Path) -> None:
    from lecturepack.infrastructure.runtime_generation import GenerationCancelled, RuntimeGenerationStore

    store = RuntimeGenerationStore(tmp_path / "writable")
    source = _payload(tmp_path / "source")
    with pytest.raises(GenerationCancelled):
        store.publish_from_directory(source, admit=lambda root: True, cancellation_requested=lambda: True)
    assert store.read_active() is None
    assert store.recover() is None
    assert store.recover() is None


def test_interrupted_journal_or_pointer_never_falls_back_to_bundle(tmp_path: Path) -> None:
    from lecturepack.infrastructure.runtime_generation import resolve_active_runtime_root

    bundle = tmp_path / "bundle"
    writable = tmp_path / "profile"
    _payload(bundle)
    state_dir = writable / "runtime-generations"
    state_dir.mkdir(parents=True)
    (state_dir / "repair-journal.json").write_text(json.dumps({"schema_version": 1, "state": "activating"}), encoding="utf-8")

    resolved = resolve_active_runtime_root(_config(bundle, writable))
    assert resolved.ok is False
    assert resolved.root is None
    assert "journal" in resolved.reason.lower()
