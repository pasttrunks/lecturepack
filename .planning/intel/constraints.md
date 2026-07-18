# LecturePack -- Constraints Intel

Extracted from: ARCHITECTURE.md (SPEC), IMPLEMENTATION_PLAN.md (SPEC), PRODUCT_SPEC.md (SPEC), TEST_PLAN.md (SPEC)

---

## CONSTRAINT-layered-architecture
- source: docs/ARCHITECTURE.md
- type: protocol
- content: Four-layer architecture enforced: UI -> Controller -> Service -> Infrastructure. Each layer may only call the layer directly below. UI never calls infrastructure directly. Services never reference UI widgets. Infrastructure never holds application state.

---

## CONSTRAINT-threading-model
- source: docs/ARCHITECTURE.md
- type: protocol
- content: QProcess for external CLI tools (FFmpeg, whisper-cli) integrated with Qt event loop. QThread with worker objects for internal Python processing (OpenCV, hashing, ReportLab). Workers emit progress signals consumed by UI. Cancellation: QProcess uses terminate() (WM_CLOSE on Windows), QThread workers check cancellation flag between iterations.

---

## CONSTRAINT-pipeline-stages
- source: docs/ARCHITECTURE.md
- type: schema
- content: Seven sequential stages in v1.0.1: Inspect, Extract Audio, Transcribe, Detect Slides, Align, Review Ready, Export. Each independently tracked in state.json. Product modes gate stage execution (Transcript Only skips Detect Slides; Slides Only skips Extract Audio + Transcribe).

---

## CONSTRAINT-state-persistence
- source: docs/ARCHITECTURE.md
- type: schema
- content: state.json written atomically (temp-file + os.replace). Stage statuses: pending|running|completed|failed|cancelled|skipped. On startup, "running" reclassified as "interrupted". Resume skips completed stages. Output files use temporary names (*.tmp), renamed on completion.

---

## CONSTRAINT-binary-resolution
- source: docs/ARCHITECTURE.md
- type: protocol
- content: External binaries resolved at runtime via sys._MEIPASS (PyInstaller) or project root (development). Never on system PATH. Bundled: ffmpeg.exe 8.1.x, ffprobe.exe 8.1.x, whisper-cli.exe v1.9.1.

---

## CONSTRAINT-whisper-backend-selection
- source: docs/ARCHITECTURE.md
- type: protocol
- content: Backend selection: If cpu -> force CPU; If vulkan -> attempt Vulkan, fail if unavailable; If auto -> check Vulkan binary exists, run 5s probe, parse stderr for ggml_vulkan/whisper_backend_init_gpu, use Vulkan if initializes else fall back to CPU. CPU is primary path; Vulkan is optional accelerator.

---

## CONSTRAINT-data-layout
- source: docs/ARCHITECTURE.md
- type: schema
- content: LecturePackData/ (default ~/LecturePackData, configurable): config.json, jobs/<job-uuid>/ (manifest.json, source.json, settings.json, state.json, audio/, transcript/, frames/, exports/, logs/), models/ (ggml-*.bin), logs/app.log.

---

## CONSTRAINT-source-fingerprint
- source: docs/ARCHITECTURE.md
- type: schema
- content: Partial hash: SHA-256 of (first 64 KB + last 64 KB + file size as 8-byte big-endian). Runs in milliseconds. Used to detect whether original file has changed.

---

## CONSTRAINT-dependency-matrix
- source: docs/IMPLEMENTATION_PLAN.md
- type: schema
- content: Python: PySide6 6.11.x, opencv-python-headless 5.0.x, scikit-image 0.26.x, Pillow 12.x, imagehash 4.3.x, img2pdf 0.6.x, ReportLab 4.x, Jinja2 3.x, openai 1.x. Dev: pytest 8.x, pytest-qt 4.x, PyInstaller 6.x.

---

## CONSTRAINT-json-schemas
- source: docs/IMPLEMENTATION_PLAN.md
- type: schema
- content: Six JSON schemas defined: manifest.json, source.json, settings.json, state.json, candidate frame metadata. All have schema_version field. settings.json contains preset, whisper config, slide_detection thresholds, export formats, glossary.

---

## CONSTRAINT-slide-detection-algorithm
- source: docs/IMPLEMENTATION_PLAN.md
- type: protocol
- content: Three-stage cascade: Stage 1 dHash (H<=3 reject, H>=20 accept), Stage 2 SSIM (>=0.92 reject, <=0.75 accept), Stage 3 tiebreaker (histogram Bhattacharyya + pixel diff). Stability detection: 0.25s checks, N consecutive with SSIM>=0.97, max 5s wait. Four presets with different thresholds.

---

## CONSTRAINT-privacy-requirements
- source: docs/PRODUCT_SPEC.md
- type: nfr
- content: No telemetry/analytics (P1). No network except first-run model downloads and localhost LM Studio (P2). Never upload videos/audio/transcripts/slides (P3). Never access university portals or store credentials (P4). Never modify/delete original video (P5). Never execute transcript content as commands (P6). All external process paths safely escaped (P7).

---

## CONSTRAINT-target-hardware
- source: docs/PRODUCT_SPEC.md
- type: nfr
- content: Intel Core i7-9700F (8C/8T, 3.0-4.7 GHz, AVX2), AMD Radeon RX Vega 56 8GB HBM2, 24GB DDR4, SSD, Windows desktop. Must not assume NVIDIA GPU, CUDA, ROCm, or Apple Silicon.

---

## CONSTRAINT-test-execution-rules
- source: docs/TEST_PLAN.md
- type: protocol
- content: Tests must pass before any phase reported complete. Actual pytest output must be included. Tests must not be weakened, deleted, or mocked to force passage. Mocks acceptable for external tools in unit tests; integration tests must use real binaries. Synthetic test video generator maintained alongside tests. Screenshots/recordings for UI acceptance.
