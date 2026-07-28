"""Static contract for the approval-gated Phase 2 signing decision.

The pending branch is intentionally green: it proves that all security-relevant
fields are conspicuously unresolved, no verifier dependency is implied, and
Phase 2 remains closed until named-human approval and concrete vectors arrive.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
ADR = DECISIONS.split("## AD-19:", 1)[1]


def test_pending_adr_visibly_enumerates_every_unresolved_field() -> None:
    assert "**Status:** Pending named-human approval" in ADR
    required_fields = (
        "verifier library and exact version", "algorithm", "signature encoding",
        "public-key encoding", "canonical manifest schema and bytes",
        "exact app-version release asset naming",
        "embedded public-key format and location", "signing owner", "release owner",
        "approver", "key custodian", "backup authority and storage",
        "rotation cadence and trigger", "revocation authority and mechanism",
        "incident communication authority and path",
        "PyInstaller collection and frozen onedir proof", "retained evidence",
    )
    for field in required_fields:
        line = next((line for line in ADR.splitlines() if f"| {field} |" in line), "")
        assert "PENDING" in line, f"{field} must remain visibly pending"


def test_pending_adr_proposes_without_selecting_a_verifier_or_dependency() -> None:
    assert "propose `cryptography==49.0.0`" in ADR
    assert "No verifier is selected" in ADR
    assert "no verifier dependency is authorized" in ADR
    assert "no dependency is added in Phase 1" in ADR
    assert not (ROOT / "lecturepack" / "infrastructure" / "release_verifier.py").exists()


def test_pending_adr_keeps_phase_two_gate_closed() -> None:
    assert "Phase 2 repair/download/signature implementation remains\nclosed" in ADR
    assert "post-approval concrete-vector contract\npasses" in ADR
    assert "pending-state test intentionally verifies this closed gate" in ADR
