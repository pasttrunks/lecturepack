# Deferred Items — Phase 01: Clean-Device Footprint & First Launch

Out-of-scope discoveries found during plan execution. Not fixed per the executor's
scope-boundary rule (only auto-fix issues directly caused by the current task's changes).

## Found during 01-02 (restore installer asset publication to release.yml)

**Pre-existing test failures in `tests/test_release_trust.py`, unrelated to plan 01-02's
changes.** Confirmed via `git log --oneline -- .github/workflows/release.yml`: the
cryptography wheel SHA256 pin these tests assert on was removed from `release.yml` at
commit `efb99cd` ("fix(ci): simplify cryptography installation in release workflow"),
well before plan 01-02's `dcd6c11`. Reverting plan 01-02's diff entirely (confirmed via
manual mutation-check swap) does not change these results — they fail identically on the
pre-01-02 workflow content.

Failing tests, run via
`pytest tests/test_update_service.py tests/test_update_integration.py tests/test_release_trust.py tests/test_signing_adr_contract.py -q`:

- `tests/test_release_trust.py::test_frozen_manifest_authenticates_before_parsing_and_altered_byte_fails`
  — `ReleaseTrustError: manifest signature verification failed`. The fixture's known-good
  manifest/signature pair no longer verifies against the currently-configured production
  Ed25519 public key (`lecturepack/infrastructure/release_trust.py`), likely stale since
  commit `55257a8` ("fix(security): set production Ed25519 signing key for release trust
  verification") rotated the key without regenerating `tests/fixtures/release_trust/`.
- `tests/test_release_trust.py::test_exact_six_asset_layout_and_checked_archive_total`
  — downstream of the same manifest-verification failure.
- `tests/test_release_trust.py::test_offer_uses_authenticated_metadata_and_admission_evidence_only`
  — downstream of the same manifest-verification failure.
- `tests/test_release_trust.py::test_release_workflow_binds_both_triggers_to_the_peeled_tag_before_signing`
  — asserts `release.yml` contains the literal cryptography wheel hash
  `e5dfc1e64de5677cec922ffa8da89c546d0415bf6efdf081842e5d44c84e1f0e`. That hash-pinned
  wheel-install step was replaced with `pip install cryptography==49.0.0` at `efb99cd`/
  `95dd5fb`; the test was never updated to match.

**Not fixed here** — plan 01-02's scope is the additive installer-asset restore plus its
own contract test (D-22). Regenerating `tests/fixtures/release_trust/` against the current
production key, or updating this test's hash-pin assertion, is a separate fix in
`lecturepack/infrastructure/release_trust.py` / `tests/test_release_trust.py`, files plan
01-02 does not touch.

**Verified unaffected by 01-02:** `tests/test_update_service.py` (23 tests) and
`tests/test_update_integration.py`, plus `tests/test_signing_adr_contract.py` (all AD-19
ADR-text and Ed25519-vector tests) — all pass. `tests/test_release_asset_contract.py`
(new, this plan) — 10/10 pass.

## Full-suite run, same root cause, also pre-existing

A full `pytest` run (877 passed, 7 failed) surfaced three more failures downstream of the
same stale-fixture-vs-rotated-key issue above — none of these files import or reference
`release.yml` or `app/desktop/update_service.py`, so plan 01-02's changes cannot be their
cause:

- `tests/test_runtime_packaged_repair.py::test_disposable_packaged_repair_proof_uses_signed_current_onedir`
- `tests/test_runtime_repair.py::test_offer_authenticates_only_manifest_and_signature_before_confirmation`
  — both raise `RepairFailure: manifest signature verification failed`, same root cause as
  `test_release_trust.py` above.
- `tests/test_runtime_packaged_smoke.py::test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile`
  — pre-flagged by the orchestrator as a known pre-existing failure requiring the
  `LECTUREPACK_ONEDIR_FIXTURE` env var, not this plan's to fix.

Recommend a follow-up task (outside 01-02's scope) to regenerate
`tests/fixtures/release_trust/manifest.json` / `manifest.sig` against the production
Ed25519 key set in `lecturepack/infrastructure/release_trust.py`, and to update
`test_release_trust.py`'s hash-pin assertion to match the current `release.yml`
dependency-install step.

## Found during 01-04 D-24 verification (orchestrator-owned build step)

**`app/requirements.txt` does not mirror the repo root `requirements.txt`, despite its own
header claiming it does.** Its comment reads "The engine deps below mirror the repo root
requirements.txt so `app/` can be installed on its own," but three declared root
dependencies are missing from it: `Send2Trash`, `tzdata`, and `yt-dlp`.

This is load-bearing because `.github/workflows/release.yml` installs
`-r app/requirements.txt -r app/requirements-build.txt` — so **CI builds have never
contained these three packages**. Local builds happened to contain `tzdata` only because
the developer's global Python environment had the root requirements installed. This is the
same class of defect as D-24 (packaged contents depending on developer-machine state)
but in the opposite direction: declared dependencies going *missing* rather than
undeclared ones being *collected*.

Per-package impact, measured against the pre-cut baseline tree:

| Package | Source usage | In baseline build | Consequence when absent |
|---|---|---|---|
| `Send2Trash` | `app/desktop/engine_adapter.py:1206` | **absent** | **Files are hard-deleted instead of sent to the recycle bin** |
| `tzdata` | `lecturepack/services/job_queue.py:18` (`from zoneinfo import ZoneInfo`) | bundled | Silent fallback to system-local time (`job_queue.py:186`), losing tz-aware scheduling |
| `yt-dlp` | `lecturepack/services/media_fetch.py:50` | absent | "Import from a link" hidden — **explicitly optional by design**, not a defect |

**`Send2Trash` is a user-data concern, not just a packaging one.** The guard at
`engine_adapter.py:1202` reads "Only a genuinely absent send2trash justifies a hard delete
now" — and in packaged builds it *is* genuinely absent, so the fallback path is the only
path. Packaged LecturePack permanently deletes user files where the source intends a
recoverable recycle-bin move. Root `requirements.txt` declares `Send2Trash>=1.8.0`, so the
intent is unambiguous; only the packaging path lost it.

**Not fixed here.** D-24 explicitly scoped out a broader dependency audit, and adding
`Send2Trash`/`yt-dlp` to the packaged set would change shipped behavior (deletion
semantics; a newly-appearing UI affordance) — a product decision, not a size cut. The
D-24 verification build therefore installed the locked `app/` requirements **plus `tzdata`
only**, so the post-cut tree matches the baseline's actual contents minus the intended
cuts and the before/after size comparison stays apples-to-apples.

**Recommended follow-up (its own slice):** make `app/requirements.txt` genuinely mirror
root — or have CI install both files — and decide deliberately whether packaged builds
should ship `Send2Trash` (restoring recycle-bin deletion) and `yt-dlp`. Add a test
asserting the two requirement sets agree, so the header's claim is enforced rather than
aspirational.
