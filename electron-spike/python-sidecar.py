"""Headless LecturePack sidecar for the Electron migration vertical slice.

The sidecar deliberately uses ``QCoreApplication`` because the existing
controller still uses QtCore ``QProcess``, ``QThread``, and ``QTimer``. It does
not create a widget, a Qt window, or a WebEngine view. The processing engine is
reused unchanged behind a small request-id JSONL contract over stdin/stdout.

Commands:
    health_check, list_jobs, import_video, start_job, cancel_job, get_job,
    get_slides, get_transcript, export, set_setting, shutdown

Events:
    ready, bootstrap_progress, bootstrap_complete, jobs_changed,
    pipeline_changed, status_changed, log_line, slides_changed,
    transcript_changed, export_progress, error
"""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import queue
import re
import shutil
import sys
import threading
import time
from typing import Any

from PySide6.QtCore import QCoreApplication, QProcess, QTimer

# Reject unsafe job ids for any path-traversal-sensitive operation (delete,
# group, rename, open). A job id is a UUID-safe token; anything else is refused.
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


STAGES = [
    "Inspect",
    "Extract Audio",
    "Transcribe",
    "Detect Slides",
    "Align",
    "Review Ready",
    "Export",
]


def _clock(seconds: float) -> str:
    value = max(0.0, float(seconds or 0.0))
    whole = int(value)
    millis = int(round((value - whole) * 1000))
    if millis >= 1000:
        whole += 1
        millis = 0
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _duration_label(seconds: float) -> str:
    value = max(0, int(round(float(seconds or 0.0))))
    hours, rem = divmod(value, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _as_uri(path: Path) -> str:
    try:
        return path.resolve().as_uri()
    except (OSError, ValueError):
        return ""


class Sidecar:
    """Own the QtCore event loop and adapt the existing engine to JSONL."""

    def __init__(self, args: argparse.Namespace, app: QCoreApplication):
        self.app = app
        self.args = args
        self._commands: queue.Queue[Any] = queue.Queue()
        self._stdout_lock = threading.Lock()
        self._stdin_thread = threading.Thread(
            target=self._read_stdin,
            name="LecturePackSidecarStdin",
            daemon=True,
        )

        self.session_id = f"electron-sidecar-{os.getpid()}"
        self.current_job = None
        self.controller = None
        self.current_stage = ""
        self.stage_percent: dict[str, int] = {}
        self.backend_label = ""
        self.auto_export = True
        self._shutting_down = False
        self._shutdown_started_at = 0.0
        self._shutdown_timer: QTimer | None = None
        self._engine_error = ""

        self.repo_root = self._resolve_repo_root()
        if self.repo_root and str(self.repo_root) not in sys.path:
            sys.path.insert(0, str(self.repo_root))
        self.runtime_root = self._resolve_runtime_root()
        self.data_dir = Path(args.data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.demo_video = Path(args.demo_video).expanduser().resolve() if args.demo_video else None

        self._emit({
            "event": "bootstrap_progress",
            "id": "python_import",
            "state": "checking",
            "detail": "Loading the existing LecturePack engine",
        })
        self._load_engine()
        self._emit({
            "event": "bootstrap_progress",
            "id": "engine_import",
            "state": "failed" if self._engine_error else "resolved",
            "detail": self._engine_error or "LecturePack controller imports resolved",
        })
        self._configure_runtime()
        self._emit({
            "event": "bootstrap_progress",
            "id": "runtime_config",
            "state": "failed" if self._engine_error else "resolved",
            "detail": self._engine_error or "Bundled CPU runtime paths resolved",
        })
        self._connect_controller()
        self._emit({
            "event": "bootstrap_progress",
            "id": "controller",
            "state": "failed" if self._engine_error else "resolved",
            "detail": self._engine_error or "Headless JobController connected",
        })
        self._init_queue()
        self._emit({
            "event": "bootstrap_progress",
            "id": "queue",
            "state": "failed" if self._engine_error else "resolved",
            "detail": self._engine_error or "Persistent job queue restored",
        })

        self._poll_timer = QTimer(self.app)
        self._poll_timer.setInterval(25)
        self._poll_timer.timeout.connect(self._drain_commands)
        self._poll_timer.start()

        self._emit({
            "event": "ready",
            "protocol_version": 1,
            "pid": os.getpid(),
            "engine_loaded": not bool(self._engine_error),
            "engine": "lecturepack",
            "controller": "lecturepack.controllers.job_controller.JobController",
            "qt_application": "QCoreApplication",
            "runtime_root": str(self.runtime_root),
            "data_dir": str(self.data_dir),
            **({"error": self._engine_error} if self._engine_error else {}),
        })
        self._emit({
            "event": "bootstrap_progress",
            "id": "python_import",
            "state": "resolved" if not self._engine_error else "failed",
            "detail": "Headless sidecar ready" if not self._engine_error else self._engine_error,
        })
        self._emit({
            "event": "bootstrap_complete",
            "bootstrap_pending": False,
            "runtime_health_state": "HEALTHY" if not self._engine_error else "SETUP_REQUIRED",
            "setup_acknowledged": not bool(self._engine_error),
            "healthy": not bool(self._engine_error),
            "engine_loaded": not bool(self._engine_error),
        })
        # Do not start a blocking Windows pipe read while importing OpenCV,
        # PySide6 workers, and the existing controller. In the locked Windows
        # runtime that can starve the importing thread; starting it after the
        # ready handshake keeps the JSONL boundary responsive without changing
        # the engine internals.
        self._stdin_thread.start()

    # ------------------------------------------------------------------ #
    # Process and import setup
    # ------------------------------------------------------------------ #
    def _resolve_repo_root(self) -> Path | None:
        if self.args.repo_root:
            return Path(self.args.repo_root).expanduser().resolve()
        if getattr(sys, "frozen", False):
            return None
        candidate = Path(__file__).resolve().parents[1]
        return candidate if (candidate / "lecturepack").is_dir() else None

    def _resolve_runtime_root(self) -> Path:
        if self.args.resources_root:
            candidate = Path(self.args.resources_root).expanduser().resolve()
            # PyInstaller 6 onedir places collected data under _internal while
            # keeping the console executable one directory above it.
            if (candidate / "bin").is_dir():
                return candidate
            if (candidate / "_internal" / "bin").is_dir():
                return candidate / "_internal"
            return candidate
        if getattr(sys, "frozen", False):
            candidate = Path(sys.executable).resolve().parent
            return candidate / "_internal" if (candidate / "_internal" / "bin").is_dir() else candidate
        return self.repo_root or Path(__file__).resolve().parents[1]

    def _load_engine(self) -> None:
        try:
            from lecturepack.controllers.job_controller import JobController
            from lecturepack.infrastructure.config_manager import ConfigManager
            from lecturepack.infrastructure.file_manager import FileManager
            from lecturepack.models.job import Job
            from lecturepack import electron_backend, electron_study
            from lecturepack.services import media_fetch, study_service, transcript_store
            from lecturepack.services import study_presets
            from lecturepack.services.job_queue import JobQueue

            self.JobController = JobController
            self.ConfigManager = ConfigManager
            self.FileManager = FileManager
            self.Job = Job
            self.transcript_store = transcript_store
            self.JobQueue = JobQueue
            self.electron_backend = electron_backend
            self.electron_study = electron_study
            self.media_fetch = media_fetch
            self.study_service = study_service
            self.study_presets = study_presets
        except Exception as exc:  # noqa: BLE001 - surfaced through ready/error
            self._engine_error = f"{type(exc).__name__}: {exc}"

    def _first_file(self, *candidates: Path) -> str:
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return ""

    def _configure_runtime(self) -> None:
        if self._engine_error:
            return
        self.config = self.ConfigManager(str(self.data_dir))
        ffmpeg = self._first_file(
            self.runtime_root / "bin" / "ffmpeg.exe",
            self.runtime_root / "ffmpeg.exe",
        )
        ffprobe = self._first_file(
            self.runtime_root / "bin" / "ffprobe.exe",
            self.runtime_root / "ffprobe.exe",
        )
        whisper = self._first_file(
            self.runtime_root / "bin" / "Release" / "whisper-cli.exe",
            self.runtime_root / "bin" / "whisper-cli.exe",
            self.runtime_root / "whisper-cli.exe",
        )
        model = self._first_file(
            self.runtime_root / "models" / "ggml-base.en.bin",
            self.runtime_root / "ggml-base.en.bin",
        )
        if not all((ffmpeg, ffprobe, whisper, model)):
            missing = [
                name for name, value in (
                    ("ffmpeg", ffmpeg),
                    ("ffprobe", ffprobe),
                    ("whisper", whisper),
                    ("model", model),
                ) if not value
            ]
            self._engine_error = "Missing packaged runtime: " + ", ".join(missing)
            return

        # Use the locked, packaged paths for this slice. The existing engine
        # still owns discovery and execution; the sidecar only supplies its
        # runtime configuration and selects the verified CPU binary.
        self.config.settings.update({
            "ffmpeg_exe": ffmpeg,
            "ffprobe_exe": ffprobe,
            "whisper_exe": whisper,
            "whisper_model": model,
            "engine": "cpu",
            "parallel_pipeline": True,
        })
        self.config.save()

    def _connect_controller(self) -> None:
        if self._engine_error:
            return
        try:
            self.controller = self.JobController(self.config)
            self.controller.stage_started.connect(self._on_stage_started)
            self.controller.stage_progress.connect(self._on_stage_progress)
            self.controller.stage_log.connect(self._on_stage_log)
            self.controller.stage_finished.connect(self._on_stage_finished)
            self.controller.stage_cached.connect(self._on_stage_cached)
            self.controller.backend_info.connect(self._on_backend_info)
            self.controller.transcript_segment.connect(self._on_transcript_segment)
            self.controller.pipeline_completed.connect(self._on_pipeline_completed)
            self.controller.pipeline_failed.connect(self._on_pipeline_failed)
        except Exception as exc:  # noqa: BLE001 - surfaced through ready/error
            self._engine_error = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    # Persistent queue
    # ------------------------------------------------------------------ #
    def _init_queue(self) -> None:
        """Restore the persistent job queue and reconcile schedules on launch."""
        if self._engine_error:
            return
        try:
            self.queue = self.JobQueue(str(self.data_dir))
            # Bring any due/missed schedules into the queue per their policy.
            self.queue.reconcile_schedules_on_launch()
        except Exception as exc:  # noqa: BLE001 - a queue failure must not kill startup
            self._engine_error = f"{type(exc).__name__}: {exc}"

    def _push_queue(self) -> None:
        """Emit queue_changed with the active slot, rows, and schedules."""
        if not hasattr(self, "queue"):
            return
        rows = [{"id": jid, "position": pos}
                for pos, jid in enumerate(self.queue.queued())]
        self._emit({
            "event": "queue_changed",
            "active": self.queue.active,
            "queue": rows,
            "schedules": self.queue.schedules(),
        })

    def _reconcile_queue_on_startup(self) -> None:
        """Resolve schedules that came due while the app was closed."""
        if not hasattr(self, "queue"):
            return
        try:
            self.queue.reconcile_schedules_on_launch()
        except Exception:
            pass

    def _promote_next(self) -> None:
        """Release the active slot and launch the next queued job (FIFO)."""
        if not hasattr(self, "queue"):
            return
        if self.current_job is not None:
            self.queue.finish_active(self.current_job.job_id)
        nxt = self.queue.promote_next()
        self._push_queue()
        if not nxt:
            return
        try:
            job = self._job_for({"job_id": nxt})
        except Exception:
            return
        # Defer so the just-finished pipeline fully unwinds before the next one.
        QTimer.singleShot(0, lambda: self._start_queued(job))

    def _start_queued(self, job: Any) -> None:
        """Start a queued job (no request_id; fire-and-forget)."""
        if self.controller is None or self._shutting_down:
            return
        if self.current_stage:
            return
        self._activate_job(job, emit_payloads=False)
        self.auto_export = True
        self.current_stage = "Queued"
        self._emit({"event": "job_started", "job_id": job.job_id})
        self._emit_job_payloads()
        self._push_queue()
        self.controller.run_pipeline()

    # ------------------------------------------------------------------ #
    # JSONL process boundary
    # ------------------------------------------------------------------ #
    def _emit(self, payload: dict[str, Any]) -> None:
        try:
            # Keep JSONL bytes ASCII-safe across Windows code pages. JSON.parse
            # restores escaped Unicode in the renderer without replacement
            # characters at the process boundary.
            line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            with self._stdout_lock:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
        except (BrokenPipeError, OSError):
            self._shutting_down = True
            self.app.quit()

    def _respond(self, request_id: str | None, command: str, **payload: Any) -> None:
        if not request_id:
            return
        self._emit({
            "event": "response",
            "response_to": request_id,
            "command": command,
            "ok": True,
            **payload,
        })

    def _fail(self, request_id: str | None, command: str, message: str) -> None:
        self._emit({
            "event": "error",
            "response_to": request_id,
            "command": command,
            "ok": False,
            "error": str(message),
        })

    def _read_stdin(self) -> None:
        try:
            for line in sys.stdin:
                self._commands.put(line)
        finally:
            self._commands.put(None)

    def _drain_commands(self) -> None:
        for _ in range(50):
            try:
                raw = self._commands.get_nowait()
            except queue.Empty:
                return
            if raw is None:
                self._request_shutdown()
                return
            try:
                message = json.loads(str(raw).strip())
            except json.JSONDecodeError as exc:
                self._emit({"event": "error", "error": f"invalid JSON: {exc.msg}"})
                continue
            if not isinstance(message, dict):
                self._emit({"event": "error", "error": "JSONL command must be an object"})
                continue
            self._handle_command(message)

    def _handle_command(self, message: dict[str, Any]) -> None:
        request_id = str(message.get("request_id") or "") or None
        command = str(message.get("command") or "")
        payload = message.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        try:
            if command == "health_check":
                self._health_check(request_id, command)
            elif command == "list_jobs":
                self._list_jobs(request_id, command)
            elif command == "import_video":
                self._import_video(request_id, command, payload)
            elif command == "start_job":
                self._start_job(request_id, command, payload)
            elif command == "cancel_job":
                self._cancel_job(request_id, command, payload)
            elif command == "get_job":
                self._get_job(request_id, command, payload)
            elif command == "get_slides":
                self._get_slides(request_id, command, payload)
            elif command == "get_transcript":
                self._get_transcript(request_id, command, payload)
            elif command == "set_slide_state":
                self._set_slide_state(request_id, command, payload)
            elif command == "save_corrections":
                self._save_corrections(request_id, command, payload)
            elif command == "export":
                self._export(request_id, command, payload)
            elif command == "set_setting":
                self._set_setting(request_id, command, payload)
            elif command == "delete_job":
                self._delete_job(request_id, command, payload)
            elif command == "delete_jobs":
                self._delete_jobs(request_id, command, payload)
            elif command == "enqueue_job":
                self._enqueue_job(request_id, command, payload)
            elif command == "reorder_queue":
                self._reorder_queue(request_id, command, payload)
            elif command == "run_now":
                self._run_now(request_id, command, payload)
            elif command == "remove_from_queue":
                self._remove_from_queue(request_id, command, payload)
            elif command == "schedule_job":
                self._schedule_job(request_id, command, payload)
            elif command == "unschedule_job":
                self._unschedule_job(request_id, command, payload)
            elif command == "pause_job":
                self._pause_job(request_id, command, payload)
            elif command == "resume_job":
                self._resume_job(request_id, command, payload)
            elif command == "restart_job":
                self._restart_job(request_id, command, payload)
            elif command == "retry_stage":
                self._retry_stage(request_id, command, payload)
            elif command == "set_job_group":
                self._set_job_group(request_id, command, payload)
            elif command == "set_jobs_group":
                self._set_jobs_group(request_id, command, payload)
            elif command == "rename_job":
                self._rename_job(request_id, command, payload)
            elif command == "media_link_support":
                self._media_link_support(request_id, command)
            elif command == "probe_media_url":
                self._probe_media_url(request_id, command, payload)
            elif command == "import_media_url":
                self._import_media_url(request_id, command, payload)
            elif command == "cancel_media_url":
                self._cancel_media_url(request_id, command)
            elif command == "get_settings":
                self._get_settings(request_id, command)
            elif command == "ask_ai":
                self._ask_ai(request_id, command, payload)
            elif command == "generate_quiz":
                self._generate_quiz(request_id, command, payload)
            elif command == "cancel_quiz":
                self._cancel_quiz(request_id, command)
            elif command == "save_quiz_session":
                self._save_quiz_session(request_id, command, payload)
            elif command == "generate_flashcards":
                self._generate_flashcards(request_id, command, payload)
            elif command == "cancel_flashcards":
                self._cancel_flashcards(request_id, command)
            elif command == "save_flashcard_session":
                self._save_flashcard_session(request_id, command, payload)
            elif command == "save_notes":
                self._save_notes(request_id, command, payload)
            elif command == "smart_study_status":
                self._smart_study_status(request_id, command)
            elif command == "set_study_preset":
                self._set_study_preset(request_id, command, payload)
            elif command == "install_smart_study":
                self._install_smart_study(request_id, command, payload)
            elif command == "cancel_smart_study":
                self._cancel_smart_study(request_id, command)
            elif command == "launch_ollama_installer":
                self._launch_ollama_installer(request_id, command)
            elif command == "list_ollama_models":
                self._list_ollama_models(request_id, command)
            elif command == "set_groq_key":
                self._set_groq_key(request_id, command, payload)
            elif command == "remove_groq_key":
                self._remove_groq_key(request_id, command)
            elif command == "test_groq_key":
                self._test_groq_key(request_id, command)
            elif command == "test_endpoint":
                self._test_endpoint(request_id, command)
            elif command == "run_diagnostics":
                self._run_diagnostics(request_id, command, payload)
            elif command == "validate_vulkan":
                self._validate_vulkan(request_id, command)
            elif command == "validate_cuda":
                self._validate_cuda(request_id, command)
            elif command == "cuda_pack_status":
                self._cuda_pack_status(request_id, command)
            elif command == "install_cuda_pack":
                self._install_cuda_pack(request_id, command)
            elif command == "cancel_cuda_pack":
                self._cancel_cuda_pack(request_id, command)
            elif command == "get_notification_prefs":
                self._get_notification_prefs(request_id, command)
            elif command == "set_notification_prefs":
                self._set_notification_prefs(request_id, command, payload)
            elif command == "test_notification":
                self._test_notification(request_id, command)
            elif command == "repair_selection":
                self._repair_selection(request_id, command)
            elif command == "shutdown":
                self._respond(request_id, command, shutting_down=True)
                self._request_shutdown()
            else:
                self._fail(request_id, command, f"unsupported command: {command!r}")
        except Exception as exc:  # noqa: BLE001 - protocol must report failures
            message_text = f"{type(exc).__name__}: {exc}"
            self._emit({"event": "error", "command": command, "error": message_text})
            self._fail(request_id, command, message_text)

    # ------------------------------------------------------------------ #
    # Contract commands
    # ------------------------------------------------------------------ #
    def _health_check(self, request_id: str | None, command: str) -> None:
        paths = {
            "ffmpeg": self.config.get("ffmpeg_exe", "") if hasattr(self, "config") else "",
            "ffprobe": self.config.get("ffprobe_exe", "") if hasattr(self, "config") else "",
            "whisper": self.config.get("whisper_exe", "") if hasattr(self, "config") else "",
            "model": self.config.get("whisper_model", "") if hasattr(self, "config") else "",
        }
        if self._engine_error:
            self._emit({"event": "runtime_missing", "component": "runtime",
                        "detail": self._engine_error})
        self._respond(
            request_id,
            command,
            healthy=not bool(self._engine_error),
            engine_loaded=not bool(self._engine_error),
            qt_application="QCoreApplication",
            paths={name: {"path": value, "exists": bool(value and os.path.isfile(value))}
                   for name, value in paths.items()},
            error=self._engine_error,
        )

    def _job_objects(self) -> list[Any]:
        if self._engine_error:
            return []
        root = self.data_dir / "jobs"
        if not root.is_dir():
            return []
        jobs = []
        for directory in sorted(root.iterdir()):
            if not directory.is_dir() or not (directory / "manifest.json").is_file():
                continue
            try:
                jobs.append(self.Job(str(self.data_dir), job_id=directory.name,
                                     current_session_id=self.session_id))
            except Exception as exc:  # noqa: BLE001 - one corrupt job must not hide others
                self._emit({"event": "error", "error": f"job {directory.name}: {exc}"})
        jobs.sort(key=lambda job: str(job.manifest.get("created_at", "")), reverse=True)
        return jobs

    def _job_status(self, job: Any) -> str:
        lifecycle = str(job.state.get("lifecycle", ""))
        overall = str(job.state.get("overall_status", "pending"))
        if lifecycle == "completed" or overall == "completed":
            return "done"
        if lifecycle == "failed" or overall == "failed":
            return "failed"
        if lifecycle == "cancelled" or overall == "cancelled":
            return "cancelled"
        if lifecycle == "interrupted" or overall == "interrupted":
            return "interrupted"
        if lifecycle in {"running", "pause_requested"} or overall == "running":
            return "running"
        if lifecycle == "paused":
            return "paused"
        return "queued"

    def _is_active_processing(self, job: Any) -> bool:
        """Keep the UI badge running until the active export is complete.

        The controller can persist a completed pipeline state before the
        sidecar's automatic Study Pack export has finished. The existing UI
        has a ``running`` badge (not a separate ``processing`` value), so the
        adapter keeps that established value authoritative while this active
        request still has a stage and Export is not complete.
        """
        same_job = self.current_job is job or (
            self.current_job is not None
            and str(getattr(self.current_job, "job_id", "")) == str(getattr(job, "job_id", ""))
        )
        if not same_job or not self.current_stage:
            return False
        if str(job.state.get("lifecycle", "")) in {"failed", "cancelled"}:
            return False
        if str(job.state.get("overall_status", "")) in {"failed", "cancelled"}:
            return False
        return job.get_stage_status("Export") != "completed"

    def _job_percent(self, job: Any) -> int:
        completed = 0
        active = 0
        for stage in STAGES:
            status = job.get_stage_status(stage)
            if status == "completed":
                completed += 1
            elif status == "running":
                active = self.stage_percent.get(stage, 0)
        return max(0, min(100, round((completed + active / 100.0) / len(STAGES) * 100)))

    def _summary(self, job: Any) -> dict[str, Any]:
        source = job.manifest.get("source", {}) or {}
        duration = float(job.source.get("duration", 0.0) or 0.0)
        same_job = self.current_job is job or (
            self.current_job is not None
            and str(getattr(self.current_job, "job_id", "")) == str(getattr(job, "job_id", ""))
        )
        active = self.current_stage if same_job else ""
        status = "running" if self._is_active_processing(job) else self._job_status(job)
        return {
            "id": job.job_id,
            "name": job.manifest.get("title") or source.get("filename") or "Lecture",
            "file": source.get("filename", ""),
            "status": status,
            "pct": self._job_percent(job),
            "stage": active or self._last_stage(job),
            "meta": f"{_duration_label(duration)} - local Electron sidecar" if duration else "local Electron sidecar",
            "duration": duration,
            "updated_at": job.state.get("last_updated", ""),
        }

    @staticmethod
    def _last_stage(job: Any) -> str:
        for stage in reversed(STAGES):
            if job.get_stage_status(stage) == "completed":
                return stage
        return "Queued"

    def _list_jobs(self, request_id: str | None, command: str) -> None:
        jobs = self._job_objects()
        if jobs and self.current_job is None:
            self._activate_job(jobs[0], emit_payloads=False)
        summaries = [self._summary(job) for job in jobs]
        self._emit({"event": "jobs_changed", "jobs": summaries})
        if self.current_job is not None:
            self._emit({
                "event": "active_job",
                "id": self.current_job.job_id,
                "title": self.current_job.manifest.get("title", "Lecture"),
            })
        else:
            self._emit({"event": "active_job", "id": "", "title": ""})
        self._respond(request_id, command, jobs=summaries)

    def _resolve_demo_video(self) -> Path | None:
        """Resolve the bundled demo video for the normal import path.

        The packaged app ships the demo under resources/assets/demo-lecture.mp4
        (package-win.mjs extraResource). The sidecar also accepts an explicit
        --demo-video for developer runs. The demo always flows through the
        normal import_video path; there is no separate fake demo pipeline.
        """
        if self.demo_video is not None and self.demo_video.is_file():
            return self.demo_video
        candidates = [
            self.runtime_root / "assets" / "demo-lecture.mp4",
            self.runtime_root / "demo-lecture.mp4",
        ]
        if self.repo_root is not None:
            candidates.append(self.repo_root / "electron-spike" / "assets" / "demo-lecture.mp4")
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _copy_demo_if_needed(self, source: Path) -> Path:
        target = self.data_dir / "demo-inputs" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve() and not target.is_file():
            shutil.copy2(source, target)
        return target if target.is_file() else source

    def _generate_poster(self, job: Any, source: Path) -> None:
        """Extract an instant job-card thumbnail at import time.

        The renderer requests ``lpasset://poster/<job_id>/poster`` which the
        Electron main resolves to this file. Generating it here (a fast frame
        at t=0) makes the card thumbnail appear immediately after import,
        before any processing begins. A failure must never prevent the import.
        """
        try:
            ffmpeg = self.config.get("ffmpeg_exe", "") if hasattr(self, "config") else ""
            if not ffmpeg or not os.path.isfile(ffmpeg):
                return
            root = Path(job.paths["root"])
            root.mkdir(parents=True, exist_ok=True)
            dst = root / "poster.webp"
            if dst.is_file():
                return
            import subprocess
            subprocess.run(
                [ffmpeg, "-y", "-i", str(source), "-frames:v", "1",
                 "-vf", "scale=320:-2", "-f", "webp", str(dst)],
                capture_output=True, timeout=30, check=False,
            )
        except Exception:  # noqa: BLE001 - thumbnail failure must not block import
            pass

    @staticmethod
    def _import_meta(metadata: dict[str, Any], source: Path) -> str:
        width = int(metadata.get("width", 0) or 0)
        height = int(metadata.get("height", 0) or 0)
        duration = _duration_label(float(metadata.get("duration", 0.0) or 0.0))
        codec = str(metadata.get("video_codec", "unknown") or "unknown")
        size_bytes = int(metadata.get("size_bytes", 0) or 0)
        size_mb = f"{size_bytes / (1024 * 1024):.1f} MB" if size_bytes else "size unknown"
        dimensions = f"{width}x{height}" if width and height else "video"
        return f"{dimensions} - {duration} - {codec} - {size_mb}"

    @staticmethod
    def _preset(value: Any) -> str:
        normalized = str(value or "balanced").strip().lower()
        aliases = {"low": "conservative", "high": "detailed"}
        normalized = aliases.get(normalized, normalized)
        return normalized if normalized in {"conservative", "balanced", "detailed"} else "balanced"

    @staticmethod
    def _product_mode(value: Any) -> str:
        return {
            "study": "study_pack",
            "transcript": "transcript_only",
            "slides": "slides_only",
        }.get(str(value or "study").strip().lower(), "study_pack")

    def _import_video(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        path_text = str(payload.get("path") or "")
        if payload.get("bundled_demo"):
            # D-2: the demo flows through the normal import path using the
            # bundled demo video. There is no separate fake demo pipeline.
            source = self._resolve_demo_video()
            if source is None:
                raise FileNotFoundError("bundled demo video not found")
        else:
            source = Path(path_text).expanduser().resolve() if path_text else self.demo_video
        if source is None or not source.is_file():
            raise FileNotFoundError(f"video not found: {source or path_text}")
        if payload.get("bundled_demo"):
            source = self._copy_demo_if_needed(source)
        if self.controller is None:
            raise RuntimeError(self._engine_error or "engine is not loaded")
        metadata = self.controller.ffmpeg_wrapper.inspect_video(str(source))
        job = self.Job(str(self.data_dir), video_path=str(source))
        job.manifest["title"] = str(payload.get("title") or source.stem or "Lecture")
        job.source.update(metadata)
        job.settings["preset"] = self._preset(payload.get("preset"))
        job.settings.setdefault("whisper", {})["engine"] = "cpu"
        model = self.config.get("whisper_model", "")
        if model and os.path.isfile(model):
            job.settings["whisper"]["model"] = model
        job.settings["whisper"]["transcription_backend"] = "local-whispercpp"
        job.save()
        # PC polish: generate the job-card thumbnail immediately at import so
        # the card shows a real video frame before processing starts. A failure
        # must never prevent the import.
        self._generate_poster(job, source)
        self._activate_job(job, emit_payloads=True)
        self._emit({
            "event": "onboarding",
            "job": job.job_id,
            "name": source.name,
            "meta": self._import_meta(metadata, source),
        })
        self._respond(
            request_id,
            command,
            job=self._summary(job),
            job_id=job.job_id,
            source=metadata,
        )

    def _activate_job(self, job: Any, *, emit_payloads: bool) -> None:
        self.current_job = job
        self.current_stage = ""
        self.stage_percent = {}
        if self.controller is not None:
            self.controller.set_job(job)
        self._emit({
            "event": "active_job",
            "id": job.job_id,
            "title": job.manifest.get("title", "Lecture"),
        })
        if emit_payloads:
            self._emit_job_payloads()

    def _job_for(self, payload: dict[str, Any]) -> Any:
        job_id = str(payload.get("job_id") or "")
        if job_id and self.current_job is not None and self.current_job.job_id == job_id:
            return self.current_job
        if job_id:
            for job in self._job_objects():
                if job.job_id == job_id:
                    self._activate_job(job, emit_payloads=False)
                    return job
            raise FileNotFoundError(f"job not found: {job_id}")
        if self.current_job is not None:
            return self.current_job
        jobs = self._job_objects()
        if jobs:
            self._activate_job(jobs[0], emit_payloads=False)
            return jobs[0]
        raise RuntimeError("no job is loaded")

    def _start_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        if self.controller is None:
            raise RuntimeError(self._engine_error or "engine is not loaded")
        job = self._job_for(payload)
        if self.current_stage:
            self._respond(request_id, command, job_id=job.job_id, already_running=True)
            return
        if payload.get("mode"):
            job.settings["product_mode"] = self._product_mode(payload.get("mode"))
        if payload.get("preset"):
            job.settings["preset"] = self._preset(payload.get("preset"))
        job.settings.setdefault("whisper", {})["engine"] = "cpu"
        job.settings["whisper"]["transcription_backend"] = "local-whispercpp"
        model = self.config.get("whisper_model", "")
        if model and os.path.isfile(model):
            job.settings["whisper"]["model"] = model
        job.save()
        self.auto_export = bool(payload.get("auto_export", True))
        self.current_stage = "Queued"
        self._emit_job_payloads()
        self.controller.run_pipeline()
        self._respond(request_id, command, job_id=job.job_id, started=True)

    def _cancel_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        if self.controller is not None:
            self.controller.cancel()
        self.current_stage = ""
        self._emit({"event": "job_cancelled", "job_id": job.job_id})
        self._emit_status("Cancelled", job=job, detail="Processing cancelled")
        self._emit_job_payloads()
        self._promote_next()
        self._respond(request_id, command, job_id=job.job_id, cancelled=True)

    def _get_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        self._activate_job(job, emit_payloads=True)
        self._respond(
            request_id,
            command,
            job=self._summary(job),
            manifest=job.manifest,
            source=job.source,
            state=job.state,
            exports=self._export_files(job),
            job_dir=str(job.paths["root"]),
            export_dir=str(job.paths["exports"]),
        )

    def _get_slides(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        slides = self._slides(job)
        self._emit({"event": "slides_changed", "job": job.job_id, **self._slide_payload(job, slides)})
        self._respond(request_id, command, job_id=job.job_id, slides=slides)

    def _get_transcript(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        transcript = self._transcript(job)
        self._emit({"event": "transcript_changed", "job": job.job_id, **transcript})
        self._respond(request_id, command, job_id=job.job_id, transcript=transcript.get("transcript", {}))

    def _set_slide_state(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        try:
            index = int(payload.get("index"))
        except (TypeError, ValueError):
            raise ValueError("slide index must be an integer") from None
        state = str(payload.get("state") or "").strip().lower()
        if state not in {"accepted", "rejected"}:
            raise ValueError("slide state must be accepted or rejected")
        path = os.path.join(job.paths["root"], "candidates.json")
        candidates = self.FileManager.read_json_safe(path, []) or []
        if index < 0 or index >= len(candidates):
            raise IndexError(f"slide index out of range: {index}")
        candidates[index]["decision"] = state
        self.FileManager.write_json_atomic(path, candidates)
        slides = self._slides(job)
        self._emit({"event": "slides_changed", "job": job.job_id, **self._slide_payload(job, slides)})
        self._respond(request_id, command, job_id=job.job_id, index=index, state=state, applied=True)

    def _save_corrections(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        texts = payload.get("texts", [])
        if isinstance(texts, str):
            try:
                texts = json.loads(texts)
            except json.JSONDecodeError:
                texts = []
        if not isinstance(texts, list):
            raise ValueError("transcript corrections must be an array")
        segments = self.transcript_store.load_working(job.paths)
        changed = 0
        for segment, value in zip(segments, texts):
            text = str(value)
            if segment.get("text", "") != text:
                segment["text"] = text
                segment["edited"] = True
                changed += 1
        self.transcript_store.save_working(job.paths, segments)
        transcript = self._transcript(job)
        self._emit({"event": "transcript_changed", "job": job.job_id, **transcript})
        self._respond(request_id, command, job_id=job.job_id, saved=True, changed=changed)

    def _export(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        if self.controller is None:
            raise RuntimeError(self._engine_error or "engine is not loaded")
        job = self._job_for(payload)
        if self.current_stage:
            self._respond(request_id, command, job_id=job.job_id, already_running=True)
            return
        self.current_stage = "Export"
        self.auto_export = False
        self.controller.export_now()
        self._respond(request_id, command, job_id=job.job_id, started=True)

    def _ollama_settings(self) -> dict:
        return dict(self.config.get("ollama", {}) or {}) if hasattr(self, "config") else {}

    def _settings_payload(self) -> dict:
        o = self._ollama_settings()
        return {
            "version": getattr(self, "app_version", "0.0.0"),
            "model_path": self.config.get("whisper_model", "") if hasattr(self, "config") else "",
            "endpoint": o.get("base_url") or "http://localhost:11434",
            "engine": self.config.get("engine", "auto") if hasattr(self, "config") else "auto",
            "ollama_model": o.get("model", ""),
            "transcription_backend": self.config.get("transcription_backend", "local-whispercpp")
                if hasattr(self, "config") else "local-whispercpp",
            "slide_detection_preset": self._preset(self.config.get("slide_detection_preset", "balanced"))
                if hasattr(self, "config") else "balanced",
            "export_dir": str(self.data_dir),
        }

    def _get_settings(self, request_id: str | None, command: str) -> None:
        payload = self._settings_payload()
        self._emit({"event": "settings_changed", "job": "", **payload})
        self._respond(request_id, command, settings=payload)

    def _set_setting(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        key = str(payload.get("key") or "").strip()
        value = payload.get("value")
        job = self.current_job
        if job is None and key in {"slide_detection_preset", "engine", "transcription_backend"}:
            jobs = self._job_objects()
            if jobs:
                self._activate_job(jobs[0], emit_payloads=False)
                job = self.current_job

        applied = True
        normalized = value
        if key == "slide_detection_preset":
            normalized = self._preset(value)
            if job is not None:
                job.settings["preset"] = normalized
            if hasattr(self, "config"):
                self.config.set("slide_detection_preset", normalized)
        elif key == "engine":
            normalized = str(value or "auto").strip().lower()
            if normalized not in {"auto", "cpu", "vulkan", "cuda"}:
                normalized = "auto"
            if hasattr(self, "config"):
                self.config.set("engine", normalized)
            if job is not None:
                job.settings.setdefault("whisper", {})["engine"] = normalized
        elif key == "transcription_backend":
            normalized = str(value or "local-whispercpp").strip()
            if normalized not in {"local-whispercpp", "groq-fast", "groq-accurate"}:
                applied = False
                normalized = "local-whispercpp"
            if hasattr(self, "config"):
                self.config.set("transcription_backend", normalized)
            if job is not None:
                job.settings.setdefault("whisper", {})["transcription_backend"] = normalized
        elif key == "whisper_model":
            normalized = str(value or "").strip()
            if normalized:
                if hasattr(self, "config"):
                    self.config.set("whisper_model", normalized)
                if job is not None:
                    job.settings.setdefault("whisper", {})["model"] = normalized
            else:
                applied = False
        elif key == "ollama_base_url":
            normalized = str(value or "").strip()
            o = dict(self._ollama_settings())
            o["base_url"] = normalized
            if hasattr(self, "config"):
                self.config.set("ollama", o)
        elif key == "ollama_model":
            normalized = str(value or "").strip()
            o = dict(self._ollama_settings())
            o["model"] = normalized
            if hasattr(self, "config"):
                self.config.set("ollama", o)
        else:
            # Unknown settings are acknowledged without persistence so the UI
            # never sees a storm of unsupported-command errors.
            applied = False

        if job is not None and key in {"slide_detection_preset", "engine", "transcription_backend",
                                       "whisper_model"}:
            job.save()
        self._emit({
            "event": "settings_changed",
            "job": job.job_id if job is not None else "",
            "key": key,
            "value": normalized,
            "applied": applied,
        })
        self._respond(request_id, command, key=key, value=normalized, applied=applied)

    # ------------------------------------------------------------------ #
    # Phase 9: job management and queue
    # ------------------------------------------------------------------ #
    def _delete_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        result = self.electron_backend.delete_job(str(self.data_dir), job_id)
        self._emit({"event": "job_deleted", **result})
        if result.get("ok"):
            if self.current_job is not None and self.current_job.job_id == job_id:
                self.current_job = None
                self.current_stage = ""
                self._emit({"event": "active_job", "id": "", "title": ""})
            self._emit_job_payloads()
        self._respond(request_id, command, **result)

    def _delete_jobs(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        ids = payload.get("ids", [])
        if isinstance(ids, str):
            try:
                ids = json.loads(ids)
            except json.JSONDecodeError:
                ids = []
        result = self.electron_backend.delete_jobs(str(self.data_dir), ids)
        self._emit({"event": "job_deleted", **result})
        if result.get("ok"):
            self._emit_job_payloads()
        self._respond(request_id, command, **result)

    def _enqueue_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        job = self._job_for(payload)
        position = self.electron_backend.enqueue_job(self.queue, job_id)
        self._emit({"event": "job_queued", "job_id": job_id, "position": position})
        self._push_queue()
        self._emit_job_payloads()
        self._respond(request_id, command, job_id=job_id, position=position, ok=position >= 0)

    def _reorder_queue(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        try:
            index = int(payload.get("index", 0))
        except (TypeError, ValueError):
            index = 0
        ok = self.electron_backend.reorder_queue(self.queue, job_id, index)
        self._push_queue()
        self._respond(request_id, command, job_id=job_id, index=index, ok=ok)

    def _run_now(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        ok = self.electron_backend.run_now(self.queue, job_id)
        self._push_queue()
        self._respond(request_id, command, job_id=job_id, ok=ok)

    def _remove_from_queue(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        ok = self.electron_backend.remove_from_queue(self.queue, job_id)
        self._push_queue()
        self._emit_job_payloads()
        self._respond(request_id, command, job_id=job_id, ok=ok)

    def _schedule_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        self.electron_backend.schedule_job(
            self.queue, job_id,
            str(payload.get("when") or ""),
            str(payload.get("tz") or "local"),
            str(payload.get("missed_policy") or "run_when_opened"),
        )
        self._push_queue()
        self._emit_job_payloads()
        self._respond(request_id, command, job_id=job_id, ok=True)

    def _unschedule_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        ok = self.electron_backend.unschedule_job(self.queue, job_id)
        self._push_queue()
        self._respond(request_id, command, job_id=job_id, ok=ok)

    def _pause_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        paused = self.electron_backend.pause_job(self.controller)
        self._emit({"event": "pause_state", "state": "paused" if paused else "requested",
                    "job": job.job_id})
        self._emit_job_payloads()
        self._respond(request_id, command, job_id=job.job_id, paused=paused)

    def _resume_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        self._activate_job(job, emit_payloads=False)
        self.electron_backend.resume_job(job, self.controller)
        self.current_stage = "Queued"
        self._emit_job_payloads()
        self._respond(request_id, command, job_id=job.job_id, started=True)

    def _restart_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        self.electron_backend.restart_job(job)
        job.save()
        self._activate_job(job, emit_payloads=False)
        self.auto_export = True
        self.current_stage = "Queued"
        self._emit_job_payloads()
        self.controller.run_pipeline()
        self._respond(request_id, command, job_id=job.job_id, started=True)

    def _retry_stage(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self._job_for(payload)
        stage = str(payload.get("stage") or "")
        self._activate_job(job, emit_payloads=False)
        self.electron_backend.retry_stage(job, self.controller, stage)
        self.current_stage = stage
        self._emit_job_payloads()
        self._respond(request_id, command, job_id=job.job_id, stage=stage, started=True)

    def _set_job_group(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        group = str(payload.get("group") or "")
        ok = self.electron_backend.set_job_group(str(self.data_dir), job_id, group)
        if ok and self.current_job is not None and self.current_job.job_id == job_id:
            self.current_job.manifest["group"] = group
        self._emit_job_payloads()
        self._respond(request_id, command, job_id=job_id, group=group, ok=ok)

    def _set_jobs_group(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        ids = payload.get("ids", [])
        if isinstance(ids, str):
            try:
                ids = json.loads(ids)
            except json.JSONDecodeError:
                ids = []
        group = str(payload.get("group") or "")
        count = self.electron_backend.set_jobs_group(str(self.data_dir), ids, group)
        self._emit_job_payloads()
        self._respond(request_id, command, count=count, group=group, ok=count > 0)

    def _rename_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id") or "")
        title = str(payload.get("title") or "")
        result = self.electron_backend.rename_job(str(self.data_dir), job_id, title)
        if self.current_job is not None and self.current_job.job_id == job_id:
            self.current_job.manifest["title"] = result["title"]
            self._emit({"event": "active_job", "id": job_id, "title": result["title"]})
        self._emit_job_payloads()
        self._respond(request_id, command, **result)

    # ------------------------------------------------------------------ #
    # Phase 9: runtime, GPU, diagnostics, repair, storage
    # ------------------------------------------------------------------ #
    def _run_diagnostics(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        from lecturepack.services.job_ops import build_diagnostics
        job_id = str(payload.get("job_id") or "")
        job = None
        if job_id:
            try:
                job = self._job_for({"job_id": job_id})
            except Exception:
                job = None
        job = job or self.current_job
        state = job.state if job is not None else {}
        stages = state.get("stages", {}) if isinstance(state, dict) else {}
        failed = next((n for n, sd in stages.items()
                       if sd.get("status") in ("failed", "interrupted")), "")
        err = stages.get(failed, {}).get("error", "") if failed else ""
        diag = build_diagnostics(
            app_version="0.0.0",
            job_id=job_id,
            stage=failed,
            status=state.get("lifecycle", state.get("overall_status", "")) if isinstance(state, dict) else "",
            error=err,
            exit_code=None,
            timestamp=state.get("last_updated", "") if isinstance(state, dict) else "",
            runtime_paths={
                "whisper_exe": self.config.get("whisper_exe", "") if hasattr(self, "config") else "",
                "ffmpeg": getattr(getattr(self.controller, "ffmpeg_wrapper", None), "ffmpeg_path", ""),
                "data_dir": str(self.data_dir),
            })
        self._emit({"event": "diagnostics", "bundle": diag, "job_id": job_id})
        self._respond(request_id, command, ok=True, job_id=job_id)

    def _validate_vulkan(self, request_id: str | None, command: str) -> None:
        try:
            from lecturepack.infrastructure.transcription_engines import (
                EngineRegistry, ENGINE_VULKAN)
            reg = EngineRegistry(self.config)
            vk = reg.detect_engines().get(ENGINE_VULKAN)
            requested = self.config.get("engine", "auto")
            resolved = reg.resolve(requested)
            avail = bool(vk and vk.available)
            selected = resolved.key == ENGINE_VULKAN
            if not avail:
                state = "unavailable"
                msg = f"Vulkan unavailable — {(vk.reason if vk else 'not detected')}"
            elif selected:
                state = "loaded"
                msg = f"Vulkan available and selected — will load {resolved.backend}"
            else:
                state = "available"
                msg = f"Vulkan available but not selected — currently using {resolved.backend}"
            payload = {
                "state": state, "message": msg, "available": avail,
                "selected": selected, "reason": (vk.reason if vk else ""),
                "requested": requested, "resolved_backend": resolved.backend,
                "resolved_label": resolved.label,
                "benchmark_ok": bool(self.config.get("vulkan_benchmark_ok", False)),
                "exe": (vk.exe_path if vk else "")}
        except Exception as exc:  # noqa: BLE001 - defensive
            payload = {"state": "error", "message": f"Vulkan check failed: {exc}",
                       "available": False, "selected": False}
        self._emit({"event": "vulkan_status", **payload})
        self._respond(request_id, command, ok=True, **payload)

    def _validate_cuda(self, request_id: str | None, command: str) -> None:
        try:
            from lecturepack.infrastructure.transcription_engines import (
                EngineRegistry, ENGINE_CUDA)
            reg = EngineRegistry(self.config)
            cuda = reg.detect_engines().get(ENGINE_CUDA)
            requested = self.config.get("engine", "auto")
            resolved = reg.resolve(requested)
            avail = bool(cuda and cuda.available)
            selected = resolved.key == ENGINE_CUDA
            if not avail:
                state = "unavailable"
                msg = f"CUDA unavailable — {(cuda.reason if cuda else 'not detected')}"
            elif selected:
                state = "loaded"
                msg = f"CUDA available and selected — will load {resolved.backend}"
            else:
                state = "available"
                msg = f"CUDA available but not selected — currently using {resolved.backend}"
            payload = {
                "state": state, "message": msg, "available": avail,
                "selected": selected, "reason": (cuda.reason if cuda else ""),
                "requested": requested, "resolved_backend": resolved.backend,
                "resolved_label": resolved.label,
                "benchmark_ok": bool(self.config.get("cuda_benchmark_ok", False)),
                "exe": (cuda.exe_path if cuda else "")}
        except Exception as exc:  # noqa: BLE001 - defensive
            payload = {"state": "error", "message": f"CUDA check failed: {exc}",
                       "available": False, "selected": False}
        self._emit({"event": "cuda_status", **payload})
        self._respond(request_id, command, ok=True, **payload)

    def _nvidia_present(self) -> bool:
        try:
            from lecturepack.infrastructure.transcription_engines import nvidia_cuda_present
            return bool(nvidia_cuda_present())
        except Exception:
            return False

    def _cuda_pack_status(self, request_id: str | None, command: str) -> None:
        try:
            from app.desktop import cuda_pack
        except Exception:
            cuda_pack = None
        installed = bool(cuda_pack and cuda_pack.is_installed())
        size_label = cuda_pack.CUDA_PACK["size_label"] if cuda_pack else "unknown"
        payload = {"state": "installed" if installed else "idle",
                   "gpu_present": self._nvidia_present(),
                   "installed": installed, "size_label": size_label}
        self._emit({"event": "cuda_pack", **payload})
        self._respond(request_id, command, ok=True, **payload)

    def _cancel_cuda_pack(self, request_id: str | None, command: str) -> None:
        ev = getattr(self, "_cuda_pack_cancel", None)
        if ev is not None:
            ev.set()
        self._respond(request_id, command, ok=True, cancelled=ev is not None)

    def _install_cuda_pack(self, request_id: str | None, command: str) -> None:
        try:
            from app.desktop import cuda_pack
        except Exception as exc:
            self._emit({"event": "cuda_pack", "state": "error",
                        "message": f"CUDA pack unavailable: {exc}"})
            self._respond(request_id, command, ok=False, started=False)
            return
        cancel = threading.Event()
        self._cuda_pack_cancel = cancel
        pack = cuda_pack.CUDA_PACK

        def emit(state, message="", pct=None, **extra):
            payload = {"state": state, "message": message, "percent": pct,
                       "gpu_present": self._nvidia_present(),
                       "installed": cuda_pack.is_installed(),
                       "size_label": pack["size_label"]}
            payload.update(extra)
            self._emit({"event": "cuda_pack", **payload})

        def _rm(p):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

        def worker():
            if not self._nvidia_present():
                emit("error", "No NVIDIA CUDA GPU/driver detected on this computer.")
                return
            import tempfile
            base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            cache = os.path.join(base, "LecturePack", "Updates")
            os.makedirs(cache, exist_ok=True)
            partial = os.path.join(cache, pack["name"] + ".partial")
            final_zip = os.path.join(cache, pack["name"])
            _rm(partial)
            last = {"p": -5.0}

            def prog(pct, read, total):
                if cancel.is_set():
                    return
                if pct - last["p"] >= 1.0 or pct >= 100:
                    last["p"] = pct
                    emit("downloading", f"Downloading CUDA acceleration ({pack['size_label']})…",
                         round(pct, 1))

            emit("downloading", f"Downloading CUDA acceleration ({pack['size_label']})…", 0.0)
            try:
                cuda_pack.download(pack["url"], partial, on_progress=prog, cancel=cancel.is_set)
            except RuntimeError as exc:
                _rm(partial)
                emit("cancelled", "Download cancelled.") if str(exc) == "__cancelled__"                     else emit("error", f"Download failed: {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                _rm(partial)
                emit("error", f"Download failed: {exc}")
                return
            emit("verifying", "Verifying download…")
            if not cuda_pack.verify(partial):
                _rm(partial)
                emit("error", "Checksum mismatch — download rejected.")
                return
            os.replace(partial, final_zip)
            emit("installing", "Installing CUDA files…")
            try:
                n = cuda_pack.extract_pack(final_zip, cuda_pack.bin_cuda_dir())
            except Exception as exc:  # noqa: BLE001
                _rm(final_zip)
                emit("error", f"Install failed: {exc}")
                return
            _rm(final_zip)
            if not cuda_pack.is_installed():
                emit("error", "Install completed but whisper-cli.exe is missing.")
                return
            self._validate_cuda(None, "install_cuda_pack")
            emit("ready", f"CUDA acceleration installed ({n} files). "
                          "Pick NVIDIA CUDA under Compute engine.")

        threading.Thread(target=worker, daemon=True, name="lp-cuda-pack").start()
        self._respond(request_id, command, ok=True, started=True)

    def _push_storage(self) -> None:
        """Emit storage_changed with the data-dir usage."""
        try:
            used = 0
            for dirpath, _dirnames, filenames in os.walk(str(self.data_dir)):
                for fn in filenames:
                    try:
                        used += os.path.getsize(os.path.join(dirpath, fn))
                    except OSError:
                        pass
            free = shutil.disk_usage(str(self.data_dir)).free
            denom = used + free
            pct = (used / denom * 100.0) if denom else 0.0
            self._emit({
                "event": "storage_changed",
                "total": used + free,
                "used": used,
                "free": free,
                "percent": round(pct, 2),
            })
            if pct >= 90.0:
                self._emit({
                    "event": "storage_warning",
                    "total": used + free,
                    "used": used,
                    "free": free,
                    "percent": round(pct, 2),
                    "message": "LecturePack data is using 90%+ of its available space.",
                })
        except Exception:
            pass

    def _load_notification_prefs(self) -> dict:
        raw = self.config.get("notifications", None) if hasattr(self, "config") else None
        return dict(raw) if isinstance(raw, dict) else {}

    def _get_notification_prefs(self, request_id: str | None, command: str) -> None:
        prefs = self._load_notification_prefs()
        self._emit({"event": "notification_prefs", "prefs": prefs})
        self._respond(request_id, command, ok=True, prefs=prefs)

    def _set_notification_prefs(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        prefs = payload.get("prefs")
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except json.JSONDecodeError:
                prefs = {}
        if not isinstance(prefs, dict):
            prefs = {}
        self.config.set("notifications", prefs)
        self._emit({"event": "notification_prefs", "prefs": prefs})
        self._respond(request_id, command, ok=True, prefs=prefs)

    def _test_notification(self, request_id: str | None, command: str) -> None:
        # The sidecar has no native notification surface; report success so the
        # UI never sees an error. Luna owns the actual OS notification.
        self._respond(request_id, command, ok=True, sent=True)

    def _repair_selection(self, request_id: str | None, command: str) -> None:
        job = self.current_job
        if job is None:
            self._respond(request_id, command, ok=False, job_id="", started=False)
            return
        # Context repair is a Qt-dialog feature in the desktop app. The sidecar
        # reports the job is loaded; Luna owns the repair UI. The engine's
        # deterministic repair runs on the transcript workspace.
        self._emit({"event": "repair_required", "operation_id": "context_repair",
                    "detail": "Context repair is available for the selected segments."})
        self._respond(request_id, command, ok=True, job_id=job.job_id, started=True)

    # ------------------------------------------------------------------ #
    # Phase 9: study and AI backends
    # ------------------------------------------------------------------ #
    def _ollama_base(self) -> str:
        return self._ollama_settings().get("base_url") or "http://localhost:11434"

    def _groq_store(self):
        from lecturepack.infrastructure.secret_store import WindowsCredentialStore
        return WindowsCredentialStore()

    def _emit_groq_status(self, message: str = "", testing: bool = False) -> None:
        has = False
        try:
            has = self._groq_store().has_secret()
        except Exception:
            has = False
        self._emit({
            "event": "groq_status",
            "has_key": bool(has),
            "testing": bool(testing),
            "backend": self.config.get("transcription_backend", "local-whispercpp")
                if hasattr(self, "config") else "local-whispercpp",
            "message": message or ("API key stored." if has else "No API key stored."),
        })

    def _set_groq_key(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        key = str(payload.get("key") or "")
        try:
            self._groq_store().set(key)
            self._emit_groq_status("API key saved to Windows Credential Manager.")
            self._respond(request_id, command, ok=True, stored=True)
        except Exception as exc:
            self._emit_groq_status(f"Could not save key: {exc}")
            self._respond(request_id, command, ok=False, stored=False)

    def _remove_groq_key(self, request_id: str | None, command: str) -> None:
        try:
            self._groq_store().remove()
            self._emit_groq_status("API key removed.")
            self._respond(request_id, command, ok=True, removed=True)
        except Exception as exc:
            self._emit_groq_status(f"Could not remove key: {exc}")
            self._respond(request_id, command, ok=False, removed=False)

    def _test_groq_key(self, request_id: str | None, command: str) -> None:
        self._emit_groq_status("Testing Groq credentials…", testing=True)

        def work():
            try:
                from lecturepack.services.groq_transcription import GroqHttpClient
                key = self._groq_store().get()
                if not key:
                    self._emit_groq_status("No API key stored — set one first.")
                    return
                ok = GroqHttpClient().test_key(key)
                self._emit_groq_status(
                    "Groq credential test passed — account limits and billing still apply."
                    if ok else "Groq credential test failed — check the key.")
            except Exception as exc:
                self._emit_groq_status(f"Groq test failed: {exc}")

        threading.Thread(target=work, daemon=True, name="lp-groq-test").start()
        self._respond(request_id, command, ok=True)

    def _list_ollama_models(self, request_id: str | None, command: str) -> None:
        base = self._ollama_base()
        selected = self._ollama_settings().get("model", "")

        def worker():
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                models = OllamaClient(base).list_models()
                self._emit({"event": "ollama_models", "models": models,
                            "selected": selected, "available": True})
            except Exception as exc:
                self._emit({"event": "ollama_models", "models": [], "selected": selected,
                            "available": False, "error": str(exc)})

        threading.Thread(target=worker, daemon=True, name="lp-ollama-models").start()
        self._respond(request_id, command, ok=True)

    def _smart_study_status(self, request_id: str | None, command: str) -> None:
        base = self._ollama_base()

        def worker():
            ollama = {"available": False}
            installed = []
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                c = OllamaClient(base)
                ollama = c.is_available()
                if ollama.get("available"):
                    installed = [m["name"] for m in c.list_models()]
            except Exception as exc:
                ollama = {"available": False, "error": str(exc)}
            self._emit({"event": "smart_study",
                        **self.electron_study.smart_study_payload(
                            self.config, ollama=ollama, installed=installed)})

        threading.Thread(target=worker, daemon=True, name="lp-smart-study").start()
        self._respond(request_id, command, ok=True)

    def _set_study_preset(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        preset = str(payload.get("preset") or "")
        o = dict(self._ollama_settings())
        if preset in (self.study_presets.PRESET_LIGHTWEIGHT, self.study_presets.PRESET_BALANCED):
            o["model"] = self.study_presets.model_for_preset(preset)
            o["enabled"] = True
            self.config.set("study_preset", preset)
        else:
            self.config.set("study_preset", self.study_presets.PRESET_CUSTOM)
        self.config.set("ollama", o)
        self._emit({"event": "settings_changed", "job": "", **self._settings_payload()})
        self._respond(request_id, command, ok=True, preset=preset,
                      model=o.get("model", ""))

    def _cancel_smart_study(self, request_id: str | None, command: str) -> None:
        ev = getattr(self, "_smart_study_cancel", None)
        if ev is not None:
            ev.set()
        self._respond(request_id, command, ok=True, cancelled=ev is not None)

    def _launch_ollama_installer(self, request_id: str | None, command: str) -> None:
        import webbrowser
        try:
            webbrowser.open(self.study_presets.OLLAMA_DOWNLOAD_URL)
        except Exception:
            pass
        self._respond(request_id, command, ok=True)

    def _install_smart_study(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        preset = str(payload.get("preset") or "")
        if preset not in (self.study_presets.PRESET_LIGHTWEIGHT, self.study_presets.PRESET_BALANCED):
            preset = self.study_presets.PRESET_BALANCED
        label = self.study_presets.STUDY_PRESETS[preset]["label"]
        model = self.study_presets.model_for_preset(preset)
        cancel = threading.Event()
        self._smart_study_cancel = cancel
        base = self._ollama_base()

        def emit(state: str, message: str = "", pct: float | None = None, **extra: Any) -> None:
            payload_out = self.electron_study.smart_study_payload(
                self.config, state=state, message=message, pct=pct)
            payload_out.update(extra)
            payload_out["preset"] = preset
            self._emit({"event": "smart_study", **payload_out})

        def worker():
            from lecturepack.infrastructure.ollama_client import (
                OllamaClient, OllamaError, OllamaCancelled)
            c = OllamaClient(base)
            if not c.is_available().get("available"):
                emit("need_engine",
                     "Local AI Engine (Ollama) isn't installed or running. "
                     "Install it to enable Smart Study.")
                return
            try:
                installed = [m["name"] for m in c.list_models()]
            except Exception:
                installed = []
            if model not in installed:
                emit("downloading", f"Downloading {label}…", 0.0)
                last = {"pct": -5.0}

                def on_prog(p):
                    if cancel.is_set():
                        return
                    pct = p.get("percent")
                    if pct is None or pct - last["pct"] >= 1.0 or pct >= 100:
                        last["pct"] = pct if pct is not None else last["pct"]
                        emit("downloading", f"Downloading {label}…",
                             round(pct, 1) if pct is not None else None,
                             status=p.get("status", ""))

                try:
                    c.pull_model(model, on_progress=on_prog, cancel_event=cancel)
                except OllamaCancelled:
                    emit("cancelled", "Smart Study setup cancelled.")
                    return
                except OllamaError as exc:
                    emit("error", f"Download failed: {exc}")
                    return
            emit("testing", f"Testing {label}…")
            try:
                res = c.chat_structured(
                    model, "Reply with compact JSON only.", 'Return {"ok": true}.',
                    {"type": "object", "properties": {"ok": {"type": "boolean"}},
                     "required": ["ok"]},
                    num_predict=32, keep_alive="5m", cancel_event=cancel, timeout=90.0)
                json.loads(res.get("content", "") or "{}")
            except OllamaCancelled:
                emit("cancelled", "Smart Study setup cancelled.")
                return
            except Exception as exc:
                emit("error", f"The model downloaded but the test request failed: {exc}")
                return
            o = dict(self._ollama_settings())
            o["model"] = model
            o["enabled"] = True
            self.config.set("ollama", o)
            self.config.set("study_preset", preset)
            self.config.set("smart_study_ready", True)
            self._emit({"event": "settings_changed", "job": "", **self._settings_payload()})
            emit("ready", f"Smart Study ready — {label}.")

        threading.Thread(target=worker, daemon=True, name="lp-smart-study-install").start()
        self._respond(request_id, command, ok=True, preset=preset)

    def _test_endpoint(self, request_id: str | None, command: str) -> None:
        base = self._ollama_base()
        model = self._ollama_settings().get("model", "")

        def worker():
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                probe = OllamaClient(base).is_available()
                if probe.get("available"):
                    self._emit({"event": "ai_status",
                                "label": self.study_presets.PROVIDER_LOCAL, "model": model})
                    self._respond(request_id, command, ok=True, available=True,
                                  label=self.study_presets.PROVIDER_LOCAL, model=model)
                else:
                    self._emit({"event": "ai_status",
                                "label": self.study_presets.PROVIDER_BUILTIN, "model": model})
                    self._respond(request_id, command, ok=True, available=False,
                                  label=self.study_presets.PROVIDER_BUILTIN, model=model)
            except Exception as exc:
                self._respond(request_id, command, ok=False, available=False,
                              error=str(exc)[:200])

        threading.Thread(target=worker, daemon=True, name="lp-endpoint-test").start()

    def _emit_study_changed(self) -> None:
        """Emit the study_changed overview payload for the current job."""
        job = self.current_job
        if job is None:
            return
        try:
            overview = self.study_service.build_overview(job)
        except Exception:
            overview = {}
        key_terms = overview.get("key_terms", []) or []
        try:
            cards = []
            for card in self.study_service.load_flashcards(job).get("cards") or []:
                term = card.get("term") or card.get("front") or ""
                definition = card.get("definition") or card.get("back") or ""
                if term or definition:
                    cards.append({"q": term, "a": definition})
            notes = self.study_service.load_study_data(job).get("notes", "") or ""
        except Exception:
            cards = []
            notes = ""
        self._emit({
            "event": "study_changed",
            "topics": [{"t": "00:00", "title": "Lecture", "active": True}],
            "topicBlocks": [{"left": 0.5, "width": 99, "active": True}],
            "topicLabels": ["Lecture"],
            "keyTerms": key_terms,
            "summary": overview.get("summary", "") or "",
            "summarySource": overview.get("summary_source", "") or "",
            "bookmarks": [],
            "stats": [
                ["Slides", str(overview.get("accepted_slide_count", 0))],
                ["Segments", str(overview.get("transcript_segment_count", 0))],
                ["Needs review", str(overview.get("needs_review_count", 0))],
            ],
            "cards": cards or [{"q": "No flashcards yet",
                                "a": "Generate flashcards from this lecture."}],
            "notes": notes,
        })

    def _ask_ai(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        prompt = str(payload.get("prompt") or "")
        job = self.current_job
        if job is None:
            self._emit({"event": "ai_token",
                        "text": "Open or process a lecture first, then ask away."})
            self._emit({"event": "ai_done"})
            self._respond(request_id, command, ok=True, job_id="")
            return
        segments = self.transcript_store.load_working(job.paths) or []
        o = self._ollama_settings()
        local_ready = bool(o.get("enabled") and o.get("model"))
        if not local_ready:
            answer = self.electron_study.builtin_answer(prompt, segments)
            self._emit({"event": "ai_token", "text": answer})
            self._emit({"event": "ai_done"})
            self._emit({"event": "ai_status",
                        "label": self.study_presets.PROVIDER_BUILTIN, "model": ""})
            try:
                self.study_service.append_chat_message(job, "user", prompt)
                self.study_service.append_chat_message(job, "assistant", answer)
            except Exception:
                pass
            self._respond(request_id, command, ok=True, job_id=job.job_id)
            return
        # Local AI path: use the existing StudyAssistantWorker (Qt thread).
        from lecturepack.services.study_assistant_service import StudyAssistantWorker
        transcript_text = StudyAssistantWorker.transcript_context(segments)
        self._emit({"event": "ai_status", "label": "Thinking…", "model": o.get("model")})
        worker = StudyAssistantWorker(
            "chat", transcript_text, o, history=[], question=prompt, count=5)
        self._ai_worker = worker

        def ok(task, result):
            answer = (result or {}).get("answer", "") if isinstance(result, dict) else ""
            answer = answer or "I couldn't find an answer in the transcript."
            self._emit({"event": "ai_token", "text": answer})
            self._emit({"event": "ai_done"})
            self._emit({"event": "ai_status",
                        "label": self.study_presets.PROVIDER_LOCAL, "model": o.get("model")})
            try:
                self.study_service.append_chat_message(job, "user", prompt)
                self.study_service.append_chat_message(job, "assistant", answer)
            except Exception:
                pass

        def fail(kind, message, details):
            self._emit({"event": "ai_token", "text": f"⚠ {message}"})
            self._emit({"event": "ai_done"})
            self._emit({"event": "ai_status", "label": "AI error", "model": o.get("model")})

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()
        self._respond(request_id, command, ok=True, job_id=job.job_id)

    def _generate_quiz(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self.current_job
        if job is None:
            self._emit({"event": "quiz_status", "state": "error",
                        "message": "Open or process a lecture first."})
            self._respond(request_id, command, ok=False, job_id="")
            return
        try:
            count = max(1, min(int(payload.get("count") or 5), 50))
        except (TypeError, ValueError):
            count = 5
        meta = {"count": count, "difficulty": payload.get("difficulty", "Mixed"),
                "type": payload.get("type", "multiple choice"),
                "scope": payload.get("scope", "entire lecture"),
                "source": payload.get("source", "transcript")}
        o = self._ollama_settings()
        self._emit({"event": "quiz_status", "state": "generating", "message": "Generating quiz…"})
        self._emit({"event": "study_progress", "job_id": job.job_id, "kind": "quiz",
                    "pct": 0, "message": "Generating quiz…"})

        def deliver(questions, provider, model=""):
            questions = self.electron_study.normalize_quiz(questions, count)
            if not questions:
                self._emit({"event": "quiz_status", "state": "error",
                            "message": "Couldn't build a quiz for this lecture."})
                return
            self._save_quiz(job, questions, meta, provider, model)
            self._emit({"event": "quiz_changed", "questions": questions,
                        "provider": provider, "model": model,
                        "meta": {**meta, "provider": provider, "model": model},
                        "session": None})
            self._emit({"event": "quiz_status", "state": "ready",
                        "message": f"{len(questions)} questions · {provider}"})

        segments = self.transcript_store.load_working(job.paths) or []

        def do_fallback():
            try:
                terms = self.study_service.build_overview(job).get("key_terms", []) or []
            except Exception:
                terms = []
            deliver(self.electron_study.generate_quiz_fallback(terms, count, segments),
                    self.study_presets.PROVIDER_BUILTIN)

        if not (o.get("enabled") and o.get("model")):
            do_fallback()
            self._respond(request_id, command, ok=True, job_id=job.job_id)
            return

        from lecturepack.services.study_assistant_service import StudyAssistantWorker
        transcript_text = StudyAssistantWorker.transcript_context(segments)
        worker = StudyAssistantWorker("quiz", transcript_text, o, count=count,
                                      difficulty=meta["difficulty"], qtype=meta["type"])
        self._quiz_worker = worker

        def ok(task, result):
            qs = (result or {}).get("questions") if isinstance(result, dict) else None
            if qs:
                deliver(qs, self.study_presets.PROVIDER_LOCAL, o.get("model", ""))
            else:
                do_fallback()

        def fail(kind, message, details):
            do_fallback()

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()
        self._respond(request_id, command, ok=True, job_id=job.job_id)

    def _save_quiz(self, job, questions, meta, provider, model, reset_session=True):
        data = self.study_service.load_study_data(job)
        prev = data.get("quiz") if isinstance(data.get("quiz"), dict) else {}
        data["quiz"] = {
            "questions": questions,
            "meta": {**meta, "provider": provider, "model": model},
            "session": {} if reset_session else (prev.get("session") or {}),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.study_service.save_study_data(job, data)

    def _cancel_quiz(self, request_id: str | None, command: str) -> None:
        w = getattr(self, "_quiz_worker", None)
        if w is not None:
            try:
                w.detach_and_stop()
            except Exception:
                pass
        self._emit({"event": "quiz_status", "state": "cancelled",
                    "message": "Generation cancelled."})
        self._respond(request_id, command, ok=True, cancelled=True)

    def _save_quiz_session(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self.current_job
        if job is None:
            self._respond(request_id, command, ok=False, job_id="")
            return
        session = payload.get("session")
        if isinstance(session, str):
            try:
                session = json.loads(session)
            except json.JSONDecodeError:
                session = None
        if not isinstance(session, dict):
            self._respond(request_id, command, ok=False, job_id=job.job_id)
            return
        data = self.study_service.load_study_data(job)
        q = data.get("quiz") if isinstance(data.get("quiz"), dict) else {}
        q["session"] = session
        data["quiz"] = q
        self.study_service.save_study_data(job, data)
        self._respond(request_id, command, ok=True, job_id=job.job_id, saved=True)

    def _generate_flashcards(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self.current_job
        if job is None:
            self._emit({"event": "flashcards_status", "state": "error",
                        "message": "Open or process a lecture first."})
            self._respond(request_id, command, ok=False, job_id="")
            return
        try:
            count = max(1, min(int(payload.get("count") or 10), 60))
        except (TypeError, ValueError):
            count = 10
        meta = {"count": count, "difficulty": payload.get("difficulty", "Basic"),
                "style": payload.get("style", "term → definition"),
                "scope": payload.get("scope", "entire lecture")}
        o = self._ollama_settings()
        self._emit({"event": "flashcards_status", "state": "generating",
                    "message": "Generating flashcards…"})
        self._emit({"event": "study_progress", "job_id": job.job_id, "kind": "flashcards",
                    "pct": 0, "message": "Generating flashcards…"})

        def deliver(cards, provider, model=""):
            cards = self.electron_study.normalize_flashcards(cards, count)
            if not cards:
                self._emit({"event": "flashcards_status", "state": "error",
                            "message": "Couldn't build flashcards for this lecture."})
                return
            self._save_flashcards(job, cards, meta, provider, model)
            self._emit({"event": "flashcards_changed", "cards": cards,
                        "provider": provider, "model": model,
                        "meta": {**meta, "provider": provider, "model": model},
                        "session": None})
            self._emit({"event": "flashcards_status", "state": "ready",
                        "message": f"{len(cards)} cards · {provider}"})

        segments = self.transcript_store.load_working(job.paths) or []

        def do_fallback():
            try:
                terms = self.study_service.build_overview(job).get("key_terms", []) or []
            except Exception:
                terms = []
            deliver(self.electron_study.generate_flashcards_fallback(terms, count, segments),
                    self.study_presets.PROVIDER_BUILTIN)

        if not (o.get("enabled") and o.get("model")):
            do_fallback()
            self._respond(request_id, command, ok=True, job_id=job.job_id)
            return

        from lecturepack.services.study_assistant_service import StudyAssistantWorker
        transcript_text = StudyAssistantWorker.transcript_context(segments)
        worker = StudyAssistantWorker("flashcards", transcript_text, o, count=count,
                                      difficulty=meta["difficulty"])
        self._flash_worker = worker

        def ok(task, result):
            cards = (result or {}).get("cards") if isinstance(result, dict) else None
            if cards:
                deliver(cards, self.study_presets.PROVIDER_LOCAL, o.get("model", ""))
            else:
                do_fallback()

        def fail(kind, message, details):
            do_fallback()

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()
        self._respond(request_id, command, ok=True, job_id=job.job_id)

    def _save_flashcards(self, job, cards, meta, provider, model):
        data = self.study_service.load_study_data(job)
        data["flashcards"] = {
            "cards": cards,
            "meta": {**meta, "provider": provider, "model": model},
            "session": {},
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.study_service.save_study_data(job, data)

    def _cancel_flashcards(self, request_id: str | None, command: str) -> None:
        w = getattr(self, "_flash_worker", None)
        if w is not None:
            try:
                w.detach_and_stop()
            except Exception:
                pass
        self._emit({"event": "flashcards_status", "state": "cancelled",
                    "message": "Generation cancelled."})
        self._respond(request_id, command, ok=True, cancelled=True)

    def _save_flashcard_session(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self.current_job
        if job is None:
            self._respond(request_id, command, ok=False, job_id="")
            return
        session = payload.get("session")
        if isinstance(session, str):
            try:
                session = json.loads(session)
            except json.JSONDecodeError:
                session = None
        if not isinstance(session, dict):
            self._respond(request_id, command, ok=False, job_id=job.job_id)
            return
        data = self.study_service.load_study_data(job)
        f = data.get("flashcards") if isinstance(data.get("flashcards"), dict) else {}
        f["session"] = session
        data["flashcards"] = f
        self.study_service.save_study_data(job, data)
        self._respond(request_id, command, ok=True, job_id=job.job_id, saved=True)

    def _save_notes(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job = self.current_job
        if job is None:
            self._respond(request_id, command, ok=False, job_id="")
            return
        data = self.study_service.load_study_data(job)
        data["notes"] = str(payload.get("text") or "")[:20000]
        self.study_service.save_study_data(job, data)
        self._respond(request_id, command, ok=True, job_id=job.job_id, saved=True)

    # ------------------------------------------------------------------ #
    # Phase 9: paste link / yt-dlp
    # ------------------------------------------------------------------ #
    def _media_link_support(self, request_id: str | None, command: str) -> None:
        available = self.media_fetch.is_available()
        version = self.media_fetch.version()
        self._emit({
            "event": "media_link_state",
            "available": available,
            "version": version,
        })
        self._respond(request_id, command, available=available, version=version)

    def _probe_media_url(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        url = str(payload.get("url") or "").strip()
        if not self.media_fetch.looks_like_url(url):
            self._emit({"event": "media_probe", "ok": False,
                        "error": "That doesn't look like a web link."})
            self._respond(request_id, command, ok=False,
                          error="That doesn't look like a web link.")
            return

        def worker():
            try:
                info = self.media_fetch.MediaFetcher().probe(url)
                info["ok"] = True
                payload_out = info
            except self.media_fetch.MediaFetchError as exc:
                payload_out = {"ok": False, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 - never kill the thread
                payload_out = {"ok": False, "error": str(exc)[:300]}
            self._emit({"event": "media_probe", **payload_out})

        threading.Thread(target=worker, daemon=True,
                         name="lp-media-probe").start()
        self._respond(request_id, command, ok=True)

    def _downloads_dir(self) -> str:
        d = self.data_dir / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _cancel_media_url(self, request_id: str | None, command: str) -> None:
        ev = getattr(self, "_media_cancel", None)
        if ev is not None:
            ev.set()
        self._respond(request_id, command, ok=True, cancelled=ev is not None)

    def _import_media_url(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        url = str(payload.get("url") or "").strip()
        title = str(payload.get("title") or "")
        if not self.media_fetch.looks_like_url(url):
            self._emit({"event": "media_done", "ok": False,
                        "error": "That doesn't look like a web link."})
            self._respond(request_id, command, ok=False,
                          error="That doesn't look like a web link.")
            return
        if getattr(self, "_media_busy", False):
            self._emit({"event": "media_done", "ok": False,
                        "error": "A link download is already running."})
            self._respond(request_id, command, ok=False,
                          error="A link download is already running.")
            return

        self._media_busy = True
        cancel = threading.Event()
        self._media_cancel = cancel
        dest = self._downloads_dir()

        def worker():
            try:
                path = self.media_fetch.MediaFetcher().download(
                    url, dest,
                    progress_cb=lambda p: self._emit({"event": "media_progress", **p}),
                    cancel_check=cancel.is_set,
                    title=title or None,
                )
                if cancel.is_set():
                    payload_out = {"ok": False, "cancelled": True}
                else:
                    payload_out = {"ok": True, "path": path,
                                   "name": os.path.basename(path)}
            except self.media_fetch.MediaFetchCancelled:
                payload_out = {"ok": False, "cancelled": True}
            except self.media_fetch.MediaFetchError as exc:
                payload_out = {"ok": False, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 - never kill the thread
                payload_out = {"ok": False, "error": str(exc)[:300]}
            finally:
                self._media_busy = False
                self._media_cancel = None
            self._emit({"event": "media_done", **payload_out})
            if payload_out.get("ok"):
                # Hand off on the main thread: import_video touches Qt + engine.
                QTimer.singleShot(0, lambda: self._import_video(None, "import_media_url",
                                                                {"path": payload_out["path"]}))

        threading.Thread(target=worker, daemon=True,
                         name="lp-media-download").start()
        self._respond(request_id, command, ok=True, started=True)

    def _processing_workers_running(self) -> bool:
        """Keep QThread/QProcess owners alive while a cancellation drains.

        ``JobController.cancel`` deliberately clears its active-stage set as
        soon as cancellation is requested, but Qt workers and QProcesses may
        still be delivering their final signals. Quitting QCoreApplication in
        that window can make PySide6 destroy a live worker and abort the
        sidecar. The host still owns the final timeout/tree-kill guard; this
        short drain avoids that race when the engine can finish normally.
        """
        controller = self.controller
        if controller is None:
            return False
        workers = [
            getattr(controller, "slide_worker", None),
            getattr(controller, "align_worker", None),
            getattr(controller, "export_worker", None),
        ]
        workers.extend(getattr(controller, "_retired_workers", []) or [])
        for worker in workers:
            try:
                if worker is not None and worker.isRunning():
                    return True
            except RuntimeError:
                continue

        wrappers = [
            getattr(controller, "ffmpeg_wrapper", None),
            getattr(controller, "whisper_wrapper", None),
            getattr(getattr(controller, "transcription_backend", None), "wrapper", None),
        ]
        for wrapper in wrappers:
            process = getattr(wrapper, "process", None)
            if process is None:
                continue
            try:
                if process.state() != QProcess.ProcessState.NotRunning:
                    return True
            except RuntimeError:
                continue
        return False

    def _finish_shutdown(self) -> None:
        if not self._shutting_down:
            return
        elapsed = time.monotonic() - self._shutdown_started_at
        if self._processing_workers_running() and elapsed < 8.0:
            return
        if self._shutdown_timer is not None:
            self._shutdown_timer.stop()
        self.app.quit()

    def _request_shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._shutdown_started_at = time.monotonic()
        if self.controller is not None:
            try:
                self.controller.cancel()
            except Exception:
                pass
        # The Electron parent owns the final process-tree cleanup. Stop the
        # protocol poller, then let cancelled QThreads/QProcesses deliver
        # their terminal signals before leaving the QtCore loop. The bounded
        # drain prevents QThread destruction races; the Electron host still
        # enforces its shorter process-tree timeout if a worker is stuck.
        if hasattr(self, "_poll_timer"):
            self._poll_timer.stop()
        if self._shutdown_timer is None:
            self._shutdown_timer = QTimer(self.app)
            self._shutdown_timer.setInterval(50)
            self._shutdown_timer.timeout.connect(self._finish_shutdown)
        self._shutdown_timer.start()
        self._finish_shutdown()

    # ------------------------------------------------------------------ #
    # Controller -> JSONL events
    # ------------------------------------------------------------------ #
    def _on_stage_started(self, stage: str) -> None:
        self.current_stage = str(stage)
        self.stage_percent[str(stage)] = 0
        self._emit_status("Processing", detail=f"{stage} - starting")
        self._emit_pipeline()

    def _on_stage_progress(self, stage: str, percent: int) -> None:
        stage = str(stage)
        self.current_stage = stage
        self.stage_percent[stage] = max(0, min(100, int(percent or 0)))
        if stage == "Export" and self.current_job is not None:
            progress = self.stage_percent[stage]
            self._emit({
                "event": "export_progress",
                "job": self.current_job.job_id,
                "pct": progress,
                "label": f"exporting - {progress}%",
            })
        self._emit_status("Processing", detail=f"{stage} - {self.stage_percent[stage]}%")
        self._emit_pipeline()

    def _on_stage_log(self, stage: str, text: str) -> None:
        if self.current_job is None:
            return
        normalized = str(text or "").replace("\r", "\n")
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        for line in lines:
            self._emit({
                "event": "log_line",
                "job": self.current_job.job_id,
                "tag": f"[{stage}]",
                "color": "var(--blue-ink)" if stage == "Detect Slides" else "var(--muted)",
                "text": line,
            })

    def _on_stage_finished(self, stage: str, success: bool, error: str) -> None:
        stage = str(stage)
        self.stage_percent[stage] = 100 if success else self.stage_percent.get(stage, 0)
        if self.current_job is not None and success and stage in {
            "Transcribe", "Detect Slides", "Review Ready", "Export"
        }:
            self._emit_job_payloads()
        if success and stage == "Export" and self.current_job is not None:
            self._emit({
                "event": "export_progress",
                "job": self.current_job.job_id,
                "pct": 100,
                "label": "Export complete",
            })
            self.current_stage = ""
            self.auto_export = False
            self._emit_job_payloads()
            self._emit_status("Done", detail="Study Pack export complete")
            self._emit({
                "event": "job_completed",
                "job_id": self.current_job.job_id,
                "slides_detected": len(self._slides(self.current_job)),
                "segment_count": self._transcript(self.current_job)["transcript"].get("segments", 0),
            })
        if not success:
            if stage == "Export":
                self.current_stage = ""
            self._emit({
                "event": "error",
                "job": self.current_job.job_id if self.current_job else "",
                "stage": stage,
                "error": str(error or f"{stage} failed"),
            })
            self._emit_status("Failed", detail=f"{stage} failed")
        self._emit_pipeline()

    def _on_stage_cached(self, stage: str) -> None:
        self._on_stage_log(str(stage), "Using the persisted completed stage.")

    def _on_backend_info(self, info: str) -> None:
        self.backend_label = str(info or "")
        self._emit_status("Processing", detail=f"{self.current_stage} - {self.backend_label}")

    def _on_transcript_segment(self, segment: dict) -> None:
        # Live transcript data is intentionally not treated as canonical. The
        # canonical raw/normalized files are read after the stage succeeds.
        if self.current_job is not None:
            self._emit({
                "event": "log_line",
                "job": self.current_job.job_id,
                "tag": "[Transcribe]",
                "color": "var(--orange-ink)",
                "text": str(segment.get("text", "")),
            })

    def _on_pipeline_completed(self) -> None:
        if self.current_job is None:
            return
        self.current_stage = "Review Ready"
        self._emit_job_payloads()
        self._emit_status("Review Ready", detail="Transcript and slides are ready")
        if self.auto_export and self.current_job.get_stage_status("Export") != "completed":
            QTimer.singleShot(0, self._start_automatic_export)
        else:
            self.current_stage = ""
            self._promote_next()

    def _start_automatic_export(self) -> None:
        if self.controller is None or self.current_job is None or self._shutting_down:
            return
        self.current_stage = "Export"
        self.controller.export_now()

    def _on_pipeline_failed(self, error: str) -> None:
        if self.current_job is not None:
            self.current_stage = ""
            self._emit({
                "event": "job_failed",
                "job_id": self.current_job.job_id,
                "stage": self._last_stage(self.current_job),
                "error": str(error or "Processing failed")[:500],
            })
            self._emit_status("Failed", detail=str(error or "Processing failed"))
            self._emit_job_payloads()
            self._promote_next()

    # ------------------------------------------------------------------ #
    # Payload builders
    # ------------------------------------------------------------------ #
    def _emit_status(self, label: str, *, job: Any | None = None, detail: str = "") -> None:
        job = job or self.current_job
        if job is None:
            return
        pct = self._job_percent(job)
        self._emit({
            "event": "status_changed",
            "job": job.job_id,
            "label": label,
            "pct": pct,
            "detail": detail,
            "right": self.backend_label or "Electron sidecar",
            "side": f"{label} - {pct}%" if label == "Processing" else label,
        })

    def _emit_pipeline(self) -> None:
        if self.current_job is None:
            return
        self._emit({
            "event": "pipeline_changed",
            "job": self.current_job.job_id,
            "title": self.current_job.manifest.get("title", "Lecture"),
            "meta": f"{self._summary(self.current_job)['meta']} - {self._job_percent(self.current_job)}%",
            "stages": self._pipeline_stages(self.current_job),
        })

    def _pipeline_stages(self, job: Any) -> list[dict[str, Any]]:
        active = self.current_stage
        stages = []
        for index, stage in enumerate(STAGES):
            status = job.get_stage_status(stage)
            if status == "completed":
                state = "done"
                percent = 100
            elif status == "failed":
                state = "error"
                percent = self.stage_percent.get(stage, 0)
            elif stage == active or status == "running":
                state = "active"
                percent = self.stage_percent.get(stage, 0)
            else:
                state = "pending"
                percent = 0
            stages.append({
                "label": stage,
                "state": state,
                "pct": percent,
                "color": "blue" if index % 2 else "orange",
            })
        return stages

    def _slides(self, job: Any) -> list[dict[str, Any]]:
        candidates = self.FileManager.read_json_safe(
            os.path.join(job.paths["root"], "candidates.json"), []) or []
        duration = float(job.source.get("duration", 0.0) or 0.0)
        slides = []
        for index, candidate in enumerate(candidates):
            timestamp = float(candidate.get("timestamp_seconds", 0.0) or 0.0)
            image_name = str(candidate.get("image_filename") or candidate.get("output_filename") or "")
            image_path = Path(job.paths["candidates"]) / image_name if image_name else None
            image_uri = _as_uri(image_path) if image_path and image_path.is_file() else ""
            decision = str(candidate.get("decision", "accepted"))
            slides.append({
                "index": index,
                "pct": round(max(0.0, min(100.0, timestamp / duration * 100.0)), 2) if duration else 0,
                "time": _clock(timestamp),
                "state": decision,
                "sel": decision == "accepted",
                "frame": int(candidate.get("frame_number", 0) or 0),
                "timestamp_seconds": timestamp,
                "image_filename": image_name,
                "img": image_uri,
                "thumb": image_uri,
            })
        return slides

    def _slide_payload(self, job: Any, slides: list[dict[str, Any]]) -> dict[str, Any]:
        duration = float(job.source.get("duration", 0.0) or 0.0)
        return {
            "slides": slides,
            "duration": _duration_label(duration),
            "durationMid": _duration_label(duration / 2.0),
        }

    def _transcript(self, job: Any) -> dict[str, Any]:
        segments = []
        if hasattr(self, "transcript_store"):
            segments = self.transcript_store.load_working(job.paths)
        review = []
        blocks = []
        for segment in segments:
            start = float(segment.get("start", 0.0) or 0.0)
            end = float(segment.get("end", start) or start)
            text = str(segment.get("text", "")).strip()
            review.append({"t": _clock(start), "text": text})
            blocks.append({
                "t": _clock(start),
                "hotTime": len(blocks) == 0,
                "html": html.escape(text),
            })
        duration = float(job.source.get("duration", 0.0) or 0.0)
        return {
            "reviewSegments": review,
            "transcript": {
                "title": job.manifest.get("title", "Lecture"),
                "duration": _duration_label(duration),
                "segments": len(segments),
                "corrections": sum(1 for segment in segments if segment.get("edited")),
                "blocks": blocks,
            },
        }

    def _export_files(self, job: Any) -> list[str]:
        export_dir = Path(job.paths["exports"])
        if not export_dir.is_dir():
            return []
        return sorted(path.name for path in export_dir.iterdir() if path.is_file())

    def _emit_job_payloads(self) -> None:
        if self.current_job is None:
            return
        job = self.current_job
        slides = self._slides(job)
        transcript = self._transcript(job)
        self._emit({"event": "jobs_changed", "jobs": [self._summary(item) for item in self._job_objects()]})
        self._emit({"event": "slides_changed", "job": job.job_id, **self._slide_payload(job, slides)})
        self._emit({"event": "transcript_changed", "job": job.job_id, **transcript})
        self._emit_pipeline()
        if hasattr(self, "study_service"):
            self._emit_study_changed()
        self._push_storage()

        if job.get_stage_status("Export") == "completed":
            self._emit({
                "event": "export_done",
                "job": job.job_id,
                "files": self._export_files(job),
                "meta": f"{len(self._export_files(job))} files written to the Study Pack export folder",
            })


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="", help="Developer checkout root for source runs")
    parser.add_argument("--resources-root", default="", help="Sidecar resource root containing bin/ and models/")
    parser.add_argument("--data-dir", required=True, help="Writable persistent LecturePack data directory")
    parser.add_argument("--demo-video", default="", help="Bundled demo video used by the vertical slice")
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args(sys.argv[1:])
    app = QCoreApplication(sys.argv)
    Sidecar(args, app)
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
