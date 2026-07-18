# LecturePack -- Context Intel

Extracted from: DOC-type documents (20 files)

---

## Project History and Milestones
- source: docs/PROJECT_HISTORY_AND_DECISIONS.md, docs/LecturePack_Project_History_Architecture_and_Roadmap.md
- v0.1.0: Working MVP established end-to-end feasibility
- v0.2.0-0.2.1: PyInstaller portable release; startup crash fix for missing dependencies
- v0.2.2: M4V file support
- v0.3.0: Study workflow (multi-select review, transcript editing, profiles)
- v0.4.0: Adaptive slide detection experiment (frozen as experimental, not promoted)
- v1.0.0: Unified architecture consolidation
- v1.0.1: First credible real-media-verified release (70 tests, packaged validation)
- v1.1.0: UI rebuild, Vulkan backend, concurrent stages, 106 tests, 55.6% speedup reported
- v1.2: Stability (121 tests), Study workspace (130 tests), Groq architecture (151 tests)
- Current published stable: v1.1.0-ui-speed-ollama
- Active branch: v1.2-hybrid-study (never packaged or released)

---

## Critical Safety Incident
- source: docs/LecturePack_Project_History_Architecture_and_Roadmap.md
- During packaged validation, an agent used destructive cleanup against LecturePackData\jobs and deleted the original full CL100 job. This led to permanent rules: never recursively clean LecturePackData, always back up jobs before validation, use separate validation directories, require phase handoffs and safety tags.

---

## MVP Verification and What Works
- source: docs/HANDOFF.md
- Core pipeline engine with full async stages verified.
- Three-stage slide detection cascade tuned and verified.
- SSIM-deduplication guard prevents incorrect collapsing.
- Job persistence and discovery verified.
- Export services produce high-quality PDF and HTML study packs.
- All 4 tests pass in under 7 seconds.
- Real speech transcription verified with whisper-cli.exe and ggml-base.en.bin.
- Real video (1080p, 41.97s) processed: 7 slides, 100% accuracy, ~30s total pipeline.
- Re-export cache verified: 0.12s without re-running processing.

---

## Phase 0 Decisions
- source: docs/HANDOFF_PHASE_0.md
- All technology choices documented and rationale captured.
- Schemas defined in IMPLEMENTATION_PLAN.md.
- Slide detection algorithm fully specified.
- Phase 0 complete. Awaiting Phase 1 authorization.
- Known risks: Vulkan stability, threshold generalization, CPU transcription speed, PyInstaller packaging, ReportLab PDF quality.

---

## v1.2 Baseline Profiling
- source: docs/HANDOFF_PHASE_V1_2_BASELINE.md
- Branch: v1.2-hybrid-study
- Baseline on 4,479.9s lecture: Transcribe 605.41s, Detect Slides 523.47s (concurrent), Align+Export 7.39s. Total wall: 619.31s.
- Peak working set: 1,658,843,136 bytes. Peak GPU engine: 86.62%.
- Actual backend: bin\vulkan\whisper-cli.exe with ggml-small.en-q8_0.bin.
- 106 tests passed in 120.14s.

---

## v1.2 Provider-Neutral Seam
- source: docs/HANDOFF_PHASE_V1_2_PROVIDER_NEUTRAL.md
- Added TranscriptionBackend QObject contract with capabilities, request, result, progress, cancellation, error.
- LocalWhisperCppBackend wraps existing WhisperWrapper + EngineRegistry.
- BackendRegistry resolves provider-level choices, fails closed to Private Local.
- Cache fingerprints byte-identical to v1.1 for local; non-local fingerprints include adapter keys.
- 136 tests passed.

---

## v1.2 Groq Architecture
- source: docs/HANDOFF_PHASE_V1_2_GROQ.md
- Registered GroqWhisperBackend for Online Fast (whisper-large-v3-turbo) and Online Accurate (whisper-large-v3).
- Windows Credential Manager for API key storage. Per-job consent required.
- 23 MiB upload ceiling. FLAC audio only. No video/slides/transcript/metadata sent.
- Chunked upload with overlap de-duplication, retry, caching.
- Fallback to Private Local on failure. Preserves valid prior transcript.
- 151 tests passed. Live validation blocked by missing API key.

---

## v1.2 Groq Live Validation
- source: docs/HANDOFF_PHASE_V1_2_GROQ_LIVE.md
- Fixed local fallback model path resolution bug.
- Short video (42s): Online Fast 8.64s wall, Online Accurate 7.71s wall.
- Difficult-name comparison: Groq resolved "Mark Lehner" and "dolerite" correctly; local whisper.cpp did not.
- Groq Accurate omitted first 20s of intro (lower recall on low-volume segments).
- Full-lecture benchmark skipped (file not present).
- All 151 tests passed.

---

## v1.2 Stability Fixes
- source: docs/HANDOFF_PHASE_V1_2_STABILITY.md
- Fixed: slide selection scroll/preview, Context Repair non-blocking close, app-close controller cancel, PID-scoped process-tree termination, backend persistence, settings migration.
- Close latency: 0.013s dialog, 0.005s main window.
- Process-tree cleanup verified: owned PIDs terminated, unrelated processes survived.
- Re-export isolation verified: 13 artifact signatures preserved.
- 121 tests passed.

---

## v1.2 Study Workspace
- source: docs/HANDOFF_PHASE_V1_2_STUDY.md, docs/STUDY_WORKSPACE.md
- Default landing page for completed jobs: three-column layout, deterministic overview, bookmarks, notes, resume position.
- User-authored state in atomic study.json (schema 1).
- Overview derived from working transcript, aligned.json, section_overrides.json, candidates, source duration, backend_used.
- Exports include user annotations with proper escaping. Source-derived content unchanged.
- Old jobs without study.json load as empty state (no migration).
- 130 tests passed.

---

## Ollama / Local AI Integration
- source: docs/OLLAMA_SETUP.md
- Optional Ollama server (localhost:11434) for Context Repair, section headings, summaries.
- Recommended model: qwen3:1.7b (benchmarked: 5/8 correct fixes, 21.9s).
- Schema-constrained JSON output, temperature 0, finite context chunks.
- Failures never crash LecturePack. Deterministic offline repair always available.
- No AI proposal auto-accepted; each shown with diff, explanation, confidence.

---

## Performance and Backends
- source: docs/PERFORMANCE_AND_BACKENDS.md
- v1.1 speed improvements: two-pass piped detection, concurrent transcription+detection, optional Vulkan GPU engine.
- v1.1 parallel Vulkan: 47.8s for 6-min excerpt (69% faster than v1.0.1).
- Vulkan build: whisper.cpp v1.9.1 with ggml Vulkan backend, requires VS2022 + LunarG Vulkan SDK.
- Stage cache keys: fingerprint over actual inputs per stage.
- Model profiles: Fast (base.en 141MB), Balanced (small.en-q8_0 252MB), Accurate (small.en 465MB).

---

## Privacy and Data
- source: docs/PRIVACY_AND_DATA.md
- Local-first. No account, no phone home, no upload.
- Data under %USERPROFILE%\LecturePackData.
- Network: transcription and slide detection entirely offline. Context Repair optional (deterministic by default). Ollama talks only to localhost.
- Telemetry: none.
- v1.1 AI assistance: Ollama only, localhost, responses cached in job folder.

---

## Slide Detection Evaluation
- source: docs/SLIDE_DETECTION_EVALUATION.md
- Ground-truth evaluation framework. Deterministic construction schedule for synthetic fixture.
- Balanced preset on synthetic: P=1.000 R=1.000 F1=1.000.
- Real Egypt lecture calm section: P=1.000 R=1.000 F1=1.000 (4 slide states).
- Embedded video section: 13 candidates, all distinct scenes, no duplicates.
- Guards calibrated on physically-meaningful signatures, not per-frame magic numbers.

---

## Transcription and Context Repair
- source: docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md
- Three-layer transcript model: Layer 1 Raw (immutable), Layer 2 Normalized (deterministic, non-generative), Layer 3 Context Repair (optional, auditable, reversible).
- Raw transcript content_hash() proves immutability.
- Context Repair safety: rejects invalid JSON, unknown segment IDs, no-ops, extreme length changes, low similarity, invented proper nouns not in approved list.
- Whisper prompting is a weak decoder bias; Context Repair is more effective for specific names.

---

## Troubleshooting
- source: docs/TROUBLESHOOTING.md
- Common issues: app won't start (run --selftest), model missing, OneDrive placeholder stalls, too many/few slides (use presets/crop/mask), name errors (use Context Repair), re-export speed (cached), Ollama failures (non-crashing).
- v1.1: Vulkan engine in bin/vulkan/, stage caching, cancel with 300ms grace.

---

## Windows Portable Install
- source: docs/WINDOWS_PORTABLE_INSTALL.md
- Self-contained onedir package. No Python required.
- Bundled: LecturePack.exe + _internal/, whisper-cli.exe, whisper.dll, ggml*.dll, bin/ffmpeg.exe, bin/ffprobe.exe.
- Models NOT bundled. User downloads ggml-base.en.bin separately.
- Headless self-check: LecturePack.exe --selftest.
- Windows 10/11 x64, SSE4.2+ CPU required.

---

## Risk Register
- source: docs/RISK_REGISTER.md
- R1: Vulkan unstable on Vega 56 (Medium/Medium) - CPU fallback always available.
- R2: Slide detection thresholds don't generalize (High/Medium) - configurable presets + review screen.
- R3: CPU transcription too slow (Medium/High) - benchmark 4 models, user picks tradeoff.
- R4: PyInstaller breaks with full deps (Medium/High) - clean-machine test mandatory.
- R5: ReportLab PDF quality insufficient (Low-Medium/Medium) - dedicated template.
- R6-R10: FFmpeg compliance, model download failure, package size, temporal filter speed, long transcript layout.
