# §3 Vulkan validation + backend truthfulness

## Result on this machine: Vulkan WORKS
`detection_real_machine.json` (read-only, from the live config + engine registry):
both CPU and Vulkan whisper-cli binaries are present, Vulkan is available, and the
`auto`/`vulkan` selection resolves to **Vulkan** ("benchmarked faster"). The real
Mesopotamia job's `state.json` confirms transcription ran with
`backend_used: "Vulkan (Vulkan0)"` — so the compute path is genuinely GPU, not a
silent CPU fallback.

## What was added
- `LecturePackAdapter.validate_vulkan()` — uses `EngineRegistry.detect_engines()`
  + `resolve()` to emit `vulkan_status` with an honest state:
  `loaded` (available + selected) / `available` (present but another backend
  selected) / `unavailable` (+ concrete reason, e.g. "No Vulkan runtime") /
  `error`. Includes the resolved backend + recorded benchmark flag. Emitted on
  UI ready and whenever the compute engine is changed.
- Settings UI: a **Validate** button + a `#vulkan-status` line under the
  CPU/Vulkan toggle showing the current backend truthfully; the footer already
  shows the actual loaded backend from the job (`backend_used`).
- Selecting Vulkan persists to the engine config and is applied to the job's
  whisper settings at processing start (from earlier P0.3 wiring), so a Vulkan
  click never silently stays on CPU.

## Tests
`tests/test_webview_vulkan.py` (3, registry monkeypatched → machine-independent):
available+selected → "loaded"; available+CPU-selected → "available"; unavailable →
reason surfaced.

## Live timing benchmark (CPU vs Vulkan wall-time) — user-runnable
A recorded benchmark already set `vulkan_benchmark_ok: true`. A fresh side-by-side
wall-time comparison requires processing a clip under each engine (writes a job);
that is a user-initiated run and is not fabricated here.
