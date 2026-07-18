# Phase 1 Handoff — Packaging & Release

**Updated:** 2026-07-18
**Branch:** `v1.2-hybrid-study`
**Status:** All three Phase 1 plans are complete; phase verification is next.

## Authorized Scope

Phase 1 packages, tests, validates, and publishes LecturePack v1.2.0. Phase 2 reliability work, live Groq validation, new dependencies, real user data/media, and original-video changes remain out of scope.

## Completed

- Plan 01-01 completed and summarized in `.planning/phases/01-packaging-release/01-01-SUMMARY.md`.
- Release version metadata is canonicalized at 1.2.0 and the PyInstaller spec/module inventory is guarded by focused tests.
- Plan 01-02 Tasks 1–2 completed: four alignment acceptance tests, clause-level traceability, and pytest collection reconciliation.
- Plan 01-02 Task 3 completed under accepted AD-15: architecture release validation is an exact-identity no-regression gate against commit `25e9dd1`; strict conformance remains the Phase 2 target.
- Plan 01-03 completed: the real 1.2.0 PyInstaller onedir and portable ZIP were built, inventoried, integrity-checked, and exercised from both onedir and a clean extraction path containing a space.

## Current Evidence

- Full suite: `158 passed in 113.56s`, exit 0.
- Current focused packaging suite: `7 passed in 0.97s`, exit 0.
- Development self-test: exit 0, timeout false, `SELFTEST PASS: LecturePack v1.2.0`.
- Privacy audit: PASS, zero violations.
- Architecture audit: PASS for Phase 1 no-regression, exit 0; baseline/current 47 forbidden imports across 62 cross-layer edges, zero new, zero resolved, 47 deferred.
- Strict architecture conformance: NO. The existing debt is disclosed and assigned to Phase 2.
- Traceability: `CURRENT_RUN_STATUS: PASS`; source validation: `OVERALL_STATUS: PASS`.
- Real release build: exit 0; `LecturePack-portable-1.2.0.zip` is 383,712,406 bytes.
- ZIP SHA-256: `f5680469c55b4420249b1cfcd264f4161d049080f9e2cfd17d551f2620715f9e`, equal across independent computation, `SHA256SUMS.txt`, and `BUILD_MANIFEST.json`.
- Onedir and ZIP runtime/document inventories: PASS; model/secret/config/job/transcript/slide/original-media exclusions: PASS.
- Onedir frozen self-test: timeout false, exit 0, `SELFTEST PASS: LecturePack v1.2.0`.
- Clean-extracted frozen self-test: timeout false, exit 0, `SELFTEST PASS: LecturePack v1.2.0`; validated extraction cleanup completed.

Evidence is under `docs/evidence/v1.2.0/release/`.

## Architecture Debt

`docs/ARCHITECTURE.md` requires each layer to call only the layer directly below and forbids direct UI-to-infrastructure calls. The current code has controller-to-infrastructure and UI-to-service/infrastructure imports. Repair is a broad production refactor outside Phase 1's packaging scope.

AD-15 preserves that rule while allowing Phase 1 packaging to proceed only when no exact violation identity is new relative to `25e9dd1`. Phase 2 owns closure of all 47 baseline violations. Do not describe the current tree as strictly conformant.

## Commits

- `6070968` — complete Plan 01-01 metadata.
- `1859585` — alignment acceptance coverage.
- `dc2a78d` — pytest collection reconciliation.
- `25e9dd1` — durable blocking architecture-audit evidence.
- `a41454a` — accepted architecture baseline and passing privacy/no-regression evidence.
- `5c97724` — real portable build and complete inventory evidence.
- `af20614` — retained initial pre-deletion release allowlist evidence.
- `35cd04e` — checksum and two-path frozen self-test evidence.

## Resume Point

Proceed to GSD phase verification and owner release approval. Do not begin Phase 2 until the Phase 1 approval gate is explicitly passed. Keep the 47-item architecture baseline visible in release reporting; strict conformance is not claimed and remediation remains Phase 2 work.
