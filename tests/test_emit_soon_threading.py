"""BUG-09: signals marshalled from worker threads never reached the UI.

``LecturePackAdapter._emit_soon`` is the only path by which the link-import
worker threads (probe / download progress / done) talk to the UI. It used
``QTimer.singleShot(0, functor)`` with NO context object.

That overload starts the timer *in the calling thread*. The callers are plain
``threading.Thread`` workers with no Qt event loop, so the timer never fired,
the functor was never invoked, and the signal was never emitted. The symptom
was a permanently-stuck "Looking it up..." spinner with an EMPTY stderr --
nothing raised, because the worker's own try/except had already succeeded.

These tests exercise the real method against a real QObject, from a real
worker thread, so the regression cannot come back silently.
"""

from __future__ import annotations

import os
import re
import sys
import threading

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

ADAPTER_SRC = os.path.join(APP_DIR, "desktop", "engine_adapter.py")


def test_qtimer_singleshot_without_context_never_fires_from_a_plain_thread():
    """Documents WHY the context argument is load-bearing rather than style.

    If a future Qt/PySide release makes the bare overload work cross-thread,
    this test fails and the comment in _emit_soon can be revisited.
    """
    from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    class _B(QObject):
        sig = Signal(str)

    b = _B()
    got = []
    b.sig.connect(got.append)

    threading.Thread(
        target=lambda: QTimer.singleShot(0, lambda: b.sig.emit("no-context")),
        daemon=True,
    ).start()
    threading.Thread(
        target=lambda: QTimer.singleShot(0, b, lambda: b.sig.emit("with-context")),
        daemon=True,
    ).start()

    QTimer.singleShot(1500, app.quit)
    app.exec()

    assert "with-context" in got, "context overload must deliver to the main thread"
    assert "no-context" not in got, (
        "bare overload unexpectedly delivered -- if PySide changed, revisit BUG-09")


def test_emit_soon_delivers_from_a_worker_thread():
    """The real _emit_soon, called off-thread, must reach a main-thread slot."""
    from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

    from desktop.engine_adapter import LecturePackAdapter

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    class _Backend(QObject):
        media_probe = Signal(str)

    backend = _Backend()
    received = []
    backend.media_probe.connect(received.append)

    # Bind only the method under test; constructing a full adapter would drag
    # in the engine, config and job store for a two-line function.
    holder = type("_H", (), {"backend": backend})()
    emit_soon = LecturePackAdapter._emit_soon.__get__(holder, type(holder))

    threading.Thread(
        target=lambda: emit_soon(backend.media_probe, {"ok": True, "title": "x"}),
        daemon=True,
    ).start()

    QTimer.singleShot(1500, app.quit)
    app.exec()

    assert received, "_emit_soon dropped the payload (BUG-09 regression)"
    assert '"ok": true' in received[0].lower()


def test_no_worker_thread_singleshot_lacks_a_context_object():
    """Static guard: inside the link-import worker closures, every
    QTimer.singleShot(0, ...) must pass a context QObject as the 2nd arg.

    A bare `QTimer.singleShot(0, lambda ...)` there is the exact BUG-09 shape.
    """
    src = open(ADAPTER_SRC, encoding="utf-8").read()

    # The two media worker methods are where plain threads are started.
    offenders = []
    for m in re.finditer(r"QTimer\.singleShot\(\s*0\s*,\s*([^,)]+)", src):
        second = m.group(1).strip()
        if second.startswith("lambda") or second.startswith("_go"):
            line = src[:m.start()].count("\n") + 1
            offenders.append((line, second[:40]))

    allowed_lines = _lines_reached_only_from_the_main_thread(src)
    real = [o for o in offenders if o[0] not in allowed_lines]
    assert not real, (
        "QTimer.singleShot(0, ...) without a context object at: "
        + ", ".join(f"line {ln} ({txt})" for ln, txt in real))


def _lines_reached_only_from_the_main_thread(src: str) -> set:
    """`_promote_next` runs as a Qt slot connected to controller signals, so it
    is already on the main thread and its bare singleShot is correct."""
    allowed = set()
    for m in re.finditer(r"QTimer\.singleShot\(\s*0\s*,\s*_go\s*\)", src):
        allowed.add(src[:m.start()].count("\n") + 1)
    return allowed
