# Troubleshooting

## The app won't start / closes immediately
- Run `LecturePack.exe --selftest` from PowerShell; it prints a PASS line and
  exits 0 if the bundle is intact.
- Make sure you extracted the **whole** ZIP (the `_internal` folder and the
  `*.dll` files must sit next to `LecturePack.exe`).
- SmartScreen may block the unsigned binary: "More info" → "Run anyway".

## "Whisper model missing" / transcription won't start
- A `.bin` model is not bundled. Download one (e.g. `ggml-base.en.bin`) and set it
  under **Whisper Model** on the setup screen. The Diagnostics bar must show the
  model as valid (green) before **Start Processing** is enabled.

## Processing hangs at "Extract Audio" or the video won't open
- If the video lives in **OneDrive** and shows as *online-only* (a cloud
  placeholder), Windows must download it first. Right-click → "Always keep on this
  device", or copy the file to a normal local folder, then try again. Accessing a
  not-yet-downloaded placeholder can stall FFmpeg.
- Confirm the path exists and the file is a supported type
  (`.mp4 .avi .mkv .mov .m4v .webm`).

## Too many / too few slides detected
- Use the **Sensitivity** preset: *Conservative* (fewest), *Balanced* (default),
  *Detailed* (most). *Detailed* catches progressive builds; *Conservative* is for
  clean single-topic decks.
- Set **ignore regions** over a webcam overlay or a live-caption band, and a
  **crop** around the slide area, on the setup screen.
- Embedded **video clips** inside a lecture produce scene-change keyframes — this
  is expected; reject them in review.

## Transcription got a name or term wrong
- This is inherent to `base.en`. Add the correct spelling under **Context &
  Names**, then either retranscribe (the term is added to the Whisper prompt) or
  open **Context Repair** to review a proposed correction. The Whisper prompt is a
  weak bias; Context Repair is usually more effective for specific names.
- Context Repair never replaces a name without your review, and never invents a
  name that is not on your approved list.

## Re-export seems slow
- Re-export (after changing slide keep/reject decisions) only regenerates the
  export files. It does **not** rerun audio extraction, Whisper, or slide
  detection — those cached artifacts are reused.

## A local LLM for Context Repair
- Context Repair works offline with no LLM (deterministic approved-name matching).
- To use an LLM, run LM Studio or Ollama locally and point the app at its
  OpenAI-compatible endpoint (e.g. `http://localhost:1234`). Only that endpoint
  receives transcript text.

## Where is my data?
- `%USERPROFILE%\LecturePackData`. See
  [PRIVACY_AND_DATA.md](PRIVACY_AND_DATA.md).


## v1.1 additions

**"Vulkan whisper-cli.exe not installed" / engine falls back to CPU**
The optional GPU engine lives in `bin/vulkan/`. It is used only when
`vulkan-1.dll` exists (GPU driver installed) and `ggml-vulkan.dll` is present.
The status bar always shows the actually loaded backend. Force CPU via
Settings → Default engine → CPU.

**Ollama features greyed out or failing**
Ollama is optional. Check Settings → AI (Ollama) → Refresh. If the server is
down you can keep working; Context Repair offers "Use deterministic repair
only". See docs/OLLAMA_SETUP.md. An Ollama failure never crashes the app —
use "Copy diagnostic details" when reporting issues.

**A stage reruns although the job was processed before**
v1.1 caches stages by their inputs (source file signature, crop/ignore
regions, preset/detector version, engine/model, glossary, VAD). Changing any
of those re-runs only the affected stages; the stage list marks untouched
stages as "Cached".

**Cancel takes a moment**
Cancel first asks processes to exit, then kills them (300 ms grace). After a
cancel no ffmpeg/whisper-cli processes should remain — if you ever see one in
Task Manager, please report it.
