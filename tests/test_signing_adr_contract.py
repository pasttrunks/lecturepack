"""Executable contract for the approved Phase 2 signing trust boundary.

This test intentionally exercises cryptography's real Ed25519 API using fixed
bytes.  It does not provide a production verifier or repair implementation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
ADR = DECISIONS.split("## AD-19:", 1)[1]

PUBLIC_KEY_HEX = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"
SIGNING_KEY_ID = "56475aa75463474c"
CANONICAL_MANIFEST = (
    b'{"app_version":"0.9.0-beta.6","assets":[{"component":"ffmpeg",'
    b'"file_name":"ffmpeg.zip","sha256":"0123456789abcdef0123456789abcdef'
    b'0123456789abcdef0123456789abcdef","size_bytes":1}],"schema_version":1,'
    b'"signing_key_id":"56475aa75463474c"}'
)
KNOWN_GOOD_SIGNATURE = bytes.fromhex(
    "b322d468ac44e967e9934cafa09b3b391562a1b145429361072f689a8ebe1315"
    "2e2566032eb1d75429b9f8562debe1bfe15b307eb3322581901a17bf151ff40f"
)


def test_approved_adr_records_complete_accountable_contract() -> None:
    assert "**Status:** Approved" in ADR
    assert "**Approval date:** 2026-07-28" in ADR
    required_text = (
        "cryptography==49.0.0",
        "e5dfc1e64de5677cec922ffa8da89c546d0415bf6efdf081842e5d44c84e1f0e",
        "pure Ed25519 detached signature",
        "no prehash, no alternate algorithm fallback, and no parse/reserialize",
        "exactly 32 raw octets represented as exactly 64 lowercase ASCII hex characters",
        "compiled-in constant in `lecturepack/infrastructure/release_trust.py`",
        "exactly 64 raw binary bytes",
        "schema_version", "app_version", "signing_key_id", "assets",
        "Recursively sorted keys", "compact separators", "UTF-8 without BOM/trailing newline",
        "assets sorted by component then file_name", "duplicates/unknown fields rejected",
        "Verify exact downloaded bytes before parsing",
        "https://github.com/pasttrunks/lecturepack/releases/download/v{app_version}/",
        "LecturePack-{app_version}-RuntimeManifest-v1.json",
        "LecturePack-{app_version}-RuntimeManifest-v1.json.sig",
        "LecturePack-{app_version}-Runtime-ffmpeg.zip",
        "LecturePack-{app_version}-Runtime-whisper-cpu.zip",
        "LecturePack-{app_version}-Runtime-model-base-en.zip",
        "LecturePack-{app_version}-Runtime-smoke-fixture.zip",
        "LECTUREPACK_RELEASE_ED25519_PRIVATE_KEY_HEX",
        "pasttrunks", "Bitwarden secure attachment/item named `LecturePack Release Signing Key Backup`",
        "trigger-only, no annual cadence", "suspected compromise", "maintainer-access loss",
        "key loss", "signing-workflow compromise", "GitHub Security Advisory",
        "GitHub private vulnerability reporting", "self-approval", "lack of separation of duties",
        "clean PyInstaller onedir", "dedicated frozen verifier self-test",
        "known-good vector", "one altered manifest byte", "GitHub Actions artifact ONLY",
        "maximum retention GitHub permits", "artifact-expiry limitation",
        "no release SigningEvidence.zip", "no repository SIGNING.md index",
        "Phase 2 gate opens contractually only after approved tests pass",
    )
    for required in required_text:
        assert required in ADR, required


def test_real_ed25519_known_good_vector_accepts_exact_canonical_bytes() -> None:
    public_key = bytes.fromhex(PUBLIC_KEY_HEX)
    assert len(public_key) == 32
    assert PUBLIC_KEY_HEX == PUBLIC_KEY_HEX.lower()
    assert hashlib.sha256(public_key).hexdigest()[:16] == SIGNING_KEY_ID
    assert len(KNOWN_GOOD_SIGNATURE) == 64
    Ed25519PublicKey.from_public_bytes(public_key).verify(KNOWN_GOOD_SIGNATURE, CANONICAL_MANIFEST)


@pytest.mark.parametrize(
    "manifest, signature",
    (
        (CANONICAL_MANIFEST.replace(b"ffmpeg.zip", b"ffmpex.zip"), KNOWN_GOOD_SIGNATURE),
        (CANONICAL_MANIFEST, KNOWN_GOOD_SIGNATURE[:-1] + bytes([KNOWN_GOOD_SIGNATURE[-1] ^ 1])),
        (CANONICAL_MANIFEST.replace(b'{', b'{ ', 1), KNOWN_GOOD_SIGNATURE),
        (CANONICAL_MANIFEST.replace(b'"app_version"', b'"schema_version"', 1), KNOWN_GOOD_SIGNATURE),
    ),
)
def test_real_ed25519_rejects_altered_or_noncanonical_bytes(manifest: bytes, signature: bytes) -> None:
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
    with pytest.raises(InvalidSignature):
        public_key.verify(signature, manifest)


@pytest.mark.parametrize("key", (b"", b"x" * 31, b"x" * 33))
def test_ed25519_rejects_bad_raw_public_key_lengths(key: bytes) -> None:
    with pytest.raises(ValueError):
        Ed25519PublicKey.from_public_bytes(key)
