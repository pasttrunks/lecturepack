"""D-18/D-19/D-20/D-21: single-instance guard, process identity, non-silent
icon path.

Task 2 covers `app/desktop/single_instance.py`'s `SingleInstanceGuard`: a
second launch must raise and focus the running instance's window instead of
exiting silently (D-18), and the guard must run in `main()` before
`MainWindow()` -- and therefore before `Backend.__init__`'s deferred
`assess()` worker -- so a second process is never left invisible (D-19).
The IPC channel is a local trust boundary: its wire format is one fixed
ASCII sentinel compared by byte equality, never parsed or deserialized
(T-01-05-01..04).

Task 3 covers `app/desktop/main.py`'s AppUserModelID declaration (D-20) and
the two icon-resolution guards that must report rather than silently
disappear when the `.ico` is missing (D-21).

Every guard test uses its own unique endpoint name (`_unique_endpoint()`) so
tests can never collide with each other or with a real running LecturePack
instance on the same machine.
"""

from __future__ import annotations

import ast
import os
import sys
import uuid

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(REPO_ROOT, "app", "desktop", "main.py")
SINGLE_INSTANCE_PY = os.path.join(REPO_ROOT, "app", "desktop", "single_instance.py")
ISS_PATH = os.path.join(REPO_ROOT, "app", "packaging", "lecturepack.iss")

MAIN_SOURCE = open(MAIN_PY, encoding="utf-8").read()
MAIN_TREE = ast.parse(MAIN_SOURCE)
SINGLE_INSTANCE_SOURCE = open(SINGLE_INSTANCE_PY, encoding="utf-8").read()
ISS_TEXT = open(ISS_PATH, encoding="utf-8").read()

from app.desktop import main as main_module  # noqa: E402
from app.desktop import single_instance as si  # noqa: E402

# QLocalSocket/QLocalServer need a QCoreApplication instance to exist.
# pytest-qt's `qapp` fixture creates (or reuses) the process-wide
# QApplication; applying it to every test in this module -- regardless of
# whether an individual test also asks for `qtbot` -- means the guard tests
# below don't depend on test execution order or on another test file having
# already constructed one first (matters when this file is run in
# isolation, as `pytest tests/test_single_instance_identity.py -x` does).
pytestmark = pytest.mark.usefixtures("qapp")


def _unique_endpoint() -> str:
    return f"lecturepack-test-single-instance-{uuid.uuid4().hex}"


# --------------------------------------------------------------------- #
# Task 2: SingleInstanceGuard behavior
# --------------------------------------------------------------------- #


def test_first_acquire_returns_primary():
    guard = si.SingleInstanceGuard(_unique_endpoint())
    try:
        assert guard.acquire() == "primary"
    finally:
        guard.release()


def test_second_acquire_while_first_holds_returns_secondary():
    endpoint = _unique_endpoint()
    primary = si.SingleInstanceGuard(endpoint)
    secondary = si.SingleInstanceGuard(endpoint)
    try:
        assert primary.acquire() == "primary"
        assert secondary.acquire() == "secondary"
    finally:
        primary.release()


def test_release_then_reacquire_returns_primary_again():
    endpoint = _unique_endpoint()
    first = si.SingleInstanceGuard(endpoint)
    try:
        assert first.acquire() == "primary"
    finally:
        first.release()

    second = si.SingleInstanceGuard(endpoint)
    try:
        assert second.acquire() == "primary"
    finally:
        second.release()


def test_secondary_signal_existing_delivers_sentinel_and_fires_callback_once(qtbot):
    endpoint = _unique_endpoint()
    primary = si.SingleInstanceGuard(endpoint)
    try:
        assert primary.acquire() == "primary"
        received = []
        primary.set_raise_handler(lambda: received.append(True))

        secondary = si.SingleInstanceGuard(endpoint)
        assert secondary.acquire() == "secondary"
        assert secondary.signal_existing() is True

        qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
        assert received == [True]
    finally:
        primary.release()


def test_non_sentinel_payload_does_not_invoke_the_raise_handler(qtbot):
    from PySide6.QtNetwork import QLocalSocket

    endpoint = _unique_endpoint()
    primary = si.SingleInstanceGuard(endpoint)
    try:
        assert primary.acquire() == "primary"
        received = []
        primary.set_raise_handler(lambda: received.append(True))

        sock = QLocalSocket()
        sock.connectToServer(endpoint)
        assert sock.waitForConnected(1000)
        sock.write(b"not-the-sentinel")
        sock.flush()
        sock.waitForBytesWritten(500)
        qtbot.wait(300)

        assert received == [], (
            "the raise handler fired for a payload that was not the exact "
            "RAISE_SENTINEL -- the handler must compare by equality only"
        )
    finally:
        primary.release()


def test_acquire_reclaims_a_stale_endpoint_via_removeserver(monkeypatch):
    """T-01-05-03: a crashed prior instance never gets a chance to clean up
    after itself, so acquire() must unconditionally reclaim the endpoint
    (QLocalServer.removeServer) before listening, rather than assuming it
    is free."""
    from PySide6.QtNetwork import QLocalServer

    endpoint = _unique_endpoint()
    calls = []
    real_remove = QLocalServer.removeServer

    def fake_remove(name):
        calls.append(name)
        return real_remove(name)

    monkeypatch.setattr(QLocalServer, "removeServer", staticmethod(fake_remove))

    guard = si.SingleInstanceGuard(endpoint)
    try:
        assert guard.acquire() == "primary"
        assert calls == [endpoint], (
            "acquire() must reclaim a stale endpoint via "
            "QLocalServer.removeServer() before listening"
        )
    finally:
        guard.release()


def test_acquire_fails_open_to_primary_when_the_ipc_primitive_raises(monkeypatch):
    from PySide6.QtNetwork import QLocalSocket

    def boom(self, name):
        raise RuntimeError("simulated IPC primitive failure")

    monkeypatch.setattr(QLocalSocket, "connectToServer", boom)

    guard = si.SingleInstanceGuard(_unique_endpoint())
    assert guard.acquire() == "primary", (
        "an OS-integration/IPC failure must never prevent the app from "
        "starting -- acquire() must fail open to 'primary'"
    )


def test_endpoint_name_is_a_fixed_literal_not_argv_or_env():
    """The endpoint must be derived from stable application identity, never
    from sys.argv or an environment variable -- a caller-influenced name
    would let an unprivileged process pick which 'instance' it collides
    with. Scans actual code (not comments/docstrings, which legitimately
    discuss sys.argv/os.environ as things NOT to use)."""
    tree = ast.parse(SINGLE_INSTANCE_SOURCE)
    code_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in ("sys", "os"):
                code_names.add(f"{node.value.id}.{node.attr}")
    assert "sys.argv" not in code_names
    assert "os.environ" not in code_names
    assert si.SINGLE_INSTANCE_ENDPOINT == "LecturePack.single-instance.v1"


def test_no_deserialization_primitives_referenced_in_single_instance_module():
    """T-01-05-01: the received payload is never passed to json.loads, eval,
    exec, pickle, or any other deserializer -- the handler compares against
    a literal and nothing more."""
    forbidden = ["json.loads(", "eval(", "exec(", "pickle."]
    offenders = [f for f in forbidden if f in SINGLE_INSTANCE_SOURCE]
    assert offenders == [], f"forbidden deserialization primitives found: {offenders}"


def test_connection_handler_reads_at_most_max_message_bytes():
    """T-01-05-04: every read from a peer connection must be bounded by
    MAX_MESSAGE_BYTES -- statically verified so a future edit that swaps in
    an unbounded read() call fails this test."""
    tree = ast.parse(SINGLE_INSTANCE_SOURCE)
    read_calls_using_bound = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "MAX_MESSAGE_BYTES"
        ):
            read_calls_using_bound.append(node)
    assert read_calls_using_bound, (
        "no connection .read(MAX_MESSAGE_BYTES) call found -- a peer "
        "connection's read must be bounded"
    )


def test_mutation_sentinel_equality_loosened_is_caught_by_this_test(qtbot):
    """Mutation-testing note (not a real mutation harness): if
    `payload == RAISE_SENTINEL` in single_instance.py were loosened to
    `RAISE_SENTINEL in payload` or `payload.startswith(RAISE_SENTINEL)`,
    `test_non_sentinel_payload_does_not_invoke_the_raise_handler` above
    would still pass (its payload shares no prefix with the sentinel), but
    a payload of `RAISE_SENTINEL + b"-and-then-something-else"` would then
    wrongly fire the handler under the loosened check. This test proves
    the exact-equality boundary directly."""
    from PySide6.QtNetwork import QLocalSocket

    endpoint = _unique_endpoint()
    guard = si.SingleInstanceGuard(endpoint)
    try:
        assert guard.acquire() == "primary"
        received = []
        guard.set_raise_handler(lambda: received.append(True))

        sock = QLocalSocket()
        sock.connectToServer(endpoint)
        assert sock.waitForConnected(1000)
        sock.write(si.RAISE_SENTINEL + b"-trailing-garbage")
        sock.flush()
        sock.waitForBytesWritten(500)

        qtbot.wait(500)

        assert received == [], (
            "a sentinel-with-trailing-bytes payload fired the raise "
            "handler -- the comparison must be exact equality, not a "
            "prefix/substring check (this is what a loosened equality "
            "check would let through)"
        )
    finally:
        guard.release()


# --------------------------------------------------------------------- #
# Task 2: main() wiring -- guard runs before MainWindow(), raise path reuse
# --------------------------------------------------------------------- #


def _main_func_node():
    for node in ast.walk(MAIN_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main() not found in main.py")


def _first_call_lines(node, names):
    """First source line at which each name in `names` is called or
    constructed anywhere under `node`. Uses min() over all matches rather
    than "first encountered during ast.walk" because ast.walk is
    breadth-first and not guaranteed to visit nodes in source order."""
    found: dict[str, list[int]] = {}
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                fname = n.func.id
            elif isinstance(n.func, ast.Attribute):
                fname = n.func.attr
            else:
                fname = None
            if fname in names:
                found.setdefault(fname, []).append(n.lineno)
    return {k: min(v) for k, v in found.items()}


def test_single_instance_guard_acquire_precedes_mainwindow_construction():
    main_node = _main_func_node()
    lines = _first_call_lines(main_node, {"acquire", "MainWindow"})
    assert "acquire" in lines, "guard.acquire() is not called in main()"
    assert "MainWindow" in lines, "MainWindow() is not constructed in main()"
    assert lines["acquire"] < lines["MainWindow"], (
        "guard.acquire() must run before MainWindow() -- and therefore "
        "before Backend.__init__ and its deferred assess() worker (D-19)"
    )


def test_raise_handler_registered_before_show_when_ready():
    main_node = _main_func_node()
    lines = _first_call_lines(main_node, {"set_raise_handler", "show_when_ready"})
    assert "set_raise_handler" in lines
    assert "show_when_ready" in lines
    assert lines["set_raise_handler"] < lines["show_when_ready"]


def test_mainwindow_raise_and_focus_uses_the_established_focus_sequence():
    """The raise handler must reach MainWindow's existing raise path
    (showNormal-if-minimized, raise_, activateWindow), not a second,
    independently invented focus mechanism."""
    for node in ast.walk(MAIN_TREE):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            main_window_cls = node
            break
    else:
        raise AssertionError("MainWindow class not found")

    for node in main_window_cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == "raise_and_focus":
            raise_and_focus = node
            break
    else:
        raise AssertionError("MainWindow.raise_and_focus not found")

    calls = {
        n.func.attr
        for n in ast.walk(raise_and_focus)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert {"showNormal", "raise_", "activateWindow"} <= calls

    for node in main_window_cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_on_notification_clicked":
            on_clicked = node
            break
    else:
        raise AssertionError("MainWindow._on_notification_clicked not found")

    clicked_calls = {
        n.func.attr
        for n in ast.walk(on_clicked)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "raise_and_focus" in clicked_calls, (
        "_on_notification_clicked must reuse raise_and_focus rather than "
        "inventing a second focus mechanism"
    )


# --------------------------------------------------------------------- #
# Task 3: AppUserModelID declaration and ordering
# --------------------------------------------------------------------- #


def test_app_user_model_id_literal_defined():
    assert hasattr(main_module, "APP_USER_MODEL_ID")
    assert isinstance(main_module.APP_USER_MODEL_ID, str)
    assert main_module.APP_USER_MODEL_ID


def test_set_app_user_model_id_calls_shell32_on_win32(monkeypatch):
    import ctypes

    calls = []

    class _FakeShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            calls.append(value)

    class _FakeWindll:
        shell32 = _FakeShell32()

    monkeypatch.setattr(main_module.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", _FakeWindll(), raising=False)

    main_module._set_app_user_model_id()

    assert calls == [main_module.APP_USER_MODEL_ID]


def test_set_app_user_model_id_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(main_module.sys, "platform", "linux")
    main_module._set_app_user_model_id()  # must not raise


def test_set_app_user_model_id_swallows_ctypes_exceptions(monkeypatch):
    import ctypes

    class _BoomShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            raise OSError("no shell32 available")

    class _BoomWindll:
        shell32 = _BoomShell32()

    monkeypatch.setattr(main_module.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", _BoomWindll(), raising=False)

    main_module._set_app_user_model_id()  # must not raise


def test_set_app_user_model_id_called_before_register_asset_scheme():
    main_node = _main_func_node()
    lines = _first_call_lines(main_node, {"_set_app_user_model_id", "register_asset_scheme"})
    assert "_set_app_user_model_id" in lines
    assert "register_asset_scheme" in lines
    assert lines["_set_app_user_model_id"] < lines["register_asset_scheme"], (
        "SetCurrentProcessExplicitAppUserModelID must run before any "
        "window/UI-adjacent setup, per D-20"
    )


def test_aumid_literal_matches_lecturepack_iss_byte_for_byte():
    aumid = main_module.APP_USER_MODEL_ID
    assert f'#define AppUserModelID "{aumid}"' in ISS_TEXT, (
        "main.py's APP_USER_MODEL_ID must match lecturepack.iss's "
        "AppUserModelID #define byte-for-byte -- a mismatch is silent and "
        "reproduces the blank taskbar icon"
    )


def test_aumid_set_on_exactly_two_icons_entries_not_the_uninstall_entry():
    icons_lines = [
        line for line in ISS_TEXT.splitlines()
        if line.strip().startswith('Name: "{group}\\{#AppName}"')
        or line.strip().startswith('Name: "{autodesktop}\\{#AppName}"')
        or line.strip().startswith('Name: "{group}\\{cm:UninstallProgram')
    ]
    assert len(icons_lines) == 3, f"expected exactly 3 relevant [Icons] entries, found {len(icons_lines)}"

    with_aumid = [line for line in icons_lines if "AppUserModelID:" in line]
    assert len(with_aumid) == 2, (
        f"expected AppUserModelID on exactly 2 [Icons] entries, found "
        f"{len(with_aumid)}: {with_aumid}"
    )

    uninstall_lines = [line for line in icons_lines if "cm:UninstallProgram" in line]
    assert len(uninstall_lines) == 1
    assert "AppUserModelID" not in uninstall_lines[0], (
        "the uninstall shortcut points at {uninstallexe}, a different "
        "process -- it must not carry AppUserModelID"
    )


def test_aumid_literal_contains_no_version_digit_sequence():
    """A version bump must never orphan a pinned taskbar or Start icon."""
    import re

    assert not re.search(r"\d", main_module.APP_USER_MODEL_ID), (
        "APP_USER_MODEL_ID must contain no digit sequence (e.g. a version "
        f"number); got {main_module.APP_USER_MODEL_ID!r}"
    )


# --------------------------------------------------------------------- #
# Task 3: non-silent icon path (D-21)
# --------------------------------------------------------------------- #


def test_report_missing_icon_writes_the_resolved_path_to_stderr(capsys):
    main_module._report_missing_icon("window-icon", r"C:\nonexistent\lecturepack.ico")
    captured = capsys.readouterr()
    assert "window-icon" in captured.err
    assert r"C:\nonexistent\lecturepack.ico" in captured.err


def test_report_missing_icon_tray_tag_writes_to_stderr(capsys):
    main_module._report_missing_icon("tray-icon", r"C:\nonexistent\lecturepack.ico")
    captured = capsys.readouterr()
    assert "tray-icon" in captured.err
    assert r"C:\nonexistent\lecturepack.ico" in captured.err


def test_resolve_icon_path_source_run(monkeypatch):
    monkeypatch.setattr(main_module.sys, "frozen", False, raising=False)
    path = main_module._resolve_icon_path()
    assert path.endswith("lecturepack.ico")
    assert "packaging" in path


def test_resolve_icon_path_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "LecturePack.exe"
    monkeypatch.setattr(main_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main_module.sys, "executable", str(exe), raising=False)
    path = main_module._resolve_icon_path()
    assert path == str(tmp_path / "lecturepack.ico")


def _find_class(name):
    for node in ast.walk(MAIN_TREE):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in main.py")


def _find_method(cls, name):
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{cls.name}.{name} not found")


def _icon_exists_guards(init_node):
    """Every `if os.path.exists(...): <body> else: <orelse>` If-node inside
    __init__ whose test is a call to os.path.exists."""
    guards = []
    for node in ast.walk(init_node):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Call)
            and isinstance(test.func, ast.Attribute)
            and test.func.attr == "exists"
        ):
            guards.append(node)
    return guards


def _calls_in(nodes):
    calls = set()
    for stmt in nodes:
        for n in ast.walk(stmt):
            if not isinstance(n, ast.Call):
                continue
            if isinstance(n.func, ast.Attribute):
                calls.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                calls.add(n.func.id)
    return calls


def test_window_icon_guard_reports_when_missing_and_sets_icon_when_present():
    init = _find_method(_find_class("MainWindow"), "__init__")
    guards = _icon_exists_guards(init)
    assert len(guards) == 2, f"expected exactly 2 os.path.exists icon guards, found {len(guards)}"

    window_guard = guards[0]
    body_calls = _calls_in(window_guard.body)
    orelse_calls = _calls_in(window_guard.orelse)
    assert "setWindowIcon" in body_calls, "present-.ico path must still call setWindowIcon"
    assert "_report_missing_icon" not in body_calls, "the present-.ico path must not report"
    assert "_report_missing_icon" in orelse_calls, "the missing-.ico path must report"
    assert "setWindowIcon" not in orelse_calls


def test_tray_icon_guard_reports_when_missing_and_sets_icon_when_present():
    init = _find_method(_find_class("MainWindow"), "__init__")
    guards = _icon_exists_guards(init)
    assert len(guards) == 2

    tray_guard = guards[1]
    body_calls = _calls_in(tray_guard.body)
    orelse_calls = _calls_in(tray_guard.orelse)
    assert "setIcon" in body_calls, "present-.ico path must still call tray.setIcon"
    assert "_report_missing_icon" not in body_calls
    assert "_report_missing_icon" in orelse_calls
    assert "setIcon" not in orelse_calls
