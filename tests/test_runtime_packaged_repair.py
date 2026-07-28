"""Real disposable frozen-onedir repair proof; no developer runtime substitute."""
from __future__ import annotations

import os
from pathlib import Path

from app.packaging import build


def test_disposable_packaged_repair_proof_uses_signed_current_onedir() -> None:
    fixture = os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "").strip()
    assert fixture, "clean onedir fixture is required: set LECTUREPACK_ONEDIR_FIXTURE"

    proof = build.run_disposable_packaged_repair_proof(Path(fixture), timeout_ms=30_000)

    assert proof["fixture_executable_sha256"]
    assert proof["repaired_active_generation"] != proof["previous_generation"]
    assert proof["admission_state"] == "HEALTHY"
    assert proof["damaged_admission_state"] == "SETUP_REQUIRED"
    assert proof["rollback_generation"] == proof["repaired_active_generation"]
    assert proof["cancel_generation"] == proof["repaired_active_generation"]
    evidence = proof["smoke_evidence"]
    assert evidence["argv"] and evidence["exit_code"] == 0
    assert evidence["duration_ms"] < 30_000
    assert "backend" in f"{evidence['stdout']}\n{evidence['stderr']}".lower()
