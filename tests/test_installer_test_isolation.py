"""Acceptance cleanup must preserve host state, including failure paths."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cleanup_restores_even_when_acceptance_and_uninstall_fail(tmp_path, monkeypatch):
    guard = load_script("installer_test_isolation")
    app = tmp_path / "app"
    calls = []

    def run(argv, **kwargs):
        assert kwargs["shell"] is False
        calls.append(argv)
        if Path(argv[0]).name == "unins000.exe":
            raise subprocess.CalledProcessError(7, argv)

    monkeypatch.setattr(guard.subprocess, "run", run)
    with pytest.raises(ExceptionGroup) as caught:
        with guard.InstallerTestIsolation(app, tmp_path / "state.json"):
            app.mkdir()
            (app / "unins000.exe").write_bytes(b"unit-test stub")
            raise ValueError("acceptance failed before completion")
    assert "acceptance failed before completion" in str(caught.value.exceptions[0])
    assert caught.value.exceptions[1].returncode == 7
    assert calls[0][calls[0].index("-Action") + 1] == "Snapshot"
    assert Path(calls[1][0]).name == "unins000.exe"
    assert calls[2][calls[2].index("-Action") + 1] == "Restore"


def test_snapshot_failure_never_runs_installation_or_restore(tmp_path, monkeypatch):
    guard = load_script("installer_test_isolation")
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(guard.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        with guard.InstallerTestIsolation(tmp_path / "app", tmp_path / "state.json"):
            pytest.fail("installation must not start without a snapshot")
    assert len(calls) == 1


def test_updater_refuses_to_delete_existing_acceptance_data(tmp_path):
    module = load_script("updater_ab_acceptance")
    (tmp_path / "data").mkdir()
    marker = tmp_path / "data" / "important.json"
    marker.write_text("preserve me")
    from argparse import Namespace
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        module.run(Namespace(workspace=str(tmp_path)))
    assert marker.read_text() == "preserve me"


def test_version_path_with_quotes_is_data_not_powershell_code(tmp_path, monkeypatch):
    module = load_script("updater_ab_acceptance")
    unusual = tmp_path / "lecture's Ω" / "LecturePack.exe"

    def run(argv, **kwargs):
        assert str(unusual) not in argv[-1]
        assert kwargs["env"]["LECTUREPACK_TEST_EXE"] == str(unusual)
        assert "-LiteralPath" in argv[-1]
        return subprocess.CompletedProcess(argv, 0, "2.1.4\n", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.product_version(unusual) == "2.1.4"


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows registry and shell contract")
def test_native_guard_restores_typed_registry_and_shortcut_bytes(tmp_path):
    import winreg
    parent = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    name = "LecturePackAcceptanceFixture_" + uuid.uuid4().hex
    fixture = parent + "\\" + name
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, fixture) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "LecturePack acceptance fixture")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(tmp_path / "legacy"))
        winreg.SetValueEx(key, "Binary", 0, winreg.REG_BINARY, b"\x00\xff\x17")
        winreg.SetValueEx(key, "List", 0, winreg.REG_MULTI_SZ, ["one", "two"])
        winreg.SetValueEx(key, "Expanded", 0, winreg.REG_EXPAND_SZ, "%TEMP%\\legacy")
        winreg.SetValueEx(key, "Number", 0, winreg.REG_DWORD, 4294967295)
        winreg.SetValueEx(key, "LongNumber", 0, winreg.REG_QWORD, 9007199254740993)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, fixture + r"\nested") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "original child")
    state_path = tmp_path / "state.json"
    app = tmp_path / "app"
    guard = ROOT / "scripts" / "installer_test_isolation.ps1"

    def invoke(action):
        return subprocess.run(
            [str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
             "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(guard),
             "-Action", action, "-InstallDir", str(app), "-StatePath", str(state_path)],
            shell=False, check=True, capture_output=True, text=True,
        )

    state = None
    try:
        invoke("Snapshot")
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        # A second acceptance runner must not race the first snapshot.
        duplicate = subprocess.run(
            [str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
             "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(guard),
             "-Action", "Snapshot", "-InstallDir", str(tmp_path / "second app"),
             "-StatePath", str(tmp_path / "second-state.json")],
            shell=False, capture_output=True, text=True,
        )
        assert duplicate.returncode != 0
        assert not (tmp_path / "second-state.json").exists()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, fixture, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(app))
            winreg.SetValueEx(key, "Binary", 0, winreg.REG_BINARY, b"changed")
            winreg.SetValueEx(key, "NewInstallerValue", 0, winreg.REG_DWORD, 42)
        # Exercise exact recovery after a real filesystem overwrite, not a mock.
        shortcut = state["shortcuts"][0]
        path = Path(shortcut["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"disposable installer shortcut fixture")
        # An unrelated concurrent registry change is preserved, while shortcuts
        # still restore and the lease remains available for explicit recovery.
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, fixture, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(tmp_path / "unrelated"))
        with pytest.raises(subprocess.CalledProcessError):
            invoke("Restore")
        if shortcut["existed"]:
            assert path.read_bytes() == base64.b64decode(shortcut["bytes"])
        else:
            assert not path.exists()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, fixture, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            assert winreg.QueryValueEx(key, "Binary")[0] == b"changed"
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(app))
        invoke("Restore")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, fixture) as key:
            assert winreg.QueryValueEx(key, "Binary") == (b"\x00\xff\x17", winreg.REG_BINARY)
            assert winreg.QueryValueEx(key, "List") == (["one", "two"], winreg.REG_MULTI_SZ)
            assert winreg.QueryValueEx(key, "Expanded") == ("%TEMP%\\legacy", winreg.REG_EXPAND_SZ)
            assert winreg.QueryValueEx(key, "Number") == (4294967295, winreg.REG_DWORD)
            assert winreg.QueryValueEx(key, "LongNumber") == (9007199254740993, winreg.REG_QWORD)
            with pytest.raises(FileNotFoundError):
                winreg.QueryValueEx(key, "NewInstallerValue")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, fixture + r"\nested") as key:
            assert winreg.QueryValueEx(key, "") == ("original child", winreg.REG_SZ)
        for shortcut in state["shortcuts"]:
            path = Path(shortcut["path"])
            assert path.exists() == shortcut["existed"]
            if shortcut["existed"]:
                assert path.read_bytes() == base64.b64decode(shortcut["bytes"])
        restored = json.loads(Path(str(state_path) + ".restored.json").read_text(encoding="utf-8-sig"))
        assert restored == {"registry_restored": True, "shortcuts_restored": True}
    finally:
        # Keep a failing guard test from polluting the host; independent fallback
        # does not turn the failed assertion into a pass.
        if state:
            for shortcut in state["shortcuts"]:
                path = Path(shortcut["path"])
                if shortcut["existed"]:
                    path.write_bytes(base64.b64decode(shortcut["bytes"]))
                elif path.is_file():
                    path.unlink()
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, fixture + r"\nested")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, fixture)
