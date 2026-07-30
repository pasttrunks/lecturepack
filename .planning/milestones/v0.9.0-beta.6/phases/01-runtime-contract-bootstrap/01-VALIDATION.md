---
phase: 1
slug: runtime-contract-bootstrap
status: validated
nyquist_compliant: false
wave_0_complete: true
created: 2026-07-27
validated: 2026-07-28
automated_coverage: 8/9
manual_deferred: 1
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + existing PySide6 `qapp` fixture |
| **Config file** | `pytest.ini`, `tests/conftest.py` |
| **Quick run command** | `pytest tests/test_runtime_inventory.py tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py tests/test_adapter_startup.py tests/test_beta3_packaging.py tests/test_cuda_engine.py -q` |
| **Full suite command** | `pytest` |
| **Measured runtime** | Focused bootstrap: `18 passed in 1.25s`; final full suite: `743 passed in 187.42s` |

## Sampling Rate

- **After every task commit:** Run the task's directly affected test file(s) plus the quick command when all Wave 0 files exist.
- **After every plan wave:** Run `pytest` and preserve the actual output.
- **Before phase approval:** Targeted and full suites must be green, packaged/disposable bootstrap smoke evidence must be attached, and the RUNT-09 ADR must be explicitly approved.
- **Max feedback latency:** Targeted unit/controller tests should remain under 60 seconds; real packaged model smoke has a separately calibrated bounded timeout.

## Per-Requirement Verification Map

| Requirement | Expected behavior | Test type | Automated command | File exists | Status |
|-------------|-------------------|-----------|-------------------|-------------|--------|
| RUNT-01 | Fresh disposable profile resolves the exact bundled CPU set | unit/integration | `pytest tests/test_runtime_inventory.py tests/test_runtime_packaged_smoke.py -q` | ✅ | ✅ covered |
| RUNT-02 | Startup, package checks, diagnostics, and later repair consume one inventory | unit/static + deferred integration | `pytest tests/test_runtime_inventory.py tests/test_beta3_packaging.py tests/test_runtime_diagnostics.py -q` | ✅ current consumers | ◐ repair consumer deferred to Phase 2 |
| RUNT-03 | No partial/stale facts persist; complete healthy facts persist atomically | unit | `pytest tests/test_runtime_bootstrap.py -q` | ✅ | ✅ covered |
| RUNT-04 | Light/full policy covers real CLI/model/WAV smoke, failures, timeouts, identity, update/repair, and light payload loss | unit/packaged process fixture | `pytest tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py -q` | ✅ | ✅ covered |
| RUNT-05 | No controller/readiness/probe behavior occurs before `HEALTHY`; exactly one transition follows | controller integration | `pytest tests/test_adapter_startup.py tests/test_runtime_bootstrap.py -q` | ✅ | ✅ covered |
| RUNT-06 | Upgrade selects base.en and preserves alternative models | migration unit | `pytest tests/test_runtime_bootstrap.py -q` | ✅ | ✅ covered |
| RUNT-07 | Healthy optional selection remains after CPU admission | unit | `pytest tests/test_cuda_engine.py tests/test_runtime_bootstrap.py -q` | ✅ | ✅ covered |
| RUNT-08 | Broken optional selection yields CPU plus structured notice and no hard gate/network | unit/controller | `pytest tests/test_cuda_engine.py tests/test_runtime_bootstrap.py -q` | ✅ | ✅ covered |
| RUNT-09 | ADR contains every mandatory trust/release field and selected verifier vectors pass | static test + approved human decision | `pytest tests/test_signing_adr_contract.py -q` | ✅ | ✅ covered |

## Required Fault Matrix

- Inventory: missing, empty, unreadable, corrupt executable/model/DLL; every resolved `ggml-cpu-*.dll`; absolute/traversal/duplicate entry; changed version/identity.
- Bootstrap: fresh, healthy light launch, stale saved paths, partial facts, identity-changed full smoke, update/repair-forced full smoke, persistence only after all checks pass; marker-v1 migration preserves healthy optional engine selection, records requested/reason on fallback, selects base.en once, retains alternative models, and never resets a later manual choice.
- Smoke: package the project-owned 1.000 s, 16 kHz, mono `pcm_s16le` fixture from `app/packaging/assets/runtime-smoke.wav` to `smoke/runtime-smoke.wav`; invoke `bin/whisper-cli.exe -m models/ggml-base.en.bin -f smoke/runtime-smoke.wav -t 1 -nt` with a 30,000 ms deadline and no output-file flag. Cover ffmpeg/ffprobe success, nonzero, no-output hang/timeout; Whisper backend-DLL/model/WAV/processing evidence, missing DLL, bad model, unreadable WAV, nonzero, and timeout; capture argument vector, exit code, stdout, stderr, duration, and reason.
- Ordering: slow/failed bootstrap proves no `JobController`, `on_ui_ready`, job signal, Ollama probe, CUDA/Vulkan validation, or demo action before `HEALTHY`; success proves exactly one normal-ready sequence.
- Optional engines: CPU only, valid saved CUDA/custom, missing optional executable/DLL/driver, Vulkan unavailable; valid preference preserved, invalid preference visibly falls back, zero admission network calls.
- Packaged smoke: onedir path with spaces/non-ASCII, fresh `LECTUREPACK_DATA_DIR`, real bundled CLIs and bounded model input, captured evidence; mocks cannot substitute for this proof.

## Wave 0 Requirements

- [x] `tests/test_runtime_inventory.py` — canonical entry/path/identity/package-consumer matrix.
- [x] `tests/test_runtime_bootstrap.py` — persistence, light/full policy, runner evidence, ordering, migration, fallback notice, explicit update/repair, and light payload loss.
- [x] `app/packaging/assets/runtime-smoke.wav` — project-owned deterministic 1.000 s, 16 kHz, mono signed 16-bit little-endian PCM tone, hashed in canonical inventory and packaged as `smoke/runtime-smoke.wav`.
- [x] `tests/test_runtime_packaged_smoke.py` — exact real packaged CLI/model/WAV execution and evidence assertions under a disposable Unicode/space path; missing package fixture blocks rather than skips Phase 1 evidence.
- [x] `tests/fixtures/mock_runtime_hang.py` — deterministic no-output hang for the timeout branch.
- [x] `tests/test_signing_adr_contract.py` — required ADR fields and known-good/altered-byte verifier vectors after approval.
- [x] Packaged disposable subprocess harness/fixture — real CPU payload proof without owner/developer data.

## Manual-Only Verifications

| Behavior | Requirement | Why manual | Test instructions |
|----------|-------------|------------|-------------------|
| Real repair consumer uses the canonical inventory | RUNT-02 | Repair implementation is deliberately a Phase 2 deliverable under AD-19; Phase 1 has no real repair consumer to invoke | In Phase 2, run the real repair admission/activation boundary and prove it consumes the canonical inventory without redefining component membership. |
| Minimum-CPU timeout calibration | RUNT-04 | Hardware timing cannot be inferred from unit mocks | Run the bounded real model smoke on the minimum supported CPU, record duration and selected timeout budget, then encode the approved bound in tests/config. |

## Validation Sign-Off

- [x] Every Phase 1 implementation task has an automated verification command or an explicit manual/deferred boundary.
- [x] No three consecutive tasks lack automated feedback.
- [x] Wave 0 test and harness references now exist.
- [x] No watch-mode flags are used.
- [x] Targeted and full pytest outputs are preserved in summaries, review, verification, and this audit.
- [x] Real packaged/bootstrap smoke evidence is preserved; mocks are not claimed as integration proof.
- [x] RUNT-09 ADR is approved and its verifier contract is testable.
- [x] `wave_0_complete: true` is backed by executed evidence; `nyquist_compliant` remains false because the user deferred the real RUNT-02 repair-consumer test to Phase 2.

**Approval:** validated (partial) 2026-07-28

## Validation Audit 2026-07-28

| Metric | Count |
|---|---:|
| Requirements covered automatically | 8 |
| Automated gaps found | 2 |
| Automated gaps resolved | 2 |
| Manual/deferred requirement checks | 1 |

The Nyquist audit identified explicit update/repair full-validation and light-path payload-loss branches in RUNT-04. The user chose to add both now; they pass in `tests/test_runtime_bootstrap.py`. The user chose to defer the real RUNT-02 repair-consumer integration check to Phase 2 because Phase 1 intentionally defines the trust and admission contract but does not implement repair.

Final evidence after the added tests: `18 passed in 1.25s` focused and `743 passed in 187.42s` full-suite, with the verified real packaged fixture enabled.
