"""Produce the exact signed runtime assets consumed by Phase 2 repair.

This is deliberately a release-engineering helper, not application runtime
code.  It accepts a complete canonical onedir runtime and writes only the
four fixed ZIPs plus the signed canonical manifest and raw signature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lecturepack.infrastructure.release_trust import _asset_names
from lecturepack.infrastructure.runtime_inventory import RuntimeInventoryError, canonical_inventory, resolve_inventory


_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
_COMPONENT_ORDER = ("ffmpeg", "model-base-en", "smoke-fixture", "whisper-cpu")
_ZIP_DATE = (2026, 1, 1, 0, 0, 0)


def _source_version() -> str:
    text = (REPO_ROOT / "app" / "desktop" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if match is None:
        raise ValueError("application version is unavailable from app/desktop/version.py")
    return match.group(1)


def _require_exact_version(app_version: str) -> None:
    if not isinstance(app_version, str) or not _VERSION_RE.fullmatch(app_version):
        raise ValueError("application version must be the exact unprefixed semantic version")


def _private_key(private_key_hex: str) -> Ed25519PrivateKey:
    if not isinstance(private_key_hex, str) or not re.fullmatch(r"[0-9a-f]{64}", private_key_hex):
        raise ValueError("release signing input must be exactly 64 lowercase hexadecimal characters")
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))


def _component_members(inventory: dict[str, Path]) -> dict[str, tuple[str, ...]]:
    entries = tuple(sorted(inventory))
    groups = {
        "ffmpeg": tuple(entry for entry in entries if entry in {"bin/ffmpeg.exe", "bin/ffprobe.exe"}),
        "model-base-en": tuple(entry for entry in entries if entry == "models/ggml-base.en.bin"),
        "smoke-fixture": tuple(entry for entry in entries if entry == "smoke/runtime-smoke.wav"),
        "whisper-cpu": tuple(
            entry
            for entry in entries
            if entry.startswith("bin/") and entry not in {"bin/ffmpeg.exe", "bin/ffprobe.exe"}
        ),
    }
    if tuple(sorted(member for members in groups.values() for member in members)) != entries:
        raise RuntimeInventoryError("runtime inventory cannot be mapped to the fixed release archive layout")
    if any(not groups[component] for component in _COMPONENT_ORDER):
        raise RuntimeInventoryError("runtime inventory is incomplete for the fixed release archive layout")
    return groups


def _zip_members(destination: Path, runtime_root: Path, members: Iterable[str]) -> None:
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for member in members:
            source = runtime_root / member
            info = zipfile.ZipInfo(member, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_signed_runtime_release(
    *,
    app_version: str,
    runtime_root: Path,
    output_directory: Path,
    private_key_hex: str,
    cpu_dll_names: tuple[str, ...] | list[str] | None = None,
) -> dict[str, object]:
    """Write exactly the authenticated release layout and return safe audit hashes."""
    _require_exact_version(app_version)
    signer = _private_key(private_key_hex)
    root = Path(runtime_root).resolve()
    out = Path(output_directory).resolve()
    if not root.is_dir():
        raise RuntimeInventoryError("canonical runtime root is missing")
    if out.exists() and any(out.iterdir()):
        raise ValueError("output directory must be absent or empty")
    out.mkdir(parents=True, exist_ok=True)

    try:
        inventory = resolve_inventory(
            root,
            canonical_inventory(cpu_dll_names) if cpu_dll_names is not None else None,
        )
    except RuntimeInventoryError:
        raise
    members = _component_members(inventory)
    names = _asset_names(app_version)
    archive_records: list[dict[str, object]] = []
    for component in _COMPONENT_ORDER:
        name = names[component]
        destination = out / name
        _zip_members(destination, root, members[component])
        archive_records.append(
            {
                "component": component,
                "file_name": name,
                "sha256": _sha256(destination),
                "size_bytes": destination.stat().st_size,
            }
        )

    public_key = signer.public_key().public_bytes_raw()
    payload = {
        "app_version": app_version,
        "assets": archive_records,
        "schema_version": 1,
        "signing_key_id": hashlib.sha256(public_key).hexdigest()[:16],
    }
    raw_manifest = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    manifest_name = names["manifest"]
    signature_name = names["signature"]
    (out / manifest_name).write_bytes(raw_manifest)
    (out / signature_name).write_bytes(signer.sign(raw_manifest))

    expected = set(names.values())
    actual = {path.name for path in out.iterdir() if path.is_file()}
    if actual != expected:
        raise RuntimeError("release builder produced an unexpected asset layout")
    return {
        "app_version": app_version,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "signature_sha256": _sha256(out / signature_name),
        "archive_members": members,
        "assets": {path.name: {"sha256": _sha256(path), "size_bytes": path.stat().st_size} for path in sorted(out.iterdir())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build signed fixed-layout LecturePack runtime release assets.")
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--private-key-env", default="LECTUREPACK_RELEASE_ED25519_PRIVATE_KEY_HEX")
    args = parser.parse_args()
    private_key_hex = os.environ.get(args.private_key_env, "")
    if not private_key_hex:
        parser.error(f"required signing input environment variable is unset: {args.private_key_env}")
    audit = build_signed_runtime_release(
        app_version=args.app_version,
        runtime_root=args.runtime_root,
        output_directory=args.output_directory,
        private_key_hex=private_key_hex,
    )
    print(json.dumps(audit, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
