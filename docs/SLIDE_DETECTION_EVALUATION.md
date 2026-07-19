# Slide Detection — Ground-Truth Evaluation

To make detector quality measurable (and to catch progressive-build
"candidate explosions" and motion/overlay false positives), Lecture Pack ships a
ground-truth evaluation framework.

## Design

- **Ground truth is not derived from detector output.** For the synthetic
  fixture it is derived from the deterministic construction schedule in
  `tests/fixtures/generate_test_video.py`. Real-media ground truth (m2, Egypt
  clips) must be human-labelled the same way — a list of meaningful slide states
  with acceptance windows, plus distractor windows.
- **Meaningful states** each have an acceptance window `[t_min, t_max]` in
  seconds. `t_max` is later than the change time to allow stable-frame capture
  after a transition.
- **Distractor windows** mark things that must *not* create separate candidates
  (mouse pointer, fade transitions, webcam overlays, captions, rapid ink
  strokes). False positives landing in these windows are reported by name.

## Evaluator

`lecturepack/services/detection_eval.py` is pure standard library. `evaluate`
does greedy one-to-one matching of candidate timestamps to ground-truth events
and reports TP / FP / FN, precision, recall, F1, candidate count vs. meaningful
state count, mean timestamp error, and per-distractor hit counts. A duplicate
capture of the same state correctly counts as a false positive.

`meets_targets` checks a result against the project acceptance criteria:
recall ≥ 0.95, precision ≥ 0.85, candidate count within 20% of the meaningful
state count, and zero missed major changes.

## Synthetic fixture ground truth

`tests/fixtures/ground_truth/synthetic_lecture.json` labels 8 meaningful states
across the 65-second fixture, including the **slide-2 reappearance at 0:55**
(which must be preserved as a separate timeline event, not de-duplicated), and 5
distractor windows.

## Running the evaluation

The evaluator's metric logic is verified by `tests/test_detection_eval.py`
(7 tests, no OpenCV required). Running the **real** detector over a video needs
the app's runtime dependencies (OpenCV, numpy, scikit-image), so it is run on
the developer/Windows machine:

```
python tests/scratch/run_detection_eval.py \
    --video tests/fixtures/synthetic_lecture.mp4 \
    --ground-truth tests/fixtures/ground_truth/synthetic_lecture.json \
    --preset balanced --json-out eval_synthetic_balanced.json
```

The harness runs `SlideDetectorWorker` synchronously, scores its candidates, and
prints matched/missed/spurious events, distractor hits, and target pass/fail.
Iterate on short clips first; run the full 71-minute lecture only once after the
short-clip evaluation passes, reusing cached audio/transcript.

## v1.0 results (native Windows, real detector, no ignore masks)

Baseline (pre-v1.0) vs. after adding the two preset-gated precision guards
(overlay caption/subtitle-band rejection; major-change future-persistence to
reject fade/dissolve transitions):

| Preset | Baseline | v1.0 | Targets |
|--------|----------|------|---------|
| Balanced (default) | P=0.667 R=0.750 F1=0.706 | **P=1.000 R=1.000 F1=1.000** | ✅ all pass |
| Detailed | P=0.727 R=1.000 F1=0.842 | P=0.889 R=1.000 F1=0.941 | ✅ all pass |
| Conservative | P=0.833 R=0.625 F1=0.714 | P=0.833 R=0.625 F1=0.714 | ✗ low-sensitivity by design |

### How the guards were calibrated (not overfit)
The guards trigger on measured, physically-meaningful signatures rather than
per-frame magic numbers:

- **Fade rejection.** The synthetic fade (30–33 s) momentarily "stabilises"
  mid-blend and was captured as a spurious `major_change` at 31.5 s. Its
  future-SSIM (captured frame vs. the frame 1 s later) was **0.778**, while every
  real slide measured **≥ 0.975** (the whiteboard slide, which keeps gaining ink,
  was the lowest real value at 0.975). Threshold `major_persistence_ssim = 0.90`
  sits cleanly in that gap.
- **Caption/overlay band.** Live captions live in the bottom ~10 % of the frame
  (rows 430–480 of 480). Both genuine progressive builds add content in the
  mid-frame (Topic C at y≈290; whiteboard ink at y≈200–250), so rejecting changes
  whose contours are *entirely* within the bottom 15 % removes the caption and
  webcam-noise false positives without touching real builds.

Removing the balanced fade false-positive also recovered the two slides the
baseline had missed (`s5_code`, `s7_final`): the spurious mid-fade capture was
consuming the `min_time_between_slides` budget and pushing the real captures
outside their acceptance windows.

These results are locked in as regression tests in
`tests/test_detection_targets.py` (balanced and detailed must meet all targets;
the fade and caption bands must produce no candidates).

## v1.0.1 results on REAL lecture material (Egypt lecture)

The synthetic fixture is necessary but not sufficient. Two excerpts of the real
Egypt lecture were evaluated with **human/agent-labeled ground truth**, produced
by visually inspecting dense (every-4s / every-6s) contact sheets of each excerpt
*independently of detector output*. Evidence: `docs/evidence/v1.0.1/detector/`.

### Calm lecture-slide section (5:00–7:00), balanced preset
Ground truth (4 slide states): quote → EGYPTOLOGY title → blue discipline box →
bullets. Ground-truth file: `tests/fixtures/ground_truth/egypt_excerptB_0500_0700.json`.

```
P=1.000 R=1.000 F1=1.000 | TP=4 FP=0 FN=0 | candidates=4 vs states=4 | ts_err=1.75s
```

Meets every balanced-mode acceptance target on real material: no missed major
slide changes, recall ≥ 0.90, precision ≥ 0.80, no fade/caption/pointer clusters.

### Embedded video section (29:18–35:21), balanced preset
This excerpt is an **embedded educational video** (animations + live footage),
not slides. The detector produced **13 candidates**, and visual classification of
every candidate frame confirmed **13 distinct scenes, 0 duplicates, 0
transition/fade/caption artifacts** — roughly one keyframe per 28 s of continuous
video. Honest characterisation: the detector does not explode on video content,
but video keyframes are not "slides"; reject them in review or crop to the slide
region. This is a limitation of applying slide detection to embedded video, not a
regression.

The perfect synthetic result alone would not justify these claims — the calm real
excerpt is the material evidence that balanced mode meets the targets in practice.
