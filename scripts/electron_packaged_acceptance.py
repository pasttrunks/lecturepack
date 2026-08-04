"""Automated + human-readable release gate for the Phase 8 packaged Electron app.

The gate has no production impact: it does not modify the Electron host, the
Python sidecar, the renderer, the processing engine, or the Qt app. It is a
documentation/contract-only gate that exercises a *disposable* packaged build
from the outside and records one JSON result plus a text summary.

The gate covers the 12 packaged-app acceptance requirements:

    1.  Electron launches from the packaged directory.
    2.  The packaged Python sidecar becomes ready.
    3.  FFmpeg / FFprobe / whisper.cpp / bundled model resolve from packaged paths.
    4.  A bundled disposable demo video can be imported.
    5.  Real processing reaches completion.
    6.  Slides and transcript are generated.
    7.  Study Pack export completes and its files exist.
    8.  The app closes cleanly.
    9.  The app relaunches with the same disposable data directory.
    10. The completed job restores as done.
    11. No sidecar / FFmpeg / FFprobe / whisper / Python / Electron child
        process remains after shutdown.
    12. Logs contain no renderer crash, page-load failure, unresponsive event,
        malformed bridge payload, unsupported command, or unhandled exception.

Design notes
------------
- Drive-by-evidence, not screen scraping. The packaged ``LecturePack.exe``
  writes a ``production-*.jsonl`` evidence stream to ``--results`` (host
  events incl. ``session_started``, ``sidecar_message`` ``ready``,
  ``job_restored``, ``page_load_failed``, ``render_process_gone``,
  ``renderer_unresponsive``, ``page_message_failed``, ``console``,
  ``sidecar_stderr``). We read that evidence.
- The bundled ``LecturePackSidecar.exe`` speaks a JSONL contract over
  stdin/stdout (``health_check``, ``import_video``, ``start_job``,
  ``get_slides``, ``get_transcript``, ``export``, ``shutdown`` and the
  ``ready``/``job_completed``/``export_done``/``slides_changed``/
  ``transcript_changed`` events). We drive it directly to verify the real
  bundled runtime end-to-end without CDP or screen scraping.
- Heavy logic lives in pure helpers so the focused test suite never needs a
  real packaged app; only ``main()`` touches subprocesses and the filesystem.

Usage
-----
    python scripts/electron_packaged_acceptance.py \
        --app-dir "path/to/dist/LecturePack-win32-x64" \
        --results-dir "path/to/results" \
        [--data-dir "path/to/disposable-data"] [--keep-data] \
        [--demo-video "path/to/demo-lecture.mp4"] \
        [--timeout-seconds 300]

Safe data directory
-------------------
The runner rejects any data directory that is, or resolves to, the normal user
``LecturePackData`` location (``~/LecturePackData`` and the profile / Documents
/ AppData variants, plus the Electron userData default). It only ever operates
on a disposable directory.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

APP_EXE_NAMES = ("LecturePack.exe", "lecturepack.exe")
SIDECAR_EXE_NAME = "LecturePackSidecar.exe"
FORBIDDEN_DIRNAME = "LecturePackData"

# Relative to the packaged resource root that contains bin/ and models/.
PACKAGED_RUNTIME_FILES = (
    ("bin/ffmpeg.exe", "ffmpeg"),
    ("bin/ffprobe.exe", "ffprobe"),
    ("bin/Release/whisper-cli.exe", "whisper"),
    ("models/ggml-base.en.bin", "model"),
)

ACCEPTANCE_KEYS = (
    "app_launched",
    "sidecar_ready",
    "runtime_paths_ready",
    "job_started",
    "job_completed",
    "slides_generated",
    "transcript_generated",
    "export_completed",
    "export_file_count",
    "first_exit_clean",
    "restore_passed",
    "orphan_processes",
    "renderer_failures",
    "bridge_errors",
    "unexpected_errors",
    "passed",
)

# Host evidence event names that indicate renderer / page / bridge failure.
RENDERER_FAILURE_EVENTS = ("page_load_failed", "render_process_gone", "renderer_unresponsive")
BRIDGE_FAILURE_EVENTS = (
    "page_message_failed",
    "sidecar_spawn_error",
    "bootstrap_failed",
)
# Free-text markers looked up inside console / sidecar_stderr / error records.
BRIDGE_ERROR_MARKERS = (
    "unsupported command",
    "malformed",
    "invalid json",
    "invalid sidecar jsonl",
    "unhandled exception",
    "unhandled error",
)

# Child process family we watch for orphans after shutdown (requirement 11).
WATCH_PROCESS_TOKENS = (
    "lecturepack",
    "sidecar",
    "ffmpeg",
    "ffprobe",
    "whisper",
    "python",
    "electron",
)

# JSONL request-id correlation default timeout.
PROTOCOL_TIMEOUT_S = 60.0


# --------------------------------------------------------------------------- #
# Path discovery + safe data-directory validation (pure)
# --------------------------------------------------------------------------- #

def discover_app_exe(app_dir: Path) -> Optional[Path]:
    """Return the packaged LecturePack executable inside ``app_dir`` or None."""
    if not app_dir or not app_dir.is_dir():
        return None
    for name in APP_EXE_NAMES:
        candidate = app_dir / name
        if candidate.is_file():
            return candidate
    for child in sorted(app_dir.iterdir()):
        if child.is_dir():
            found = discover_app_exe(child)
            if found is not None:
                return found
    return None


def _home() -> Path:
    return Path.home()


def _env_path(name: str) -> Optional[Path]:
    value = os.environ.get(name, "")
    return Path(value) if value else None


def normal_lecturepack_data_candidates() -> list[Path]:
    """Resolved user data locations the runner must never touch."""
    home = _home()
    candidates: list[Path] = [
        home / FORBIDDEN_DIRNAME,
        home / "Documents" / FORBIDDEN_DIRNAME,
        home / "Desktop" / FORBIDDEN_DIRNAME,
    ]
    for env_name in ("USERPROFILE", "HOMEDRIVE", "APPDATA", "LOCALAPPDATA"):
        base = _env_path(env_name)
        if base:
            candidates.append(base / FORBIDDEN_DIRNAME)
    for app_dir in ("lecturepack", "LecturePack", "LecturePackElectron"):
        ap = _env_path("APPDATA")
        if ap:
            candidates.append(ap / app_dir / FORBIDDEN_DIRNAME)
    resolved: set[Path] = set()
    for candidate in candidates:
        try:
            resolved.add(candidate.expanduser().resolve())
        except (OSError, RuntimeError):
            continue
    return sorted(resolved)


def data_dir_status(data_dir: str | Path) -> tuple[bool, str]:
    """Return ``(allowed, reason)``; ``reason`` is non-empty only when disallowed."""
    path = Path(data_dir).expanduser().resolve()
    for forbidden in normal_lecturepack_data_candidates():
        if path == forbidden:
            return False, f"data dir resolves to the normal user location: {path}"
    profile_roots = [(_home()).resolve()]
    for env_name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        base = _env_path(env_name)
        if base:
            profile_roots.append(base.expanduser().resolve())
    profile_roots.extend([
        (_home() / "Documents").resolve(),
        (_home() / "Desktop").resolve(),
    ])
    if path.name == FORBIDDEN_DIRNAME:
        for root in profile_roots:
            if path.parent == root:
                return False, f"data dir is the user LecturePackData under a profile root: {path}"
    return True, ""


def resolve_args_path(value: str | None, base: Path | None = None) -> Optional[Path]:
    if not value:
        return None
    path = Path(value).expanduser()
    if base is not None and not path.is_absolute():
        path = base / path
    return path


# --------------------------------------------------------------------------- #
# Deterministic helpers exported for the focused test suite
# --------------------------------------------------------------------------- #

def poll_until(
    predicate: Callable[[], Any],
    timeout_s: float,
    interval_s: float = 0.25,
    label: str = "condition",
) -> Any:
    """Poll ``predicate()`` until true or ``timeout_s``; raises ``TimeoutError``
    instead of hanging so the caller can convert it into a useful partial result."""
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        try:
            value = predicate()
        except Exception:  # noqa: BLE001 - a failing poll is treated as unmet
            value = False
        if value:
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out after {timeout_s:.1f}s waiting for {label}")
        time.sleep(max(0.0, min(float(interval_s), 5.0)))


def detect_orphans(
    before: Iterable[dict[str, Any]],
    after: Iterable[dict[str, Any]],
    watch_tokens: Iterable[str] = WATCH_PROCESS_TOKENS,
) -> list[str]:
    """Return sorted names still running after shutdown that were not present
    before the run and match the app process family."""
    tokens = tuple((t or "").lower() for t in watch_tokens)
    before_pids = {int(p.get("pid", 0)) for p in before if p.get("pid") is not None}
    orphans: set[str] = set()
    for process in after:
        name = str(process.get("name", ""))
        pid = process.get("pid")
        if pid is None or int(pid) in before_pids:
            continue
        lowered = name.lower()
        if any(token in lowered for token in tokens):
            orphans.add(name)
    return sorted(orphans)


def runtime_paths_exist(resources_root: Path) -> dict[str, bool]:
    """Check the packaged runtime files exist relative to ``resources_root``."""
    resources_root = Path(resources_root).expanduser().resolve()
    result: dict[str, bool] = {}
    for rel, name in PACKAGED_RUNTIME_FILES:
        result[name] = (resources_root / rel).is_file()
    return result


# --------------------------------------------------------------------------- #
# Process + filesystem helpers (only used by the real run)
# --------------------------------------------------------------------------- #

def snapshot_processes() -> list[dict[str, Any]]:
    """Return a lightweight ``{name, pid}`` list of running processes."""
    if sys.platform == "win32":
        try:
            output = subprocess.run(
                ["tasklist.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, check=False, timeout=30,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        processes = []
        for line in output.splitlines():
            parts = line.strip().strip('"').replace('"', "").split(",")
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[1].strip())
            except ValueError:
                continue
            processes.append({"name": parts[0].strip(), "pid": pid})
        return processes
    try:
        out = subprocess.run(
            ["ps", "-e", "-o", "comm="], capture_output=True, text=True, check=False,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [{"name": line.strip(), "pid": 0} for line in out.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Evidence reading + classification (pure, unit-testable)
# --------------------------------------------------------------------------- #

def read_evidence(results_dir: str | Path) -> list[dict[str, Any]]:
    """Parse every ``production-*.jsonl`` record under ``results_dir``."""
    results_dir = Path(results_dir)
    records: list[dict[str, Any]] = []
    if not results_dir.is_dir():
        return records
    for evidence_file in sorted(results_dir.glob("production-*.jsonl")):
        for line in evidence_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"event": "_unparseable", "raw": line[:300]})
    return records


def _compact(record: dict[str, Any]) -> str:
    bits: list[str] = []
    for key in ("event", "stage", "command", "level", "errorCode", "error"):
        value = record.get(key)
        if value not in (None, ""):
            bits.append(f"{key}={value}")
    text = record.get("text") or record.get("message")
    if text:
        bits.append(str(text)[:240])
    return " | ".join(bits) if bits else str(record)[:240]


def classify_host_evidence(
    records: list[dict[str, Any]],
    exit_code: int | None,
) -> dict[str, Any]:
    """Map host evidence records to the acceptance checks (pure).

    The packaged host logs sidecar messages through its logger, so sidecar
    events (``ready``, ``job_restored``) appear as top-level records alongside
    host events (``session_started``, ``page_load_failed``).
    """
    events = [str(r.get("event", "")) for r in records]

    app_launched = "session_started" in events
    ready_records = [r for r in records if str(r.get("event", "")) == "ready"]
    sidecar_ready = bool(ready_records) and not any(
        str(r.get("engine_loaded", "")).lower() == "false" for r in ready_records
    )
    restore_passed = "job_restored" in events

    renderer_failures = [
        _compact(r) for r in records if str(r.get("event", "")) in RENDERER_FAILURE_EVENTS
    ]

    bridge_errors: list[str] = []
    for r in records:
        event = str(r.get("event", ""))
        if event in BRIDGE_FAILURE_EVENTS:
            bridge_errors.append(_compact(r))
            continue
        if event in ("console", "sidecar_stderr", "error"):
            text = " ".join(
                str(r.get(key, "")) for key in ("text", "message", "error", "command", "raw")
            ).lower()
            if event == "error" and r.get("ok") is False:
                bridge_errors.append(_compact(r))
            elif any(marker in text for marker in BRIDGE_ERROR_MARKERS):
                bridge_errors.append(_compact(r))

    unexpected_errors: list[str] = []
    for r in records:
        event = str(r.get("event", ""))
        if event.startswith(("unhandled", "exception")):
            unexpected_errors.append(_compact(r))
        if event == "console" and str(r.get("level", "")) == "error":
            message = str(r.get("message") or r.get("text") or "")
            if any(marker in message.lower() for marker in BRIDGE_ERROR_MARKERS):
                unexpected_errors.append(_compact(r))
        if event == "_unparseable":
            unexpected_errors.append("malformed bridge payload in evidence stream")
    if exit_code is not None and exit_code != 0:
        unexpected_errors.append(f"packaged app exit code {exit_code}")

    return {
        "app_launched": app_launched,
        "sidecar_ready": sidecar_ready,
        "restore_passed": restore_passed,
        "first_exit_clean": exit_code == 0,
        "renderer_failures": renderer_failures,
        "bridge_errors": bridge_errors,
        "unexpected_errors": unexpected_errors,
    }


# --------------------------------------------------------------------------- #
# Export evidence validation (pure, unit-testable)
# --------------------------------------------------------------------------- #

def validate_export(job_dir: str | Path, export_dir: str | Path) -> dict[str, Any]:
    """Return ``{export_completed, export_file_count, files}``.

    The Study Pack export is complete when the export directory exists, is
    non-empty, and contains either the historical ``manifest.json`` marker or
    one of the existing Study Pack HTML/PDF artifacts. ``files`` is a sorted
    relative list for the human summary.
    """
    export_dir = Path(export_dir)
    files: list[str] = []
    if export_dir.is_dir():
        files = sorted(
            p.relative_to(export_dir).as_posix()
            for p in export_dir.rglob("*")
            if p.is_file()
        )
    export_markers = {
        "manifest.json",
        "study-pack.html",
        "study-pack.pdf",
        "study_pack.html",
        "study_pack.pdf",
    }
    completed = export_dir.is_dir() and bool(files) and any(
        Path(relative).name in export_markers for relative in files
    )
    return {
        "export_completed": completed,
        "export_file_count": len(files),
        "files": files,
        "job_dir": str(Path(job_dir)),
        "export_dir": str(export_dir),
    }


# --------------------------------------------------------------------------- #
# Result scoring (pure, unit-testable, deterministic)
# --------------------------------------------------------------------------- #

_REQUIRED_TRUE = (
    "app_launched",
    "sidecar_ready",
    "runtime_paths_ready",
    "job_started",
    "job_completed",
    "slides_generated",
    "transcript_generated",
    "export_completed",
    "first_exit_clean",
    "restore_passed",
)


def score_result(checks: dict[str, Any]) -> dict[str, Any]:
    """Collapse per-gate booleans + evidence arrays into the acceptance result.

    ``checks`` must provide every key named in ``_REQUIRED_TRUE`` plus
    ``export_file_count`` (int) and ``orphan_processes`` / ``renderer_failures`` /
    ``bridge_errors`` / ``unexpected_errors`` (lists). Returns a plain dict with
    exactly the canonical ``ACCEPTANCE_KEYS`` in order, so the JSON is
    deterministic and machine-readable.
    """
    booleans_all_true = all(bool(checks.get(key)) for key in _REQUIRED_TRUE)
    export_has_files = int(checks.get("export_file_count", 0) or 0) > 0
    no_failures = (
        not checks.get("orphan_processes")
        and not checks.get("renderer_failures")
        and not checks.get("bridge_errors")
        and not checks.get("unexpected_errors")
    )
    passed = bool(booleans_all_true and export_has_files and no_failures)
    return {
        "app_launched": bool(checks.get("app_launched")),
        "sidecar_ready": bool(checks.get("sidecar_ready")),
        "runtime_paths_ready": bool(checks.get("runtime_paths_ready")),
        "job_started": bool(checks.get("job_started")),
        "job_completed": bool(checks.get("job_completed")),
        "slides_generated": bool(checks.get("slides_generated")),
        "transcript_generated": bool(checks.get("transcript_generated")),
        "export_completed": bool(checks.get("export_completed")),
        "export_file_count": int(checks.get("export_file_count", 0) or 0),
        "first_exit_clean": bool(checks.get("first_exit_clean")),
        "restore_passed": bool(checks.get("restore_passed")),
        "orphan_processes": list(checks.get("orphan_processes") or []),
        "renderer_failures": list(checks.get("renderer_failures") or []),
        "bridge_errors": list(checks.get("bridge_errors") or []),
        "unexpected_errors": list(checks.get("unexpected_errors") or []),
        "passed": bool(passed),
    }


def dump_result(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=False) + "\n"


def result_to_text(result: dict[str, Any], notes: Iterable[str] = ()) -> str:
    lines = [
        "LecturePack packaged-app acceptance result",
        "=" * 46,
        f"  overall  {'PASS' if result.get('passed') else 'FAIL'}",
        "-" * 46,
    ]
    for key in ACCEPTANCE_KEYS:
        value = result[key]
        if isinstance(value, list):
            marker = "PASS" if not value else "FAIL"
            lines.append(f"  {key:<22} {marker}  {value}")
        else:
            marker = ("PASS" if value else "FAIL") if key != "passed" else "----"
            lines.append(f"  {key:<22} {marker}  {value}")
    note_list = list(notes)
    if note_list:
        lines.append("-" * 46)
        lines.extend(f"  note: {note}" for note in note_list)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Live JSONL sidecar session (used only by the real run)
# --------------------------------------------------------------------------- #

class JsonlSession:
    """Own a subprocess that speaks the sidecar's JSONL stdin/stdout contract."""

    def __init__(self, executable: Path, args: list[str], timeout_s: float = PROTOCOL_TIMEOUT_S):
        self.executable = Path(executable)
        self.args = list(args)
        self.timeout = float(timeout_s)
        self.proc: Optional[subprocess.Popen] = None
        self._queue: queue.Queue[Optional[dict[str, Any]]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self.messages: list[dict[str, Any]] = []
        self.stderr_lines: list[str] = []
        self._request_counter = 0

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [str(self.executable)] + self.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        for line in self.proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                msg = {"event": "error", "error": f"malformed sidecar line: {line[:200]}"}
            if isinstance(msg, dict) and str(msg.get("event", "")):
                self.messages.append(msg)
                self._queue.put(msg)
        for line in self.proc.stderr or []:  # type: ignore[union-attr]
            if line.strip():
                self.stderr_lines.append(line.strip())

    def send(self, command: str, payload: dict[str, Any] | None = None) -> str:
        self._request_counter += 1
        request_id = f"acceptance-{self._request_counter}-{command}"
        self.proc.stdin.write(
            json.dumps({"request_id": request_id, "command": command, "payload": payload or {}}) + "\n"
        )
        self.proc.stdin.flush()
        return request_id

    def _next(self, timeout: float | None) -> dict[str, Any]:
        return self._queue.get(timeout=self.timeout if timeout is None else timeout)

    def wait_event(self, event_name: str, timeout: float | None = None,
                   predicate: Callable[[dict[str, Any]], bool] | None = None) -> dict[str, Any]:
        def matches(msg: dict[str, Any]) -> bool:
            return str(msg.get("event", "")) == event_name and (
                predicate is None or predicate(msg)
            )

        # A request handler may consume an event while waiting for its
        # response. Preserve the evidence history so a later gate assertion
        # can still observe completion events such as export_done.
        for message in self.messages:
            if matches(message):
                return message

        timeout = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            msg = self._next(remaining)
            if matches(msg):
                return msg
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for sidecar event {event_name!r}")

    def request(self, command: str, payload: dict[str, Any] | None = None,
                timeout: float | None = None) -> dict[str, Any]:
        request_id = self.send(command, payload)
        timeout = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            msg = self._next(remaining)
            if str(msg.get("response_to", "")) == request_id:
                return msg
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {command!r} response")

    def close(self) -> int | None:
        if self.proc is None:
            return None
        try:
            if self.proc.poll() is None:
                try:
                    self.proc.stdin.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
        finally:
            pass
        return self.proc.returncode


def discover_sidecar(app_dir: Path) -> Optional[Path]:
    """Locate the bundled ``LecturePackSidecar.exe`` under the packaged app."""
    app_dir = Path(app_dir)
    for rel in (
        "resources/LecturePackSidecar/LecturePackSidecar.exe",
        "resources/sidecar/LecturePackSidecar.exe",
        "resources/LecturePackSidecar.exe",
        "resources/_internal/LecturePackSidecar/LecturePackSidecar.exe",
    ):
        candidate = app_dir / rel
        if candidate.is_file():
            return candidate
    matches = list(app_dir.rglob(SIDECAR_EXE_NAME))
    return matches[0] if matches else None


def locate_resources_root(sidecar_exe: Path) -> Path:
    """Resources root that contains ``bin/`` and ``models/`` for the sidecar."""
    for candidate in (sidecar_exe.parent, sidecar_exe.parent / "_internal", sidecar_exe.parent.parent):
        if (candidate / "bin").is_dir() and (candidate / "models").is_dir():
            return candidate
    return sidecar_exe.parent


def locate_export_dir(job_root: Path) -> Path:
    """Return the Study Pack export directory under ``job_root`` if present."""
    for candidate in (job_root / "exports", job_root / "export"):
        if candidate.is_dir():
            return candidate
    for candidate in job_root.rglob("exports"):
        if candidate.is_dir():
            return candidate
    return job_root / "exports"


def _run_sidecar_gate(
    sidecar: Path,
    resources_root: Path,
    data_dir: Path,
    demo_video: Path,
    timeout_s: float,
) -> tuple[dict[str, Any], list[str]]:
    """Drive the packaged sidecar through a real end-to-end job; return checks + notes.

    Verifies requirements 3-7 against the *bundled runtime* without any UI or
    CDP, by speaking the exact JSONL contract the packaged host uses internally.
    """
    checks = {
        "sidecar_ready": False,
        "runtime_paths_ready": False,
        "job_started": False,
        "job_completed": False,
        "slides_generated": False,
        "transcript_generated": False,
        "export_completed": False,
        "export_file_count": 0,
        "first_exit_clean": True,
    }
    notes: list[str] = []
    if not demo_video.is_file():
        notes.append(f"demo video not found: {demo_video}")
        return checks, notes
    session = JsonlSession(
        sidecar,
        [
            "--resources-root", str(resources_root),
            "--data-dir", str(data_dir),
            "--demo-video", str(demo_video),
        ],
        timeout_s=timeout_s,
    )
    session.start()
    job_id: str = ""
    try:
        ready = session.wait_event("ready", timeout=min(timeout_s, PROTOCOL_TIMEOUT_S))
        checks["sidecar_ready"] = ready.get("engine_loaded") is True

        health = session.request("health_check")
        paths = health.get("paths") if isinstance(health.get("paths"), dict) else {}
        checks["runtime_paths_ready"] = bool(paths) and all(
            bool(p.get("exists")) for p in paths.values()
        ) and all(p.get("exists") for p in paths.values() if isinstance(p, dict))

        imported = session.request(
            "import_video", {"path": str(demo_video), "bundled_demo": True}
        )
        job_id = str(imported.get("job_id") or "")

        started = session.request("start_job", {"job_id": job_id, "mode": "study", "auto_export": True})
        checks["job_started"] = bool(started.get("ok") or started.get("started"))

        session.wait_event("job_completed", timeout=timeout_s)
        checks["job_completed"] = True

        slides = session.request("get_slides", {"job_id": job_id})
        checks["slides_generated"] = bool(slides.get("slides"))

        transcript = session.request("get_transcript", {"job_id": job_id})
        checks["transcript_generated"] = bool(transcript.get("transcript"))

        if not any(str(message.get("event", "")) == "export_done" for message in session.messages):
            session.request("export", {"job_id": job_id})
            session.wait_event("export_done", timeout=min(timeout_s, PROTOCOL_TIMEOUT_S))
        job_root = data_dir / "jobs" / job_id
        export = validate_export(job_root, locate_export_dir(job_root))
        checks["export_completed"] = export["export_completed"]
        checks["export_file_count"] = export["export_file_count"]
        notes.append(f"export files: {export['files']}")

        session.request("shutdown")
        code = session.close()
        checks["first_exit_clean"] = code == 0
        if code != 0:
            notes.append(f"sidecar shutdown exit code {code}")
    except (TimeoutError, subprocess.SubprocessError) as exc:
        notes.append(f"sidecar gate raised: {exc}")
        session.close()
        if session.proc is not None and session.proc.poll() is None:
            try:
                session.proc.kill()
            except Exception:  # noqa: BLE001
                pass
    return checks, notes


def _close_app_window(pid: int) -> bool:
    """Ask the app's top-level window to close (WM_CLOSE) so it exits cleanly."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False
    user32 = ctypes.windll.user32
    sent = [False]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd: int, _lparam: int) -> int:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            sent[0] = True
            return False
        return True

    user32.EnumWindows(_cb, 0)
    return sent[0]


def _read_new_jsonl(results_dir: Path, baseline_files: set[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for evidence_file in sorted(results_dir.glob("production-*.jsonl")):
        if evidence_file in baseline_files:
            continue
        for line in evidence_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"event": "_unparseable"})
    return records


def _evidence_has(records: list[dict[str, Any]], event: str) -> bool:
    return any(str(r.get("event", "")) == event for r in records)


def _run_host_once(
    exe: Path,
    results_dir: Path,
    data_dir: Path,
    timeout_s: float,
    label: str,
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Launch the packaged app once; return (host_checks, orphans, new_evidence)."""
    results_dir.mkdir(parents=True, exist_ok=True)
    baseline_files = set(results_dir.glob("production-*.jsonl"))
    env = os.environ.copy()
    env["LECTUREPACK_DATA_DIR"] = str(data_dir)
    before = snapshot_processes()

    proc = subprocess.Popen(
        [str(exe), "--results", str(results_dir), "--data-dir", str(data_dir)],
        cwd=str(exe.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        poll_until(
            lambda: proc.poll() is not None
            or _evidence_has(_read_new_jsonl(results_dir, baseline_files), "session_started"),
            timeout_s,
            label=f"{label}: launch evidence",
        )
        poll_until(
            lambda: proc.poll() is not None
            or _evidence_has(_read_new_jsonl(results_dir, baseline_files), "ready"),
            timeout_s,
            label=f"{label}: sidecar ready",
        )
        try:
            poll_until(
                lambda: proc.poll() is not None
                or _evidence_has(_read_new_jsonl(results_dir, baseline_files), "job_restored"),
                min(timeout_s, 30.0),
                label=f"{label}: job restore",
            )
        except TimeoutError:
            # Keep the run bounded and let classify_host_evidence report the
            # missing restore as a failed acceptance check.
            pass
        if proc.poll() is None and not _close_app_window(proc.pid):
            proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    after = snapshot_processes()
    orphans = detect_orphans(before, after)
    records = _read_new_jsonl(results_dir, baseline_files)
    host = classify_host_evidence(records, proc.returncode)
    return host, orphans, records


def _empty_checks() -> dict[str, Any]:
    return {
        "app_launched": False,
        "sidecar_ready": False,
        "runtime_paths_ready": False,
        "job_started": False,
        "job_completed": False,
        "slides_generated": False,
        "transcript_generated": False,
        "export_completed": False,
        "export_file_count": 0,
        "first_exit_clean": False,
        "restore_passed": False,
        "orphan_processes": [],
        "renderer_failures": [],
        "bridge_errors": [],
        "unexpected_errors": [],
    }


def _merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "sidecar_ready", "runtime_paths_ready", "job_started", "job_completed",
        "slides_generated", "transcript_generated", "export_completed",
    ):
        if source.get(key):
            target[key] = True
    if source.get("export_file_count"):
        target["export_file_count"] = int(source["export_file_count"])


def run_gate(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    """Run the whole acceptance gate against a real packaged build.

    Returns ``(result, notes)``. The disposable data dir is removed afterwards
    unless ``--keep-data`` was passed.
    """
    notes: list[str] = []
    allowed, reason = data_dir_status(args.data_dir)
    if not allowed:
        checks = _empty_checks()
        checks["unexpected_errors"] = [f"data-dir rejected: {reason}"]
        return score_result(checks), [reason]

    app_dir = Path(args.app_dir)
    exe = discover_app_exe(app_dir)
    if exe is None:
        checks = _empty_checks()
        checks["unexpected_errors"] = [f"packaged executable not found under {app_dir}"]
        return score_result(checks), [str(checks["unexpected_errors"][0])]

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    results_dir = Path(args.results_dir) if args.results_dir else Path(
        tempfile.mkdtemp(prefix="lp-acceptance-results-")
    )
    results_dir.mkdir(parents=True, exist_ok=True)
    notes.append(f"results dir: {results_dir}")
    timeout = max(1.0, float(args.timeout_seconds))

    demo = resolve_args_path(args.demo_video)
    if demo is None:
        for rel in (
            "assets/demo-lecture.mp4",
            "resources/assets/demo-lecture.mp4",
            "resources/demo-lecture.mp4",
        ):
            candidate = app_dir / rel
            if candidate.is_file():
                demo = candidate
                break
    if demo is None:
        matches = list(app_dir.rglob("demo-lecture.mp4")) + list(Path("electron-spike/assets").glob("demo-lecture.mp4"))
        demo = matches[0] if matches else None
    if demo is None:
        notes.append("demo video not found; importing relies on host evidence")

    checks = _empty_checks()

    sidecar = Path(args.sidecar) if args.sidecar else discover_sidecar(exe.parent)
    if sidecar is not None and sidecar.is_file() and demo is not None:
        resources_root = locate_resources_root(sidecar)
        sc_checks, sc_notes = _run_sidecar_gate(sidecar, resources_root, data_dir, demo, timeout)
        _merge_into(checks, sc_checks)
        notes.extend(sc_notes)
    else:
        notes.append("bundled sidecar or demo video unavailable; processing/export gates use host evidence only")

    host1, orphans1, _ = _run_host_once(exe, results_dir, data_dir, timeout, "first")
    host2, orphans2, _ = _run_host_once(exe, results_dir, data_dir, timeout, "relaunch")

    checks["app_launched"] = host1["app_launched"] and host2["app_launched"]
    checks["sidecar_ready"] = checks["sidecar_ready"] or (host1["sidecar_ready"] and host2["sidecar_ready"])
    checks["first_exit_clean"] = host1["first_exit_clean"]
    checks["restore_passed"] = host2["restore_passed"]
    checks["orphan_processes"] = sorted(set(orphans1 + orphans2))
    checks["renderer_failures"] = host1["renderer_failures"] + host2["renderer_failures"]
    checks["bridge_errors"] = host1["bridge_errors"] + host2["bridge_errors"]
    checks["unexpected_errors"] = host1["unexpected_errors"] + host2["unexpected_errors"]

    result = score_result(checks)
    (results_dir / "acceptance-result.json").write_text(dump_result(result), encoding="utf-8")
    (results_dir / "acceptance-summary.txt").write_text(
        result_to_text(result, notes), encoding="utf-8"
    )

    if not args.keep_data:
        shutil.rmtree(data_dir, ignore_errors=True)
    return result, notes


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="electron_packaged_acceptance",
        description="Release gate for the Phase 8 packaged Electron LecturePack app "
                    "(drive-by-evidence; never touches the user LecturePackData).",
    )
    ap.add_argument("--app-dir", required=True,
                    help="Packaged Electron directory containing LecturePack.exe")
    ap.add_argument("--data-dir", required=True,
                    help="Disposable data directory (must NOT be the user LecturePackData)")
    ap.add_argument("--results-dir", default=None,
                    help="Where acceptance-result.json + acceptance-summary.txt are written")
    ap.add_argument("--demo-video", default=None,
                    help="Bundled demo video used for the processing gate")
    ap.add_argument("--timeout-seconds", type=float, default=300.0,
                    help="Bound on each wait (sidecar job + host launch/restore)")
    ap.add_argument("--keep-data", action="store_true",
                    help="Keep the disposable data directory after the run")
    ap.add_argument("--sidecar", default=None,
                    help="Explicit path to LecturePackSidecar.exe (auto-discovered otherwise)")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    allowed, reason = data_dir_status(args.data_dir)
    if not allowed:
        sys.stderr.write(f"electron_packaged_acceptance: refusing unsafe data dir: {reason}\n")
        return 2
    result, notes = run_gate(args)
    summary = result_to_text(result, notes)
    sys.stdout.write(summary)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())





