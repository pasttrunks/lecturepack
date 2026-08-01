"""Launch the packaged onedir exe on a throwaway profile and verify it becomes ready.

The gate BUG-27 needed. Every existing check (unit tests, packaged-runtime smoke,
`--assert-pruned`) passed while the packaged app died on startup with
`ImportError: DLL load failed while importing QtWebChannel` -- because none of
them opened the app. This script does.

Exits 0 when a visible window handle appears within the timeout. Exits non-zero
with a diagnosis if the process crashes, exits early, or fails to show a window.

Usage:
    python scripts/packaged_launch_smoke.py [--exe PATH] [--timeout SECONDS]

Defaults to app/dist/LecturePack/LecturePack.exe and 60 s. Windows-only (uses
Win32 GetGUIThreadInfo via ctypes to detect window creation without depending
on PySide6 or any third party).
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


def _main_window_handle(pid: int) -> int:
    """Return the top-level window handle owned by `pid`, or 0 if none exists yet."""
    user32 = ctypes.windll.user32
    result = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd: int, _lparam: int) -> int:  # type: ignore[valid-type]
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == pid and user32.IsWindowVisible(hwnd):
            result[0] = hwnd
            return False  # stop enumerating
        return True

    user32.EnumWindows(_cb, 0)
    return result[0]


def launch_and_wait(exe: Path, timeout_s: float) -> tuple[int, str]:
    """Launch `exe` on a fresh throwaway profile; return (exit_code, diagnosis)."""
    if not exe.is_file():
        return 2, f"executable not found: {exe}"

    scratch_profile = Path(tempfile.mkdtemp(prefix="lp-smoke-profile-"))
    env = os.environ.copy()
    env["LECTUREPACK_DATA_DIR"] = str(scratch_profile)

    proc = subprocess.Popen([str(exe)], env=env, cwd=str(exe.parent))
    start = time.monotonic()
    try:
        while time.monotonic() - start < timeout_s:
            time.sleep(0.2)
            if proc.poll() is not None:
                elapsed = time.monotonic() - start
                return (
                    3,
                    f"process exited after {elapsed:.1f}s with code {proc.returncode} "
                    "before showing a window (packaged app failed to start)",
                )
            if _main_window_handle(proc.pid):
                elapsed = time.monotonic() - start
                return 0, f"window shown after {elapsed:.2f}s"
        return (
            4,
            f"no window within {timeout_s:.0f}s (process still running, PID {proc.pid})",
        )
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(scratch_profile, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--exe",
        default=str(Path("app") / "dist" / "LecturePack" / "LecturePack.exe"),
        help="Path to the built LecturePack.exe (default: app/dist/LecturePack/LecturePack.exe)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for a window (default: 60)",
    )
    args = ap.parse_args()
    if sys.platform != "win32":
        print("packaged_launch_smoke: Windows-only, skipping", file=sys.stderr)
        return 0
    exit_code, msg = launch_and_wait(Path(args.exe), args.timeout)
    stream = sys.stdout if exit_code == 0 else sys.stderr
    print(f"packaged_launch_smoke: {msg}", file=stream)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
