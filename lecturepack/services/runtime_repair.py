"""Consented coordinator for the fixed, signed runtime repair release.

This module is deliberately Qt-free: desktop code owns threading while this
service owns the operation-bound trust and transaction state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Mapping
from urllib.error import URLError

from lecturepack.infrastructure.release_trust import ReleaseTrustError, ReleaseTrustVerifier, official_release_urls
from lecturepack.infrastructure.runtime_generation import GenerationCancelled
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

    def payload(self) -> dict[str, str]:
        return {"operation_id": self.operation_id, "kind": self.kind, "detail": self.detail}


@dataclass(frozen=True)
class RepairOperation:
    operation_id: str
    app_version: str
    official_source: str
    affected_components: tuple[str, ...]
    download_size_bytes: int
    expires_at: datetime


def _redact(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(authorization|token|password|secret)=[^\s&]+", r"\1=[redacted]", text)
    return text[:1000]


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
        self._clock, self._backoff, self._offer_ttl = clock or (lambda: datetime.now(timezone.utc)), backoff or (lambda _: None), offer_ttl
        self._offers: dict[str, RepairOperation] = {}
        self._manifests = {}
        self._generation_store, self._bootstrap_assessor = generation_store, bootstrap_assessor
        self.events: list[RepairEvent] = []
        self._cancelled: set[str] = set()

    def _emit(self, operation_id: str, kind: str, detail: str = "") -> RepairEvent:
        event = RepairEvent(operation_id, kind, _redact(detail))
        self.events.append(event)
        return event

    def _get(self, operation_id: str, url: str) -> bytes:
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                body = self.transport.get(url)
                if not isinstance(body, bytes):
                    raise RepairFailure("failed", "repair transport returned non-byte content")
                return body
            except RepairFailure:
                raise
            except (OSError, URLError, ConnectionError) as error:
                if attempt == self._MAX_ATTEMPTS:
                    raise RepairFailure("offline", "an internet connection is required for repair") from error
                self._emit(operation_id, "retrying", f"connection interrupted; retrying ({attempt + 1} of {self._MAX_ATTEMPTS})")
                self._backoff(attempt)

    def begin_repair_offer(self, operation_id: str) -> RepairOperation:
        """Fetch exactly the two immutable metadata objects; never archives."""
        if not operation_id or operation_id in self._offers:
            raise RepairFailure("failed", "repair operation identifier is invalid")
        urls = official_release_urls(self.app_version)
        manifest_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json"))
        signature_url = next(url for url in urls.values() if url.endswith("Manifest-v1.json.sig"))
        self._emit(operation_id, "started")
        try:
            manifest = self._verifier.verify_manifest(self._get(operation_id, manifest_url), self._get(operation_id, signature_url))
            evidence = self._admission_evidence() if callable(self._admission_evidence) else self._admission_evidence
            trusted = self._verifier.authenticated_offer(manifest, evidence)
        except (ReleaseTrustError, RepairFailure) as error:
            self._emit(operation_id, "failed", str(error))
            raise RepairFailure(getattr(error, "code", "failed"), str(error)) from error
        offer = RepairOperation(operation_id, trusted.app_version, manifest_url.rsplit("/", 1)[0] + "/",
                               trusted.affected_components, trusted.download_size_bytes, self._clock() + self._offer_ttl)
        self._offers[operation_id] = offer
        self._manifests[operation_id] = manifest
        self._emit(operation_id, "metadata_ready")
        return offer

    def cancel(self, operation_id: str) -> None:
        self._offers.pop(operation_id, None)
        self._cancelled.add(operation_id)
        self._emit(operation_id, "cancel_requested")
        self._emit(operation_id, "cancelled")

    def confirm_repair(self, operation_id: str) -> RepairOperation:
        """Validate consent; archive acquisition is intentionally a later boundary."""
        offer = self._offers.pop(operation_id, None)
        if offer is None or operation_id in self._cancelled or offer.expires_at <= self._clock():
            raise RepairFailure("failed", "repair confirmation does not match an active authenticated offer")
        return offer

    def perform_repair(self, operation_id: str) -> RepairOperation:
        """Acquire only after matching consent, stage all archives, then admit."""
        offer = self.confirm_repair(operation_id)
        manifest = self._manifests.pop(operation_id, None)
        if manifest is None or self._generation_store is None or self._bootstrap_assessor is None:
            raise RepairFailure("failed", "repair transaction is not configured")
        temporary = Path(tempfile.mkdtemp(prefix="lecturepack-repair-"))
        try:
            source_paths = {}
            expected = set(canonical_inventory())
            self._emit(operation_id, "progress", "Downloading")
            for asset in manifest.archives:
                if operation_id in self._cancelled:
                    raise GenerationCancelled("repair cancelled")
                url = official_release_urls(self.app_version)[asset.file_name]
                payload = self._get(operation_id, url)
                if len(payload) != asset.size_bytes or hashlib.sha256(payload).hexdigest() != asset.sha256:
                    raise RepairFailure("failed", "repair archive verification failed")
                archive_path = temporary / asset.file_name
                archive_path.write_bytes(payload)
                with zipfile.ZipFile(archive_path) as archive:
                    for info in archive.infolist():
                        name = info.filename
                        posix, windows = PurePosixPath(name), PureWindowsPath(name)
                        if name not in expected or "\\" in name or posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or info.is_dir():
                            raise RepairFailure("failed", "repair archive contains an unsafe runtime path")
                        target = (temporary / "payload" / name).resolve()
                        root = (temporary / "payload").resolve()
                        if root not in target.parents:
                            raise RepairFailure("failed", "repair archive escapes staging")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as src, target.open("xb") as dst:
                            shutil.copyfileobj(src, dst)
                        source_paths[name] = target
            if set(source_paths) != expected:
                raise RepairFailure("failed", "repair archives do not contain the canonical runtime inventory")
            self._emit(operation_id, "progress", "Installing safely")
            def admit(root):
                result = self._bootstrap_assessor(root)
                return result.state == "HEALTHY"
            active = self._generation_store.publish_from_directory(source_paths, admit=admit,
                cancellation_requested=lambda: operation_id in self._cancelled)
            self._emit(operation_id, "activated")
            result = self._bootstrap_assessor(active.root)
            if result.state != "HEALTHY":
                raise RepairFailure("failed", "repaired runtime did not pass admission")
            self._emit(operation_id, "admitted")
            return offer
        except GenerationCancelled as error:
            self._emit(operation_id, "cancelled", str(error))
            raise RepairFailure("cancelled", str(error)) from error
        except RepairFailure as error:
            self._emit(operation_id, "failed", str(error))
            raise
        except Exception as error:
            self._emit(operation_id, "failed", str(error))
            raise RepairFailure("failed", str(error)) from error
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
