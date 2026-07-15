# Lecture Pack -- Decision Log

Record of major technical decisions. Newest entries at the top.

---

## AD-8: PyInstaller over Nuitka for Initial Packaging

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The application bundles PySide6, OpenCV-headless, scikit-image, ReportLab, img2pdf, and external binaries (FFmpeg, whisper-cli). Packaging must produce a standalone Windows executable that works on a clean machine without Python installed.

**Decision:** Use PyInstaller in standalone directory mode for initial packaging.

**Alternatives considered:**
- Nuitka: produces smaller binaries and fewer antivirus false positives, but has a steeper setup curve and occasional version-specific regressions with complex dependency sets.
- pyside6-deploy: wraps Nuitka but is semi-experimental with sparse documentation and poor ergonomics. Not recommended for production.
- cx_Freeze: smaller community, requires more manual configuration.

**Rationale:** PyInstaller has the most mature hook system for PySide6 and OpenCV. Its Qt plugin auto-detection reduces the risk of blank-window crashes on clean machines. The GPL-2.0 bootloader exception permits packaging proprietary applications. Nuitka remains available as a future optimization if package size or AV false positives become problems.

**Sources:** nuitka.net, pyinstaller.org, PySide6 packaging docs

---

## AD-7: Self-Contained HTML Study Pack with Base64 Images

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The HTML study pack must work offline without a web server. Browsers block `file://` protocol video seeking (no HTTP Range Request support), so embedded `<video>` with `currentTime` seeking is unreliable for local files.

**Decision:** Generate a single self-contained HTML file with slide images embedded as base64 data URIs. Video timestamp links open the source video in the system default player rather than seeking within the HTML page.

**Alternatives considered:**
- Embedded `<video>` with `file://` src: blocked by browser security policies.
- Local HTTP server: works but adds complexity and violates the Qt-only requirement.
- Electron wrapper: explicitly excluded by the specification.

**Rationale:** A single-file HTML with embedded images is the simplest offline-compatible approach. The video seeking limitation is documented in the study pack header. A future enhancement could use QMediaPlayer within the Qt application for integrated slide-to-video navigation.

---

## AD-6: ReportLab for Study-Pack PDF, img2pdf for Slides-Only PDF

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** Two different PDF outputs are needed: (1) a slides-only PDF containing original slide images with no re-encoding, and (2) a study-pack PDF combining slide images with transcript text, requiring text layout and pagination.

**Decision:** Use img2pdf for the slides-only PDF (lossless image embedding) and ReportLab for the study-pack PDF (Platypus layout engine for mixed image+text content).

**Alternatives considered:**
- WeasyPrint for study-pack PDF: renders HTML/CSS to PDF with automatic pagination, but requires native system libraries (Cairo, Pango, GTK) that are difficult to bundle on Windows and add ~100 MB of dependencies.
- ReportLab for both: possible but img2pdf is more efficient for image-only PDFs (embeds raw JPEG/PNG streams without re-encoding).

**Rationale:** ReportLab is pure Python with no native system dependencies, making packaging straightforward. WeasyPrint's Cairo/Pango/GTK dependency chain is a significant packaging obstacle that could delay Phase 5.

**Sources:** reportlab.com, github.com/josch/img2pdf, courtbouillon.org (WeasyPrint docs)

---

## AD-5: Deterministic CV Pipeline for Slide Detection (No LLM)

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The slide extractor must identify visual slide transitions in lecture videos. Two approaches: send frames to an LLM for analysis, or use deterministic computer vision techniques.

**Decision:** Use a three-stage tiered cascade (dHash fast screen, SSIM confirmation, histogram tiebreaker) with temporal median filtering, stability detection, and preset-specific thresholds.

**Rationale:** Deterministic CV is reproducible, testable, has no external dependency, and runs locally without a GPU-bound LLM. The tiered approach is fast (~80% of frames rejected at Stage 1) and tunable via preset parameters. Full decision metadata is recorded for every frame, enabling post-hoc debugging and threshold adjustment.

**Sources:** OpenCV docs, scikit-image SSIM docs, imagehash library

---

## AD-4: Application-Relative Paths for External Binaries

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The application depends on FFmpeg and whisper-cli executables. These must be reliably located at runtime on any Windows machine.

**Decision:** Bundle binaries in a `bin/` subdirectory relative to the application. Resolve paths using `sys._MEIPASS` (PyInstaller) or project root (development). Never rely on system PATH.

**Rationale:** Eliminates the failure mode where the user has an incompatible system FFmpeg or no FFmpeg at all. Guarantees version compatibility.

---

## AD-3: Plain Files and JSON Manifests (No Database)

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** Job state and metadata must be persisted between sessions and recoverable after crashes.

**Decision:** Use plain files (JSON, PNG, WAV, SRT) organized in a per-job directory structure. No SQLite or other embedded database.

**Rationale:** Human-readable and recoverable without proprietary tools. A user can inspect job state with a text editor. The directory structure is self-describing. Crash recovery can be implemented by checking which output files exist.

---

## AD-2: Per-Stage State Machine with Atomic Writes

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** Processing a lecture involves 8 sequential stages. The application must resume after crashes without repeating completed work.

**Decision:** Track each stage's status (pending/running/completed/failed/cancelled) in `state.json`. Write atomically using temp-file + `os.replace()`. On startup, reclassify any "running" stage as "interrupted" and offer resume.

**Rationale:** Atomic writes prevent corrupt state files. Per-stage tracking enables granular resume. Output files use temporary names during creation and are renamed on completion, so partial files are never mistaken for complete ones.

---

## AD-1: QProcess for External Tools, QThread for Internal Processing

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The application must remain responsive during long-running operations (transcription, slide detection, export). External CLI tools (FFmpeg, whisper-cli) and internal Python processing (OpenCV frame comparison) both need to run without blocking the UI.

**Decision:** Use QProcess for external CLI tools and QThread with worker objects for internal Python processing. Workers emit progress signals consumed by the UI via Qt's signal/slot mechanism.

**Alternatives considered:**
- `subprocess.Popen` with threads: works but does not integrate with Qt's event loop as cleanly.
- `multiprocessing`: adds IPC complexity; QThread is sufficient since OpenCV releases the GIL during heavy computation.
- QThreadPool + QRunnable: better for many small parallel tasks; not needed for the sequential pipeline.

**Rationale:** QProcess provides non-blocking external process management integrated with Qt's event loop, with built-in `readyReadStandardOutput`/`readyReadStandardError` signals for real-time log capture. QThread workers avoid IPC overhead for internal processing while keeping the UI thread free.

**Sources:** doc.qt.io/qtforpython/PySide6/QtCore/QProcess.html, PySide6 threading guides
