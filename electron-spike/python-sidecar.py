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
import shutil
import sys
import threading
import time
from typing import Any

from PySide6.QtCore import QCoreApplication, QProcess, QTimer


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
            from lecturepack.services import transcript_store

            self.JobController = JobController
            self.ConfigManager = ConfigManager
            self.FileManager = FileManager
            self.Job = Job
            self.transcript_store = transcript_store
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

    def _copy_demo_if_needed(self, source: Path) -> Path:
        target = self.data_dir / "demo-inputs" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve() and not target.is_file():
            shutil.copy2(source, target)
        return target if target.is_file() else source

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
        self._emit_status("Cancelled", job=job, detail="Processing cancelled")
        self._emit_job_payloads()
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
        elif key == "engine":
            normalized = str(value or "cpu").strip().lower()
            if normalized not in {"cpu", "auto"}:
                normalized = "cpu"
            if hasattr(self, "config"):
                self.config.set("engine", normalized)
            if job is not None:
                job.settings.setdefault("whisper", {})["engine"] = normalized
        elif key == "transcription_backend":
            normalized = str(value or "local-whispercpp").strip()
            if normalized != "local-whispercpp":
                applied = False
                normalized = "local-whispercpp"
            if hasattr(self, "config"):
                self.config.set("transcription_backend", normalized)
            if job is not None:
                job.settings.setdefault("whisper", {})["transcription_backend"] = normalized
        else:
            # Secondary settings are intentionally outside Phase 8. Treat them
            # as harmless acknowledgements so the reused UI cannot create a
            # storm of unsupported-command errors.
            applied = False

        if job is not None and key in {"slide_detection_preset", "engine", "transcription_backend"}:
            job.save()
        self._emit({
            "event": "settings_changed",
            "job": job.job_id if job is not None else "",
            "key": key,
            "value": normalized,
            "applied": applied,
        })
        self._respond(request_id, command, key=key, value=normalized, applied=applied)

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

    def _start_automatic_export(self) -> None:
        if self.controller is None or self.current_job is None or self._shutting_down:
            return
        self.current_stage = "Export"
        self.controller.export_now()

    def _on_pipeline_failed(self, error: str) -> None:
        if self.current_job is not None:
            self.current_stage = ""
            self._emit_status("Failed", detail=str(error or "Processing failed"))
            self._emit_job_payloads()

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
