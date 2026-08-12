"""Cross-boundary contracts for the AI-first Study production upgrade."""
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = (ROOT / "electron-spike" / "python-sidecar.py").read_text(encoding="utf-8")
UI = (ROOT / "app" / "ui" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app" / "ui" / "app.js").read_text(encoding="utf-8")
GATEWAY = (ROOT / "ai-gateway" / "src" / "index.js").read_text(encoding="utf-8")
PROVIDERS = (ROOT / "ai-gateway" / "src" / "providers.js").read_text(encoding="utf-8")
CONTRACT = json.loads((
    ROOT / "electron-spike" / "contracts" / "electron-bridge-contract.json"
).read_text(encoding="utf-8"))


def _method(name: str, next_name: str) -> str:
    start = SIDECAR.index(f"    def {name}")
    end = SIDECAR.index(f"    def {next_name}", start)
    return SIDECAR[start:end]


def test_lecture_completion_starts_study_without_blocking_export_or_queue():
    method = _method("_on_pipeline_completed", "_start_automatic_export")
    assert "self._start_ai_study(self.current_job)" in method
    assert "QTimer.singleShot(0, self._start_automatic_export)" in method
    worker = _method("_start_ai_study", "_start_partial_study_refresh")
    assert "threading.Thread" in worker
    assert "daemon=True" in worker
    assert ".join(" not in worker


def test_retry_basic_diagnostics_and_manual_mastery_are_bridge_contracts():
    operations = {item["name"] for item in CONTRACT["operations"]}
    assert {
        "study_v2_retry", "study_v2_use_basic", "study_v2_copy_diagnostics",
        "study_v2_set_mastery", "study_generation",
    }.issubset(operations)
    for command in (
        "study_v2_retry", "study_v2_use_basic", "study_v2_copy_diagnostics",
        "study_v2_set_mastery",
    ):
        assert f'command == "{command}"' in SIDECAR
        assert command in APP


def test_normal_study_ui_has_six_equal_modes_and_no_provider_controls():
    study = UI[UI.index("<!-- ===== STUDY ===== -->"):UI.index("<!-- Legacy study content")]
    assert re.findall(r'data-study-mode="([^"]+)"', study) == [
        "overview", "flashcards", "quiz", "ask", "quick", "teach"]
    assert all(label in study for label in (
        "Study Guide", "Flashcards", "Quiz", "Ask", "Quick Study", "Teach Me"))
    tabs = re.findall(r'<button class="lp-hit lp-tab study-mode-tab[^>]+>', study)
    assert len(tabs) == 6
    assert all('role="tab"' in tab and 'aria-selected=' in tab for tab in tabs)
    assert all("background:" not in tab and "color:" not in tab for tab in tabs)
    assert not re.search(r"Ollama|provider|endpoint|API key|Installed model", study, re.I)
    assert 'id="legacy-smart-study-settings" hidden' in UI


def test_failure_state_exposes_retry_safe_diagnostics_and_basic_study():
    for element_id in (
        "btn-study-ai-retry", "btn-study-copy-diagnostics", "btn-study-use-basic"):
        assert f'id="{element_id}"' in UI
    assert "Study AI needs attention" in APP
    assert "Retry, or continue with Basic Study" in APP
    assert "navigator.clipboard.writeText" in APP


def test_provider_and_model_routing_exist_only_in_gateway_code():
    assert "OPENROUTER_API_KEY" in PROVIDERS
    assert "NVIDIA_API_KEY" in PROVIDERS
    assert "resolveRoutes" in PROVIDERS
    desktop_sources = "\n".join([
        (ROOT / "lecturepack" / "services" / "ai_gateway.py").read_text(encoding="utf-8"),
        SIDECAR,
        UI[UI.index("<!-- ===== STUDY ===== -->"):UI.index("<!-- Legacy study content")],
    ])
    assert "OPENROUTER_API_KEY" not in desktop_sources
    assert "NVIDIA_API_KEY" not in desktop_sources
    assert '"model":' not in _method("_ask_ai", "_generate_quiz")


def test_gateway_has_three_route_fallback_and_server_side_rate_limits():
    assert "primary" in PROVIDERS and "secondary" in PROVIDERS and "tertiary" in PROVIDERS
    assert "INSTALL_LIMITER" in GATEWAY
    assert "NETWORK_LIMITER" in GATEWAY
    assert "usage_limited" in GATEWAY
    assert "Provider and model selection are controlled by LecturePack" in GATEWAY
    assert "max_total_results: 3" in PROVIDERS
    assert "max_tool_calls = 1" in PROVIDERS


def test_gateway_usage_metadata_is_content_free_and_complete():
    migration = (ROOT / "ai-gateway" / "migrations" / "0001_init.sql").read_text(
        encoding="utf-8")
    storage = (ROOT / "ai-gateway" / "src" / "storage.js").read_text(
        encoding="utf-8")
    for field in (
        "installation_id", "task", "provider", "model", "input_tokens",
        "output_tokens", "latency_ms", "result", "failure_code", "retryable",
        "attempt_number", "request_id", "created_at",
    ):
        assert field in migration
    schema_sql = "\n".join(
        line for line in migration.splitlines() if not line.lstrip().startswith("--"))
    assert not re.search(r"\b(?:transcript|prompt|completion|slide_image)\w*\s+TEXT\b",
                         schema_sql, re.I)
    assert "event.prompt" not in storage
    assert "event.completion" not in storage


def test_settings_privacy_copy_describes_study_gateway_honestly():
    assert "Local lecture processing." in UI
    assert "selected transcript and accepted-slide evidence" in UI
    assert "anonymous service-health metadata" in UI
    assert "Local processing · Private by design · No account" in UI
    assert "grounded explanations and linked evidence" in UI
    assert "10 seconds · bundled demo" in UI
    assert "100% local." not in UI
    assert "entirely on your machine" not in UI
    assert "all on this machine" not in UI
    assert "10 seconds · local only" not in UI


def test_web_citations_are_openable_and_lecture_sources_are_navigable():
    assert 'target="_blank" rel="noopener noreferrer"' in APP
    assert "study-web-source" in APP
    assert "data-segment" in APP and "data-slide" in APP
    assert "navigateStudySource" in APP


def test_ask_does_not_persist_generic_chat_history():
    method = _method("_ask_ai", "_generate_quiz")
    assert "append_chat_message" not in method
    assert "history" not in method
    assert "ai_study_service.ask" in method


def test_owner_alert_is_payload_free_and_defaults_to_requested_owner():
    start = GATEWAY.index("async function sendOwnerAlert")
    end = GATEWAY.index("export default", start)
    alert = GATEWAY[start:end]
    assert "discordsammy2@gmail.com" in alert
    assert "No transcript, prompt, response, slide image, token, or provider secret" in alert
    assert "alert.transcript" not in alert
    assert "alert.prompt" not in alert
    assert "alert.response" not in alert


def test_packaged_desktop_contains_no_literal_provider_credentials():
    roots = [ROOT / "app", ROOT / "electron-spike", ROOT / "lecturepack"]
    suspicious = re.compile(
        r"(?:sk-or-v1-[A-Za-z0-9_-]{20,}|nvapi-[A-Za-z0-9_-]{20,}|re_[A-Za-z0-9]{24,})")
    hits = []
    for base in roots:
        for path in base.rglob("*"):
            if {"node_modules", "__pycache__", "dist", "build"}.intersection(path.parts):
                continue
            if path.suffix.lower() not in {".py", ".js", ".json", ".html", ".css", ".spec"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if suspicious.search(text):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []
