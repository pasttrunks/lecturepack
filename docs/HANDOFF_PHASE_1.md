# Phase 1 Handoff — Runtime Contract & Bootstrap

**Updated:** 2026-07-28  
**Branch:** `codex/beta6-reliability-plan`  
**Status:** Execution complete, but independent verification found Phase 1 gaps; Phase 2 repair implementation remains unstarted.

## Completed work

- The canonical CPU inventory, bounded validator, disposable onedir smoke, and v1.9.1 ASCII-only `WhisperPathStaging` boundary are complete. Unicode source and destination paths remain supported outside the native CLI argv boundary.
- `RuntimeBootstrapService` persists only complete validated CPU evidence, performs the one-time base-English migration, and resolves optional engines only after CPU admission.
- `Backend` now assesses runtime health before it constructs an `EngineAdapter`, controller, job behavior, navigation behavior, or optional probe. `SETUP_REQUIRED` retains a stable no-adapter state for the Phase 2 setup gate.
- A healthy admission creates the adapter once. `ui_ready()` produces the one normal ready path only after that admission; a broken optional preference is sent afterwards as `diagnostics` payload `{ "type": "runtime_fallback", "fallback": { requested, resolved, reason } }`, separate from ordinary status and readiness.
- `RuntimeDiagnosticsController` delegates to `RuntimeDiagnosticsService`, which reads the persisted canonical identity and immutable bootstrap evidence only. `Backend.get_runtime_health_snapshot()` serializes that controller result for QWebChannel; neither bridge nor adapter constructs a second required-runtime inventory.
- AD-19 is approved. It locks `cryptography==49.0.0`, byte-exact detached Ed25519 manifest signatures, release asset naming, key lifecycle, and the future compiled trust-root/frozen-proof requirements.

## Verification evidence

- `pytest tests/test_adapter_startup.py tests/test_runtime_diagnostics.py tests/test_runtime_bootstrap.py tests/test_runtime_packaged_smoke.py -q` with `LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack` — **19 passed in 10.82s**.
- `LECTUREPACK_ONEDIR_FIXTURE=C:\Users\marsh\Documents\LecturePack\app\dist\LecturePack; pytest -q` — **728 passed in 179.15s (0:02:59)**.
- The same targeted command without `LECTUREPACK_ONEDIR_FIXTURE` intentionally failed one packaged-smoke test because the fixture is mandatory; no test was skipped or weakened.
- Real packaged smoke evidence remains the Plan 01 proof: copied Unicode/space runtime, fresh `LECTUREPACK_DATA_DIR`, `bin/ffmpeg.exe -version`, `bin/ffprobe.exe -version`, then `bin/whisper-cli.exe -m <ASCII staged ggml-base.en.bin> -f <ASCII staged runtime-smoke.wav> -t 1 -nt`; exit 0 in 4328 ms with CPU backend, model, WAV-read, and processing evidence and no output transcript.

## Remaining work and blockers

- Phase 1 is not approved or complete. The advisory code review recorded four critical findings and one warning; the goal verifier returned `gaps_found` with 5/9 must-haves verified. Gap-closure planning is required before more implementation.
- The blocking Phase 1 gaps are: create canonical runtime destination directories during clean packaging; perform bounded real model-plus-WAV CPU transcription during startup admission; convert executable launch failures into failed evidence and `SETUP_REQUIRED`; guard all adapter/updater bridge slots while admission is withheld; and stage optional VAD model paths at the ASCII-only native argv boundary.
- Phase 2 must implement the non-dismissible setup UI, explicit consent, signed exact-version acquisition, manifest/hash validation, transactional writable runtime generation, rollback, revalidation, and actionable diagnostics. None of that repair behavior is implemented here.
- AD-19 approval satisfies the Phase 1 contract prerequisite, but Phase 2 remains blocked until its ADR post-checkpoint task passes the approved known-good and altered-byte signature vectors in the implementation context.
- Before release, obtain physical CPU-only, NVIDIA, and AMD/Intel Windows evidence across fresh/upgraded profiles and hostile paths; frozen verifier proof and signing workflow remain Phase 2+ work.
- Four copied smoke-test directories remain under `%TEMP%` from pre-staging failure investigations. A scoped PowerShell cleanup was attempted after resolving the exact paths, but host policy rejected recursive deletion; they contain copies only, never original lecture videos or user data. The four disposable cleanup domains remain temporary-only: copied Unicode/space runtime, fresh `LECTUREPACK_DATA_DIR`, private ASCII staging workspace, and `smoke-output` output prefix.

## Scope and safety

No original lecture video, user job/profile data, immutable source payload, main worktree, UI/web asset, animation, theme, or repair/download flow was modified. The bridge fallback uses the existing diagnostics transport because the web bridge signal registry is intentionally outside this phase's permitted file list.
