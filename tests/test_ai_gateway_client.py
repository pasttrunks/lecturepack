"""Focused desktop-client contracts for the server-routed Study gateway."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.services.ai_gateway import (  # noqa: E402
    GatewayClient,
    GatewayError,
    sanitize_diagnostics,
)


class _Response:
    def __init__(self, url: str, payload: dict, status: int = 200):
        self._url = url
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self._url

    def read(self, limit: int):
        return self._body[:limit]


class _Opener:
    def __init__(self, *, allow_registration: bool = True):
        self.allow_registration = allow_registration
        self.calls: list[dict] = []

    def open(self, request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        call = {
            "url": request.full_url,
            "body": body,
            "authorization": request.get_header("Authorization") or "",
            "timeout": timeout,
        }
        self.calls.append(call)
        if request.full_url.endswith("/v1/installations/register"):
            if not self.allow_registration:
                raise AssertionError("a current installation token must survive restart")
            return _Response(request.full_url, {
                "ok": True,
                "installation_token": "opaque-install-token",
                "expires_at": "2099-01-01T00:00:00+00:00",
            })
        return _Response(request.full_url, {
            "ok": True,
            "result": {"answer": "Grounded answer"},
            "diagnostics": {"attempted_routes": ["ask-primary"]},
        })


def test_gateway_url_requires_https_except_loopback(tmp_path):
    with pytest.raises(ValueError, match="HTTPS"):
        GatewayClient(tmp_path, gateway_url="http://study.example.test")
    assert GatewayClient(
        tmp_path, gateway_url="http://127.0.0.1:8787").gateway_url.endswith("8787")


def test_client_registers_anonymously_and_server_controls_routing(tmp_path):
    opener = _Opener()
    client = GatewayClient(
        tmp_path, gateway_url="http://127.0.0.1:8787", opener=opener,
        app_version="9.8.7")
    response = client.request("ask", {"question": "Why?"}, request_id="lp-test")
    assert response["result"]["answer"] == "Grounded answer"
    assert len(opener.calls) == 2
    registration, task = opener.calls
    assert registration["body"]["installation_id"]
    assert registration["body"]["app_version"] == "9.8.7"
    assert task["authorization"] == "Bearer opaque-install-token"
    assert task["body"]["task"] == "ask"
    assert "provider" not in task["body"] and "model" not in task["body"]


def test_client_rejects_provider_or_model_selection(tmp_path):
    client = GatewayClient(
        tmp_path, gateway_url="http://localhost:8787", opener=_Opener())
    with pytest.raises(ValueError, match="server-controlled"):
        client.request("ask", {"question": "Why?", "model": "client/model"})
    with pytest.raises(ValueError, match="unsupported"):
        client.request("arbitrary_chat", {"prompt": "hello"})


def test_safe_diagnostics_allowlist_excludes_secrets_and_payloads():
    cleaned = sanitize_diagnostics({
        "request_id": "lp-1",
        "task_type": "ask",
        "attempted_routes": ["ask-primary", "bad route with spaces"],
        "provider_codes": ["provider_timeout", "bad code"],
        "provider_status": [429, 503, "secret"],
        "retry_count": 2,
        "api_key": "secret-key",
        "transcript": "private lecture words",
        "prompt": "private question",
        "provider_body": "raw response",
        "last_successful_stage": "private lecture words masquerading as a stage",
    })
    serialized = json.dumps(cleaned)
    assert cleaned["attempted_routes"] == ["ask-primary"]
    assert cleaned["provider_codes"] == ["provider_timeout"]
    assert cleaned["provider_status"] == [429, 503]
    assert cleaned["retry_count"] == 2
    assert "secret-key" not in serialized
    assert "private lecture words" not in serialized
    assert "private question" not in serialized
    assert "provider_body" not in cleaned
    assert cleaned["last_successful_stage"] == ""


def test_installation_token_persists_across_client_restart(tmp_path):
    first_opener = _Opener()
    first = GatewayClient(
        tmp_path, gateway_url="http://localhost:8787", opener=first_opener)
    first.request("ask", {"question": "first"})

    second_opener = _Opener(allow_registration=False)
    second = GatewayClient(
        tmp_path, gateway_url="http://localhost:8787", opener=second_opener)
    second.request("ask", {"question": "second"})
    assert len(second_opener.calls) == 1
    assert second_opener.calls[0]["authorization"] == "Bearer opaque-install-token"
    persisted = json.loads((tmp_path / "ai-installation-v1.json").read_text(encoding="utf-8"))
    assert persisted["installation_token"] == "opaque-install-token"
    assert "provider" not in persisted and "model" not in persisted


def test_gateway_error_never_keeps_unlisted_diagnostics():
    error = GatewayError(
        "provider_chain_failed", "Study AI could not finish.",
        diagnostics={
            "attempted_routes": ["analysis-primary", "analysis-secondary"],
            "authorization": "Bearer secret",
            "raw_response": "private output",
        },
    )
    assert error.diagnostics["attempted_routes"] == [
        "analysis-primary", "analysis-secondary"]
    assert "authorization" not in error.diagnostics
    assert "raw_response" not in error.diagnostics
