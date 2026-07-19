# Project History and Core Architecture Decisions

This document summarizes the major milestones, architecture decisions, safety rules, and lessons learned from the development of Lecture Pack.

---

## 1. Major Versions and Milestones

- **v0.1.0-working-mvp** (Commit `0a6465e`): Complete working MVP of Lecture Pack. Established basic transcription with whisper.cpp, slide frame extraction using OpenCV, and ReportLab/Jinja2 exports.
- **v0.2.0-portable-release** (Commit `83a20ff`): First PyInstaller portable release candidate. Bundled FFmpeg, ffprobe, and whisper-cli binaries in a single package.
- **v0.2.1-portable-verified** (Commit `0d7f3a7`): Verified portable release fixing a startup crash related to missing dependencies.
- **v0.2.2-m4v-fix** (Commit `b89f42e`): Added support for `.m4v` video files case-insensitively and unified extension handling.
- **v0.3.0-study-workflow** (Commit `05b4d76`): Implemented non-blocking Whisper capability detection (VAD, prompt support), transcription profile recommendations, and unified PySide6 Review UI.
- **v0.4.0-adaptive-detection** (Commit `aa19732`): Introduced two-path adaptive slide detection using rolling local motion baseline and connected components contour checks.

---

## 2. Key Architecture Decisions

- **Deterministic CV Pipeline**: Lecture Pack uses purely local, deterministic CV algorithms (SSIM, difference hashing, connected components contour analysis) rather than GPU-bound LLMs or cloud APIs. This guarantees reproducibility and privacy.
- **Out-of-Process Isolation**: Long-running operations like audio extraction (`ffmpeg`) and transcription (`whisper-cli`) run out-of-process via `QProcess` to protect UI responsiveness. Internal processing (OpenCV analysis, PDF generation) runs in dedicated `QThread` workers.
- **Self-Contained Exports**: The HTML study pack is built with Jinja2 and embeds slide images as base64 data URIs. This ensures it functions offline without local HTTP servers.
- **State Machine with Atomic Writes**: Jobs write state files (`state.json`) atomically (temp file write followed by `os.replace()`) to prevent corruption during system crashes.

---

## 3. Core Safety Rules

- **No Video Modification**: The original video file must never be modified, renamed, moved, or deleted.
- **No Credentials Storage**: The app never connects to external university portals or stores user credentials.
- **Strict Local Boundary**: No network calls are made except first-run model downloads and localhost LM Studio endpoint tests. No telemetry or analytics exist.
- **Process Security**: All process invocations must safely escape executable and media paths.

---

## 4. Key Project Lessons and Risks

### 1. Job and Data Safety
- **Risk**: Auto-deleting or cleaning job directories can lead to permanent data loss of user transcripts and configurations.
- **Rule**: Lecture Pack must never automatically delete or clean up job data. Jobs are archived or restored explicitly by the user, and "deleted" slides are only marked as excluded from exports.

### 2. Dependency Inclusion in Packages
- **Lesson**: PyInstaller optimizations can exclude essential libraries (like SciPy) if not explicitly declared, causing runtime crashes during media processing.
- **Rule**: Standalone packaging verification must run the entire pipeline on actual media files, not merely verify that the application launches.

### 3. Separation of Raw and Corrected Transcripts
- **Design**: Raw transcript output (`raw.json`) must remain immutable for auditability.
- **Rationale**: User corrections are stored separately in `edited.json`. This allows the user to easily revert edits and reset individual segments without losing the baseline whisper transcription.

### 4. Quantitative Hysteresis in Slide Detection
- **Lesson**: Relying only on candidate counts is misleading (a detector can have low counts but miss major slides, or high counts with duplicates).
- **Rule**: Slide detector tuning must use ground-truth matching. Hysteresis, cooldowns, and clustering are required to coalesce rapid progressive reveals and transient motion noise (like cursor movements, transitions, and captions) into clean single-slide candidates.
