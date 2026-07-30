---
phase: 1
slug: runtime-contract-bootstrap
status: verified
threats_open: 0
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
created: 2026-07-28
---

# Phase 1 — Security

> ASVS L1 verification of the threat registers authored in the seven Phase 1 plans.

## Trust Boundaries

| Boundary | Description | Data crossing |
|---|---|---|
| Packaged payload | Canonical executables, DLLs, model, and smoke WAV enter runtime admission | Local release assets and their recorded identity |
| Native process boundary | Fixed local tools receive bounded argument-array invocations | Staged ASCII paths and captured process evidence |
| Persisted health boundary | Full validation facts become reusable light-validation state | Atomic local configuration data |
| Desktop admission boundary | Bridge operations reach adapter/updater collaborators only after health | JSON-safe runtime diagnostics and guarded calls |
| Release trust boundary | Phase 1 defines, but does not implement, signed repair verification | AD-19 key, manifest, asset, and frozen-build contract |

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Verified mitigation | Status |
|---|---|---|---|---|---|---|
| T-01-01 | Tampering | Runtime inventory | high | mitigate | Root containment, duplicate/traversal rejection, and nonempty payload tests | closed |
| T-01-02 | Denial of service | Process validation | high | mitigate | Fixed argv, finite timeout, captured evidence, owned-process-tree termination | closed |
| T-01-03 | Tampering | Health persistence | high | mitigate | Only complete successful evidence persists through atomic configuration writes | closed |
| T-01-04 | Denial of service | Optional engines | high | mitigate | Optional resolution occurs only after CPU admission | closed |
| T-01-05 | Elevation of privilege | Desktop startup | high | mitigate | Adapter/updater construction is conditional on `HEALTHY` | closed |
| T-01-06 | Spoofing | Signing authority | high | mitigate | Approved AD-19 defines signer/verifier ownership and defers implementation to Phase 2 | closed |
| T-01-07 | Tampering | Signed manifest | high | mitigate | AD-19 defines canonical bytes/schema and altered-byte rejection vectors | closed |
| T-01-08 | Repudiation | Release authority | high | mitigate | AD-19 names custody, rotation, revocation, incident, and evidence owners | closed |
| T-01-09 | Tampering | Runtime diagnostics | high | mitigate | Controller-owned snapshot is the canonical diagnostics source | closed |
| T-01-10 | Tampering | Clean packaging | high | mitigate | Canonical destination parents only; source/destination nonempty checks | closed |
| T-01-11 | Denial of service | Process launch | high | mitigate | Launch `OSError` becomes failed evidence; no unowned cleanup occurs | closed |
| T-01-12 | Elevation of privilege | Admission exceptions | high | mitigate | Unexpected validator errors fail closed before persistence or optional resolution | closed |
| T-01-13 | Tampering | Whisper admission | high | mitigate | Canonical staged model and WAV must pass the real CPU smoke | closed |
| T-01-14 | Denial of service | Whisper process | high | mitigate | Fixed bounded argv, owned-tree containment, and staging cleanup in `finally` | closed |
| T-01-15 | Information disclosure | Unicode staging | medium | mitigate | Private disposable ASCII staging uses byte-equivalent copies and cleanup | closed |
| T-01-16 | Tampering | VAD native path | high | mitigate | Optional VAD model is staged and all native filesystem args are ASCII | closed |
| T-01-17 | Elevation of privilege | Bridge operations | high | mitigate | Central registry guards adapter/updater operations before dereference | closed |
| T-01-18 | Denial of service | Setup-required bridge | high | mitigate | Stable JSON-safe no-op diagnostics are repeatable and side-effect-free | closed |
| T-01-19 | Tampering | Diagnostics projection | medium | mitigate | Bootstrap and runtime-health endpoints reuse one controller snapshot | closed |
| T-01-SC | Tampering | Dependency scope | high | mitigate | No runtime package installation; production verifier/repair remains Phase 2 work | closed |

## Summary Threat Flags

Plans 01-05 through 01-07 report no additional threat flags. No unregistered Phase 1 threat flag remains.

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Audit date | Threats total | Closed | Open | Run by |
|---|---:|---:|---:|---|
| 2026-07-28 | 20 | 20 | 0 | Independent `gsd-security-auditor` (ASVS L1) |

## Sign-Off

- [x] All threats have a disposition.
- [x] No accepted risk requires documentation.
- [x] `threats_open: 0` confirmed at the high-severity blocking threshold.
- [x] `status: verified` set in frontmatter.

**Approval:** verified 2026-07-28
