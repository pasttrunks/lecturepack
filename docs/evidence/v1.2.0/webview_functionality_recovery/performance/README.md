# §4 Performance profiling

## What was implemented
Per-stage timing instrumentation in the WebView adapter: `_on_stage_started` /
`_on_stage_finished` / `_on_stage_cached` record each stage's wall time, and
`_on_pipeline_completed` writes `<job>/performance.json` with per-stage durations,
whether each stage was cached, total wall time, and the realtime factor
(source_duration / wall). Every completed run is now measurable — no fabricated
numbers. The Transcribe stage's actual backend is already recorded in state.json
(`backend_used`, e.g. "Vulkan (Vulkan0)").

## Verified end-to-end
Ran `tests/fixtures/synthetic_lecture.mp4` through the real pipeline (temp data
dir + real toolchain, Vulkan) → pipeline completed and wrote `performance.json`
(see `sample_performance.json`). NOTE: that run's stages are `cached=true` (the
source had been processed before → content-addressed stage cache), so its 4.06 s /
16× numbers are cache-hit overhead, NOT a cold baseline. It confirms the profiler
output shape, not lecture-scale timings.
(A study-mode run of the same fixture fails at Extract Audio — the synthetic slide
video has no audio track; that's a fixture limitation, not a pipeline bug.)

## To capture a real cold baseline (baseline.json)
Process a real, not-yet-processed A/V lecture (e.g. a 60–75 min recording) with the
app or the adapter; `<job>/performance.json` is written automatically with cold
per-stage timings. Copy it here as `baseline.json`. Do not reuse an already-cached
source or the stages report as cached.
