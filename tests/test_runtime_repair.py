"""Consent and trust boundaries for the signed runtime repair transaction."""
from __future__ import annotations

from pathlib import Path

import pytest

from lecturepack.infrastructure.release_trust import ReleaseTrustVerifier, official_release_urls


class _Transport:
    def __init__(self, values):
        self.values, self.requests = values, []

    def get(self, url):
        self.requests.append(url)
        return self.values[url]


def test_offer_authenticates_only_manifest_and_signature_before_confirmation():
    from lecturepack.services.runtime_repair import RuntimeRepairService

    fixture = Path(__file__).parent / "fixtures" / "release_trust"
    version = "0.9.0-beta.6"
    urls = official_release_urls(version)
    manifest_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json"))
    signature_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json.sig"))
    service = RuntimeRepairService(
        version,
        _Transport({manifest_url: fixture.joinpath("manifest.json").read_bytes(), signature_url: fixture.joinpath("manifest.sig").read_bytes()}),
        verifier=ReleaseTrustVerifier(version),
        admission_evidence={"bin/ffmpeg.exe": "Media tools", "models/ggml-base.en.bin": "Speech model"},
    )

    offer = service.begin_repair_offer("op-1")

    assert service.transport.requests == [manifest_url, signature_url]
    assert offer.operation_id == "op-1"
    assert offer.app_version == version
    assert offer.official_source == "https://github.com/pasttrunks/lecturepack/releases/download/v0.9.0-beta.6/"
    assert offer.affected_components == ("Media tools", "Speech model")
    assert offer.download_size_bytes > 0
    with pytest.raises(Exception):
        service.confirm_repair("different-offer")


def test_setup_bridge_rejects_stale_repair_confirmation(qapp, monkeypatch):
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from desktop import bridge

    class Result:
        state = "SETUP_REQUIRED"
        components = {}
        fallback_notice = None
    class Bootstrap:
        def __init__(self, config): pass
        def assess(self, **kwargs): return Result()
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", Bootstrap)
    backend = bridge.Backend(None)
    assert backend.confirm_runtime_repair("stale") == '{"type": "invalid_repair_offer"}'
