"""The self-contained demo screen (AD-47).

The old demo was a spotlight overlay that measured the live application UI at
runtime. Eight separate bugs were fixed in it and it was still not usable,
because the premise was the defect: a tour that measures the live UI is a
second renderer for your layout, and it breaks every time any screen changes.
Study V2 broke it and nobody noticed until a user did.

These tests pin the properties that make the replacement safe, not its copy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
ASSETS = ROOT / "app" / "assets" / "demo"
HTML = (UI / "index.html").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "app.css").read_text(encoding="utf-8")


def _demo_module() -> str:
    start = JS.index("var DEMO_KEY")
    return JS[start:JS.index("  function boot() {", start)]


def test_demo_is_a_screen_and_measures_nothing() -> None:
    """The whole point: no geometry, no spotlight, no live-UI coupling."""
    assert 'data-screen="demo"' in HTML

    module = _demo_module()
    for banned in (
        "getBoundingClientRect",   # measuring the live UI is the original sin
        "tour-dim",                # no scrim rectangles to tile or overlap
        "positionTourSpotlight",
        "positionTourCard",
        "window.innerWidth",
        "window.innerHeight",
        "requestAnimationFrame",   # nothing to re-measure per frame
    ):
        assert banned not in module, f"demo module must not use {banned}"


def test_demo_data_is_script_loaded_not_fetched() -> None:
    """`fetch()` of a sibling file is blocked under file://.

    The renderer is loaded with Electron's `loadFile`, i.e. the file://
    protocol with web security on. An earlier version of this screen used
    `fetch('../assets/demo/demo.json')`; it failed silently on EVERY launch,
    including the packaged app, and degraded to the fallback each time. A
    script tag is not subject to that, so the demo cannot fail to load its own
    data.
    """
    assert '<script src="../assets/demo/demo.data.js">' in HTML
    module = _demo_module()
    # Ignore comments -- the code comment here explains why fetch is absent.
    code = "\n".join(
        line for line in module.splitlines()
        if not line.lstrip().startswith(("//", "/*", "*"))
    )
    assert "fetch(" not in code, "the demo must not fetch its data"
    assert "window.LP_DEMO_DATA" in code

    data_js = (ASSETS / "demo.data.js").read_text(encoding="utf-8")
    assert data_js.lstrip().startswith("/*")
    payload = json.loads(data_js.split("window.LP_DEMO_DATA =", 1)[1].rstrip().rstrip(";"))
    for key in ("source", "slides", "lines", "card", "quiz"):
        assert key in payload, f"demo data is missing {key}"
    assert payload["slides"], "demo data has no slides"
    for slide in payload["slides"]:
        assert (ASSETS / slide["img"]).is_file(), f"missing bundled slide {slide['img']}"
    assert (ASSETS / "hero.png").is_file()
    # The answer must be a real index into the options.
    assert 0 <= payload["quiz"]["answer"] < len(payload["quiz"]["options"])


def test_every_chapter_survives_missing_data() -> None:
    """A missing asset degrades one artifact; it never blanks the demo.

    The copy is the payload and the artifact only illustrates it, so the demo
    still explains the product and both hand-off CTAs still work.
    """
    module = _demo_module()
    assert "function demoFallback(" in module
    assert "if (!demoData) {" in module
    assert ".lp-demo-fallback" in CSS
    # The hero is the one <img> not inside a fallback-able container.
    assert "hero.onerror" in module

    chapters = re.findall(r'data-ch="(\d+)"', HTML)
    assert len(chapters) == 5, f"expected 5 chapters, found {chapters}"


def test_demo_does_not_run_the_pipeline_and_hands_off_explicitly() -> None:
    """Processing happens AFTER the walkthrough, from an explicit button.

    Running the pipeline up front needs ffprobe and a Whisper model, takes tens
    of seconds and can fail -- and a failure there reads as the PRODUCT
    failing, on a first impression. So the demo shows pre-baked real output and
    offers to process for real once the student knows what the stages mean.
    """
    module = _demo_module()
    assert "function runDemoForReal()" in module
    assert "lpBridge.startDemoJob()" in module
    # The walkthrough itself must not start a job.
    walkthrough = module[:module.index("function runDemoForReal()")]
    assert "startDemoJob" not in walkthrough

    assert 'id="btn-demo-run"' in HTML
    assert 'id="btn-demo-own"' in HTML
    assert 'id="btn-demo-skip"' in HTML


def test_demo_styling_obeys_AD_20() -> None:
    """No compositor-expensive effects: confirmed flicker on clean-install Windows."""
    block = CSS.split("--- guided demo (self-contained screen)", 1)[1]
    for banned in ("will-change", "filter:blur", "backdrop-filter", "100vmax", "9999px"):
        assert banned not in block, f"AD-20: {banned} must not appear in demo styling"
    assert "animation:" not in block, "AD-20: no animation on the demo surface"


def test_quiz_does_not_reveal_its_answer_before_the_student_answers() -> None:
    module = _demo_module()
    render = module[module.index("demo-quiz-opts"):]
    render = render[:render.index("}).join('');")]
    assert "data-correct" not in render, "the correct option must not be marked at render time"
    assert 'data-state="correct"' in CSS
