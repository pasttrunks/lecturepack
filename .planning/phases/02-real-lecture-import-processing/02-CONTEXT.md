# Phase 2: Real Lecture Import & Processing - Context

**Gathered:** 2026-08-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the normal lecture import and processing pipeline so it works the way the demo
does. Local videos and URL imports must reliably use the bundled transcription runtime,
jobs must persist visibly through their full lifecycle, and all three output modes
(Transcript Only, Slides Only, Study Pack) must complete successfully.

The demo already works — the gap is between the demo path and the normal import path.
This phase closes that gap without redesigning the job system or the demo.

</domain>

<decisions>
## Implementation Decisions

### Runtime Resolution (D-01 through D-04)

- **D-01:** Bundled runtime paths (whisper-cli.exe, ggml-base.en.bin, ffmpeg, ffprobe)
  must reach normal processing automatically on a clean install. Claude picks the
  simplest approach — likely auto-populating ConfigManager on boot, since Settings is
  already the source of truth for the normal path.

- **D-02:** User Settings wins over bundled defaults. If the user explicitly sets a
  different whisper path or model in Settings, that override is respected. Bundled paths
  are defaults, not mandates.

- **D-03:** The demo keeps its separate isolation (own JobController, own ConfigManager,
  hardcoded engine/model). Do not merge the demo into the normal processing path. Unify
  only the runtime path resolution so both demo and normal find the same binaries —
  the demo's _bundled_demo_model_path() and the normal path's config reads should
  ultimately resolve to the same physical files.

- **D-04:** Claude decides whether the resolver handles engine selection (CPU vs Vulkan)
  or just paths, and whether yt-dlp absence hides the Paste Link button or shows an
  error on click. Pick whatever the existing code already does or whatever is simplest.

### Job Lifecycle Visibility (D-05 through D-07)

- **D-05:** Reproduce the specific bugs and fix what's broken. Do not redesign the job
  system. The persistence machinery (state.json, queue.json, lifecycle states) exists —
  find why the UI loses track of jobs and fix the wiring.

- **D-06:** Failed jobs stay visible with their error message until the user explicitly
  dismisses or retries them. No auto-clearing on timeout.

- **D-07:** After importing a lecture, it must remain selected in Source. After creating
  a job, it must be visible in Recent/Active. The top-left indicator must reflect the
  actual current job and open its real timeline.

### Pre-Processing Settings Timing (D-08)

- **D-08:** Output mode and slide sensitivity are shown during processing but visually
  locked (greyed out, disabled, or with a lock indicator) once processing starts. The
  user can see what was chosen without being misled into thinking they can change it
  mid-run. If code review reveals any setting that genuinely supports live adjustment,
  that specific setting alone stays interactive.

### Paste Link / yt-dlp (D-09)

- **D-09:** Reconnect existing functionality. The backend code exists
  (`import_media_url` in engine_adapter.py, `MediaFetcher` using yt-dlp). Just make it
  work for one supported URL (YouTube via yt-dlp) with a clear error on failure. No
  playlist support, no format selection, no new UI design.

### Reproduction Strategy (D-10)

- **D-10:** Build fresh from current code (which includes Phase 1 + 1.1 fixes:
  corrected requirements, pruning, setup checklist, etc.) before reproducing. Use the
  bundled polar bears demo video (10 seconds, 4 confirmed slides) as the test file for
  normal import — import it through the regular path, not the demo path.

### Claude's Discretion

Claude has flexibility on:
- The specific mechanism for auto-populating bundled paths (boot-time write to config
  vs shared resolver function vs other approach) — pick the simplest given existing code
- Whether the resolver also handles engine selection or just paths
- Whether missing yt-dlp hides the Paste Link button or shows an error on click

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Import and processing pipeline
- `app/desktop/engine_adapter.py` — The central adapter: `import_video()` (line 1745), `import_media_url()` (line 1657), `start_processing()` (line 1771), `start_demo_job()` (line 1391), `_bundled_demo_model_path()` (line 1374), `_kick_poster()` (line 1727)
- `app/desktop/bridge.py` — Qt-to-JS bridge: `import_video`, `probe_media_url`, `import_media_url`, `start_processing`, `get_bootstrap`
- `app/ui/app.js` — WebEngine UI: source selection, job display, processing view, settings display

### Runtime and configuration
- `lecturepack/infrastructure/runtime_inventory.py` — Canonical runtime inventory, `PRUNABLE_QT_COMPONENTS`, `REQUIRED_QT_WEBENGINE_DEPS`
- `lecturepack/infrastructure/config_manager.py` — `ConfigManager`: settings persistence, `whisper_model`, `whisper_exe`, `resource_dir`
- `lecturepack/infrastructure/transcription_engines.py` — `EngineRegistry`: CPU/Vulkan selection, `_probe_backend`

### Job system
- `lecturepack/services/job_queue.py` — `JobQueue`: active job, FIFO queue, schedules, `queue.json`
- `lecturepack/models/job_lifecycle.py` — Lifecycle states: NEW, QUEUED, RUNNING, PAUSED, INTERRUPTED, FAILED, COMPLETE
- `app/desktop/assets.py` — `AssetResolver`: thumbnail generation, `lpasset://` URL scheme

### Constraints and prior decisions
- `docs/DECISIONS.md` — AD-18 (ASCII native-staging boundary), AD-19 (Ed25519 signed-manifest repair)
- `.planning/phases/01-clean-device-footprint-first-launch/01-CONTEXT.md` — Phase 1 decisions D-01 through D-24
- `BUG_LIST.md` — Cumulative bug record

### Media fetch
- `lecturepack/services/media_fetch.py` — `MediaFetcher`: yt-dlp download wrapper

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_bundled_demo_model_path()` in engine_adapter.py: searches three candidate paths for the bundled model. Can inform the normal resolver.
- `_kick_poster(job)` + `AssetResolver.make_poster_now()`: thumbnail generation already exists and fires on import.
- `MediaFetcher` in media_fetch.py: yt-dlp wrapper already built.
- `JobQueue` in job_queue.py: full queue management with persistence already exists.
- `_reconcile_jobs_on_startup()` in engine_adapter.py: stale-state cleanup on boot.

### Established Patterns
- Demo uses its own controller/config — this isolation is preserved (D-03).
- Jobs persist as `state.json` in `<data_dir>/jobs/<id>/`.
- Bridge signals flow from Python to JS via `@Slot` methods emitting events.
- `canonical_inventory()` and `resolve_inventory()` already validate the full runtime.

### Integration Points
- `LecturePackAdapter.__init__` or `Backend.__init__` — where auto-population of bundled paths would go.
- `start_processing()` — where runtime config is read and validated before launching the pipeline.
- `app.js` source/job/processing views — where UI state bugs manifest.
- First-run checklist (Phase 1) — already proves runtime is healthy; could inform path resolution.

</code_context>

<specifics>
## Specific Ideas

- Test with the bundled polar bears demo video (10s, 4 slides) imported through the normal path, not the demo button.
- The first-run checklist already validates the runtime — its results could seed the initial config values.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 2-Real Lecture Import & Processing*
*Context gathered: 2026-08-01*
