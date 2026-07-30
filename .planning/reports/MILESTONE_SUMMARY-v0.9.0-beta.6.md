# Milestone Summary: v0.9.0-beta.6 — Clean-Machine Reliability and Onboarding

**Milestone:** v0.9.0-beta.6  
**Status:** **100% Complete & Verified**  
**Date:** July 29, 2026  

---

## 1. Executive Overview

Milestone v0.9.0-beta.6 delivers clean-machine reliability, signed repair, empty owned Home landing, guided onboarding demo, visual artifact reliability, and packaged release verification for portable LecturePack on Windows.

- **Core Value:** Convert locally stored lecture videos into complete, reviewable, portable study packs entirely on-device with zero cloud telemetry.
- **Milestone Progress:** 5 of 5 phases completed, 22 plans executed, 853 unit/integration tests passing.

---

## 2. Completed Phase Deliverables

1. **Phase 1: Runtime Contract & Bootstrap**
   - Deterministic CPU runtime admission for FFmpeg, ffprobe, Whisper CLI/DLL set, and `ggml-base.en.bin`.
   - Setup-required bridge safety guards blocking navigation until runtime health is `HEALTHY`.
   - Explicitly approved Ed25519 signing/verifier contract (AD-19).

2. **Phase 2: Hard Setup & Signed Repair**
   - Non-dismissible setup gate for missing, unreadable, or corrupt runtime components.
   - Exact-version release acquisition authenticated via Ed25519 signatures before archive parsing.
   - Transactional activation with atomic rollback on fault.

3. **Phase 3: Empty Launch & Guided Demo**
   - First-run empty Home ownership with explicit job activation.
   - Replayable 5-step guided tour (Home -> Process -> Review -> Transcript -> Study) with rights-clear Polar Bears demo card.
   - Isolated demo pipeline preventing test data from polluting user profile or library state.

4. **Phase 4: Visual Artifact Reliability**
   - Pre-visible theme initialization eliminating Light/Dark startup flashes.
   - Non-blocking pure CSS spotlight box (`box-shadow: 0 0 0 9999px rgba(8,10,14,0.65)` with `pointer-events: none`).
   - WCAG AA Normal contrast across all surface pairs and responsive reflow down to 640px.

5. **Phase 5: Packaged & Physical Release Gate**
   - PyInstaller standalone build (`LecturePack.exe`) with clean-state gate verification.
   - Packaged profile smoke tests passing under hostile non-ASCII Unicode paths (`LecturePack Testing Staging Ñº/`).
   - 19-case signed repair fault matrix verified.

---

## 3. Key Technical Decisions

- **AD-18:** Keep Unicode paths end-to-end while staging native whisper.cpp arguments under private ASCII paths.
- **AD-19:** Ed25519 detached signatures over exact canonical manifest bytes; signature verified BEFORE ZIP archive parsing.
- **Windows PySide6 DLL Order:** Call `os.add_dll_directory` for `PySide6`, `shiboken6`, and `PATH` before importing `QtCore`.
- **Pure CSS Spotlight:** Replace full-viewport SVG masks with `box-shadow: 0 0 0 9999px rgba(8,10,14,0.65)` and `pointer-events: none` to eliminate QtWebEngine hit-testing locks.

---

## 4. Release Verification Matrix

- **Total Test Suite:** 853 passed (851 unit/integration + 2 packaged fixture tests).
- **UI Visual Suite:** 53/53 passed in 0.75s.
- **Repair Fault Matrix:** 19/19 passed in 3.02s.
- **Packaged Smoke Suite:** 5/5 passed in 109s.
- **Privacy Assurance:** 100% local processing; zero cloud telemetry.
