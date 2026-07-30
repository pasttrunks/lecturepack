---
phase: 02-hard-setup-signed-repair
plan: 01
subsystem: infrastructure
tags: [ed25519, cryptography, signed-manifest, runtime-repair, security]
requires:
  - phase: 01-runtime-contract-bootstrap
    provides: approved AD-19 signing contract and canonical runtime inventory
provides:
  - strict Ed25519 signed-manifest trust verifier
  - immutable exact-version release layout and frozen accept/reject vector
  - metadata-only authenticated repair offer with checked archive total
affects: [runtime-generation, runtime-repair, setup-gate, packaged-verifier]
tech-stack:
  added: [cryptography==49.0.0]
  patterns: [verify raw bytes before parsing, canonical JSON allowlists, fixed-origin release metadata]
key-files:
  created:
    - lecturepack/infrastructure/release_trust.py
    - tests/test_release_trust.py
    - tests/fixtures/release_trust/manifest.json
    - tests/fixtures/release_trust/manifest.sig
    - tests/fixtures/release_trust/manifest-altered.json
    - tests/fixtures/release_trust/release-layout.json
  modified: []
key-decisions:
  - "Release metadata is authenticated as exact raw Ed25519 bytes before any UTF-8 or JSON parsing."
  - "Repair confirmation derives its affected components and unsigned-64-bit archive total solely from authenticated metadata and current admission evidence."
patterns-established:
  - "Release trust remains Qt-free and has no transport, archive extraction, or filesystem mutation capability."
  - "Exact-version fixed URLs and strict component/file allowlists replace release discovery and flexible asset selection."
requirements-completed: [REPR-03, REPR-04, REPR-05, REPR-06]
coverage:
  - id: D1
    description: "Frozen Ed25519 manifest vector authenticates exact canonical bytes and rejects an altered byte."
    requirement: REPR-05
    verification:
      - kind: unit
        ref: tests/test_release_trust.py#test_frozen_manifest_authenticates_before_parsing_and_altered_byte_fails
        status: pass
    human_judgment: false
  - id: D2
    description: "The exact six-asset official release contract and checked four-ZIP byte total are enforced."
    requirement: REPR-04
    verification:
      - kind: unit
        ref: tests/test_release_trust.py#test_exact_six_asset_layout_and_checked_archive_total
        status: pass
    human_judgment: false
  - id: D3
    description: "Malformed signature, canonical JSON, schema, asset, path, duplicate, inventory, and size-overflow cases fail closed."
    requirement: REPR-06
    verification:
      - kind: unit
        ref: python -m pytest tests/test_release_trust.py tests/test_signing_adr_contract.py -q
        status: pass
    human_judgment: false
duration: 24min
completed: 2026-07-28
status: complete
---

# Phase 02 Plan 01: Signed Release Trust Root Summary

**Fail-closed Ed25519 verification for an exact-version, six-asset runtime release with frozen raw-byte vectors and metadata-only repair offers.**

## Performance

- **Duration:** 24 min
- **Completed:** 2026-07-28
- **Tasks:** 3/3 (including the approved provenance gate)
- **Files modified:** 7

## Accomplishments

- Recorded approved `cryptography==49.0.0` provenance: the project/version and Windows x64 wheel SHA-256 match AD-19.
- Added immutable signed/altered release-manifest vectors and the exact R1 six-asset layout.
- Implemented a Qt-free verifier that authenticates raw bytes before strict canonical parsing and exposes no network or installation behavior.
- Added fixed official URLs, four-archive validation, checked unsigned-64-bit totals, archive-member safety checks, and metadata-only offer derivation.

## Task Commits

1. **Task 1: Lock the signed release bytes and exact layout contract** — `f578ada` (test)
2. **Task 2: Implement fail-closed exact-byte release trust verification** — `650ee7d` (feat)

## Files Created/Modified

- `lecturepack/infrastructure/release_trust.py` — deterministic trust policy, immutable records, exact URLs, and fail-closed validators.
- `tests/test_release_trust.py` — frozen-vector and malformed-input regression coverage.
- `tests/fixtures/release_trust/` — signed known-good bytes, altered bytes, and complete release layout.

## Decisions Made

- Verified metadata is the sole pre-consent input: the authenticated offer never acquires archive bytes.
- Exact asset names are generated from the running app version under the locked official GitHub release origin.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected frozen fixture byte representation and signing-key ID**
- **Found during:** Task 2
- **Issue:** Text-file creation added a trailing newline to a canonical signed manifest, and its key ID was not the SHA-256-derived ID required by AD-19.
- **Fix:** Rewrote the frozen manifest without a newline, retained the detached signature as exactly 64 raw bytes, and regenerated the synthetic fixture signature with the correct key ID.
- **Files modified:** `tests/fixtures/release_trust/manifest.json`, `manifest.sig`, `manifest-altered.json`
- **Verification:** `python -m pytest tests/test_release_trust.py tests/test_signing_adr_contract.py -q` — 24 passed.
- **Committed in:** `650ee7d`

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).
**Impact on plan:** Required to preserve the plan's exact-byte and raw-signature security contract; no scope expansion.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The later repair transaction can consume only the typed authenticated manifest and offer. It must retain the fixed-origin/no-pre-consent-payload boundary and use the canonical runtime inventory during staged generation validation.

## Self-Check: PASSED

- All six planned trust artifacts exist.
- Task commits `f578ada` and `650ee7d` exist in git history.
- Final focused verification passed: `24 passed in 0.14s`.

---
*Phase: 02-hard-setup-signed-repair*
*Completed: 2026-07-28*
