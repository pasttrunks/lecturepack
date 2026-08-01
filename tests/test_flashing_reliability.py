"""Regression coverage for the beta 8 flashing diagnosis and beta 9 fixes."""

from __future__ import annotations

from pathlib import Path

from app.desktop.engine_adapter import LecturePackAdapter


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"


def read_ui(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


def test_theme_and_startup_surfaces_share_one_root_and_background_transaction():
    html = read_ui("index.html")
    js = read_ui("app.js")
    css = read_ui("app.css")
    main = (ROOT / "app" / "desktop" / "main.py").read_text(encoding="utf-8")

    assert '<html lang="en" data-theme="light">' in html
    assert 'id="app" data-theme=' not in html
    assert "document.documentElement.dataset.theme = theme" in js
    assert "document.documentElement.dataset.theme || 'light'" in js
    assert "document.documentElement.dataset.theme = " in main
    assert "document.getElementById('app').dataset.theme" not in main
    assert "body{width:100%;height:100vh;overflow-y:auto}" in css
    assert "self.backend.settings_changed.connect(self._sync_page_background)" in main
    assert "self.view.page().setBackgroundColor(QColor(color))" in main
    assert main.index("self.setCentralWidget(self.view)") < main.index("self.view.load(QUrl.fromLocalFile(index))")


def test_setup_gate_does_not_toggle_document_scroll_or_rebuild_unchanged_frames():
    js = read_ui("app.js")
    gate = js.split("var RuntimeSetupGate =", 1)[1].split("/* Clears", 1)[0]
    render = gate.split("function render(dataChanged) {", 1)[1].split("function closeOverlay", 1)[0]

    assert "document.documentElement.style.overflow" not in gate
    assert "if (!stateChanged && !dataChanged) return;" in render
    assert "lastRenderedState = next;" in render
    assert "LP.motion.close(el, finish)" in gate
    assert "updateFirstRunRow(host" in gate


def test_pipeline_and_status_handlers_preserve_live_dom_nodes():
    js = read_ui("app.js")
    pipeline = js.split("lpBridge.on('pipeline_changed'", 1)[1].split("lpBridge.on('log_line'", 1)[0]

    assert "schedulePipelineRender();" in pipeline
    assert "renderPipeline();" not in pipeline
    assert "if (logEl.innerHTML !== logHtml)" in js
    assert "setStatusDotText($('side-job-status'), s.side" in js
    assert "setStatusDotText($('ai-status'), txt, col, false)" in js


def test_backend_ignores_duplicate_progress_and_identical_pipeline_payloads():
    adapter = LecturePackAdapter.__new__(LecturePackAdapter)
    adapter._stages = [{
        "name": "Transcribe", "label": "Transcribe", "color": "#fff",
        "state": "pending", "pct": 0,
    }]
    adapter._pipeline_start = 0.0
    adapter._stage_timings = {}
    adapter._last_pipeline_payload = None
    adapter._last_stage_progress = {}
    adapter._demo_session = None

    class Window:
        def __init__(self):
            self.progress = []

        def on_progress(self, value):
            self.progress.append(value)

    adapter.win = Window()
    events = []
    adapter._emit = lambda signal, payload: events.append((signal, payload))

    adapter._render_pipeline(title="Transcribing", meta="steady")
    adapter._render_pipeline(title="Transcribing", meta="steady")
    assert [signal for signal, _ in events].count("pipeline_changed") == 1

    adapter._on_stage_started("Transcribe")
    adapter._on_stage_progress("Transcribe", 0)
    adapter._on_stage_progress("Transcribe", 20)
    adapter._on_stage_progress("Transcribe", 20)
    status_events = [payload for signal, payload in events if signal == "status_changed"]
    assert [payload["pct"] for payload in status_events] == [0, 20]
    assert adapter.win.progress == [20]
