"""Consent and trust boundaries for the signed runtime repair transaction."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import stat
from threading import Event
import time
import zipfile

import pytest

from lecturepack.infrastructure.release_trust import ReleaseTrustVerifier, official_release_urls


FIXTURE_PUBLIC_KEY_HEX = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"


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
        verifier=ReleaseTrustVerifier(version, FIXTURE_PUBLIC_KEY_HEX),
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


def test_setup_bridge_rejects_stale_repair_confirmation(qapp, monkeypatch, tmp_path):
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    import lecturepack.constants as constants
    import lecturepack.infrastructure.config_manager as cm
    from desktop import bridge

    # 01-06: Backend's deferred worker now probes real data-directory
    # writability (D-13 host-only checklist item) using a real ConfigManager
    # here. Point it at tmp_path so that probe never touches ~/LecturePackData.
    monkeypatch.setattr(constants, "DEFAULT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cm, "DEFAULT_DATA_DIR", str(tmp_path))

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
    backend._runtime_repair = type("Repair", (), {
        "admission_result": Result("HEALTHY"), "diagnostic_report": lambda self: "[]",
    })()
    forwarded = []
    backend.repair_event.connect(forwarded.append)

    backend._on_repair_event({"operation_id": "bridge-op", "kind": "admitted"})
    backend._on_repair_event({"operation_id": "bridge-op", "kind": "admitted"})

    assert assessments == [{}]
    assert constructions == ["adapter", "updater"]
    assert [__import__("json").loads(item)["kind"] for item in forwarded] == ["admitted"]
    assert backend._repair_offer_id is None


def test_cancel_at_streaming_extraction_and_activation_boundaries_preserves_selection(tmp_path, monkeypatch):
    """Every cancellation boundary leaves the same previous pointer selected."""
    import lecturepack.services.runtime_repair as repair_module
    from lecturepack.infrastructure.runtime_inventory import canonical_inventory

    version, manifest, values, urls = _repair_release()
    for boundary in ("stream", "extract", "activate"):
        service = _service(tmp_path / boundary, values.copy(), manifest)
        source, previous_paths = tmp_path / boundary / "old", {}
        for entry in canonical_inventory(("ggml-cpu-avx2.dll",)):
            path = source / entry
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"previous" + entry.encode())
            previous_paths[entry] = path
        previous = service._generation_store.publish_from_directory(previous_paths, admit=lambda root: True)
        service.begin_repair_offer(boundary)
        if boundary == "stream":
            class Streaming(_Transport):
                def stream_get(self, url):
                    body = self.get(url)
                    yield body[:1]
                    service.cancel(boundary)
                    yield body[1:]
            service.transport = Streaming(values)
        elif boundary == "extract":
            original = repair_module.safe_extract_verified_archive
            def cancel_after_extract(*args, **kwargs):
                result = original(*args, **kwargs)
                service.cancel(boundary)
                return result
            monkeypatch.setattr(repair_module, "safe_extract_verified_archive", cancel_after_extract)
        else:
            original = service._generation_store.publish_from_directory
            def cancel_at_activation(*args, **kwargs):
                service.cancel(boundary)
                return original(*args, **kwargs)
            service._generation_store.publish_from_directory = cancel_at_activation
        with pytest.raises(Exception) as error:
            service.perform_repair(boundary)
        assert error.value.code == "cancelled"
        assert service._generation_store.read_active().generation_id == previous.generation_id
        assert [event.kind for event in service.events].count("cancelled") == 1
        monkeypatch.undo()


@pytest.mark.parametrize("kind", ("symlink", "duplicate", "cross_component", "archive_limit"))
def test_archive_fault_matrix_rejects_special_duplicate_cross_component_and_size_bounds(tmp_path, monkeypatch, kind):
    import lecturepack.services.runtime_repair as repair_module
    version, manifest, values, urls = _repair_release()
    first = manifest.archives[0]
    if kind == "symlink":
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("bin/ffmpeg.exe")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target")
            archive.writestr("bin/ffprobe.exe", b"probe")
        body = buffer.getvalue()
    elif kind == "duplicate":
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("bin/ffmpeg.exe", b"one")
            archive.writestr("bin/ffmpeg.exe", b"two")
            archive.writestr("bin/ffprobe.exe", b"probe")
        body = buffer.getvalue()
    else:
        body = _zip_bytes({"models/ggml-base.en.bin": b"wrong component"}) if kind == "cross_component" else values[urls[first.file_name]]
        if kind == "archive_limit":
            monkeypatch.setattr(repair_module, "_MAX_ARCHIVE_BYTES", 1)
    values[urls[first.file_name]] = body
    assets = (_Asset(first.component, first.file_name, sha256(body).hexdigest(), len(body)), *manifest.archives[1:])
    service = _service(tmp_path, values, _Manifest(assets))
    service.begin_repair_offer(kind)
    with pytest.raises(Exception):
        service.perform_repair(kind)
    assert [event.kind for event in service.events].count("failed") == 1


def test_bridge_repair_diagnostics_are_redacted_copyable_and_confined(qapp, tmp_path, monkeypatch):
    import json
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from desktop import bridge

    class Result:
        state, components, fallback_notice = "SETUP_REQUIRED", {}, None
    class Bootstrap:
        def __init__(self, config): pass
        def assess(self, **kwargs): return Result()
    class Config:
        def resolve_data_dir(self): return str(tmp_path / "profile")
    class Diagnostics:
        def runtime_health_snapshot(self): return {"admission_state": "SETUP_REQUIRED", "components": {}}
    monkeypatch.setattr(bridge, "ConfigManager", Config)
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", Bootstrap)
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsService", lambda *args: object())
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsController", lambda *args: Diagnostics())
    backend = bridge.Backend(None)
    service = _service(tmp_path, {}, _Manifest(()))
    service._emit("diagnostic", "failed", "Authorization: private-token password=hunter2")
    backend._runtime_repair = service

    assert json.loads(backend.copy_runtime_repair_diagnostics())["type"] == "runtime_repair_diagnostics_copied"
    copied = bridge.QGuiApplication.clipboard().text()
    assert "private-token" not in copied and "hunter2" not in copied and "[redacted]" in copied
    saved = json.loads(backend.save_runtime_repair_diagnostics("repair.txt"))
    assert Path(saved["path"]).read_text(encoding="utf-8") == copied
    assert json.loads(backend.save_runtime_repair_diagnostics("../escape.txt"))["type"] == "invalid_runtime_repair_diagnostics_path"


def test_canonical_store_admission_failure_restores_pointer_and_bridge_never_constructs(tmp_path, qapp, monkeypatch):
    """The bridge consumes the service's rollback-capable canonical result only."""
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from desktop import bridge
    from lecturepack.infrastructure.runtime_inventory import canonical_inventory

    version, manifest, values, urls = _repair_release()
    results = iter(("HEALTHY", "SETUP_REQUIRED"))
    service = _service(tmp_path, values, manifest, assessor=lambda root: type("Result", (), {"state": next(results)})())
    source, payload = tmp_path / "previous", {}
    for entry in canonical_inventory(("ggml-cpu-avx2.dll",)):
        path = source / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"before" + entry.encode())
        payload[entry] = path
    previous = service._generation_store.publish_from_directory(payload, admit=lambda root: True)
    service.begin_repair_offer("canonical-failure")
    with pytest.raises(Exception):
        service.perform_repair("canonical-failure")
    assert service._generation_store.read_active().generation_id == previous.generation_id

    constructed = []
    class Initial:
        state, components, fallback_notice = "SETUP_REQUIRED", {}, None
    class Bootstrap:
        def __init__(self, config): pass
        def assess(self, **kwargs): return Initial()
    class Diagnostics:
        def runtime_health_snapshot(self): return {"admission_state": "SETUP_REQUIRED", "components": {}}
    monkeypatch.setattr(bridge, "ConfigManager", lambda: object())
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", Bootstrap)
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsService", lambda *args: object())
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsController", lambda *args: Diagnostics())
    monkeypatch.setattr(bridge, "make_adapter", lambda *args, **kwargs: constructed.append("adapter"))
    monkeypatch.setattr(bridge, "Updater", lambda *args, **kwargs: constructed.append("updater"))
    backend = bridge.Backend(None)
    backend._repair_offer_id, backend._runtime_repair = "canonical-failure", service
    terminal = []
    backend.repair_event.connect(terminal.append)
    backend._on_repair_event(service.events[-1].payload())
    backend._on_repair_event({"operation_id": "canonical-failure", "kind": "admitted"})
    assert constructed == []
    assert [__import__("json").loads(event)["kind"] for event in terminal] == ["failed"]


def test_bridge_rejects_concurrent_start_and_ignores_repeat_cancel_and_out_of_order_terminal(qapp, monkeypatch):
    import json
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from desktop import bridge

    class Result:
        state, components, fallback_notice = "SETUP_REQUIRED", {}, None
    class Bootstrap:
        def __init__(self, config): pass
        def assess(self, **kwargs): return Result()
    class Diagnostics:
        def runtime_health_snapshot(self): return {"admission_state": "SETUP_REQUIRED", "components": {}}
    class Service:
        events = []
        admission_result = None
        def cancel(self, operation_id):
            self.events.extend([])
        def diagnostic_report(self): return "[]"
    class Worker:
        def __init__(self, service, operation_id, **kwargs): self.service, self.operation_id = service, operation_id
        class _Signal:
            def connect(self, callback): self.callback = callback
        repair_event = _Signal()
        def start(self): pass
        def cancel(self): self.service.cancel(self.operation_id)
    monkeypatch.setattr(bridge, "ConfigManager", lambda: object())
    monkeypatch.setattr(bridge, "RuntimeBootstrapService", Bootstrap)
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsService", lambda *args: object())
    monkeypatch.setattr(bridge, "RuntimeDiagnosticsController", lambda *args: Diagnostics())
    monkeypatch.setattr(bridge, "RuntimeRepairWorker", Worker)
    monkeypatch.setattr(bridge.Backend, "_make_runtime_repair_service", lambda self: Service())
    backend = bridge.Backend(None)
    assert json.loads(backend.start_runtime_repair("op"))["operation_id"] == "op"
    assert json.loads(backend.start_runtime_repair("other"))["type"] == "repair_in_progress"
    forwarded = []
    backend.repair_event.connect(forwarded.append)
    backend.cancel_runtime_repair("op")
    backend.cancel_runtime_repair("op")
    backend._on_repair_event({"operation_id": "wrong", "kind": "failed"})
    backend._on_repair_event({"operation_id": "op", "kind": "cancelled"})
    backend._on_repair_event({"operation_id": "op", "kind": "cancelled"})
    assert [json.loads(item)["kind"] for item in forwarded] == ["cancelled"]


def test_worker_streams_started_and_progress_before_blocked_transport_completes(qapp, tmp_path):
    """The UI receives live operation events; completion never flushes a buffer."""
    import sys
    app_dir = str(Path(__file__).parents[1] / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from PySide6.QtCore import QCoreApplication
    from desktop.repair_worker import RuntimeRepairWorker

    version, manifest, values, urls = _repair_release()
    metadata_entered, metadata_release = Event(), Event()
    payload_entered, payload_release = Event(), Event()
    manifest_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json"))

    class BlockingTransport(_Transport):
        def get(self, url):
            if url == manifest_url and not metadata_release.is_set():
                metadata_entered.set()
                assert metadata_release.wait(2)
            return super().get(url)
        def stream_get(self, url):
            payload_entered.set()
            assert payload_release.wait(2)
            yield self.get(url)

    service = _service(tmp_path, values, manifest, transport=BlockingTransport(values))
    seen = []
    offer_worker = RuntimeRepairWorker(service, "live")
    offer_worker.repair_event.connect(lambda payload: seen.append(dict(payload)))
    offer_worker.start()
    assert metadata_entered.wait(1)
    QCoreApplication.processEvents()
    assert [payload["kind"] for payload in seen] == ["started"]
    metadata_release.set()
    assert offer_worker.wait(2_000)
    QCoreApplication.processEvents()
    assert [payload["kind"] for payload in seen] == ["started", "metadata_ready"]

    repair_worker = RuntimeRepairWorker(service, "live", confirm=True)
    repair_worker.repair_event.connect(lambda payload: seen.append(dict(payload)))
    repair_worker.start()
    assert payload_entered.wait(1)
    QCoreApplication.processEvents()
    assert [payload["kind"] for payload in seen] == ["started", "metadata_ready", "progress"]
    payload_release.set()
    assert repair_worker.wait(2_000)
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(.01)
    terminals = [payload for payload in seen if payload["kind"] in {"failed", "cancelled", "admitted"}]
    assert [payload["kind"] for payload in terminals] == ["admitted"]
