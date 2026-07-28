"""Consent and trust boundaries for the signed runtime repair transaction."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from lecturepack.infrastructure.release_trust import ReleaseTrustVerifier, official_release_urls


class _Transport:
    def __init__(self, values):
        self.values, self.requests = values, []

    def get(self, url):
        self.requests.append(url)
        value = self.values[url]
        if isinstance(value, Exception):
            raise value
        return value


@dataclass(frozen=True)
class _Asset:
    component: str
    file_name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class _Manifest:
    archives: tuple[_Asset, ...]


class _RepairVerifier:
    """A deterministic trusted-manifest seam; release_trust owns signature tests."""
    def __init__(self, manifest):
        self.manifest = manifest

    def verify_manifest(self, manifest, signature):
        assert manifest == b"signed manifest" and signature == b"signature"
        return self.manifest

    def authenticated_offer(self, manifest, evidence):
        from lecturepack.infrastructure.release_trust import AuthenticatedOffer
        return AuthenticatedOffer("0.9.0-beta.6", tuple(sorted(set(evidence.values()))), manifest.archives,
                                  sum(asset.size_bytes for asset in manifest.archives))

    def validate_archive_members(self, component, received, expected):
        assert tuple(received) == tuple(expected)


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    return buffer.getvalue()


def _repair_release():
    """Return a four-archive exact R1 payload and its fixed transport values."""
    version = "0.9.0-beta.6"
    payloads = {
        "ffmpeg": {"bin/ffmpeg.exe": b"ffmpeg", "bin/ffprobe.exe": b"ffprobe"},
        "model-base-en": {"models/ggml-base.en.bin": b"model"},
        "smoke-fixture": {"smoke/runtime-smoke.wav": b"smoke"},
        "whisper-cpu": {
            "bin/ggml-base.dll": b"base", "bin/ggml-cpu-avx2.dll": b"cpu", "bin/ggml.dll": b"ggml",
            "bin/whisper-cli.exe": b"cli", "bin/whisper.dll": b"whisper",
        },
    }
    from lecturepack.infrastructure.release_trust import official_release_urls
    urls = official_release_urls(version)
    values = {
        next(url for url in urls.values() if url.endswith("Manifest-v1.json")): b"signed manifest",
        next(url for url in urls.values() if url.endswith("Manifest-v1.json.sig")): b"signature",
    }
    assets = []
    for component in sorted(payloads):
        file_name = next(name for name in urls if name.endswith(f"-{component}.zip"))
        body = _zip_bytes(payloads[component])
        values[urls[file_name]] = body
        assets.append(_Asset(component, file_name, sha256(body).hexdigest(), len(body)))
    return version, _Manifest(tuple(assets)), values, urls


def _service(tmp_path, values, manifest, *, assessor=None, transport=None):
    from lecturepack.infrastructure.runtime_generation import RuntimeGenerationStore
    from lecturepack.services.runtime_repair import RuntimeRepairService
    return RuntimeRepairService(
        "0.9.0-beta.6", transport or _Transport(values), verifier=_RepairVerifier(manifest),
        admission_evidence={"bin/ffmpeg.exe": "Media tools"}, generation_store=RuntimeGenerationStore(tmp_path / "data"),
        bootstrap_assessor=assessor or (lambda root: type("Result", (), {"state": "HEALTHY"})()),
    )


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


def test_confirmed_repair_streams_exact_four_archives_and_admits_only_after_transaction(tmp_path):
    version, manifest, values, urls = _repair_release()
    transport = _Transport(values)
    service = _service(tmp_path, values, manifest, transport=transport)

    offer = service.begin_repair_offer("repair-1")

    assert transport.requests == [
        next(url for url in urls.values() if url.endswith("Manifest-v1.json")),
        next(url for url in urls.values() if url.endswith("Manifest-v1.json.sig")),
    ]
    assert offer.download_size_bytes == sum(asset.size_bytes for asset in manifest.archives)
    service.perform_repair("repair-1")

    assert transport.requests[2:] == [urls[asset.file_name] for asset in manifest.archives]
    active = service._generation_store.read_active()
    assert active is not None
    assert (active.root / "smoke/runtime-smoke.wav").read_bytes() == b"smoke"
    assert [(event.kind, event.classification) for event in service.events] == [
        ("started", ""), ("metadata_ready", ""), ("progress", ""), ("progress", ""),
        ("activated", ""), ("admitted", ""),
    ]


@pytest.mark.parametrize("unsafe_member", ("../escape.exe", "bin/ffmpeg.exe:evil", "bin/FFMPEG.EXE"))
def test_archive_rejection_preserves_the_prior_active_generation(tmp_path, unsafe_member):
    version, manifest, values, urls = _repair_release()
    bad = _zip_bytes({unsafe_member: b"bad"})
    first = manifest.archives[0]
    values[urls[first.file_name]] = bad
    assets = (_Asset(first.component, first.file_name, sha256(bad).hexdigest(), len(bad)), *manifest.archives[1:])
    service = _service(tmp_path, values, _Manifest(assets))
    previous_source = tmp_path / "previous"
    from lecturepack.infrastructure.runtime_inventory import canonical_inventory
    previous_paths = {}
    for entry in canonical_inventory(("ggml-cpu-avx2.dll",)):
        path = previous_source / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old-" + entry.encode())
        previous_paths[entry] = path
    previous = service._generation_store.publish_from_directory(previous_paths, admit=lambda root: True)
    before = {path.relative_to(previous.root).as_posix(): path.read_bytes() for path in previous.root.rglob("*") if path.is_file()}

    service.begin_repair_offer("repair-unsafe")
    with pytest.raises(Exception):
        service.perform_repair("repair-unsafe")

    active = service._generation_store.read_active()
    assert active is not None and active.generation_id == previous.generation_id
    assert {path.relative_to(active.root).as_posix(): path.read_bytes() for path in active.root.rglob("*") if path.is_file()} == before
    assert [event.kind for event in service.events].count("failed") == 1


def test_retry_exhaustion_is_offline_and_cancel_is_idempotent_without_archive_requests(tmp_path):
    version, manifest, values, urls = _repair_release()
    manifest_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json"))
    offline = _Transport({manifest_url: ConnectionError("offline")})
    service = _service(tmp_path, {}, manifest, transport=offline)

    with pytest.raises(Exception) as error:
        service.begin_repair_offer("offline")

    assert error.value.code == "offline"
    assert [event.kind for event in service.events] == ["started", "retrying", "retrying", "failed"]
    assert service.events[-1].classification == "offline"
    service.cancel("cancelled")
    service.cancel("cancelled")
    assert [event.kind for event in service.events[-2:]] == ["cancel_requested", "cancelled"]
    assert all(url.endswith(("Manifest-v1.json", "Manifest-v1.json.sig")) for url in offline.requests)


def test_post_activation_admission_failure_rolls_back_before_terminal_failure(tmp_path):
    version, manifest, values, urls = _repair_release()
    calls = []

    def assessor(root):
        calls.append(root)
        return type("Result", (), {"state": "HEALTHY" if len(calls) < 2 else "SETUP_REQUIRED"})()

    service = _service(tmp_path, values, manifest, assessor=assessor)
    service.begin_repair_offer("admission-fails")
    with pytest.raises(Exception):
        service.perform_repair("admission-fails")

    assert service._generation_store.read_active() is None
    assert [event.kind for event in service.events][-2:] == ["progress", "failed"]


def test_worker_forwards_one_json_safe_ordered_offer_event(qapp, tmp_path):
    import json
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from desktop.repair_worker import RuntimeRepairWorker

    version, manifest, values, urls = _repair_release()
    worker = RuntimeRepairWorker(_service(tmp_path, values, manifest), "worker-offer")
    received = []
    worker.repair_event.connect(received.append)
    worker.run()  # deterministic service/Qt-boundary test; no event loop timing race

    assert [payload["kind"] for payload in received] == ["started", "metadata_ready"]
    assert received[-1]["affected_components"] == ["Media tools"]
    assert json.loads(json.dumps(received[-1])) == received[-1]


def test_bridge_accepts_one_admitted_event_then_constructs_collaborators_once(qapp, monkeypatch):
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from desktop import bridge

    assessments, constructions = [], []

    class Result:
        def __init__(self, state):
            self.state, self.components, self.fallback_notice = state, {}, None

    class Bootstrap:
        def __init__(self, config):
            pass
        def assess(self, **kwargs):
            assessments.append(kwargs)
            return Result("SETUP_REQUIRED" if len(assessments) == 1 else "HEALTHY")

    class Diagnostics:
        def runtime_health_snapshot(self):
            return {"admission_state": "HEALTHY", "components": {}}

    monkeypatch.setattr(bridge, "ConfigManager", lambda: object())
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", Bootstrap)
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsService", lambda *args: object())
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsController", lambda *args: Diagnostics())
    monkeypatch.setattr(bridge, "make_adapter", lambda *args, **kwargs: constructions.append("adapter") or object())
    monkeypatch.setattr(bridge, "Updater", lambda *args, **kwargs: constructions.append("updater") or object())
    backend = bridge.Backend(None)
    backend._repair_offer_id = "bridge-op"
    forwarded = []
    backend.repair_event.connect(forwarded.append)

    backend._on_repair_event({"operation_id": "bridge-op", "kind": "admitted"})
    backend._on_repair_event({"operation_id": "bridge-op", "kind": "admitted"})

    assert assessments == [{}, {"trigger": "repair"}]
    assert constructions == ["adapter", "updater"]
    assert [__import__("json").loads(item)["kind"] for item in forwarded] == ["admitted"]
    assert backend._repair_offer_id is None
