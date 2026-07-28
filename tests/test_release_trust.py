"""Frozen trust-root contract for the signed exact-version runtime release."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lecturepack.infrastructure.release_trust import (
    RELEASE_PUBLIC_KEY_HEX,
    ReleaseTrustError,
    ReleaseTrustVerifier,
    official_release_urls,
)


FIXTURES = Path(__file__).parent / "fixtures" / "release_trust"
APP_VERSION = "0.9.0-beta.6"
EXPECTED_ARCHIVES = {
    "LecturePack-0.9.0-beta.6-Runtime-ffmpeg.zip",
    "LecturePack-0.9.0-beta.6-Runtime-whisper-cpu.zip",
    "LecturePack-0.9.0-beta.6-Runtime-model-base-en.zip",
    "LecturePack-0.9.0-beta.6-Runtime-smoke-fixture.zip",
}


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _signed_variant(mutator=None, *, raw: bytes | None = None):
    """Create an ephemeral signer only to exercise post-authentication rejection."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    payload = json.loads(_bytes("manifest.json"))
    payload["signing_key_id"] = hashlib.sha256(public_key).hexdigest()[:16]
    if mutator is not None:
        mutator(payload)
    manifest = raw or json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ReleaseTrustVerifier(APP_VERSION, public_key.hex()), manifest, private_key.sign(manifest)


def test_frozen_manifest_authenticates_before_parsing_and_altered_byte_fails() -> None:
    verifier = ReleaseTrustVerifier(APP_VERSION)
    manifest = verifier.verify_manifest(_bytes("manifest.json"), _bytes("manifest.sig"))

    assert RELEASE_PUBLIC_KEY_HEX == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert manifest.app_version == APP_VERSION
    with pytest.raises(ReleaseTrustError):
        verifier.verify_manifest(_bytes("manifest-altered.json"), _bytes("manifest.sig"))


def test_exact_six_asset_layout_and_checked_archive_total() -> None:
    layout = json.loads(_bytes("release-layout.json"))
    verifier = ReleaseTrustVerifier(APP_VERSION)
    manifest = verifier.verify_manifest(_bytes("manifest.json"), _bytes("manifest.sig"))

    urls = official_release_urls(APP_VERSION)
    assert set(urls) == {
        "LecturePack-0.9.0-beta.6-RuntimeManifest-v1.json",
        "LecturePack-0.9.0-beta.6-RuntimeManifest-v1.json.sig",
        *EXPECTED_ARCHIVES,
    }
    assert {record.file_name for record in manifest.archives} == EXPECTED_ARCHIVES
    assert manifest.download_size_bytes == 1_000
    assert layout["assets"]["manifest"]["role"] == "metadata"
    assert layout["assets"]["signature"]["role"] == "metadata"


def test_offer_uses_authenticated_metadata_and_admission_evidence_only() -> None:
    verifier = ReleaseTrustVerifier(APP_VERSION)
    manifest = verifier.verify_manifest(_bytes("manifest.json"), _bytes("manifest.sig"))

    offer = verifier.authenticated_offer(
        manifest,
        {"bin/ffmpeg.exe": "Media tools", "models/ggml-base.en.bin": "Base English model"},
    )

    assert offer.app_version == APP_VERSION
    assert offer.download_size_bytes == 1_000
    assert offer.affected_components == ("Base English model", "Media tools")
    assert {record.file_name for record in offer.archives} == EXPECTED_ARCHIVES


@pytest.mark.parametrize(
    ("members", "expected"),
    (
        (("bin/ffmpeg.exe", "../escape.exe"), ("bin/ffmpeg.exe", "bin/ffprobe.exe")),
        (("bin/ffmpeg.exe", "BIN/FFMPEG.EXE"), ("bin/ffmpeg.exe", "bin/ffprobe.exe")),
        (("bin/ffmpeg.exe",), ("bin/ffmpeg.exe", "bin/ffprobe.exe")),
    ),
)
def test_archive_member_validation_rejects_unsafe_duplicate_and_drift(
    members: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    with pytest.raises(ReleaseTrustError):
        ReleaseTrustVerifier(APP_VERSION).validate_archive_members("ffmpeg", members, expected)


@pytest.mark.parametrize(
    "mutator",
    (
        lambda payload: payload.__setitem__("schema_version", 2),
        lambda payload: payload.__setitem__("app_version", "0.9.0-beta.5"),
        lambda payload: payload.__setitem__("unknown", "field"),
        lambda payload: payload["assets"].pop(),
        lambda payload: payload["assets"].append(payload["assets"][0]),
        lambda payload: payload["assets"][0].__setitem__("sha256", "UPPERCASE"),
        lambda payload: payload["assets"][0].__setitem__("size_bytes", (1 << 64)),
    ),
)
def test_authenticated_malicious_schema_variants_fail_closed(mutator) -> None:
    verifier, raw_manifest, signature = _signed_variant(mutator)
    with pytest.raises(ReleaseTrustError):
        verifier.verify_manifest(raw_manifest, signature)


def test_duplicate_json_key_noncanonical_json_bad_signature_and_bad_key_fail_closed() -> None:
    raw = b'{"app_version":"0.9.0-beta.6","app_version":"0.9.0-beta.6"}'
    verifier, _, signature = _signed_variant(raw=raw)
    with pytest.raises(ReleaseTrustError):
        verifier.verify_manifest(raw, signature)
    with pytest.raises(ReleaseTrustError):
        ReleaseTrustVerifier(APP_VERSION, "A" * 64)
    with pytest.raises(ReleaseTrustError):
        verifier.verify_manifest(_bytes("manifest.json"), b"short")


def test_unsigned_64_total_overflow_fails_closed() -> None:
    def set_max_sizes(payload):
        for asset in payload["assets"]:
            asset["size_bytes"] = (1 << 64) - 1

    verifier, raw_manifest, signature = _signed_variant(set_max_sizes)
    with pytest.raises(ReleaseTrustError):
        verifier.verify_manifest(raw_manifest, signature)
