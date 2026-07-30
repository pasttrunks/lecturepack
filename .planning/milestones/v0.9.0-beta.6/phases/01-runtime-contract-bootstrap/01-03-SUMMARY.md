---
phase: 01-runtime-contract-bootstrap
plan: 03
subsystem: desktop runtime admission and diagnostics
tags: [runtime-bootstrap, qwebchannel, diagnostics, startup, pytest]
dependency_graph:
  requires: [01-01, 01-02]
  provides: [admitted desktop adapter path, canonical runtime-health JSON]
  affects: [phase-2-setup-gate, desktop-diagnostics]
tech_stack:
  added: []
  patterns: [bootstrap-before-adapter, controller-service diagnostics projection]
key_files:
  created: [lecturepack/controllers/runtime_diagnostics_controller.py, lecturepack/services/runtime_diagnostics.py, tests/test_runtime_diagnostics.py]
  modified: [app/desktop/bridge.py, app/desktop/engine_adapter.py, tests/test_adapter_startup.py, docs/HANDOFF_PHASE_1.md]
decisions:
  - Backend owns runtime admission and constructs no adapter before HEALTHY.
  - Runtime diagnostics transport serializes one controller/service snapshot and never rebuilds required inventory.
metrics:
  duration: 32m
  completed: 2026-07-28
status: complete
---

# Phase 01 Plan 03: Desktop Admission and Diagnostics Summary

The active desktop bridge now admits the real adapter only after canonical CPU health, and QWebChannel reads the same persisted runtime-health evidence through a controller/service boundary.

## Completed Tasks

1. Added test-first startup ordering contracts and gated `Backend` adapter creation on `RuntimeBootstrapService` `HEALTHY` admission.
2. Added test-first runtime diagnostics contracts and a read-only controller/service snapshot that carries canonical identity, admission state, validation mode, components, and optional fallback evidence.
3. Replaced the stale Phase 1 handoff with actual bootstrap, diagnostics, smoke, ADR, blocker, and test evidence.

## Verification

- `pytest tests/test_adapter_startup.py tests/test_runtime_diagnostics.py tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py -q` with `LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack` — **19 passed in 10.82s**.
- `LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack; pytest -q` — **728 passed in 179.15s**.

## Task Commits

1. Startup RED: `75fd1d1`; startup admission GREEN: `1617762`.
2. Diagnostics RED: `64624af`; diagnostics GREEN: `22988fa`; bridge-channel regression fix: `026a1c0`.
3. Honest Phase 1 handoff: `44b7158`.

## Deviations from Plan

### Auto-fixed Issues

1. [Rule 3 - Blocking integration] The full suite rejects newly declared Python bridge signals that are absent from the immutable web signal registry.
   - Found during: Task 2 full verification.
   - Fix: kept fallback post-HEALTHY and distinct as a typed payload on existing `diagnostics`, avoiding unauthorized `app/ui/bridge.js` changes.
   - Commit: `026a1c0`.

## Known Stubs

None. Phase 2 setup/repair and release-verifier work are intentionally deferred, not stubs in this plan.

## Phase 2 Readiness

AD-19 is approved, but repair implementation remains unstarted and must not begin until its ADR post-checkpoint task passes the approved signature vectors.

## Self-Check: PASSED

- Required source, tests, handoff, and this summary exist.
- Task commits `75fd1d1`, `1617762`, `64624af`, `22988fa`, `026a1c0`, and `44b7158` exist.
