---
phase: 01-runtime-contract-bootstrap
reviewed: 2026-07-28T16:15:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - lecturepack/services/runtime_bootstrap.py
  - app/packaging/build.py
  - tests/test_runtime_bootstrap.py
  - tests/test_runtime_packaged_smoke.py
findings:
  critical: 1
  warning: 0
  info: 0
  total: 1
status: issues_found
---

# Phase 01: Post-fix Code Review Report

**Reviewed:** 2026-07-28T16:15:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

The two requested repairs address their original findings: failed evidence now forces full validation, and default Whisper output is inspected before staging cleanup. Focused tests (27 passed, including the real packaged fixture) and the reported full suite (739 passed) support those repairs. One fail-open remains: a partial persisted snapshot that merely says every component is healthy still bypasses full validation.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Partial positive persisted evidence is still admitted without a smoke

**File:** `lecturepack/services/runtime_bootstrap.py:96-105`
**Issue:** The revised predicate treats each component mapping containing only `{"healthy": True}` as sufficient for light validation. That is partial evidence, not the complete bounded process evidence required by the runtime contract. With a matching stored identity and component names, such a snapshot produces `HEALTHY` in `light` mode and does not invoke `full_validator`; an injected reproduction returned `HEALTHY light []`. A damaged or tampered `runtime_health` record can therefore recreate healthy state from file presence rather than a successful CPU smoke.

**Fix:** Require the complete success-evidence shape before allowing light validation, including at least `healthy`, `reason`, `exit_code`, `argv`, `stdout`, `stderr`, `duration_ms`, and `timed_out` for every canonical component. Otherwise require full validation. Add a regression with same-identity `{"healthy": True}`-only components that asserts full validation is called and that a failed validator leaves admission `SETUP_REQUIRED`.

```python
required_fields = {
    "healthy", "reason", "exit_code", "argv", "stdout", "stderr",
    "duration_ms", "timed_out",
}
return not all(
    isinstance(component, Mapping)
    and component.get("healthy") is True
    and required_fields <= component.keys()
    for component in components.values()
)
```

## Resolved-findings audit trail

- **Resolved — prior CR-01:** `lecturepack/services/runtime_bootstrap.py:96-105` now rejects same-identity evidence where any component is explicitly unhealthy. `tests/test_runtime_bootstrap.py:129-160` proves the full validator is called and a repeated failure remains `SETUP_REQUIRED` without overwriting the stored failure.
- **Resolved — prior WR-01:** `app/packaging/build.py:85-101` now enumerates all files in the private staging tree before cleanup and fails with the captured process evidence. `tests/test_runtime_packaged_smoke.py:32-63` writes the default `audio.txt`, proves rejection, and verifies staging cleanup.

---

_Reviewed: 2026-07-28T16:15:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
