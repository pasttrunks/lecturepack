---
phase: 02
slug: hard-setup-signed-repair
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-28
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 with pytest-qt |
| **Config file** | `pytest.ini` |
| **Quick run command** | `python -m pytest tests/test_release_trust.py tests/test_runtime_generation.py tests/test_runtime_repair.py tests/test_setup_gate_repair.py -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | Targeted: under 60 seconds; full suite: about 210 seconds |

---

## Sampling Rate

- **After every task commit:** Run the narrowest relevant Phase 2 test file, then the quick run command once all four target files exist.
- **After every plan wave:** Run `python -m pytest -q`.
- **Before `$gsd-verify-work`:** The full suite, signed verifier vectors, fault matrix, disposable PyInstaller verifier self-test, and real packaged repaired-runtime smoke must be green.
- **Max feedback latency:** 60 seconds for task-level automated feedback; about 210 seconds at wave boundaries.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-W0-01 | TBD | 0 | REPR-05, REPR-06 | T-02-01, T-02-02, T-02-03 | Signature, manifest, inventory, and archive validation fail closed | unit/fault matrix | `python -m pytest tests/test_release_trust.py -q` | ❌ W0 | ⬜ pending |
| 02-W0-02 | TBD | 0 | REPR-07, REPR-08 | T-02-04 | Staging, cancellation, activation failure, and rollback preserve the old generation | filesystem integration | `python -m pytest tests/test_runtime_generation.py tests/test_runtime_repair.py -q` | ❌ W0 | ⬜ pending |
| 02-W0-03 | TBD | 0 | REPR-01, REPR-02, REPR-03, REPR-04, REPR-09, REPR-10 | T-02-05, T-02-06 | Gate blocks normal entry; consent precedes network; success reruns admission; offline exposes only allowed actions | bridge/UI integration | `python -m pytest tests/test_setup_gate_repair.py -q` | ❌ W0 | ⬜ pending |
| 02-E2E-01 | TBD | final | REPR-05, REPR-06 | T-02-01 | Frozen verifier accepts the approved real vector and rejects an altered manifest byte | packaged integration | Plan-defined disposable PyInstaller verifier self-test command | ❌ W0 | ⬜ pending |
| 02-E2E-02 | TBD | final | REPR-07, REPR-09 | T-02-04 | Real repaired runtime passes canonical admission under Unicode and space paths | packaged integration | Plan-defined disposable packaged-runtime smoke command | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/fixtures/release_trust/` — immutable known-good signed manifest, detached signature, altered-byte vector, archive fixtures, and explicit complete release-layout table.
- [ ] `tests/test_release_trust.py` — exact-byte Ed25519, schema/version/key-id, hash, unsafe path, duplicate, missing, extra, and mixed-release rejection.
- [ ] `tests/test_runtime_generation.py` — active-generation resolver and atomic pointer contract tests.
- [ ] `tests/test_runtime_repair.py` — transaction fault injection for download, write, permission, cancel, validation, and activation failures without real GitHub access.
- [ ] `tests/test_setup_gate_repair.py` — bootstrap gate, guarded commands, consent-before-network, progress/failure/offline actions, success readmission, and collaborator-construction ordering.
- [ ] Disposable PyInstaller verifier harness and real packaged repaired-runtime smoke harness, with executable/wheel hashes, build log, captured argv, exit code, duration, stdout, and stderr.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Gate overlay preserves beta-5 shadows, embedded pressed states, motion, and transitions without exposing the app underneath to interaction | REPR-01, REPR-02 | Offscreen Qt/DOM assertions cannot prove rendered motion quality or interaction blocking across the packaged desktop stack | Launch a disposable packaged build with a deliberately unhealthy runtime; capture the initial gate, confirmation, progress, failure, diagnostics, offline, and success states; verify keyboard, pointer, and focus cannot reach the underlying app; compare button/motion behavior with beta 5 |
| Cancel remains available and takes effect at a safe boundary during visible repair progress | REPR-08 | Timing and perceived responsiveness require packaged interactive observation in addition to deterministic cancellation tests | Begin a disposable repair, cancel during download and during staged installation, confirm the gate returns with the previous generation active and no partial content exposed |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive tasks without automated verification.
- [ ] Wave 0 covers every missing test reference.
- [ ] No watch-mode flags are used.
- [ ] Task feedback latency is under 60 seconds and wave feedback is under about 210 seconds.
- [ ] Real cryptographic vectors and packaged integrations are not replaced by mocked proof.
- [ ] `nyquist_compliant: true` is set only after execution evidence closes every mapped behavior.

**Approval:** pending
