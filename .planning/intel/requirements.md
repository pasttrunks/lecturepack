# LecturePack -- Requirements Intel

Extracted from: PRODUCT_SPEC.md (SPEC), ARCHITECTURE.md (SPEC), IMPLEMENTATION_PLAN.md (SPEC), TEST_PLAN.md (SPEC)

---

## REQ-core-conversion
- source: docs/PRODUCT_SPEC.md
- description: Lecture Pack converts locally stored university lecture videos into study materials: timestamped transcript, slides PDF, individual slide images, combined study pack, review interface, and optional local AI study notes.
- acceptance: All core processing runs locally without paid APIs, subscriptions, cloud processing, accounts, telemetry, or usage limits. Local LLM is optional.
- scope: core product purpose

---

## REQ-privacy-safety
- source: docs/PRODUCT_SPEC.md
- description: P1: No telemetry/analytics. P2: No network except first-run model downloads and localhost LM Studio. P3: Never upload videos/audio/transcripts/slides. P4: Never access university portals or store credentials. P5: Never modify/delete original video. P6: Never execute transcript content as commands. P7: All external process paths safely escaped.
- acceptance: All seven privacy rules verified by automated and manual tests.
- scope: privacy, safety, data protection

---

## REQ-transcription
- source: docs/PRODUCT_SPEC.md
- description: Inspect source via ffprobe, extract 16 kHz mono WAV, run whisper.cpp outside UI process, capture progress/logs, export timestamped JSON/SRT/TXT, preserve raw output, allow separate edited transcript, stop cleanly on cancel, resume without repeating audio extraction, report CPU/Vulkan backend, support configurable glossary, never silently correct names/numbers.
- acceptance: All 12 transcription requirements verified per TEST_PLAN.md Section 3.3.
- scope: transcription pipeline

---

## REQ-slide-extraction
- source: docs/PRODUCT_SPEC.md
- description: Deterministic CV pipeline (no LLM). Three-stage cascade: dHash fast screen, SSIM confirmation, histogram+pixel diff tiebreaker. Preprocessing (crop, mask, downscale, grayscale, blur, temporal median filter). Stability detection. Change type classification. Sequential and global deduplication. Full metadata recording.
- acceptance: All slide detection assertions per TEST_PLAN.md Section 3.4 met.
- scope: slide detection

---

## REQ-alignment
- source: docs/PRODUCT_SPEC.md
- description: Deterministic timestamp overlap alignment. Each slide has display interval, each segment has time range. Segment assigned to slide with greatest temporal overlap. Boundary: assign to earlier slide. Every slide gets >= 1 segment; every segment maps to exactly 1 slide.
- acceptance: Alignment assertions per TEST_PLAN.md Section 3.5 met.
- scope: transcript-to-slide alignment

---

## REQ-export-formats
- source: docs/PRODUCT_SPEC.md
- description: Export formats: Slides PDF (img2pdf), Slides folder, Transcript TXT, Transcript SRT, Transcript JSON, HTML study pack (Jinja2, base64, offline), PDF study pack (ReportLab).
- acceptance: All export assertions per TEST_PLAN.md Section 3.6 met.
- scope: export pipeline

---

## REQ-job-lifecycle
- source: docs/PRODUCT_SPEC.md
- description: Support canceling and safely resuming a job. Per-stage state tracking. Crash recovery via atomic writes. Resume skips completed stages. Original video never copied into job directory.
- acceptance: Job lifecycle assertions per TEST_PLAN.md Section 3.7 met.
- scope: job management, persistence

---

## REQ-architecture-layers
- source: docs/ARCHITECTURE.md
- description: Four-layer architecture: UI (PySide6), Controller (JobController), Service (transcription, slide detection, export, alignment, LLM), Infrastructure (FFmpeg/whisper wrappers, CV engine, file I/O). Each layer calls only the layer directly below. UI never calls infrastructure directly. Services never reference UI widgets.
- acceptance: Architecture constraints enforced by code review and test structure.
- scope: system architecture

---

## REQ-implementation-phases
- source: docs/IMPLEMENTATION_PLAN.md
- description: Six development phases: Phase 1 (Foundation), Phase 2 (Transcription MVP), Phase 3 (Slide Extraction MVP), Phase 4 (Review and Alignment), Phase 5 (Study-Pack Export and Packaging), Phase 6 (Optional Qwen Module). Each phase has deliverables and tag.
- acceptance: Each phase passes acceptance tests before next phase authorized.
- scope: development process

---

## REQ-test-framework
- source: docs/TEST_PLAN.md
- description: pytest 8.x with pytest-qt. Synthetic test fixtures via generate_test_video.py. Standard test video with 7 expected slides, pointer/webcam/caption distractor windows, duplicate detection. Six video variants. Nine assertion categories.
- acceptance: Full test suite passes; real-media and packaged validation performed.
- scope: testing infrastructure
