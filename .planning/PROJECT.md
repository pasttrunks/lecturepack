# PROJECT.md — LecturePack

## Overview

LecturePack is a Windows desktop application (PySide6 / Python 3.12, packaged with PyInstaller onedir) that converts locally stored university lecture videos into study materials: timestamped transcripts, recovered slide images, aligned study packs, and a student workspace with bookmarks and notes. Local-first with optional Groq online transcription.

## Core Value

Convert lecture videos into complete, reviewable, portable study packs — entirely on-device, with no accounts, no telemetry, and no cloud dependency by default.

## Scope

- **Current state:** `v0.9.0-beta.5` at commit `459faf5` is the authoritative portable beta. Its core runtime payload is bundled, but a fresh profile does not initialize or verify Whisper before processing validation.
- **Immediate goal:** Ship `v0.9.0-beta.6` as a dependable clean-machine onboarding release with automatic bundled-runtime initialization, verified repair, empty launch ownership, concise guided onboarding, visual-artifact fixes, and a physical-machine release gate.
- **Architecture:** Strict 4-layer model (UI → Controller → Service → Infrastructure), per-job staged pipeline, plain-file JSON persistence, QProcess for external tools, QThread for internal compute.

## Goals

1. Make the bundled CPU runtime self-discovering, deterministic, persisted, and usable without manual Settings configuration.
2. Block main-app entry behind actionable setup and transactional repair when required runtime components are missing or corrupt.
3. Start with no active lecture and teach the main workflow through a concise, real, isolated synthetic demo.
4. Preserve beta 5's intentional visual language while eliminating flicker, repaint artifacts, overflow, and layout jumps.
5. Prove beta 6 on CPU-only, NVIDIA, and AMD/Intel Windows machines, including offline, upgraded-profile, hostile-path, and damaged-runtime cases.

## Non-Goals

- New transcription providers, accounts, telemetry, analytics, or unrelated network access.
- Redesigning or simplifying beta 5's visual language, motion, shadows, or pressed-button behavior.
- Offline repair-package import or manual browsing for required runtime files.
- Permanent demo jobs, fake persisted lectures, or university/third-party demo content.
- Unrelated architecture debt, detector refactors, or feature work not required by beta-6 acceptance tests.

## Constraints

| ID | Constraint | Type |
|----|-----------|------|
| C-1 | 4-layer architecture enforced: UI → Controller → Service → Infrastructure. No layer skips. | protocol |
| C-2 | QProcess for external CLI tools, QThread for internal processing (AD-1) | protocol |
| C-3 | 7-stage pipeline: Inspect → Extract Audio → Transcribe → Detect Slides → Align → Review Ready → Export (as-built, not the 8-stage design spec) | schema |
| C-4 | Per-stage state.json with atomic writes (temp-file + os.replace) and crash recovery (AD-2) | schema |
| C-5 | Plain files and JSON manifests — no database (AD-3) | schema |
| C-6 | Application-relative binary resolution via sys._MEIPASS or project root (AD-4) | protocol |
| C-7 | Privacy: P1-P7 — no telemetry, no upload, no credential storage, no original video modification | nfr |
| C-8 | Network offline by default. Only sanctioned: localhost Ollama, opt-in Groq API (after per-job consent) | nfr |
| C-9 | API keys in Windows Credential Manager only — never in config, job JSON, or logs (AD-13) | protocol |
| C-10 | Target hardware: Intel i7-9700F + AMD Vega 56. No NVIDIA/CUDA/ROCm assumption. CPU mandatory; Vulkan optional. | nfr |
| C-11 | Windows 10/11 x64 only (ctypes + Advapi32.dll in secret_store.py, CREATE_NO_WINDOW, taskkill) | platform |
| C-12 | Dependencies: PySide6 6.11.x, opencv-python-headless 5.x, scikit-image 0.26.x, Pillow 12.x, ReportLab 4.x, img2pdf 0.6.x, Jinja2 3.x, pytest 8.x, pytest-qt 4.x, PyInstaller 6.x | schema |
| C-13 | Tests must pass before any phase reported complete. Actual pytest output required. No weakening or deletion of tests. | protocol |

## Locked Decisions (ADR)

| ID | Decision | Scope | Status |
|----|----------|-------|--------|
| AD-1 | QProcess for external tools, QThread for internal processing | Process isolation, threading model | LOCKED |
| AD-2 | Per-stage state machine with atomic writes | Crash recovery, job state persistence | LOCKED |
| AD-3 | Plain files and JSON manifests, no database | Data persistence, job storage | LOCKED |
| AD-4 | Application-relative paths for external binaries | Binary resolution, packaging | LOCKED |
| AD-5 | Deterministic CV pipeline for slide detection (no LLM) | Slide detection algorithm | LOCKED |
| AD-6 | ReportLab for study-pack PDF, img2pdf for slides-only PDF | PDF generation | LOCKED |
| AD-7 | Self-contained HTML with base64 images | Offline export | LOCKED |
| AD-8 | PyInstaller over Nuitka for initial packaging | Windows packaging, distribution | LOCKED |
| AD-9 | Adaptive baseline and two-path slide detection | v0.4 slide detection enhancement | LOCKED |
| AD-10 | Non-blocking UI shutdown and PID-scoped process trees | v1.2 process lifecycle, UI responsiveness | LOCKED |
| AD-11 | Separate user study data from source-derived artifacts | v1.2 study workspace, data provenance | LOCKED |
| AD-12 | Provider-neutral transcription above local compute engines | v1.2 transcription architecture | LOCKED |
| AD-13 | Opt-in Groq audio transcription with Credential Manager | v1.2 online transcription, credential management | LOCKED |

## Tech Debt (Not Locked — Identified for Future Remediation)

- Fresh config persists blank FFmpeg, ffprobe, Whisper executable, and model paths; only FFmpeg initializes during normal startup.
- Whisper discovery is diagnostics-only, while desktop processing rejects the empty paths before engine discovery can help.
- Portable packaging checks required payload presence and size but does not execute binaries, prove DLL/model loading, or initialize a disposable profile.
- Startup automatically activates the latest completed lecture rather than showing an empty Home screen.
- No signed, exact-version, transactional repair path exists for the bundled CPU runtime.
- Theme initialization and repeated entrance animation can create flicker/repaint artifacts; long local-model names can overflow.
- `QThread.terminate()` still used for AlignWorker and ExportWorker, contradicting AD-10 rationale
- `FFmpegWrapper.inspect_video` runs synchronously on GUI thread with no timeout
- Detector decision logic duplicated ~400 lines across piped and legacy paths
- Piped detector can emit candidates whose image file was never written
- Groq chunk cache unbounded; glossary no-op changes bust cache
- No cooperative cancel flag for AlignWorker/ExportWorker
- No timeout on ffprobe inspect; OneDrive placeholder stall risk
- Test count drift: 149 collected vs 151 recorded in latest handoff
- `run_packaged_validation` in app.py hardcodes owner paths and mutates real user data
- `validate_real_video.py` uses removed WhisperWrapper API

## Success Criteria

1. A fresh disposable profile discovers, validates, and persists the packaged FFmpeg, ffprobe, CPU Whisper CLI/DLLs, and `ggml-base.en.bin` without manual configuration.
2. Missing or corrupt required components trigger the hard setup gate; one-click repair verifies a signed exact-version manifest and SHA-256 hashes, installs transactionally, and recovers automatically.
3. Healthy startup shows an empty Home screen with existing jobs visible but inactive; the synthetic demo never creates a permanent library item.
4. The offline demo completes the real import-to-export workflow on the minimum supported CPU and cleans up safely after success, cancellation, or crash.
5. Beta-5 appearance and intentional animation behavior remain intact while regression tests and manual comparison show no unwanted theme flash, repaint flicker, model-name overflow, or layout jump.
6. Targeted tests and the full pytest suite pass, and the public release gate is completed on CPU-only, NVIDIA, and AMD/Intel Windows systems across fresh/upgraded profiles and hostile paths.

## Current Milestone: v0.9.0-beta.6 Clean-Machine Reliability and Onboarding

**Goal:** Make the portable beta initialize, repair, teach, and validate its complete core workflow reliably on clean Windows machines.

**Target features:**
- Deterministic bundled-runtime bootstrap and validation
- Hard setup gate with signed transactional one-click repair
- Empty launch ownership and concise real guided demo
- Strict visual preservation with artifact-only fixes
- Automated and physical clean-machine release gates

## Architecture Reference

See `.planning/codebase/ARCHITECTURE.md` for the as-built architecture. See `docs/ARCHITECTURE.md` for the design document with v1.0.1, v1.1, and v1.2 addenda.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Move verified requirements to validated status.
2. Record invalidated or deferred requirements honestly.
3. Add newly approved requirements and technical decisions.
4. Recheck whether the overview and current milestone still match reality.

**After each milestone:**
1. Review all requirements and exclusions.
2. Reconfirm the core value and clean-machine promise.
3. Record release evidence and unresolved gaps.

---
*Last updated: 2026-07-27 after beta-6 milestone discussion*
