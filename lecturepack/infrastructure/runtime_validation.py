"""Bounded, evidence-rich validation for the bundled runtime payload."""
from __future__ import annotations
from dataclasses import dataclass
import subprocess
import time
from typing import Sequence
from lecturepack.infrastructure.process_tree import terminate_owned_subprocess_tree

@dataclass(frozen=True)
class SmokeEvidence:
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    reason: str
    timed_out: bool
    @property
    def ok(self) -> bool:
        return self.reason == "success"

class RuntimeValidator:
    """Run a fixed local command with a bounded lifetime and captured evidence."""
    def __init__(self, timeout_ms: int = 30_000):
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        self.timeout_ms = timeout_ms
    def run(self, program: str, args: Sequence[str]) -> SmokeEvidence:
        argv = [str(program), *(str(arg) for arg in args)]
        started = time.monotonic()
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            duration_ms = int((time.monotonic() - started) * 1000)
            return SmokeEvidence(argv, None, "", str(error), duration_ms, "launch failed", False)
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_ms / 1000)
            code = process.returncode
            reason, timed_out = ("success", False) if code == 0 else ("nonzero exit", False)
        except subprocess.TimeoutExpired:
            terminate_owned_subprocess_tree(process)
            stdout, stderr = process.communicate()
            code, reason, timed_out = process.returncode, "timeout", True
        duration_ms = int((time.monotonic() - started) * 1000)
        return SmokeEvidence(argv, code, stdout or "", stderr or "", duration_ms, reason, timed_out)
