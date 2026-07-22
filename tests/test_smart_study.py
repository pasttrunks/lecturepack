"""Smart Study presets, RAM recommendation, Ollama pull, and adapter flow.

Covers the public-beta Smart Study work (§5-§8): the pure recommendation logic,
the streaming model pull, and the desktop adapter's status/preset/install slots.
Nothing here touches the network or a real Ollama server (both are faked), and
no API key or secret is involved.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import types

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from desktop import smart_study as sstudy  # noqa: E402
from lecturepack.infrastructure import ollama_client as oc  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402


# --------------------------------------------------------------------------- #
# Pure recommendation logic (no Qt, no network).
# --------------------------------------------------------------------------- #
def test_presets_expose_two_named_choices_with_ids_hidden_from_labels():
    presets = sstudy.preset_list()
    assert [p["key"] for p in presets] == ["lightweight", "balanced"]
    assert sstudy.model_for_preset("lightweight") == "qwen3:1.7b"
    assert sstudy.model_for_preset("balanced") == "qwen3:4b"
    # Balanced is the recommended default and the labels are friendly names.
    bal = sstudy.STUDY_PRESETS["balanced"]
    assert bal["recommended"] is True and bal["label"] == "Balanced Study"


def test_model_for_preset_custom_falls_back_to_supplied_model():
    assert sstudy.model_for_preset("custom", "llama3.2:3b") == "llama3.2:3b"
    assert sstudy.preset_for_model("qwen3:4b") == "balanced"
    assert sstudy.preset_for_model("something-else") == "custom"
    assert sstudy.preset_for_model("") == ""


@pytest.mark.parametrize("ram,expected,builtin,advanced", [
    (8.0, "lightweight", True, False),      # < 12 GB -> built-in default
    (16.0, "balanced", False, False),       # 12-24 GB -> balanced
    (32.0, "balanced", False, True),        # > 24 GB -> balanced + advanced
    (0.0, "balanced", False, True),         # unknown -> safe general default
])
def test_recommend_preset_thresholds(ram, expected, builtin, advanced):
    rec = sstudy.recommend_preset(ram)
    assert rec["recommended"] == expected
    assert rec["default_builtin"] is builtin
    assert rec["allow_advanced_models"] is advanced
    assert rec["note"]


def test_usable_ram_gb_is_a_nonnegative_float():
    ram = sstudy.usable_ram_gb()
    assert isinstance(ram, float) and ram >= 0.0


# --------------------------------------------------------------------------- #
# Ollama streaming pull.
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, lines):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        pass


def test_pull_model_streams_progress_and_returns_success(monkeypatch):
    client = oc.OllamaClient("http://localhost:11434")
    lines = [
        b'{"status":"pulling manifest"}\n',
        b'{"status":"downloading","total":10,"completed":5}\n',
        b'{"status":"success"}\n',
    ]
    monkeypatch.setattr(client, "_request",
                        lambda path, payload=None, timeout=None: _FakeResp(lines))
    seen = []
    res = client.pull_model("qwen3:4b", on_progress=seen.append)
    assert res["status"] == "success"
    assert any(p.get("percent") == 50.0 for p in seen)


def test_pull_model_raises_on_server_error(monkeypatch):
    client = oc.OllamaClient("http://localhost:11434")
    monkeypatch.setattr(client, "_request",
                        lambda path, payload=None, timeout=None: _FakeResp([b'{"error":"no space"}\n']))
    with pytest.raises(oc.OllamaBadResponse):
        client.pull_model("qwen3:4b")


def test_pull_model_honours_cancel_event(monkeypatch):
    client = oc.OllamaClient("http://localhost:11434")
    ev = threading.Event()
    ev.set()
    monkeypatch.setattr(client, "_request",
                        lambda path, payload=None, timeout=None: _FakeResp([b'{"status":"x"}\n']))
    with pytest.raises(oc.OllamaCancelled):
        client.pull_model("qwen3:4b", cancel_event=ev)


# --------------------------------------------------------------------------- #
# Adapter Smart Study slots (threads run inline, Ollama faked).
# --------------------------------------------------------------------------- #
class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, p):
        self.emissions.append(p)


class _FakeBackend:
    def __init__(self):
        for n in ("log_line", "settings_changed", "ai_status", "smart_study",
                  "ollama_models"):
            setattr(self, n, _Signal())


class _FakeOllama:
    """Class-level knobs so tests can set availability/installed models."""
    available = True
    installed: list = []
    pulls: list = []

    def __init__(self, base=None, **kw):
        pass

    def is_available(self):
        return {"available": type(self).available}

    def list_models(self):
        return [{"name": n} for n in type(self).installed]

    def pull_model(self, name, on_progress=None, cancel_event=None, timeout=None):
        type(self).pulls.append(name)
        if on_progress:
            on_progress({"status": "downloading", "percent": 40.0, "completed": 4, "total": 10})
            on_progress({"status": "success", "percent": 100.0, "completed": 10, "total": 10})
        type(self).installed = list(type(self).installed) + [name]
        return {"status": "success"}

    def chat_structured(self, *a, **k):
        return {"content": '{"ok": true}'}


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    _FakeOllama.available = True
    _FakeOllama.installed = []
    _FakeOllama.pulls = []
    monkeypatch.setattr(oc, "OllamaClient", _FakeOllama)
    # Run adapter worker threads inline so assertions are deterministic.
    monkeypatch.setattr(ea, "threading",
                        types.SimpleNamespace(Thread=_ImmediateThread, Event=threading.Event))
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    a._smart_study_cancel = None
    return a


class _ImmediateThread:
    def __init__(self, target=None, daemon=None, **kw):
        self._t = target

    def start(self):
        if self._t:
            self._t()


def _last(sig):
    return json.loads(sig.emissions[-1]) if not isinstance(sig.emissions[-1], dict) else sig.emissions[-1]


def _emissions(sig):
    out = []
    for e in sig.emissions:
        out.append(json.loads(e) if isinstance(e, str) else e)
    return out


def test_smart_study_status_reports_presets_and_recommendation(adapter):
    adapter.smart_study_status()
    d = _last(adapter.backend.smart_study)
    assert [p["key"] for p in d["presets"]] == ["lightweight", "balanced"]
    assert d["recommendation"]["recommended"] in ("lightweight", "balanced")
    assert d["ollama"]["available"] is True
    # No model selected yet -> Built-in Study is the provider.
    assert d["provider"] == "Built-in Study"


def test_set_study_preset_persists_model_and_enables(adapter):
    adapter.set_study_preset("balanced")
    o = adapter.config.get("ollama", {})
    assert o["model"] == "qwen3:4b" and o["enabled"] is True
    assert adapter.config.get("study_preset") == "balanced"


def test_install_smart_study_downloads_tests_and_marks_ready(adapter):
    adapter.install_smart_study("balanced")
    states = [e.get("state") for e in _emissions(adapter.backend.smart_study)]
    assert "downloading" in states
    assert "ready" in states
    assert "qwen3:4b" in _FakeOllama.pulls
    o = adapter.config.get("ollama", {})
    assert o["model"] == "qwen3:4b" and o["enabled"] is True
    assert adapter.config.get("smart_study_ready") is True


def test_install_smart_study_reports_need_engine_when_ollama_absent(adapter):
    _FakeOllama.available = False
    adapter.install_smart_study("balanced")
    states = [e.get("state") for e in _emissions(adapter.backend.smart_study)]
    assert states[-1] == "need_engine"
    assert _FakeOllama.pulls == []            # never attempted a download
    assert adapter.config.get("smart_study_ready", False) is False


def test_install_skips_download_when_model_already_present(adapter):
    _FakeOllama.installed = ["qwen3:4b"]
    adapter.install_smart_study("balanced")
    states = [e.get("state") for e in _emissions(adapter.backend.smart_study)]
    assert "downloading" not in states       # already installed
    assert "ready" in states
    assert _FakeOllama.pulls == []


def test_builtin_answer_returns_source_linked_snippets_without_ai():
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    segs = [
        {"start": 72.0, "text": "They aligned the pyramid to true north using a star."},
        {"start": 130.0, "text": "The base is level to within two centimeters."},
    ]
    ans = a._builtin_answer("how did they align it to north?", segs)
    assert "Built-in Study" in ans
    assert "01:12" in ans                     # 72s -> 01:12 timestamp cite
    assert "true north" in ans


def test_builtin_answer_handles_no_match_gracefully():
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    ans = a._builtin_answer("quantum chromodynamics", [{"start": 0.0, "text": "hello world"}])
    assert "couldn't find" in ans.lower()
