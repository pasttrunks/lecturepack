"""Unit tests for lecturepack/services/job_ops.py — stage-aware retry planning,
completion metrics, and redacted diagnostics (privacy)."""

import os

from lecturepack.services import job_ops as ops

STAGES = ["Inspect", "Extract Audio", "Transcribe", "Detect Slides", "Align",
          "Review Ready", "Export"]


# --- stage retry ----------------------------------------------------------- #
def test_retry_preserves_upstream_resets_failed_and_downstream():
    status = {
        "Inspect": {"status": "completed"},
        "Extract Audio": {"status": "completed"},
        "Transcribe": {"status": "completed"},
        "Detect Slides": {"status": "failed"},
        "Align": {"status": "pending"},
        "Review Ready": {"status": "pending"},
        "Export": {"status": "pending"},
    }
    plan = ops.plan_stage_retry(STAGES, status, "Detect Slides")
    assert plan["preserved"] == ["Inspect", "Extract Audio", "Transcribe"]
    assert "Detect Slides" in plan["reset"]
    assert "Align" in plan["reset"] and "Export" in plan["reset"]
    # upstream completed work is NOT thrown away
    assert "Transcribe" not in plan["reset"]


def test_retry_reruns_incomplete_upstream():
    status = {
        "Inspect": {"status": "completed"},
        "Extract Audio": {"status": "interrupted"},  # upstream but not completed
        "Transcribe": {"status": "failed"},
    }
    plan = ops.plan_stage_retry(STAGES, status, "Transcribe")
    assert "Extract Audio" in plan["reset"]
    assert plan["preserved"] == ["Inspect"]


def test_retry_respects_skipped_stages():
    status = {s: {"status": "completed"} for s in STAGES}
    status["Align"] = {"status": "failed"}
    plan = ops.plan_stage_retry(STAGES, status, "Align",
                                skipped={"Detect Slides"})
    assert "Detect Slides" not in plan["reset"]
    assert "Detect Slides" not in plan["preserved"]
    assert "Detect Slides" in plan["skipped"]


# --- completion metrics ---------------------------------------------------- #
def test_transcript_word_and_segment_count():
    segs = [{"text": "hello world"}, {"text": "foo bar baz"}, {"text": ""}]
    assert ops.transcript_word_count(segs) == 5
    assert ops.count_segments(segs) == 3


def test_wall_time_and_format():
    secs = ops.wall_time_seconds("2026-07-23T12:00:00+00:00",
                                 "2026-07-23T12:01:30+00:00")
    assert secs == 90.0
    assert ops.format_duration(90) == "1m 30s"
    assert ops.format_duration(3725) == "1h 2m 5s"
    assert ops.format_duration(None) == "—"


def test_wall_time_negative_is_none():
    assert ops.wall_time_seconds("2026-07-23T12:01:00+00:00",
                                 "2026-07-23T12:00:00+00:00") is None


def test_completion_metrics_assembles():
    m = ops.completion_metrics(
        segments=[{"text": "a b c"}], slides_detected=12,
        started_iso="2026-07-23T12:00:00+00:00",
        finished_iso="2026-07-23T12:00:30+00:00",
        study_state="ready", export_state="pdf")
    assert m["transcript_words"] == 3
    assert m["segment_count"] == 1
    assert m["slides_detected"] == 12
    assert m["wall_time"] == "30s"
    assert m["study_state"] == "ready"


# --- redaction / diagnostics (privacy) ------------------------------------- #
def test_redact_strips_groq_and_openai_keys():
    s = "failed with key gsk_ABCDEFGHIJKLMNOP1234 and sk-abcdefghijklmnop"
    out = ops.redact_text(s)
    assert "gsk_" not in out
    assert "sk-abcdef" not in out
    assert "[REDACTED]" in out


def test_redact_bearer_and_labeled_secrets():
    assert "[REDACTED]" in ops.redact_text("Authorization: Bearer abc123def456ghi")
    assert "[REDACTED]" in ops.redact_text("api_key=supersecretvalue123")
    assert "[REDACTED]" in ops.redact_text("password: hunter2hunter2")


def test_redact_anonymizes_user_path():
    p = r"C:\Users\marsh\Documents\LecturePack\bin\whisper-cli.exe"
    out = ops.redact_text(p)
    assert "marsh" not in out
    assert "<user>" in out or "%USERPROFILE%" in out


def test_build_diagnostics_redacts_and_excludes_content():
    diag = ops.build_diagnostics(
        app_version="0.9.0-beta.3", job_id="job-123", stage="Transcribe",
        status="failed",
        error=r"boom at C:\Users\marsh\x with token gsk_SECRETSECRET123456",
        exit_code=3, timestamp="2026-07-23T12:00:00+00:00",
        runtime_paths={"whisper": r"C:\Users\marsh\bin\whisper-cli.exe"})
    assert diag["app_version"] == "0.9.0-beta.3"
    assert diag["exit_code"] == 3
    # error is redacted
    assert "gsk_" not in diag["error_summary"]
    assert "marsh" not in diag["error_summary"]
    # runtime paths anonymized
    assert "marsh" not in diag["runtime_paths"]["whisper"]
    # no transcript/content keys present
    assert set(diag.keys()) == {
        "app_version", "job_id", "stage", "status", "error_summary",
        "exit_code", "timestamp", "runtime_paths"}


def test_redact_empty():
    assert ops.redact_text("") == ""
    assert ops.redact_text(None) == ""
