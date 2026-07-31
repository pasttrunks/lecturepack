---
phase: 01-clean-device-footprint-first-launch
plan: 02
subsystem: ci
tags: [ci, release, updater, github-actions, supply-chain]

# Dependency graph
requires: []
provides:
  - ".github/workflows/release.yml — publishes the three updater assets additively alongside the six signed AD-19 runtime assets"
  - "tests/test_release_asset_contract.py — 10 tests binding release.yml's published asset list to expected_asset_names()"
affects: [01-08-PLAN.md]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Consumer-contract test: the assertion set is derived from expected_asset_names() at test time rather than hardcoded, so the updater's own requirement is the single source of truth"
    - "Pre-publish existence gate in CI (test -s per asset + SHA256SUMS membership grep) so a missing asset fails the job instead of producing a silently incomplete release"
---

# Phase 1 Plan 2: Restore Installer Asset Publication (D-22) Summary

**`release.yml` publishes `Setup.exe`, `Portable.zip`, and `SHA256SUMS.txt` again — appended alongside the six signed runtime assets, never swapped for them — with 10 tests binding the published list to `expected_asset_names()` so the `a6164b1` regression cannot recur silently.**

## Accomplishments

- Restored `choco install innosetup` before the build step, and dropped `--no-installer` so `validate_release_assets(version, require_installer=True)` actually gates the build rather than being unreachable in CI.
- Appended the three updater asset paths to the release step's `files:` list. All six `runtime-release-assets/…` lines are byte-for-byte untouched — verified by reading the committed diff, not by assertion.
- Added an `Assert updater assets exist` step: each asset must be present and non-empty (`test -s`), and `SHA256SUMS.txt` must list `Setup.exe` and `Portable.zip`. A missing asset now fails the job before publication instead of producing a release the updater cannot consume.
- Restored prerelease-channel gating (`prerelease: ${{ contains(env.APP_VERSION, '-') }}`), which the pre-`a6164b1` job carried.
- `tests/test_release_asset_contract.py` — 10 tests, all passing. Coverage includes: the release step publishes every name `expected_asset_names()` requires (both installer and portable forms); the six signed AD-19 assets are still published and were not swapped away; asset paths are exact names, never globs; `--no-installer` is gone; Inno Setup is installed before the build; the pre-publish assertion exists; prerelease gating is preserved; and `select_asset` fails on a six-signed-assets-only release but succeeds once the installer assets are present.

## Task Commits

- `dcd6c11` — feat(01-02): additively restore installer asset publication to release.yml
- (this commit) — test(01-02): bind release.yml's asset list to expected_asset_names(); close out plan

## Files Created/Modified

- `.github/workflows/release.yml` — modified (20 insertions, 1 deletion)
- `tests/test_release_asset_contract.py` — created (195 lines, 10 tests)
- `.planning/phases/01-clean-device-footprint-first-launch/deferred-items.md` — created

## Decisions Made

Implements **D-22** in full. The signed-runtime assets serve the *repair* path (AD-19); the installer assets serve the *update* path. Both now coexist, which was the whole point — `a6164b1` had substituted one for the other.

## Deviations from Plan

### Interrupted mid-plan by an API session limit, closed out by the orchestrator

Task 1 committed cleanly as `dcd6c11`. The executor was killed by a session limit while writing `deferred-items.md`, leaving `tests/test_release_asset_contract.py` and `deferred-items.md` written but uncommitted and no SUMMARY.md — the safe-resume-gate condition. Rather than re-run the plan, the orchestrator verified the committed diff was correctly additive, ran the uncommitted test suite (10/10 pass), and closed the plan out. No work was redone and none was lost.

### Out-of-scope, logged not fixed

Seven pre-existing test failures were found and recorded in `deferred-items.md`, with a mutation check: reverting this plan's diff entirely leaves them failing identically, so they are not caused here. Root cause is a stale test fixture versus a rotated key — `tests/fixtures/release_trust/` was never regenerated after `55257a8` rotated the production Ed25519 key — plus `test_release_trust.py` still asserting a cryptography wheel hash-pin that `efb99cd`/`95dd5fb` removed from `release.yml`.

**This matters beyond bookkeeping:** four of those failures are in `tests/test_release_trust.py` and two more in the runtime-repair suite, all raising `manifest signature verification failed`. AD-19's signature-verification test coverage is therefore currently red for reasons predating this phase. Nothing in this plan weakens AD-19, and `tests/test_signing_adr_contract.py` (ADR-text and Ed25519 vectors) passes — but the trust-path regression tests are not currently guarding anything.

---

**Total deviations:** 1 interruption closed out without rework, 7 out-of-scope pre-existing failures logged.
**Impact on plan:** Both tasks complete, verified, committed. D-22 is satisfied and the phase may now claim "beta-6 updater behavior preserved" for the *publication* half. Note that CI itself has not been observed producing these assets — the guarantee rests on the workflow diff plus the contract tests, and a real tagged release is the only thing that proves it end to end.

## Issues Encountered

Recommend a follow-up task, outside this phase: regenerate `tests/fixtures/release_trust/manifest.json` and `manifest.sig` against the Ed25519 key currently set in `lecturepack/infrastructure/release_trust.py`, and update `test_release_trust.py`'s hash-pin assertion to match the current dependency-install step.

## Next Phase Readiness

Nothing blocks wave 2. `01-08` consumes this plan's guarantee when it records release-asset evidence.

---

## Self-Check: PASSED

- Six signed runtime assets confirmed present and unmodified in the committed diff.
- 10/10 contract tests pass.
- No build artifacts committed; `app/dist/` baseline left intact for `01-08`.
