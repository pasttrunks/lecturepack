"""BUG-04 (remaining work): the backend disk-usage signal.

The sidebar storage widget shipped permanently hidden because nothing ever
reported disk usage, and the UI refuses to invent a figure -- inventing one
("340 MB" for every user, in every state) was the original bug. These tests
cover the signal that finally fills it, and the honesty rule around it:
**no usable measurement means the widget stays hidden, not that it guesses.**
"""

from __future__ import annotations

import json
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    def __init__(self):
        self.storage_changed = _Signal()

    def last(self):
        em = self.storage_changed.emissions
        return json.loads(em[-1]) if em else None


class _ImmediateThread:
    """Run the walk inline so assertions don't race the worker."""

    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self._t, self._a, self._k = target, args, kwargs or {}

    def start(self):
        if self._t:
            self._t(*self._a, **self._k)


class _Stub:
    push_storage = ea.LecturePackAdapter.push_storage
    _run_storage_walk = ea.LecturePackAdapter._run_storage_walk
    _emit_soon = ea.LecturePackAdapter._emit_soon
    _STORAGE_DEBOUNCE_MS = ea.LecturePackAdapter._STORAGE_DEBOUNCE_MS

    def __init__(self, backend, data_dir):
        self.backend = backend
        self.config = type("C", (), {"data_dir": str(data_dir)})()


@pytest.fixture()
def stub(tmp_path, monkeypatch):
    monkeypatch.setattr(ea.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(ea.QTimer, "singleShot",
                        staticmethod(lambda ms, *a: a[-1]()))
    return _Stub(_FakeBackend(), tmp_path)


def test_reports_real_bytes_for_the_data_dir(stub, tmp_path):
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "a.bin").write_bytes(b"x" * 5000)
    (tmp_path / "config.json").write_bytes(b"y" * 1000)

    stub.push_storage()
    got = stub.backend.last()

    assert got["ok"] is True
    # Exact, not approximate: this is a measurement, and the whole point of
    # BUG-04 is that the number must be real.
    assert got["used"] == 6000
    assert got["free_h"] and got["used_h"]
    assert 0.0 <= got["pct"] <= 100.0


def test_empty_data_dir_reports_zero_not_a_fabricated_figure(stub):
    stub.push_storage()
    got = stub.backend.last()
    assert got["ok"] is True and got["used"] == 0


def test_walk_survives_a_file_vanishing_mid_scan(stub, tmp_path, monkeypatch):
    """Jobs get deleted while the UI is open; a racing walk must not crash."""
    (tmp_path / "gone.bin").write_bytes(b"z" * 10)

    real_getsize = os.path.getsize

    def flaky(path):
        if path.endswith("gone.bin"):
            raise OSError("vanished")
        return real_getsize(path)

    monkeypatch.setattr(ea.os.path, "getsize", flaky)
    stub.push_storage()
    got = stub.backend.last()
    assert got["ok"] is True and got["used"] == 0


def test_failure_reports_not_ok_so_the_widget_stays_hidden(stub, monkeypatch):
    monkeypatch.setattr(ea.shutil, "disk_usage",
                        lambda p: (_ for _ in ()).throw(OSError("no such drive")))
    stub.push_storage()
    got = stub.backend.last()
    assert got["ok"] is False, "a failed measurement must not report a figure"


def test_demo_adapter_reports_not_ok(tmp_path):
    """The preview/demo adapter has no real data dir -- it must decline."""
    b = _FakeBackend()
    ea.EngineAdapter(b).push_storage()
    assert b.last() == {"ok": False}


def test_ui_hides_the_widget_unless_ok():
    """The handler must gate on ok, not merely on the signal arriving."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "app", "ui", "app.js"), encoding="utf-8").read()
    assert "storage_changed" in js, "UI never listens for the signal"
    handler = js.split("storage_changed", 1)[1][:600]
    assert "s.ok" in handler and "hidden = true" in handler


def test_a_burst_of_job_changes_causes_exactly_one_walk(tmp_path, monkeypatch):
    """BUG-13: bulk delete / queue promotion fire jobs_changed several times in
    a row. Each one used to launch its own full os.walk of the data root on an
    unbounded thread. They must coalesce into a single measurement."""
    (tmp_path / "a.bin").write_bytes(b"x" * 100)

    walks = []
    real_walk = os.walk
    monkeypatch.setattr(ea.os, "walk", lambda p: (walks.append(p), real_walk(p))[1])

    # Capture the debounced callback instead of firing it, so a burst can be
    # delivered before the timer would have elapsed -- that is the real case.
    scheduled = []
    monkeypatch.setattr(ea.QTimer, "singleShot",
                        staticmethod(lambda ms, *a: scheduled.append(a[-1])))
    monkeypatch.setattr(ea.threading, "Thread", _ImmediateThread)

    s = _Stub(_FakeBackend(), tmp_path)
    for _ in range(10):
        s.push_storage()

    assert len(scheduled) == 1, f"burst armed {len(scheduled)} timers, expected 1"
    scheduled[0]()                       # the debounce elapses
    assert len(walks) == 1, f"{len(walks)} walks for one burst, expected 1"


def test_a_walk_already_running_is_not_stacked(tmp_path, monkeypatch):
    """A second measurement must never run concurrently with the first."""
    monkeypatch.setattr(ea.QTimer, "singleShot", staticmethod(lambda ms, *a: a[-1]()))
    monkeypatch.setattr(ea.threading, "Thread", _ImmediateThread)
    s = _Stub(_FakeBackend(), tmp_path)

    s._storage_inflight = True           # pretend a walk is in progress
    walks = []
    monkeypatch.setattr(ea.os, "walk", lambda p: walks.append(p) or iter(()))
    s._storage_timer_armed = False
    s._run_storage_walk()
    assert walks == [], "started a second concurrent walk"


def test_inflight_flag_clears_even_when_the_walk_fails(tmp_path, monkeypatch):
    """A failed walk must not wedge the widget for the rest of the session."""
    monkeypatch.setattr(ea.QTimer, "singleShot", staticmethod(lambda ms, *a: a[-1]()))
    monkeypatch.setattr(ea.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(ea.shutil, "disk_usage",
                        lambda p: (_ for _ in ()).throw(OSError("boom")))
    s = _Stub(_FakeBackend(), tmp_path)
    s.push_storage()
    assert s._storage_inflight is False


def test_signal_is_declared_on_the_bridge():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = open(os.path.join(root, "app", "desktop", "bridge.py"), encoding="utf-8").read()
    assert "storage_changed = Signal(str)" in py
