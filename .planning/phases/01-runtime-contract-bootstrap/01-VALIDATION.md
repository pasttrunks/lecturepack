---
phase: 1
slug: runtime-contract-bootstrap
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + existing PySide6 `qapp` fixture |
| **Config file** | `pytest.ini`, `tests/conftest.py` |
| **Quick run command** | `pytest tests/test_runtime_inventory.py tests/test_runtime_bootstrap.py tests/test_adapter_startup.py tests/test_beta3_packaging.py tests/test_cuda_engine.py -q` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | Calibrate during Wave 0 and record actual output; no guessed completion claim |

## Sampling Rate

- **After every task commit:** Run the task's directly affected test file(s) plus the quick command when all Wave 0 files exist.
- **After every plan wave:** Run `pytest` and preserve the actual output.
- **Before phase approval:** Targeted and full suites must be green, packaged/disposable bootstrap smoke evidence must be attached, and the RUNT-09 ADR must be explicitly approved.
- **Max feedback latency:** Targeted unit/controller tests should remain under 60 seconds; real packaged model smoke has a separately calibrated bounded timeout.

## Per-Requirement Verification Map

| Requirement | Expected behavior | Test type | Automated command | File exists | Status |
|-------------|-------------------|-----------|-------------------|-------------|--------|
| RUNT-01 | Fresh disposable profile resolves the exact bundled CPU set | unit/integration | `pytest tests/test_runtime_inventory.py -q` | ❌ Wave 0 | ⬜ pending |
| RUNT-02 | Startup, package checks, diagnostics, and later repair consume one inventory | unit/static | `pytest tests/test_runtime_inventory.py tests/test_beta3_packaging.py -q` | ◐ extend | ⬜ pending |
| RUNT-03 | No partial/stale facts persist; complete healthy facts persist atomically | unit | `pytest tests/test_runtime_bootstrap.py -q` | ❌ Wave 0 | ⬜ pending |
| RUNT-04 | Light/full policy covers success, nonzero, hang, timeout, and identity changes | unit/process fixture | `pytest tests/test_runtime_bootstrap.py -q` | ❌ Wave 0 | ⬜ pending |
| RUNT-05 | No controller/readiness/probe behavior occurs before `HEALTHY`; exactly one transition follows | controller integration | `pytest tests/test_adapter_startup.py tests/test_runtime_bootstrap.py -q` | ◐ extend | ⬜ pending |
| RUNT-06 | Upgrade selects base.en and preserves alternative models | migration unit | `pytest tests/test_runtime_bootstrap.py -q` | ❌ Wave 0 | ⬜ pending |
| RUNT-07 | Healthy optional selection remains after CPU admission | unit | `pytest tests/test_cuda_engine.py -q` | ✅ extend | ⬜ pending |
| RUNT-08 | Broken optional selection yields CPU plus structured notice and no hard gate/network | unit/controller | `pytest tests/test_cuda_engine.py tests/test_runtime_bootstrap.py -q` | ◐ extend | ⬜ pending |
| RUNT-09 | ADR contains every mandatory trust/release field and selected verifier vectors pass | static test + human approval | `pytest tests/test_signing_adr_contract.py -q` | ❌ Wave 0 | ⬜ pending |

## Required Fault Matrix

- Inventory: missing, empty, unreadable, corrupt executable/model/DLL; every resolved `ggml-cpu-*.dll`; absolute/traversal/duplicate entry; changed version/identity.
- Bootstrap: fresh, healthy light launch, stale saved paths, partial facts, identity-changed full smoke, update/repair-forced full smoke, persistence only after all checks pass.
- Smoke: ffmpeg/ffprobe success, nonzero, no-output hang/timeout; Whisper DLL/model load success/failure; captured argument vector, exit code, stdout, stderr, duration, and reason.
- Ordering: slow/failed bootstrap proves no `JobController`, `on_ui_ready`, job signal, Ollama probe, CUDA/Vulkan validation, or demo action before `HEALTHY`; success proves exactly one normal-ready sequence.
- Optional engines: CPU only, valid saved CUDA/custom, missing optional executable/DLL/driver, Vulkan unavailable; valid preference preserved, invalid preference visibly falls back, zero admission network calls.
- Packaged smoke: onedir path with spaces/non-ASCII, fresh `LECTUREPACK_DATA_DIR`, real bundled CLIs and bounded model input, captured evidence; mocks cannot substitute for this proof.

## Wave 0 Requirements

- [ ] `tests/test_runtime_inventory.py` — canonical entry/path/identity/package-consumer matrix.
- [ ] `tests/test_runtime_bootstrap.py` — persistence, light/full policy, runner evidence, ordering, migration, and fallback notice.
- [ ] `tests/fixtures/mock_runtime_hang.py` — deterministic no-output hang for the timeout branch.
- [ ] `tests/test_signing_adr_contract.py` — required ADR fields and known-good/altered-byte verifier vectors after approval.
- [ ] Packaged disposable subprocess harness/fixture — real CPU payload proof without owner/developer data.

## Manual-Only Verifications

| Behavior | Requirement | Why manual | Test instructions |
|----------|-------------|------------|-------------------|
| Signing/verifier ADR approval | RUNT-09 | Dependency, key custody, and release ownership require an explicit owner decision | Review the ADR fields, verifier choice/version, canonical bytes, key lifecycle, PyInstaller proof, and release roles; record approval before Phase 2. |
| Minimum-CPU timeout calibration | RUNT-04 | Hardware timing cannot be inferred from unit mocks | Run the bounded real model smoke on the minimum supported CPU, record duration and selected timeout budget, then encode the approved bound in tests/config. |

## Validation Sign-Off

- [ ] Every implementation task has an automated verification command or an explicit Wave 0 dependency.
- [ ] No three consecutive tasks lack automated feedback.
- [ ] Wave 0 covers every missing test/harness reference.
- [ ] No watch-mode flags are used.
- [ ] Targeted and full pytest outputs are preserved verbatim.
- [ ] Real packaged/bootstrap smoke evidence is preserved; mocks are not claimed as integration proof.
- [ ] RUNT-09 ADR is approved and its verifier contract is testable.
- [ ] `nyquist_compliant: true` and `wave_0_complete: true` are set only after the evidence exists.

**Approval:** pending

