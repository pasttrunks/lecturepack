"""Guard the Explorer "Send to -> LecturePack" integration.

LecturePack already accepted file paths on the command line and forwarded
them into a running instance through its single-instance lock; what was
missing was the Explorer shortcut that actually hands it those paths. This
covers the installer side and the argument-handling side, and asserts the
integration reuses the existing import path rather than adding a second one.

The live install/uninstall proof is a packaged release-machine step, since it
needs a compiled Setup.exe and touches the real per-user SendTo folder.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "app" / "packaging" / "lecturepack.iss"
ISS_TEXT = ISS.read_text(encoding="utf-8", errors="replace")
MAIN = ROOT / "electron-spike" / "production-main.js"
MAIN_TEXT = MAIN.read_text(encoding="utf-8")
IMPORT_PATH_JS = ROOT / "electron-spike" / "import-path.js"

NODE = shutil.which("node")


def _icons_section() -> str:
    """The [Icons] block only, so a match in a comment elsewhere cannot pass."""
    match = re.search(r"^\[Icons\]\s*$(.*?)(?=^\[|\Z)", ISS_TEXT, re.MULTILINE | re.DOTALL)
    assert match, "lecturepack.iss has no [Icons] section"
    return match.group(1)


def _sendto_entry() -> str:
    for line in _icons_section().splitlines():
        stripped = line.strip()
        if stripped.startswith(";") or not stripped:
            continue
        if "{sendto}" in stripped:
            return stripped
    raise AssertionError("no {sendto} entry in [Icons]")


# ------------------------------------------------------------------ installer
def test_installer_creates_a_send_to_shortcut():
    entry = _sendto_entry()
    assert r"{sendto}\{#AppName}" in entry, entry


def test_send_to_shortcut_points_at_the_installed_executable():
    entry = _sendto_entry()
    assert 'Filename: "{app}\\{#AppExeName}"' in entry, entry


def test_send_to_shortcut_is_created_unconditionally_on_a_fresh_install():
    """It must not hide behind an unchecked optional task."""
    entry = _sendto_entry()
    assert "Tasks:" not in entry, (
        f"the Send to shortcut must not be gated behind an optional task: {entry}"
    )


def test_send_to_shortcut_is_per_user_and_needs_no_elevation():
    """{sendto} is the per-user SendTo folder; the install stays unelevated."""
    assert "PrivilegesRequired=lowest" in ISS_TEXT
    assert "{commonsendto}" not in ISS_TEXT, "must not write a machine-wide SendTo entry"


def test_send_to_shortcut_is_removed_on_uninstall():
    """Inno removes [Icons] entries automatically; the guarantee here is that
    the entry lives in [Icons] and is not hand-rolled into [Registry] or a
    [Code] routine that would leave it behind."""
    entry = _sendto_entry()
    assert entry.startswith("Name:")
    registry = re.search(r"^\[Registry\]", ISS_TEXT, re.MULTILINE)
    assert registry is None, "Send to must not be implemented as a registry hack"


# ----------------------------------------------------------- argument handling
def test_main_forwards_second_instance_paths_into_the_existing_import_path():
    assert "requestSingleInstanceLock" in MAIN_TEXT
    assert "second-instance" in MAIN_TEXT
    # Reuses importMultiplePaths -- no second import subsystem.
    second = MAIN_TEXT[MAIN_TEXT.index("'second-instance'"):]
    second = second[:2000]
    assert "extractFileArguments" in second
    assert "importMultiplePaths" in second


def test_first_instance_also_imports_paths_it_was_launched_with():
    assert "extractFileArguments(process.argv)" in MAIN_TEXT


@pytest.mark.skipif(NODE is None, reason="Node is required to exercise import-path.js")
def test_extract_file_arguments_keeps_real_paths_and_drops_switches(tmp_path):
    """Explorer passes the selected file paths as plain arguments; Electron and
    Chromium switches must never be mistaken for lectures."""
    lecture = tmp_path / "Week 1 Lecture.mp4"
    lecture.write_bytes(b"stub")

    script = (
        "const {extractFileArguments}=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify("
        "extractFileArguments(JSON.parse(process.argv[2]))));"
    )
    argv = [
        "C:\\Program Files\\LecturePack\\LecturePack.exe",
        "--allow-file-access-from-files",
        str(lecture),
    ]
    completed = subprocess.run(
        [NODE, "-e", script, str(IMPORT_PATH_JS), __import__("json").dumps(argv)],
        capture_output=True, text=True, check=True,
    )
    selected = __import__("json").loads(completed.stdout)
    assert selected == [str(lecture)]


@pytest.mark.skipif(NODE is None, reason="Node is required to exercise import-path.js")
def test_extract_file_arguments_ignores_the_executable_itself(tmp_path):
    script = (
        "const {extractFileArguments}=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify("
        "extractFileArguments(JSON.parse(process.argv[2]))));"
    )
    completed = subprocess.run(
        [NODE, "-e", script, str(IMPORT_PATH_JS),
         __import__("json").dumps(["C:\\LecturePack\\LecturePack.exe"])],
        capture_output=True, text=True, check=True,
    )
    assert __import__("json").loads(completed.stdout) == []


def test_import_path_never_writes_to_the_source_lecture():
    """A lecture handed over by Send to is read-only input, always."""
    text = IMPORT_PATH_JS.read_text(encoding="utf-8")
    for forbidden in ("writeFile", "unlink", "rename", "rmSync", "truncate", "appendFile"):
        assert forbidden not in text, f"import-path.js must not call {forbidden}"
