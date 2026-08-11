"""Packaged LecturePack 2.0.1 state/identity acceptance gate.

This gate complements the generic packaged processing gate.  It drives the
real frozen sidecar JSONL boundary with disposable data and verifies the
state contracts introduced by the 2.0.1 polish pass: existing-user tour
eligibility, explicit demo identity/cleanup/reconciliation, existing-ID FIFO
queueing, and safe reset containment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from electron_packaged_acceptance import (  # noqa: E402
    JsonlSession,
    data_dir_status,
    discover_sidecar,
    locate_resources_root,
)
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402
from lecturepack.models.job import Job  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_job(data_dir: Path, source: Path, title: str) -> str:
    job = Job(str(data_dir), video_path=str(source))
    job.manifest["title"] = title
    job.save()
    return str(job.job_id)


def fresh_dir(path: Path) -> None:
    if path.exists():
        if any(path.iterdir()):
            raise RuntimeError(f"refusing to reuse non-empty disposable directory: {path}")
    else:
        path.mkdir(parents=True, exist_ok=True)


def start_sidecar(sidecar: Path, resources_root: Path, data_dir: Path,
                  demo: Path, timeout: float) -> JsonlSession:
    session = JsonlSession(
        sidecar,
        [
            "--resources-root", str(resources_root),
            "--data-dir", str(data_dir),
            "--demo-video", str(demo),
        ],
        timeout_s=timeout,
    )
    session.start()
    ready = session.wait_event("ready", timeout=min(timeout, 90.0))
    if ready.get("engine_loaded") is not True:
        session.close()
        raise RuntimeError(f"packaged sidecar did not become ready: {ready}")
    return session


def clean_shutdown(session: JsonlSession) -> None:
    try:
        if session.proc is not None and session.proc.poll() is None:
            session.request("shutdown", timeout=30.0)
    finally:
        session.close()


def crash_shutdown(session: JsonlSession) -> None:
    process = session.proc
    if process is None or process.poll() is not None:
        return
    process.kill()
    process.wait(timeout=30)


def check(condition: bool, checks: dict[str, bool], name: str, detail: Any = None,
          details: dict[str, Any] | None = None) -> None:
    checks[name] = bool(condition)
    if details is not None:
        details[name] = detail


def run_gate(app_dir: Path, data_root: Path, results_dir: Path,
             demo: Path, timeout: float) -> dict[str, Any]:
    allowed, reason = data_dir_status(data_root)
    if not allowed:
        raise RuntimeError(f"disposable data root rejected: {reason}")
    if not demo.is_file():
        raise RuntimeError(f"bundled Polar Bears demo is missing: {demo}")
    fresh_dir(data_root)
    results_dir.mkdir(parents=True, exist_ok=True)

    sidecar = discover_sidecar(app_dir)
    if sidecar is None:
        raise RuntimeError(f"packaged sidecar not found below {app_dir}")
    resources_root = locate_resources_root(sidecar)
    model = resources_root / "models" / "ggml-base.en.bin"
    model_before = sha256(model) if model.is_file() else ""

    external_source = results_dir / "external-source-lecture.mp4"
    external_source.write_bytes(b"LecturePack external-source fixture v2.0.1\n")
    external_before = sha256(external_source)

    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    notes: list[str] = []

    # Existing-user upgrade, demo skip/finish, and replay all share a real
    # disposable library so the gate proves normal jobs survive each demo run.
    upgrade_dir = data_root / "existing-user"
    upgrade_dir.mkdir()
    config = ConfigManager(str(upgrade_dir))
    config.settings.update({
        "guided_tour_version": 1,
        "guided_tour_seen_version": 1,
        "guided_tour_status": "completed",
    })
    config.save()
    real_ids = [
        make_job(upgrade_dir, external_source, "Real lecture A"),
        make_job(upgrade_dir, external_source, "Real lecture B"),
    ]
    session = start_sidecar(sidecar, resources_root, upgrade_dir, demo, timeout)
    try:
        health = session.request("health_check")
        fatal_checks = [
            item for item in health.get("checks", [])
            if isinstance(item, dict) and item.get("fatal_at_startup")
        ]
        check(
            health.get("startup_ok") is True
            and all(item.get("ok") is True for item in fatal_checks),
            checks,
            "runtime_setup_fatal_checks",
            {"startup_ok": health.get("startup_ok"), "checks": health.get("checks", [])},
            details,
        )
        optional_failed = [
            item.get("id") for item in health.get("checks", [])
            if isinstance(item, dict) and not item.get("ok")
            and not item.get("fatal_at_startup")
        ]
        if optional_failed:
            notes.append("optional packaged checks unavailable: " + ", ".join(map(str, optional_failed)))

        listed = session.request("list_jobs")
        tour = listed.get("guided_tour") or {}
        check(
            set(real_ids).issubset({str(job.get("id")) for job in listed.get("jobs", [])}),
            checks,
            "existing_jobs_loaded",
            listed.get("jobs", []),
            details,
        )
        check(
            tour.get("version") == "2.0.1"
            and tour.get("eligible") is True
            and tour.get("completed") is False
            and tour.get("skipped") is False,
            checks,
            "existing_user_tour_eligible",
            tour,
            details,
        )

        skipped_import = session.request(
            "import_video", {"path": str(demo), "bundled_demo": True}
        )
        skip_job = str(skipped_import.get("job_id") or "")
        skip_session = str(skipped_import.get("demo_session_id") or "")
        check(bool(skip_job and skip_session and skipped_import.get("is_demo") is True),
              checks, "demo_identity_on_start", skipped_import, details)
        skip_end = session.request(
            "end_demo_job", {"job_id": skip_job, "reason": "tour_skip"}
        )
        check(skip_end.get("ok") is True and skip_end.get("status") in {"cleaned", "not_running"},
              checks, "demo_skip_cleanup", skip_end, details)
        after_skip = session.request("list_jobs")
        after_skip_ids = {str(job.get("id")) for job in after_skip.get("jobs", [])}
        check(set(real_ids).issubset(after_skip_ids) and skip_job not in after_skip_ids,
              checks, "skip_preserves_real_jobs", after_skip.get("jobs", []), details)
        check(skip_job not in {str(item.get("id")) for item in after_skip.get("queue", [])},
              checks, "skip_clears_queue_identity", after_skip.get("queue", []), details)
        check((after_skip.get("guided_tour") or {}).get("skipped") is True,
              checks, "skip_persists_tour_state", after_skip.get("guided_tour"), details)

        replay = session.request("replay_guided_tour")
        check(replay.get("ready_to_start") is True and (replay.get("guided_tour") or {}).get("eligible") is True,
              checks, "replay_command_resets_offer", replay, details)
        completed_import = session.request(
            "import_video", {"path": str(demo), "bundled_demo": True}
        )
        completed_job = str(completed_import.get("job_id") or "")
        complete_end = session.request(
            "end_demo_job", {"job_id": completed_job, "reason": "tour_complete"}
        )
        after_complete = session.request("list_jobs")
        complete_ids = {str(job.get("id")) for job in after_complete.get("jobs", [])}
        check(complete_end.get("ok") is True and completed_job not in complete_ids,
              checks, "demo_finish_cleanup", complete_end, details)
        check(set(real_ids).issubset(complete_ids), checks, "replay_preserves_real_jobs",
              after_complete.get("jobs", []), details)
        check((after_complete.get("guided_tour") or {}).get("completed") is True,
              checks, "finish_persists_tour_state", after_complete.get("guided_tour"), details)
    finally:
        clean_shutdown(session)

    # A marked demo left by a killed sidecar is removed on the next launch.
    reconcile_dir = data_root / "crash-reconcile"
    reconcile_dir.mkdir()
    make_job(reconcile_dir, external_source, "Real lecture after crash")
    session = start_sidecar(sidecar, resources_root, reconcile_dir, demo, timeout)
    crashed_job = ""
    try:
        imported = session.request("import_video", {"path": str(demo), "bundled_demo": True})
        crashed_job = str(imported.get("job_id") or "")
        check(bool(crashed_job), checks, "crash_fixture_demo_created", imported, details)
        crash_shutdown(session)
    finally:
        if session.proc is not None and session.proc.poll() is None:
            session.close()
    session = start_sidecar(sidecar, resources_root, reconcile_dir, demo, timeout)
    try:
        recovered = session.request("list_jobs")
        recovered_ids = {str(job.get("id")) for job in recovered.get("jobs", [])}
        check(crashed_job not in recovered_ids, checks, "crash_reconciles_demo", recovered, details)
        check(not (reconcile_dir / "demo-session.json").exists(), checks,
              "crash_removes_demo_marker", None, details)
    finally:
        clean_shutdown(session)

    # Existing-ID queue contract: supplied order and duplicate idempotency are
    # observed before the disposable queue worker is torn down.
    queue_dir = data_root / "queue-contract"
    queue_dir.mkdir()
    queue_ids = [make_job(queue_dir, external_source, f"Queue lecture {i}") for i in range(3)]
    session = start_sidecar(sidecar, resources_root, queue_dir, demo, timeout)
    try:
        queued = session.request("queue_jobs", {"job_ids": queue_ids})
        check(queued.get("queued_ids") == queue_ids and queued.get("count") == len(queue_ids),
              checks, "queue_existing_ids_ordered", queued, details)
        duplicate = session.request("queue_jobs", {"job_ids": queue_ids})
        check(duplicate.get("queued_ids") == [] and all(
            row.get("reason") in {"already_queued", "active", "done", "failed", "cancelled"}
            for row in duplicate.get("skipped", [])
        ), checks, "queue_existing_ids_idempotent", duplicate, details)
    finally:
        crash_shutdown(session)

    # Reset only known app-owned state and leave the external source and
    # packaged model byte-identical.
    reset_dir = data_root / "reset-fixture"
    reset_dir.mkdir()
    make_job(reset_dir, external_source, "Reset lecture")
    (reset_dir / "downloads").mkdir()
    (reset_dir / "downloads" / "owned.mp4").write_bytes(b"owned LecturePack media")
    (reset_dir / "study").mkdir()
    (reset_dir / "study" / "progress.json").write_text("{\"progress\": 1}\n", encoding="utf-8")
    for name in ("queue.json", "downloads-state.json", "bookmarks.json", "session.json", "settings.json"):
        (reset_dir / name).write_text("{}\n", encoding="utf-8")
    reset_config = ConfigManager(str(reset_dir))
    reset_config.settings["guided_tour_status"] = "completed"
    reset_config.settings["guided_tour_seen_version"] = 2
    reset_config.save()
    session = start_sidecar(sidecar, resources_root, reset_dir, demo, timeout)
    try:
        reset = session.request("reset_lecturepack")
        check(reset.get("ok") is True and reset.get("relaunch_required") is True,
              checks, "sidecar_reset_completed", reset, details)
        reset_list = session.request("list_jobs")
        reset_tour = reset_list.get("guided_tour") or {}
        check(not reset_list.get("jobs") and not (reset_dir / "jobs").exists(),
              checks, "reset_clears_owned_jobs", reset_list, details)
        check(reset_tour.get("eligible") is True and reset_tour.get("completed") is False,
              checks, "reset_restores_tour_offer", reset_tour, details)
        check(not (reset_dir / "downloads").exists() and not (reset_dir / "study").exists(),
              checks, "reset_clears_owned_media_and_study", None, details)
    finally:
        clean_shutdown(session)

    external_after = sha256(external_source)
    model_after = sha256(model) if model.is_file() else ""
    check(external_before == external_after, checks, "external_source_preserved",
          {"before": external_before, "after": external_after}, details)
    check(bool(model_before) and model_before == model_after, checks,
          "packaged_model_preserved", {"before": model_before, "after": model_after}, details)

    result = {
        "candidate": str(app_dir.resolve()),
        "sidecar": str(sidecar.resolve()),
        "data_root": str(data_root.resolve()),
        "checks": checks,
        "details": details,
        "notes": notes,
        "passed": all(checks.values()),
    }
    (results_dir / "polish-packaged-state-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--demo-video", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()
    result = run_gate(
        args.app_dir.resolve(), args.data_dir.resolve(), args.results_dir.resolve(),
        args.demo_video.resolve(), max(30.0, args.timeout_seconds),
    )
    print(json.dumps({"passed": result["passed"], "checks": result["checks"]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
