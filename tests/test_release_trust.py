"""Frozen trust-root contract for the signed exact-version runtime release."""
from __future__ import annotations

import json
import hashlib
import importlib.util
from pathlib import Path
import zipfile

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
# The fixture is intentionally signed with RFC 8032's public test vector. The
# production release root is compiled separately in release_trust.py and its
# private seed must never be stored in the repository.
FIXTURE_PUBLIC_KEY_HEX = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
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
    verifier = ReleaseTrustVerifier(APP_VERSION, FIXTURE_PUBLIC_KEY_HEX)
    manifest = verifier.verify_manifest(_bytes("manifest.json"), _bytes("manifest.sig"))

    assert RELEASE_PUBLIC_KEY_HEX == "b15b321dc50d9e2cb4b59898361f7b58278f676f3cabf11d18d383b61c6c04e3"
    assert manifest.app_version == APP_VERSION
    with pytest.raises(ReleaseTrustError):
        verifier.verify_manifest(_bytes("manifest-altered.json"), _bytes("manifest.sig"))


def test_exact_six_asset_layout_and_checked_archive_total() -> None:
    layout = json.loads(_bytes("release-layout.json"))
    verifier = ReleaseTrustVerifier(APP_VERSION, FIXTURE_PUBLIC_KEY_HEX)
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
    verifier = ReleaseTrustVerifier(APP_VERSION, FIXTURE_PUBLIC_KEY_HEX)
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


def _release_builder_module():
    """Load the release-only builder without making it an application import."""
    path = Path(__file__).parents[1] / "scripts" / "build_signed_runtime_release.py"
    spec = importlib.util.spec_from_file_location("build_signed_runtime_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_builder_emits_only_the_exact_signed_six_asset_layout(tmp_path) -> None:
    """A local ephemeral signer proves the builder's exact-byte trust contract."""
    from lecturepack.infrastructure.runtime_inventory import canonical_inventory

    runtime_root = tmp_path / "canonical runtime"
    for entry in canonical_inventory(("ggml-cpu-test.dll",)):
        path = runtime_root / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(entry.encode("utf-8"))
    private_key = Ed25519PrivateKey.generate()
    output = tmp_path / "signed output"

    result = _release_builder_module().build_signed_runtime_release(
        app_version=APP_VERSION,
        runtime_root=runtime_root,
        output_directory=output,
        private_key_hex=private_key.private_bytes_raw().hex(),
        cpu_dll_names=("ggml-cpu-test.dll",),
    )

    expected = {
        f"LecturePack-{APP_VERSION}-RuntimeManifest-v1.json",
        f"LecturePack-{APP_VERSION}-RuntimeManifest-v1.json.sig",
        *EXPECTED_ARCHIVES,
    }
    assert {path.name for path in output.iterdir()} == expected
    public_key = private_key.public_key().public_bytes_raw().hex()
    manifest = ReleaseTrustVerifier(APP_VERSION, public_key).verify_manifest(
        (output / f"LecturePack-{APP_VERSION}-RuntimeManifest-v1.json").read_bytes(),
        (output / f"LecturePack-{APP_VERSION}-RuntimeManifest-v1.json.sig").read_bytes(),
    )
    assert {asset.file_name for asset in manifest.archives} == EXPECTED_ARCHIVES
    assert result["manifest_sha256"] == hashlib.sha256(manifest.raw_bytes).hexdigest()
    for asset in manifest.archives:
        with zipfile.ZipFile(output / asset.file_name) as archive:
            assert archive.namelist() == list(result["archive_members"][asset.component])


@pytest.mark.parametrize("wrong", ("v0.9.0-beta.6", "0.9.0 beta.6", "0.9"))
def test_release_builder_rejects_noncanonical_app_version(tmp_path, wrong: str) -> None:
    private_key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="application version"):
        _release_builder_module().build_signed_runtime_release(
            app_version=wrong,
            runtime_root=tmp_path,
            output_directory=tmp_path / "out",
            private_key_hex=private_key.private_bytes_raw().hex(),
        )


def test_release_workflow_binds_both_triggers_to_the_peeled_tag_before_signing() -> None:
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "push:" in workflow and "v*" in workflow and "workflow_dispatch:" in workflow
    assert 'refs/tags/v${APP_VERSION}^{commit}' in workflow
    assert "git rev-parse HEAD" in workflow
    assert "FULL_OBJECT_ID" in workflow
    assert "LECTUREPACK_RELEASE_ED25519_PRIVATE_KEY_HEX" in workflow
    assert "cryptography==49.0.0" in workflow
    assert "e5dfc1e64de5677cec922ffa8da89c546d0415bf6efdf081842e5d44c84e1f0e" in workflow
    assert "softprops/action-gh-release" in workflow
    assert "LecturePack-*-" not in workflow
