"""HTTPS client for the LecturePack AI Gateway.

The desktop owns no provider keys, provider choices, or model choices. It sends
only fixed Study task types and lecture-derived metadata to the LecturePack
gateway. A stable anonymous installation id and expiring opaque token are kept
inside the app data directory; neither is a university credential.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import ssl
import threading
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
import uuid

from lecturepack.infrastructure.file_manager import FileManager


DEFAULT_GATEWAY_URL = "https://lecturepack-ai-gateway.discordsammy2.workers.dev"
INSTALLATION_FILENAME = "ai-installation-v1.json"
INSTALLATION_SCHEMA_VERSION = 1
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
TASK_TYPES = {
    "lecture_analysis",
    "study_material_generation",
    "ask",
    "teach_me",
    "grade_short_answer",
    "regenerate_concept",
    "vision_slide",
    "web_enrichment",
}
_SAFE_ROUTE = re.compile(r"^[A-Za-z0-9_./:@-]{1,120}$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SAFE_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,39}$")
_SAFE_STAGES = {
    "Local lecture processing",
    "Lecture analysis",
    "Canonical lecture analysis",
    "Selected slide interpretation",
    "Optional web enrichment",
    "Study material generation",
    "Partial concept regeneration",
}


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    """Do not forward installation tokens across HTTP redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _valid_installation_id(value: Any) -> bool:
    try:
        parsed = uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return False
    return str(parsed) == str(value).lower()


def _validate_gateway_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlparse.urlsplit(raw)
    host = (parsed.hostname or "").lower()
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("LecturePack AI Gateway must use HTTPS (HTTP is allowed only on loopback for tests).")
    if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("LecturePack AI Gateway URL is invalid.")
    return raw


def sanitize_diagnostics(value: Any) -> dict[str, Any]:
    """Return the small diagnostics allowlist that is safe to show/copy."""
    source = value if isinstance(value, dict) else {}
    routes = []
    for route in source.get("attempted_routes", []) or []:
        route = str(route)
        if _SAFE_ROUTE.fullmatch(route) and route not in routes:
            routes.append(route)
    provider_codes = []
    for code in source.get("provider_codes", []) or []:
        code = str(code)
        if _SAFE_CODE.fullmatch(code) and code not in provider_codes:
            provider_codes.append(code)

    def safe_number(key: str, *, maximum: int) -> int:
        try:
            return max(0, min(maximum, int(source.get(key) or 0)))
        except (TypeError, ValueError):
            return 0

    raw_statuses = source.get("provider_status", []) or []
    if not isinstance(raw_statuses, list):
        raw_statuses = [raw_statuses]
    provider_status = []
    for status in raw_statuses:
        try:
            status = max(0, min(599, int(status)))
        except (TypeError, ValueError):
            continue
        if status and status not in provider_status:
            provider_status.append(status)

    request_id = str(source.get("request_id") or "")
    task_type = str(source.get("task_type") or source.get("task") or "")
    timestamp = str(source.get("timestamp") or "")
    app_version = str(source.get("app_version") or "")
    error_category = str(source.get("error_category") or "")
    stage = str(source.get("last_successful_stage") or "")
    return {
        "request_id": request_id if _SAFE_REQUEST_ID.fullmatch(request_id) else "",
        "task_type": task_type if task_type in TASK_TYPES else "",
        "timestamp": timestamp[:64] if _parse_iso(timestamp) else _iso(),
        "app_version": app_version if _SAFE_VERSION.fullmatch(app_version) else "",
        "error_category": error_category if _SAFE_CODE.fullmatch(error_category) else "",
        "attempted_routes": routes[:3],
        "provider_codes": provider_codes[:3],
        "http_status": safe_number("http_status", maximum=599),
        "provider_status": provider_status[:3],
        "retry_count": safe_number("retry_count", maximum=3),
        "last_successful_stage": stage if stage in _SAFE_STAGES else "",
    }


class GatewayError(RuntimeError):
    """Safe, normalized gateway failure. Raw provider bodies are never kept."""

    def __init__(self, code: str, message: str, *, retryable: bool = True,
                 status: int = 0, diagnostics: dict[str, Any] | None = None):
        super().__init__(str(message or "Study AI could not complete the request."))
        self.code = str(code or "gateway_error")[:80]
        self.retryable = bool(retryable)
        self.status = int(status or 0)
        clean = dict(diagnostics or {})
        clean.setdefault("error_category", self.code)
        clean.setdefault("http_status", self.status)
        self.diagnostics = sanitize_diagnostics(clean)


class GatewayClient:
    """Dependency-free JSON client with anonymous install-token refresh."""

    def __init__(self, data_dir: str | os.PathLike[str], *,
                 gateway_url: str | None = None,
                 app_version: str | None = None,
                 timeout_seconds: float = 175.0,
                 opener: Any | None = None):
        configured = gateway_url or os.environ.get(
            "LECTUREPACK_AI_GATEWAY_URL", DEFAULT_GATEWAY_URL)
        self.gateway_url = _validate_gateway_url(configured)
        self.app_version = str(
            app_version or os.environ.get("LECTUREPACK_APP_VERSION", "2.0.1"))[:40]
        self.timeout_seconds = max(5.0, min(float(timeout_seconds), 180.0))
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.installation_path = self.data_dir / INSTALLATION_FILENAME
        self._ssl_context = ssl.create_default_context()
        self._opener = opener or urlrequest.build_opener(
            _NoRedirect(), urlrequest.HTTPSHandler(context=self._ssl_context))
        self._state_lock = threading.RLock()

    def _load_state(self) -> dict[str, Any]:
        data = FileManager.read_json_safe(str(self.installation_path), {}) or {}
        if not isinstance(data, dict):
            data = {}
        installation_id = str(data.get("installation_id") or "").lower()
        if not _valid_installation_id(installation_id):
            installation_id = str(uuid.uuid4())
        origin = str(data.get("gateway_origin") or "")
        if origin != self.gateway_url:
            data["installation_token"] = ""
            data["expires_at"] = ""
        data.update({
            "schema_version": INSTALLATION_SCHEMA_VERSION,
            "installation_id": installation_id,
            "gateway_origin": self.gateway_url,
        })
        return data

    def _save_state(self, data: dict[str, Any]) -> None:
        clean = {
            "schema_version": INSTALLATION_SCHEMA_VERSION,
            "installation_id": str(data.get("installation_id") or ""),
            "installation_token": str(data.get("installation_token") or ""),
            "expires_at": str(data.get("expires_at") or ""),
            "gateway_origin": self.gateway_url,
            "registered_app_version": self.app_version,
        }
        FileManager.write_json_atomic(str(self.installation_path), clean)
        try:
            os.chmod(self.installation_path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _token_current(state: dict[str, Any]) -> bool:
        token = str(state.get("installation_token") or "")
        expires = _parse_iso(state.get("expires_at"))
        return bool(token and expires and expires > _now() + timedelta(minutes=5))

    def _post(self, path: str, payload: dict[str, Any], *,
              token: str = "") -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"LecturePack/{self.app_version}",
            "X-LecturePack-Version": self.app_version,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urlrequest.Request(
            self.gateway_url + path, data=body, headers=headers, method="POST")
        try:
            response = self._opener.open(
                request, timeout=self.timeout_seconds) if hasattr(self._opener, "open") else self._opener(
                    request, timeout=self.timeout_seconds, context=self._ssl_context)
            with response:
                final_url = _validate_gateway_url(response.geturl().rsplit(path, 1)[0])
                if final_url != self.gateway_url:
                    raise GatewayError(
                        "gateway_redirect", "Study AI refused an unexpected gateway redirect.",
                        retryable=False)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                status = int(getattr(response, "status", 200) or 200)
        except urlerror.HTTPError as exc:
            raw = exc.read(MAX_RESPONSE_BYTES + 1)
            status = int(exc.code or 0)
            return self._decode_response(raw, status)
        except (GatewayError, ValueError):
            raise
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            code = "gateway_timeout" if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower() else "gateway_unreachable"
            message = "Study AI timed out. Retry, or use Basic Study." if code == "gateway_timeout" else "Study AI could not reach the LecturePack gateway. Retry, or use Basic Study."
            raise GatewayError(code, message, retryable=True) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GatewayError("gateway_response_too_large", "Study AI returned an unexpectedly large response.")
        return self._decode_response(raw, status)

    def _decode_response(self, raw: bytes, status: int) -> dict[str, Any]:
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GatewayError("gateway_response_too_large", "Study AI returned an unexpectedly large response.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GatewayError(
                "gateway_invalid_response",
                "Study AI returned an invalid response. Retry, or use Basic Study.",
                status=status) from None
        if not isinstance(payload, dict):
            raise GatewayError("gateway_invalid_response", "Study AI returned an invalid response.", status=status)
        if status >= 400 or payload.get("ok") is False:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
            raise GatewayError(
                str(error.get("code") or f"gateway_http_{status}"),
                str(error.get("message") or "Study AI could not complete the request."),
                retryable=bool(error.get("retryable", status >= 500 or status == 429)),
                status=status,
                diagnostics=diagnostics,
            )
        return payload

    def _register(self, state: dict[str, Any]) -> dict[str, Any]:
        response = self._post("/v1/installations/register", {
            "installation_id": state["installation_id"],
            "app_version": self.app_version,
        })
        token = str(response.get("installation_token") or "")
        expires_at = str(response.get("expires_at") or "")
        if not token or not _parse_iso(expires_at):
            raise GatewayError(
                "registration_invalid", "Study AI could not register this installation.")
        state["installation_token"] = token
        state["expires_at"] = expires_at
        self._save_state(state)
        return state

    def installation_id(self) -> str:
        with self._state_lock:
            state = self._load_state()
            self._save_state(state)
            return str(state["installation_id"])

    def request(self, task: str, input_data: dict[str, Any], *,
                request_id: str | None = None) -> dict[str, Any]:
        task = str(task or "")
        if task not in TASK_TYPES:
            raise ValueError(f"unsupported Study task: {task}")
        if not isinstance(input_data, dict):
            raise TypeError("Study task input must be an object")
        forbidden = {"provider", "model", "route", "api_key", "apiKey"}
        if forbidden.intersection(input_data):
            raise ValueError("provider and model selection are server-controlled")
        request_id = str(request_id or f"lp-{uuid.uuid4()}")
        with self._state_lock:
            state = self._load_state()
            if not self._token_current(state):
                state = self._register(state)
            token = str(state.get("installation_token") or "")
        envelope = {
            "request_id": request_id,
            "task": task,
            "input": input_data,
            "client_context": {"app_version": self.app_version},
        }
        try:
            response = self._post(
                "/v1/tasks", envelope,
                token=token)
        except GatewayError as exc:
            if exc.status != 401 or exc.code not in {"token_expired", "unauthorized"}:
                exc.diagnostics.update({
                    "request_id": request_id,
                    "task_type": task,
                    "app_version": self.app_version,
                })
                exc.diagnostics = sanitize_diagnostics(exc.diagnostics)
                raise
            with self._state_lock:
                state = self._load_state()
                state["installation_token"] = ""
                state["expires_at"] = ""
                state = self._register(state)
            try:
                response = self._post(
                    "/v1/tasks", envelope,
                    token=str(state.get("installation_token") or ""))
            except GatewayError as retry_exc:
                retry_exc.diagnostics.update({
                    "request_id": request_id,
                    "task_type": task,
                    "app_version": self.app_version,
                })
                retry_exc.diagnostics = sanitize_diagnostics(retry_exc.diagnostics)
                raise
        result = response.get("result")
        if not isinstance(result, dict):
            raise GatewayError(
                "gateway_invalid_result", "Study AI returned an invalid task result.",
                diagnostics={
                    "request_id": request_id,
                    "task_type": task,
                    "app_version": self.app_version,
                })
        diagnostics = response.get("diagnostics") if isinstance(response.get("diagnostics"), dict) else {}
        diagnostics.update({
            "request_id": request_id,
            "task_type": task,
            "app_version": self.app_version,
        })
        return {
            "result": result,
            "diagnostics": sanitize_diagnostics(diagnostics),
        }
