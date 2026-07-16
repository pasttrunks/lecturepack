# Lecture Pack

Turn a lecture recording into a reviewable **study pack**: detected slides, an
aligned transcript with an auditable layered correction workflow, and exports in
many formats — all processed **locally on your Windows machine**. No cloud, no
account, no upload.

> Version 1.0.1 (`v1.0.1-real-media-verified`). Windows x64, CPU-only.

---

## What it does

1. **Inspect** the video (ffprobe metadata).
2. **Extract audio** to 16 kHz mono (bundled FFmpeg).
3. **Transcribe** with whisper.cpp (bundled `whisper-cli.exe` + a `ggml` model).
4. **Detect slides** with an adaptive computer-vision detector (rolling motion
   baseline, two-path major/progressive detection, fade & caption/overlay
   rejection).
5. **Align** transcript segments to slide intervals.
6. **Review** slides (keep/reject) and transcript (edit, Context Repair).
7. **Export** slides PDF, HTML study pack, and transcripts in
   `txt / md / json / jsonl / csv / srt / vtt`.

### Product modes
A single **Output** selector on the setup screen chooses what to produce:

| Mode | Runs | Produces |
|------|------|----------|
| **Study Pack** (default) | audio → transcribe → detect → align | slides PDF, HTML study pack, all transcript formats |
| **Transcript Only** | audio → transcribe | transcript formats (no slide detection) |
| **Slides Only** | detect slides | slides PDF (no audio / whisper) |

## The layered transcript

Lecture Pack never silently overwrites what Whisper produced. A transcript is
kept as four separate, auditable layers:

1. **Raw** — exact whisper.cpp output, immutable (guarded by a SHA-256 hash).
2. **Normalized** — deterministic, non-generative cleanup (whitespace,
   hallucination-loop collapse, duplicate merge, paragraph grouping). Never
   changes a word, name, number, or fact.
3. **Context proposals** — optional, reversible corrections of *likely
   mishearings*. Either from a local LLM (LM Studio / Ollama, OpenAI-compatible)
   or, with no LLM configured, from **deterministic approved-name matching** that
   can only ever propose names you approved — it cannot invent one.
4. **User-approved corrections** — only the corrections you accept, applied to a
   fresh projection. Rejecting a correction is a pure no-op.

See [docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md](docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md).

### Context & Names
Enter proper nouns and terms (e.g. *Mark Lehner*, *dolerite*, *Giza*). They feed
both the Whisper initial prompt (on retranscription) and the Context Repair
proposals. Uncertain names are **never** replaced without your review.

## Transcript workspace

- Semantic sections (topic heading, time range, associated slide).
- Search across the transcript (`Ctrl+F`, `F3` / `Shift+F3`).
- Copy the current slide, current topic, selected slides, or the full
  transcript, in any export format, with a timestamps toggle (`Ctrl+C`).
- Save corrections (`Ctrl+S`). Multiple selections copy in chronological order.

## Install (portable, no Python needed)

1. Download `LecturePack-portable-1.0.1.zip` from the release.
2. Verify the checksum against `SHA256SUMS.txt`.
3. Extract anywhere (a path with spaces is fine).
4. Run `LecturePack.exe`.

A Whisper model (`.bin`) is **not** bundled; point the app at one (e.g.
`ggml-base.en.bin`) on first run. See
[docs/WINDOWS_PORTABLE_INSTALL.md](docs/WINDOWS_PORTABLE_INSTALL.md).

## Privacy

All processing is local. Job data lives under `~/LecturePackData`. The optional
Context Repair LLM only ever talks to an endpoint **you** configure (default:
none). See [docs/PRIVACY_AND_DATA.md](docs/PRIVACY_AND_DATA.md).

## Limitations (honest)

- Automatic transcription is **not perfect**. `base.en` mishears proper nouns and
  technical terms; the Whisper `--prompt` only weakly biases these. Context
  Repair helps but is a *proposal* you review — it is not ground truth.
- The detector is excellent on lecture slides (perfect on the tested real calm
  section) but embedded **video content** yields scene-change keyframes, not
  "slides"; the low-sensitivity *Conservative* preset intentionally under-captures.
- Unsigned binary — SmartScreen may warn on first launch.

## Development

```
.venv\Scripts\python.exe -m pytest        # full test suite
python build_release.py                    # build the portable package
```

See [CHANGELOG.md](CHANGELOG.md) and [docs/](docs/).
