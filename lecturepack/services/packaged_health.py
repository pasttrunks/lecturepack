"""Authoritative health checks for the packaged Electron sidecar.

The release validator, startup gate, and support diagnostics all consume the
same structured result.  Checks use the paths already selected by the sidecar;
they never search PATH or a developer checkout.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from lecturepack.infrastructure.runtime_validation import RuntimeValidator
from lecturepack.infrastructure.whisper_path_staging import WhisperPathStaging
from lecturepack.services.first_run_checklist import data_directory_writable


CHECK_ORDER: tuple[str, ...] = (
    "data_directory",
    "ffmpeg",
    "ffprobe",
    "whisper_runtime",
    "whisper_smoke",
    "bundled_model",
    "study_core",
    "yt_dlp",
    "controller",
)

_FATAL_AT_STARTUP = frozenset({
    "data_directory",
    "ffmpeg",
    "ffprobe",
    "whisper_runtime",
    "whisper_smoke",
    "bundled_model",
    "controller",
})


def _result(
    check_id: str,
    ok: bool,
    title: str,
    detail: str,
    *,
    technical: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "ok": bool(ok),
        "required": True,
        "fatal_at_startup": check_id in _FATAL_AT_STARTUP,
        "title": title,
        "detail": detail,
        "technical": technical,
    }


def _readable_file(path: Path) -> tuple[bool, str]:
    try:
        if not path.is_file():
            return False, "file is missing"
        if path.stat().st_size <= 0:
            return False, "file is empty"
        with path.open("rb") as handle:
            handle.read(1)
        return True, "readable"
    except OSError as error:
        return False, str(error)


def _program_check(check_id: str, path: Path, title: str) -> dict[str, Any]:
    readable, reason = _readable_file(path)
    if not readable:
        return _result(
            check_id,
            False,
            title,
            f"LecturePack could not start its bundled {check_id} runtime.",
            technical=f"{path.name}: {reason}",
        )
    smoke = RuntimeValidator(timeout_ms=5_000).run(str(path), ["-version"])
    return _result(
        check_id,
        smoke.ok,
        title,
        f"Bundled {check_id} started successfully." if smoke.ok
        else f"LecturePack could not start its bundled {check_id} runtime.",
        technical=(
            f"reason={smoke.reason}; exit_code={smoke.exit_code}; "
            f"duration_ms={smoke.duration_ms}; stderr={smoke.stderr[-500:]}"
        ),
    )


def _whisper_runtime_check(release_dir: Path, executable: Path) -> dict[str, Any]:
    required = [
        executable,
        release_dir / "ggml-base.dll",
        release_dir / "ggml.dll",
        release_dir / "whisper.dll",
    ]
    cpu_dlls = sorted(release_dir.glob("ggml-cpu-*.dll"))
    failures = []
    for path in required:
        readable, reason = _readable_file(path)
        if not readable:
            failures.append(f"{path.name}: {reason}")
    if not cpu_dlls:
        failures.append("ggml-cpu-*.dll: no CPU implementation was bundled")
    else:
        for path in cpu_dlls:
            readable, reason = _readable_file(path)
            if not readable:
                failures.append(f"{path.name}: {reason}")
    ok = not failures
    return _result(
        "whisper_runtime",
        ok,
        "Speech runtime unavailable",
        "Bundled Whisper runtime files are ready." if ok
        else "LecturePack could not load its bundled Whisper runtime.",
        technical="; ".join(failures) if failures else f"{len(cpu_dlls)} CPU implementation DLL(s) available",
    )


def _whisper_smoke_check(executable: Path, model: Path, smoke_wav: Path) -> dict[str, Any]:
    staging = WhisperPathStaging(model, smoke_wav, smoke_wav.parent / "health-output" / "transcript")
    try:
        staged_model, staged_wav, _output = staging.prepare()
        smoke = RuntimeValidator(timeout_ms=15_000).run(
            str(executable),
            ["-m", staged_model, "-f", staged_wav, "-t", "1", "-nt"],
        )
    except (OSError, RuntimeError, FileNotFoundError) as error:
        return _result(
            "whisper_smoke",
            False,
            "Speech runtime unavailable",
            "LecturePack could not complete its bundled Whisper smoke test.",
            technical=f"{type(error).__name__}: {error}",
        )
    finally:
        staging.cleanup()
    return _result(
        "whisper_smoke",
        smoke.ok,
        "Speech runtime unavailable",
        "Bundled Whisper smoke test passed." if smoke.ok
        else "LecturePack could not complete its bundled Whisper smoke test.",
        technical=(
            f"reason={smoke.reason}; exit_code={smoke.exit_code}; "
            f"duration_ms={smoke.duration_ms}; stderr={smoke.stderr[-500:]}"
        ),
    )


def run_packaged_health(
    *,
    runtime_root: str | Path,
    data_dir: str | Path,
    controller: Any,
    study_core_info: Callable[[], dict[str, Any]],
    media_available: Callable[[], bool],
    media_version: Callable[[], str],
    smoke_wav: str | Path | None = None,
) -> dict[str, Any]:
    """Run the single packaged release/startup health sequence."""
    root = Path(runtime_root)
    data_path = Path(data_dir)
    release_dir = root / "bin" / "Release"
    ffmpeg = root / "bin" / "ffmpeg.exe"
    ffprobe = root / "bin" / "ffprobe.exe"
    whisper = release_dir / "whisper-cli.exe"
    model = root / "models" / "ggml-base.en.bin"
    smoke_path = Path(smoke_wav) if smoke_wav is not None else root / "smoke" / "runtime-smoke.wav"

    writable = data_directory_writable(data_path)
    data_check = _result(
        "data_directory",
        bool(writable["writable"]),
        "Storage folder unavailable",
        "LecturePack can write to its data folder." if writable["writable"]
        else "LecturePack cannot write to its data folder.",
        technical=str(writable.get("detail", "")),
    )

    runtime_check = _whisper_runtime_check(release_dir, whisper)
    model_ok, model_reason = _readable_file(model)
    model_check = _result(
        "bundled_model",
        model_ok,
        "Speech model unavailable",
        "Bundled speech model is readable." if model_ok
        else "LecturePack could not read its bundled speech model.",
        technical=f"{model.name}: {model_reason}",
    )

    with ThreadPoolExecutor(max_workers=3) as pool:
        ffmpeg_future = pool.submit(_program_check, "ffmpeg", ffmpeg, "Media runtime unavailable")
        ffprobe_future = pool.submit(_program_check, "ffprobe", ffprobe, "Media inspection unavailable")
        whisper_future = pool.submit(_whisper_smoke_check, whisper, model, smoke_path)
        ffmpeg_check = ffmpeg_future.result()
        ffprobe_check = ffprobe_future.result()
        whisper_check = whisper_future.result()

    try:
        core_info = study_core_info()
    except (ImportError, OSError, SystemError, ValueError, TypeError) as error:
        core_info = {"available": False, "implementation": "python", "error": f"{type(error).__name__}: {error}"}
    core_ok = bool(core_info.get("available") is True and core_info.get("implementation") == "rust")
    core_check = _result(
        "study_core",
        core_ok,
        "Native Study engine unavailable",
        "Rust Study Core is available." if core_ok
        else "LecturePack will use the slower Python Study fallback.",
        technical=str(core_info.get("error") or core_info),
    )

    try:
        yt_available = bool(media_available())
        yt_version = media_version() if yt_available else ""
    except (ImportError, OSError, SystemError, AttributeError) as error:
        yt_available = False
        yt_version = f"{type(error).__name__}: {error}"
    yt_check = _result(
        "yt_dlp",
        yt_available,
        "Link importing unavailable",
        "Bundled yt-dlp is available." if yt_available
        else "Paste Link is unavailable because yt-dlp could not load.",
        technical=f"version={yt_version}" if yt_available else yt_version or "yt-dlp import failed",
    )

    controller_ok = controller is not None
    controller_check = _result(
        "controller",
        controller_ok,
        "Processing service unavailable",
        "LecturePack processing controller initialized." if controller_ok
        else "LecturePack could not initialize its processing service.",
    )

    by_id = {
        item["id"]: item for item in (
            data_check,
            ffmpeg_check,
            ffprobe_check,
            runtime_check,
            whisper_check,
            model_check,
            core_check,
            yt_check,
            controller_check,
        )
    }
    checks = [by_id[check_id] for check_id in CHECK_ORDER]
    return {
        "passed": all(check["ok"] for check in checks if check["required"]),
        "startup_ok": all(check["ok"] for check in checks if check["fatal_at_startup"]),
        "checks": checks,
    }
