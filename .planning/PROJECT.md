# PROJECT.md — LecturePack

## Overview

LecturePack is a Windows desktop application (PySide6 / Python 3.12, packaged with PyInstaller onedir) that converts locally stored university lecture videos into study materials: timestamped transcripts, recovered slide images, aligned study packs, and a student workspace with bookmarks and notes. Local-first with optional Groq online transcription.

## Core Value

Convert lecture videos into complete, reviewable, portable study packs — entirely on-device, with no accounts, no telemetry, and no cloud dependency by default.

## Scope

- **Current state:** v1.2-hybrid-study branch with complete stability, Study workspace, and Groq architecture code. Published release is v1.1.0.
- **Immediate goal:** Package, test, validate, and ship v1.2 as a release.
- **Architecture:** Strict 4-layer model (UI → Controller → Service → Infrastructure), per-job staged pipeline, plain-file JSON persistence, QProcess for external tools, QThread for internal compute.

## Goals

1. Ship v1.2 as a packaged release from the v1.2-hybrid-study branch
2. Full test suite passing (151+ tests) with clean application self-test
3. PyInstaller packaging spec audited and validated against the current module tree
4. Version strings updated from stale 1.1.0 to 1.2.0
5. No import errors, QThread lifecycle issues, or QSS syntax errors on startup

## Non-Goals

- New feature development beyond packaging/shipping v1.2
- Groq live API validation (deferred — no API key available; online modes remain architecturally complete but unproven)
- Deep tech debt remediation (cooperative cancel for align/export, GUI-thread subprocess fixes, detector deduplication, virtualized review widgets)
- Additional UI redesign or new workspaces
- CI/CD pipeline setup

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

- Version strings stale at 1.1.0 across __init__.py, constants.py, build_release.py, and LecturePack.spec
- Packaging spec (hiddenimports) not audited since v1.1; v1.2 modules may be missing
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

**Primary (must pass before v1.2 release):**
1. Full pytest suite passes with clean output (target: 151+ tests, 0 failures, 0 errors)
2. Application self-test (`--selftest`) passes: all imports resolve, MainWindow constructs, QSS validates, no QThread lifecycle errors
3. PyInstaller package builds successfully from the current tree; packaged EXE initializes without import/startup errors
4. Version strings consistently report 1.2.0 across all artifacts

**Secondary (verified by owner):**
5. UI visual correctness verified manually (navigation, pages, Study workspace, theme)
6. Packaged EXE processes a real lecture video end-to-end (acceptance test)

## Architecture Reference

See `.planning/codebase/ARCHITECTURE.md` for the as-built architecture. See `docs/ARCHITECTURE.md` for the design document with v1.0.1, v1.1, and v1.2 addenda.
