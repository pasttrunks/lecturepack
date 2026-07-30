"""Fail-closed trust policy for the signed exact-version runtime release.

This module deliberately has no Qt, filesystem mutation, archive extraction, or
network code.  A later repair transaction may use its authenticated metadata,
but only after this module accepts the exact downloaded manifest bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Iterable, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


RELEASE_PUBLIC_KEY_HEX = "b15b321dc50d9e2cb4b59898361f7b58278f676f3cabf11d18d383b61c6c04e3"
_SCHEMA_VERSION = 1
_MAX_U64 = (1 << 64) - 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMPONENTS = ("ffmpeg", "model-base-en", "smoke-fixture", "whisper-cpu")


class ReleaseTrustError(ValueError):
    """Raised whenever release metadata cannot establish the locked trust contract."""


@dataclass(frozen=True)
class ReleaseAsset:
    component: str
    file_name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ReleaseManifest:
    schema_version: int
    app_version: str
    signing_key_id: str
    archives: tuple[ReleaseAsset, ...]
    raw_bytes: bytes

    @property
    def download_size_bytes(self) -> int:
        total = 0
        for archive in self.archives:
            if archive.size_bytes > _MAX_U64 - total:
                raise ReleaseTrustError("archive download size overflows unsigned 64-bit total")
            total += archive.size_bytes
        return total


@dataclass(frozen=True)
class ReleaseLayout:
    """Exact permitted archive-member mapping for one application version."""

    app_version: str
    archive_members: Mapping[str, tuple[str, ...]]

    def validate_inventory(self, inventory: Iterable[str]) -> None:
        expected = tuple(inventory)
        _validate_members(expected)
        members = tuple(member for values in self.archive_members.values() for member in values)
        _validate_members(members)
        if set(members) != set(expected) or len(members) != len(expected):
            raise ReleaseTrustError("release layout does not exactly match canonical runtime inventory")


@dataclass(frozen=True)
class AuthenticatedOffer:
    app_version: str
    affected_components: tuple[str, ...]
    archives: tuple[ReleaseAsset, ...]
    download_size_bytes: int


def _asset_names(app_version: str) -> dict[str, str]:
    if not isinstance(app_version, str) or not app_version:
        raise ReleaseTrustError("application version is required")
    prefix = f"LecturePack-{app_version}-Runtime"
    return {
        "manifest": f"{prefix}Manifest-v1.json",
        "signature": f"{prefix}Manifest-v1.json.sig",
        "ffmpeg": f"{prefix}-ffmpeg.zip",
        "model-base-en": f"{prefix}-model-base-en.zip",
        "smoke-fixture": f"{prefix}-smoke-fixture.zip",
        "whisper-cpu": f"{prefix}-whisper-cpu.zip",
    }


def official_release_urls(app_version: str) -> dict[str, str]:
    """Return the only allowed exact-version metadata and archive URLs."""
    base = f"https://github.com/pasttrunks/lecturepack/releases/download/v{app_version}/"
    return {name: base + name for name in _asset_names(app_version).values()}


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ReleaseTrustError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _require_exact_fields(value: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ReleaseTrustError(f"{label} fields are not the locked schema")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ReleaseTrustError(f"{label} must be a string")
    return value


def _require_uint(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > _MAX_U64:
        raise ReleaseTrustError(f"{label} must be an unsigned 64-bit integer")
    return value


def _validate_members(members: Iterable[str]) -> None:
    selected = tuple(members)
    lowered: set[str] = set()
    for member in selected:
        if not isinstance(member, str) or not member:
            raise ReleaseTrustError("archive member must be a non-empty path")
        posix = PurePosixPath(member)
        windows = PureWindowsPath(member)
        if "\\" in member or posix.is_absolute() or windows.is_absolute() or ".." in posix.parts:
            raise ReleaseTrustError(f"unsafe archive member path: {member!r}")
        lowered_member = member.lower()
        if lowered_member in lowered:
            raise ReleaseTrustError(f"duplicate or case-colliding archive member: {member!r}")
        lowered.add(lowered_member)


class ReleaseTrustVerifier:
    """Authenticate and strictly parse one application's release manifest."""

    def __init__(self, app_version: str, public_key_hex: str = RELEASE_PUBLIC_KEY_HEX) -> None:
        if not isinstance(public_key_hex, str) or not re.fullmatch(r"[0-9a-f]{64}", public_key_hex):
            raise ReleaseTrustError("compiled release public key must be 64 lowercase hexadecimal characters")
        try:
            raw_public_key = bytes.fromhex(public_key_hex)
            self._public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
        except (TypeError, ValueError) as exc:
            raise ReleaseTrustError("compiled release public key is invalid") from exc
        self._app_version = _require_string(app_version, "application version")
        self._key_id = hashlib.sha256(raw_public_key).hexdigest()[:16]

    def verify_manifest(self, raw_manifest: bytes, raw_signature: bytes) -> ReleaseManifest:
        """Verify exact received bytes before canonical JSON parsing."""
        if not isinstance(raw_manifest, bytes):
            raise ReleaseTrustError("manifest must be received as raw bytes")
        if not isinstance(raw_signature, bytes) or len(raw_signature) != 64:
            raise ReleaseTrustError("detached signature must be exactly 64 raw bytes")
        try:
            self._public_key.verify(raw_signature, raw_manifest)
        except InvalidSignature as exc:
            raise ReleaseTrustError("manifest signature verification failed") from exc

        try:
            decoded = raw_manifest.decode("utf-8")
            parsed = json.loads(decoded, object_pairs_hook=_reject_duplicate_pairs)
        except (UnicodeDecodeError, json.JSONDecodeError, ReleaseTrustError) as exc:
            raise ReleaseTrustError("manifest is not strict UTF-8 JSON") from exc
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if raw_manifest != canonical:
            raise ReleaseTrustError("manifest bytes are not canonical JSON")

        root = _require_exact_fields(parsed, {"schema_version", "app_version", "signing_key_id", "assets"}, "manifest")
        if root["schema_version"] != _SCHEMA_VERSION:
            raise ReleaseTrustError("unsupported manifest schema")
        if root["app_version"] != self._app_version:
            raise ReleaseTrustError("manifest application version does not match running application")
        if root["signing_key_id"] != self._key_id:
            raise ReleaseTrustError("manifest signing key id does not match compiled key")
        assets = root["assets"]
        if not isinstance(assets, list) or len(assets) != len(_COMPONENTS):
            raise ReleaseTrustError("manifest must contain exactly the four runtime archives")

        expected_names = _asset_names(self._app_version)
        records: list[ReleaseAsset] = []
        for item in assets:
            asset = _require_exact_fields(item, {"component", "file_name", "sha256", "size_bytes"}, "asset")
            component = _require_string(asset["component"], "asset component")
            file_name = _require_string(asset["file_name"], "asset file name")
            digest = _require_string(asset["sha256"], "asset sha256")
            size_bytes = _require_uint(asset["size_bytes"], "asset size")
            if component not in _COMPONENTS or file_name != expected_names[component]:
                raise ReleaseTrustError("manifest archive name or component is not in the exact release layout")
            if not _SHA256_RE.fullmatch(digest):
                raise ReleaseTrustError("asset sha256 must be lowercase hexadecimal")
            if size_bytes == 0:
                raise ReleaseTrustError("asset size must be non-zero")
            records.append(ReleaseAsset(component, file_name, digest, size_bytes))
        if tuple(record.component for record in records) != tuple(sorted(_COMPONENTS)):
            raise ReleaseTrustError("manifest assets are not canonically sorted by component")
        if len({record.file_name for record in records}) != len(records):
            raise ReleaseTrustError("manifest contains duplicate archive names")
        manifest = ReleaseManifest(_SCHEMA_VERSION, self._app_version, self._key_id, tuple(records), raw_manifest)
        _ = manifest.download_size_bytes
        return manifest

    def authenticated_offer(
        self, manifest: ReleaseManifest, admission_evidence: Mapping[str, str]
    ) -> AuthenticatedOffer:
        """Derive confirmation data from verified metadata and admission evidence only."""
        if not isinstance(manifest, ReleaseManifest) or manifest.app_version != self._app_version:
            raise ReleaseTrustError("authenticated offer requires this verifier's manifest")
        if not isinstance(admission_evidence, Mapping):
            raise ReleaseTrustError("admission evidence must be a component mapping")
        labels = {_require_string(label, "affected component label") for label in admission_evidence.values()}
        return AuthenticatedOffer(
            app_version=manifest.app_version,
            affected_components=tuple(sorted(labels)),
            archives=manifest.archives,
            download_size_bytes=manifest.download_size_bytes,
        )

    def validate_archive_members(
        self, component: str, members: Iterable[str], expected_members: Iterable[str]
    ) -> None:
        """Reject traversal, duplicate, bomb-like, or inventory-drift member lists."""
        if component not in _COMPONENTS:
            raise ReleaseTrustError("unknown runtime archive component")
        received = tuple(members)
        expected = tuple(expected_members)
        if len(received) > 32:
            raise ReleaseTrustError("archive member count exceeds fixed layout bound")
        _validate_members(received)
        _validate_members(expected)
        if received != expected:
            raise ReleaseTrustError("archive members do not exactly match the signed release layout")
