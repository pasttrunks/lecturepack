"""Packaged AI-first Study acceptance using the real bundled demo pipeline.

This is deliberately not a real-provider test. It freezes and drives the
production sidecar against a loopback gateway with deterministic Polar Bears
responses, proving packaged orchestration, persistence, interactions,
fallbacks, privacy boundaries, and clean shutdown without requiring secrets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any

from electron_packaged_acceptance import (
    JsonlSession,
    data_dir_status,
    detect_orphans,
    discover_sidecar,
    locate_resources_root,
    snapshot_processes,
)


WEB_URL = "https://www.fws.gov/species/polar-bear-ursus-maritimus"
WINDOWS_PATH_RE = re.compile(r"(?<![a-z0-9])[a-z]:[\\/]", re.IGNORECASE)


def contains_local_path(serialized: str, demo_video: str) -> bool:
    """Reject local file evidence without mistaking the ``s:/`` in HTTPS URLs."""
    return (
        demo_video in serialized
        or ".mp4\"" in serialized
        or WINDOWS_PATH_RE.search(serialized) is not None
    )


def _grounded(concept_ids: list[str], segment_id: str, *, web: bool = False) -> dict[str, Any]:
    return {
        "concept_ids": concept_ids,
        "lecture_sources": [{"segment_id": segment_id}],
        "web_sources": ([{
            "title": "U.S. Fish & Wildlife Service — Polar Bear",
            "url": WEB_URL,
            "claim": "Polar bears depend on sea-ice habitat for core life activities.",
        }] if web else []),
        "provenance": "mixed" if web else "lecture",
    }


def _analysis(task_input: dict[str, Any]) -> dict[str, Any]:
    transcript = task_input.get("transcript") or []
    if not transcript and task_input.get("chunk_analyses"):
        transcript = [{"segment_id": "0"}, {"segment_id": "1"}]
    first = str((transcript[0] if transcript else {}).get("segment_id") or "0")
    last = str((transcript[-1] if transcript else {}).get("segment_id") or first)
    slides = task_input.get("slides") or []
    return {
        "lecture_summary": "Polar bears combine transparent fur, black skin, and marine behavior to survive in the Arctic, while sea-ice loss threatens hunting access.",
        "concepts": [
            {"id": "c-fur", "title": "Transparent fur and black skin", "importance": 5,
             "explanation": "Transparent hairs scatter light above heat-absorbing black skin.",
             "related_concept_ids": ["c-ice"], "emphasis": "core adaptation",
             **_grounded(["c-fur"], first)},
            {"id": "c-ice", "title": "Sea-ice hunting ecology", "importance": 5,
             "explanation": "As marine mammals, polar bears use sea ice as access to prey.",
             "related_concept_ids": ["c-fur"], "emphasis": "ecological pressure",
             **_grounded(["c-ice"], last)},
        ],
        "relationships": [{"from_concept_id": "c-fur", "to_concept_id": "c-ice",
                           "relationship": "Both traits support Arctic survival."}],
        "key_terms": [], "people": [], "dates": [], "misconceptions": [],
        "research_requests": [{"concept_id": "c-ice", "query": "polar bear sea ice habitat",
                               "reason": "Add clearly labeled current public context."}],
        "vision_requests": ([{"slide_id": str(slides[0].get("slide_id") or ""),
                              "reason": "Interpret the first accepted visual."}] if slides else []),
    }


def _materials(task_input: dict[str, Any]) -> dict[str, Any]:
    transcript = ((task_input.get("lecture") or {}).get("transcript") or [])
    first = str((transcript[0] if transcript else {}).get("segment_id") or "0")
    last = str((transcript[-1] if transcript else {}).get("segment_id") or first)
    fur = _grounded(["c-fur"], first)
    ice = _grounded(["c-ice"], last, web=True)
    return {
        "lecture_summary": "Polar bears are Arctic marine mammals whose physical adaptations and reliance on sea ice work together.",
        "concepts": [
            {"id": "c-fur", "title": "Transparent fur and black skin", "importance": 5,
             "explanation": "The lecture corrects the common white-fur misconception: the hairs are transparent and the skin beneath is black.",
             "related_concept_ids": ["c-ice"], "emphasis": "remember this", **fur},
            {"id": "c-ice", "title": "Sea-ice hunting ecology", "importance": 5,
             "explanation": "Polar bears are marine mammals that depend on sea ice to reach prey; habitat loss changes access and energy costs.",
             "related_concept_ids": ["c-fur"], "emphasis": "key relationship", **ice},
        ],
        "key_terms": [
            {"label": "Marine mammal", "detail": "A mammal ecologically tied to marine environments.", **_grounded(["c-ice"], last)},
            {"label": "Transparent guard hair", "detail": "Outer hair without white pigment that scatters visible light.", **fur},
        ],
        "people": [], "dates": [],
        "study_guide": [
            {"heading": "What makes the fur look white?", "body": "Transparent hairs scatter light while black skin lies beneath them.", **fur},
            {"heading": "Why sea ice matters", "body": "Sea ice functions as hunting habitat; loss increases ecological pressure.", **ice},
        ],
        "flashcards": [
            {"id": "f-fur", "front": "Is polar-bear fur actually white?", "back": "No. The hairs are transparent and scatter light above black skin.", "difficulty": "core", **fur},
            {"id": "f-ice", "front": "Why are polar bears classed as marine mammals?", "back": "Their feeding ecology and movement depend on Arctic seas and sea ice.", "difficulty": "core", **ice},
        ],
        "quiz": [
            {"id": "q-mc", "question": "What color pigment is in polar-bear fur?", "qtype": "multiple_choice", "options": ["No white pigment; hairs are transparent", "White", "Black"], "correct_index": 0, "accepted_answers": [], "rubric": "", "explanation": "The lecture explicitly describes transparent fur.", **fur},
            {"id": "q-tf", "question": "Polar bears are marine mammals.", "qtype": "true_false", "options": ["True", "False"], "correct_index": 0, "accepted_answers": [], "rubric": "", "explanation": "Their ecology is tied to Arctic marine habitat.", **_grounded(["c-ice"], last)},
            {"id": "q-short", "question": "Explain why sea-ice loss affects polar-bear hunting.", "qtype": "short_answer", "options": [], "correct_index": 0, "accepted_answers": ["Sea ice provides access to prey."], "rubric": "Connect sea ice to access to prey and energy cost.", "explanation": "Sea ice is a hunting platform.", **ice},
        ],
        "misconceptions": [{"label": "White fur pigment", "detail": "The white appearance comes from scattered light, not white pigment.", **fur}],
        "quick_study_material": {"five_minute": ["c-fur"], "ten_minute": ["c-fur", "c-ice"], "twenty_minute": ["c-fur", "c-ice"], "full": ["c-fur", "c-ice"]},
        "teach_me_foundations": [{"concept_id": "c-ice", "explanation": "Treat sea ice as moving habitat, not merely frozen scenery.", "analogy": "It is a seasonal bridge to prey.", "check_question": "What happens when that bridge shrinks?", "rubric": "Mention reduced prey access or higher energy cost.", **ice}],
    }


class GatewayState:
    def __init__(self, demo_video: Path):
        self.demo_video = str(demo_video.resolve()).casefold()
        self.requests: list[dict[str, Any]] = []
        self.fail = False
        self.path_leak = False
        self.client_routing = False

    def result(self, task: str, task_input: dict[str, Any]) -> dict[str, Any]:
        if task == "lecture_analysis":
            return _analysis(task_input)
        if task == "vision_slide":
            return {"slide_id": str(task_input.get("slide_id") or ""), "visible_text": "Polar bear adaptation", "interpretation": "The selected visual reinforces the adaptation concept.", "concept_ids": ["c-fur"]}
        if task == "web_enrichment":
            return {"summary": "Current public context is kept separate from lecture claims.", "facts": [{"claim": "Sea ice is core habitat.", "title": "U.S. Fish & Wildlife Service — Polar Bear", "url": WEB_URL}], "sources": [{"title": "U.S. Fish & Wildlife Service — Polar Bear", "url": WEB_URL, "claim": "Sea ice is core habitat."}]}
        if task == "study_material_generation":
            return _materials(task_input)
        if task == "ask":
            return {"answer": "The lecture says transparent hairs scatter light above black skin; the verified public source is separately labeled.", **_grounded(["c-fur"], "0", web=True)}
        if task == "teach_me":
            return {"explanation": "Sea ice is functional habitat that gives access to prey.", "analogy": "Think of it as a seasonal bridge.", "check_question": "Why does a shorter bridge matter?", "rubric": "Connect less ice with reduced prey access or higher energy cost.", **_grounded(["c-ice"], "0", web=True)}
        if task == "grade_short_answer":
            return {"correct": True, "score": 0.94, "feedback": "You connected sea ice with access to prey.", "ideal_answer": "Sea ice provides hunting access; less ice can raise energy costs.", **_grounded(["c-ice"], "0", web=True)}
        if task == "regenerate_concept":
            material = _materials({"lecture": {"transcript": [{"segment_id": "0"}]}})
            return {"concept": material["concepts"][0], "flashcards": [material["flashcards"][0]], "quiz": [material["quiz"][0]], "study_guide_fragments": [material["study_guide"][0]]}
        raise ValueError(f"unsupported task {task}")


def start_gateway(state: GatewayState) -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            length = min(int(self.headers.get("content-length") or 0), 5_000_000)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            serialized = json.dumps(body, ensure_ascii=False).casefold()
            if contains_local_path(serialized, state.demo_video):
                state.path_leak = True
            task_input = body.get("input") if isinstance(body.get("input"), dict) else {}
            if (any(key in body for key in ("provider", "model", "route"))
                    or any(key in task_input for key in ("provider", "model", "route"))):
                state.client_routing = True
            if self.path.endswith("/v1/installations/register"):
                response = {"ok": True, "installation_token": "packaged-acceptance-token", "expires_at": "2099-01-01T00:00:00+00:00"}
                status = 200
            else:
                task = str(body.get("task") or "")
                state.requests.append({"task": task, "input_chars": len(json.dumps(task_input)), "has_image": "image_data_url" in task_input})
                if state.fail:
                    status = 503
                    response = {"ok": False, "error": {"code": "ai_routes_failed", "message": "Study AI could not complete this request.", "retryable": True}, "diagnostics": {"request_id": body.get("request_id"), "task": task, "attempted_routes": [f"{task}-primary@openrouter:fixture/primary", f"{task}-secondary@workers_ai:fixture/secondary"], "provider_codes": ["provider_unavailable", "provider_unavailable"], "provider_status": [503, 502], "retry_count": 1}}
                else:
                    status = 200
                    response = {"ok": True, "request_id": body.get("request_id"), "task": task, "result": state.result(task, task_input), "diagnostics": {"request_id": body.get("request_id"), "task": task, "attempted_routes": [], "provider_codes": [], "provider_status": [], "retry_count": 0, "timestamp": datetime.now(timezone.utc).isoformat()}}
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _check_content(content: dict[str, Any]) -> dict[str, bool]:
    quiz_types = {item.get("qtype") for item in content.get("quiz", [])}
    serialized = json.dumps(content)
    return {
        "ready": content.get("study_status") == "ready",
        "guide": len(content.get("study_guide", [])) >= 2,
        "flashcards": len(content.get("flashcards", [])) >= 2,
        "mixed_quiz": {"multiple_choice", "true_false", "short_answer"}.issubset(quiz_types),
        "lecture_citations": '"start_ms"' in serialized and '"segment_id"' in serialized,
        "web_citations": WEB_URL in serialized,
        "teach_foundations": bool(content.get("teach_me_foundations")),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    app_dir = Path(args.app_dir).resolve()
    data_dir = Path(args.data_dir).resolve()
    results_dir = Path(args.results_dir).resolve()
    demo_video = Path(args.demo_video).resolve()
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
    state = GatewayState(demo_video)
    server, gateway_url = start_gateway(state)
    env = os.environ.copy()
    env["LECTUREPACK_AI_GATEWAY_URL"] = gateway_url
    env["LECTUREPACK_APP_VERSION"] = "2.0.1"
    session = JsonlSession(sidecar, ["--resources-root", str(resources), "--data-dir", str(data_dir), "--demo-video", str(demo_video)], timeout_s=args.timeout_seconds, env=env)
    checks: dict[str, Any] = {}
    observations: list[str] = []
    health_details: list[dict[str, Any]] = []
    harness_error = ""
    job_id = ""
    try:
        session.start()
        ready = session.wait_event("ready", timeout=60)
        checks["sidecar_ready"] = ready.get("engine_loaded") is True
        health = session.request("health_check", timeout=60)
        health_details = [
            {"id": item.get("id"), "ok": item.get("ok"),
             "reason": item.get("reason") or item.get("detail") or item.get("technical")}
            for item in (health.get("checks") or []) if isinstance(item, dict)
        ]
        checks["runtime_health"] = health.get("startup_ok") is True
        # Use the bundled Polar Bears asset as an ordinary lecture. Guided-demo
        # mode has intentional lifecycle cleanup and is a separate acceptance.
        imported = session.request("import_video", {"path": str(demo_video)}, timeout=60)
        job_id = str(imported.get("job_id") or "")
        started = session.request("start_job", {"job_id": job_id, "mode": "study", "auto_export": True}, timeout=60)
        checks["processing_started"] = bool(started.get("started") or started.get("ok"))
        session.wait_event("job_completed", timeout=args.timeout_seconds)
        checks["processing_completed"] = True
        session.wait_event("study_generation", timeout=120, predicate=lambda msg: msg.get("status") == "ready")
        status = session.request("study_v2_status", {"job_id": job_id}, timeout=60)
        content = status.get("content") if isinstance(status.get("content"), dict) else {}
        checks.update(_check_content(content))
        observations.extend([
            str(content.get("lecture_summary") or "")[:500],
            " | ".join(str(item.get("title") or "") for item in content.get("concepts", [])),
            " | ".join(str(item.get("front") or "") for item in content.get("flashcards", [])),
        ])
        concept_id = str(content["concepts"][0]["id"])
        mastery = session.request("study_v2_set_mastery", {"job_id": job_id, "concept_id": concept_id, "mastery": "MASTERED"})
        checks["manual_mastery"] = mastery.get("progress", {}).get("concepts", {}).get(concept_id, {}).get("mastery") == "MASTERED"
        quick = session.request("study_v2_quick_study", {"job_id": job_id, "minutes": 5})
        checks["quick_study"] = bool(quick.get("session", {}).get("items"))
        session.request("ask_ai", {"job_id": job_id, "prompt": "Why does the fur look white?"})
        answer = session.wait_event("ai_token", timeout=60, predicate=lambda msg: msg.get("job") == job_id)
        ask_sources = session.wait_event("ai_sources", timeout=60, predicate=lambda msg: msg.get("job") == job_id)
        checks["ask"] = "transparent" in str(answer.get("text") or "").casefold()
        checks["ask_sources"] = bool(ask_sources.get("sources"))
        session.request("study_v2_teach_me", {"job_id": job_id, "concept_id": "c-ice"})
        teach = session.wait_event("study_teach_ready", timeout=60, predicate=lambda msg: msg.get("concept_id") == "c-ice")
        checks["teach_me"] = teach.get("ok") is True and bool((teach.get("result") or {}).get("check_question"))
        short = next(item for item in content["quiz"] if item.get("qtype") == "short_answer")
        session.request("study_v2_grade_short_answer", {"job_id": job_id, "question_id": short["id"], "answer": "Sea ice lets bears reach prey, and less ice costs more energy."})
        grade = session.wait_event("study_short_answer_graded", timeout=60, predicate=lambda msg: msg.get("question_id") == short["id"])
        checks["live_grading"] = grade.get("ok") is True and (grade.get("result") or {}).get("score", 0) >= 0.9
        state.fail = True
        retry = session.request("study_v2_retry", {"job_id": job_id})
        checks["retry_started"] = retry.get("started") is True
        session.wait_event("study_generation", timeout=60, predicate=lambda msg: msg.get("status") == "failed")
        diagnostics = session.request("study_v2_copy_diagnostics", {"job_id": job_id}).get("diagnostics") or {}
        diagnostic_text = json.dumps(diagnostics).casefold()
        checks["safe_diagnostics"] = (
            diagnostics.get("error_category") == "ai_routes_failed"
            and diagnostics.get("retry_count") == 1
            and any("@openrouter:" in route for route in diagnostics.get("attempted_routes", []))
            and any("@workers_ai:" in route for route in diagnostics.get("attempted_routes", []))
            and "authorization" not in diagnostic_text
            and "transcript" not in diagnostic_text
            and "raw_response" not in diagnostic_text
        )
        basic = session.request("study_v2_use_basic", {"job_id": job_id}).get("content") or {}
        checks["basic_fallback"] = basic.get("study_status") == "basic" and bool(basic.get("concepts"))
        vision_count = len([item for item in state.requests if item["task"] == "vision_slide"])
        checks["selective_vision"] = 1 <= vision_count <= 3
        checks["bounded_web"] = 1 <= len([item for item in state.requests if item["task"] == "web_enrichment"]) <= 3
        checks["payload_privacy"] = not state.path_leak and not state.client_routing
        session.request("shutdown", timeout=30)
        checks["clean_exit"] = session.close() == 0
        checks["acceptance_completed"] = True
    except Exception as exc:  # noqa: BLE001 - preserve partial packaged evidence
        harness_error = f"{type(exc).__name__}: {exc}"
        checks["acceptance_completed"] = False
    finally:
        server.shutdown()
        server.server_close()
        if session.proc is not None and session.proc.poll() is None:
            session.close()
        time.sleep(1)
    checks["orphan_processes"] = detect_orphans(before, snapshot_processes())
    checks["no_orphans"] = not checks["orphan_processes"]
    checks["passed"] = all(value is True for key, value in checks.items() if key not in {"orphan_processes", "passed"})
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "packaged_sidecar": str(sidecar), "demo_video": str(demo_video), "job_id": job_id, "gateway_mode": "loopback deterministic acceptance double (not real provider)", "checks": checks, "runtime_health_details": health_details, "task_counts": {task: len([item for item in state.requests if item["task"] == task]) for task in sorted({item["task"] for item in state.requests})}, "quality_observations": observations, "harness_error": harness_error, "stderr": session.stderr_lines[-30:]}
    (results_dir / "ai-study-packaged-acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--demo-video", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=360.0)
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["checks"]["passed"] else 1)
