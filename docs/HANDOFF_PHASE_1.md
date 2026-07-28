# Phase 1 Handoff — Runtime Contract & Bootstrap

**Updated:** 2026-07-28  
**Branch:** `codex/beta6-reliability-plan`  
**Status:** Phase 1 is verified complete. All 7 plans are complete, final code review is clean, goal verification passed 9/9, security closed 20/20 registered threats, and roadmap/state have advanced to Phase 2 planning. Phase 2 implementation remains unstarted and requires explicit user approval.

## Gap repairs completed in Plans 01-05 through 01-07

- **01-05:** canonical package assembly now creates `bin`, `models`, and `smoke` parents from a fresh onedir tree; a blocked/corrupt executable launch becomes bounded failed evidence and `SETUP_REQUIRED`, never persisted healthy state.
- **01-06:** full admission performs bounded staged CPU transcription of the canonical base-English model and smoke WAV. Corrupt model evidence is rejected, and optional VAD models are byte-verified and staged under the private ASCII native argv root.
- **01-07:** every adapter- and updater-facing bridge action is centrally guarded while admission is `SETUP_REQUIRED`. It emits the existing `diagnostics` transport payload `{type: "setup_required", operation, runtime_health}` before collaborator access; `get_updater_state()` returns the same JSON-safe payload. `get_bootstrap()` now exposes `theme`, `version`, `runtime_health_state`, and `setup_required`, while `get_runtime_health_snapshot()` remains the controller-owned detailed projection.

No frontend/web asset, animation, transition, motion, theme/styling behavior, original lecture video, user data, setup/repair/consent flow, dependency, or network path was added or changed.

## Actual verification evidence

All packaged/full-suite commands used this supplied fixture environment value:

`LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\AppData\Local\Temp\LecturePack Phase1 Gap Fixture Corrected 20260728`

It is a run-scoped copy of `C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack`, augmented only with repository-approved `app\packaging\assets\runtime-smoke.wav` at `smoke\runtime-smoke.wav`. `check_clean_state()` passed before real smoke. The fixture was never modified; smoke copied it to a disposable Unicode/space path and used a fresh profile.

- `pytest tests/test_adapter_startup.py tests/test_runtime_diagnostics.py -q` — **10 passed in 0.93s**.
- `pytest tests/test_beta3_packaging.py tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py tests/test_whisper_path_staging.py tests/test_adapter_startup.py tests/test_runtime_diagnostics.py -q` — **38 passed in 16.70s**.
- Required fixture validation (`check_clean_state()`), then `pytest tests/test_runtime_packaged_smoke.py -q` — **3 passed in 15.67s**.
- `pytest tests/test_runtime_bootstrap.py -q` after the Nyquist audit — **18 passed in 1.25s**.
- Final `pytest -q` under the same fixture — **743 passed in 187.42s (0:03:07)**.

Final independent gates:

- `01-REVIEW.md` — **clean**, 0 critical, 0 warning, 0 info findings after three fail-open/smoke-artifact findings were repaired and re-reviewed.
- `01-VERIFICATION.md` — **passed**, **9/9 must-haves verified**, RUNT-01 through RUNT-09 satisfied.
- `01-SECURITY.md` — **verified**, **20/20 threats closed**, `threats_open: 0` at ASVS L1.
- `01-VALIDATION.md` — **validated (partial)**, **8/9 requirements automated**. The two identified RUNT-04 branches were added and pass; the real RUNT-02 repair-consumer integration is explicitly deferred to Phase 2 because Phase 1 intentionally has no repair consumer.

The table-driven bridge gate covers every current adapter/updater dereference: settings; model/engine controls; import, job, queue, review, study, and export actions; all update actions; and Qt `QMetaObject.invokeMethod` dispatch. Repeated calls retain `SETUP_REQUIRED`, do not construct collaborators, and do not write settings, navigate, process jobs, probe optional engines, start updater work, or emit ready/fallback semantics.

## Real packaged smoke evidence from this run

The disposable copied runtime invoked:

`whisper-cli.exe -m C:\Users\marsh\AppData\Local\Temp\LecturePackWhisper\lpws-rnd1y9ss\inputs\model.bin -f C:\Users\marsh\AppData\Local\Temp\LecturePackWhisper\lpws-rnd1y9ss\inputs\audio.wav -t 1 -nt`

It exited **0** in **4078 ms**, with reason `success`; stdout was `(electronic beeping)`. Stderr recorded the copied runtime's `ggml-cpu-haswell.dll` CPU backend, staged model load, staged WAV read, `n_threads = 1`, and processing of the one-second WAV. The executable path remained in the disposable copied runtime; model and audio argv paths were ASCII staged. This is real packaged evidence, not a mock.

Fresh-tree assembly, corrupt-model rejection, blocked launch evidence, VAD staging, and bridge no-side-effect behavior are covered by the passing regression suites above. The earlier 01-05 and 01-06 summaries retain their exact respective historical test outputs and evidence.

## Next-phase and release work

- Phase 1 has no remaining implementation or verification blocker. The user must explicitly approve Phase 2 before implementation begins.
- Required pre-release evidence remains unrun: physical CPU-only, NVIDIA, and AMD/Intel Windows machines; fresh and upgraded profiles; hostile path coverage; frozen verifier/signing workflow proof.
- Phase 2 remains out of scope and unstarted: non-dismissible setup UI, consent, signed exact-version acquisition, manifest/hash validation, transactional writable runtime generation, rollback, revalidation, and actionable repair diagnostics.
- AD-19 remains approved and unchanged. Its compiled trust-root, real repair-consumer integration, production verifier, and frozen proof requirements are Phase 2 gates and are not claimed as passed here.

## Scope and safety

No original lecture video or user job/profile data was modified. The supplied fixture and all smoke runtime copies were read-only inputs; disposable copies and private staging directories were confined to `%TEMP%`. No university credentials, telemetry, analytics, or non-localhost network request was introduced.
