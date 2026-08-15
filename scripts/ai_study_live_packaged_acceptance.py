"""Run the packaged Polar Bears Study flow against the production gateway.

Unlike ``ai_study_packaged_acceptance.py``, this runner does not start a
deterministic gateway double. It proves that the frozen sidecar, bundled local
lecture pipeline, anonymous gateway registration, and live AI routes work
together. The deterministic runner remains the failure/privacy-path gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit

from electron_packaged_acceptance import (
    JsonlSession,
    data_dir_status,
    detect_orphans,
    discover_sidecar,
    locate_resources_root,
    snapshot_processes,
)


def _gateway_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlsplit(raw)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise SystemExit("--gateway-url must be a credential-free HTTPS origin")
    return raw


def _quality_checks(content: dict[str, Any]) -> dict[str, bool]:
    serialized = json.dumps(content, ensure_ascii=False)
    quiz_types = {
        str(item.get("qtype") or "")
        for item in content.get("quiz", []) if isinstance(item, dict)
    }
    web_sources = [
        source
        for key in ("concepts", "study_guide", "flashcards", "quiz")
        for item in content.get(key, []) if isinstance(item, dict)
        for source in item.get("web_sources", []) if isinstance(source, dict)
    ]
    return {
        "study_ready": content.get("study_status") == "ready",
        "summary_quality": len(str(content.get("lecture_summary") or "").strip()) >= 40,
        "concept_quality": len(content.get("concepts", [])) >= 2,
        "guide_quality": len(content.get("study_guide", [])) >= 2,
        "flashcard_quality": len(content.get("flashcards", [])) >= 2,
        "mixed_quiz_quality": {
            "multiple_choice", "true_false", "short_answer",
        }.issubset(quiz_types),
        "lecture_citations": '"segment_id"' in serialized and '"start_ms"' in serialized,
        "web_source_labels_valid": all(
            str(source.get("url") or "").startswith("https://")
            and bool(str(source.get("title") or "").strip())
            for source in web_sources
        ),
        "teach_foundations": bool(content.get("teach_me_foundations")),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    app_dir = Path(args.app_dir).resolve()
    data_dir = Path(args.data_dir).resolve()
    results_dir = Path(args.results_dir).resolve()
    demo_video = Path(args.demo_video).resolve()
    gateway_url = _gateway_url(args.gateway_url)
    allowed, reason = data_dir_status(data_dir)
    if not allowed:
        raise SystemExit(f"unsafe data dir: {reason}")
    data_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    sidecar = discover_sidecar(app_dir)
    if sidecar is None:
        raise SystemExit(f"packaged sidecar not found under {app_dir}")
    resources = locate_resources_root(sidecar)
    before = snapshot_processes()
    env = os.environ.copy()
    if args.use_packaged_default:
        env.pop("LECTUREPACK_AI_GATEWAY_URL", None)
    else:
        env["LECTUREPACK_AI_GATEWAY_URL"] = gateway_url
    env["LECTUREPACK_APP_VERSION"] = "2.0.1"
    session = JsonlSession(
        sidecar,
        ["--resources-root", str(resources), "--data-dir", str(data_dir),
         "--demo-video", str(demo_video)],
        timeout_s=args.timeout_seconds,
        env=env,
    )
    checks: dict[str, Any] = {}
    health_details: list[dict[str, Any]] = []
    observations: dict[str, Any] = {}
    harness_error = ""
    job_id = ""
    try:
        session.start()
        ready = session.wait_event("ready", timeout=60)
        checks["sidecar_ready"] = ready.get("engine_loaded") is True
        health = session.request("health_check", timeout=60)
        health_details = [
            {
                "id": item.get("id"),
                "ok": item.get("ok"),
                "reason": item.get("reason") or item.get("detail") or item.get("technical"),
            }
            for item in (health.get("checks") or []) if isinstance(item, dict)
        ]
        checks["runtime_health"] = health.get("startup_ok") is True

        imported = session.request("import_video", {"path": str(demo_video)}, timeout=60)
        job_id = str(imported.get("job_id") or "")
        started = session.request(
            "start_job", {"job_id": job_id, "mode": "study", "auto_export": True},
            timeout=60,
        )
        checks["processing_started"] = bool(started.get("started") or started.get("ok"))
        session.wait_event("job_completed", timeout=args.timeout_seconds)
        checks["processing_completed"] = True
        session.wait_event(
            "study_generation", timeout=args.timeout_seconds,
            predicate=lambda message: message.get("status") in {"ready", "failed"},
        )
        status = session.request("study_v2_status", {"job_id": job_id}, timeout=60)
        content = status.get("content") if isinstance(status.get("content"), dict) else {}
        checks.update(_quality_checks(content))
        observations = {
            "summary": str(content.get("lecture_summary") or "")[:800],
            "concept_titles": [
                str(item.get("title") or "")[:200]
                for item in content.get("concepts", [])[:10] if isinstance(item, dict)
            ],
            "counts": {
                key: len(content.get(key, []))
                for key in ("concepts", "study_guide", "flashcards", "quiz")
            },
        }

        concepts = [item for item in content.get("concepts", []) if isinstance(item, dict)]
        if not concepts:
            raise RuntimeError(
                f"Study generation ended with status {content.get('study_status') or 'unknown'}"
            )
        first_concept = concepts[0]
        concept_id = str(first_concept.get("id") or "")
        concept_title = str(first_concept.get("title") or "this concept")
        mastery = session.request(
            "study_v2_set_mastery",
            {"job_id": job_id, "concept_id": concept_id, "mastery": "MASTERED"},
        )
        checks["manual_mastery"] = (
            mastery.get("progress", {}).get("concepts", {}).get(concept_id, {}).get("mastery")
            == "MASTERED"
        )
        quick = session.request("study_v2_quick_study", {"job_id": job_id, "minutes": 5})
        checks["quick_study"] = bool(quick.get("session", {}).get("items"))

        session.request(
            "ask_ai",
            {"job_id": job_id, "prompt": f"Explain {concept_title} using the lecture evidence."},
        )
        answer = session.wait_event(
            "ai_token", timeout=180, predicate=lambda message: message.get("job") == job_id,
        )
        ask_sources = session.wait_event(
            "ai_sources", timeout=60, predicate=lambda message: message.get("job") == job_id,
        )
        checks["ask"] = len(str(answer.get("text") or "").strip()) >= 30
        checks["ask_sources"] = bool(ask_sources.get("sources"))

        session.request(
            "study_v2_teach_me", {"job_id": job_id, "concept_id": concept_id},
        )
        teach = session.wait_event(
            "study_teach_ready", timeout=180,
            predicate=lambda message: message.get("concept_id") == concept_id,
        )
        teach_result = teach.get("result") if isinstance(teach.get("result"), dict) else {}
        checks["teach_me"] = (
            teach.get("ok") is True
            and bool(str(teach_result.get("explanation") or "").strip())
            and bool(str(teach_result.get("check_question") or "").strip())
        )

        short_answers = [
            item for item in content.get("quiz", [])
            if isinstance(item, dict) and item.get("qtype") == "short_answer"
        ]
        checks["short_answer_available"] = bool(short_answers)
        if short_answers:
            short = short_answers[0]
            accepted = short.get("accepted_answers") or []
            answer_text = str(
                (accepted[0] if accepted else "")
                or short.get("explanation") or short.get("rubric") or concept_title
            )
            session.request(
                "study_v2_grade_short_answer",
                {"job_id": job_id, "question_id": str(short.get("id") or ""),
                 "answer": answer_text},
            )
            grade = session.wait_event(
                "study_short_answer_graded", timeout=180,
                predicate=lambda message: message.get("question_id") == short.get("id"),
            )
            grade_result = grade.get("result") if isinstance(grade.get("result"), dict) else {}
            checks["live_grading"] = (
                grade.get("ok") is True
                and isinstance(grade_result.get("score"), (int, float))
                and bool(str(grade_result.get("feedback") or "").strip())
            )
        else:
            checks["live_grading"] = False

        basic = session.request("study_v2_use_basic", {"job_id": job_id}).get("content") or {}
        checks["basic_fallback"] = (
            basic.get("study_status") == "basic" and bool(basic.get("concepts"))
        )
        installation = data_dir / "ai-installation-v1.json"
        checks["anonymous_registration_persisted"] = installation.is_file()
        if installation.is_file():
            persisted = json.loads(installation.read_text(encoding="utf-8"))
            checks["desktop_gateway_config"] = persisted.get("gateway_origin") == gateway_url
            checks["opaque_installation_token"] = bool(persisted.get("installation_token"))
        else:
            checks["desktop_gateway_config"] = False
            checks["opaque_installation_token"] = False

        session.request("shutdown", timeout=30)
        checks["clean_exit"] = session.close() == 0
        checks["acceptance_completed"] = True
    except Exception as exc:  # noqa: BLE001 - preserve partial packaged evidence
        harness_error = f"{type(exc).__name__}: {exc}"
        checks["acceptance_completed"] = False
    finally:
        if session.proc is not None and session.proc.poll() is None:
            session.close()
        time.sleep(1)

    checks["orphan_processes"] = detect_orphans(before, snapshot_processes())
    checks["no_orphans"] = not checks["orphan_processes"]
    checks["passed"] = all(
        value is True
        for key, value in checks.items()
        if key not in {"orphan_processes", "passed"}
    )
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "packaged_sidecar": str(sidecar),
        "demo_video": str(demo_video),
        "job_id": job_id,
        "gateway_mode": "production HTTPS gateway (real providers)",
        "gateway_configuration": (
            "packaged default" if args.use_packaged_default else "acceptance environment override"
        ),
        "gateway_origin": gateway_url,
        "checks": checks,
        "runtime_health_details": health_details,
        "quality_observations": observations,
        "harness_error": harness_error,
        "stderr": session.stderr_lines[-30:],
    }
    report_path = results_dir / "ai-study-live-packaged-acceptance.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--demo-video", required=True)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--use-packaged-default", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["checks"]["passed"] else 1)
