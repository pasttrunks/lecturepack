---
phase: 01-runtime-contract-bootstrap
reviewed: 2026-07-28T12:39:56Z
depth: standard
files_reviewed: 26
files_reviewed_list:
  - app/desktop/bridge.py
  - app/desktop/engine_adapter.py
  - app/packaging/assets/runtime-smoke.wav
  - app/packaging/build.py
  - app/requirements.txt
  - docs/DECISIONS.md
  - docs/HANDOFF_PHASE_1.md
  - lecturepack/controllers/runtime_diagnostics_controller.py
  - lecturepack/infrastructure/config_manager.py
  - lecturepack/infrastructure/runtime_inventory.py
  - lecturepack/infrastructure/runtime_validation.py
  - lecturepack/infrastructure/whisper_path_staging.py
  - lecturepack/infrastructure/whisper_wrapper.py
  - lecturepack/services/runtime_bootstrap.py
  - lecturepack/services/runtime_diagnostics.py
  - requirements.txt
  - tests/fixtures/mock_runtime_hang.py
  - tests/test_adapter_startup.py
  - tests/test_beta3_packaging.py
  - tests/test_runtime_bootstrap.py
  - tests/test_runtime_diagnostics.py
  - tests/test_runtime_inventory.py
  - tests/test_runtime_packaged_smoke.py
  - tests/test_signing_adr_contract.py
  - tests/test_study_workflow.py
  - tests/test_whisper_path_staging.py
findings:
  critical: 4
  warning: 1
  info: 0
  total: 5
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-07-28T12:39:56Z
**Depth:** standard
**Files Reviewed:** 26
**Status:** issues_found

## Summary

The Phase 1 runtime contract has useful inventory, staging, and persistence primitives, but it does not currently guarantee a usable clean-install runtime. The packaging path can fail before producing a bundle, and startup can either crash or admit a corrupt Whisper model as healthy. The Unicode safety boundary also leaks the VAD model path directly to the known-unsafe native argv boundary.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Engine bundling no longer creates required destination directories

**File:** `app/packaging/build.py:244`
**Issue:** `bundle_engine()` now copies every canonical payload directly to destinations such as `dist/LecturePack/bin/ffmpeg.exe`, `models/ggml-base.en.bin`, and `smoke/runtime-smoke.wav`, but it no longer creates `bin`, `models`, or `smoke`. A clean PyInstaller onedir is not required to contain those directories, so `shutil.copy2()` raises `FileNotFoundError` and the release build cannot create the promised clean installation. The synthetic cleanliness test pre-creates these directories and therefore misses the regression.
**Fix:** Create each `destination.parent` before copying (or create the three canonical directories before the loop), then add a `bundle_engine()` test using a fresh onedir tree with no runtime directories.

### CR-02: Startup crashes instead of returning SETUP_REQUIRED when a bundled executable cannot launch

**File:** `lecturepack/infrastructure/runtime_validation.py:31`
**Issue:** `subprocess.Popen()` is outside the `try` block. Windows raises `OSError` when the executable is blocked, corrupt, or has a missing dependent DLL. During the full startup assessment, that exception escapes `RuntimeBootstrapService.assess()` (`runtime_bootstrap.py:65`) and aborts construction of `Backend`, rather than recording failed evidence and entering the required setup state.
**Fix:** Catch `OSError` around process creation and return a failed `SmokeEvidence` (for example, reason `"launch failed"`, no exit code, captured exception text). Ensure `assess()` also converts unexpected validator failures into `SETUP_REQUIRED` without persisting health.

### CR-03: Runtime admission treats a corrupt Whisper model as healthy

**File:** `lecturepack/services/runtime_bootstrap.py:88`
**Issue:** The full validator runs `whisper-cli --help`, which never opens `models/ggml-base.en.bin` or reads the bundled WAV. The model and smoke asset are marked healthy solely because they are nonempty at lines 76-79. Consequently, a truncated or malformed model is persisted as `HEALTHY`; normal transcription then fails after the application has admitted the runtime. This violates the phase goal that a healthy bundled CPU runtime is established before normal behavior begins.
**Fix:** In full validation run a bounded real CPU transcription using the canonical model and smoke WAV (the same argv/staging approach as `run_disposable_runtime_smoke`), and map that evidence to the Whisper/model/smoke components. Add a test with a nonempty invalid model that proves admission is rejected.

### CR-04: VAD model paths bypass the ASCII staging boundary

**File:** `lecturepack/infrastructure/whisper_wrapper.py:198-205`
**Issue:** Model, audio, and output paths are staged to ASCII-only paths, but an enabled VAD model is appended as the original `v_model` string. A VAD model located under a valid Unicode Windows path is therefore passed directly to whisper.cpp v1.9.1, precisely the argv boundary AD-18 says is unsafe; the native process can crash or fail despite the main inputs being staged.
**Fix:** Extend `WhisperPathStaging` to stage the optional VAD model too and use that staged ASCII path for `--vad-model`/`-vm`. Cover it with a Unicode VAD-path test that asserts every native path argument is ASCII.

## Warnings

### WR-01: SETUP_REQUIRED leaves callable QWebChannel slots that dereference None

**File:** `app/desktop/bridge.py:143-146`
**Issue:** Only `ui_ready()` checks whether admission withheld the adapter. Every other adapter/updater slot (for example `set_setting`, `browse_model`, import, diagnostics, and update actions) still dereferences `self._adapter` or `self._updater` while they are `None`. The pre-Phase-2 UI can invoke any of these after receiving the ordinary bootstrap payload, producing unhandled `AttributeError`s instead of a stable setup-required response.
**Fix:** Centralize an admission guard for all adapter/updater-facing slots that returns a structured setup-required error/no-op, and make `get_bootstrap()` expose admission state so the frontend can avoid normal controls.

---

_Reviewed: 2026-07-28T12:39:56Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
