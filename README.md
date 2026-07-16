# Lecture Pack

Turn a lecture recording into a reviewable **study pack**: detected slides, an
aligned transcript with an auditable layered correction workflow, and exports in
many formats — all processed **locally on your Windows machine**. No cloud, no
account, no upload.

> Version 1.1.0 (`v1.1.0-ui-speed-ollama`). Windows x64. CPU always; optional
> Vulkan GPU transcription (AMD/cross-vendor) and optional local-AI assistance
> via Ollama.

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

## The v1.1 interface

A navigation rail switches between six pages — **Home** (jobs), **Process**
(settings + stage-by-stage progress with elapsed/ETA and a logs drawer),
**Review** (slide timeline · large preview · transcript for the selection),
**Transcript**, **Exports** and **Settings**. Light/dark themes; window
layout, splitters and view modes persist.

**Review**: selected slides are unmistakable (thick accent outline,
contrasting background, checkmark badge, focus ring, auto scroll-into-view,
live count). Click / Ctrl-click / Shift-click / Ctrl+A select; `Delete`
rejects (never deletes files); `R` restores; `Ctrl+Z` undoes; right-click for
Keep / Reject / Restore / Export selected / Copy image / Open source
timestamp.

**Transcript workspace** (independent of slide review):

- *Full Transcript*: readable document, section headings, optional
  timestamps, search highlighting, timestamp links that select the matching
  slide, one-click **Copy full transcript**.
- *Segments*: grid with start/end/duration/confidence/status; edit the active
  segment in its own editor; **split at cursor, merge, reset, undo/redo**;
  sort/filter freely — exports stay chronological; raw Whisper output stays
  immutable.
- *Sections*: conservative topic sections; rename anything; AI-suggested
  headings are explicitly marked “(AI)”.
- *Context Repair*: reviewable correction proposals (see below).
- Copy as `txt / md / json / jsonl / csv / srt / vtt` with a timestamps
  toggle (`Ctrl+C`, `Ctrl+F`, `F3`/`Shift+F3`, `Ctrl+S`, `Ctrl+Z`/`Ctrl+Y`).

## Speed (v1.1)

Transcription and slide detection run **concurrently**; slide detection uses
a two-pass decode (one sequential downscaled FFmpeg analysis stream + full-res
capture only for accepted slides); an optional **whisper.cpp Vulkan engine**
uses the GPU when measured faster. On the reference PC the 6-minute test
excerpt dropped from **156 s (v1.0.1) to 48 s (−69 %)**. Details:
[docs/PERFORMANCE_AND_BACKENDS.md](docs/PERFORMANCE_AND_BACKENDS.md).

## Local AI (optional, via Ollama)

With a locally installed [Ollama](https://ollama.com), LecturePack can propose
transcript corrections and section headings (recommended model:
`qwen3:1.7b`). Proposals are schema-validated, cached, generated off the GUI
thread, and **never auto-accepted**; every failure mode is recoverable inline.
Without Ollama, the deterministic offline provider still works. Setup:
[docs/OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md).

## Install (portable, no Python needed)

1. Download `LecturePack-portable-1.1.0.zip` from the release.
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
