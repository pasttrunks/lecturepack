# LecturePack v1.0.0 (Unified) - Release Notes

**Release Date:** July 2026
**Tag:** `v1.0.0-unified`
**Previous Release:** `v0.4.0-adaptive-detection`

---

## What's New in v1.0.0

### Layered, auditable transcript model
A three-layer transcript pipeline replaces ad-hoc raw parsing
(`lecturepack/services/transcript_service.py`):

- **Layer 1 — Raw (immutable):** exact whisper.cpp output with per-token
  confidence and a SHA-256 content hash that proves the raw layer is never
  modified by later stages.
- **Layer 2 — Normalized (deterministic, non-generative):** whitespace/punctuation
  cleanup, hallucination-loop collapse, exact-duplicate merge and paragraph
  grouping. Never changes a word, name, number, or fact.
- **Layer 3 — Context Repair (optional, reversible):** LLM-assisted correction of
  *likely mishearings only*, via a local OpenAI-compatible endpoint (LM Studio /
  Ollama). Strict JSON-schema validation, invented-name guardrails, and
  per-correction accept/reject with the original always recoverable.

The normalized layer now runs inside the pipeline: after transcription the
controller writes `transcript/normalized.json` and `transcript/context_candidates.json`,
and exports include a paragraph-grouped `transcript.normalized.txt`.

### Product modes
A single **Output** selector on the setup screen chooses what to produce:

| Mode | Stages run | Exports |
|------|-----------|---------|
| **Study Pack** (default) | audio → transcribe → detect → align | slides.pdf, transcript.*, study-pack.html |
| **Transcript Only** | audio → transcribe | transcript.txt / .srt / .json / .normalized.txt |
| **Slides Only** | detect slides | slides.pdf |

Stage gating lives in `JobController`; export selection in `ExportService`.

### Slide-detector precision guards
Two general, preset-gated guards added to `cv_engine.py`:

- **Overlay-band rejection** — progressive-build changes confined to the bottom
  caption/subtitle band are ignored (live captions, burnt-in subtitles).
- **Major-change persistence** — a "major change" whose captured frame is not
  still present ~1 s later is rejected, so fade/dissolve transitions no longer
  produce a spurious mid-blend slide.

Measured on the ground-truth fixture (`tests/fixtures/synthetic_lecture.mp4`,
no ignore masks — the algorithm must reject the mouse pointer, fade, webcam
noise and captions on its own):

| Preset | Before | After | Meets targets* |
|--------|--------|-------|----------------|
| **Balanced** (default) | P=0.67 R=0.75 F1=0.71 | **P=1.00 R=1.00 F1=1.00** | ✅ |
| Detailed | P=0.73 R=1.00 F1=0.84 | P=0.89 R=1.00 F1=0.94 | ✅ |
| Conservative | P=0.83 R=0.63 | P=0.83 R=0.63 | ✗ (low-sensitivity by design) |

\* Targets: recall ≥ 0.95, precision ≥ 0.85, candidate count within 20% of the
true slide count, zero missed slides. Locked in as regression tests
(`tests/test_detection_targets.py`).

### Version consolidation
The package version, `constants.APP_VERSION`, the window title, and new-job
manifests all now report **1.0.0** (previously 0.2.1 / 0.4.0 / 0.1.0 disagreed).

---

## Verified in this build

- **Test suite:** 53 passed (Windows, Python 3.12.3, PySide6 6.11.1). Includes
  the real slide detector run against the fixture and the full controller
  pipeline (mock ffmpeg/whisper) for each product mode.
- **Real whisper.cpp transcription:** bundled `whisper-cli.exe` + `ggml-base.en`
  transcribed a 42 s 16 kHz WAV (exit 0), producing full token-level JSON that
  parses through all three transcript layers with the raw content hash unchanged.
- **Slide detection:** default preset scores P=1.00 / R=1.00 on the ground-truth
  fixture (see table above).

---

## Known Limitations

- **Whisper accuracy** — the `base.en` model may mishear proper nouns and
  technical terms (e.g. "Abu Simbel", "Tutankhamun"). Use a larger model or the
  optional Context Repair layer with an approved-names glossary. This is inherent
  to the model, not a bug.
- **Conservative preset** — intentionally low-sensitivity; it under-captures
  fast slide changes and does not meet the ground-truth targets. Use Balanced
  (default) or Detailed for full coverage.
- **Context Repair** — requires a locally running OpenAI-compatible endpoint; the
  app is fully functional with none configured.
- **Platform** — Windows x64, CPU-only Whisper (SSE4.2+). Unsigned binary;
  SmartScreen may warn on first launch.

---

## Build Information

- **Python:** 3.12.3
- **PyInstaller:** 6.21.0
- **PySide6:** 6.11.1
- **OpenCV:** opencv-python-headless 5.0.0 · **numpy:** 2.5.1
- **FFmpeg:** bundled (GPL build) · **whisper.cpp:** CPU-only, 9 ggml-cpu variants
- **Platform:** Windows 10/11 x64

---

## License

See `THIRD_PARTY_NOTICES.txt` for complete third-party license information. The
FFmpeg binary is compiled with GPL-licensed code (libx264/libx265); under the
GPL, source availability must be offered if this package is redistributed.
