"""Consented coordinator for the fixed, signed runtime repair release.

This module is deliberately Qt-free: desktop code owns threading while this
service owns the operation-bound trust and transaction state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Callable, Mapping
from urllib.error import URLError

from lecturepack.infrastructure.release_trust import ReleaseTrustError, ReleaseTrustVerifier, official_release_urls


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
                 offer_ttl: timedelta = timedelta(minutes=10)) -> None:
        self.app_version, self.transport = app_version, transport
        self._verifier = verifier or ReleaseTrustVerifier(app_version)
        self._admission_evidence = admission_evidence or {}
        self._clock, self._backoff, self._offer_ttl = clock or (lambda: datetime.now(timezone.utc)), backoff or (lambda _: None), offer_ttl
        self._offers: dict[str, RepairOperation] = {}
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
