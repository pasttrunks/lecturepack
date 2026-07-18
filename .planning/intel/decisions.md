# LecturePack -- Decisions Intel

Extracted from: docs/DECISIONS.md (ADR, locked)

---

## AD-1: QProcess for External Tools, QThread for Internal Processing
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Use QProcess for external CLI tools (FFmpeg, whisper-cli) and QThread with worker objects for internal Python processing. Workers emit progress signals consumed by the UI via Qt signal/slot.
- scope: process isolation, threading model

---

## AD-2: Per-Stage State Machine with Atomic Writes
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Track each stage's status (pending/running/completed/failed/cancelled) in state.json. Write atomically using temp-file + os.replace(). On startup, reclassify any "running" stage as "interrupted" and offer resume.
- scope: crash recovery, job state persistence

---

## AD-3: Plain Files and JSON Manifests (No Database)
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Use plain files (JSON, PNG, WAV, SRT) organized in a per-job directory structure. No SQLite or other embedded database.
- scope: data persistence, job storage

---

## AD-4: Application-Relative Paths for External Binaries
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Bundle binaries in a bin/ subdirectory relative to the application. Resolve paths using sys._MEIPASS (PyInstaller) or project root (development). Never rely on system PATH.
- scope: binary resolution, packaging

---

## AD-5: Deterministic CV Pipeline for Slide Detection (No LLM)
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Use a three-stage tiered cascade (dHash fast screen, SSIM confirmation, histogram tiebreaker) with temporal median filtering, stability detection, and preset-specific thresholds. No LLM involvement.
- scope: slide detection algorithm

---

## AD-6: ReportLab for Study-Pack PDF, img2pdf for Slides-Only PDF
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Use img2pdf for the slides-only PDF (lossless image embedding) and ReportLab for the study-pack PDF (Platypus layout engine for mixed image+text content).
- scope: PDF generation

---

## AD-7: Self-Contained HTML Study Pack with Base64 Images
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Generate a single self-contained HTML file with slide images embedded as base64 data URIs. Video timestamp links open the source video in the system default player rather than seeking within the HTML page.
- scope: HTML export, offline compatibility

---

## AD-8: PyInstaller over Nuitka for Initial Packaging
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Use PyInstaller in standalone directory mode for initial packaging. Nuitka remains available as a future optimization.
- scope: Windows packaging, distribution

---

## AD-9: Adaptive Baseline and Two-Path Slide Detection (v0.4.0)
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Replace single-threshold cascade with two explicit detection paths: Major Slide-Change Path (rolling local baseline) and Progressive-Build Path (contour analysis for small persistent additions). Expose a single sensitivity control in the UI.
- scope: slide detection, v0.4 enhancement

---

## AD-10: Non-Blocking UI Shutdown and PID-Scoped Process Trees (v1.2 stability)
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Detach Context Repair workers immediately on owner close; route application close through JobController.cancel(); on Windows terminate external-tool trees by exact root PID using taskkill /PID /T /F; persist backend emitted by whisper.cpp under state.json stages Transcribe backend_used.
- scope: process lifecycle, UI responsiveness, Windows process cleanup

---

## AD-11: Separate User Study Data from Source-Derived Artifacts (v1.2 Study)
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Store user-authored Study state in one atomic per-job study.json file (schema version 1). Derive overview text, topics, key terms, review counts, duration from existing job artifacts on demand. Label deterministic summary provenance in the UI.
- scope: study workspace, data provenance separation

---

## AD-12: Provider-Neutral Transcription Above Local Compute Engines (v1.2)
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Add a service-layer TranscriptionBackend QObject contract with explicit capability, request, result, progress, runtime-backend, cancellation, and structured-error data. Keep CPU/Vulkan selection inside a LocalWhisperCppBackend adapter. A BackendRegistry resolves provider-level choices and fails closed to Private Local.
- scope: transcription provider architecture, v1.2

---

## AD-13: Opt-In Groq Audio Transcription with Credential Manager (v1.2)
- source: docs/DECISIONS.md
- status: locked (Accepted)
- decision: Register two explicit provider adapters (groq-fast: whisper-large-v3-turbo, groq-accurate: whisper-large-v3). Private Local remains the default. Require per-job consent before an online run. Read key only from Windows Credential Manager. Upload only lossless FLAC audio; 23 MiB direct-upload ceiling. Chunked upload with retry, caching, offset, de-duplication. On eligible failure, retry through Private Local.
- scope: online transcription, Groq integration, credential management
