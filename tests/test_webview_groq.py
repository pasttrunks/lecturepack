"""Groq online-transcription WebView wiring (§6).

Exercises the adapter's key management + backend-mode persistence, reusing the
existing WindowsCredentialStore + Groq client — both monkeypatched so nothing
touches the real OS Credential Manager or the network (no live key available).
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from lecturepack.infrastructure import secret_store as ss  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, p):
        self.emissions.append(p)


class _FakeBackend:
    def __init__(self):
        for n in ("log_line", "settings_changed", "groq_status", "ai_status",
                  "ollama_models", "vulkan_status"):
            setattr(self, n, _Signal())


class _FakeStore:
    _v = {"k": ""}

    def set(self, secret):
        if not str(secret or "").strip():
            raise ss.SecretStoreError("API key cannot be empty.")
        _FakeStore._v["k"] = secret

    def get(self):
        return _FakeStore._v["k"]

    def remove(self):
        had = bool(_FakeStore._v["k"]); _FakeStore._v["k"] = ""; return had

    def has_secret(self):
        return bool(_FakeStore._v["k"])


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    _FakeStore._v["k"] = ""
    monkeypatch.setattr(ss, "WindowsCredentialStore", _FakeStore)
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    return a


def _last(sig):
    return json.loads(sig.emissions[-1])


def test_set_and_remove_groq_key(adapter):
    adapter.set_groq_key("gsk_test_123")
    d = _last(adapter.backend.groq_status)
    assert d["has_key"] is True
    assert _FakeStore._v["k"] == "gsk_test_123"
    adapter.remove_groq_key()
    assert _last(adapter.backend.groq_status)["has_key"] is False


def test_set_empty_key_reports_error(adapter):
    adapter.set_groq_key("")
    d = _last(adapter.backend.groq_status)
    assert d["has_key"] is False
    assert "could not save" in d["message"].lower()


def test_groq_status_reflects_stored_key(adapter):
    adapter._emit_groq_status()
    assert _last(adapter.backend.groq_status)["has_key"] is False
    _FakeStore._v["k"] = "gsk_x"
    adapter._emit_groq_status()
    assert _last(adapter.backend.groq_status)["has_key"] is True


def test_transcription_backend_persists(adapter):
    for mode in ("groq-fast", "groq-accurate", "local-whispercpp"):
        adapter.on_setting_changed("transcription_backend", mode)
        assert adapter.config.get("transcription_backend") == mode
    # invalid falls back to local
    adapter.on_setting_changed("transcription_backend", "nonsense")
    assert adapter.config.get("transcription_backend") == "local-whispercpp"
    assert adapter._settings_payload()["transcription_backend"] == "local-whispercpp"


def test_test_groq_key_no_key(adapter):
    adapter.test_groq_key()
    # threaded; wait briefly for the worker to report
    end = time.monotonic() + 5
    while time.monotonic() < end and "No API key" not in \
            (adapter.backend.groq_status.emissions[-1] if adapter.backend.groq_status.emissions else ""):
        time.sleep(0.05)
    assert "No API key" in adapter.backend.groq_status.emissions[-1]


def test_test_groq_key_passes_with_fake_client(adapter, monkeypatch):
    _FakeStore._v["k"] = "gsk_ok"

    class _Client:
        def test_key(self, key):
            return True
    import lecturepack.services.groq_transcription as gt
    monkeypatch.setattr(gt, "GroqHttpClient", _Client)
    adapter.test_groq_key()
    end = time.monotonic() + 5
    while time.monotonic() < end and "passed" not in \
            (adapter.backend.groq_status.emissions[-1] if adapter.backend.groq_status.emissions else ""):
        time.sleep(0.05)
    assert "passed" in adapter.backend.groq_status.emissions[-1].lower()
