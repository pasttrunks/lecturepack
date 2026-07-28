---
phase: 01-runtime-contract-bootstrap
reviewed: 2026-07-28T16:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - app/packaging/build.py
  - lecturepack/infrastructure/runtime_validation.py
  - lecturepack/services/runtime_bootstrap.py
  - lecturepack/infrastructure/whisper_path_staging.py
  - lecturepack/infrastructure/whisper_wrapper.py
  - app/desktop/bridge.py
  - tests/test_beta3_packaging.py
  - tests/test_runtime_bootstrap.py
  - tests/test_runtime_packaged_smoke.py
  - tests/test_whisper_path_staging.py
  - tests/test_study_workflow.py
  - tests/test_adapter_startup.py
  - tests/test_runtime_diagnostics.py
findings:
  critical: 1
  warning: 1
  info: 0
  total: 2
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-07-28T16:00:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

The reviewed implementation correctly uses argument arrays, stages native Whisper inputs to ASCII paths, and guards the listed bridge operations during setup-required admission. However, persisted failed runtime evidence can be silently upgraded to `HEALTHY` without rerunning the required smoke, defeating the CPU admission gate. The disposable-smoke artifact assertion is also ineffective because cleanup precedes the check.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Previously failed runtime evidence is re-admitted without full validation

**File:** `lecturepack/services/runtime_bootstrap.py:55-88`
**Issue:** `_requires_full()` at lines 91-97 checks only the persisted identity and component-key set. If a prior full smoke recorded a component as unhealthy (for example, a corrupt model or launch failure) but the files remain nonempty and the identity is unchanged, `assess()` selects light mode. Lines 57-62 then use only `is_file()` and size, and line 86 persists a new healthy snapshot. A direct injected reproduction with persisted `{"healthy": false}` evidence, the same identity, and a nonempty executable returns `HEALTHY light` with zero full-validator calls. This violates the fail-closed admission contract: a failed required component must stay setup-required until a full validation proves recovery.

**Fix:** Require a full validation unless the persisted snapshot has a complete matching component set whose every component is explicitly `healthy is True` (and, ideally, contains the expected complete evidence fields). For example:

```python
components = previous.get("components")
if not isinstance(components, dict) or set(components) != set(paths):
    return True
return not all(
    isinstance(component, Mapping) and component.get("healthy") is True
    for component in components.values()
)
```

Add a regression to `tests/test_runtime_bootstrap.py` that seeds same-identity failed component evidence and asserts `validation_mode == "full"`, no healthy persistence until the full validator succeeds, and `SETUP_REQUIRED` if it fails again.

## Warnings

### WR-01: The smoke test cannot detect a transcript artifact from its Whisper invocation

**File:** `app/packaging/build.py:75-91`
**Issue:** The `finally` block deletes the staging directory at line 85 before line 90 checks `staged_prefix`. That path can therefore never exist, so the assertion does not prove the required no-output behavior. In addition, the command at lines 80-83 does not pass `-of staged_prefix`; if the CLI writes a default output next to the staged WAV, it would not be checked even before cleanup. The packaged-smoke test consequently reports an unverified artifact guarantee.

**Fix:** Before `cleanup()`, inspect the entire staging root for output files (or direct Whisper output with `-of` to the staged prefix and assert that no `transcript.*` files exist). Preserve any unexpected-path list in the failure evidence, then clean up in `finally`. Add a regression that uses a fixture which writes a default output and verifies the smoke fails.

---

_Reviewed: 2026-07-28T16:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
