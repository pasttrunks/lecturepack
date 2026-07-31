"""First-run checklist verdict service — exactly the five D-13 items.

Backend decides, UI renders (established pattern, `01-CONTEXT.md`
`<code_context>` "Established Patterns"): every verdict in this module is
computed in Python from `RuntimeBootstrapResult.components` evidence plus two
small, injectable, unit-testable local predicates. The UI (Plan 01-07) only
renders the resulting `{"id", "verdict", "detail"}` records — it must never
compute health itself.

Per D-13 the checklist verifies exactly five things, in this canonical order:
supported Windows version; bundled FFmpeg and ffprobe; bundled Whisper
executable and required DLLs; bundled model; writable LecturePack data
directory. Nothing else.

Per D-14 the checklist never downloads or reinstalls anything already
bundled, so no returned item may carry a remediation, action, URL, download
or repair field — verdict and detail only. `detail` is technical evidence
(an OS build number, a failing canonical-inventory entry name, an existing
`reason` field) and never an absolute filesystem path or a user-facing
sentence — the user-facing advisory copy is owned by Plan 01-07 per the
UI-SPEC Copywriting Contract.

`WINDOWS_SUPPORTED_MIN_BUILD` is Windows 10 1809 (build 17763), the
documented floor for the PySide6 6.x line this app ships
(`app/requirements.txt` pins `PySide6>=6.7.0`; 6.11.1 is installed).
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

FIRST_RUN_CHECKLIST_ITEMS: tuple[str, ...] = (
    "windows_version",
    "ffmpeg_ffprobe",
    "whisper_runtime",
    "bundled_model",
    "data_directory",
)

VERDICT_READY = "ready"
VERDICT_NEEDS_ATTENTION = "needs_attention"

WINDOWS_SUPPORTED_MIN_BUILD = 17763


def supported_windows_version(version_info: tuple[int, int, int] | None = None) -> dict[str, Any]:
    """Report whether the given (or host) Windows version meets the floor.

    ``version_info`` is an injected ``(major, minor, build)`` tuple so this
    predicate is testable off any host. When ``None`` and the host is
    ``win32``, resolve from ``sys.getwindowsversion()``. When ``None`` off
    ``win32``, report unsupported with a reason naming the platform — this
    predicate never raises.
    """
    if version_info is None:
        if sys.platform == "win32":
            try:
                host = sys.getwindowsversion()  # type: ignore[attr-defined]
                version_info = (host.major, host.minor, host.build)
            except Exception as error:
                return {
                    "supported": False,
                    "detail": f"unable to determine Windows version: {error}",
                }
        else:
            return {
                "supported": False,
                "detail": f"not running on Windows (platform: {sys.platform})",
            }

    _major, _minor, build = version_info
    supported = build >= WINDOWS_SUPPORTED_MIN_BUILD
    if supported:
        detail = f"Windows build {build} meets the supported minimum (build {WINDOWS_SUPPORTED_MIN_BUILD})"
    else:
        detail = (
            f"Windows build {build} is below the supported minimum "
            f"(build {WINDOWS_SUPPORTED_MIN_BUILD})"
        )
    return {"supported": supported, "detail": detail}


def data_directory_writable(path: str | Path) -> dict[str, Any]:
    """Probe whether ``path`` is writable, leaving no trace behind.

    Creates a uniquely named probe file inside ``path``, writes a byte, then
    removes it in a ``finally``. Catches ``OSError`` and reports not-writable
    rather than propagating. Never includes an absolute path in ``detail``
    (T-01-03-04) — only the OS-provided short reason.
    """
    target = Path(path)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        reason = error.strerror or str(error)
        return {"writable": False, "detail": f"data directory not writable: {reason}"}

    probe_path = target / f".lecturepack-writability-probe-{uuid.uuid4().hex}"
    try:
        with open(probe_path, "wb") as handle:
            handle.write(b"0")
        return {"writable": True, "detail": "data directory is writable"}
    except OSError as error:
        reason = error.strerror or str(error)
        return {"writable": False, "detail": f"data directory not writable: {reason}"}
    finally:
        try:
            if probe_path.exists():
                probe_path.unlink()
        except OSError:
            pass


def checklist_group_for(inventory_entry: str) -> str:
    """Map a canonical inventory entry to its D-13 checklist group.

    ``bin/ffmpeg.exe`` and ``bin/ffprobe.exe`` -> ``ffmpeg_ffprobe``.
    ``models/ggml-base.en.bin`` -> ``bundled_model``. Everything else under
    ``bin/`` (the whisper executable, its DLLs, and any dynamically
    discovered ``bin/ggml-cpu-*.dll``) plus ``smoke/runtime-smoke.wav`` ->
    ``whisper_runtime``. Raises ``ValueError`` for an unrecognized entry so a
    future inventory addition cannot be silently dropped from the checklist.
    """
    if inventory_entry in ("bin/ffmpeg.exe", "bin/ffprobe.exe"):
        return "ffmpeg_ffprobe"
    if inventory_entry == "models/ggml-base.en.bin":
        return "bundled_model"
    if inventory_entry == "smoke/runtime-smoke.wav" or inventory_entry.startswith("bin/"):
        return "whisper_runtime"
    raise ValueError(f"unrecognized canonical inventory entry, cannot map to a checklist group: {inventory_entry!r}")


def _group_item(item_id: str, members: list[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    if not members:
        return {"id": item_id, "verdict": VERDICT_NEEDS_ATTENTION, "detail": f"no components mapped to {item_id}"}

    healthy = all(bool(evidence.get("healthy")) for _, evidence in members)
    if healthy:
        names = ", ".join(sorted(name for name, _ in members))
        detail = f"all {len(members)} component(s) healthy: {names}"
    else:
        failing_name, failing_evidence = next(
            (name, evidence) for name, evidence in members if not evidence.get("healthy")
        )
        reason = failing_evidence.get("reason", "unhealthy")
        detail = f"{failing_name} failed: {reason}"
    return {
        "id": item_id,
        "verdict": VERDICT_READY if healthy else VERDICT_NEEDS_ATTENTION,
        "detail": detail,
    }


def build_first_run_checklist(
    result: Any,
    *,
    windows_version: tuple[int, int, int] | None = None,
    data_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build the five-item, remediation-free D-13 checklist payload.

    ``result`` is a ``RuntimeBootstrapResult`` (or its ``components``
    mapping directly). Returns a list of five plain dicts, in canonical
    order, each carrying only ``{"id", "verdict", "detail"}`` — no
    remediation, action, url, download or repair field of any kind (D-14).
    """
    components: Mapping[str, Mapping[str, Any]] = getattr(result, "components", result)

    windows_check = supported_windows_version(windows_version)
    windows_item = {
        "id": "windows_version",
        "verdict": VERDICT_READY if windows_check["supported"] else VERDICT_NEEDS_ATTENTION,
        "detail": windows_check["detail"],
    }

    groups: dict[str, list[tuple[str, Mapping[str, Any]]]] = {
        "ffmpeg_ffprobe": [],
        "whisper_runtime": [],
        "bundled_model": [],
    }
    for entry, evidence in components.items():
        groups[checklist_group_for(entry)].append((entry, evidence))

    ffmpeg_item = _group_item("ffmpeg_ffprobe", groups["ffmpeg_ffprobe"])
    whisper_item = _group_item("whisper_runtime", groups["whisper_runtime"])
    model_item = _group_item("bundled_model", groups["bundled_model"])

    data_check = data_directory_writable(data_dir)
    data_item = {
        "id": "data_directory",
        "verdict": VERDICT_READY if data_check["writable"] else VERDICT_NEEDS_ATTENTION,
        "detail": data_check["detail"],
    }

    return [windows_item, ffmpeg_item, whisper_item, model_item, data_item]
