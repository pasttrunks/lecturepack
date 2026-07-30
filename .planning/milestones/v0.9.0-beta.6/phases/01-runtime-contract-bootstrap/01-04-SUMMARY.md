---
phase: 01-runtime-contract-bootstrap
plan: 04
subsystem: release trust contract
tags: [security, signing, ed25519, cryptography, adr]
dependency_graph:
  requires: [01-01]
  provides: [approved Phase 2 signed-repair trust contract]
  affects: [Phase 2 runtime repair]
tech_stack:
  added: [cryptography==49.0.0]
  patterns: [Ed25519 detached verification of byte-exact canonical manifests]
key_files:
  created: [tests/test_signing_adr_contract.py]
  modified: [docs/DECISIONS.md, requirements.txt, app/requirements.txt]
decisions:
  - AD-19 approves cryptography==49.0.0 and pure Ed25519 detached signatures over exact canonical manifest bytes.
  - The release trust root will be compiled into a future application release; Phase 2 implementation remains deferred.
metrics:
  duration: 17m
  completed: 2026-07-28
status: complete
---

# Phase 01 Plan 04: Approved Signing Contract Summary

AD-19 now provides a byte-exact Ed25519 repair-release contract with a real known-good and altered-byte rejection vector, while deferring all repair implementation to Phase 2.

## Completed Tasks

1. Preserved the pre-approval draft and checkpoint commit (`ca48037`).
2. Added a RED-stage contract test with literal Ed25519 public key, canonical manifest bytes, known-good signature, altered-byte/signature rejection, and invalid-key-length cases (`3c5e2fb`).
3. Recorded the named approval and every selected security/operations value in AD-19, then pinned the approved verifier dependency in both authorized requirements files (`b648c02`).

## Decisions Made

- `cryptography==49.0.0` is the approved verifier dependency. The official Windows x64 wheel `cryptography-49.0.0-cp311-abi3-win_amd64.whl` was obtained in a safe temporary directory and SHA-256 verified as `e5dfc1e64de5677cec922ffa8da89c546d0415bf6efdf081842e5d44c84e1f0e` before use; the installed version was already `49.0.0`, so no reinstall was needed.
- A detached pure Ed25519 signature authenticates exact canonical manifest bytes only. The static test uses public key `03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8`, key ID `56475aa75463474c`, and a literal 64-byte signature.
- `pasttrunks` is signing/release/key-lifecycle owner and self-approver. The lack of separation of duties and GitHub Actions artifact expiry are accepted risks recorded in AD-19.
- Phase 2 is contractually open only after the complete approved ADR test and both real signature vectors pass. This plan did not implement repair/downloads, a production verifier, signing workflow, compiled trust module, or frozen self-test.

## Verification

- `pytest tests/test_signing_adr_contract.py -q` — **9 passed in 0.08s**.
- `LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack; pytest -q` — **723 passed in 184.39s (0:03:04)**.

## Deviations from Plan

### Auto-fixed Issues

1. [Rule 2 - Critical functionality] Added the explicitly approved `cryptography==49.0.0` dependency to root and app requirements.
   - **Found during:** Task 3 approval continuation.
   - **Issue:** The original plan predated named approval and therefore prohibited adding a verifier; the named approval explicitly authorized the dependency and real vectors.
   - **Fix:** Hash-verified the official Windows x64 wheel, confirmed the installed version, pinned both authorized requirements files, and tested the real API.
   - **Files modified:** `requirements.txt`, `app/requirements.txt`.
   - **Commit:** `b648c02`.

## Known Stubs

None. Production release-verifier, compiled trust root, signing workflow, and frozen proof are intentionally deferred Phase 2 work, not stubs in this Phase 1 contract plan.

## Self-Check: PASSED

- Required ADR, test, and requirements files exist.
- Task commits `ca48037`, `3c5e2fb`, and `b648c02` exist in Git history.
