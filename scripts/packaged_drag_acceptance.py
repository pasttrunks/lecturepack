"""Packaged-app acceptance gate for the internal drag layer (DEF-026 / DEF-029).

DEF-025 shipped dead in EVERY build because external file drop was only ever
verified in a browser.  DEF-026 is the same feature's third failure and was,
again, only verified in a real browser -- ``electron-spike/production-main.js``
loading ``app/ui`` straight from the worktree.  This script closes that exact
gap: it drives the internal drag on the FROZEN executable with trusted pointer
input, and asserts the drop actually landed rather than that nothing threw.

It reuses ``packaged_visual_acceptance`` for launching, the first-run runtime
gate, and the real import, then adds the one thing that harness has no route
for -- synthetic mouse input.  CDP ``Input.dispatchMouseEvent`` is used rather
than JS-dispatched events: Chromium synthesises TRUSTED pointer events from it,
so the ``pointerdown``/``pointermove``/``pointerup`` layer in app.js sees the
same input a hand would produce.  A ``new PointerEvent(...)`` from
``Runtime.evaluate`` would prove nothing -- an untrusted event can drive a
listener that a real gesture never reaches.

Usage (Windows, from the repository root)::

    python scripts/packaged_drag_acceptance.py

Data lives in a disposable profile.  The real LecturePackData directory is
never opened.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from packaged_visual_acceptance import (  # noqa: E402
    DEFAULT_EXE,
    DEFAULT_VIDEO,
    VisualRun,
    _activate,
    _set_saved_theme,
    iso_now,
)

LIFT_SLOP = 14  # app.js LIFT_THRESHOLD is smaller; overshoot it decisively.

ARMED_TARGET_JS = """
(() => {
  const el = document.querySelector('[data-lp-drop].lp-drop-ok, [data-lp-drop].lp-drop-candidate,'
    + ' [data-lp-drop].lp-drop-bad');
  return el ? (el.dataset.lpDrop || true) : false;
})()
"""

ANNOUNCEMENT_JS = """
(() => {
  const el = document.getElementById('lp-drag-strip');
  return el && !el.hidden ? (el.textContent || '').trim() : '';
})()
"""

INVENTORY_JS = """
(() => ({
  sources: document.querySelectorAll('[data-lp-drag]').length,
  targets: Array.from(document.querySelectorAll('[data-lp-drop]')).map(el => el.dataset.lpDrop)
}))()
"""

# The drag module (`LPDrag`) is closure-local and unreachable from Runtime.evaluate,
# so the lift is detected by what it puts on the page: beginDrag() adds
# `lp-drag-in-flight` to <body> and mounts a `.lp-drag-proxy` carried card.
DRAGGING_JS = """
(() => ({
  inFlight: document.body.classList.contains('lp-drag-in-flight'),
  proxy: !!document.querySelector('.lp-drag-proxy'),
  sourceMarked: !!document.querySelector('.lp-dragging')
}))()
"""


def _rect(run: VisualRun, selector: str) -> dict[str, float]:
    """Viewport-relative centre of an element, or {} when it is absent."""
    expression = (
        "(() => {"
        "  const el = document.querySelector(" + json.dumps(selector) + ");"
        "  if (!el) return null;"
        "  const r = el.getBoundingClientRect();"
        "  if (!r.width || !r.height) return null;"
        "  return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height};"
        "})()"
    )
    return run.cdp.evaluate(expression) or {}  # type: ignore[union-attr]


def _hit(run: VisualRun, x: float, y: float) -> dict[str, Any]:
    """What is actually under the press point.

    onPointerDown REFUSES to lift when the press lands on a real control
    (button/a/input/...), because a lift starting on Start or Remove would steal
    that click.  A failed lift is therefore ambiguous until this is known: it is
    either a broken drag or a test aiming at a button.
    """
    expression = (
        "(() => {"
        f"  const el = document.elementFromPoint({round(x)}, {round(y)});"
        "  if (!el) return null;"
        "  const ctl = el.closest('button, a, input, textarea, select, summary,"
        " [contenteditable], [data-selbox]');"
        "  return {tag: el.tagName, cls: (el.className || '').toString().slice(0, 80),"
        "          onGrip: !!el.closest('.lp-drag-grip'),"
        "          onControl: !!ctl,"
        "          controlCls: ctl ? (ctl.className || '').toString().slice(0, 60) : null,"
        "          inSource: !!el.closest('[data-lp-drag]')};"
        "})()"
    )
    return run.cdp.evaluate(expression) or {}  # type: ignore[union-attr]


def _mouse(run: VisualRun, kind: str, x: float, y: float) -> None:
    run.cdp.call(  # type: ignore[union-attr]
        "Input.dispatchMouseEvent",
        {
            "type": kind,
            "x": round(x),
            "y": round(y),
            "button": "left",
            "buttons": 1,
            "clickCount": 0 if kind == "mouseMoved" else 1,
            "pointerType": "mouse",
        },
    )


def _drag(
    run: VisualRun,
    source: str,
    target: str | None,
    *,
    target_point: tuple[float, float] | None = None,
    steps: int = 18,
) -> dict[str, Any]:
    """Lift `source` and release it over `target`, in small realistic steps.

    The step count matters: the layer only lifts after LIFT_THRESHOLD is
    exceeded, and auto-scroll (DEF-023, which regressed through this very code
    path) only updates on pointermove.  A single jump from A to B would skip
    both and pass while the real gesture is broken.
    """
    if target_point is not None:
        dst = {"x": target_point[0], "y": target_point[1]}
    else:
        dst = _rect(run, target or "")
        if not dst:
            raise AssertionError(f"drop target not present in the packaged app: {target}")

    # The card can sit below the fold, and CDP input is dispatched at VIEWPORT
    # coordinates -- pressing a rect that is scrolled out of view sends the
    # event into nothing and looks exactly like a dead drag.
    run.cdp.evaluate(  # type: ignore[union-attr]
        "(() => {const el = document.querySelector(" + json.dumps(source) + ");"
        " if (el) el.scrollIntoView({block: 'center', inline: 'center'}); return true;})()"
    )
    time.sleep(0.25)

    # Press the grip when the source has one. It exists only to be dragged, and
    # it is the single exception to the control guard -- a card's centre can
    # easily be a button, which the layer will (correctly) refuse to hijack.
    src = _rect(run, source + " .lp-drag-grip") or _rect(run, source)
    if not src:
        raise AssertionError(f"drag source not present in the packaged app: {source}")

    view = run.cdp.evaluate("({w: innerWidth, h: innerHeight})")  # type: ignore[union-attr]
    if not (0 <= src["x"] <= view["w"] and 0 <= src["y"] <= view["h"]):
        raise AssertionError(
            f"press point {src['x']:.0f},{src['y']:.0f} is outside the {view['w']}x{view['h']} "
            "viewport after scrollIntoView -- the gesture would be dispatched into nothing"
        )

    hit = _hit(run, src["x"], src["y"])
    if not hit:
        raise AssertionError(f"nothing is hit-testable at the press point {src['x']:.0f},{src['y']:.0f}")
    _mouse(run, "mousePressed", src["x"], src["y"])
    # Cross the lift threshold first, on the spot, so the lift is unambiguous.
    _mouse(run, "mouseMoved", src["x"] + LIFT_SLOP, src["y"] + LIFT_SLOP)
    time.sleep(0.05)
    lift = run.cdp.evaluate(DRAGGING_JS) or {}  # type: ignore[union-attr]

    for step in range(1, steps + 1):
        frac = step / steps
        _mouse(
            run,
            "mouseMoved",
            src["x"] + (dst["x"] - src["x"]) * frac,
            src["y"] + (dst["y"] - src["y"]) * frac,
        )
        time.sleep(0.02)

    armed = run.cdp.evaluate(ARMED_TARGET_JS)  # type: ignore[union-attr]
    _mouse(run, "mouseReleased", dst["x"], dst["y"])
    time.sleep(0.45)  # snapProxy flight; the action runs on arrival
    return {
        "lifted": bool(lift.get("inFlight") and lift.get("proxy")),
        "lift": lift,
        "armed": armed,
        "press_point": {"x": round(src["x"]), "y": round(src["y"])},
        "under_press": hit,
    }


def _dismiss_modal(run: VisualRun, label: str = "Cancel") -> dict[str, Any]:
    """Close an open lpModal by button label.

    Dropping an already-processed lecture on Process correctly raises the
    reprocess confirmation, and its scrim then covers the whole page -- a second
    gesture would press the scrim and look like a dead drag.  lpModal buttons
    carry no stable ids, so they are matched by their visible label.
    """
    expression = (
        "(() => {"
        "  const ov = document.querySelector('.lp-modal-ov');"
        "  if (!ov) return {modal: false};"
        "  const want = " + json.dumps(label.lower()) + ";"
        "  const btn = Array.from(ov.querySelectorAll('button'))"
        "    .find(b => (b.textContent || '').trim().toLowerCase() === want);"
        "  if (!btn) return {modal: true, clicked: false,"
        "    labels: Array.from(ov.querySelectorAll('button')).map(b => (b.textContent || '').trim())};"
        "  btn.click();"
        "  return {modal: true, clicked: true};"
        "})()"
    )
    result = run.cdp.evaluate(expression) or {}  # type: ignore[union-attr]
    time.sleep(0.35)
    result["still_open"] = bool(
        run.cdp.evaluate("!!document.querySelector('.lp-modal-ov')")  # type: ignore[union-attr]
    )
    return result


def _announcement(run: VisualRun) -> str:
    return run.cdp.evaluate(ANNOUNCEMENT_JS) or ""  # type: ignore[union-attr]


def main() -> int:
    ap = argparse.ArgumentParser(description="Packaged internal-drag acceptance gate")
    ap.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    ap.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    exe = args.exe.resolve()
    if not exe.is_file():
        ap.error(
            f"packaged executable not found: {exe}\n"
            "Build it: python scripts/release_build.py --no-installer"
        )
    video = args.video.resolve()
    if not video.is_file():
        ap.error(f"demo video not found: {video}")

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    output = (args.output or Path(tempfile.gettempdir()) / f"lecturepack-drag-acceptance-{stamp}").resolve()
    output.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "started_at": iso_now(),
        "executable": str(exe),
        "ok": False,
        "checks": [],
    }
    run = VisualRun(exe, video, output / "run", idle_seconds=0.0, keep_profile=False)
    run.output_dir.mkdir(parents=True, exist_ok=True)

    def check(name: str, passed: bool, detail: Any = None) -> None:
        report["checks"].append({"check": name, "pass": bool(passed), "detail": detail})

    try:
        _set_saved_theme("dark")
        run.stage = "launch"
        run.launch("drag-acceptance")
        run.wait_for(lambda m: m.get("readyState") == "complete", "packaged page", 60)

        run.stage = "first-run-setup"
        run.wait_for(lambda m: m.get("runtime", {}).get("checklist"), "first-run checklist", 90)
        # "Done" is the only control that clears the gate once every check is
        # ready; `#btn-runtime-confirm` ("Confirm & repair") stays disabled on a
        # healthy machine, and #btn-runtime-continue no longer exists at all.
        run.wait_for(
            lambda m: run.cdp.evaluate(  # type: ignore[union-attr]
                "(() => {const b = document.getElementById('btn-runtime-done');"
                " return !!(b && !b.disabled && (b.offsetWidth || b.offsetHeight));})()"
            ),
            "runtime checks ready (Done enabled)",
            180,
        )
        run.click("#btn-runtime-done")
        run.wait_for(lambda m: not m.get("runtime", {}).get("visible"), "setup gate cleared", 20)

        # A real lecture is required: the drag sources are library cards, and a
        # clean profile has none.  BUG-15 removed the fake seed lectures.
        run.stage = "real-import"
        run.import_and_process()
        report["processing"] = run.processing_result
        check(
            "real lecture present after import",
            bool(run.processing_result.get("ok")),
            run.processing_result,
        )

        _activate(run.hwnd)
        run.stage = "drag-lecture-to-process"
        run.click(".lp-nav[data-nav='home']")
        run.wait_for(lambda m: m.get("screen") == "home", "home before drag", 20)

        # Anything modal left over from the import/processing run covers the page,
        # so the first press would land on its scrim and read as a dead drag.
        # Record WHAT was open before clearing it -- an unexpected dialog here is a
        # product finding, not a harness detail.
        blocking = run.cdp.evaluate(  # type: ignore[union-attr]
            "(() => {"
            "  const ov = document.querySelector('.lp-modal-ov, .lp-scrim');"
            "  if (!ov) return null;"
            "  return {cls: (ov.className||'').toString().slice(0,60),"
            "          text: (ov.textContent||'').trim().slice(0,160),"
            "          buttons: Array.from(ov.querySelectorAll('button'))"
            "            .map(b => (b.textContent||'').trim()).filter(Boolean).slice(0,6)};"
            "})()"
        )
        report["modal_open_before_drag"] = blocking
        if blocking:
            for label in ("Cancel", "Close", "Done", "OK"):
                if _dismiss_modal(run, label).get("still_open") is False:
                    break
            run.cdp.evaluate(  # type: ignore[union-attr]
                "(() => {const ov = document.querySelector('.lp-modal-ov, .lp-scrim');"
                " if (ov && ov.parentNode) ov.parentNode.removeChild(ov); return true;})()"
            )

        inventory = run.cdp.evaluate(INVENTORY_JS)  # type: ignore[union-attr]
        report["inventory"] = inventory
        check("drag sources exist in the packaged DOM", bool(inventory.get("sources")), inventory)

        # DEF-026's core claim: a drop on the Process tab lands and is announced.
        gesture = _drag(run, "[data-lp-drag='lecture']", ".lp-nav[data-nav='process']")
        report["gesture_process"] = gesture
        check("card lifted on trusted pointer input", gesture["lifted"], gesture)

        said = _announcement(run)
        report["announcement_process"] = said
        check("drop on Process was announced, not silent", "queued for processing" in said.lower(), said)

        landed = run.wait_for(
            lambda m: m.get("screen") == "process" or bool(m.get("processing", {}).get("source")),
            "drop on Process took effect",
            20,
        )
        check(
            "drop on Process changed real app state",
            bool(landed),
            {"screen": landed.get("screen"), "source": landed.get("processing", {}).get("source")},
        )

        # Dropping an ALREADY-PROCESSED lecture on Process asks before replacing
        # its slides/transcript/Study pack. That confirmation is correct
        # behaviour, so assert it appeared, then decline it.
        modal = _dismiss_modal(run, "Cancel")

        # NOTE for whoever extends this gate: everything above proves the drop was
        # ANNOUNCED and QUEUED. That is not the same as processed, and the gap let
        # DEF-036 ship -- a queued lecture sat at "Queued" forever on an idle app
        # because nothing drained the queue unless another job had just ended.
        # The queue-actually-starts assertion lives below, after the confirmation
        # is accepted rather than declined.
        report["reprocess_confirmation"] = modal
        check("reprocess drop asked before replacing existing work", bool(modal.get("modal")), modal)
        check("confirmation dismissed cleanly", not modal.get("still_open"), modal)

        # The anti-silent-failure rule: a drop on NOTHING must say so.
        run.click(".lp-nav[data-nav='home']")
        run.wait_for(lambda m: m.get("screen") == "home", "home before null drop", 20)
        # Release over a point with no [data-lp-drop] ancestor, chosen inside the
        # viewport rather than from an element rect -- body's centre is usually
        # below the fold.
        dead = run.cdp.evaluate(  # type: ignore[union-attr]
            "(() => {"
            "  for (let y = 8; y < innerHeight; y += 17) {"
            "    for (let x = Math.round(innerWidth / 2); x < innerWidth - 4; x += 29) {"
            "      const el = document.elementFromPoint(x, y);"
            "      if (el && !el.closest('[data-lp-drop]') && !el.closest('[data-lp-drag]')) return {x, y};"
            "    }"
            "  }"
            "  return null;"
            "})()"
        )
        if not dead:
            raise AssertionError("no point outside every drop target was found in the viewport")
        report["null_drop_point"] = dead
        null_drop = _drag(run, "[data-lp-drag='lecture']", None, target_point=(dead["x"], dead["y"]))
        report["gesture_null"] = null_drop
        said_null = _announcement(run)
        report["announcement_null"] = said_null
        # Must LIFT and then be told it did not take. Accepting "never lifted"
        # here would let a completely dead drag satisfy the anti-silent-failure
        # check -- a green tick for the very bug it is meant to catch.
        check(
            "a drop on nothing reports failure out loud",
            bool(null_drop["lifted"]) and "not moved" in said_null.lower(),
            {"lifted": null_drop["lifted"], "said": said_null},
        )

        # DEF-036: queued is not processed. Drop on Process, ACCEPT the reprocess
        # confirmation this time, and require the pipeline to actually begin.
        run.stage = "queued-work-actually-starts"
        run.click(".lp-nav[data-nav='home']")
        run.wait_for(lambda m: m.get("screen") == "home", "home before start", 20)
        _drag(run, "[data-lp-drag='lecture']", ".lp-nav[data-nav='process']")
        accepted = _dismiss_modal(run, "Process again")
        report["reprocess_accepted"] = accepted

        started = {}
        deadline = time.time() + 120
        while time.time() < deadline:
            started = run.cdp.evaluate(  # type: ignore[union-attr]
                "(() => {"
                "  const f = document.getElementById('status-footer');"
                "  const q = (LP.data.queue && LP.data.queue.queue) || [];"
                "  return {status: f ? (f.dataset.status || '') : '',"
                "          label: (document.getElementById('status-state')||{}).textContent || '',"
                "          active: !!(LP.data.queue && LP.data.queue.active),"
                "          queued: q.length,"
                "          stages: document.querySelectorAll('#pipeline-stages .stage').length};"
                "})()"
            ) or {}
            if started.get("status") == "processing" or started.get("active"):
                break
            time.sleep(1.0)
        report["queue_started"] = started
        check(
            "a lecture dropped on Process actually STARTS, not just queues",
            started.get("status") == "processing" or bool(started.get("active")),
            started,
        )

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["stage"] = run.stage
    finally:
        try:
            run.finish()
        finally:
            run.cleanup_profile()
        report["ended_at"] = iso_now()
        report["ok"] = (
            bool(report["checks"])
            and all(c["pass"] for c in report["checks"])
            and "error" not in report
        )
        (output / "drag-acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": report["ok"],
                "error": report.get("error"),
                "checks": report["checks"],
                "evidence": str(output),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
