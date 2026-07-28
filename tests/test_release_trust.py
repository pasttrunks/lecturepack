"""Frozen trust-root contract for the signed exact-version runtime release."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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
