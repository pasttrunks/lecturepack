"""Writable, transactional runtime generations for signed repair.

The portable onedir is deliberately never a transaction target.  A repaired
payload is constructed below the application data directory and becomes usable
only when one small, same-directory ``active.json`` pointer is published.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat
import uuid
import zipfile
from typing import Callable, Iterable, Mapping

from lecturepack.infrastructure.runtime_inventory import RuntimeInventoryError, resolve_inventory


class GenerationError(ValueError):
    """Raised when an untrusted generation cannot be safely accepted."""


class GenerationCancelled(GenerationError):
    """Raised before the atomic active-pointer boundary is crossed."""


@dataclass(frozen=True)
class ActiveGeneration:
    generation_id: str
    root: Path


@dataclass(frozen=True)
class RuntimeRootResolution:
    root: Path | None
    source: str | None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.root is not None


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"invalid runtime state file: {path.name}") from exc
    if not isinstance(value, dict):
        raise GenerationError(f"invalid runtime state file: {path.name}")
    return value


def _safe_member(name: str) -> bool:
    posix, windows = PurePosixPath(name), PureWindowsPath(name)
    return bool(name and "/" in name and "\\" not in name and not posix.is_absolute()
                and not windows.is_absolute() and ".." not in posix.parts and not name.endswith("/"))


def safe_extract_verified_archive(
    archive_path: Path | str,
    staging_root: Path | str,
    *,
    expected_members: Iterable[str],
    expected_hashes: Mapping[str, str],
    max_compressed_bytes: int = 512 * 1024 * 1024,
    max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024,
) -> dict[str, Path]:
    """Stream one strict archive into private staging without ``extractall``."""
    archive_path, root = Path(archive_path), Path(staging_root)
    expected = tuple(expected_members)
    if set(expected) != set(expected_hashes) or len(expected) != len(set(expected)):
        raise GenerationError("archive hash mapping does not match expected members")
    if any(not _safe_member(member) for member in expected):
        raise GenerationError("expected archive member is unsafe")
    lowered = {member.lower() for member in expected}
    if len(lowered) != len(expected):
        raise GenerationError("expected archive members case-collide")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            names = tuple(info.filename for info in infos)
            if (len(names) != len(set(names)) or any(not _safe_member(name) for name in names)
                    or names != expected or {name.lower() for name in names} != lowered):
                raise GenerationError("archive members are not the exact safe release layout")
            if any(info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) for info in infos):
                raise GenerationError("archive contains a directory or link")
            compressed = sum(info.compress_size for info in infos)
            uncompressed = sum(info.file_size for info in infos)
            if compressed > max_compressed_bytes or uncompressed > max_uncompressed_bytes:
                raise GenerationError("archive exceeds configured extraction limits")
            extracted: dict[str, Path] = {}
            root_resolved = root.resolve()
            for info in infos:
                destination = (root / info.filename).resolve()
                if root_resolved not in destination.parents:
                    raise GenerationError("archive member escapes staging root")
                destination.parent.mkdir(parents=True, exist_ok=True)
                digest = sha256()
                with archive.open(info, "r") as source, destination.open("xb") as target:
                    while chunk := source.read(64 * 1024):
                        digest.update(chunk)
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                if digest.hexdigest() != expected_hashes[info.filename]:
                    destination.unlink(missing_ok=True)
                    raise GenerationError(f"archive member hash mismatch: {info.filename}")
                extracted[info.filename] = destination
            return extracted
    except (OSError, zipfile.BadZipFile) as exc:
        raise GenerationError("runtime archive could not be safely extracted") from exc


class RuntimeGenerationStore:
    """Journaled active-pointer storage rooted in writable application data."""

    _SCHEMA_VERSION = 1

    def __init__(self, writable_root: Path | str) -> None:
        self.root = Path(writable_root) / "runtime-generations"
        self.generations = self.root / "generations"
        self.active_path = self.root / "active.json"
        self.journal_path = self.root / "repair-journal.json"

    def _pointer(self, generation_id: str) -> dict[str, object]:
        return {"schema_version": self._SCHEMA_VERSION, "generation_id": generation_id}

    def _parse_pointer(self, payload: Mapping[str, object]) -> ActiveGeneration:
        if set(payload) != {"schema_version", "generation_id"} or payload.get("schema_version") != self._SCHEMA_VERSION:
            raise GenerationError("active pointer schema is invalid")
        generation_id = payload.get("generation_id")
        if not isinstance(generation_id, str) or not generation_id or Path(generation_id).name != generation_id:
            raise GenerationError("active pointer generation is invalid")
        root = (self.generations / generation_id).resolve()
        if self.generations.resolve() not in root.parents:
            raise GenerationError("active pointer escapes generation store")
        try:
            resolve_inventory(root)
        except RuntimeInventoryError as exc:
            raise GenerationError(f"active generation is incomplete: {exc}") from exc
        return ActiveGeneration(generation_id, root)

    def read_active(self) -> ActiveGeneration | None:
        if not self.active_path.exists():
            return None
        return self._parse_pointer(_read_json(self.active_path))

    def _restore(self, previous: Mapping[str, object] | None) -> None:
        if previous is None:
            self.active_path.unlink(missing_ok=True)
        else:
            _write_json_atomic(self.active_path, previous)

    def recover(self) -> ActiveGeneration | None:
        """Restore an interrupted transaction's prior pointer, idempotently."""
        if not self.journal_path.exists():
            return self.read_active()
        journal = _read_json(self.journal_path)
        if set(journal) != {"schema_version", "state", "previous"} or journal.get("schema_version") != self._SCHEMA_VERSION:
            raise GenerationError("repair journal schema is invalid")
        previous = journal["previous"]
        if previous is not None and not isinstance(previous, dict):
            raise GenerationError("repair journal previous pointer is invalid")
        self._restore(previous)
        self.journal_path.unlink(missing_ok=True)
        return self.read_active()

    def publish_from_directory(
        self,
        source_paths: Mapping[str, Path],
        *,
        admit: Callable[[Path], bool],
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> ActiveGeneration:
        """Copy a complete source payload, prove it, then atomically activate it."""
        if self.journal_path.exists():
            self.recover()
        previous = _read_json(self.active_path) if self.active_path.exists() else None
        if cancellation_requested and cancellation_requested():
            raise GenerationCancelled("repair cancelled before activation")
        generation_id = uuid.uuid4().hex
        staging = self.generations / f".{generation_id}.staging"
        final = self.generations / generation_id
        try:
            staging.mkdir(parents=True, exist_ok=False)
            for entry, source in source_paths.items():
                destination = (staging / entry).resolve()
                if staging.resolve() not in destination.parents:
                    raise GenerationError("runtime source entry escapes staging")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with Path(source).open("rb") as input_handle, destination.open("xb") as output_handle:
                    shutil.copyfileobj(input_handle, output_handle, 64 * 1024)
                    output_handle.flush()
                    os.fsync(output_handle.fileno())
            resolve_inventory(staging)
            if not admit(staging):
                raise RuntimeError("admission rejected staged runtime")
            if cancellation_requested and cancellation_requested():
                raise GenerationCancelled("repair cancelled before activation")
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, final)
            _write_json_atomic(self.journal_path, {"schema_version": self._SCHEMA_VERSION, "state": "activating", "previous": previous})
            _write_json_atomic(self.active_path, self._pointer(generation_id))
            if not admit(final):
                raise RuntimeError("admission rejected active runtime")
            self.journal_path.unlink(missing_ok=True)
            return ActiveGeneration(generation_id, final)
        except Exception:
            if self.journal_path.exists():
                self._restore(previous)
                self.journal_path.unlink(missing_ok=True)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)


def resolve_active_runtime_root(config_manager) -> RuntimeRootResolution:
    """Resolve the sole admissible runtime root without silently bypassing damage."""
    bundle = Path(config_manager.resource_dir)
    try:
        writable = config_manager.resolve_data_dir()
        store = RuntimeGenerationStore(writable)
        if store.journal_path.exists():
            return RuntimeRootResolution(None, None, "repair journal requires recovery")
        active = store.read_active()
        if active is not None:
            return RuntimeRootResolution(active.root, "generation")
        if store.active_path.exists():
            return RuntimeRootResolution(None, None, "active pointer is invalid")
        return RuntimeRootResolution(bundle, "bundle")
    except (GenerationError, OSError) as exc:
        return RuntimeRootResolution(None, None, str(exc))
