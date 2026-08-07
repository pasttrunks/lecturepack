"""Job-scoped workspace state + payload freshness guard.

The workspace screens (Process/Review/Transcript/Study/Exports) belong to ONE
lecture. Two mechanisms enforce that:

1. ownership -- LP.state.jobId decides what renders; "nothing loaded" is
   structurally empty, driven by the backend's active_job signal.
2. freshness -- every job-scoped payload is stamped with its owning job id, so
   a signal that arrives after the user switched lectures is dropped instead of
   silently repainting the previous lecture's data.

Backend half is asserted directly; the UI half is asserted statically here and
was verified behaviourally in a browser.
"""

from __future__ import annotations

import json
import os
import re
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from PySide6.QtCore import QObject

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()
BRIDGE_JS = open(os.path.join(ROOT, "app", "ui", "bridge.js"), encoding="utf-8").read()
BRIDGE_PY = open(os.path.join(ROOT, "app", "desktop", "bridge.py"), encoding="utf-8").read()


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _Backend:
    _NAMES = ("active_job", "pipeline_changed", "slides_changed",
              "transcript_changed", "study_changed", "quiz_changed",
              "flashcards_changed", "export_progress", "export_done",
              "post_completion", "log_line", "jobs_changed", "storage_changed",
              "status_changed", "settings_changed", "job_deleted")

    def __init__(self):
        for n in self._NAMES:
            setattr(self, n, _Signal())

    def last(self, name):
        em = getattr(self, name).emissions
        return json.loads(em[-1]) if em else None


class _Job:
    def __init__(self, job_id, title=""):
        self.job_id = job_id
        self.manifest = {"title": title}


class _Host:
    """Minimal host for the two adapter methods under test."""
    _JOB_SCOPED_SIGNALS = ea.LecturePackAdapter._JOB_SCOPED_SIGNALS
    _emit = ea.LecturePackAdapter._emit
    _set_active_job = ea.LecturePackAdapter._set_active_job

    def __init__(self, backend):
        self.backend = backend
        self.current_job = None


# ------------------------------------------------------- signal plumbing

def test_active_job_signal_declared_on_both_sides():
    assert "active_job = Signal(str)" in BRIDGE_PY
    assert "'active_job'" in BRIDGE_JS


def test_every_job_scoped_signal_is_a_real_backend_signal():
    for name in ea.LecturePackAdapter._JOB_SCOPED_SIGNALS:
        assert f"{name} = Signal(str)" in BRIDGE_PY, f"{name} not a Signal"


# ------------------------------------------------------- stamping (#2)

def test_emit_stamps_job_scoped_payloads_with_the_active_job():
    h = _Host(_Backend())
    h.current_job = _Job("job-a", "Lecture A")
    h._emit("slides_changed", {"slides": []})
    assert h.backend.last("slides_changed")["job"] == "job-a"


def test_emit_stamps_empty_string_when_no_job_is_active():
    h = _Host(_Backend())
    h._emit("transcript_changed", {"transcript": {}})
    assert h.backend.last("transcript_changed")["job"] == ""


def test_emit_does_not_stamp_app_wide_signals():
    h = _Host(_Backend())
    h.current_job = _Job("job-a")
    h._emit("jobs_changed", [{"id": "x"}])
    h._emit("settings_changed", {"export_dir": "d"})
    assert "job" not in h.backend.last("settings_changed")
    assert h.backend.last("jobs_changed") == [{"id": "x"}]


def test_emit_never_overwrites_an_explicit_job_field():
    h = _Host(_Backend())
    h.current_job = _Job("job-a")
    h._emit("study_changed", {"job": "job-b"})
    assert h.backend.last("study_changed")["job"] == "job-b"


def test_emit_leaves_string_payloads_untouched():
    h = _Host(_Backend())
    h.current_job = _Job("job-a")
    h._emit("slides_changed", '{"slides":[]}')
    assert h.backend.last("slides_changed") == {"slides": []}


def test_emit_does_not_mutate_the_callers_dict():
    h = _Host(_Backend())
    h.current_job = _Job("job-a")
    payload = {"slides": []}
    h._emit("slides_changed", payload)
    assert payload == {"slides": []}


# ------------------------------------------------------- ownership (#1)

def test_set_active_job_emits_id_and_title():
    h = _Host(_Backend())
    h._set_active_job(_Job("job-a", "Egypt & Archaeology"))
    assert h.backend.last("active_job") == {"id": "job-a",
                                           "title": "Egypt & Archaeology"}
    assert h.current_job.job_id == "job-a"


def test_set_active_job_none_clears_the_workspace():
    h = _Host(_Backend())
    h._set_active_job(_Job("job-a", "A"))
    h._set_active_job(None)
    assert h.backend.last("active_job") == {"id": "", "title": ""}
    assert h.current_job is None


def test_set_active_job_survives_a_broken_manifest():
    class Bad:
        job_id = "job-b"

        @property
        def manifest(self):
            raise RuntimeError("unreadable")
    h = _Host(_Backend())
    h._set_active_job(Bad())
    assert h.backend.last("active_job") == {"id": "job-b", "title": ""}


def test_all_current_job_assignments_route_through_the_setter():
    """Any direct assignment outside the setter would skip the active_job
    signal and desync the UI."""
    src = open(os.path.join(ROOT, "app", "desktop", "engine_adapter.py"),
               encoding="utf-8").read()
    body = src.split("def _set_active_job", 1)
    setter_region = body[1][:600] if len(body) > 1 else ""
    assignments = re.findall(r"self\.current_job = .+", src)
    inside_setter = re.findall(r"self\.current_job = .+", setter_region)
    assert len(assignments) == len(inside_setter) == 1, \
        "current_job must only be assigned inside _set_active_job"


# ------------------------------------------------------- UI contract

def test_ui_declares_job_ownership_state():
    assert re.search(r"jobId:\s*''", JS)
    assert "byJob: {}" in JS
    for fn in ("function setActiveJob", "function ownsPayload",
               "function emptyWorkspace", "function renderWorkspace"):
        assert fn in JS, f"missing {fn}"


def test_every_workspace_handler_routes_by_job_id():
    """Every job-scoped payload is routed to the workspace it belongs to
    (routeJobPayload), so a signal for a different lecture is never painted
    over the viewed one -- and is kept for when the user switches back."""
    for sig in ("pipeline_changed", "slides_changed", "transcript_changed",
                "study_changed", "quiz_changed", "flashcards_changed"):
        block = JS.split(f"lpBridge.on('{sig}'", 1)[1][:560]
        assert "routeJobPayload(" in block, f"{sig} handler has no job routing"


def test_ui_follows_active_job_signal():
    block = JS.split("lpBridge.on('active_job'", 1)[1].split("lpBridge.on('pipeline_changed'", 1)[0]
    assert "selectJob(" in block
    assert "autoSelectedActiveId" in block


def test_empty_workspace_covers_every_job_scoped_key():
    keys = re.search(r"var WORKSPACE_KEYS = \[(.*?)\];", JS, re.S).group(1)
    empty = JS.split("function emptyWorkspace", 1)[1].split("\n  }", 1)[0]
    for key in re.findall(r"'([a-zA-Z]+)'", keys):
        assert f"{key}:" in empty, f"emptyWorkspace() has no '{key}' default"


def test_switching_jobs_snapshots_then_applies():
    body = JS.split("function setActiveJob", 1)[1].split("\n  }", 1)[0]
    assert "snapshotWorkspace()" in body and "applyWorkspace(" in body
    assert "emptyWorkspace()" in body
    # per-lecture view state must be reset too, not just data
    assert "LP.state.chat = []" in body
    assert "LP.state.exportPhase = 'idle'" in body


def test_deleting_the_active_job_empties_the_workspace():
    handler = _job_deleted_handler()
    assert "delete LP.byJob[d.id]" in handler
    assert "setActiveJob('', '')" in handler
    # and the bulk branch drops each deleted lecture's cache entry too
    assert "delete LP.byJob[id]" in handler


def test_log_lines_are_dropped_when_no_lecture_is_loaded():
    block = JS.split("lpBridge.on('log_line'", 1)[1][:260]
    assert "if (!owner) return" in block


def test_status_changed_cannot_name_a_lecture_when_none_is_loaded():
    block = JS.split("function renderProcessingStatus()", 1)[1].split("// Main slide preview", 1)[0]
    assert "s.job !== undefined && LP.state.jobId" in block


# ------------------------------- regressions found during verification

def test_timeline_survives_an_empty_workspace():
    """renderTimeline indexed slides[v] unconditionally; with no lecture loaded
    that threw and aborted the whole renderWorkspace() pass, leaving the sidebar
    naming a lecture that was no longer active."""
    body = JS.split("function renderTimeline", 1)[1].split("\n  }", 1)[0]
    assert "LP.data.slides[v].pct" not in body, "unguarded slides[v] index is back"
    assert "at ? at.pct : 0" in body
    assert "No slides yet" in body


def test_chrome_renders_before_the_workspace():
    """Chrome must not be collateral damage if a workspace renderer throws."""
    body = JS.split("function setActiveJob", 1)[1].split("\n  }", 1)[0]
    assert body.index("renderJobChrome()") < body.index("renderWorkspace()")


def _job_deleted_handler():
    """The whole job_deleted handler body (it now has a bulk branch too)."""
    return JS.split("lpBridge.on('job_deleted'", 1)[1].split("\n    });", 1)[0]


def test_delete_deactivates_before_dropping_the_cache_entry():
    """setActiveJob snapshots the outgoing lecture into byJob, so deleting the
    cache entry first put it straight back. Must hold in BOTH branches."""
    handler = _job_deleted_handler()
    single = handler.split("if (d.bulk)", 1)[1].split("return;", 1)[1]
    assert single.index("setActiveJob('', '')") < single.index("delete LP.byJob[d.id]")

    bulk = handler.split("if (d.bulk)", 1)[1].split("return;", 1)[0]
    assert bulk.index("setActiveJob('', '')") < bulk.index("delete LP.byJob[id]"),         "bulk branch must deactivate before dropping the cache entry too"


def test_bridge_exposes_a_local_dispatch():
    assert "emit: function (name" in BRIDGE_JS
