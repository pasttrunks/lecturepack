"""Scoped termination for process trees started and owned by LecturePack."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QProcess


def terminate_qprocess_tree(process: QProcess, timeout_ms: int = 3000) -> dict:
    """Terminate ``process`` and its descendants without name-based killing.

    On Windows, ``taskkill /PID <owned-root> /T /F`` targets only the tree
    rooted at the exact PID returned by LecturePack's QProcess.  It never uses
    an image name, so unrelated ffmpeg/whisper/python processes are untouched.
    """
    running = process is not None and process.state() == QProcess.ProcessState.Running
    pid = int(process.processId()) if running else 0
    report = {
        "root_pid": pid,
        "strategy": "already-stopped",
        "taskkill_returncode": None,
        "finished": not running,
    }
    if not running:
        return report

    if os.name == "nt" and pid > 0:
        report["strategy"] = "taskkill-pid-tree"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, text=True, timeout=5, check=False,
                creationflags=creationflags)
            report["taskkill_returncode"] = result.returncode
        except (OSError, subprocess.SubprocessError):
            report["taskkill_returncode"] = -1
    else:
        report["strategy"] = "terminate-then-kill"
        process.terminate()

    if not process.waitForFinished(timeout_ms):
        process.kill()
        process.waitForFinished(timeout_ms)
    report["finished"] = process.state() == QProcess.ProcessState.NotRunning
    return report
