"""Stage retry, completion metrics, and redacted diagnostics (beta.3 Phase 4).

Pure helpers (no Qt) so they are fully unit-testable. The controller/adapter
call these to (a) retry only the failed stage plus its required downstream work
while preserving verified upstream outputs, (b) compute real completion metrics,
and (c) build a diagnostics bundle that is safe to copy/share — never containing
API keys, credentials, transcript text, or lecture content.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Iterable, Optional

# Post-completion behavior preferences (persisted setting key + values).
POST_COMPLETION_KEY = "post_completion_behavior"
OPEN_COMPLETED_LECTURE = "open_completed_lecture"
STAY_ON_PROCESSING = "stay_on_processing"
ASK = "ask"
POST_COMPLETION_DEFAULT = OPEN_COMPLETED_LECTURE
POST_COMPLETION_VALUES = frozenset(
    {OPEN_COMPLETED_LECTURE, STAY_ON_PROCESSING, ASK})


# --- stage-aware retry ----------------------------------------------------- #
def plan_stage_retry(stage_order: list, stage_status: dict, failed_stage: str,
                     skipped: Optional[Iterable[str]] = None) -> dict:
    """Plan a retry of ``failed_stage``: reset it plus every required downstream
    stage, while PRESERVING completed upstream stages. Skipped stages (product
    mode) stay skipped. Replaces the old bulk "reset every failed/interrupted
    stage" behavior so a transient failure late in the pipeline doesn't throw
    away good upstream work.

    Returns {"reset": [...], "preserved": [...], "skipped": [...]}.
    """
    skipped = set(skipped or [])
    if failed_stage not in stage_order:
        return {"reset": [], "preserved": list(stage_order), "skipped": list(skipped)}
    idx = stage_order.index(failed_stage)
    reset, preserved = [], []
    for i, stage in enumerate(stage_order):
        if stage in skipped:
            continue
        if i < idx:
            # upstream: keep if verifiably completed, else it must re-run too.
            if stage_status.get(stage, {}).get("status") == "completed":
                preserved.append(stage)
            else:
                reset.append(stage)
        else:
            reset.append(stage)  # failed stage + downstream
    return {"reset": reset, "preserved": preserved, "skipped": sorted(skipped)}


# --- completion metrics ---------------------------------------------------- #
def transcript_word_count(segments: Iterable[dict]) -> int:
    total = 0
    for seg in segments or []:
        total += len((seg.get("text") or "").split())
    return total


def count_segments(segments: Iterable[dict]) -> int:
    return len(list(segments or []))


def wall_time_seconds(started_iso: str, finished_iso: str) -> Optional[float]:
    try:
        a = datetime.fromisoformat(started_iso)
        b = datetime.fromisoformat(finished_iso)
        secs = (b - a).total_seconds()
        return secs if secs >= 0 else None
    except Exception:
        return None


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def completion_metrics(*, segments=None, slides_detected: int = 0,
                       started_iso: str = "", finished_iso: str = "",
                       study_state: str = "none", export_state: str = "none") -> dict:
    """Assemble the completion panel metrics from already-loaded inputs."""
    secs = wall_time_seconds(started_iso, finished_iso)
    return {
        "wall_time_seconds": secs,
        "wall_time": format_duration(secs),
        "transcript_words": transcript_word_count(segments),
        "segment_count": count_segments(segments),
        "slides_detected": int(slides_detected or 0),
        "study_state": study_state,
        "export_state": export_state,
    }


# --- redaction / diagnostics ----------------------------------------------- #
# Secret-ish token patterns (Groq gsk_, OpenAI sk-, bearer tokens, long hex/b64).
_SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*\S+"),
]


def redact_text(text: str) -> str:
    """Strip anything that looks like a credential and anonymize the user's home
    path (username) so a diagnostics bundle is safe to share."""
    if not text:
        return ""
    out = str(text)
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    out = _anonymize_paths(out)
    return out


def _anonymize_paths(text: str) -> str:
    home = os.path.expanduser("~")
    if home and home in text:
        text = text.replace(home, r"%USERPROFILE%")
    # Also catch other users' profiles / raw C:\Users\<name>\.
    text = re.sub(r"(?i)([A-Z]:\\Users\\)[^\\/:*?\"<>|\r\n]+",
                  r"\1<user>", text)
    text = re.sub(r"(/home/)[^/\r\n]+", r"\1<user>", text)
    return text


def build_diagnostics(*, app_version: str, job_id: str, stage: str = "",
                      status: str = "", error: str = "", exit_code=None,
                      timestamp: str = "", runtime_paths: Optional[dict] = None) -> dict:
    """Build a redacted diagnostics bundle. NEVER includes keys, credentials,
    transcript text, or lecture content — callers pass only metadata; free-text
    fields (error, paths) are run through redaction."""
    safe_paths = {}
    for k, v in (runtime_paths or {}).items():
        safe_paths[k] = _anonymize_paths(str(v)) if v else ""
    return {
        "app_version": app_version,
        "job_id": job_id,
        "stage": stage,
        "status": status,
        "error_summary": redact_text(error)[:1000],
        "exit_code": exit_code,
        "timestamp": timestamp,
        "runtime_paths": safe_paths,
    }
