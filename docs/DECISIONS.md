# Lecture Pack -- Decision Log

Record of major technical decisions. Newest entries at the top.

---

## AD-17: "Premium Glassmorphic Dark" UI Overhaul (Phase 2, v1.4)

**Date:** 2026-07-19
**Status:** Accepted

**Context:** The v1.1 shell looked like an engineering console. Phase 2
rebuilt the visual layer as a premium dark, glassmorphic desktop experience
without touching the pipeline, services, or persistence.

**Decision:**
- **Theme:** a static `lecturepack/ui/themes/dark_theme.qss` (Catppuccin
  Mocha palette: `#1E1E2E` base, `#89B4FA` accent) with literal hex values
  (QSS has no CSS variables). `ui/theme.py` keeps its v1.1 API and gains the
  matching `MOCHA_*` constants, the Mocha dark `QPalette`, a QSS loader, and
  an `add_card_shadow` helper. The file QSS is appended last so it wins the
  cascade over the structural v1.1 rules.
- **Frameless shell:** `Qt.FramelessWindowHint` plus a custom
  `TitleBarWidget` (drag, double-click maximize, min/max/close) and a
  `QSizeGrip` in the status bar. Accepted tradeoff: Windows 11 snap layouts
  and the native drop shadow are lost.
- **Transcript rendering:** custom `TranscriptBlockWidget` cards inside a
  lazily materialized `TranscriptStreamView` (batches of 120, extended on
  scroll or via `ensure_materialized`) so long lectures never pay the full
  widget cost; `bisect`-based pure helpers do O(log n) timestamp matching.
- **Study workspace:** slide timeline (reused `SlideGridWidget`, accepted
  slides only) left, transcript right, v1.2 overview in a collapsible card.
  Bidirectional sync uses two guards — `_sync_guard` (transcript → grid)
  and `_programmatic_scroll` (cleared when the smooth-scroll animation
  finishes) — so the two directions cannot oscillate.
- **Process page:** dropzone hero with an accent glow on drag-hover;
  engine/VAD/detection settings moved into an animated-width (220 ms)
  "Advanced Settings" drawer; Phase 1's live pane now uses the same block
  widget (capped at 200 blocks). Every pre-existing widget attribute, object
  name, and signal relied on by MainWindow/tests is preserved.
- **Focus Mode:** fades exactly three shell widgets (nav rail, command bar,
  status bar) via opacity animations, then hides them; floating
  semi-transparent "Exit Focus" button plus `Esc`.
- **Page transitions:** `AnimatedStackedWidget` (180 ms slide+fade) with a
  rapid-navigation guard.
- The dark theme remains **opt-in** (`dark_theme` config default unchanged);
  flipping the default was outside the approved phase file list.

**Alternatives considered:**
- QSS generated in Python from constants (single source of truth): rejected
  in favor of a readable, hand-tweakable static QSS file plus mirrored
  constants for widget code.
- Overlay (non-layout) settings drawer: rejected; in-layout animated
  `maximumWidth` is simpler and avoids overlay geometry bugs.
- Native title bar with dark theme only: rejected; the frameless shell is
  core to the intended look.
- Showing all slides (incl. rejected) in the Study workspace: rejected;
  Study is a post-review reading surface, so it shows accepted slides only.

---

## AD-16: Live Transcript Streaming from whisper.cpp stdout; No Controller Thread Move (v1.3)

**Date:** 2026-07-18
**Status:** Accepted

**Context:** During transcription the UI appeared frozen and no transcript text
was visible until the stage completed. The transcription path already used
`QProcess` asynchronously, so the freeze was not process blocking. The real
causes were (a) whisper-cli carriage-return progress updates forwarded per
chunk into `QTextEdit.insertPlainText`, forcing hundreds of document
relayouts per second and starving the GUI event loop, and (b) transcript
text existing only in the final `raw.json/srt/txt` artifacts.

**Decision:** Parse whisper.cpp's real-time stdout segment lines
(`[HH:MM:SS.mmm --> HH:MM:SS.mmm] text`) incrementally and surface them as
ephemeral, display-only `segment_ready` dicts
(`{"start_ms", "end_ms", "text", "seq"}`). The chain is
`WhisperWrapper.segment_ready` -> `TranscriptionBackend.segment_ready` (new
optional interface signal, advertised via
`BackendCapabilities.supports_live_segments`) -> `JobController.transcript_segment`
-> the process page's live-transcript pane. Live segments are never written to
the raw/normalized/working persistence layers; the canonical transcript is
still built from `raw.json` on stage success. Separately, transcribe-stage log
output is coalesced in `JobController` and flushed to `stage_log` on a 200 ms
`QTimer` (with a final flush before the result is handled), which removes the
relayout storm for all log consumers.

`JobController` was deliberately **not** moved to a dedicated `QThread`:
`QProcess` signals are already non-blocking and delivered through the GUI
event loop, so the move would add cross-thread lifecycle risk (cancel
semantics, worker parenting, job-state saves) with no measured benefit.

**Alternatives considered:**
- Moving `JobController` (or only `WhisperWrapper`+`QProcess`) to a worker
  thread: rejected for Phase 1; adds thread-affinity complexity and does not
  address the log-relayout storm, which was the actual freeze. The
  wrapper-only variant remains an option if process I/O ever measurably
  contends with the GUI.
- True word-level streaming via `whisper-stream`: rejected as an engine
  change with unverified Vulkan-build implications. whisper-cli emits
  segment-per-line only, so Phase 1 delivers segment-level live text.
- UI-side throttling in the process page: rejected in favor of the
  controller-side throttle so every present and future `stage_log` consumer
  benefits.

**Rationale:** The parser operates on a byte buffer split on both `\n` and
`\r`, which tolerates merged-channel progress pollution and decodes complete
lines only, fixing split multi-byte UTF-8 across reads. An unterminated
trailing line is flushed at process end so no segment is lost.

---

## AD-15: Baseline-Gated Architecture Release Check (v1.2)

**Date:** 2026-07-18
**Status:** Accepted

**Context:** The Phase 1 whole-tree import audit correctly found 47 existing
violations of the approved adjacent-layer rule across 62 cross-layer edges.
Eliminating those violations requires a broad production refactor outside the
packaging release scope. The audit remains useful as a release regression gate,
but its existing debt must not be mistaken for strict conformance.

**Decision:** The strict UI -> Controller -> Service -> Infrastructure rule in
`docs/ARCHITECTURE.md` remains the target architecture. For the v1.2 Phase 1
packaging release, the architecture gate blocks only a violation whose exact
identity is absent from the evidence committed at `25e9dd1`. The 47 existing
violations across 62 cross-layer edges are disclosed baseline debt and are
deferred to Phase 2 for closure. Phase 1 may report `ARCHITECTURE_CHECK: PASS`
only when `NEW_VIOLATIONS_COUNT: 0`; it must also report that strict architecture
conformance has not been achieved.

**Alternatives considered:** Blocking the v1.2 packaging release on an immediate
broad architecture refactor was rejected because it materially expands Phase 1
and risks unrelated release behavior. Silently ignoring or removing the audit
was rejected because it would erase known debt and permit new violations to
enter undetected.

**Rationale:** An immutable, identity-level baseline preserves a fail-closed
no-regression gate for the release while keeping all existing violations visible
and assigning their actual remediation to a separately planned Phase 2 effort.

---

## AD-14: Canonical Runtime and Build Version Authority (v1.2)

**Date:** 2026-07-18
**Status:** Accepted

**Context:** The package initializer, application constants, release script,
and human-facing build labels previously carried independent release-version
literals. That allowed the runtime version, new-job manifests, archive names,
and release metadata to drift apart during a release update.

**Decision:** Define the executable release semantic version only in
`lecturepack.__version__`. Application code consumes that value through
`constants.APP_VERSION`, and release tooling consumes it through
`build_release.VERSION`. Human-facing build labels, including the
`LecturePack.spec` header, remain synchronized with the canonical version but
are explicitly non-authoritative.

**Alternatives considered:** Keeping independent literals in every consumer
was rejected because it preserves the source of runtime, manifest, and archive
drift. Parsing the PyInstaller spec header at runtime was rejected because a
human-facing comment is not an import-safe metadata contract and would couple
application startup to build configuration text.

**Rationale:** A dependency-free package-level authority is available to both
runtime and build consumers without initialization-order dependencies, while
synchronized labels remain readable to release reviewers.

---

## AD-13: Opt-In Groq Audio Transcription with Credential Manager (v1.2)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** Online Fast and Online Accurate must improve transcription speed or
accuracy without weakening Private Local defaults, uploading visual/job data,
persisting API keys, blocking the Qt event loop, or replacing a valid local
transcript with a partial provider result. Provider limits and pricing can
change independently of LecturePack.

**Decision:** Register two explicit provider adapters above the neutral
transcription seam: `groq-fast` uses `whisper-large-v3-turbo` and
`groq-accurate` uses `whisper-large-v3`. Private Local remains the default for
new and old jobs. Require per-job consent immediately before an online run and
read the key only from Windows Credential Manager. Upload only lossless FLAC
audio derived from the existing 16 kHz mono WAV; do not send video, slides,
transcript text, job metadata, or glossary prompts.

Use a conservative 23 MiB direct-upload ceiling beneath Groq's documented
25 MB free-tier limit. Plan overlapping, ordered chunks from worst-case PCM
size, encode each with an exact LecturePack-owned FFmpeg PID, retry transient
errors with bounded exponential backoff and `retry-after`, cache successful
per-chunk JSON by an input fingerprint, offset timestamps, remove overlap
duplicates, and atomically publish canonical raw outputs only after all chunks
merge. On eligible online failure, retry only the transcription branch through
Private Local while concurrent slide detection continues. Preserve any prior
canonical transcript until either provider or fallback succeeds.

**Alternatives considered:** Storing a key in `config.json` or job settings was
rejected as plaintext secret persistence. Environment-only configuration was
rejected because it does not provide the required native Set/Test/Remove
workflow. Adding the Groq SDK was rejected because the OpenAI-compatible
multipart endpoint is small enough for the standard library and a new runtime
dependency was unnecessary. Uploading the original video was rejected because
only audio is required. Assuming developer-tier limits or a free allowance was
rejected because limits and billing are account-specific and mutable.

**Rationale:** This design makes every network action visible and opt-in,
minimizes uploaded data, resumes safely, keeps the native window responsive,
and preserves the already-proven local path as a real fallback rather than a
second provider implementation.

**Official sources checked 2026-07-16:**
[Groq Speech to Text](https://console.groq.com/docs/speech-to-text),
[Groq rate limits](https://console.groq.com/docs/rate-limits),
[Groq API errors](https://console.groq.com/docs/errors), and the official model
pages for
[`whisper-large-v3-turbo`](https://console.groq.com/docs/model/whisper-large-v3-turbo)
and [`whisper-large-v3`](https://console.groq.com/docs/model/whisper-large-v3).

---

## AD-12: Provider-Neutral Transcription Above Local Compute Engines (v1.2)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** LecturePack already has a proven `EngineRegistry` for selecting
whisper.cpp CPU or Vulkan binaries. Optional online transcription needs a
separate provider boundary without scattering HTTP, secret, retry, chunk, or
fallback logic through `JobController`, and without recasting a selected
engine as proof of the backend that actually loaded.

**Decision:** Add a service-layer `TranscriptionBackend` QObject contract with
explicit capability, request, result, progress, runtime-backend, cancellation,
and structured-error data. Keep CPU/Vulkan selection inside a
`LocalWhisperCppBackend` adapter around the existing QProcess wrapper. A
`BackendRegistry` resolves provider-level choices and fails closed to Private
Local when a requested adapter is absent. Persist requested provider,
effective provider, selected local engine, and runtime-proven backend as
distinct fields.

The existing local stage fingerprint remains byte-identical when the local
default is implicit or explicit. Non-local requests include both requested and
currently resolvable effective adapters, so output created by a local fallback
is invalidated if that provider later becomes available.

**Alternatives considered:** Treating CPU and Vulkan as cloud-equivalent
providers was rejected because they share the same executable contract and
canonical output. Putting provider branches directly in `JobController` was
rejected because it couples scheduling to vendor behavior. Replacing
`WhisperWrapper` was rejected because its QProcess, cancellation, and
runtime-backend parsing are already tested. Adding an SDK/dependency in this
phase was rejected because no online adapter is yet enabled.

**Rationale:** The boundary keeps private local behavior and old cache keys
stable while giving later Groq/Gemini work one injectable, cancellable seam.
Capability metadata makes upload/secret behavior auditable before any backend
can be presented to the user.

---

## AD-11: Separate User Study Data from Source-Derived Artifacts (v1.2 Study)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** The Study workspace needs durable slide bookmarks, section
bookmarks, short notes, and a per-job resume position. Writing those values
into `candidates.json`, raw/working transcript layers, or aligned output would
mix user-authored content with source-derived content and make re-export less
safe. The overview also needs to work offline and must not silently introduce
AI-generated claims.

**Decision:** Store user-authored Study state in one atomic per-job
`study.json` file (schema version 1). Derive overview text, topics, key terms,
review counts, duration, and the actually loaded backend from existing job
artifacts on demand. Label deterministic summary provenance in the UI and
keep AI-marked section headings visibly marked. Export Study data with
explicit source-derived and user-authored provenance groups.

**Alternatives considered:** Extending `candidates.json` was rejected because
candidate decisions are source-processing state. Extending transcript
`working.json` was rejected because bookmarks and resume positions are not
transcript edits. SQLite was rejected because per-job atomic JSON is already
the project persistence contract. Generating the overview with a provider was
rejected for this phase because it would add latency, nondeterminism, and a
network/provider dependency outside the approved scope.

**Rationale:** A dedicated user-data layer preserves provenance, permits old
jobs with no Study file to open unchanged, makes restart behavior auditable,
and allows HTML/PDF/JSON exports to include notes without modifying raw
transcript, source metadata, or candidate images.

---

## AD-10: Non-Blocking UI Shutdown and PID-Scoped Process Trees (v1.2 stability)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** Closing Context Repair could wait up to five seconds for a
cooperative network worker, application close did not explicitly cancel the
active controller, and direct `QProcess.kill()` did not guarantee that helper
descendants exited. The UI also displayed requested/capability backends after
a run instead of retaining the backend actually reported by whisper.cpp.

**Decision:**

1. Detach Context Repair workers immediately on owner close, request
   cooperative cancellation, and retain strong ownership in a detached-worker
   registry until each QThread has really finished.
2. Route application close through `JobController.cancel()` before tearing
   down page workers.
3. On Windows, terminate an external-tool tree by the exact root PID returned
   by LecturePack's `QProcess` using `taskkill /PID <pid> /T /F`. Never kill by
   executable/image name. Retain terminate/kill fallback behavior on non-Windows.
4. Persist the backend emitted by whisper.cpp under
   `state.json -> stages -> Transcribe -> backend_used`; prefer that value over
   requested-engine and binary-capability labels when a job is reopened.

**Alternatives considered:** Blocking `QThread.wait()` was rejected because it
freezes close handling. `QThread.terminate()` was rejected for Context Repair
because asynchronous thread termination can interrupt Python/Qt state at an
unsafe point. Image-name process killing was rejected because it can terminate
unrelated user processes. Persisting only the requested engine was rejected
because auto/fallback resolution does not prove which compute backend loaded.

**Rationale:** The selected design keeps the native window responsive, preserves
Qt object lifetime, scopes destructive process action to PIDs LecturePack
created, and makes backend diagnostics auditable across restarts.

---

## AD-9: Adaptive Baseline and Two-Path Slide Detection (v0.4.0)

**Date:** 2026-07-15 (Phase 4)  
**Status:** Accepted  

**Context:** The slide detection engine needs to handle animated builds, transitions, and noise without producing excessive false slide candidates, while ensuring real slides and small persistent additions (progressive builds/handwriting) are correctly captured.

**Decision:** Replace the single-threshold slide change cascade with two explicit detection paths:
1. **Major Slide-Change Path**: Evaluates frame changes against a rolling local baseline of recent frame-to-frame changes. A change is accepted only if it stands significantly above this baseline and stabilizes.
2. **Progressive-Build Path**: Identifies small persistent localized additions using contour analysis on the difference image, filtering out pointer-sized or caption-sized regions, and verifying spatial persistence in subsequent frames.

Expose a single simple sensitivity control ("Conservative", "Balanced", "Detailed") in the UI that internally configures thresholds and window metrics.

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
