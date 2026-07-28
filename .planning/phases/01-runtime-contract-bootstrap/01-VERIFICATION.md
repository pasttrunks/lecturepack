---
phase: 01-runtime-contract-bootstrap
verified: 2026-07-28T15:51:29Z
status: passed
score: 9/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/9
  gaps_closed:
    - "Fresh onedir assembly now creates the canonical payload destination parents."
    - "Launch and full-validator exceptions now produce failed evidence and SETUP_REQUIRED."
    - "Full admission now proves staged canonical model and WAV transcription before persistence."
    - "Optional VAD model paths are staged to the private ASCII native-argv root."
    - "All adapter/updater bridge operations are guarded while setup is required."
  gaps_remaining: []
  regressions: []
requirements:
  RUNT-01: satisfied
  RUNT-02: satisfied
  RUNT-03: satisfied
  RUNT-04: satisfied
  RUNT-05: satisfied
  RUNT-06: satisfied
  RUNT-07: satisfied
  RUNT-08: satisfied
  RUNT-09: satisfied
---

# Phase 1: Runtime Contract & Bootstrap Verification Report

**Phase Goal:** A clean installation can deterministically establish and persist a healthy bundled CPU processing runtime before any normal application behavior begins.
**Verified:** 2026-07-28T15:51:29Z
**Status:** passed
**Re-verification:** Yes — after gap closure

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | RUNT-01 — Fresh portable profile discovers and validates the complete packaged CPU runtime without Settings input. | ✓ VERIFIED | `bundle_engine()` creates each canonical destination parent before copying. `test_bundle_engine_creates_runtime_parents_in_a_fresh_onedir` proves a clean synthetic onedir passes `check_clean_state()`. Direct packaged smoke copied the supplied clean onedir to a Unicode-and-space path, used a fresh profile, and completed real CPU transcription. |
| 2 | RUNT-02 — Startup, packaging, diagnostics, repair seams, and tests use one canonical required-runtime inventory. | ✓ VERIFIED | `runtime_inventory.py` supplies canonical/root-contained entries and payload identity; `build.py` and `RuntimeBootstrapService` consume it rather than recreating component membership. |
| 3 | RUNT-03 — Only complete validated facts persist as healthy runtime state. | ✓ VERIFIED | Full admission maps one complete smoke record (argv, exit, stdout/stderr, duration, timeout, reason) to all canonical CPU components. Corrupt-model and incomplete-evidence regressions retain `SETUP_REQUIRED` and do not persist health/migration state. |
| 4 | RUNT-04 — Launch applies the appropriate light/full validation and fails safely. | ✓ VERIFIED | Matching identity plus complete successful full evidence is required for light validation; first/update/repair/identity/partial evidence requires full validation. `RuntimeValidator` converts `OSError` launch failures to failed evidence; bootstrap catches unexpected validator errors as `SETUP_REQUIRED`. Full validation invokes staged `whisper-cli -m model.bin -f audio.wav -t 1 -nt` with bounded evidence. |
| 5 | RUNT-05 — No normal adapter readiness, job action, optional probe, navigation, demo, or update behavior starts before HEALTHY. | ✓ VERIFIED | Bridge constructs adapter/updater only after `assess()` returns HEALTHY. Its guarded operation registry intercepts all exposed adapter/updater operations during `SETUP_REQUIRED`, producing the JSON-safe `setup_required` diagnostics payload before collaborator access. Qt slot dispatch is covered too. |
| 6 | RUNT-06 — Base English becomes the beta-6 default once while later manual selections remain available. | ✓ VERIFIED | `ConfigManager.persist_runtime_health()` uses `migration_versions.runtime_contract == 1`, selects bundled base English only on the one-time migration, and retains a different existing/manual model thereafter. |
| 7 | RUNT-07 — A healthy selected optional engine remains selected while bundled CPU remains the validated recovery path. | ✓ VERIFIED | CPU admission happens before optional resolution; `_resolve_post_health_optional()` changes selection only when the requested optional CUDA/Vulkan engine resolves to CPU. The healthy-custom preference regression passes. |
| 8 | RUNT-08 — An unavailable optional engine visibly falls back to CPU after healthy admission. | ✓ VERIFIED | Post-health optional resolution emits typed `runtime_fallback` diagnostics and stores `engine=cpu`; it does not emit this notice as a ready event or probe optional engines before CPU health. |
| 9 | RUNT-09 — An approved ADR defines the signed-manifest verifier and release-authority contract required before repair. | ✓ VERIFIED | AD-19 is explicitly Approved and defines Ed25519/versioned dependency hash, raw encodings, canonical bytes/schema, exact asset origin/names, key custody/rotation/revocation, and PyInstaller proof requirements. Real fixed Ed25519 accept/reject vectors pass. The ADR expressly defers the compiled trust module, production verifier, signing workflow, and frozen self-test proof to Phase 2; none is falsely claimed implemented in Phase 1. |

**Score:** 9/9 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `lecturepack/infrastructure/runtime_inventory.py` | Canonical CPU runtime contract | ✓ VERIFIED | Ordered root-contained inventory, nonempty resolution, and content identity are substantive and consumed by package/bootstrap/smoke code. |
| `app/packaging/build.py` | Clean onedir payload assembly and disposable smoke | ✓ VERIFIED | Copies exactly canonical payloads after `destination.parent.mkdir(...)`; smoke runs FFmpeg/ffprobe and staged Whisper, rejects output artifacts, and cleans staging. |
| `lecturepack/infrastructure/runtime_validation.py` | Bounded command evidence | ✓ VERIFIED | Argument-array process execution records command, exit, streams, duration and reason; OSError and timeout return failed `SmokeEvidence`. |
| `lecturepack/services/runtime_bootstrap.py` | Fail-closed admission and persistence policy | ✓ VERIFIED | Requires complete successful evidence before persistence; failure/exception paths return `SETUP_REQUIRED` before migration or optional resolution. |
| `lecturepack/infrastructure/whisper_path_staging.py` and `whisper_wrapper.py` | Unicode-safe native inputs | ✓ VERIFIED | Model, WAV, output prefix, and optional VAD model use byte-checked ASCII staging with shared cleanup. |
| `app/desktop/bridge.py` | Healthy-only desktop boundary | ✓ VERIFIED | Central guard prevents collaborator construction/dereference and returns/emits truthful canonical diagnostics while setup is required. |
| `docs/DECISIONS.md` and `tests/test_signing_adr_contract.py` | Approved AD-19 contract | ✓ VERIFIED | Approved contract plus real Ed25519 known-good and altered-byte rejection vector tests; no prohibited Phase 2 verifier implementation observed. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- |
| Packaging | canonical inventory | `canonical_inventory()` / `required_runtime_payload()` | WIRED | Assembly, clean-state validation, and smoke use canonical paths. |
| Bootstrap | canonical inventory and validator | `resolve_inventory()` → `_validate_full()` → `RuntimeValidator` | WIRED | Full admission runs real staged canonical model/WAV transcription and maps its evidence to required components. |
| Persisted health | light/full admission decision | identity + complete-evidence check in `_requires_full()` | WIRED | Partial/failed/mismatched evidence cannot silently take the light path. |
| Backend | bootstrap | `Backend.__init__()` assesses before `make_adapter()`/`Updater()` | WIRED | Setup-required bridge calls are intercepted before collaborator access. |
| Bridge | canonical diagnostics | `RuntimeDiagnosticsController` snapshot | WIRED | `get_bootstrap()`, setup-required payload, and detailed snapshot share the controller-owned projection. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `RuntimeBootstrapService` | `components` / `runtime_health` | resolved packaged payload plus real FFmpeg/ffprobe/Whisper smoke evidence | Yes — real packaged executable/DLL/model/WAV evidence | ✓ FLOWING |
| `Backend` | `runtime_health_result` / diagnostics snapshot | bootstrap assessment through diagnostics controller | Yes — healthy/setup-required state is projected to bridge consumers | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Former gap closures and AD-19 vectors | Selected 18 focused pytest cases across packaging, bootstrap, real packaged smoke, VAD staging, bridge dispatch, and signing ADR | `18 passed in 15.68s` | ✓ PASS |
| Real disposable package runtime | `test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile` with supplied `LECTUREPACK_ONEDIR_FIXTURE` | Included above; runs real `whisper-cli` from a disposable Unicode-and-space copy with a fresh profile | ✓ PASS |
| Final focused regression evidence | Runtime + packaged focused suite | Reported independent evidence: `19 passed in 15.95s` | ✓ PASS |
| Final full-suite regression evidence | `pytest -q` | Reported independent evidence: `740 passed in 191.41s` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| RUNT-01 | 01-01, 01-05, 01-06 | Fresh packaged CPU discovery/admission | ✓ SATISFIED | Fresh onedir parent-creation regression and real Unicode/space disposable smoke. |
| RUNT-02 | 01-01, 01-03 | Shared canonical inventory | ✓ SATISFIED | Inventory feeds packaging, bootstrap, smoke, identity, and diagnostics. |
| RUNT-03 | 01-02, 01-05, 01-06 | Persist only complete validated health | ✓ SATISFIED | Corrupt/incomplete/exception evidence stays setup-required without persistence. |
| RUNT-04 | 01-01, 01-02, 01-05, 01-06 | Light/full checks and safe bounded failures | ✓ SATISFIED | Complete-evidence admission, staged transcription, OSError/timeout handling. |
| RUNT-05 | 01-03, 01-07 | No normal behavior pre-health | ✓ SATISFIED | Healthy-only construction plus exhaustive guarded bridge/Qt dispatch tests. |
| RUNT-06 | 01-02 | One-time base-English migration | ✓ SATISFIED | Migration marker preserves later choice. |
| RUNT-07 | 01-02 | Healthy optional preference preserved | ✓ SATISFIED | Optional resolution post-CPU; custom-choice regression. |
| RUNT-08 | 01-02, 01-03 | Visible CPU fallback | ✓ SATISFIED | Typed post-health `runtime_fallback` diagnostics. |
| RUNT-09 | 01-04 | Approved signed verifier contract | ✓ SATISFIED | AD-19 approval and real vectors; frozen verifier proof remains a Phase 2 gate. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| — | — | No unresolved `TBD`/`FIXME`/`XXX`, placeholder, empty handler, hardcoded visible empty-data, or unguarded setup-required collaborator pattern found in Phase 1 gap-closure implementation files. | ℹ️ Info | No blocker. |

### Scope Preservation

The Phase 1 gap-closure commit range (`dca41f5^..284b1c4`) contains no `app/ui/`, `lecturepack/ui/`, CSS, HTML, JavaScript, QSS, animation, motion, shadow, or theme asset change. The beta-5 visual contract was therefore not altered by this closure work.

### Gaps Summary

No Phase 1 gap remains. The Phase 1 contract deliberately does **not** implement signed repair, a production verifier/trust-root module, signing workflow, or frozen PyInstaller verifier proof. AD-19 defines and approves those requirements and makes the frozen verifier proof an explicit Phase 2 gate; this is an intentional, documented phase boundary rather than a missing Phase 1 deliverable.

---

_Verified: 2026-07-28T15:51:29Z_
_Verifier: the agent (gsd-verifier)_
