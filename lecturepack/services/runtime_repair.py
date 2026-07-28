"""Consented coordinator for the fixed, signed runtime repair release.

This module is deliberately Qt-free: desktop code owns threading while this
service owns the operation-bound trust and transaction state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import tempfile
import zipfile
from typing import Callable, Iterable, Mapping
from urllib.error import URLError

from lecturepack.infrastructure.release_trust import ReleaseTrustError, ReleaseTrustVerifier, official_release_urls
from lecturepack.infrastructure.runtime_generation import (
    GenerationCancelled,
    GenerationError,
    safe_extract_verified_archive,
)
from lecturepack.infrastructure.runtime_inventory import canonical_inventory


class RepairFailure(RuntimeError):
    """A typed, display-safe repair failure."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = _redact(detail)
        super().__init__(self.detail)


@dataclass(frozen=True)
class RepairEvent:
    operation_id: str
    kind: str
    detail: str = ""
    classification: str = ""

    def payload(self) -> dict[str, str]:
        payload = {"operation_id": self.operation_id, "kind": self.kind, "detail": self.detail}
        if self.classification:
            payload["classification"] = self.classification
        return payload


@dataclass(frozen=True)
class RepairOperation:
    operation_id: str
    app_version: str
    official_source: str
    affected_components: tuple[str, ...]
    download_size_bytes: int
    expires_at: datetime


_TERMINAL_EVENTS = frozenset({"cancelled", "failed", "admitted"})
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_WINDOWS_DEVICES = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))})
_FIXED_MEMBERS = {
    "ffmpeg": ("bin/ffmpeg.exe", "bin/ffprobe.exe"),
    "model-base-en": ("models/ggml-base.en.bin",),
    "smoke-fixture": ("smoke/runtime-smoke.wav",),
    "whisper-cpu": ("bin/ggml-base.dll", "bin/ggml.dll", "bin/whisper-cli.exe", "bin/whisper.dll"),
}


def _redact(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(authorization|token|password|secret)=[^\s&]+", r"\1=[redacted]", text)
    return text[:1000]


def _safe_member_name(name: str) -> bool:
    """Apply Windows-safe runtime-name rules before any staging write."""
    if not isinstance(name, str) or not name or ":" in name or "\\" in name:
        return False
    posix, windows = PurePosixPath(name), PureWindowsPath(name)
    if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or name.endswith("/"):
        return False
    for part in posix.parts:
        stem = part.rstrip(". ").split(".", 1)[0].lower()
        if not part or part[-1:] in {".", " "} or stem in _WINDOWS_DEVICES:
            return False
    return True


class RuntimeRepairService:
    """Acquire signed metadata before an explicit matching confirmation."""

    _MAX_ATTEMPTS = 3

    def __init__(self, app_version: str, transport, *, verifier: ReleaseTrustVerifier | None = None,
                 admission_evidence: Mapping[str, str] | Callable[[], Mapping[str, str]] | None = None,
                 clock: Callable[[], datetime] | None = None, backoff: Callable[[int], None] | None = None,
                 offer_ttl: timedelta = timedelta(minutes=10), generation_store=None, bootstrap_assessor=None) -> None:
        self.app_version, self.transport = app_version, transport
        self._verifier = verifier or ReleaseTrustVerifier(app_version)
        self._admission_evidence = admission_evidence or {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._backoff, self._offer_ttl = backoff or (lambda _: None), offer_ttl
        self._offers: dict[str, RepairOperation] = {}
        self._manifests: dict[str, object] = {}
        self._generation_store, self._bootstrap_assessor = generation_store, bootstrap_assessor
        self.events: list[RepairEvent] = []
        self._cancelled: set[str] = set()
        self._terminal: set[str] = set()

    def _emit(self, operation_id: str, kind: str, detail: str = "", classification: str = "") -> RepairEvent | None:
        """Emit one ordered terminal outcome while keeping every field JSON-safe."""
        if operation_id in self._terminal:
            return None
        event = RepairEvent(str(operation_id), str(kind), _redact(detail), str(classification))
        self.events.append(event)
        if kind in _TERMINAL_EVENTS:
            self._terminal.add(operation_id)
            self._offers.pop(operation_id, None)
            self._manifests.pop(operation_id, None)
        return event

    def _cancel_boundary(self, operation_id: str) -> None:
        if operation_id in self._cancelled:
            raise GenerationCancelled("repair cancelled at a safe boundary")

    def _get_metadata(self, operation_id: str, url: str) -> bytes:
        """Fetch one fixed metadata object with bounded retry classification."""
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            self._cancel_boundary(operation_id)
            try:
                body = self.transport.get(url)
                if not isinstance(body, bytes):
                    raise RepairFailure("failed", "repair transport returned non-byte metadata")
                return body
            except RepairFailure:
                raise
            except GenerationCancelled:
                raise
            except (OSError, URLError, ConnectionError) as error:
                if attempt == self._MAX_ATTEMPTS:
                    raise RepairFailure("offline", "an internet connection is required for repair") from error
                self._emit(operation_id, "retrying", f"connection interrupted; retrying ({attempt + 1} of {self._MAX_ATTEMPTS})")
                self._backoff(attempt)
        raise AssertionError("bounded metadata retry loop unexpectedly ended")

    def _archive_chunks(self, url: str) -> Iterable[bytes]:
        """Prefer a streaming transport without widening the fixed-URL contract."""
        if hasattr(self.transport, "stream_get"):
            return self.transport.stream_get(url)
        body = self.transport.get(url)
        if not isinstance(body, bytes):
            raise RepairFailure("failed", "repair transport returned non-byte archive content")
        return (body,)

    def _download_archive(self, operation_id: str, url: str, expected_size: int, expected_digest: str, destination: Path) -> None:
        """Write a signed archive in bounded chunks and verify it before opening."""
        if expected_size > _MAX_ARCHIVE_BYTES:
            raise RepairFailure("failed", "signed repair archive exceeds the configured safety limit")
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            self._cancel_boundary(operation_id)
            written, digest = 0, sha256()
            try:
                with destination.open("xb") as output:
                    for chunk in self._archive_chunks(url):
                        self._cancel_boundary(operation_id)
                        if not isinstance(chunk, bytes):
                            raise RepairFailure("failed", "repair transport returned non-byte archive content")
                        written += len(chunk)
                        if written > expected_size:
                            raise RepairFailure("failed", "repair archive exceeds its signed size")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                if written != expected_size or digest.hexdigest() != expected_digest:
                    raise RepairFailure("failed", "repair archive verification failed")
                return
            except RepairFailure:
                destination.unlink(missing_ok=True)
                raise
            except GenerationCancelled:
                destination.unlink(missing_ok=True)
                raise
            except PermissionError as error:
                destination.unlink(missing_ok=True)
                raise RepairFailure("failed", "repair archive could not be written to staging") from error
            except (OSError, URLError, ConnectionError) as error:
                destination.unlink(missing_ok=True)
                if attempt == self._MAX_ATTEMPTS:
                    raise RepairFailure("offline", "an internet connection is required for repair") from error
                self._emit(operation_id, "retrying", f"connection interrupted; retrying ({attempt + 1} of {self._MAX_ATTEMPTS})")
                self._backoff(attempt)
        raise AssertionError("bounded archive retry loop unexpectedly ended")

    def begin_repair_offer(self, operation_id: str) -> RepairOperation:
        """Fetch exactly the two immutable metadata objects; never archives."""
        if not operation_id or operation_id in self._offers or operation_id in self._terminal:
            raise RepairFailure("failed", "repair operation identifier is invalid")
        urls = official_release_urls(self.app_version)
        manifest_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json"))
        signature_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json.sig"))
        self._emit(operation_id, "started")
        try:
            # Raw signature verification deliberately precedes all schema/version/key/inventory use.
            manifest = self._verifier.verify_manifest(
                self._get_metadata(operation_id, manifest_url), self._get_metadata(operation_id, signature_url)
            )
            evidence = self._admission_evidence() if callable(self._admission_evidence) else self._admission_evidence
            trusted = self._verifier.authenticated_offer(manifest, evidence)
            offer = RepairOperation(operation_id, trusted.app_version, manifest_url.rsplit("/", 1)[0] + "/",
                                   trusted.affected_components, trusted.download_size_bytes, self._clock() + self._offer_ttl)
            self._offers[operation_id] = offer
            self._manifests[operation_id] = manifest
            self._emit(operation_id, "metadata_ready")
            return offer
        except GenerationCancelled as error:
            self._emit(operation_id, "cancelled", str(error))
            raise RepairFailure("cancelled", str(error)) from error
        except (ReleaseTrustError, RepairFailure) as error:
            self._emit(operation_id, "failed", str(error), getattr(error, "code", "failed"))
            raise RepairFailure(getattr(error, "code", "failed"), str(error)) from error

    def cancel(self, operation_id: str) -> None:
        """Request cancellation once; its terminal event is stable and idempotent."""
        if operation_id in self._terminal or operation_id in self._cancelled:
            return
        self._cancelled.add(operation_id)
        self._offers.pop(operation_id, None)
        self._manifests.pop(operation_id, None)
        self._emit(operation_id, "cancel_requested")
        self._emit(operation_id, "cancelled")

    def confirm_repair(self, operation_id: str) -> RepairOperation:
        """Validate consent; archive acquisition is intentionally a later boundary."""
        offer = self._offers.pop(operation_id, None)
        if offer is None or operation_id in self._cancelled or offer.expires_at <= self._clock():
            self._manifests.pop(operation_id, None)
            failure = RepairFailure("failed", "repair confirmation does not match an active authenticated offer")
            self._emit(operation_id, "failed", str(failure), failure.code)
            raise failure
        return offer

    def _members_for_archive(self, component: str, archive_path: Path) -> tuple[tuple[str, ...], dict[str, str]]:
        """Freeze each archive's exact safe members before extraction to staging."""
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = archive.infolist()
                names = tuple(info.filename for info in infos)
                if (not names or len(names) != len(set(names)) or
                        len({name.lower() for name in names}) != len(names) or
                        any(not _safe_member_name(name) for name in names)):
                    raise RepairFailure("failed", "repair archive contains unsafe or duplicate runtime paths")
                expected_fixed = _FIXED_MEMBERS.get(component)
                if expected_fixed is None:
                    raise RepairFailure("failed", "repair archive has an unknown component")
                if component == "whisper-cpu":
                    cpu_members = tuple(name for name in names if name.startswith("bin/ggml-cpu-") and name.endswith(".dll"))
                    expected = tuple(sorted((*expected_fixed, *cpu_members)))
                    if not cpu_members:
                        raise RepairFailure("failed", "repair archive is missing a Whisper CPU backend")
                else:
                    expected = expected_fixed
                expected = tuple(sorted(expected))
                self._verifier.validate_archive_members(component, names, expected)
                if any(info.is_dir() for info in infos):
                    raise RepairFailure("failed", "repair archive contains a directory entry")
                for info in infos:
                    file_type = stat.S_IFMT(info.external_attr >> 16)
                    if file_type and file_type != stat.S_IFREG:
                        raise RepairFailure("failed", "repair archive contains a link or special entry")
                member_hashes: dict[str, str] = {}
                for info in infos:
                    if info.file_size > 2 * 1024 * 1024 * 1024:
                        raise RepairFailure("failed", "repair archive member exceeds extraction safety limit")
                    digest = sha256()
                    with archive.open(info, "r") as source:
                        while chunk := source.read(64 * 1024):
                            digest.update(chunk)
                    member_hashes[info.filename] = digest.hexdigest()
                return expected, member_hashes
        except RepairFailure:
            raise
        except (OSError, zipfile.BadZipFile, GenerationError) as error:
            raise RepairFailure("failed", "repair archive could not be safely inspected") from error

    def perform_repair(self, operation_id: str) -> RepairOperation:
        """Acquire only after matching consent, stage all archives, then admit."""
        offer = self.confirm_repair(operation_id)
        manifest = self._manifests.pop(operation_id, None)
        if manifest is None or self._generation_store is None or self._bootstrap_assessor is None:
            raise RepairFailure("failed", "repair transaction is not configured")
        temporary = Path(tempfile.mkdtemp(prefix="lecturepack-repair-"))
        try:
            source_paths: dict[str, Path] = {}
            archive_total = 0
            urls = official_release_urls(self.app_version)
            self._emit(operation_id, "progress", "Downloading")
            for asset in manifest.archives:
                self._cancel_boundary(operation_id)
                archive_path = temporary / asset.file_name
                self._download_archive(operation_id, urls[asset.file_name], asset.size_bytes, asset.sha256, archive_path)
                archive_total += asset.size_bytes
                expected_members, hashes = self._members_for_archive(asset.component, archive_path)
                extracted = safe_extract_verified_archive(
                    archive_path, temporary / "payload", expected_members=expected_members, expected_hashes=hashes,
                    max_compressed_bytes=_MAX_ARCHIVE_BYTES,
                )
                if set(source_paths).intersection(extracted):
                    raise RepairFailure("failed", "repair archives overlap the canonical runtime inventory")
                source_paths.update(extracted)
                self._cancel_boundary(operation_id)
            cpu_dll_names = tuple(Path(name).name for name in source_paths if name.startswith("bin/ggml-cpu-") and name.endswith(".dll"))
            expected_inventory = set(canonical_inventory(cpu_dll_names))
            if archive_total != offer.download_size_bytes or set(source_paths) != expected_inventory:
                raise RepairFailure("failed", "repair archives do not contain the canonical runtime inventory")
            self._emit(operation_id, "progress", "Installing safely")

            def admit(root: Path) -> bool:
                # This callback executes both staged and post-pointer canonical repair admission
                # while RuntimeGenerationStore still owns rollback of the prior active pointer.
                return self._bootstrap_assessor(root).state == "HEALTHY"

            self._generation_store.publish_from_directory(
                source_paths, admit=admit, cancellation_requested=lambda: operation_id in self._cancelled,
            )
            self._emit(operation_id, "activated")
            self._emit(operation_id, "admitted")
            return offer
        except GenerationCancelled as error:
            self._emit(operation_id, "cancelled", str(error))
            raise RepairFailure("cancelled", str(error)) from error
        except (RepairFailure, GenerationError) as error:
            failure = error if isinstance(error, RepairFailure) else RepairFailure("failed", str(error))
            self._emit(operation_id, "failed", str(failure), failure.code)
            raise failure
        except Exception as error:
            self._emit(operation_id, "failed", str(error))
            raise RepairFailure("failed", str(error)) from error
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
