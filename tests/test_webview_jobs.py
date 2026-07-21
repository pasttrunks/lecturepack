"""Home job management: delete (user-confirmed) and course/subject grouping.

Exercises the adapter logic against a TEMP data dir with copied/fake job
structures — never the real ~/LecturePackData. send2trash is monkeypatched to a
plain rmtree so tests don't move anything into the real OS Recycle Bin.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import engine_adapter as ea  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    def __init__(self):
        for name in ("log_line", "jobs_changed", "job_deleted"):
            setattr(self, name, _Signal())


def _adapter(tmp_path):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(str(tmp_path))
    a.backend = _FakeBackend()
    a.current_job = None
    return a


def _make_job(data_dir, job_id, title="CL100 - Day 3 - Mesopotamia", group=None):
    root = os.path.join(data_dir, "jobs", job_id)
    os.makedirs(os.path.join(root, "frames", "candidates"), exist_ok=True)
    man = {"schema_version": 1, "job_id": job_id, "created_at": "2026-01-01T00:00:00",
           "title": title, "source": {"filename": "lecture.mp4"}}
    if group is not None:
        man["group"] = group
    with open(os.path.join(root, "manifest.json"), "w") as fh:
        json.dump(man, fh)
    with open(os.path.join(root, "state.json"), "w") as fh:
        json.dump({"stages": {}, "overall_status": "completed"}, fh)
    with open(os.path.join(root, "source.json"), "w") as fh:
        json.dump({"duration": 100.0}, fh)
    # a byte of "content" so freed-size is non-zero
    with open(os.path.join(root, "frames", "candidates", "slide_1.png"), "wb") as fh:
        fh.write(b"x" * 2048)
    return root


# ------------------------------------------------------------- group derivation
@pytest.mark.parametrize("title,expected", [
    ("CL100 - Day 3 - Mesopotamia", "CL100"),
    ("PHYS101 lecture two", "PHYS101"),
    ("Biology: cells", "Biology"),
    ("Solo", "Solo"),
    ("", "Ungrouped"),
])
def test_derive_group(title, expected):
    assert ea._derive_group(title) == expected


def test_list_jobs_includes_group(tmp_path):
    _make_job(str(tmp_path), "jobA", title="CL100 - Day 1 - Intro")
    _make_job(str(tmp_path), "jobB", title="Custom", group="History 200")
    a = _adapter(tmp_path)
    rows = {r["id"]: r for r in a._list_jobs()}
    assert rows["jobA"]["group"] == "CL100"        # derived
    assert rows["jobB"]["group"] == "History 200"  # explicit


# ------------------------------------------------------------------ set group
def test_set_job_group_persists(tmp_path):
    _make_job(str(tmp_path), "jobA", title="Untitled")
    a = _adapter(tmp_path)
    a.set_job_group("jobA", "Chem 1")
    man = json.load(open(os.path.join(str(tmp_path), "jobs", "jobA", "manifest.json")))
    assert man["group"] == "Chem 1"
    # blank reverts to the derived default (removes explicit group)
    a.set_job_group("jobA", "")
    man = json.load(open(os.path.join(str(tmp_path), "jobs", "jobA", "manifest.json")))
    assert "group" not in man


def test_set_group_unknown_job_is_safe(tmp_path):
    a = _adapter(tmp_path)
    a.set_job_group("nope", "X")  # must not raise
    assert "unknown job" in " ".join(a.backend.log_line.emissions)


# ---------------------------------------------------------------------- delete
def test_delete_job_removes_dir(tmp_path, monkeypatch):
    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", lambda p: shutil.rmtree(p))
    root = _make_job(str(tmp_path), "jobA")
    a = _adapter(tmp_path)
    a.delete_job("jobA")
    assert not os.path.exists(root)
    payload = json.loads(a.backend.job_deleted.emissions[-1])
    assert payload["ok"] is True and payload["id"] == "jobA"
    assert payload["freed"]  # non-empty size string


def test_delete_harddelete_fallback_when_recycle_unavailable(tmp_path, monkeypatch):
    import send2trash

    def boom(_p):
        raise RuntimeError("no recycle bin")
    monkeypatch.setattr(send2trash, "send2trash", boom)
    root = _make_job(str(tmp_path), "jobA")
    a = _adapter(tmp_path)
    a.delete_job("jobA")
    assert not os.path.exists(root)  # shutil.rmtree fallback ran


def test_delete_unknown_job_reports_failure(tmp_path):
    a = _adapter(tmp_path)
    a.delete_job("does-not-exist")
    payload = json.loads(a.backend.job_deleted.emissions[-1])
    assert payload["ok"] is False


def test_delete_rejects_traversal_id(tmp_path, monkeypatch):
    import send2trash
    called = []
    monkeypatch.setattr(send2trash, "send2trash", lambda p: called.append(p))
    # a sibling dir that must NOT be touched
    outside = os.path.join(str(tmp_path), "jobs_secret")
    os.makedirs(outside)
    a = _adapter(tmp_path)
    for bad in ("../jobs_secret", "..", "a/b", "../../etc"):
        a.delete_job(bad)
    assert called == []            # nothing was ever deleted
    assert os.path.isdir(outside)  # sibling untouched
