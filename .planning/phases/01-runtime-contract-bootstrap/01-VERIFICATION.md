---
phase: 01-runtime-contract-bootstrap
verified: 2026-07-28T12:42:48Z
status: gaps_found
score: 5/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "A fresh portable profile finds and validates the complete packaged CPU runtime without Settings input."
    status: failed
    reason: "The clean package assembly path copies into bin/, models/, and smoke/ without creating those directories; a fresh PyInstaller onedir can therefore fail before a clean installation exists."
    artifacts:
      - path: "app/packaging/build.py"
        issue: "bundle_engine() calls shutil.copy2() directly for canonical destinations and never creates destination.parent."
    missing:
      - "Create required destination directories before copying and add a fresh-onedir packaging regression test."
  - truth: "Only complete validated runtime facts become persistent HEALTHY state."
    status: failed
    reason: "Full admission accepts every non-executable component merely because it is readable; a nonempty corrupt ggml-base.en.bin is persisted as healthy."
    artifacts:
      - path: "lecturepack/services/runtime_bootstrap.py"
        issue: "_validate_full() runs whisper-cli --help and marks model, smoke WAV, and DLL entries healthy as inventory-readable."
    missing:
      - "Run bounded staged CPU transcription against the canonical model and smoke WAV during full admission; reject a nonempty invalid model."
  - truth: "Every launch uses the appropriate bounded validation and safely reaches SETUP_REQUIRED when required runtime validation cannot succeed."
    status: failed
    reason: "RuntimeValidator.run() creates the subprocess outside its exception handling. An OSError from a blocked/corrupt executable or missing dependent DLL escapes assess() and crashes startup instead of producing failed evidence."
    artifacts:
      - path: "lecturepack/infrastructure/runtime_validation.py"
        issue: "subprocess.Popen() at line 31 is not protected by an OSError handler."
      - path: "lecturepack/services/runtime_bootstrap.py"
        issue: "assess() invokes full_validator without converting unexpected launch/validator failures into SETUP_REQUIRED."
    missing:
      - "Capture launch failures as SmokeEvidence and fail closed without persistence; add an OSError launch regression test."
  - truth: "No normal application behavior begins before required runtime health is HEALTHY."
    status: failed
    reason: "Although adapter construction is withheld, SETUP_REQUIRED leaves many exposed QWebChannel slots dereferencing None. A web call such as set_setting, browse_model, import, job action, or update action raises AttributeError rather than returning a stable setup-required result."
    artifacts:
      - path: "app/desktop/bridge.py"
        issue: "Only ui_ready() checks _adapter; adapter/updater-facing slots do not guard the withheld-admission state."
    missing:
      - "Centralize a setup-required guard for all adapter/updater slots and expose admission state in bootstrap transport."
  - truth: "Whisper native argv remains ASCII-safe for all staged model inputs."
    status: partial
    reason: "The Phase 1 staging boundary stages the primary model, audio, and output only. An enabled Unicode VAD model path is passed directly to whisper.cpp."
    artifacts:
      - path: "lecturepack/infrastructure/whisper_wrapper.py"
        issue: "--vad-model/-vm receives v_model instead of a staged ASCII path."
    missing:
      - "Extend WhisperPathStaging and its tests to stage optional VAD models before native invocation."
---

# Phase 1: Runtime Contract & Bootstrap Verification Report

**Phase Goal:** A clean installation can deterministically establish and persist a healthy bundled CPU processing runtime before any normal application behavior begins.
**Verified:** 2026-07-28T12:42:48Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | RUNT-01 — fresh profile finds and validates packaged CPU runtime | ✗ FAILED | `bundle_engine()` copies canonical payload into uncreated `bin/`, `models/`, and `smoke/` directories; clean onedir assembly can fail. Full admission also never loads the bundled model/WAV. |
| 2 | RUNT-02 — one canonical required-runtime inventory is shared | ✓ VERIFIED | `runtime_inventory.py` supplies root-contained canonical entries; packaging, bootstrap, packaged smoke, and diagnostics consume its identity/evidence rather than rebuilding component lists. |
| 3 | RUNT-03 — only complete validated facts persist | ✗ FAILED | `RuntimeBootstrapService._validate_full()` marks model/WAV/DLL data healthy based on readability, so corrupt nonempty model data can be persisted. |
| 4 | RUNT-04 — light/full bounded checks occur safely as required | ✗ FAILED | Full check is `whisper-cli --help`, not model+WAV transcription; `Popen` launch errors escape the validator. |
| 5 | RUNT-05 — normal behavior cannot begin before HEALTHY | ✗ FAILED | Adapter construction is correctly ordered after assessment, but unhealthy admission leaves callable bridge slots that dereference `None`; startup can also escape rather than retain setup-required state. |
| 6 | RUNT-06 — one-time beta-6 base-English migration preserves later choices | ✓ VERIFIED | `ConfigManager.persist_runtime_health()` gates migration on `migration_versions.runtime_contract == 1`, retains a different prior model, and does not overwrite later selections. Targeted migration tests pass. |
| 7 | RUNT-07 — healthy optional engine remains selected after CPU admission | ✓ VERIFIED | Optional resolution happens after CPU admission; `test_healthy_custom_optional_preference_survives_cpu_admission` exercises preservation. |
| 8 | RUNT-08 — broken optional engine visibly falls back to CPU | ✓ VERIFIED | CPU fallback is post-HEALTHY and the bridge emits a separate typed `runtime_fallback` diagnostics payload; startup test exercises it. |
| 9 | RUNT-09 — approved signed-manifest/verifier ADR exists | ✓ VERIFIED | AD-19 is approved and executable contract vectors pass. Its frozen PyInstaller verifier proof is expressly a future Phase 2 implementation/gate, not a missing Phase 1 deliverable. |

**Score:** 5/9 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `lecturepack/infrastructure/runtime_inventory.py` | Canonical CPU inventory | ✓ VERIFIED | Substantive root-contained inventory shared by runtime consumers. |
| `lecturepack/infrastructure/runtime_validation.py` | Bounded evidence runner | ✗ STUB/UNSAFE | Captures success/nonzero/timeout but fails to capture executable launch errors. |
| `lecturepack/services/runtime_bootstrap.py` | Full admission/persistence policy | ⚠️ HOLLOW | Wired into startup and persistence, but full admission does not prove model or WAV usability. |
| `app/packaging/build.py` | Clean package payload assembly | ✗ FAILED | Destination parent directories are not created. |
| `app/desktop/bridge.py` | Healthy-only desktop boundary | ⚠️ PARTIAL | Adapter creation is gated, but setup-required calls are not guarded. |
| `docs/DECISIONS.md` / `tests/test_signing_adr_contract.py` | Approved AD-19 contract | ✓ VERIFIED | Approved ADR and real fixed Ed25519 accept/reject vectors exist. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- |
| Packaging | canonical inventory | `canonical_inventory()` / `required_runtime_payload()` | PARTIAL | Membership is canonical, but assembly fails on a clean destination. |
| Bootstrap | validator/inventory | `_validate_full()` after `resolve_inventory()` | PARTIAL | Wired, but model/WAV are not exercised and launcher error is unhandled. |
| Backend | bootstrap | `RuntimeBootstrapService(...).assess()` before `make_adapter()` | PARTIAL | Correct construction order, but failed admission does not guard exposed calls. |
| Bridge | diagnostics controller/service | `get_runtime_health_snapshot()` | WIRED | Snapshot is delegated through controller/service, without a second inventory. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `RuntimeBootstrapService` | `components` / `runtime_health` | resolved packaged files plus validator evidence | No for model/WAV usability | ⚠️ STATIC-STYLE VALIDATION |
| `Backend` | `runtime_health_result` | bootstrap assessment | Yes, but unsafe failure paths escape | ⚠️ PARTIAL |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Relevant focused regression suite | `pytest tests/test_runtime_bootstrap.py tests/test_adapter_startup.py tests/test_runtime_packaged_smoke.py tests/test_signing_adr_contract.py tests/test_whisper_path_staging.py tests/test_beta3_packaging.py -q` | 35 passed, 1 failed in 7.14s: packaged-smoke fixture required but unset | ✗ FAIL |
| Real packaged smoke | `pytest tests/test_runtime_packaged_smoke.py -q` with a verified `LECTUREPACK_ONEDIR_FIXTURE` | Not run: no fixture supplied in this worktree/session | ? SKIP |

### Requirements Coverage

| Requirement | Source Plans | Status | Evidence |
| --- | --- | --- | --- |
| RUNT-01 | 01-01 | ✗ BLOCKED | Clean package destination creation and actual model/WAV admission are absent. |
| RUNT-02 | 01-01, 01-03 | ✓ SATISFIED | Canonical inventory and one diagnostics projection are present. |
| RUNT-03 | 01-02 | ✗ BLOCKED | Corrupt readable model can persist as healthy. |
| RUNT-04 | 01-01, 01-02 | ✗ BLOCKED | No real startup transcription; launch failures escape. |
| RUNT-05 | 01-03 | ✗ BLOCKED | Unhealthy bridge state is not safely guarded. |
| RUNT-06 | 01-02 | ✓ SATISFIED | One-time migration implementation and tests. |
| RUNT-07 | 01-02 | ✓ SATISFIED | CPU-first optional preservation test/implementation. |
| RUNT-08 | 01-02, 01-03 | ✓ SATISFIED | Post-health typed CPU fallback notice. |
| RUNT-09 | 01-04 | ✓ SATISFIED | Approved AD-19 plus real vector tests; frozen proof is Phase 2. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- |
| `app/packaging/build.py` | 228 | Copy to potentially absent parent | 🛑 Blocker | Clean install cannot be deterministically assembled. |
| `lecturepack/infrastructure/runtime_validation.py` | 31 | Uncaught `Popen` failure | 🛑 Blocker | Broken executable/DLL can crash instead of fail closed. |
| `lecturepack/services/runtime_bootstrap.py` | 88–99 | `--help` plus readability accepted as full validation | 🛑 Blocker | Corrupt model can be admitted/persisted healthy. |
| `lecturepack/infrastructure/whisper_wrapper.py` | 198–205 | Unicode VAD path bypasses staging | ⚠️ Warning | Native argv safety boundary is incomplete when VAD is enabled. |
| `app/desktop/bridge.py` | 143 onward | Unguarded `None` adapter/updater calls | ⚠️ Warning | Setup-required bridge state is unstable pending Phase 2 UI work. |

### Gaps Summary

The phase goal is not achieved. The main admission path has the intended inventory and ordering structure, but it cannot prove that the model it persists will actually load, can crash on executable launch failure, and cannot reliably create a clean packaged runtime. The setup-required bridge is also not a safe stable state.

AD-19 itself is sufficient for RUNT-09. The ADR explicitly defers a compiled trust module and frozen PyInstaller proof to Phase 2; treating that deferred proof as a Phase 1 failure would contradict the approved phase boundary.

The VAD staging issue is a required repair to the Phase 1 native-path boundary, but it is not the cause of the four RUNT blockers above. UI assets are unchanged and Phase 2 repair/onboarding remains unstarted.

---

_Verified: 2026-07-28T12:42:48Z_
_Verifier: the agent (gsd-verifier)_
