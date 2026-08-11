"""Headless LecturePack sidecar for the Electron migration vertical slice.

The sidecar deliberately uses ``QCoreApplication`` because the existing
controller still uses QtCore ``QProcess``, ``QThread``, and ``QTimer``. It does
not create a widget, a Qt window, or a WebEngine view. The processing engine is
reused unchanged behind a small request-id JSONL contract over stdin/stdout.

Commands:
    health_check, list_jobs, import_video, start_job, cancel_job, get_job,
    get_slides, get_transcript, export, set_setting, shutdown

Events:
    ready, bootstrap_progress, jobs_changed,
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
import uuid
from typing import Any

from PySide6.QtCore import QCoreApplication, QProcess, QTimer

# Reject unsafe job ids for any path-traversal-sensitive operation (delete,
# group, rename, open). A job id is a UUID-safe token; anything else is refused.
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

PACKAGED_CHECK_IDS = (
    "data_directory", "ffmpeg", "ffprobe", "whisper_runtime",
    "whisper_smoke", "bundled_model", "study_core", "yt_dlp", "controller",
)


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


class ImportVideoError(Exception):
    """Structured local-video import failure with a renderer-friendly code.

    The renderer maps these codes to short actionable copy; the technical
    message (including the full path) stays in the production log.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
        self._download_lock = threading.Lock()
        self._downloads: dict[str, dict[str, Any]] = {}
        self._download_order: list[str] = []
        self._download_worker_running = False
        self._download_cancel: dict[str, threading.Event] = {}
        self._data_error = ""
        self._last_health: dict[str, Any] | None = None
        self._demo_session: dict[str, Any] | None = None
        self._cleaning_demo = False
        self._guided_tour_state: dict[str, Any] | None = None

        self.repo_root = self._resolve_repo_root()
        if self.repo_root and str(self.repo_root) not in sys.path:
            sys.path.insert(0, str(self.repo_root))
        self.runtime_root = self._resolve_runtime_root()
        self.data_dir = Path(args.data_dir).expanduser().resolve()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._data_error = f"{type(exc).__name__}: {exc}"
        self._load_download_state()
        self.demo_video = Path(args.demo_video).expanduser().resolve() if args.demo_video else None

        self._load_engine()
        self._configure_runtime()
        self._connect_controller()
        self._init_queue()
        self._reconcile_demo_session_on_startup()

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
        # Do not start a blocking Windows pipe read while importing OpenCV,
        # PySide6 workers, and the existing controller. In the locked Windows
        # runtime that can starve the importing thread; starting it after the
        # ready handshake keeps the JSONL boundary responsive without changing
        # the engine internals.
        if not args.self_test:
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
            from lecturepack.services import (
                job_ops,
                media_fetch,
                onboarding_state,
                packaged_health,
                reset_service,
                study_service,
                transcript_store,
            )
            from lecturepack.services import study_presets, study_v2
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
            self.onboarding_state = onboarding_state
            self.packaged_health = packaged_health
            self.reset_service = reset_service
            self.job_ops = job_ops
            self.study_service = study_service
            self.study_presets = study_presets
            self.study_v2 = study_v2
        except Exception as exc:  # noqa: BLE001 - surfaced through ready/error
            self._engine_error = f"{type(exc).__name__}: {exc}"

    def _first_file(self, *candidates: Path) -> str:
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return ""

    def _configure_runtime(self) -> None:
        if self._engine_error or self._data_error:
            if self._data_error and not self._engine_error:
                self._engine_error = self._data_error
            return
        self.config = self.ConfigManager(str(self.data_dir))
        self._guided_tour_state = self.onboarding_state.ensure_guided_tour_state(self.config)
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
        self._prune_queue()
        rows = [{"id": jid, "position": pos}
                for pos, jid in enumerate(self.queue.queued())]
        self._emit({
            "event": "queue_changed",
            "active": self.queue.active,
            "queue": rows,
            "schedules": self.queue.schedules(),
        })

    def _prune_queue(self) -> None:
        """Drop terminal jobs from the waiting queue so they never render as
        waiting after they have completed, failed, or been cancelled."""
        if not hasattr(self, "queue"):
            return
        try:
            statuses = {job.job_id: self._job_status(job) for job in self._job_objects()}
        except Exception:  # noqa: BLE001 - pruning must never crash an emit
            return
        for job_id in list(self.queue.queued()):
            if statuses.get(job_id) in {"done", "failed", "cancelled", "interrupted"}:
                try:
                    self.queue.remove(job_id)
                except Exception:  # noqa: BLE001
                    pass

    def _reconcile_queue_on_startup(self) -> None:
        """Resolve schedules that came due while the app was closed."""
        if not hasattr(self, "queue"):
            return
        try:
            self.queue.reconcile_schedules_on_launch()
        except Exception:
            pass

    def _recover_interrupted_jobs(self, request_id: str | None, command: str) -> None:
        """Feature 6: return crash-interrupted processing jobs back to the FIFO
        queue, exactly once, preserving the existing queue order. Called only
        after startup health has passed. A job left 'running' by a dead session
        loads as 'interrupted'; those are the only jobs re-enqueued. DONE,
        FAILED, and CANCELLED jobs are untouched, and the idempotent enqueue
        prevents duplicate queue entries."""
        if not hasattr(self, "queue"):
            self._respond(request_id, command, recovered=0, requeued=[])
            return
        requeued: list[str] = []
        try:
            for job in self._job_objects():
                if self._job_status(job) != "interrupted":
                    continue
                # Skip anything already in the queue or active (idempotent).
                if job.job_id in self.queue.queued() or self.queue.active == job.job_id:
                    continue
                position = self.electron_backend.enqueue_job(self.queue, job.job_id)
                if position is not None and position >= 0:
                    requeued.append(job.job_id)
        except Exception as exc:  # noqa: BLE001 - recovery must never crash startup
            self._emit({"event": "error", "error": f"recover_interrupted_jobs: {exc}"})
        if requeued:
            self._emit({"event": "queue_changed", "active": self.queue.active,
                        "queue": [{"id": jid, "position": pos}
                                  for pos, jid in enumerate(self.queue.queued())],
                        "schedules": self.queue.schedules()})
        self._respond(request_id, command, recovered=len(requeued), requeued=requeued)

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

    def _maybe_resume_queue(self) -> None:
        """After a restart, resume the persistent queue: when nothing is
        running and jobs are waiting, promote and start the next one."""
        if self._shutting_down or self.controller is None or self.current_stage:
            return
        if not hasattr(self, "queue") or self.queue is None:
            return
        # A stale active slot left by a terminal run (e.g. cancelled during
        # shutdown) must not block the queue from resuming after a restart.
        active_id = self.queue.active
        if active_id:
            try:
                statuses = {job.job_id: self._job_status(job) for job in self._job_objects()}
                if statuses.get(active_id) in {"done", "failed", "cancelled", "interrupted"}:
                    self.queue.finish_active(active_id)
            except Exception:  # noqa: BLE001 - startup must never crash on a bad slot
                self.queue.finish_active(active_id)
        if self.queue.active is not None:
            return
        nxt = self.queue.promote_next()
        self._push_queue()
        if not nxt:
            return
        try:
            job = self._job_for({"job_id": nxt})
        except Exception:  # noqa: BLE001 - a corrupt queued job must not block startup
            return
        QTimer.singleShot(0, lambda: self._start_queued(job))

    def _start_queued(self, job: Any) -> None:
        """Start a queued job (no request_id; fire-and-forget)."""
        if self.controller is None or self._shutting_down:
            return
        if self.current_stage:
            return
        # The previous run's QThreads/QProcesses may still be unwinding after a
        # cancellation; starting the next pipeline before they fully stop lets
        # a late worker signal cancel the new job's stage. Drain first.
        if not self._drain_previous_run():
            return
        self._activate_job(job, emit_payloads=False)
        self.auto_export = True
        self.current_stage = "Queued"
        self._emit({"event": "job_started", "job_id": job.job_id})
        self._emit_job_payloads()
        self._push_queue()
        self.controller.run_pipeline()

    def _drain_previous_run(self, timeout_ms: int = 5000) -> bool:
        """Wait (bounded) for the previous run's workers to fully unwind."""
        if self.controller is None:
            return True
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            if not self._processing_workers_running():
                return True
            QCoreApplication.processEvents()
            time.sleep(0.01)
        return not self._processing_workers_running()

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

    def _fail(self, request_id: str | None, command: str, message: str,
              error_code: str | None = None) -> None:
        self._emit({
            "event": "error",
            "response_to": request_id,
            "command": command,
            "ok": False,
            "error": str(message),
            **({"error_code": error_code} if error_code else {}),
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
            elif command == "import_videos":
                self._import_videos(request_id, command, payload)
            elif command == "apply_job_settings":
                self._apply_job_settings(request_id, command, payload)
            elif command == "queue_jobs":
                self._queue_jobs(request_id, command, payload)
            elif command == "queue_existing_jobs":
                self._queue_existing_jobs(request_id, command, payload)
            elif command == "get_onboarding_state":
                self._get_onboarding_state(request_id, command)
            elif command == "set_guided_tour_state":
                self._set_guided_tour_state(request_id, command, payload)
            elif command == "replay_guided_tour":
                self._replay_guided_tour(request_id, command)
            elif command == "acknowledge_setup":
                self._acknowledge_setup(request_id, command)
            elif command == "end_demo_job":
                self._end_demo_job(request_id, command, payload)
            elif command == "reset_lecturepack":
                self._reset_lecturepack(request_id, command)
            elif command == "recover_interrupted_jobs":
                self._recover_interrupted_jobs(request_id, command)
            elif command == "search_transcripts":
                self._search_transcripts(request_id, command, payload)
            elif command == "start_job":
                self._start_job(request_id, command, payload)
            elif command == "cancel_job":
                self._cancel_job(request_id, command, payload)
            elif command == "get_job":
                self._get_job(request_id, command, payload)
            elif command == "view_job":
                self._view_job(request_id, command, payload)
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
                self._cancel_media_url(request_id, command, payload)
            elif command == "remove_media_download":
                self._remove_media_download(request_id, command, payload)
            elif command == "retry_media_download":
                self._retry_media_download(request_id, command, payload)
            elif command == "clear_media_downloads":
                self._clear_media_downloads(request_id, command)
            elif command == "get_media_downloads":
                self._get_media_downloads(request_id, command)
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
            elif command == "study_v2_status":
                self._study_v2_status(request_id, command, payload)
            elif command == "study_v2_record_flashcard":
                self._study_v2_record_flashcard(request_id, command, payload)
            elif command == "study_v2_record_quiz":
                self._study_v2_record_quiz(request_id, command, payload)
            elif command == "study_v2_quick_study":
                self._study_v2_quick_study(request_id, command, payload)
            elif command == "study_v2_summary":
                self._study_v2_summary(request_id, command, payload)
            elif command == "study_v2_edit":
                self._study_v2_edit(request_id, command, payload)
            elif command == "study_v2_delete":
                self._study_v2_delete(request_id, command, payload)
            elif command == "study_v2_regenerate":
                self._study_v2_regenerate(request_id, command, payload)
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
            error_code = getattr(exc, "code", None)
            self._emit({
                "event": "error",
                "command": command,
                "error": message_text,
                **({"error_code": error_code} if error_code else {}),
            })
            self._fail(request_id, command, message_text, error_code=error_code)

    # ------------------------------------------------------------------ #
    # Contract commands
    # ------------------------------------------------------------------ #
    def _health_check(self, request_id: str | None, command: str) -> None:
        for check_id in PACKAGED_CHECK_IDS:
            self._emit({"event": "bootstrap_progress", "id": check_id, "state": "checking"})
        health = self._packaged_self_test(include_sidecar=False)
        self._last_health = health
        for check in health["checks"]:
            self._emit({
                "event": "bootstrap_progress",
                "id": check["id"],
                "state": "resolved" if check["ok"] else "failed",
                "detail": check["detail"],
            })
        if not health["startup_ok"]:
            failed = next(
                (check for check in health["checks"] if check["fatal_at_startup"] and not check["ok"]),
                None,
            )
            if failed:
                self._emit({"event": "runtime_missing", "component": failed["id"], "detail": failed["detail"]})
        self._respond(
            request_id,
            command,
            healthy=health["startup_ok"],
            runtime_health_state="HEALTHY" if health["startup_ok"] else "SETUP_REQUIRED",
            setup_acknowledged=bool(
                health["startup_ok"]
                and hasattr(self, "config")
                and self.config.setup_acknowledged()
            ),
            setup_complete=bool(
                health["startup_ok"]
                and hasattr(self, "config")
                and self.config.setup_acknowledged()
            ),
            engine_loaded=not bool(self._engine_error),
            qt_application="QCoreApplication",
            passed=health["passed"],
            startup_ok=health["startup_ok"],
            checks=health["checks"],
            checklist=health.get("checklist", []),
            error=self._engine_error,
        )

    def _acknowledge_setup(self, request_id: str | None, command: str) -> None:
        """Persist acknowledgement only against the latest passing health."""
        health = self._last_health
        if health is None:
            health = self._packaged_self_test(include_sidecar=False)
            self._last_health = health
        if not health.get("startup_ok") or not hasattr(self, "config"):
            self._respond(
                request_id,
                command,
                ok=False,
                error="Runtime Setup must pass its required checks before it can be acknowledged.",
                error_code="SETUP_REQUIRED",
                runtime_health_state="SETUP_REQUIRED",
                setup_acknowledged=False,
            )
            return
        self.config.persist_setup_acknowledged()
        self._respond(
            request_id,
            command,
            setup_acknowledged=True,
            setup_complete=True,
            runtime_health_state="HEALTHY",
            healthy=True,
        )

    def _packaged_self_test(self, *, include_sidecar: bool = True) -> dict[str, Any]:
        if not hasattr(self, "packaged_health"):
            checks = [{
                "id": "controller",
                "ok": False,
                "required": True,
                "fatal_at_startup": True,
                "title": "Processing service unavailable",
                "detail": "LecturePack could not import its processing service.",
                "technical": self._engine_error,
            }]
            health = {"passed": False, "startup_ok": False, "checks": checks}
        else:
            fault = self.args.self_test_fault if self.args.self_test else ""
            study_core_info = self.study_v2.study_core_info
            media_available = self.media_fetch.is_available
            media_version = self.media_fetch.version
            youtube_support = getattr(self.media_fetch, "youtube_support", None)
            if fault == "study_core":
                study_core_info = lambda: {
                    "available": False,
                    "implementation": "python",
                    "error": "release self-test injected missing native module",
                }
            elif fault == "yt_dlp":
                media_available = lambda: False
                media_version = lambda: ""
                youtube_support = lambda: {"yt_dlp": False, "ejs": False, "js_runtime": False}
            elif fault == "js_runtime":
                # Prove the packaged build notices a missing JavaScript
                # runtime instead of reporting healthy YouTube support.
                _real_support = youtube_support
                youtube_support = lambda: {
                    **(_real_support() if _real_support else {}),
                    "js_runtime": False,
                    "js_runtime_version": "",
                }
            smoke_wav = self.runtime_root / "smoke" / "runtime-smoke.wav"
            if self.repo_root is not None and not smoke_wav.is_file():
                smoke_wav = self.repo_root / "app" / "packaging" / "assets" / "runtime-smoke.wav"
            health = self.packaged_health.run_packaged_health(
                runtime_root=self.runtime_root,
                data_dir=self.data_dir,
                controller=self.controller,
                study_core_info=study_core_info,
                media_available=media_available,
                media_version=media_version,
                youtube_support=youtube_support,
                smoke_wav=smoke_wav,
            )
        checks = list(health["checks"])
        checklist = list(health.get("checklist", []))
        if include_sidecar:
            sidecar_ok = True
            checks.insert(0, {
                "id": "sidecar",
                "ok": sidecar_ok,
                "required": True,
                "fatal_at_startup": True,
                "title": "Processing service unavailable",
                "detail": "Packaged sidecar initialized." if sidecar_ok else "LecturePack could not initialize its packaged sidecar.",
                "technical": self._engine_error,
            })
        return {
            "passed": all(check.get("ok") for check in checks if check.get("required")),
            "startup_ok": all(check.get("ok") for check in checks if check.get("fatal_at_startup")),
            "checks": checks,
            "checklist": checklist,
        }

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
            job_id = directory.name
            # Never re-construct the live job: Job's loader treats a persisted
            # "running" state as orphaned and flips it to interrupted, which
            # would corrupt a pipeline that is still running in this session.
            if self.current_job is not None and self.current_job.job_id == job_id:
                jobs.append(self.current_job)
                continue
            try:
                jobs.append(self.Job(str(self.data_dir), job_id=job_id,
                                     current_session_id=self.session_id))
            except Exception as exc:  # noqa: BLE001 - one corrupt job must not hide others
                self._emit({"event": "error", "error": f"job {job_id}: {exc}"})
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
        queue_position = None
        if hasattr(self, "queue"):
            try:
                queue_position = self.queue.position(job.job_id)
            except Exception:  # noqa: BLE001 - a queue failure must not hide the job
                queue_position = None
        settings = getattr(job, "settings", None) or {}
        stages = job.state.get("stages", {}) if isinstance(job.state, dict) else {}
        failed_stage = next((name for name, details in stages.items()
                             if isinstance(details, dict) and details.get("status") == "failed"), "")
        error = str(stages.get(failed_stage, {}).get("error", "")) if failed_stage else ""
        return {
            "id": job.job_id,
            "name": job.manifest.get("title") or source.get("filename") or "Lecture",
            "file": source.get("filename", ""),
            "source_title": source.get("filename", ""),
            "status": status,
            "pct": self._job_percent(job),
            "stage": active or self._last_stage(job),
            "meta": f"{_duration_label(duration)} - local Electron sidecar" if duration else "local Electron sidecar",
            "duration": duration,
            "updated_at": job.state.get("last_updated", ""),
            "preset": str(settings.get("preset", "balanced") or "balanced"),
            "product_mode": str(settings.get("product_mode", "study_pack") or "study_pack"),
            "queue_position": queue_position,
            "waiting": queue_position is not None,
            "error": error[:500],
        }

    @staticmethod
    def _last_stage(job: Any) -> str:
        for stage in reversed(STAGES):
            if job.get_stage_status(stage) == "completed":
                return stage
        return "Queued"

    def _list_jobs(self, request_id: str | None, command: str) -> None:
        guided_tour = self._emit_onboarding_state()
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
        self._push_queue()
        self._maybe_resume_queue()
        self._respond(request_id, command, jobs=summaries, guided_tour=guided_tour)

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

        Uses QProcess so the sidecar keeps its no-shell contract; the existing
        engine's ffmpeg wrapper owns the binary path.
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
            process = QProcess()
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            process.start(ffmpeg, [
                "-y", "-i", str(source), "-frames:v", "1",
                "-vf", "scale=320:-2", "-f", "webp", str(dst),
            ])
            if not process.waitForFinished(30000):
                process.kill()
                return
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

    def _import_one(self, path_text: str, *, title: str = "", preset: Any = None,
                    bundled_demo: bool = False,
                    demo_session_id: str | None = None) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        """Import ONE video through the normal single-video path and return
        (job, summary, metadata). Shared by the single import command and the
        batch import command so a multi-file import creates every job through
        exactly the same code path as a single Browse/Drop import."""
        if bundled_demo:
            # D-2: the demo flows through the normal import path using the
            # bundled demo video. There is no separate fake demo pipeline.
            source = self._resolve_demo_video()
            if source is None:
                raise ImportVideoError("NOT_FOUND", "bundled demo video not found")
        else:
            if not path_text:
                raise ImportVideoError("RESOLVE_FAILED", "no video path was supplied")
            try:
                source = Path(path_text).expanduser().resolve()
            except (OSError, ValueError) as exc:
                raise ImportVideoError(
                    "RESOLVE_FAILED", f"could not resolve video path: {path_text}"
                ) from exc
        if source is None:
            raise ImportVideoError("RESOLVE_FAILED", "no video path was supplied")
        try:
            is_file = source.is_file()
        except OSError as exc:  # noqa: BLE001 - a locked/unreadable parent
            raise ImportVideoError("UNREADABLE", f"could not inspect video path: {source}") from exc
        if not is_file:
            raise ImportVideoError("NOT_FOUND", f"video not found: {source}")
        if not os.access(source, os.R_OK):
            raise ImportVideoError("UNREADABLE", f"video is not readable: {source}")
        if bundled_demo:
            # Starting a bundled demo is the real replay/new-tour boundary.
            # Reset only the durable offer state; ordinary lecture imports do
            # not affect onboarding and existing jobs remain untouched.
            if hasattr(self, "config"):
                self._guided_tour_state = self.onboarding_state.set_guided_tour_status(
                    self.config, "not_seen"
                )
                self._emit({"event": "onboarding_state",
                            "guided_tour": dict(self._guided_tour_state),
                            **self._guided_tour_state})
            source = self._copy_demo_if_needed(source)
        if self.controller is None:
            raise RuntimeError(self._engine_error or "engine is not loaded")
        try:
            metadata = self.controller.ffmpeg_wrapper.inspect_video(str(source))
        except Exception as exc:  # noqa: BLE001 - surfaced as a friendly format error
            raise ImportVideoError("FFPROBE_FAILED", f"ffprobe could not read the video: {exc}") from exc
        job = self.Job(str(self.data_dir), video_path=str(source))
        # Keep the immutable source filename/path in manifest["source"] and a
        # separate, editable display title in manifest["title"].
        job.manifest["title"] = str(title or self.job_ops.clean_display_title(source.name))
        if bundled_demo:
            demo_session_id = str(demo_session_id or f"demo-{uuid.uuid4()}")
            job.manifest.update({
                "is_demo": True,
                "bundled_demo": True,
                "demo_session_id": demo_session_id,
                "demo_owner": "guided_tour",
            })
        job.source.update(metadata)
        job.settings["preset"] = self._preset(preset)
        job.settings.setdefault("whisper", {})["engine"] = "cpu"
        model = self.config.get("whisper_model", "")
        if model and os.path.isfile(model):
            job.settings["whisper"]["model"] = model
        job.settings["whisper"]["transcription_backend"] = "local-whispercpp"
        job.save()
        if bundled_demo:
            self._demo_session = {
                "session_id": demo_session_id,
                "job_id": job.job_id,
                "status": "running",
            }
            try:
                self._write_demo_marker(self._demo_session)
            except Exception as exc:  # noqa: BLE001 - do not leave an untracked demo job
                try:
                    shutil.rmtree(Path(job.paths["root"]))
                except OSError:
                    pass
                self._demo_session = None
                raise ImportVideoError(
                    "DEMO_STATE_FAILED",
                    f"guided demo session could not be recorded: {exc}",
                ) from exc
        # PC polish: generate the job-card thumbnail immediately at import so
        # the card shows a real video frame before processing starts. A failure
        # must never prevent the import.
        self._generate_poster(job, source)
        return job, self._summary(job), metadata

    def _import_video(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        job, summary, metadata = self._import_one(
            str(payload.get("path") or ""),
            title=str(payload.get("title") or ""),
            preset=payload.get("preset"),
            bundled_demo=bool(payload.get("bundled_demo")),
        )
        self._activate_job(job, emit_payloads=True)
        self._emit({
            "event": "onboarding",
            "job": job.job_id,
            "name": job.manifest.get("title", "Lecture"),
            "meta": summary.get("meta", ""),
        })
        self._respond(
            request_id,
            command,
            job=summary,
            job_id=job.job_id,
            source=metadata,
            **({
                "is_demo": True,
                "demo_session_id": self._demo_session.get("session_id"),
            } if self._is_demo_job(job) and self._demo_session else {}),
        )

    def _import_videos(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Import several videos in one action. Every file flows through the
        normal single-video import path (_import_one); duplicate resolved paths
        are skipped; one failed file does not fail the rest of the batch. The
        batch is reported with one batch_import event so the renderer can show
        a compact setup state before any processing begins."""
        raw_paths = payload.get("paths") or []
        if isinstance(raw_paths, str):
            try:
                raw_paths = json.loads(raw_paths)
            except json.JSONDecodeError:
                raw_paths = []
        if not isinstance(raw_paths, list):
            raise ImportVideoError("RESOLVE_FAILED", "no video paths were supplied")
        seen: set[str] = set()
        imported: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        active_job = None
        for entry in raw_paths:
            path_text = str(entry.get("path") if isinstance(entry, dict) else entry or "")
            if not path_text:
                continue
            try:
                resolved = str(Path(path_text).expanduser().resolve())
            except (OSError, ValueError):
                resolved = path_text
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                job, summary, _metadata = self._import_one(
                    path_text,
                    title=str(entry.get("title") if isinstance(entry, dict) else "" or ""),
                    preset=entry.get("preset") if isinstance(entry, dict) else None,
                )
            except ImportVideoError as exc:
                failures.append({"path": path_text, "code": exc.code, "error": str(exc)})
                continue
            except Exception as exc:  # noqa: BLE001 - one failed import must not fail the batch
                failures.append({"path": path_text, "code": "IMPORT_FAILED", "error": str(exc)})
                continue
            imported.append(summary)
            active_job = job
        if active_job is not None:
            self._activate_job(active_job, emit_payloads=True)
        self._emit({"event": "batch_import", "jobs": imported, "failures": failures})
        self._respond(
            request_id,
            command,
            jobs=imported,
            failures=failures,
            count=len(imported),
        )

    def _apply_job_settings(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Apply one output mode / quality choice to every unstarted job in a
        batch. Jobs that are already running or already completed are left
        untouched so an explicit start is never overwritten."""
        job_ids = payload.get("job_ids") or []
        if isinstance(job_ids, str):
            try:
                job_ids = json.loads(job_ids)
            except json.JSONDecodeError:
                job_ids = []
        if not isinstance(job_ids, list):
            job_ids = []
        mode = payload.get("mode")
        preset = payload.get("preset")
        applied: list[str] = []
        skipped: list[str] = []
        for job_id in [str(job_id) for job_id in job_ids if job_id]:
            try:
                job = self._job_for({"job_id": job_id})
            except Exception:  # noqa: BLE001 - a missing job is skipped, not fatal
                skipped.append(job_id)
                continue
            status = self._job_status(job)
            if status in {"running", "paused", "done", "failed", "cancelled", "interrupted"}:
                skipped.append(job_id)
                continue
            if mode:
                job.settings["product_mode"] = self._product_mode(mode)
            if preset:
                job.settings["preset"] = self._preset(preset)
            job.save()
            applied.append(job_id)
        self._emit_job_payloads()
        self._respond(request_id, command, applied=applied, skipped=skipped)

    def _queue_jobs(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Enqueue a batch of jobs in their visible order. The queue respects
        the single active slot: the first job claims it on start, the rest
        wait in FIFO order. Nothing is started merely by queuing."""
        # The production bridge uses this historical command for internal
        # drag/drop as well as batch actions. Once the real data root exists,
        # use the identity/status-aware path; the small fallback preserves the
        # older adapter seam used by lightweight unit fixtures.
        if hasattr(self, "data_dir"):
            self._queue_existing_jobs(request_id, command, payload)
            return
        job_ids = payload.get("job_ids") or []
        if isinstance(job_ids, str):
            try:
                job_ids = json.loads(job_ids)
            except json.JSONDecodeError:
                job_ids = []
        if not isinstance(job_ids, list):
            job_ids = []
        positions: list[dict[str, Any]] = []
        for job_id in [str(job_id) for job_id in job_ids if job_id]:
            try:
                position = self.electron_backend.enqueue_job(self.queue, job_id)
            except Exception:  # noqa: BLE001 - one bad job must not stop the batch
                continue
            positions.append({"job_id": job_id, "position": position})
        self._push_queue()
        self._emit_job_payloads()
        self._respond(request_id, command, queued=positions,
                      queued_ids=[row["job_id"] for row in positions],
                      count=len(positions))
        # "Queue all" is an action, not a parked-state editor. When the active
        # slot is idle, immediately promote and start the first queued job;
        # the existing completion path continues the remaining FIFO entries.
        self._maybe_resume_queue()

    def _queue_existing_jobs(self, request_id: str | None, command: str,
                             payload: dict[str, Any]) -> None:
        """Queue already-imported jobs without importing or duplicating them.

        ``JobQueue`` remains the only FIFO authority. This adapter adds the
        validation/reporting needed by an internal drag/drop action while the
        historical ``queue_jobs`` batch command remains compatible with the
        existing batch-import UI.
        """
        job_ids = payload.get("job_ids") or []
        if isinstance(job_ids, str):
            try:
                job_ids = json.loads(job_ids)
            except json.JSONDecodeError:
                job_ids = []
        if not isinstance(job_ids, list):
            job_ids = []
        jobs_by_id = {str(job.job_id): job for job in self._job_objects()}
        queued: list[str] = []
        positions: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_id in job_ids:
            job_id = str(raw_id or "").strip()
            if not job_id:
                continue
            if job_id in seen:
                skipped.append({"job_id": job_id, "reason": "duplicate_request"})
                continue
            seen.add(job_id)
            job = jobs_by_id.get(job_id)
            if job is None:
                skipped.append({"job_id": job_id, "reason": "not_found"})
                continue
            status = self._job_status(job)
            if status in {"done", "failed", "cancelled", "interrupted"}:
                skipped.append({"job_id": job_id, "reason": status})
                continue
            if self.queue.active == job_id:
                skipped.append({"job_id": job_id, "reason": "active"})
                continue
            if job_id in self.queue.queued():
                skipped.append({"job_id": job_id, "reason": "already_queued"})
                continue
            position = self.electron_backend.enqueue_job(self.queue, job_id)
            if position is None or position < 0:
                skipped.append({"job_id": job_id, "reason": "queue_rejected"})
                continue
            queued.append(job_id)
            positions.append({"job_id": job_id, "position": position})
        self._push_queue()
        self._emit_job_payloads()
        self._respond(
            request_id,
            command,
            queued=queued,
            queued_ids=queued,
            positions=positions,
            skipped=skipped,
            count=len(queued),
        )
        self._maybe_resume_queue()

    def _emit_onboarding_state(self) -> dict[str, Any]:
        if not hasattr(self, "config"):
            return self._guided_tour_state or {
                "current_version": 2,
                "seen_version": 0,
                "version": "2.0.1",
                "status": "not_seen",
                "completed": False,
                "skipped": False,
                "eligible": True,
            }
        self._guided_tour_state = self.onboarding_state.ensure_guided_tour_state(self.config)
        self._emit({"event": "onboarding_state",
                    "guided_tour": dict(self._guided_tour_state),
                    **self._guided_tour_state})
        return dict(self._guided_tour_state)

    def _get_onboarding_state(self, request_id: str | None, command: str) -> None:
        state = self._emit_onboarding_state()
        self._respond(request_id, command, guided_tour=state, **state)

    def _set_guided_tour_state(self, request_id: str | None, command: str,
                               payload: dict[str, Any]) -> None:
        if not hasattr(self, "config"):
            self._respond(request_id, command, ok=False, error="Runtime state is unavailable.")
            return
        status = payload.get("status") or payload.get("state")
        state = self.onboarding_state.set_guided_tour_status(self.config, status)
        self._guided_tour_state = state
        self._emit({"event": "onboarding_state", "guided_tour": dict(state), **state})
        self._respond(request_id, command, guided_tour=state, **state)

    def _replay_guided_tour(self, request_id: str | None, command: str) -> None:
        """Reset only the tour offer; the bridge starts a fresh demo session."""
        if not hasattr(self, "config"):
            self._respond(request_id, command, ok=False, error="Runtime state is unavailable.")
            return
        state = self.onboarding_state.set_guided_tour_status(self.config, "not_seen")
        self._guided_tour_state = state
        self._emit({"event": "onboarding_state", "replay": True,
                    "guided_tour": dict(state), **state})
        self._respond(request_id, command, replay=True, ready_to_start=True,
                      guided_tour=state, **state)

    def _record_guided_tour_terminal_state(self, reason: Any) -> dict[str, Any] | None:
        """Persist explicit renderer demo-exit reasons at the state boundary.

        The current renderer also keeps a legacy localStorage marker. Do not
        make that browser-only marker authoritative: the sidecar owns the
        durable state and can safely interpret the two explicit tour reasons
        that cross the demo-session boundary. Operational cancellation and
        runtime failure deliberately remain eligible for a later retry.
        """
        normalized = str(reason or "").strip().lower()
        status = {
            "tour_complete": "completed",
            "tour_completed": "completed",
            "complete": "completed",
            "completed": "completed",
            "tour_exit": "skipped",
            "tour_skip": "skipped",
            "skip": "skipped",
            "skipped": "skipped",
        }.get(normalized)
        if status is None or not hasattr(self, "config"):
            return None
        state = self.onboarding_state.set_guided_tour_status(self.config, status)
        self._guided_tour_state = state
        self._emit({"event": "onboarding_state", "guided_tour": dict(state), **state})
        return state

    # ------------------------------------------------------------------ #
    # Temporary guided-demo lifecycle
    # ------------------------------------------------------------------ #
    def _demo_marker_path(self) -> Path:
        return self.data_dir / "demo-session.json"

    def _write_demo_marker(self, session: dict[str, Any]) -> None:
        self.FileManager.write_json_atomic(str(self._demo_marker_path()), {
            "schema_version": 1,
            "session_id": str(session["session_id"]),
            "job_id": str(session["job_id"]),
            "status": str(session.get("status") or "running"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })

    def _read_demo_marker(self) -> dict[str, Any] | None:
        path = self._demo_marker_path()
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _is_demo_job(self, job: Any) -> bool:
        manifest = getattr(job, "manifest", {}) or {}
        return bool(
            manifest.get("is_demo") is True
            or manifest.get("bundled_demo") is True
            or manifest.get("demo_session_id")
        )

    def _remove_demo_inputs(self) -> None:
        target = self.data_dir / "demo-inputs"
        if not (target.exists() or target.is_symlink() or os.path.islink(target)):
            return
        root = self.data_dir.resolve(strict=False)
        resolved = target.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"refusing to remove demo inputs outside data root: {target}") from exc
        if target.is_symlink() or os.path.islink(target):
            target.unlink()
        else:
            shutil.rmtree(target)

    def _delete_demo_job(self, job_id: str) -> dict[str, Any]:
        if not _SAFE_JOB_ID.fullmatch(str(job_id or "")):
            return {"ok": False, "error": "invalid demo job id"}
        result = self.electron_backend.delete_job(str(self.data_dir), str(job_id))
        if result.get("ok") and hasattr(self, "queue"):
            self.queue.remove(str(job_id))
        return result

    def _reconcile_demo_session_on_startup(self) -> None:
        """Remove only explicitly marked demo jobs left by a crashed tour."""
        if self._engine_error or not hasattr(self, "electron_backend"):
            return
        marker = self._read_demo_marker()
        demo_ids: set[str] = set()
        if marker and _SAFE_JOB_ID.fullmatch(str(marker.get("job_id") or "")):
            demo_ids.add(str(marker["job_id"]))
        jobs_root = self.data_dir / "jobs"
        if jobs_root.is_dir():
            for directory in jobs_root.iterdir():
                manifest_path = directory / "manifest.json"
                if not directory.is_dir() or not manifest_path.is_file():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(manifest, dict) and (
                    manifest.get("is_demo") is True
                    or manifest.get("bundled_demo") is True
                    or manifest.get("demo_session_id")
                ):
                    if _SAFE_JOB_ID.fullmatch(directory.name):
                        demo_ids.add(directory.name)
        removed = 0
        for job_id in sorted(demo_ids):
            try:
                result = self._delete_demo_job(job_id)
                if result.get("ok"):
                    removed += 1
            except Exception as exc:  # noqa: BLE001 - startup must surface, not hide, cleanup faults
                self._emit({"event": "error", "error": f"demo reconciliation: {exc}"})
        if marker or removed:
            try:
                self._demo_marker_path().unlink(missing_ok=True)
                self._remove_demo_inputs()
            except (OSError, RuntimeError) as exc:
                self._emit({"event": "error", "error": f"demo artifact cleanup: {exc}"})
        if removed:
            self._push_queue()

    def _cleanup_demo_session(self, reason: str = "tour_end") -> dict[str, Any]:
        session = self._demo_session or self._read_demo_marker()
        if not session:
            return {"ok": True, "status": "not_running"}
        job_id = str(session.get("job_id") or "")
        session_id = str(session.get("session_id") or "")
        if not _SAFE_JOB_ID.fullmatch(job_id):
            return {"ok": False, "error": "guided demo session has an invalid job id"}

        self._cleaning_demo = True
        try:
            if self.current_job is not None and self.current_job.job_id == job_id:
                if self.current_stage and self.controller is not None:
                    self.controller.cancel()
                    self.current_stage = ""
                    if not self._drain_previous_run():
                        return {"ok": False, "error": "guided demo workers did not stop safely"}
            result = self._delete_demo_job(job_id)
            if not result.get("ok") and (self.data_dir / "jobs" / job_id).exists():
                return {"ok": False, "error": result.get("error") or "could not remove guided demo job"}
            if self.current_job is not None and self.current_job.job_id == job_id:
                self.current_job = None
                self.current_stage = ""
                self.stage_percent = {}
                if self.controller is not None:
                    self.controller.set_job(None)
                self._emit({"event": "active_job", "id": "", "title": ""})
            try:
                self._demo_marker_path().unlink(missing_ok=True)
                self._remove_demo_inputs()
            except (OSError, RuntimeError) as exc:
                return {"ok": False, "error": f"could not remove guided demo artifacts: {exc}"}
            self._demo_session = None
            guided_tour = self._record_guided_tour_terminal_state(reason)
            self._emit({
                "event": "demo_session",
                "status": "cleaned",
                "reason": str(reason or "tour_end"),
                "session_id": session_id,
                "job_id": job_id,
            })
            self._emit({"event": "jobs_changed", "jobs": [
                self._summary(job) for job in self._job_objects()
            ]})
            self._push_queue()
            return {
                "ok": True,
                "status": "cleaned",
                "session_id": session_id,
                "job_id": job_id,
                **({"guided_tour": guided_tour} if guided_tour else {}),
            }
        finally:
            self._cleaning_demo = False

    def _end_demo_job(self, request_id: str | None, command: str,
                      payload: dict[str, Any]) -> None:
        session = self._demo_session
        reason = str(payload.get("reason") or "tour_end")
        if session is None:
            guided_tour = self._record_guided_tour_terminal_state(reason)
            self._respond(request_id, command, ok=True, status="not_running",
                          **({"guided_tour": guided_tour} if guided_tour else {}))
            return
        requested = str(payload.get("job_id") or "")
        if requested and requested != str(session.get("job_id")):
            self._respond(request_id, command, ok=False,
                          error="guided demo session does not match requested job")
            return
        result = self._cleanup_demo_session(reason)
        self._respond(request_id, command, **result)

    def _reset_lecturepack(self, request_id: str | None, command: str) -> None:
        """Stop workers, clear known data-root state, and report failures."""
        with self._download_lock:
            for event in self._download_cancel.values():
                event.set()
            for item in self._downloads.values():
                if item.get("status") in {"waiting", "downloading"}:
                    item["status"] = "cancelled"
            self._persist_downloads_locked()
        if self.controller is not None:
            try:
                self.controller.cancel()
            except Exception:
                pass
        self.current_stage = ""
        if not self._drain_previous_run(timeout_ms=8000):
            self._respond(request_id, command, ok=False,
                          error="LecturePack workers did not stop safely; reset was not completed.")
            return
        result = self.reset_service.reset_data_root(self.data_dir)
        if not result.get("ok"):
            self._respond(request_id, command, ok=False, error="LecturePack reset could not remove all owned state.",
                          reset=result)
            return
        self.current_job = None
        self._demo_session = None
        self.current_stage = ""
        self.stage_percent = {}
        if self.controller is not None:
            self.controller.set_job(None)
        self._downloads.clear()
        self._download_order.clear()
        self._download_cancel.clear()
        self.config = self.ConfigManager(str(self.data_dir))
        self._guided_tour_state = self.onboarding_state.ensure_guided_tour_state(self.config)
        self.queue = self.JobQueue(str(self.data_dir))
        self._emit({"event": "active_job", "id": "", "title": ""})
        self._emit({"event": "jobs_changed", "jobs": []})
        self._push_queue()
        self._emit_downloads()
        self._emit_onboarding_state()
        self._respond(request_id, command, reset=result,
                      guided_tour=self._guided_tour_state,
                      relaunch_required=True)

    def _search_transcripts(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Search processed transcript text across completed jobs.

        Plain case-insensitive text search over the working transcript of every
        completed job (no AI, no embeddings, no index). Phrase matches rank
        first, then word matches. Each result carries the job id/name, the
        matching segment's start timestamp, and a short snippet around the
        match so the renderer can open the lecture at that segment.
        """
        query = str(payload.get("query") or "").strip()
        limit = payload.get("limit")
        try:
            limit = max(1, min(int(limit or 20), 50))
        except (TypeError, ValueError):
            limit = 20
        if not query:
            self._respond(request_id, command, query="", results=[], count=0)
            return
        needle = query.casefold()
        needle_phrase = True if " " in query.strip() else needle
        results: list[dict[str, Any]] = []
        for job in self._job_objects():
            if self._job_status(job) != "done":
                continue
            segments = []
            try:
                segments = self.transcript_store.load_working(job.paths) or []
            except Exception:  # noqa: BLE001 - one bad job must not break search
                continue
            job_name = job.manifest.get("title") or str(job.manifest.get("source", {}).get("filename", "")) or "Lecture"
            for segment in segments:
                raw = str(segment.get("text", ""))
                text = raw.strip()
                if not text:
                    continue
                folded = raw.casefold()
                idx = folded.find(needle)
                if idx < 0:
                    continue
                # Phrase matches (exact multi-word) rank above single-word matches.
                is_phrase = len(query.split()) > 1 and needle in folded
                start_char = max(0, idx - 40)
                end_char = min(len(raw), idx + len(query) + 80)
                snippet = raw[start_char:end_char].replace("\n", " ").strip()
                if len(snippet) > 140:
                    snippet = snippet[:140] + "…"
                results.append({
                    "job_id": job.job_id,
                    "name": job_name,
                    "timestamp": _clock(float(segment.get("start", 0.0) or 0.0)),
                    "segment": len(results),
                    "snippet": snippet,
                    "phrase": is_phrase,
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        # Phrase matches first, then insertion order (earliest job/segment).
        results.sort(key=lambda r: (0 if r["phrase"] else 1))
        self._respond(request_id, command, query=query, results=results, count=len(results))

    def _activate_job(self, job: Any, *, emit_payloads: bool) -> None:
        # A pipeline is already running: never swap the controller's job, clear
        # the live stage marker, or re-point current_job mid-run -- even when
        # the requested job is the running one (e.g. a bootstrap restore or an
        # import of another video). The new job joins the list and is activated
        # only once the run ends (promote_next / explicit start).
        if self.current_stage and self.current_job is not None:
            if emit_payloads:
                self._emit_job_payloads()
            return
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
                    if not self.current_stage and self.current_job is None:
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
        if self.current_stage:
            # A job already holds the single active slot. If it is this same
            # job, refuse the duplicate start; otherwise it waits in order.
            if self.current_job is not None and self.current_job.job_id == job.job_id:
                self._respond(request_id, command, job_id=job.job_id, already_running=True)
                return
            if hasattr(self, "queue") and self.queue is not None:
                position = self.electron_backend.enqueue_job(self.queue, job.job_id)
                self._emit({"event": "job_queued", "job_id": job.job_id, "position": position})
                self._push_queue()
                self._emit_job_payloads()
                self._respond(request_id, command, job_id=job.job_id, queued=True, position=position)
                return
            # Queue unavailable (startup failure): refuse rather than double-run.
            self._respond(request_id, command, job_id=job.job_id, already_running=True)
            return
        # Nothing is processing: release any stale active slot left by a prior
        # crash, claim the single slot, and start this job immediately.
        # ``_job_for`` intentionally does not re-point an idle sidecar that is
        # still holding a previously viewed/completed job.  Starting a
        # different queued job must activate the requested job before the
        # controller runs, otherwise the queue claims one id while the
        # controller processes the stale ``current_job``.
        if self.current_job is None or self.current_job.job_id != job.job_id:
            self._activate_job(job, emit_payloads=False)
        if hasattr(self, "queue"):
            self.queue.finish_active()
            self.electron_backend.start_or_enqueue(self.queue, job.job_id)
            self._push_queue()
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

    def _view_job(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Fetch and emit one job's workspace payloads WITHOUT re-pointing the
        sidecar's current job.

        The UI tracks the job being viewed separately from the job being
        processed. While a pipeline owns the single active slot, ``get_job``
        must keep refusing to swap ``current_job`` (that would corrupt the
        running job's events), so viewing any other job needs a fetch that
        leaves the processing state untouched. The renderer calls this when
        the user selects a job; the payloads are stamped with the requested
        job id and the running job's live events keep streaming under its own.
        """
        job = self._job_for(payload)
        self._emit({"event": "jobs_changed", "jobs": [self._summary(item) for item in self._job_objects()]})
        slides = self._slides(job)
        self._emit({"event": "slides_changed", "job": job.job_id, **self._slide_payload(job, slides)})
        self._emit({"event": "transcript_changed", "job": job.job_id, **self._transcript(job)})
        self._emit_pipeline(job)
        if hasattr(self, "study_service"):
            self._emit_study_changed(job)
        if job.get_stage_status("Export") == "completed":
            self._emit({
                "event": "export_done",
                "job": job.job_id,
                "files": self._export_files(job),
                "meta": f"{len(self._export_files(job))} files written to the Study Pack export folder",
            })
        self._respond(request_id, command, ok=True, job_id=job.job_id, job=self._summary(job))
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
        # Support diagnostics consume the exact same packaged health result as
        # startup and the build-time self-test. Do not maintain a parallel set
        # of runtime probes with different pass/fail semantics.
        diag["packaged_health"] = self._last_health or self._packaged_self_test(include_sidecar=False)
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

    def _emit_study_changed(self, job: Any | None = None) -> None:
        """Emit the study_changed overview payload for a job."""
        job = job or self.current_job
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
        try:
            job = self._job_for(payload)
        except (FileNotFoundError, RuntimeError):
            self._emit({"event": "ai_token",
                        "text": "Open or process a lecture first, then ask away."})
            self._emit({"event": "ai_done"})
            self._respond(request_id, command, ok=True, job_id="")
            return
        segments = self.transcript_store.load_working(job.paths) or []
        try:
            study_content = self.study_v2.ensure_study_v2(job)
        except Exception:
            study_content = self.study_v2.load_content(job)
        o = self._ollama_settings()
        local_ready = bool(o.get("enabled") and o.get("model"))
        if not local_ready:
            answer = self.electron_study.builtin_answer(prompt, segments, study_content)
            self._emit({"event": "ai_token", "job": job.job_id, "text": answer})
            self._emit({"event": "ai_sources",
                        "job": job.job_id,
                        "sources": self.electron_study.builtin_sources(
                            prompt, segments, content=study_content)})
            self._emit({"event": "ai_done", "job": job.job_id})
            self._emit({"event": "ai_status",
                        "job": job.job_id,
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
        self._emit({"event": "ai_status", "job": job.job_id,
                    "label": "Thinking…", "model": o.get("model")})
        worker = StudyAssistantWorker(
            "chat", transcript_text, o, history=[], question=prompt, count=5)
        self._ai_worker = worker

        def ok(task, result):
            answer = (result or {}).get("answer", "") if isinstance(result, dict) else ""
            answer = answer or "I couldn't find an answer in the transcript."
            self._emit({"event": "ai_token", "job": job.job_id, "text": answer})
            self._emit({"event": "ai_sources",
                        "job": job.job_id,
                        "sources": self.electron_study.builtin_sources(
                            prompt, segments, content=study_content)})
            self._emit({"event": "ai_done", "job": job.job_id})
            self._emit({"event": "ai_status",
                        "job": job.job_id,
                        "label": self.study_presets.PROVIDER_LOCAL, "model": o.get("model")})
            try:
                self.study_service.append_chat_message(job, "user", prompt)
                self.study_service.append_chat_message(job, "assistant", answer)
            except Exception:
                pass

        def fail(kind, message, details):
            self._emit({"event": "ai_token", "job": job.job_id, "text": f"⚠ {message}"})
            self._emit({"event": "ai_done", "job": job.job_id})
            self._emit({"event": "ai_status", "job": job.job_id,
                        "label": "AI error", "model": o.get("model")})

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
    # Study V2: grounded concepts, mastery, quick study
    # ------------------------------------------------------------------ #
    def _study_v2_status(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Return the full Study V2 snapshot: content, progress, summary, and
        the Rust core diagnostic. Ensures Study V2 content exists (old-job
        migration) before returning."""
        job = self._job_for(payload)
        try:
            content = self.study_v2.ensure_study_v2(job)
        except Exception as exc:  # noqa: BLE001 - never crash on bad study data
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error=f"Study data could not be loaded: {exc}")
            return
        progress = self.study_v2.load_progress(job)
        summary = self.study_v2.calculate_study_summary(job)
        core_info = self.study_v2.study_core_info()
        self._respond(request_id, command, ok=True, job_id=job.job_id,
                      content=content, progress=progress, summary=summary,
                      core_info=core_info)

    def _study_v2_record_flashcard(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Record a flashcard review result through the Rust core."""
        job = self._job_for(payload)
        card_id = str(payload.get("card_id") or "")
        concept_ids = payload.get("concept_ids") or []
        if isinstance(concept_ids, str):
            try:
                concept_ids = json.loads(concept_ids)
            except json.JSONDecodeError:
                concept_ids = []
        correct = bool(payload.get("correct"))
        if not card_id:
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error="card_id is required")
            return
        try:
            progress = self.study_v2.record_flashcard_result(
                job, card_id, concept_ids, correct)
        except Exception as exc:  # noqa: BLE001 - never crash on bad progress
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error=f"Could not record flashcard result: {exc}")
            return
        summary = self.study_v2.calculate_study_summary(job)
        self._respond(request_id, command, ok=True, job_id=job.job_id,
                      progress=progress, summary=summary)

    def _study_v2_record_quiz(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Record a quiz answer result through the Rust core."""
        job = self._job_for(payload)
        question_id = str(payload.get("question_id") or "")
        concept_ids = payload.get("concept_ids") or []
        if isinstance(concept_ids, str):
            try:
                concept_ids = json.loads(concept_ids)
            except json.JSONDecodeError:
                concept_ids = []
        correct = bool(payload.get("correct"))
        if not question_id:
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error="question_id is required")
            return
        try:
            progress = self.study_v2.record_quiz_result(
                job, question_id, concept_ids, correct)
        except Exception as exc:  # noqa: BLE001 - never crash on bad progress
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error=f"Could not record quiz result: {exc}")
            return
        summary = self.study_v2.calculate_study_summary(job)
        self._respond(request_id, command, ok=True, job_id=job.job_id,
                      progress=progress, summary=summary)

    def _study_v2_quick_study(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Build a Quick Study session using the Rust core."""
        job = self._job_for(payload)
        try:
            session = self.study_v2.build_quick_study_session(job)
        except Exception as exc:  # noqa: BLE001 - never crash on bad study data
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error=f"Could not build Quick Study: {exc}")
            return
        self._respond(request_id, command, ok=True, job_id=job.job_id,
                      session=session)

    def _study_v2_summary(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Return the study summary (mastery counts, progress percent)."""
        job = self._job_for(payload)
        try:
            summary = self.study_v2.calculate_study_summary(job)
        except Exception as exc:  # noqa: BLE001 - never crash on bad study data
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error=f"Could not calculate study summary: {exc}")
            return
        self._respond(request_id, command, ok=True, job_id=job.job_id,
                      summary=summary)

    def _study_v2_edit(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Edit one concept/card/question."""
        job = self._job_for(payload)
        kind = str(payload.get("kind") or "")
        item_id = str(payload.get("id") or "")
        ok = False
        if kind == "concept":
            ok = self.study_v2.update_concept(
                job, item_id,
                title=payload.get("title"),
                explanation=payload.get("explanation"))
        elif kind == "flashcard":
            ok = self.study_v2.update_flashcard(
                job, item_id,
                front=payload.get("front"),
                back=payload.get("back"))
        elif kind == "quiz":
            ok = self.study_v2.update_quiz_question(
                job, item_id,
                question=payload.get("question"),
                explanation=payload.get("explanation"))
        self._respond(request_id, command, ok=ok, job_id=job.job_id, kind=kind, id=item_id)

    def _study_v2_delete(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Delete one concept/card/question."""
        job = self._job_for(payload)
        kind = str(payload.get("kind") or "")
        item_id = str(payload.get("id") or "")
        ok = False
        if kind == "concept":
            ok = self.study_v2.delete_concept(job, item_id)
        elif kind == "flashcard":
            ok = self.study_v2.delete_flashcard(job, item_id)
        elif kind == "quiz":
            ok = self.study_v2.delete_quiz_question(job, item_id)
        self._respond(request_id, command, ok=ok, job_id=job.job_id, kind=kind, id=item_id)

    def _study_v2_regenerate(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        """Regenerate one concept/card/question (targeted, not the whole pack)."""
        job = self._job_for(payload)
        kind = str(payload.get("kind") or "")
        item_id = str(payload.get("id") or "")
        # For V1, regeneration falls back to deterministic content for the
        # whole pack (the AI path is wired through the existing async worker).
        # A targeted single-item regeneration is a future refinement.
        try:
            content = self.study_v2.ensure_study_v2(job)
        except Exception as exc:  # noqa: BLE001 - never crash on bad study data
            self._respond(request_id, command, ok=False, job_id=job.job_id,
                          error=f"Could not regenerate: {exc}")
            return
        self._respond(request_id, command, ok=True, job_id=job.job_id,
                      kind=kind, id=item_id, content=content)

    # ------------------------------------------------------------------ #
    # Phase 9: paste link / yt-dlp
    # ------------------------------------------------------------------ #
    def _media_link_support(self, request_id: str | None, command: str) -> None:
        available = self.media_fetch.is_available()
        version = self.media_fetch.version()
        reason = "" if available else "Link importing is unavailable because the bundled yt-dlp runtime could not load."
        self._emit({
            "event": "media_link_state",
            "available": available,
            "version": version,
            "reason": reason,
        })
        self._respond(request_id, command, available=available, version=version, reason=reason)

    def _probe_media_url(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        raw_urls = payload.get("urls")
        if isinstance(raw_urls, str):
            raw_urls = raw_urls.splitlines()
        if not isinstance(raw_urls, list):
            raw_urls = [payload.get("url")]
        urls = []
        for value in raw_urls:
            url = str(value or "").strip()
            if url and url not in urls:
                urls.append(url)
        if not urls or any(not self.media_fetch.looks_like_url(url) for url in urls):
            error = "Enter one full http(s) link per line."
            self._emit({"event": "media_probe", "ok": False, "error": error})
            self._respond(request_id, command, ok=False, error=error)
            return

        def worker():
            items = []
            for url in urls:
                try:
                    info = self.media_fetch.MediaFetcher().probe(url)
                    items.append({"ok": True, "url": url, **info})
                except self.media_fetch.MediaFetchError as exc:
                    items.append({"ok": False, "url": url, "error": str(exc)})
                except Exception as exc:  # noqa: BLE001 - never kill the thread
                    items.append({"ok": False, "url": url, "error": str(exc)[:300]})
            payload_out = {
                "ok": all(item.get("ok") for item in items),
                "items": items,
                "count": len(items),
            }
            if len(items) == 1:
                payload_out.update(items[0])
            self._emit({"event": "media_probe", **payload_out})

        threading.Thread(target=worker, daemon=True,
                         name="lp-media-probe").start()
        self._respond(request_id, command, ok=True)

    def _downloads_dir(self) -> str:
        d = self.data_dir / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _downloads_state_path(self) -> Path | None:
        data_dir = getattr(self, "data_dir", None)
        return Path(data_dir) / "downloads-state.json" if data_dir is not None else None

    def _persist_downloads_locked(self) -> None:
        """Atomically persist public download state while _download_lock is held."""
        path = self._downloads_state_path()
        if path is None:
            return
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "schema_version": 1,
            "downloads": [dict(self._downloads[item_id])
                          for item_id in self._download_order
                          if item_id in self._downloads],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
                                 encoding="utf-8")
            os.replace(temporary, path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _load_download_state(self) -> None:
        """Restore downloads; crash-active rows become explicit Retry states."""
        path = self._downloads_state_path()
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("downloads", []) if isinstance(payload, dict) else []
        except (OSError, ValueError):
            return
        if not isinstance(rows, list):
            return
        changed = False
        with self._download_lock:
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                item_id = str(raw.get("id") or raw.get("download_id") or "")
                url = str(raw.get("url") or "")
                if not item_id or not url or item_id in self._downloads:
                    continue
                item = {key: value for key, value in raw.items()
                        if key in {"id", "download_id", "url", "title", "status",
                                   "legacy_status", "progress", "pct", "eta", "speed",
                                   "error", "name", "path", "downloaded", "total"}}
                item["id"] = item_id
                item["download_id"] = item_id
                raw_status = str(item.get("legacy_status") or item.get("status") or "failed")
                status = {
                    "running": "downloading",
                    "completed": "complete",
                }.get(raw_status, raw_status)
                item["status"] = status
                if "pct" not in item:
                    item["pct"] = int(item.get("progress", 0) or 0)
                if status in {"waiting", "downloading"}:
                    item.update({
                        "status": "failed",
                        "eta": 0,
                        "speed": 0,
                        "error": "Download was interrupted when LecturePack closed. Choose Retry to continue.",
                    })
                    changed = True
                elif status not in {"complete", "failed", "cancelled"}:
                    item["status"] = "failed"
                    item["error"] = "Download state could not be restored. Choose Retry to start again."
                    changed = True
                self._downloads[item_id] = item
                self._download_order.append(item_id)
            if changed:
                self._persist_downloads_locked()

    @staticmethod
    def _download_ui_status(status: Any) -> str:
        return {
            "downloading": "running",
            "complete": "completed",
            "cancelled": "failed",
        }.get(str(status or "failed"), str(status or "failed"))

    def _download_public(self, item: dict[str, Any]) -> dict[str, Any]:
        public = {key: value for key, value in item.items() if key not in {"path"}}
        item_id = str(item.get("download_id") or item.get("id") or "")
        progress = int(item.get("progress", item.get("pct", 0)) or 0)
        legacy_status = str(item.get("status") or "failed")
        public.update({
            "id": item_id,
            "download_id": item_id,
            "status": self._download_ui_status(legacy_status),
            "legacy_status": legacy_status,
            "progress": max(0, min(100, progress)),
            "pct": max(0, min(100, progress)),
            "eta_seconds": int(item.get("eta", 0) or 0),
            "state": self._download_ui_status(legacy_status),
        })
        return public

    def _download_snapshot(self) -> list[dict[str, Any]]:
        with self._download_lock:
            return [self._download_public(dict(self._downloads[item_id]))
                    for item_id in self._download_order if item_id in self._downloads]

    def _emit_downloads(self) -> None:
        self._emit({"event": "downloads_changed", "downloads": self._download_snapshot()})

    def _get_media_downloads(self, request_id: str | None, command: str) -> None:
        self._emit_downloads()
        self._respond(request_id, command, downloads=self._download_snapshot())

    def _cancel_media_url(self, request_id: str | None, command: str,
                          payload: dict[str, Any] | None = None) -> None:
        download_id = str((payload or {}).get("download_id") or "")
        cancelled = False
        with self._download_lock:
            targets = [download_id] if download_id else list(self._download_order)
            for item_id in targets:
                item = self._downloads.get(item_id)
                if not item or item.get("status") not in {"waiting", "downloading"}:
                    continue
                if item.get("status") == "waiting":
                    item["status"] = "cancelled"
                    cancelled = True
                event = self._download_cancel.get(item_id)
                if event is not None:
                    event.set()
                    cancelled = True
            self._persist_downloads_locked()
        self._emit_downloads()
        self._respond(request_id, command, ok=True, cancelled=cancelled,
                      downloads=self._download_snapshot())

    def _remove_media_download(self, request_id: str | None, command: str,
                               payload: dict[str, Any]) -> None:
        download_id = str(payload.get("download_id") or "")
        removed = False
        with self._download_lock:
            item = self._downloads.get(download_id)
            if item and item.get("status") in {"waiting", "failed", "cancelled", "complete"}:
                self._downloads.pop(download_id, None)
                if download_id in self._download_order:
                    self._download_order.remove(download_id)
                removed = True
            if removed:
                self._persist_downloads_locked()
        self._emit_downloads()
        self._respond(request_id, command, ok=True, removed=removed,
                      downloads=self._download_snapshot())

    def _retry_media_download(self, request_id: str | None, command: str,
                              payload: dict[str, Any]) -> None:
        download_id = str(payload.get("download_id") or "")
        retried = False
        with self._download_lock:
            item = self._downloads.get(download_id)
            if item and item.get("status") in {"failed", "cancelled"}:
                item.update({"status": "waiting", "pct": 0, "eta": 0,
                             "progress": 0, "speed": 0, "error": ""})
                retried = True
            if retried:
                self._persist_downloads_locked()
        if retried:
            self._start_download_worker()
        self._emit_downloads()
        self._respond(request_id, command, ok=True, retried=retried,
                      downloads=self._download_snapshot())

    def _clear_media_downloads(self, request_id: str | None, command: str) -> None:
        with self._download_lock:
            removable = [item_id for item_id in self._download_order
                         if self._downloads.get(item_id, {}).get("status") == "complete"]
            for item_id in removable:
                self._downloads.pop(item_id, None)
                self._download_order.remove(item_id)
            if removable:
                self._persist_downloads_locked()
        self._emit_downloads()
        self._respond(request_id, command, ok=True, cleared=len(removable),
                      downloads=self._download_snapshot())

    def _import_media_url(self, request_id: str | None, command: str, payload: dict[str, Any]) -> None:
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raw_items = [{"url": payload.get("url"), "title": payload.get("title")}]
        added = []
        with self._download_lock:
            for raw in raw_items:
                if not isinstance(raw, dict):
                    raw = {"url": raw}
                url = str(raw.get("url") or raw.get("webpage_url") or "").strip()
                if not self.media_fetch.looks_like_url(url):
                    continue
                item_id = f"download-{time.time_ns()}-{len(added)}"
                item = {
                    "id": item_id,
                    "download_id": item_id,
                    "url": url,
                    "title": str(raw.get("title") or "Lecture download"),
                    "status": "waiting",
                    "pct": 0,
                    "progress": 0,
                    "eta": 0,
                    "speed": 0,
                    "error": "",
                }
                self._downloads[item_id] = item
                self._download_order.append(item_id)
                added.append(self._download_public(dict(item)))
            if added:
                self._persist_downloads_locked()
        if not added:
            error = "Enter one full http(s) link per line."
            self._respond(request_id, command, ok=False, error=error)
            return
        self._emit_downloads()
        self._start_download_worker()
        self._respond(request_id, command, ok=True, started=True,
                      count=len(added), downloads=added)

    def _start_download_worker(self) -> None:
        with self._download_lock:
            if self._download_worker_running:
                return
            self._download_worker_running = True
        threading.Thread(target=self._download_worker, daemon=True,
                         name="lp-media-download-queue").start()

    def _next_waiting_download(self) -> dict[str, Any] | None:
        with self._download_lock:
            for item_id in self._download_order:
                item = self._downloads.get(item_id)
                if item and item.get("status") == "waiting":
                    item["status"] = "downloading"
                    event = threading.Event()
                    self._download_cancel[item_id] = event
                    self._persist_downloads_locked()
                    return dict(item)
        return None

    def _download_worker(self) -> None:
        while not self._shutting_down:
            item = self._next_waiting_download()
            if item is None:
                with self._download_lock:
                    self._download_worker_running = False
                    # Close the race where a command queued an item between the
                    # empty scan and clearing this flag.
                    has_waiting = any(value.get("status") == "waiting"
                                      for value in self._downloads.values())
                    if has_waiting:
                        self._download_worker_running = True
                        continue
                return
            item_id = item["id"]
            cancel = self._download_cancel[item_id]
            self._emit_downloads()

            def progress(update: dict[str, Any]) -> None:
                with self._download_lock:
                    current = self._downloads.get(item_id)
                    if not current:
                        return
                    current.update({key: update.get(key, current.get(key))
                                    for key in ("status", "pct", "eta", "speed", "downloaded", "total")})
                    current["status"] = "downloading"
                    current["progress"] = int(current.get("pct", 0) or 0)
                    progress_payload = dict(update)
                    progress_payload.update({
                        "download_id": item_id,
                        "status": "running",
                        "progress": current["progress"],
                        "eta_seconds": int(current.get("eta", 0) or 0),
                    })
                self._emit({"event": "media_progress", **progress_payload})
                self._emit_downloads()

            try:
                destination = Path(self._downloads_dir()) / item_id
                destination.mkdir(parents=True, exist_ok=True)
                path = self.media_fetch.MediaFetcher().download(
                    item["url"], str(destination), progress_cb=progress,
                    cancel_check=cancel.is_set, title=item.get("title") or None)
                if cancel.is_set():
                    raise self.media_fetch.MediaFetchCancelled()
                with self._download_lock:
                    current = self._downloads.get(item_id)
                    if current:
                        current.update({"status": "complete", "pct": 100,
                                        "progress": 100, "eta": 0, "path": path,
                                        "name": os.path.basename(path)})
                        self._persist_downloads_locked()
                payload_out = {"ok": True, "download_id": item_id,
                               "name": os.path.basename(path), "status": "completed",
                               "progress": 100, "eta_seconds": 0,
                               "title": item.get("title", "")}
                # The existing normal import path remains the only way a
                # downloaded recording becomes a LecturePack job.
                QTimer.singleShot(0, self._poll_timer,
                                  lambda p=path, t=item.get("title"): self._import_video(None, "import_media_url",
                                                                                         {"path": p, "title": t}))
            except self.media_fetch.MediaFetchCancelled:
                with self._download_lock:
                    if item_id in self._downloads:
                        self._downloads[item_id]["status"] = "cancelled"
                        self._persist_downloads_locked()
                payload_out = {"ok": False, "cancelled": True,
                               "download_id": item_id, "status": "failed",
                               "legacy_status": "cancelled", "progress": 0,
                               "title": item.get("title", "")}
            except Exception as exc:  # media_fetch already makes yt-dlp errors friendly
                with self._download_lock:
                    if item_id in self._downloads:
                        self._downloads[item_id].update({"status": "failed",
                                                        "error": str(exc)[:300]})
                        self._persist_downloads_locked()
                payload_out = {"ok": False, "error": str(exc)[:300],
                               "download_id": item_id, "status": "failed",
                               "progress": int(item.get("pct", 0) or 0),
                               "title": item.get("title", "")}
            finally:
                with self._download_lock:
                    self._download_cancel.pop(item_id, None)
            self._emit({"event": "media_done", **payload_out})
            self._emit_downloads()
        with self._download_lock:
            self._download_worker_running = False

    def _processing_workers_running(self) -> bool:
        """Keep QThread/QProcess owners alive while a cancellation drains.

        ``JobController.cancel`` deliberately clears its active-stage set as
        soon as cancellation is requested, but Qt workers and QProcesses may
        still be delivering their final signals. Quitting QCoreApplication in
        that window can make PySide6 destroy a live worker and abort the
        sidecar. The host still owns the final timeout/tree-kill guard; this
        short drain avoids that race when the engine can finish normally.
        """
        with self._download_lock:
            if self._download_worker_running:
                return True
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
        with self._download_lock:
            for event in self._download_cancel.values():
                event.set()
            for item in self._downloads.values():
                if item.get("status") == "waiting":
                    item["status"] = "cancelled"
            self._persist_downloads_locked()
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
            if self._is_demo_job(self.current_job) and getattr(self, "_demo_session", None) is not None:
                # Let the bridge/UI consume the terminal pipeline event first,
                # then remove the temporary demo from the normal library.
                QTimer.singleShot(0, lambda: self._cleanup_demo_session("tour_complete"))
            # Release the active slot and launch the next queued job (FIFO).
            self._promote_next()
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
        if self.current_job is None:
            return
        self._emit({
            "event": "log_line",
            "job": self.current_job.job_id,
            "tag": "[Transcribe]",
            "color": "var(--orange-ink)",
            "text": str(segment.get("text", "")),
        })
        # Live transcription progress: whisper streams segment timestamps but
        # emits no stage-percent events during Transcribe, so the UI only saw
        # stage-boundary jumps (a long lecture sat at the pre-transcribe 43%
        # the whole time). Derive a real, monotonic percent from the latest
        # segment's end time against the known duration. This only reads the
        # existing live stream -- it never changes the transcription engine.
        if self.current_stage == "Transcribe":
            duration = float((self.current_job.source or {}).get("duration", 0.0) or 0.0)
            end_ms = float(segment.get("end_ms") or 0.0)
            if duration > 0 and end_ms > 0:
                percent = max(0, min(99, round(end_ms / (duration * 1000.0) * 100)))
                if percent > self.stage_percent.get("Transcribe", 0):
                    self.stage_percent["Transcribe"] = percent
                    self._emit_status("Processing", detail=f"Transcribe - {percent}%")
                    self._emit_pipeline()

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
            demo_failed = self._is_demo_job(self.current_job) and getattr(self, "_demo_session", None) is not None
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
            if demo_failed:
                QTimer.singleShot(0, lambda: self._cleanup_demo_session("tour_failed"))

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

    def _emit_pipeline(self, job: Any | None = None) -> None:
        job = job or self.current_job
        if job is None:
            return
        same_job = job is self.current_job
        active = self.current_stage if same_job else ""
        percent = self.stage_percent if same_job else {}
        self._emit({
            "event": "pipeline_changed",
            "job": job.job_id,
            "title": job.manifest.get("title", "Lecture"),
            "meta": f"{self._summary(job)['meta']} - {self._job_percent(job)}%",
            "stages": self._pipeline_stages(job, active, percent),
        })

    def _pipeline_stages(
        self,
        job: Any,
        active_stage: str | None = None,
        stage_percent: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        # For a job other than the one currently processing, never borrow the
        # live stage marker or percentages of the running job.
        active = self.current_stage if active_stage is None else active_stage
        percent_map = self.stage_percent if stage_percent is None else stage_percent
        stages = []
        for index, stage in enumerate(STAGES):
            status = job.get_stage_status(stage)
            if status == "completed":
                state = "done"
                percent = 100
            elif status == "failed":
                state = "error"
                percent = percent_map.get(stage, 0)
            elif stage == active or (not active and status == "running"):
                state = "active"
                percent = percent_map.get(stage, 0)
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
    parser.add_argument("--self-test", action="store_true", help="Run the packaged health contract and exit")
    parser.add_argument(
        "--self-test-fault",
        choices=("study_core", "yt_dlp", "js_runtime"),
        default="",
        help="Release-validator-only injection used with --self-test",
    )
    return parser.parse_args(argv)


def main() -> int:
    # Windows pipes default to the ANSI codepage, which corrupts native paths
    # containing apostrophes or Unicode characters before the JSONL layer ever
    # sees them. Force UTF-8 on all three streams so a real path arrives at the
    # import command unchanged.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - not all environments allow reconfigure
            pass
    args = _parse_args(sys.argv[1:])
    app = QCoreApplication(sys.argv)
    sidecar = Sidecar(args, app)
    if args.self_test:
        result = sidecar._packaged_self_test()
        sidecar._emit({"event": "self_test", **result})
        return 0 if result["passed"] else 1
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
