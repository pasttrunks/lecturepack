# v1.0.1 Real-Media Verification Evidence

Artifacts captured on the native Windows machine for
`v1.0.1-real-media-verified`.

## Screenshots (`screenshots/`)
- `01_setup_product_modes.png` — setup view with the **Output** product-mode
  selector (Study Pack / Transcript Only / Slides Only).
- `02_review_transcript_copy_search.png` — review view: slide timeline + multi-
  select + bulk actions, transcript search, **Copy as** format selector (Copy
  Slide / Topic / Selected / Full), and the **Context Repair…** button.
- `03_context_repair_workspace.png` — Context Repair on a real Egypt transcript:
  Context & Names list, proposals (`dolarite→dolerite` accepted, `Mark Lehner`
  rejected), raw/normalized/proposed columns, reason + confidence, one accepted
  (green) and one rejected (red).
- `04_context_repair_proper_names.png` — the "proper names" filter.

## Detector (`detector/`)
- `egyptB_candidates.png`, `egyptB_dense.png` — calm section (5:00–7:00): the
  dense sheet is the independent ground-truth basis; the candidate sheet shows the
  4 detected slides.
- `egyptB_metrics.json` — **P=1.00 R=1.00 F1=1.00**, all balanced targets met.
- `egyptA_candidates.png` — embedded video section (29:18–35:21): 13 distinct
  scene keyframes, no fade/caption/pointer clusters.
- `egyptA_summary.json`, `egyptB_summary.json` — detector run summaries.

## Transcription (`transcription/` + `transcription_comparison.md`)
- Three base.en transcripts (no context / generic prompt / targeted prompt) and a
  comparison showing the `--prompt` did not fix the proper-name/technical errors,
  which post-hoc Context Repair then proposed for review.

## Packaged pipeline
The full packaged-EXE acceptance reports (m2 short video and the full Egypt
lecture) are produced by `LecturePack.exe --run-acceptance` and summarized in
`CHANGELOG.md` / `RELEASE_NOTES.md`.

## Reproduce
- Detector: `python tests/scratch/egypt_detector_eval.py <video> <outdir> balanced 4 <offset>`
- Metrics: `lecturepack.services.detection_eval.evaluate(...)` vs. the ground-truth JSON
- Screenshots: `python tests/scratch/gen_screenshots.py` (offscreen)
- Packaged: `LecturePack.exe --run-acceptance <video> <model> <data_dir> <out.json> [--names ...] [--mode ...]`

## Honesty notes
- "Ground truth" for the detector was labeled by visually inspecting contact-sheet
  frames, not by an external annotator.
- The transcription "reference" lines rely on domain knowledge (Mark Lehner is a
  real Egyptologist; dolerite is the correct rock), not on listening to the audio.
- small.en was not evaluated (not present locally; not authorized to download).
- No local LLM was available, so Context Repair used the deterministic offline
  provider; the LLM path is supported but was not exercised end-to-end here.
