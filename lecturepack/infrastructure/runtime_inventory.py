"""Canonical definition of the bundled CPU runtime payload."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Iterable

class RuntimeInventoryError(ValueError):
    """Raised when a runtime payload entry is unsafe or unavailable."""

_STATIC_ENTRIES = ("bin/ffmpeg.exe", "bin/ffprobe.exe", "bin/ggml-base.dll", "bin/ggml.dll", "bin/whisper-cli.exe", "bin/whisper.dll", "models/ggml-base.en.bin", "smoke/runtime-smoke.wav")

def _validate_entries(entries: Iterable[str]) -> tuple[str, ...]:
    result = tuple(entries)
    if len(result) != len(set(result)):
        raise RuntimeInventoryError("duplicate runtime inventory entry")
    for entry in result:
        path = PureWindowsPath(entry)
        if not entry or path.is_absolute() or ".." in path.parts or "\\" in entry:
            raise RuntimeInventoryError(f"unsafe runtime inventory entry: {entry!r}")
    return result

def canonical_inventory(cpu_dll_names: Iterable[str] = ()) -> tuple[str, ...]:
    """Return the ordered, bundle-relative CPU runtime inventory."""
    names = tuple(cpu_dll_names)
    if any(not name.startswith("ggml-cpu-") or not name.endswith(".dll") for name in names):
        raise RuntimeInventoryError("CPU runtime DLL names must match ggml-cpu-*.dll")
    entries = _validate_entries(_STATIC_ENTRIES + tuple(f"bin/{name}" for name in sorted(names)))
    return tuple(sorted(entries, key=lambda item: (item.split("/")[0], item)))

def inventory_for_root(root: Path) -> tuple[str, ...]:
    """Resolve the CPU DLL portion from a concrete runtime root."""
    return canonical_inventory(path.name for path in (Path(root) / "bin").glob("ggml-cpu-*.dll"))

def resolve_inventory(root: Path, entries: Iterable[str] | None = None) -> dict[str, Path]:
    """Validate and resolve every required payload file beneath ``root``."""
    root = Path(root).resolve()
    selected = _validate_entries(entries if entries is not None else inventory_for_root(root))
    resolved: dict[str, Path] = {}
    for entry in selected:
        path = (root / entry).resolve()
        if root not in path.parents:
            raise RuntimeInventoryError(f"runtime inventory path escapes root: {entry!r}")
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeInventoryError(f"missing or empty required runtime payload: {entry}")
        resolved[entry] = path
    if not any(entry.startswith("bin/ggml-cpu-") for entry in selected):
        raise RuntimeInventoryError("missing CPU backend DLLs: bin/ggml-cpu-*.dll")
    return resolved

def payload_identity(root: Path) -> str:
    """Return a deterministic SHA-256 identity for the canonical payload."""
    digest = sha256()
    for entry, path in resolve_inventory(root).items():
        digest.update(entry.encode("utf-8")); digest.update(b"\0")
        digest.update(sha256(path.read_bytes()).digest())
    return digest.hexdigest()
