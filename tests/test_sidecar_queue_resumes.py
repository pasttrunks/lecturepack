"""Every queueing command in the SHIPPED sidecar must resume an idle queue.

Which process ships matters here. The published installer is the Electron shell,
and its engine is ``electron-spike/python-sidecar.py`` -- not ``app/desktop/``.
Fixes made to the PySide6 desktop shell do not travel with the product; the
sidecar has its own queue implementation and has to be fixed on its own terms.

The sidecar's queue only advances through ``_maybe_resume_queue``. ``queue_jobs``
and ``queue_existing_jobs`` called it; ``run_now`` did not. Since ``run_now`` only
REORDERS -- it moves a job to the front and deliberately cannot preempt an active
job -- with nothing running there was no "next" to be first in, so the queue's play
button (new in 2.0.7) reordered a list and did nothing observable at all.

These are SOURCE-STRUCTURE assertions, not behavioural ones. Instantiating the
sidecar means standing up its Qt application, controller and job store; that is
covered elsewhere. The contract worth pinning cheaply is "this command resumes the
queue", because the failure mode is silent and the regression is a one-line
deletion.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SIDECAR = Path(__file__).resolve().parents[1] / "electron-spike" / "python-sidecar.py"
SOURCE = SIDECAR.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

# Commands that express "make this run", as opposed to bookkeeping.
INTENT_COMMANDS = ("_run_now", "_queue_jobs", "_queue_existing_jobs")


def _method(name: str) -> ast.FunctionDef:
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in python-sidecar.py")


def _calls(node: ast.FunctionDef) -> set[str]:
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute):
                found.add(func.attr)
            elif isinstance(func, ast.Name):
                found.add(func.id)
    return found


@pytest.mark.parametrize("command", INTENT_COMMANDS)
def test_queueing_commands_resume_an_idle_queue(command: str):
    assert "_maybe_resume_queue" in _calls(_method(command)), (
        f"{command} never resumes the queue, so with nothing already running the "
        f"job it queues will sit there forever"
    )


def test_maybe_resume_queue_refuses_while_a_pipeline_is_live():
    """The one-active-job invariant is what makes resuming safe to call anywhere."""
    src = ast.get_source_segment(SOURCE, _method("_maybe_resume_queue")) or ""
    assert "current_stage" in src, (
        "_maybe_resume_queue must bail while a stage is running, or calling it from "
        "a queueing command would start a second pipeline on top of a live one"
    )
    assert "self.queue.active is not None" in src, (
        "_maybe_resume_queue must respect a held active slot"
    )


def test_the_shipped_ui_is_the_repo_ui():
    """If app/ui did not ship, none of the UI work in this release would reach users.

    package-win.mjs passes app/ui through extraResource, landing it at
    resources/ui. Pinned because the two trees are easy to drift apart, and the UI
    being stale in the product is invisible from the repo.
    """
    packager = (SIDECAR.parent / "package-win.mjs").read_text(encoding="utf-8")
    assert "'app', 'ui'" in packager, "app/ui is no longer the packaged UI source"
    assert "extraResource" in packager and "uiDir" in packager
