"""BUG-11: the tray/taskbar wiring must be reachable inside MainWindow.__init__.

The poster-prewarm change inserted two methods into the MIDDLE of `__init__`.
Everything below the insertion point -- the tray-icon creation and the
`attach_window(self, self.tray)` call -- ended up *after* `return ""` inside
`_ffmpeg_exe`, i.e. permanently unreachable. `self.tray` was never assigned and
`attach_window` never ran, so every tray notification and all taskbar progress
silently stopped working. Nothing failed loudly: the module imports, the class
constructs, and the tests passed.

These are AST checks rather than GUI checks on purpose -- the defect is purely
structural, and a structural test catches it without needing a window, a Qt
platform plugin, or a human looking at a screenshot.
"""

from __future__ import annotations

import ast
import os

MAIN_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "desktop", "main.py")

TREE = ast.parse(open(MAIN_PY, encoding="utf-8").read())


def _class(name):
    for node in ast.walk(TREE):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in main.py")


def _method(cls, name):
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{cls.name}.{name} not found")


def _calls(node):
    return {n.func.attr for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}


def test_attach_window_is_called_from_init():
    """The Windows integration must be wired during construction."""
    init = _method(_class("MainWindow"), "__init__")
    assert "attach_window" in _calls(init), (
        "attach_window is not reachable from MainWindow.__init__ -- tray "
        "notifications and taskbar progress will silently do nothing")


def test_self_tray_is_assigned_in_init():
    init = _method(_class("MainWindow"), "__init__")
    assigned = set()
    for n in ast.walk(init):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                        and t.value.id == "self"):
                    assigned.add(t.attr)
    assert "tray" in assigned, "self.tray never assigned in __init__"


def test_no_unreachable_statements_after_return_in_any_method():
    """The general form of BUG-11: dead code stranded after a return.

    Catches a method body that continues past an unconditional `return` at the
    same nesting level -- which is exactly what happens when a new method is
    pasted into the middle of an existing one.
    """
    offenders = []
    for node in ast.walk(TREE):
        if not isinstance(node, ast.FunctionDef):
            continue
        for i, stmt in enumerate(node.body[:-1]):
            if isinstance(stmt, ast.Return):
                nxt = node.body[i + 1]
                offenders.append(f"{node.name}() line {nxt.lineno}")
    assert not offenders, (
        "unreachable code after a top-level return in: " + ", ".join(offenders))
