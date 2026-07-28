"""Home multi-select (bulk delete / group) and the sidebar poster thumbnail.

Bulk operations must reuse the SAME recycle-bin-first path as a single delete,
emit ONE summary signal and do ONE list refresh per batch, and survive partial
failure. Temp data dir throughout; never real LecturePackData.
"""

from __future__ import annotations

import json
import os
import re
import sys

import pytest
from PySide6.QtCore import QObject

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "app", "ui", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "app", "ui", "index.html"), encoding="utf-8").read()
BRIDGE_PY = open(os.path.join(ROOT, "app", "desktop", "bridge.py"), encoding="utf-8").read()


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _Backend:
    _NAMES = ("job_deleted", "jobs_changed", "storage_changed", "log_line", "active_job")

    def __init__(self):
        for n in self._NAMES:
            setattr(self, n, _Signal())

    def last(self, name):
        em = getattr(self, name).emissions
        return json.loads(em[-1]) if em else None

    def count(self, name):
        return len(getattr(self, name).emissions)


class _Host:
    """Minimal host for the bulk methods under test."""
    _JOB_SCOPED_SIGNALS = ea.LecturePackAdapter._JOB_SCOPED_SIGNALS
    _emit = ea.LecturePackAdapter._emit
    _delete_one = ea.LecturePackAdapter._delete_one
    delete_job = ea.LecturePackAdapter.delete_job
    delete_jobs = ea.LecturePackAdapter.delete_jobs
    set_jobs_group = ea.LecturePackAdapter.set_jobs_group

    def __init__(self, backend, data_dir):
        self.backend = backend
        self.data_dir = str(data_dir)
        self.current_job = None
        self.pushes = 0
        self.reloads = 0
        self.grouped = []

    # --- collaborators stubbed so the unit under test stays the bulk logic ---
    def _job_dir_guarded(self, job_id):
        d = os.path.join(self.data_dir, "jobs", job_id)
        return d if os.path.isdir(d) else None

    def _dir_size(self, path):
        return 1000

    def _log(self, *a, **k):
        pass

    def _set_active_job(self, job):
        self.current_job = job

    def _push_jobs(self):
        self.pushes += 1

    def _load_latest_completed_job(self):
        self.reloads += 1

    def _set_job_group_quiet(self, job_id, group):
        self.grouped.append((job_id, group))
        return True


@pytest.fixture()
def host(tmp_path, monkeypatch):
    # send2trash would really recycle; keep deletion inside tmp_path
    monkeypatch.setattr(ea.shutil, "rmtree", lambda p, **k: os.rmdir(p))
    monkeypatch.setitem(sys.modules, "send2trash", None)   # force the rmtree path
    h = _Host(_Backend(), tmp_path)
    for jid in ("a", "b", "c"):
        os.makedirs(os.path.join(str(tmp_path), "jobs", jid))
    return h


# --------------------------------------------------------------- bulk delete

def test_bulk_delete_removes_every_selected_job(host):
    host.delete_jobs(json.dumps(["a", "b"]))
    assert not os.path.isdir(os.path.join(host.data_dir, "jobs", "a"))
    assert not os.path.isdir(os.path.join(host.data_dir, "jobs", "b"))
    assert os.path.isdir(os.path.join(host.data_dir, "jobs", "c"))   # untouched


def test_bulk_delete_emits_one_summary_and_refreshes_once(host):
    host.delete_jobs(json.dumps(["a", "b"]))
    assert host.backend.count("job_deleted") == 1, "one summary signal per batch"
    assert host.pushes == 1, "one list refresh per batch"
    d = host.backend.last("job_deleted")
    assert d["bulk"] is True and d["ok"] is True
    assert d["count"] == 2 and sorted(d["ids"]) == ["a", "b"]
    assert d["failed"] == []
    assert d["freed"]


def test_bulk_delete_reports_partial_failure_without_losing_the_rest(host):
    host.delete_jobs(json.dumps(["a", "does-not-exist"]))
    d = host.backend.last("job_deleted")
    assert d["ok"] is True                      # 'a' did get deleted
    assert d["ids"] == ["a"]
    assert d["failed"] == ["does-not-exist"]
    assert not os.path.isdir(os.path.join(host.data_dir, "jobs", "a"))


def test_bulk_delete_with_empty_selection_is_a_safe_noop(host):
    host.delete_jobs(json.dumps([]))
    d = host.backend.last("job_deleted")
    assert d["ok"] is False and d["count"] == 0
    assert host.pushes == 0
    assert os.path.isdir(os.path.join(host.data_dir, "jobs", "a"))


@pytest.mark.parametrize("bad", ["", "not json", "{", None])
def test_bulk_delete_survives_malformed_input(host, bad):
    host.delete_jobs(bad)
    assert host.backend.last("job_deleted")["ok"] is False
    assert os.path.isdir(os.path.join(host.data_dir, "jobs", "a"))


def test_bulk_delete_ignores_blank_ids(host):
    host.delete_jobs(json.dumps(["", None, "a"]))
    assert host.backend.last("job_deleted")["ids"] == ["a"]


def test_deleting_the_active_lecture_clears_it_and_reloads_once(host):
    class J:
        job_id = "a"
    host.current_job = J()
    host.delete_jobs(json.dumps(["a", "b"]))
    assert host.current_job is None
    assert host.reloads == 1, "reload the latest lecture once, not per job"


def test_bulk_delete_does_not_reload_when_active_job_untouched(host):
    class J:
        job_id = "c"
    host.current_job = J()
    host.delete_jobs(json.dumps(["a", "b"]))
    assert host.reloads == 0
    assert host.current_job is not None


def test_single_delete_still_emits_the_non_bulk_shape(host):
    host.delete_job("a")
    d = host.backend.last("job_deleted")
    assert d["ok"] is True and d["id"] == "a"
    assert "bulk" not in d          # the UI branches on this
    assert host.pushes == 1


def test_single_delete_of_unknown_job_reports_failure(host):
    host.delete_job("nope")
    assert host.backend.last("job_deleted") == {"ok": False, "id": "nope"}
    assert host.pushes == 0


def test_single_and_bulk_share_one_deletion_path():
    """Both must go through _delete_one, so the recycle-bin-first behaviour and
    the active-job handling can never diverge."""
    src = open(os.path.join(ROOT, "app", "desktop", "engine_adapter.py"),
               encoding="utf-8").read()
    # scope to the CONCRETE adapter -- the base class holds abstract stubs with
    # the same method names
    impl = src.split("class LecturePackAdapter", 1)[1]
    for fn in ("def delete_job(", "def delete_jobs("):
        body = impl.split(fn, 1)[1].split("\n    def ", 1)[0]
        assert "_delete_one(" in body, f"{fn} does not use the shared path"
        assert "send2trash" not in body, f"{fn} reimplements deletion"


# ---------------------------------------------------------------- bulk group

def test_bulk_group_applies_to_every_id_with_one_refresh(host):
    host.set_jobs_group(json.dumps(["a", "b"]), "CL100")
    assert host.grouped == [("a", "CL100"), ("b", "CL100")]
    assert host.pushes == 1


def test_bulk_group_survives_malformed_input(host):
    host.set_jobs_group("not json", "CL100")
    assert host.grouped == []


def test_single_group_delegates_to_the_quiet_helper():
    src = open(os.path.join(ROOT, "app", "desktop", "engine_adapter.py"),
               encoding="utf-8").read()
    body = src.split("def set_job_group(self, job_id: str, group: str) -> None:", 2)[-1]
    assert "_set_job_group_quiet(" in body


# ------------------------------------------------------------------- bridge

def test_bridge_exposes_bulk_slots():
    assert "def delete_jobs" in BRIDGE_PY
    assert "def set_jobs_group" in BRIDGE_PY
    assert "@Slot(str)" in BRIDGE_PY and "@Slot(str, str)" in BRIDGE_PY


# ------------------------------------------------------------- UI: selection

def test_select_mode_controls_exist():
    for el in ("btn-select-mode", "jobs-selectbar", "jobs-selcount",
               "btn-select-all", "btn-select-none", "btn-bulk-group",
               "btn-bulk-delete", "btn-select-done"):
        assert f'id="{el}"' in HTML, f"missing #{el}"


def test_select_bar_starts_hidden():
    m = re.search(r'<div id="jobs-selectbar"([^>]*)>', HTML)
    assert m and "hidden" in m.group(1)


def test_select_mode_owns_the_card_click():
    """A plain click must still open a lecture; only select mode intercepts."""
    block = JS.split("$('jobs-grid').addEventListener('click'", 1)[1][:520]
    assert "if (LP.state.selecting)" in block
    assert block.index("LP.state.selecting") < block.index(".lp-jobbtn")


def test_selection_state_declared():
    assert re.search(r"selecting:\s*false", JS)
    assert re.search(r"selected:\s*\{\}", JS)


def test_bulk_actions_go_through_one_bridge_call_each():
    assert "lpBridge.call('delete_jobs', JSON.stringify(ids))" in JS
    assert "lpBridge.call('set_jobs_group', JSON.stringify(ids)" in JS


def test_bulk_delete_is_confirmed_before_acting():
    body = JS.split("function bulkDelete", 1)[1].split("\n  }", 1)[0]
    assert "lpModal(" in body
    assert "danger: true" in body
    assert body.index("lpModal(") < body.index("delete_jobs")


def test_bulk_delete_handler_prunes_state_and_reports_failures():
    block = JS.split("lpBridge.on('job_deleted'", 1)[1][:1100]
    assert "if (d.bulk)" in block
    assert "delete LP.byJob[id]" in block
    assert "delete LP.state.selected[id]" in block
    assert "could not be deleted" in block


def test_selection_pruned_when_jobs_disappear():
    block = JS.split("lpBridge.on('jobs_changed'", 1)[1][:700]
    assert "delete LP.state.selected[id]" in block


def test_exiting_select_mode_clears_the_selection():
    body = JS.split("function setSelectMode", 1)[1].split("\n  }", 1)[0]
    assert "if (!on) LP.state.selected = {}" in body


# ---------------------------------------------------------- UI: side poster

def test_sidebar_chip_has_a_poster_slot_over_the_icon():
    assert 'id="side-job-thumb"' in HTML
    assert 'id="side-job-poster"' in HTML
    assert "data-side-ph" in HTML, "icon fallback placeholder missing"
    m = re.search(r'<img id="side-job-poster"([^>]*)>', HTML)
    assert m and "hidden" in m.group(1), "poster must start hidden"


def test_sidebar_poster_uses_the_same_poster_source_as_cards():
    body = JS.split("function renderSidePoster", 1)[1].split("\n  }", 1)[0]
    assert "posterSrc(" in body


def test_sidebar_poster_falls_back_to_the_icon_on_error():
    body = JS.split("function renderSidePoster", 1)[1].split("\n  }", 1)[0]
    assert "img.onerror" in body
    assert "placeholder.hidden = false" in body


def test_job_chrome_renders_the_side_poster():
    body = JS.split("function renderJobChrome", 1)[1].split("\n  }", 1)[0]
    assert "renderSidePoster(LP.state.jobId)" in body


def test_reset_clears_the_side_poster():
    body = JS.split("function resetJobChrome", 1)[1].split("\n  }", 1)[0]
    assert "renderSidePoster('')" in body
