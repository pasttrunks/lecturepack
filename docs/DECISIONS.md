# Lecture Pack -- Decision Log

Record of major technical decisions. Newest entries at the top.

## AD-53: Guided-demo output and its recovery UI are exact packaged contracts

**Date:** 2026-08-12

**Status:** Implemented and packaged-accepted

**Context:** The guided tour worked from source and its five navigation steps
passed the packaged acceptance gate, but the Windows package contained only the
demo video and thumbnail. The renderer loads the prebuilt tour from
`resources/assets/demo`; its data module, hero, and slide images instead lived
under `app/assets/demo` and were never copied there. Every chapter silently
fell back to “preview unavailable,” yet the gate remained green because it
only tested navigation. Subsequent visual inspection also found three recovery
states that functional checks missed: the completed-tour fallback action could
sit below a 1024x720 viewport, quiz correctness was conveyed only by color, and
demo cleanup could leave `Idle` beside a stale `Detecting slides` footer label.

**Decision:** Treat the guided-demo output as release payload, not optional
decoration:

- The Electron packager copies the curated data module, hero, slides,
  thumbnail, and provenance file to the renderer's exact
  `resources/assets/demo` path. The separately packaged canonical demo video
  is excluded from that copy.
- Release validation fails before artifact publication if any required guided
  asset is absent. Packaged acceptance requires the real data object, decoded
  hero/slides (`naturalWidth > 0`), transcript rows, flashcard copy, quiz
  options, and zero degraded fallbacks.
- The responsive gate enters the tour through Settings' shipped Replay action,
  never through a private renderer function. It covers Demo, Home, Review, and
  Study at all three supported compact sizes.
- A zero-job demo action must be visible at 1024x720 both on first run and
  after tour completion. The completed-tour empty card switches to a compact
  horizontal layout at short desktop heights.
- Demo quiz choices expose pressed/correctness state and a textual live result.
  Returning to an empty workspace restores the last authoritative runtime
  backend label, clearing any stale processing stage.

**Alternatives considered:**

- Move the source assets into `electron-spike/assets`: rejected because the
  curated demo belongs to the app and that would duplicate its ownership.
- Keep graceful fallback as sufficient release behavior: rejected because a
  fallback is useful for corruption recovery but is not the promised demo.
- Call renderer internals from CDP to simplify the responsive gate: rejected
  because those functions intentionally live inside an IIFE and users cannot
  invoke them.
- Make the empty state shorter by dropping explanatory content: rejected; the
  compact grid keeps the same information and moves the action into view.

**Acceptance record:** A rebuilt packaged candidate passed its native runtime
self-test and the expanded stable gate with zero failures, 26 screenshots,
complete prebuilt content (two decoded slides, two transcript rows, four quiz
options, and no fallback), both 1024x720 zero-job action states, all 12
responsive screen/size cases, cleanup finality, and zero orphan processes.

## AD-52: Clean-machine acceptance uses a persisted job and always unwinds its install

**Date:** 2026-08-12

**Status:** Implemented and installer/portable-accepted

**Context:** The clean-machine validator installed the exact 2.0.1 artifact and
then imported its test media with `bundled_demo=true`. That flag correctly
creates a temporary guided-demo session. Automatic export completes the demo
and removes its job, so the validator's later transcript request addressed a
job that was intentionally gone. The resulting assertion failure also exposed
that an early validator exit could leave its disposable per-user installation,
uninstall record, and Send To shortcut behind.

**Decision:** Keep lifecycle ownership explicit between release gates. The
packaged stable gate owns the guided-demo contract, including automatic final
cleanup. Clean-machine acceptance imports the installed media as a normal job
because it must inspect persisted transcript and export state after completion.
The acceptance entry point wraps every run in a `finally` cleanup that invokes
the exact test installation's uninstaller; the normal success path uses the
same checked helper.

**Alternatives considered:**

- Disable guided-demo cleanup during validation: rejected because it would
  prove behavior users never receive and weaken the cleanup contract.
- Race transcript inspection before automatic cleanup: rejected because the
  result would depend on scheduling and would not validate normal persistence.
- Leave failed installs for manual diagnosis: rejected because release tests
  must not pollute the user's registry, Send To menu, or installed programs.

**Rationale:** A validator should test the intended lifecycle rather than rely
on stale implementation timing, and failure evidence must not alter the host
machine after the run ends.

**Acceptance record:** The exact installer subsequently passed packaged
self-test, a real normal lecture, Study data, all 13 exports, host launch and
restore, clean sidecar exit, zero orphan processes, and uninstall exit 0. The
install directory, uninstall registry entry, and Send To shortcut were absent
afterward. A disposable extraction of the exact portable ZIP also passed all
nine fault-injection scenarios with zero remaining processes. A separate run
then forced an immediate active-job completion timeout: it exited nonzero as
intended, killed the exact spawned sidecar tree, uninstalled, and again left no
process, install directory, uninstall record, or Send To shortcut.

## AD-51: Release visual evidence must prove unobscured minimum-width layouts

**Date:** 2026-08-12

**Status:** Implemented and packaged-accepted

**Context:** The stable packaged gate exercised the real Electron host and
captured screenshots, but its programmatic canonical import left the real batch
setup dialog open. The functional assertions passed while that dialog obscured
Review and Study in several screenshots. Once the dialog was closed, a new
geometry probe found a separate product defect at the supported 640x480 window
minimum: Review's timeline header was 544 pixels wide inside a 400-pixel main
pane. The application's intentional `overflow-x:hidden` made the legend and job
switcher unreachable without producing a page scrollbar.

**Decision:** Treat unobscured screenshots and renderer geometry as one release
contract:

- The packaged harness closes the import dialog through its real visible Close
  control before starting the explicit auto-export job, and records a failed
  check if an unexpected modal remains over Process, Review, Transcript, or
  Study.
- The gate resizes the real BrowserWindow to 640x480, 820x600, and 1024x720.
  At each size it visits Home, Review, and Study; captures a screenshot; and
  rejects document, header, main, active-screen, or footer horizontal overflow,
  clipped header controls, clipped screen controls, and unexpected dialogs.
- Review's timeline header has named layout hooks. At 700 pixels and below its
  metadata and legend wrap, its spacer is removed, and the shared lecture
  switcher receives a full final row with an ellipsized name.
- The Windows package contains the repository MIT `LICENSE` as an explicit
  release resource and release hardening tests require it.

**Alternatives considered:**

- Rely on screenshots alone: rejected because clipped content can sit outside
  the capture and an opaque modal can still look like a valid intentional UI.
- Rely on `scrollWidth` alone: rejected because an overlay can obscure an
  otherwise perfect layout and still produce equal client/scroll widths.
- Raise Electron's minimum width: rejected because 640x480 is already a
  supported product contract and the header, Home, and Study work at that size.
- Hide the Review legend or lecture switcher: rejected because both retain
  useful state/navigation value and fit when the header is allowed to wrap.

**Rationale:** Release evidence now measures what the student can actually see
and reach, not merely whether background operations completed. The minimum
window remains supported without silently clipping controls, while larger
layouts are unchanged.

**Acceptance record:** The rebuilt 2.0.1 packaged candidate passed all 9 layout
cases with exact main/active scroll equality, including 400/400 pixels for
Review at 640x480. The full stable gate passed with 21 screenshots and no
failures. The resulting unsigned artifacts are recorded in the current release
handoff; signing remains an external credential gate.

## AD-50: Asynchronous Study work uses per-job cancellation epochs

**Date:** 2026-08-12

**Status:** Implemented and packaged-accepted

**Context:** Guided-demo cleanup could delete its temporary job while the
background Study worker was still awaiting a provider. A late callback then
persisted `study-content-v2.json` and recreated the deleted job directory. The
same lifecycle risk applied to normal deletion, bulk deletion, reset, partial
regeneration, and interactive Ask/Teach/grade work. Deleting the current files
was therefore not a final state.

**Decision:** The sidecar owns a monotonically increasing Study epoch for each
job. Starting work captures the current epoch; demo cleanup, single/bulk
deletion, and reset advance it. Full generation and partial regeneration check
the cancellation predicate before provider work, after provider work, and
before persistence. Interactive Study requests are tracked by job so their late
completion can be discarded too. `AIStudyService` treats cancellation as a
terminal non-error and does not persist a provider failure after the job has
been cancelled.

If a cancelled callback still creates a late directory, cleanup may remove only
the exact safe `<data>/jobs/<job-id>` path and only when it is manifest-less. A
directory containing a valid job manifest is never purged by this tombstone
path.

**Alternatives considered:**

- Join every worker before deleting: rejected because provider/network calls
  can outlive a UI action and would make deletion or reset block for minutes.
- Use one global cancellation flag: rejected because deleting one lecture must
  not cancel or invalidate Study work for another lecture.
- Ignore late completion only in the renderer: rejected because the stale
  worker would still recreate durable files and reappear after restart.
- Delete any matching directory after a delay: rejected because a recreated
  valid job with the same id must not be destroyed.

**Rationale:** Epochs make deletion final without blocking the UI or depending
on provider cancellation support. The persistence service and sidecar agree on
the same cancellation boundary, and the manifest guard confines cleanup to the
specific late-write tombstone case.

**Acceptance record:** Regression tests force a delayed Study write after demo
cleanup and a delayed provider failure after cancellation; neither can
resurrect or mutate the deleted job. The stable packaged gate also waits until a
normal Smart Study reaches ready before asserting that guided-demo cleanup is
still final, well beyond the original resurrection window.

## AD-47: Put full-schema benchmarked NVIDIA routes first and cool down unhealthy routes

**Date:** 2026-08-12

**Status:** Implemented, deployed, and live-accepted

**Context:** The deployed AI-first Study gateway used OpenRouter first for most
interactive tasks and native Workers AI first for long-form generation. Its
payload-free D1 records showed frequent OpenRouter deadline failures and mean
successful Workers AI latency around 4-7 seconds for interactive work,
51 seconds for lecture analysis, and 28 seconds for material generation. The
owner supplied an NVIDIA API key through the Windows user environment and asked
for Study to use the fastest available AI. A tiny Ask response alone was not
enough evidence because LecturePack requires large, strict JSON schemas for its
two build passes and a real selected-slide image contract.

**Decision:** Keep all provider selection server-side and add NVIDIA's hosted
NIM endpoint as a third independent failure domain. Use
`meta/llama-3.1-8b-instruct` for text and
`nvidia/nemotron-nano-12b-v2-vl` for selected-slide vision. NVIDIA is first for
analysis, material generation, Ask, Teach Me, grading, concept regeneration,
and vision; native Workers AI and OpenRouter follow on independent hosts.
OpenRouter remains first for `web_enrichment` because its bounded URL
annotations are the only configured web-citation authority.

The selection is based on live, schema-valid Polar Bears tests. NVIDIA-hosted
Llama 3.1 8B completed Ask in about 0.7 seconds, lecture analysis in about
7 seconds, and the full minimum Study system in about 22 seconds. The selected
vision model completed the real bundled-slide schema in about 6.7 seconds.
Every result passed the existing gateway validator, including two guide
sections, two flashcards, all three quiz types, Teach Me content, and grounding
fields. Faster-looking catalog entries that returned 400/404, malformed JSON,
or exceeded the bounded full-schema timeout were rejected.

Route IDs are provider-stable rather than position-based. Two consecutive
failures within five minutes place a route behind healthy fallbacks while
retaining it as the last recovery attempt. This circuit state uses the existing
payload-free `provider_health` table. Per-provider route deadlines cap the
three-route long-form worst case at 160 seconds, leaving room inside the
desktop client's 175-second deadline.

**Alternatives considered:**

- Racing multiple providers and accepting the first response: rejected because
  it sends the same lecture evidence to multiple providers, increases cost,
  and conflicts with the payload-minimizing boundary.
- Selecting from a one-line latency probe: rejected because several models
  were fast on Ask but slow or invalid on the full Study schemas.
- Using Nemotron 3.5 Lightning or Nemotron Nano 9B for all text work: rejected
  because the measured full analysis/material paths were substantially slower,
  including one 120-second timeout.
- Changing models through the renderer or NVIDIA website at request time:
  rejected because provider/model input remains forbidden in the desktop and
  the saved key already had the required hosted-model access.

**Rationale:** A measured sequential fastest-first chain materially reduces
normal Study latency while preserving strict validation, three independent
hosts, honest fallback behavior, and the existing privacy boundary. A short
metadata-only cooldown prevents a repeatedly failing primary from adding the
same timeout to every student request.

**Official NVIDIA contracts checked 2026-08-12:**

- NVIDIA NIM LLM API (`POST /v1/chat/completions`):
  `https://docs.api.nvidia.com/nim/reference/llm-apis`
- NVIDIA structured generation:
  `https://docs.nvidia.com/nim/large-language-models/1.15.0/structured-generation.html`
- NVIDIA-hosted Llama 3.1 8B:
  `https://build.nvidia.com/meta/llama-3_1-8b-instruct?nim=hosted&section=deploy`
- NVIDIA Nemotron Nano 12B v2 VL:
  `https://build.nvidia.com/nvidia/nemotron-nano-12b-v2-vl`

**Production deployment record (2026-08-12):** Worker version
`d9e2dbcb-369b-4a4e-a895-e8ff75ea4fc5` is deployed at the existing production
origin. The NVIDIA key is stored only as the `NVIDIA_API_KEY` Worker secret.
All seven NVIDIA-first tasks passed through the public gateway on attempt one:
analysis 3.5 seconds, complete materials 15.6 seconds, Ask 0.6 seconds,
Teach Me 1.3 seconds, grading 0.9 seconds, concept regeneration 1.5 seconds,
and selected-slide vision 4.1 seconds (provider latency rounded from D1).
Normal success responses exposed no route/model identifier. The post-deploy
health check reported 8/8 configured tasks, the existing real-provider pytest
passed, the remote schema remained payload-free, and an exact-key scan of all
776 tracked files found zero matches.

**Release re-audit (2026-08-12):** Wrangler 4.122.0 confirmed production still
runs version `d9e2dbcb-369b-4a4e-a895-e8ff75ea4fc5` at 100 percent. Its deployed
bindings contain the exact seven-task NVIDIA-first list, the two documented
model ids, and `NVIDIA_API_KEY` only as opaque `secret_text`. D1 has no pending
migrations and `/v1/health` reports all 8 required tasks configured. Aggregate
payload-free production telemetry for the audited window showed NVIDIA text at
43/43 successes (about 5.0 seconds average, including long-form material),
NVIDIA vision at 1/1 (about 4.1 seconds), native Workers AI at 20/21 (about
19.7 seconds), and OpenRouter at 7/26 (about 16.3 seconds). NVIDIA was also the
fastest healthy route per interactive task. The local Worker source passed all
21 tests, syntax checks, and a Wrangler dry-run bundle with the same bindings.
No production deployment was changed during this re-audit.

## AD-38: Study commands and bootstrap restore are scoped to the viewed lecture

**Date:** 2026-08-09
**Status:** Implemented on `sol/release-base-integration`

**Context:** Packaged integration acceptance exposed two ways the active
processing slot could leak into the viewed Study workspace. Study V2 and Ask
commands omitted `job_id`, so the sidecar resolved them against
`current_job`; and the bootstrap `active_job` replay could overwrite the saved
view before `jobs_changed` restored the user's explicit session.

**Decision:** Every Study V2 mutation/read and Ask request carries the viewed
`LP.state.jobId`; asynchronous Study responses are discarded if the viewed
lecture changed before they return; same-screen lecture switches immediately
clear and reload the Study snapshot; Ask resolves that explicit job in the
sidecar; and session writes are suppressed until the one-time restore has read
the existing saved selection.

**Alternatives considered:**

- Re-pointing `current_job` whenever the user switches lectures: rejected
  because that identity owns the running pipeline and would violate
  `ACTIVE JOB != VIEWED JOB`.
- Adding a second Study selection store: rejected because the renderer's
  existing viewed job is already authoritative.
- Clearing Study content without scoping backend commands: rejected because
  it would hide the UI symptom while still recording mastery and edits on the
  wrong lecture.

**Rationale:** Explicitly routing through the existing viewed-job identity
preserves background processing, makes Study persistence deterministic, and
fixes the integration seam without adding architecture or product behavior.

## AD-37: Idle starts activate the requested job before claiming the queue slot

**Date:** 2026-08-09
**Status:** Implemented on `sol/release-base-integration`

**Context:** Packaged Study + QoL acceptance exposed a crossed-identity race.
After a completed lecture remained the sidecar's `current_job`, a downloaded
lecture could be imported and a different ready lecture could be started. The
queue claimed the requested job id, but `_job_for` deliberately left the idle
controller pointed at the prior `current_job`; `run_pipeline()` therefore
processed the prior lecture while the queue advertised another active id.

**Decision:** When no pipeline stage is active, `_start_job` explicitly
activates the requested job before releasing a stale queue slot, claiming the
single active slot, emitting payloads, and calling `run_pipeline()`. The
already-running path remains unchanged and continues to enqueue a different
requested job without re-pointing the controller.

**Alternatives considered:** Making `_job_for` always activate a requested job
was rejected because view/fetch callers rely on it not swapping controller
ownership during processing. Clearing `current_job` after every completion was
rejected because the completed workspace remains useful and is part of session
restore. Deriving renderer state from the mismatched controller was rejected
because it would hide backend corruption rather than preserve the one-active
job invariant.

**Rationale:** The fix is confined to the idle start boundary, preserves
ACTIVE JOB != VIEWED JOB, and keeps the existing queue, controller, and
persistence authorities aligned without adding state or changing architecture.

## AD-36: Desktop QoL state stays on the existing job, queue, import, and resume paths

**Date:** 2026-08-09
**Status:** Implemented on `sol/qol2.0`

**Context:** The desktop polish pass needed editable lecture names, faster
lecture switching, a useful global progress readout, contextual actions,
window/session restoration, and non-blocking multi-URL downloads. The product
already had separate viewed-job and processing-job state, persisted job
manifests, an authoritative queue/progress feed, per-job resume storage, an
Electron host, and a yt-dlp-backed `MediaFetcher` that hands completed files to
the normal import path.

**Decision:**

- Store the conservative imported display name in the existing manifest
  `title`; retain the exact original path and filename in manifest `source`.
  Rename continues through `electron_backend.rename_job`.
- Keep `LP.state.jobId` as the viewed lecture and `activeJobId` as the processing
  slot. The header switcher only calls the existing `view_job` flow.
- Project ETA from elapsed time and authoritative backend percent, with a
  minimum sample and smoothing. Queue badges read the existing queue snapshot.
- Route renderer context-menu entries through the same selection, queue,
  cancellation, retry, export, folder, rename, and delete commands already used
  elsewhere.
- Extend the existing per-job resume store with one small selected-job/screen
  record. Persist Electron window bounds separately in the existing Electron
  user-data directory and reject off-screen bounds before applying them.
- Keep `MediaFetcher` as the only downloader. A thin, sequential in-memory list
  supplies waiting/cancel/retry presentation while each completed file enters
  the unchanged `import_video` path. The existing Electron process-tree shutdown
  guard remains authoritative for child cleanup.

**Alternatives considered:** A second selected-lecture store, synthetic progress
timer, native-menu business-logic layer, new persistence service, downloader
service, and general-purpose scheduler were rejected as duplicate architecture.
Playlist expansion was not added because the current fetcher intentionally
resolves one recording per URL; multi-line input provides explicit batch scope.

## AD-54: Study mastery keeps an atomic last-known-good generation

**Date:** 2026-08-09
**Status:** Implemented. Authored 2026-08-09 on `codex/study-progress-backup`,
cherry-picked onto the release line 2026-08-15 as the last unmerged work from
`kimi/study-overhaul-v1`. Renumbered from AD-36, which was already taken.

**Context:** `study-progress-v2.json` contains irreplaceable user mastery,
attempt history, and Quick Study position. The shared JSON helper already wrote
through a temporary file and `os.replace`, but it used one fixed temporary name,
did not explicitly flush file contents before replacement, and retained no
recoverable generation if the primary later became corrupt.

**Decision:** Study progress persistence now writes through a unique temporary
file in the destination directory, flushes and `fsync`s the complete JSON, and
atomically replaces the destination. Before Study progress advances, a valid
current primary is atomically persisted as `study-progress-v2.json.bak`.
Loading falls back to that last-known-good generation when the primary is
missing, truncated, or invalid. The first generation is written to both
locations so it is covered before a second review occurs. An invalid primary
is never promoted over a valid backup, and backup recovery emits a warning to
the existing local log.

**Alternatives considered:** Keeping only atomic replacement was rejected
because it does not cover later filesystem corruption or a logically damaged
primary. A database and multi-generation journal were rejected as unnecessary
for the current single-writer, per-job persistence model.

**Rationale:** The change protects the highest-value user-authored Study state
without changing its schema or introducing a dependency. Unique temporary files
also avoid collisions between overlapping Study progress saves.

---

## AD-34: QOL batch actions are transactional, live progress has one authority, and Electron artifacts are explicit

**Date:** 2026-08-08
**Status:** Implemented on `kimi/qol-productivity-pass`

**Context:** The five-feature QOL/Productivity pass added multi-video import,
global processing progress, global transcript search, per-lecture resume state,
and a Ctrl+K command palette. A stabilization audit found that the UI surfaces
were present but several end-to-end actions were incomplete: Search had no
reachable trigger and did not consume its timestamp jump; Queue all parked jobs
without applying the visible settings or starting an idle queue; taskbar
progress was overwritten by a later indeterminate pipeline event; resume state
read the non-scrollable transcript content node and was not saved on app close;
and the reported portable ZIP came from the legacy PyInstaller/Qt release
builder rather than the Electron product entry point.

**Decision:**

- Make global transcript search a persistent header action and a command-palette
  action. Transcript rows carry their source timestamp; a result selection keeps
  a pending jump until the requested lecture's transcript payload is available,
  then centers and briefly highlights the exact segment.
- Treat Queue all as one user action: apply the selected output mode and quality
  before enqueueing, then immediately promote the first job when the active slot
  is idle. Existing FIFO completion promotion handles the remaining jobs.
- Keep `status_changed.pct` as the sole Windows taskbar authority for overall job
  progress. A `pipeline_changed` event may show indeterminate state only before
  the first status payload for that job; it may not overwrite determinate
  progress. Refresh the in-app global strip on every status payload.
- Store transcript resume scroll from the transcript section (the actual scroll
  container), persist the current lecture during `beforeunload`, and preserve
  explicit search/Process navigation as an override.
- Include the new overlays in the existing focus trap, use native buttons for
  batch choices and the processing strip, label dialogs, and collapse the
  breadcrumb at the minimum supported window width.
- Build and label Electron release candidates only through
  `scripts/build_electron_release.py` / `electron-spike/package-win.mjs`.
  `scripts/build_release.py` output is the legacy Qt product and must not be
  cited as evidence for Electron QOL features.

**Alternatives considered:** Leaving Queue all as a queue editor was rejected
because its label and placement communicate immediate execution. Deriving a
second taskbar percentage from active-stage events was rejected because the
sidecar already emits the authoritative overall percentage. Storing a transcript
block index instead of a timestamp was rejected because edits and regenerated
segments can change array positions. Replacing the legacy Qt ZIP in place was
rejected because it would make two different product shells share an ambiguous
artifact name.

**Rationale:** Each user action now has one observable outcome and one state
authority. The fixes remain within the Phase 9 renderer/host/sidecar seam,
preserve the existing engine and persisted job format, and make release evidence
traceable to the product that contains the feature.

---

## AD-28: Package the disposable Electron acceptance demo as a resource

**Date:** 2026-08-04
**Status:** Implemented for the Phase 8 unpacked candidate

**Context:** The packaged acceptance command intentionally imports the demo
video from `resources\\assets\\demo-lecture.mp4`, but the Windows packager was
excluding the source `electron-spike/assets` directory entirely. That made the
documented gate depend on an unbundled developer checkout.

**Decision:** Keep the source asset excluded from `app.asar`, while adding the
small demo-assets directory as an Electron `extraResource`. The resulting
portable candidate contains the disposable demo at the documented external
resource path. No customer lecture, updater, URL import, AI, installer, or
other deferred feature is added.

**Alternatives considered:** Requiring the developer to copy a video beside
the package was rejected because it weakens the reproducible acceptance gate.
Embedding the video in `app.asar` was rejected because the gate's documented
path and sidecar invocation use an external resource.

**Rationale:** This is the smallest packaging-only repair needed to run the
already-approved Phase 8 gate exactly as specified.

---

## AD-27: Phase 8 Electron Bridge Coverage Reconciliation

**Date:** 2026-08-03
**Status:** Implemented in the production Electron seam; affected-laptop gate pending

**Context:** The Phase 8 bridge coverage contract identified four operations
that the reused UI consumes as part of the production core but that the first
Electron candidate had not connected: bootstrap completion, slide decisions,
transcript corrections, and export progress. The contract commit was already
the current branch head, so the task was a compatibility review plus minimal
implementation rather than a separate architecture phase.

**Decision:** Implement exactly those four operations at the existing bridge
boundary. Emit `bootstrap_complete` after sidecar bootstrap, map and persist
`set_slide_state` in the existing `candidates.json`, map and persist
`save_corrections` through the existing transcript working layer and
`edited.json` mirror, and emit `export_progress` with the UI's existing `pct`
and `label` fields. Leave every operation marked `DEFERRED` untouched.

**Alternatives considered:** Replacing the UI with a new contract, changing
the persisted job format, implementing the full historical bridge, or
re-enabling URL import/updater/AI/GPU features were rejected because they would
expand the Phase 8 acceptance scope.

**Rationale:** These are narrow, user-visible holes in the already selected
Electron seam. Connecting them preserves the current UI and data formats while
making the contract honest and testable before the laptop gate.

---

## AD-25: Phase 7.1 Electron Contract Repair

**Date:** 2026-08-03<br>
**Status:** Implemented in the isolated migration slice; affected-laptop gate
pending

**Context:** The first vertical slice reached real processing, but three small
transport mismatches still made it unsuitable for the affected-laptop gate:
the existing UI expects `jobs_changed` to parse directly as an array, theme
clicks were being sent as unsupported sidecar requests, and a persisted
pipeline state could make an active job look complete before its Study Pack
export finished. Transport text also needed to avoid display encoding failures.

**Decision:** Keep the sidecar event envelope internal to the Electron adapter
and normalize `jobs_changed` to the exact array consumed by `app/ui/app.js`.
Locally handle `set_setting('theme', value)` in the renderer adapter, with a
local persistence attempt and no sidecar request. While an active job has a
current stage and Export is incomplete, report the existing UI vocabulary
`status: "running"`; switch to `"done"` only after the terminal export state.
Use ASCII separators in the touched transport status/meta strings.

**Alternatives considered:** Changing `app/ui/app.js` to accept a new envelope,
adding a `processing` badge vocabulary, implementing a new sidecar settings
command, or expanding the migration contract were rejected because this is a
small compatibility repair, not an architecture phase.

**Rationale:** The adapter absorbs the mismatch at the existing seam, avoids
228 unnecessary theme round trips during stress, and preserves the UI's
established status/badge behavior without changing the engine or product shell.

## AD-24: Explicit Electron Migration Vertical Slice

**Date:** 2026-08-03<br>
**Status:** Implemented as an isolated migration slice; affected-laptop gate
pending before any broader migration or release work

**Context:** AD-23 established that the Electron renderer seam could be
exercised without changing the Qt product shell, but its Mode 3 sidecar only
proved engine import and heartbeat transport. The next authorized step is a
real, reversible vertical slice that can be tested on the laptop showing the
black interval. It must prove the process boundary and one complete user
outcome without turning the work into Beta 15, a frontend rewrite, or an
engine rewrite.

**Decision:** Add an explicit `migration` mode inside the isolated
`electron-spike/` harness. Electron launches a dedicated PyInstaller onedir
sidecar built from the locked `.venv`; the sidecar uses `QCoreApplication` only
and reuses the existing `JobController` and processing services. Electron and
the sidecar exchange request-ID JSONL over stdin/stdout. The first contract
contains `health_check`, `list_jobs`, `import_video`, `start_job`,
`cancel_job`, `get_job`, `get_slides`, `get_transcript`, `export`, and
`shutdown`, plus the documented progress, pipeline, status, log, slide,
transcript, and error events.

The first real path is fixed to a bundled demo video, CPU FFmpeg/ffprobe,
CPU whisper.cpp, the existing slide detector, the existing transcript layer,
and the existing Study Pack export service. The Electron adapter supplies the
existing `app/ui` with the same event shapes; it does not expose Node or
QWebChannel to that UI. The packaged sidecar includes its own PySide6/runtime
dependencies, so a customer machine does not need Python or PySide6.

**Alternatives considered:** continuing Qt graphics/CSS diagnosis, building
Beta 15 from the current Qt shell, converting the frontend to React, or
rewriting the Python engine were rejected because they would not answer the
affected-laptop process-boundary question. Replacing the engine with a new
backend was rejected because it would invalidate the already-working FFmpeg,
whisper.cpp, slide, transcript, and export behavior. Shipping the full GPU
runtime was deferred; the first packaged candidate is the verified CPU path.

**Rationale:** A complete import-to-export-to-restart path gives the laptop a
meaningful acceptance target while preserving the existing engine and keeping
the migration reversible. Remaining bridge methods, installer, updater, and
release packaging stay outside this slice until the laptop gate passes.

## AD-23: Isolated Electron Renderer Spike (Experiment Only)

**Date:** 2026-08-03<br>
**Status:** Accepted as an unversioned diagnostic artifact; not a product-stack change

**Context:** Beta 14 improved a confirmed QtWebEngine workload defect, but the
affected laptop still showed a multi-second interval in which application
content became almost completely black. Development-machine acceptance could
not reproduce that failure. Further QtWebEngine flags or CSS tuning would not
separate a renderer-surface failure from frontend state/update logic or a
Python bridge problem.

**Decision:** Add an isolated `electron-spike/` harness that reuses the
existing `app/ui` HTML, CSS, JavaScript, and fonts without changing the
PySide6/QWebEngine product shell, the Python engine, release version, installer,
updater, or product specification. One Electron process offers three modes:

1. a script-free static page with a minimal theme toggle;
2. the real frontend with a local mock signal workload covering setup, Demo
   transitions, processing progress, 500 logs, slides, transcript, theme, and
   resize pressure; and
3. a gated local stdio sidecar that imports the existing
   `lecturepack.controllers.job_controller` entry point.

Mode 3 proves only process/engine import and heartbeat transport until Mode 2
passes on the affected laptop. No lecture-processing command is ported in this
artifact. The spike writes only local JSONL evidence and makes no network
requests at runtime.

**Alternatives considered:** Continuing the Beta 14 QtWebEngine patch cycle,
building Beta 15 from that approach, migrating React at the same time, or
rewriting the Python engine were rejected because they do not isolate the
renderer, frontend workload, and backend seam on the machine that actually
fails. A full Electron migration was rejected for this step because the
affected-laptop experiment must decide whether that migration is warranted.

**Rationale:** Separating static rendering, frontend workload, and Python
transport creates a concrete decision tree with the smallest reversible change.
The affected laptop remains the acceptance authority; a smooth development
run is not treated as evidence that the original defect is fixed.

## AD-22: Beta 12 Startup Grace and Native Placeholder (Phase 4)

**Date:** 2026-08-02
**Status:** Accepted for beta.12 startup reliability

**Context:** A fast runtime assessment can produce a sub-second checking
overlay that reads as a startup flash, while the first WebEngine frame can
leave a newly shown native window visually empty for roughly the duration of
Chromium startup. The two symptoms have different lifetimes and need not be
solved by changing the renderer or delaying the window.

**Decision:** When the runtime gate enters hidden `checking`, wait 600 ms and
open the existing overlay only if the state is still checking; clear that
timer on every state exit and close path. Show a native, theme-synchronized
`QStackedWidget` startup surface containing “LecturePack · starting…” until
the first `ui_ready()` call, then switch to the existing QWebEngine view.

**Alternatives considered:** suppressing the checking overlay unconditionally,
delaying `show()` until the WebEngine page is fully interactive, adding a DOM
placeholder, and changing WebEngine compositing or CSS. Unconditional
suppression would hide useful progress on slow installs; delaying the window
would make startup feel slower; a DOM placeholder cannot cover the native
pre-first-frame gap; renderer changes remain outside the confirmed evidence.

**Rationale:** The grace timer removes only transient modal noise while
preserving honest progress, and the native placeholder gives immediate,
theme-correct feedback without changing the WebEngine surface or startup
latency.

---

## AD-21: Beta 12 Opt-In Guided-Tour Trace Transport (Phase 4)

**Date:** 2026-08-02
**Status:** Accepted for beta.12 diagnosis; no flicker fix inferred

**Context:** Beta.11 still showed an unexplained guided-tour flicker on the
affected laptop, but the available evidence did not distinguish a hidden-state
write from a missed composited presentation. Applying another CSS or Chromium
change without that distinction would repeat the prior speculative fixes.

**Decision:** Gate the diagnostic on `LECTUREPACK_TOUR_TRACE=1` in the desktop
bridge and expose that boolean through `get_bootstrap()`. The UI batches
overlay hidden writes, overlay `MutationObserver` records, and
`requestAnimationFrame` callback timestamps, then sends each batch through one
narrow local `log_tour_trace` bridge slot. The slot writes to stderr and the
existing `log_line` signal. The default path starts no observer, heartbeat, or
trace timer, and beta.12 does not modify overlay CSS.

**Alternatives considered:** a new file/network logging service, always-on
tracing, more Chromium flags, and a speculative compositing change. The first
two broadened runtime cost or transport surface; the latter two would not
identify whether the overlay was hidden or merely missed by presentation.

**Rationale:** The local sink makes a filmed laptop run correlatable with
visible timestamps while preserving the existing no-network diagnostics
boundary. The trace evidence will determine whether a later CSS change is
warranted.

---

## AD-20: Beta 10 Automated Window Acceptance Gate (Phase 4)

**Date:** 2026-08-02
**Status:** Accepted for local beta.10 preparation; publication remains gated

**Context:** Three consecutive packaged-app runs were required to verify that
the beta.9 visual fixes held during the full user sequence, including native
video import, real processing, resizing, five-minute idle, and reopen. DOM-only
evidence could not prove a WebEngine surface flash or a resize surface loss.

**Decision:** Keep the gate as one small Windows-only script using the packaged
executable, disposable data/WebEngine profiles, Win32 window capture, a real
desktop recording, raw CDP telemetry, and a native Win32 file-dialog seam.
Use short intent windows only around known navigation/theme transitions. Fix
only confirmed causes: remeasure the processing Demo spotlight after pipeline
DOM growth, and close a stale runtime checking overlay after acknowledged
healthy bootstrap.

**Alternatives considered:** a general UI test framework, DOM screenshots as
the sole evidence, disabling animations, broad GPU flags, `will-change`
changes, and framework migration. All were rejected as broader than the
confirmed causes or unable to prove the native-window symptoms.

**Rationale:** The resulting evidence is reproducible and release-sized while
preserving the existing UI, motion, renderer, security checks, and dependency
boundary.

---

## AD-19: Beta 9 WebView Compositor and Live-Update Reliability Follow-up (Phase 4)

**Date:** 2026-08-01
**Status:** Accepted for the beta 9 diagnosis-only release

**Context:** Beta 8 still showed first-frame theme flashes, startup scrollbar
artifacts, repeated setup-gate DOM construction, and pipeline/status strobing
under rapid backend updates. Two supplied diagnosis reports were compared and
were content-identical.

**Decision:** Keep one theme authority on `document.documentElement`, synchronize
the QWebEngine and native window backgrounds from the saved theme, install the
central widget before loading the page, and leave document scrolling to CSS
containers. Guard unchanged setup-gate frames, update checklist rows in place,
coalesce pipeline renders to animation frames, suppress duplicate integer stage
progress, and update status labels without replacing their animated dot nodes.

**Alternatives considered:** GPU/DPI flags, locale/debug-payload changes,
transcript-log policy changes, and a renderer rewrite are deferred until a
reproducible beta 9 package still demonstrates those separate symptoms.

**Rationale:** These are the smallest source-local fixes that address the
reported flashes without changing the engine, data boundaries, approved visual
language, or dependency set.

---

## AD-18: ASCII Staging Boundary for whisper.cpp v1.9.1 Native Arguments (Phase 1)

**Date:** 2026-07-28
**Status:** Accepted by explicit Phase 1 continuation approval

**Context:** The pinned whisper.cpp v1.9.1 CPU binary loaded successfully from a
copied Unicode-and-space onedir, but crashed after receiving Unicode model/WAV
paths through its native CLI boundary. Replacing the binary, changing its
version, or weakening Unicode installation and user-data support is outside
this phase and was not authorized.

**Decision:** Keep all application-facing installation, model, audio, data, and
final transcript paths Unicode-capable. Immediately before invoking the native
whisper.cpp executable, copy only the model and WAV to a private,
application-controlled ASCII-only staging directory with collision-safe names.
Pass the staged model, WAV, and output-prefix paths with a QProcess argument
array; never construct a shell command. On successful completion, atomically
publish the staged transcript artifacts to the requested Unicode destination.
Remove the staging directory after success, nonzero exit, timeout, cancellation,
or preparation exception. The disposable packaged smoke uses the same staging
boundary while retaining the executable and DLLs in the copied Unicode onedir.

**Alternatives considered:**
- Passing Unicode paths directly to v1.9.1: rejected because the real disposable
  smoke reproduced a native crash after CPU DLL loading.
- Replacing or rebuilding whisper.cpp: rejected because this Phase 1 approval
  expressly pins v1.9.1 and does not authorize a payload change.
- Restricting user or installation paths to ASCII: rejected because it violates
  the product's Windows path-safety requirement.

**Rationale:** This is the smallest application-controlled compatibility boundary:
it preserves end-to-end Unicode support and source bytes while isolating a known
native argv limitation to the only paths whisper.cpp must consume.

---

## AD-17: "Premium Glassmorphic Dark" UI Overhaul (Phase 2, v1.4)

**Date:** 2026-07-19
**Status:** Accepted

**Context:** The v1.1 shell looked like an engineering console. Phase 2
rebuilt the visual layer as a premium dark, glassmorphic desktop experience
without touching the pipeline, services, or persistence.

**Decision:**
- **Theme:** a static `lecturepack/ui/themes/dark_theme.qss` (Catppuccin
  Mocha palette: `#1E1E2E` base, `#89B4FA` accent) with literal hex values
  (QSS has no CSS variables). `ui/theme.py` keeps its v1.1 API and gains the
  matching `MOCHA_*` constants, the Mocha dark `QPalette`, a QSS loader, and
  an `add_card_shadow` helper. The file QSS is appended last so it wins the
  cascade over the structural v1.1 rules.
- **Frameless shell:** `Qt.FramelessWindowHint` plus a custom
  `TitleBarWidget` (drag, double-click maximize, min/max/close) and a
  `QSizeGrip` in the status bar. Accepted tradeoff: Windows 11 snap layouts
  and the native drop shadow are lost.
- **Transcript rendering:** custom `TranscriptBlockWidget` cards inside a
  lazily materialized `TranscriptStreamView` (batches of 120, extended on
  scroll or via `ensure_materialized`) so long lectures never pay the full
  widget cost; `bisect`-based pure helpers do O(log n) timestamp matching.
- **Study workspace:** slide timeline (reused `SlideGridWidget`, accepted
  slides only) left, transcript right, v1.2 overview in a collapsible card.
  Bidirectional sync uses two guards — `_sync_guard` (transcript → grid)
  and `_programmatic_scroll` (cleared when the smooth-scroll animation
  finishes) — so the two directions cannot oscillate.
- **Process page:** dropzone hero with an accent glow on drag-hover;
  engine/VAD/detection settings moved into an animated-width (220 ms)
  "Advanced Settings" drawer; Phase 1's live pane now uses the same block
  widget (capped at 200 blocks). Every pre-existing widget attribute, object
  name, and signal relied on by MainWindow/tests is preserved.
- **Focus Mode:** fades exactly three shell widgets (nav rail, command bar,
  status bar) via opacity animations, then hides them; floating
  semi-transparent "Exit Focus" button plus `Esc`.
- **Page transitions:** `AnimatedStackedWidget` (180 ms slide+fade) with a
  rapid-navigation guard.
- The dark theme remains **opt-in** (`dark_theme` config default unchanged);
  flipping the default was outside the approved phase file list.
  *(Addendum 2026-07-19: the user approved the flip after acceptance —
  `dark_theme` now defaults to `True`, and `LecturePack.spec` ships the QSS
  in `datas` plus the new widget modules in `hiddenimports`.)*

**Alternatives considered:**
- QSS generated in Python from constants (single source of truth): rejected
  in favor of a readable, hand-tweakable static QSS file plus mirrored
  constants for widget code.
- Overlay (non-layout) settings drawer: rejected; in-layout animated
  `maximumWidth` is simpler and avoids overlay geometry bugs.
- Native title bar with dark theme only: rejected; the frameless shell is
  core to the intended look.
- Showing all slides (incl. rejected) in the Study workspace: rejected;
  Study is a post-review reading surface, so it shows accepted slides only.

---

## AD-16: Live Transcript Streaming from whisper.cpp stdout; No Controller Thread Move (v1.3)

**Date:** 2026-07-18
**Status:** Accepted

**Context:** During transcription the UI appeared frozen and no transcript text
was visible until the stage completed. The transcription path already used
`QProcess` asynchronously, so the freeze was not process blocking. The real
causes were (a) whisper-cli carriage-return progress updates forwarded per
chunk into `QTextEdit.insertPlainText`, forcing hundreds of document
relayouts per second and starving the GUI event loop, and (b) transcript
text existing only in the final `raw.json/srt/txt` artifacts.

**Decision:** Parse whisper.cpp's real-time stdout segment lines
(`[HH:MM:SS.mmm --> HH:MM:SS.mmm] text`) incrementally and surface them as
ephemeral, display-only `segment_ready` dicts
(`{"start_ms", "end_ms", "text", "seq"}`). The chain is
`WhisperWrapper.segment_ready` -> `TranscriptionBackend.segment_ready` (new
optional interface signal, advertised via
`BackendCapabilities.supports_live_segments`) -> `JobController.transcript_segment`
-> the process page's live-transcript pane. Live segments are never written to
the raw/normalized/working persistence layers; the canonical transcript is
still built from `raw.json` on stage success. Separately, transcribe-stage log
output is coalesced in `JobController` and flushed to `stage_log` on a 200 ms
`QTimer` (with a final flush before the result is handled), which removes the
relayout storm for all log consumers.

`JobController` was deliberately **not** moved to a dedicated `QThread`:
`QProcess` signals are already non-blocking and delivered through the GUI
event loop, so the move would add cross-thread lifecycle risk (cancel
semantics, worker parenting, job-state saves) with no measured benefit.

**Alternatives considered:**
- Moving `JobController` (or only `WhisperWrapper`+`QProcess`) to a worker
  thread: rejected for Phase 1; adds thread-affinity complexity and does not
  address the log-relayout storm, which was the actual freeze. The
  wrapper-only variant remains an option if process I/O ever measurably
  contends with the GUI.
- True word-level streaming via `whisper-stream`: rejected as an engine
  change with unverified Vulkan-build implications. whisper-cli emits
  segment-per-line only, so Phase 1 delivers segment-level live text.
- UI-side throttling in the process page: rejected in favor of the
  controller-side throttle so every present and future `stage_log` consumer
  benefits.

**Rationale:** The parser operates on a byte buffer split on both `\n` and
`\r`, which tolerates merged-channel progress pollution and decodes complete
lines only, fixing split multi-byte UTF-8 across reads. An unterminated
trailing line is flushed at process end so no segment is lost.

---

## AD-15: Baseline-Gated Architecture Release Check (v1.2)

**Date:** 2026-07-18
**Status:** Accepted

**Context:** The Phase 1 whole-tree import audit correctly found 47 existing
violations of the approved adjacent-layer rule across 62 cross-layer edges.
Eliminating those violations requires a broad production refactor outside the
packaging release scope. The audit remains useful as a release regression gate,
but its existing debt must not be mistaken for strict conformance.

**Decision:** The strict UI -> Controller -> Service -> Infrastructure rule in
`docs/ARCHITECTURE.md` remains the target architecture. For the v1.2 Phase 1
packaging release, the architecture gate blocks only a violation whose exact
identity is absent from the evidence committed at `25e9dd1`. The 47 existing
violations across 62 cross-layer edges are disclosed baseline debt and are
deferred to Phase 2 for closure. Phase 1 may report `ARCHITECTURE_CHECK: PASS`
only when `NEW_VIOLATIONS_COUNT: 0`; it must also report that strict architecture
conformance has not been achieved.

**Alternatives considered:** Blocking the v1.2 packaging release on an immediate
broad architecture refactor was rejected because it materially expands Phase 1
and risks unrelated release behavior. Silently ignoring or removing the audit
was rejected because it would erase known debt and permit new violations to
enter undetected.

**Rationale:** An immutable, identity-level baseline preserves a fail-closed
no-regression gate for the release while keeping all existing violations visible
and assigning their actual remediation to a separately planned Phase 2 effort.

---

## AD-14: Canonical Runtime and Build Version Authority (v1.2)

**Date:** 2026-07-18
**Status:** Accepted

**Context:** The package initializer, application constants, release script,
and human-facing build labels previously carried independent release-version
literals. That allowed the runtime version, new-job manifests, archive names,
and release metadata to drift apart during a release update.

**Decision:** Define the executable release semantic version only in
`lecturepack.__version__`. Application code consumes that value through
`constants.APP_VERSION`, and release tooling consumes it through
`build_release.VERSION`. Human-facing build labels, including the
`LecturePack.spec` header, remain synchronized with the canonical version but
are explicitly non-authoritative.

**Alternatives considered:** Keeping independent literals in every consumer
was rejected because it preserves the source of runtime, manifest, and archive
drift. Parsing the PyInstaller spec header at runtime was rejected because a
human-facing comment is not an import-safe metadata contract and would couple
application startup to build configuration text.

**Rationale:** A dependency-free package-level authority is available to both
runtime and build consumers without initialization-order dependencies, while
synchronized labels remain readable to release reviewers.

---

## AD-13: Opt-In Groq Audio Transcription with Credential Manager (v1.2)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** Online Fast and Online Accurate must improve transcription speed or
accuracy without weakening Private Local defaults, uploading visual/job data,
persisting API keys, blocking the Qt event loop, or replacing a valid local
transcript with a partial provider result. Provider limits and pricing can
change independently of LecturePack.

**Decision:** Register two explicit provider adapters above the neutral
transcription seam: `groq-fast` uses `whisper-large-v3-turbo` and
`groq-accurate` uses `whisper-large-v3`. Private Local remains the default for
new and old jobs. Require per-job consent immediately before an online run and
read the key only from Windows Credential Manager. Upload only lossless FLAC
audio derived from the existing 16 kHz mono WAV; do not send video, slides,
transcript text, job metadata, or glossary prompts.

Use a conservative 23 MiB direct-upload ceiling beneath Groq's documented
25 MB free-tier limit. Plan overlapping, ordered chunks from worst-case PCM
size, encode each with an exact LecturePack-owned FFmpeg PID, retry transient
errors with bounded exponential backoff and `retry-after`, cache successful
per-chunk JSON by an input fingerprint, offset timestamps, remove overlap
duplicates, and atomically publish canonical raw outputs only after all chunks
merge. On eligible online failure, retry only the transcription branch through
Private Local while concurrent slide detection continues. Preserve any prior
canonical transcript until either provider or fallback succeeds.

**Alternatives considered:** Storing a key in `config.json` or job settings was
rejected as plaintext secret persistence. Environment-only configuration was
rejected because it does not provide the required native Set/Test/Remove
workflow. Adding the Groq SDK was rejected because the OpenAI-compatible
multipart endpoint is small enough for the standard library and a new runtime
dependency was unnecessary. Uploading the original video was rejected because
only audio is required. Assuming developer-tier limits or a free allowance was
rejected because limits and billing are account-specific and mutable.

**Rationale:** This design makes every network action visible and opt-in,
minimizes uploaded data, resumes safely, keeps the native window responsive,
and preserves the already-proven local path as a real fallback rather than a
second provider implementation.

**Official sources checked 2026-07-16:**
[Groq Speech to Text](https://console.groq.com/docs/speech-to-text),
[Groq rate limits](https://console.groq.com/docs/rate-limits),
[Groq API errors](https://console.groq.com/docs/errors), and the official model
pages for
[`whisper-large-v3-turbo`](https://console.groq.com/docs/model/whisper-large-v3-turbo)
and [`whisper-large-v3`](https://console.groq.com/docs/model/whisper-large-v3).

---

## AD-12: Provider-Neutral Transcription Above Local Compute Engines (v1.2)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** LecturePack already has a proven `EngineRegistry` for selecting
whisper.cpp CPU or Vulkan binaries. Optional online transcription needs a
separate provider boundary without scattering HTTP, secret, retry, chunk, or
fallback logic through `JobController`, and without recasting a selected
engine as proof of the backend that actually loaded.

**Decision:** Add a service-layer `TranscriptionBackend` QObject contract with
explicit capability, request, result, progress, runtime-backend, cancellation,
and structured-error data. Keep CPU/Vulkan selection inside a
`LocalWhisperCppBackend` adapter around the existing QProcess wrapper. A
`BackendRegistry` resolves provider-level choices and fails closed to Private
Local when a requested adapter is absent. Persist requested provider,
effective provider, selected local engine, and runtime-proven backend as
distinct fields.

The existing local stage fingerprint remains byte-identical when the local
default is implicit or explicit. Non-local requests include both requested and
currently resolvable effective adapters, so output created by a local fallback
is invalidated if that provider later becomes available.

**Alternatives considered:** Treating CPU and Vulkan as cloud-equivalent
providers was rejected because they share the same executable contract and
canonical output. Putting provider branches directly in `JobController` was
rejected because it couples scheduling to vendor behavior. Replacing
`WhisperWrapper` was rejected because its QProcess, cancellation, and
runtime-backend parsing are already tested. Adding an SDK/dependency in this
phase was rejected because no online adapter is yet enabled.

**Rationale:** The boundary keeps private local behavior and old cache keys
stable while giving later Groq/Gemini work one injectable, cancellable seam.
Capability metadata makes upload/secret behavior auditable before any backend
can be presented to the user.

---

## AD-11: Separate User Study Data from Source-Derived Artifacts (v1.2 Study)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** The Study workspace needs durable slide bookmarks, section
bookmarks, short notes, and a per-job resume position. Writing those values
into `candidates.json`, raw/working transcript layers, or aligned output would
mix user-authored content with source-derived content and make re-export less
safe. The overview also needs to work offline and must not silently introduce
AI-generated claims.

**Decision:** Store user-authored Study state in one atomic per-job
`study.json` file (schema version 1). Derive overview text, topics, key terms,
review counts, duration, and the actually loaded backend from existing job
artifacts on demand. Label deterministic summary provenance in the UI and
keep AI-marked section headings visibly marked. Export Study data with
explicit source-derived and user-authored provenance groups.

**Alternatives considered:** Extending `candidates.json` was rejected because
candidate decisions are source-processing state. Extending transcript
`working.json` was rejected because bookmarks and resume positions are not
transcript edits. SQLite was rejected because per-job atomic JSON is already
the project persistence contract. Generating the overview with a provider was
rejected for this phase because it would add latency, nondeterminism, and a
network/provider dependency outside the approved scope.

**Rationale:** A dedicated user-data layer preserves provenance, permits old
jobs with no Study file to open unchanged, makes restart behavior auditable,
and allows HTML/PDF/JSON exports to include notes without modifying raw
transcript, source metadata, or candidate images.

---

## AD-10: Non-Blocking UI Shutdown and PID-Scoped Process Trees (v1.2 stability)

**Date:** 2026-07-16
**Status:** Accepted

**Context:** Closing Context Repair could wait up to five seconds for a
cooperative network worker, application close did not explicitly cancel the
active controller, and direct `QProcess.kill()` did not guarantee that helper
descendants exited. The UI also displayed requested/capability backends after
a run instead of retaining the backend actually reported by whisper.cpp.

**Decision:**

1. Detach Context Repair workers immediately on owner close, request
   cooperative cancellation, and retain strong ownership in a detached-worker
   registry until each QThread has really finished.
2. Route application close through `JobController.cancel()` before tearing
   down page workers.
3. On Windows, terminate an external-tool tree by the exact root PID returned
   by LecturePack's `QProcess` using `taskkill /PID <pid> /T /F`. Never kill by
   executable/image name. Retain terminate/kill fallback behavior on non-Windows.
4. Persist the backend emitted by whisper.cpp under
   `state.json -> stages -> Transcribe -> backend_used`; prefer that value over
   requested-engine and binary-capability labels when a job is reopened.

**Alternatives considered:** Blocking `QThread.wait()` was rejected because it
freezes close handling. `QThread.terminate()` was rejected for Context Repair
because asynchronous thread termination can interrupt Python/Qt state at an
unsafe point. Image-name process killing was rejected because it can terminate
unrelated user processes. Persisting only the requested engine was rejected
because auto/fallback resolution does not prove which compute backend loaded.

**Rationale:** The selected design keeps the native window responsive, preserves
Qt object lifetime, scopes destructive process action to PIDs LecturePack
created, and makes backend diagnostics auditable across restarts.

---

## AD-9: Adaptive Baseline and Two-Path Slide Detection (v0.4.0)

**Date:** 2026-07-15 (Phase 4)  
**Status:** Accepted  

**Context:** The slide detection engine needs to handle animated builds, transitions, and noise without producing excessive false slide candidates, while ensuring real slides and small persistent additions (progressive builds/handwriting) are correctly captured.

**Decision:** Replace the single-threshold slide change cascade with two explicit detection paths:
1. **Major Slide-Change Path**: Evaluates frame changes against a rolling local baseline of recent frame-to-frame changes. A change is accepted only if it stands significantly above this baseline and stabilizes.
2. **Progressive-Build Path**: Identifies small persistent localized additions using contour analysis on the difference image, filtering out pointer-sized or caption-sized regions, and verifying spatial persistence in subsequent frames.

Expose a single simple sensitivity control ("Conservative", "Balanced", "Detailed") in the UI that internally configures thresholds and window metrics.

---

## AD-8: PyInstaller over Nuitka for Initial Packaging

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The application bundles PySide6, OpenCV-headless, scikit-image, ReportLab, img2pdf, and external binaries (FFmpeg, whisper-cli). Packaging must produce a standalone Windows executable that works on a clean machine without Python installed.

**Decision:** Use PyInstaller in standalone directory mode for initial packaging.

**Alternatives considered:**
- Nuitka: produces smaller binaries and fewer antivirus false positives, but has a steeper setup curve and occasional version-specific regressions with complex dependency sets.
- pyside6-deploy: wraps Nuitka but is semi-experimental with sparse documentation and poor ergonomics. Not recommended for production.
- cx_Freeze: smaller community, requires more manual configuration.

**Rationale:** PyInstaller has the most mature hook system for PySide6 and OpenCV. Its Qt plugin auto-detection reduces the risk of blank-window crashes on clean machines. The GPL-2.0 bootloader exception permits packaging proprietary applications. Nuitka remains available as a future optimization if package size or AV false positives become problems.

**Sources:** nuitka.net, pyinstaller.org, PySide6 packaging docs

---

## AD-7: Self-Contained HTML Study Pack with Base64 Images

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The HTML study pack must work offline without a web server. Browsers block `file://` protocol video seeking (no HTTP Range Request support), so embedded `<video>` with `currentTime` seeking is unreliable for local files.

**Decision:** Generate a single self-contained HTML file with slide images embedded as base64 data URIs. Video timestamp links open the source video in the system default player rather than seeking within the HTML page.

**Alternatives considered:**
- Embedded `<video>` with `file://` src: blocked by browser security policies.
- Local HTTP server: works but adds complexity and violates the Qt-only requirement.
- Electron wrapper: explicitly excluded by the specification.

**Rationale:** A single-file HTML with embedded images is the simplest offline-compatible approach. The video seeking limitation is documented in the study pack header. A future enhancement could use QMediaPlayer within the Qt application for integrated slide-to-video navigation.

---

## AD-6: ReportLab for Study-Pack PDF, img2pdf for Slides-Only PDF

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** Two different PDF outputs are needed: (1) a slides-only PDF containing original slide images with no re-encoding, and (2) a study-pack PDF combining slide images with transcript text, requiring text layout and pagination.

**Decision:** Use img2pdf for the slides-only PDF (lossless image embedding) and ReportLab for the study-pack PDF (Platypus layout engine for mixed image+text content).

**Alternatives considered:**
- WeasyPrint for study-pack PDF: renders HTML/CSS to PDF with automatic pagination, but requires native system libraries (Cairo, Pango, GTK) that are difficult to bundle on Windows and add ~100 MB of dependencies.
- ReportLab for both: possible but img2pdf is more efficient for image-only PDFs (embeds raw JPEG/PNG streams without re-encoding).

**Rationale:** ReportLab is pure Python with no native system dependencies, making packaging straightforward. WeasyPrint's Cairo/Pango/GTK dependency chain is a significant packaging obstacle that could delay Phase 5.

**Sources:** reportlab.com, github.com/josch/img2pdf, courtbouillon.org (WeasyPrint docs)

---

## AD-5: Deterministic CV Pipeline for Slide Detection (No LLM)

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The slide extractor must identify visual slide transitions in lecture videos. Two approaches: send frames to an LLM for analysis, or use deterministic computer vision techniques.

**Decision:** Use a three-stage tiered cascade (dHash fast screen, SSIM confirmation, histogram tiebreaker) with temporal median filtering, stability detection, and preset-specific thresholds.

**Rationale:** Deterministic CV is reproducible, testable, has no external dependency, and runs locally without a GPU-bound LLM. The tiered approach is fast (~80% of frames rejected at Stage 1) and tunable via preset parameters. Full decision metadata is recorded for every frame, enabling post-hoc debugging and threshold adjustment.

**Sources:** OpenCV docs, scikit-image SSIM docs, imagehash library

---

## AD-4: Application-Relative Paths for External Binaries

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The application depends on FFmpeg and whisper-cli executables. These must be reliably located at runtime on any Windows machine.

**Decision:** Bundle binaries in a `bin/` subdirectory relative to the application. Resolve paths using `sys._MEIPASS` (PyInstaller) or project root (development). Never rely on system PATH.

**Rationale:** Eliminates the failure mode where the user has an incompatible system FFmpeg or no FFmpeg at all. Guarantees version compatibility.

---

## AD-3: Plain Files and JSON Manifests (No Database)

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** Job state and metadata must be persisted between sessions and recoverable after crashes.

**Decision:** Use plain files (JSON, PNG, WAV, SRT) organized in a per-job directory structure. No SQLite or other embedded database.

**Rationale:** Human-readable and recoverable without proprietary tools. A user can inspect job state with a text editor. The directory structure is self-describing. Crash recovery can be implemented by checking which output files exist.

---

## AD-2: Per-Stage State Machine with Atomic Writes

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** Processing a lecture involves 8 sequential stages. The application must resume after crashes without repeating completed work.

**Decision:** Track each stage's status (pending/running/completed/failed/cancelled) in `state.json`. Write atomically using temp-file + `os.replace()`. On startup, reclassify any "running" stage as "interrupted" and offer resume.

**Rationale:** Atomic writes prevent corrupt state files. Per-stage tracking enables granular resume. Output files use temporary names during creation and are renamed on completion, so partial files are never mistaken for complete ones.

---

## AD-1: QProcess for External Tools, QThread for Internal Processing

**Date:** 2026-07-15 (Phase 0)  
**Status:** Accepted  

**Context:** The application must remain responsive during long-running operations (transcription, slide detection, export). External CLI tools (FFmpeg, whisper-cli) and internal Python processing (OpenCV frame comparison) both need to run without blocking the UI.

**Decision:** Use QProcess for external CLI tools and QThread with worker objects for internal Python processing. Workers emit progress signals consumed by the UI via Qt's signal/slot mechanism.

**Alternatives considered:**
- `subprocess.Popen` with threads: works but does not integrate with Qt's event loop as cleanly.
- `multiprocessing`: adds IPC complexity; QThread is sufficient since OpenCV releases the GIL during heavy computation.
- QThreadPool + QRunnable: better for many small parallel tasks; not needed for the sequential pipeline.

**Rationale:** QProcess provides non-blocking external process management integrated with Qt's event loop, with built-in `readyReadStandardOutput`/`readyReadStandardError` signals for real-time log capture. QThread workers avoid IPC overhead for internal processing while keeping the UI thread free.

**Sources:** doc.qt.io/qtforpython/PySide6/QtCore/QProcess.html, PySide6 threading guides

---

## AD-19: Signed Repair Manifest Verifier and Release Authority (Phase 1)

**Date:** 2026-07-28  
**Status:** Approved  
**Approval date:** 2026-07-28  
**Approver:** pasttrunks (self-approval; accepted lack of separation of duties)  
**Decision, signing, release, key-custody, backup, rotation, revocation, and
incident-communication owner:** pasttrunks

**Context:** Phase 2 may repair a required runtime only after it can authenticate
an exact, versioned repair release. D-10 requires a documented verifier,
canonical manifest bytes, public-key distribution, asset naming, key lifecycle,
PyInstaller proof, release ownership, and retained evidence. D-11 prohibits
selecting, importing, emulating, or installing a verifier before named-human
approval. The Phase 1 ASCII-staging boundary in AD-18 remains independent of
this release-authentication decision.

**Approved technical contract:**

| Required field | Approved value |
|---|---|
| verifier library and exact version | `cryptography==49.0.0`; verify the official Windows x64 wheel SHA-256 is `e5dfc1e64de5677cec922ffa8da89c546d0415bf6efdf081842e5d44c84e1f0e` before install/use |
| algorithm | pure Ed25519 detached signature over the exact canonical manifest bytes; no prehash, no alternate algorithm fallback, and no parse/reserialize before signature verification |
| public-key encoding | exactly 32 raw octets represented as exactly 64 lowercase ASCII hex characters, no BOM/newline; the future trust root is a compiled-in constant in `lecturepack/infrastructure/release_trust.py`, not a loose resource; rotation requires an app release |
| signature asset encoding | exactly 64 raw binary bytes; no Base64/PEM/DER/JSON wrapper |
| signing key ID | first 16 lowercase hex chars of SHA-256(raw 32-byte public key) |
| manifest schema v1 | fields are `schema_version`, `app_version`, `signing_key_id`, `assets`; each asset has `component`, `file_name`, `sha256`, `size_bytes` |
| canonical manifest bytes | Recursively sorted keys, compact separators, UTF-8 without BOM/trailing newline; assets sorted by component then file_name; duplicates/unknown fields rejected. Verify exact downloaded bytes before parsing. |
| exact GitHub origin | `https://github.com/pasttrunks/lecturepack/releases/download/v{app_version}/` |
| exact release assets | `LecturePack-{app_version}-RuntimeManifest-v1.json`; `LecturePack-{app_version}-RuntimeManifest-v1.json.sig`; `LecturePack-{app_version}-Runtime-ffmpeg.zip`; `LecturePack-{app_version}-Runtime-whisper-cpu.zip`; `LecturePack-{app_version}-Runtime-model-base-en.zip`; `LecturePack-{app_version}-Runtime-smoke-fixture.zip` |
| signing workflow secret | repository-wide GitHub Actions secret `LECTUREPACK_RELEASE_ED25519_PRIVATE_KEY_HEX`, exactly 64 lowercase hex chars for the 32-byte private seed; accepted risk: no environment scoping, so any authorized repository workflow could potentially access it |
| workflow triggers | manual `workflow_dispatch` against an existing `v{app_version}` tag and automatic `v*` tag push; both verify tag, commit, and canonical application version agree before signing |
| signing and release owner | pasttrunks |
| approver | pasttrunks self-approval; accepted lack of separation of duties |
| key custodian and backup authority | pasttrunks only; backup storage is Bitwarden secure attachment/item named `LecturePack Release Signing Key Backup` |
| rotation | trigger-only, no annual cadence; triggers are suspected compromise, maintainer-access loss, key loss, or signing-workflow compromise |
| revocation authority and mechanism | pasttrunks; disable/delete repository secret; cancel signing workflows; remove affected manifests/runtime assets from official releases; GitHub Security Advisory + emergency release notes; generate new key; ship new app with replacement compiled public key; repair unavailable for revoked versions |
| incident communication | pasttrunks; private path: GitHub private vulnerability reporting; public path: GitHub Security Advisory plus emergency release notes |
| frozen proof | build clean PyInstaller onedir from hash-locked dependency; dedicated frozen verifier self-test must load compiled key, accept known-good vector, reject one altered manifest byte; retain executable hash, wheel hash, build log, raw self-test output |
| evidence retention | GitHub Actions artifact ONLY, at maximum retention GitHub permits for the repository; accepted artifact-expiry limitation; no release SigningEvidence.zip and no repository SIGNING.md index |

**Phase 2 gate:** Phase 2 gate opens contractually only after approved tests pass:
the real known-good vector and altered-byte rejection vector must pass, alongside
the complete ADR contract test. This approval authorizes adding
`cryptography==49.0.0` to the two approved requirements files and executing
those vectors, but does not authorize Phase 2 repair implementation, downloads,
a production verifier module, signing workflow, compiled trust module, or frozen
self-test before the later repair phase.

**Alternatives considered:**
- Windows CNG/native bindings: rejected because a supportable Ed25519 verifier
  contract, key import behavior, and cross-version testing would become project-owned
  security surface.
- An external PowerShell or `certutil` verification process: rejected because an
  in-process deterministic verifier avoids shell and availability variability.
- SHA-256 and transport TLS alone: rejected because they do not establish a
  release-signing authority or authenticate a changed manifest.

**Rationale:** Separating technical defaults from named operational authority
keeps the release trust boundary reviewable without pretending that an
unapproved dependency or personal accountability already exists. It also
preserves D-11's fail-closed Phase 2 gate.

---

## AD-20: Beta.11 Cross-Device Rendering Hotfix

**Date:** 2026-08-02
**Status:** Accepted for beta.11 candidate

**Context:** Beta.10 was smooth on the development computer but flickered and
felt laggy on a separate clean-install Windows computer. Starting the affected
packaged app with `--disable-gpu` did not change the symptom, so a GPU-specific
compatibility mode would not be a confirmed fix.

**Decision:** Keep the native window, `QWebEngineView`, `QWebEnginePage`,
`html`, `body`, and `#app` on the same fully opaque active-theme background.
Replace the Demo spotlight's large spread shadow and geometry transitions with
one static translucent scrim plus independently positioned border and arrow.
Throttle only visible processing renders to a 250 ms cadence, coalesce status
and pipeline signals, skip identical snapshots, preserve existing stage/log
nodes where possible, and batch new log rows in a `DocumentFragment` before a
`requestAnimationFrame` DOM write.

**Alternatives considered:**
- GPU flags or runtime graphics detection: rejected because `--disable-gpu`
  did not reproduce a useful improvement and the cause was not confirmed.
- Disabling all animations or adding `will-change` broadly: rejected because it
  changes the product's intentional motion and does not address the confirmed
  expensive spotlight/update paths.
- A visual-testing framework or framework migration: rejected because the
  smallest reliable candidate is a targeted renderer change plus existing
  acceptance tests.

**Rationale:** The fix removes the two confirmed sources of avoidable compositor
and repaint work while preserving the existing design, normal animations,
processing timing, and persistence behavior.

---

## AD-26: Phase 8 Electron Production App Core

**Date:** 2026-08-03
**Status:** Implemented on the development desktop; affected-laptop gate pending

**Context:** The Electron spike and Phase 7.1 transport repair established a
working seam, but the next authorized step is a small real application core.
The product must use the existing HTML/CSS/JavaScript UI, the existing Python
engine, the packaged sidecar, JSONL IPC, and the existing persisted job format.
The first candidate must be testable on the affected laptop before any broader
bridge, installer, updater, or frontend work is approved.

**Decision:** Use `electron-spike/production-main.js` as the production-only
Electron host and `production-preload.js` as its narrow context-isolated IPC
surface. Package the existing UI and engine resources beside a PyInstaller
onedir `LecturePackSidecar.exe`. The host starts the sidecar, performs
`health_check` and job restore, opens a local video picker, forwards processing
options, displays existing sidecar progress/log/slide/transcript events,
exports the existing Study Pack, and requests a graceful shutdown with an
exact Windows process-tree fallback.

The packaged candidate excludes the old launcher, static/mock/diagnostic modes,
demo auto-run, and the historical spike result directories. Those source files
remain in the repository as fallback evidence; they are not production entry
points. The Qt application remains the fallback product shell and is not
removed or rewritten.

**Required first-build contract:**

- Commands: `health_check`, `list_jobs`, `import_video`, `start_job`,
  `cancel_job`, `get_job`, `get_slides`, `get_transcript`, `export`,
  `set_setting`, and `shutdown`.
- Events: `ready`, `bootstrap_progress`, `jobs_changed`, `pipeline_changed`,
  `status_changed`, `log_line`, `slides_changed`, `transcript_changed`, and
  `error`, with the existing UI's `jobs_changed` array shape preserved at the
  renderer boundary.
- Real local processing only: FFmpeg, whisper.cpp CPU, slide detection,
  transcript generation, and Study Pack export.
- Persistence: a completed job must be discoverable and reviewable after a
  second launch against the same data directory.

**Alternatives considered:**

- Continuing the diagnostic launcher: rejected because it cannot be the
  customer-facing real-processing entry point.
- Rewriting the Python engine or converting the UI to React: rejected because
  neither is required for this vertical slice and both expand the risk before
  the laptop gate.
- Removing PySide6 from the sidecar immediately: deferred; the existing
  controller still imports QtCore services, while the sidecar creates no Qt
  window or WebEngine view. Decoupling can follow a passing production gate.

**Rationale:** A production-only host keeps the first build small and
reviewable while preserving the proven engine and UI. The unpacked portable
directory is an acceptance candidate, not yet Beta 15, an installer, or a
release artifact. Beta 15 and additional features remain gated on a fresh-data
run on the affected laptop.

---

## AD-27: Phase 9 Electron Product App and Backend Parity Boundary

**Date:** 2026-08-04
**Status:** Implemented on `luna/phase9-product-app`; affected-laptop gate pending

**Context:** Phase 8 proved the production Electron shell and the real local
processing path. Phase 9 expands that shell to the user-facing queue, import,
settings, study, diagnostics, notifications, export, and Windows release
surfaces while DeepSeek completes Python-side parity in a separate worktree.

**Decision:** Keep the existing HTML/CSS/JavaScript renderer and persisted job
format. Treat `electron-spike/contracts/electron-bridge-contract.json` as the
authority for renderer adapter behavior: implemented operations cross JSONL with
explicit payload mappings, partial operations retain their local handling, and
DEFERRED operations remain local no-ops. Preserve the direct array shape for
`jobs_changed`, plain text for `ai_token`, and ASCII-safe JSONL output from the
sidecar. Package the sidecar with PyInstaller, including the locked runtime
assets and URL-import provider, and produce both a portable ZIP and Inno Setup
artifact from the same unpacked candidate.

The final desktop candidate passed the automated packaged workflow using a
fresh data directory: import, real FFmpeg/whisper.cpp processing, slides,
transcript, Study Pack export, clean close, relaunch, restored job, and no
renderer/bridge/orphan-process failures. The affected-laptop manual gate is
still required before calling the build Beta 15.

**Alternatives considered:**

- Reintroducing Qt or converting the renderer to React: rejected because the
  existing renderer and sidecar seam already provide the required vertical
  slice.
- Forwarding every historical bridge call: rejected because it would violate
  the locked DEFERRED contract and reintroduce unsupported behavior.
- Making the portable ZIP depend on the developer checkout: rejected; runtime
  assets are explicitly supplied to PyInstaller and copied into the candidate.

**Rationale:** An explicit contract and ownership boundary lets Luna and
DeepSeek progress independently while keeping release evidence auditable. A
single packaged candidate is the source for both portable and installer
artifacts, which makes acceptance results and hashes meaningful.

## AD-28: Preserve Phase 9 Queue Envelopes at the Renderer Boundary

**Date:** 2026-08-04
**Status:** Implemented on `luna/phase9-product-app`

**Context:** The Phase 9 queue event intentionally carries the active slot,
queued rows, and schedules together. The Electron sidecar emitted that locked
object, but the existing renderer handler still rejected every payload that
was not a legacy direct array. Study-generation progress was also emitted by
the backend without a renderer subscriber.

**Decision:** Accept the contract queue object in the existing UI while
retaining a direct-array compatibility path for the fallback adapters. Route
implemented `study_progress` checkpoints into the existing quiz/flashcard
progress surfaces, and refresh the authoritative job list after deletion.
Infer a display-only group from a title when no explicit group is persisted;
explicit user groups still win.

**Alternatives considered:**

- Changing the sidecar event to an array: rejected because it would discard
  schedules and the active slot required by the contract.
- Rewriting the queue or study UI: rejected because the existing renderer
  already has the correct screens and persistence behavior.
- Sending theme or deferred updater/runtime operations through JSONL: rejected
  because the locked contract keeps those paths local/no-op for this phase.

**Rationale:** Keeping the envelope intact makes queue state lossless across
  the transport and limits this repair to the renderer-owned compatibility
  layer.

## AD-29: Exclude Nested Build Dependencies from the Electron ASAR

**Date:** 2026-08-04
**Status:** Implemented on `luna/phase9-product-app`

**Context:** The unpacked build source can contain a nested, ignored
`electron-spike/node_modules` or Python `__pycache__` directory left by local
packaging tools. A root-only ignore rule allowed those build-time files to be
copied into `app.asar`, even though the production host does not require them.

**Decision:** Match `node_modules` and `__pycache__` at any relative depth in
the Electron packager ignore predicate. Keep only the production entrypoints
in the ASAR; the sidecar and runtime assets remain explicit extra resources.

**Alternatives considered:**

- Deleting generated build directories before every package: rejected because
  it is destructive and makes the build depend on cleanup state.
- Leaving the nested dependencies in the artifact: rejected because they add
  unneeded customer payload and can expose historical tooling files.

**Rationale:** The package is deterministic from the source tree and excludes
build-only dependencies without changing runtime behavior.

## AD-30: Keep Runtime Recovery Safe When the Packaged Runtime Is Missing

**Date:** 2026-08-04
**Status:** Implemented on `luna/phase9-product-app`

**Context:** The existing renderer's runtime setup overlay calls historical
repair methods directly. The Phase 9 sidecar contract intentionally does not
include an in-place runtime-download operation because the production package
ships a fixed, verified runtime. Leaving those methods undefined would turn a
corrupt or incomplete install into a renderer exception.

**Decision:** Expose the historical methods at the Electron adapter boundary.
`retryRuntimeAssessment` maps to the implemented `health_check` command and
refreshes the bootstrap state. Repair and cancellation return a structured
local result; the renderer presents an explicit reinstall-required state and
never sends an unsupported command to the sidecar.

**Alternatives considered:**

- Adding new runtime repair commands to the sidecar: rejected because it would
  expand the locked contract and duplicate the deferred Qt repair service.
- Leaving the methods undefined: rejected because a missing runtime would
  cause a renderer `TypeError` and provide no recovery instruction.

**Rationale:** A bundled runtime should be repaired by reinstalling the
  verified package in this phase. The adapter remains total and the failure
  path remains clear without crossing the deferred JSONL boundary.

## AD-31: Use a Compatible YouTube Client for Link Import

**Date:** 2026-08-05
**Status:** Implemented on `deepseek/beta15-pc-polish`

**Context:** The supplied public YouTube lecture URL returned “This video is
not available” through yt-dlp's default web client, while YouTube's oEmbed
metadata and the Android player client both resolved it. The Android client
also exposed a combined MP4 format compatible with the existing format
selector. After download, the Electron sidecar's worker-to-import callback was
also being scheduled with a bare `QTimer.singleShot`, which has no event loop
in the worker thread.

**Decision:** Pass yt-dlp's YouTube extractor argument
`player_client=android` for link probes and downloads. Keep the existing
format selector and normal import path unchanged. Schedule the successful
download handoff with the sidecar's main-thread `QTimer` context so the file
becomes a normal queued LecturePack job.

**Alternatives considered:**

- Requiring users to remove URL parameters or use a different YouTube URL:
  rejected because the supplied valid URL should work as pasted.
- Retrying arbitrary YouTube clients or enabling DRM-related paths: rejected
  because it is nondeterministic and would violate the plain-stream-only
  importer boundary.
- Importing the file directly from the worker: rejected because job creation
  touches Qt and the existing engine and must stay on the sidecar event loop.

**Rationale:** A fixed compatible client makes the packaged importer
deterministic for public videos hidden from the default web client, while the
context-bound handoff preserves the existing processing/import contract.

---

## AD-32: Native import paths, pre-job options, and a visible queue

**Date:** 2026-08-06
**Status:** Implemented on `deepseek/beta15-import-queue-fix`

**Context:** Beta 15 packaged feedback showed three workflow gaps. Dragging a
video into the window often did nothing or misreported the video as
unavailable, and valid videos from normal Windows folders (including
non-ASCII paths) could fail through both drag-and-drop and Browse. Balanced/High
and the output choice were not presented at the useful time: once processing
started the user could not meaningfully change them, and the queue gave no
visible order, settings, or controls.

**Decision:**

- Resolve dropped files through `webUtils.getPathForFile` in the preload
  (already exposed) and pass the absolute native path to the sidecar. Browse
  uses the native dialog's absolute path. Both flows converge on one shared
  `importLocalVideo` gate in the Electron host that normalizes, proves
  existence/readability, and forwards the same path to `import_video`; the
  sidecar re-validates and relies on FFprobe rather than a fixed extension
  allowlist. Import failures carry stable codes (`RESOLVE_FAILED`,
  `NOT_FOUND`, `UNREADABLE`, `FFPROBE_FAILED`) that the renderer maps to
  friendly copy; technical paths stay in the production log. The sidecar
  reconfigures stdin/stdout/stderr to UTF-8 and the host sets `PYTHONUTF8=1`
  so apostrophes and Unicode survive the JSONL pipe.
- After import the renderer shows a pre-processing setup panel with
  Processing quality (Balanced/High) and Output (Study Pack / Transcript only /
  Slides only). The chosen options are passed with a job id to `start_job`,
  persisted on the job, locked for that run, and displayed in job details and
  queue rows. The Process screen no longer offers editable options mid-run.
- The queue keeps one active slot. `start_job` either claims the slot (runs
  now) or enqueues behind the running job; completion, failure, and
  cancellation release the slot and the next queued job starts automatically
  (after a bounded worker drain). The queue persists to `queue.json`,
  restores on relaunch, auto-resumes the next queued job after a restart with
  a terminal active slot, prunes terminal jobs so they never render as
  waiting, and renders position, thumbnail, name, options, and status with
  Move up / Move down / Remove controls. The sidecar never re-constructs the
  live job (Job's loader would flip a persisted running state to
  interrupted) and never swaps the controller's job mid-run.

**Alternatives considered:**

- Keeping the renderer's extension allowlist and dialog-only filter: rejected
  because valid containers unknown to the allowlist were rejected even when
  FFprobe could read them.
- Sending a browser File object or a `file://` URL to the sidecar: rejected
  because modern Electron no longer exposes `File.path` and a URL round-trip
  can mangle native paths.
- Building a scheduler with priorities/schedules: rejected because the
  requirement is a simple visible FIFO with one active job.
- Swapping the controller's job at import time while a pipeline runs:
  rejected because it corrupted the running job's persisted state and stage
  marker.

**Rationale:** A shared native-path gate keeps drag-and-drop and Browse
behaviorally identical; pre-job options use the existing backend meanings
(balanced/detailed, study_pack/transcript_only/slides_only) with no new
presets; and the queue reuses the existing persistent `JobQueue` so order and
settings survive restarts without a second scheduler.

## AD-33: Processing job and viewed job are separate; live per-job progress

**Date:** 2026-08-06
**Status:** Implemented on `kimi/job-view-switching-fix`

**Context:** Packaged Beta 15 feedback showed the UI treated the job being
processed and the job being viewed as the same thing. While a new job
processed, Home's card froze at the last stage-boundary percent (43% in the
reported capture), Process kept showing the previously completed job, and the
user could not open an older lecture mid-run. Long real lectures also exposed
that the transcription engine streams segment timestamps but no stage-percent
events, so even Process had no live percent during Transcribe.

**Decision:**

- The renderer tracks the processing job (`LP.state.activeJobId`) separately
  from the viewed job (`LP.state.jobId`, the workspace owner). `active_job`
  events auto-follow a genuinely new processing job once, but never re-yank
  the view after the user opens another job. Job-scoped events
  (`pipeline_changed`, `status_changed`, `log_line`, `slides_changed`,
  `transcript_changed`, `study_changed`, `quiz_changed`, `flashcards_changed`,
  `export_*`) route by `job_id`: the viewed job updates the live workspace;
  any other job accumulates in its per-job store so switching back is current.
  Home cards merge the latest `status_changed`/`pipeline_changed` data by job
  id and patch in place, so progress and completion settle immediately.
- A new `view_job` sidecar command fetches one job's payloads without
  re-pointing `current_job`/`current_stage`, so a completed job can be opened
  while the pipeline keeps running; `_emit_pipeline`/`_emit_study_changed`
  are parameterized by job and never borrow the running job's stage marker.
- A shared Previous/Next source switcher (rendered into Process, Review,
  Transcript, Study, and Exports) selects the adjacent job in the stable job
  list and disables at the ends. The live log gets a Latest button that
  resumes auto-follow after an upward scroll.
- Transcript copy is two explicit actions: "Copy text" (words only) and
  "Copy with timestamps" (each segment with its visible timestamp), using the
  transcript already loaded in the renderer.
- Live Transcribe progress: the sidecar derives a monotonic percent from the
  latest streamed segment's `end_ms` against the known duration (read-only;
  the transcription engine is untouched), and pipeline stages render at most
  one active stage (the explicit current stage), removing the dual-running
  bar artifact at stage transitions.

**Alternatives considered:**

- Letting the backend `active_job` signal keep driving the viewed workspace:
  rejected because `get_job` refuses to swap `current_job` mid-pipeline, and
  re-pointing it would corrupt the running job's events.
- Time-based progress estimation in the renderer: rejected because the
  segment timestamps are the real engine data and belong in the sidecar.
- Modifying the controller to wire whisper progress into `stage_progress`:
  rejected because the objective forbids changing the transcription engine,
  and the segment-derived percent needs no engine change.

**Rationale:** Keeping the two identities separate reuses the existing
per-job workspace store and event stamps; `view_job` adds the one missing
fetch path without touching the pipeline; and the progress changes only read
data the engine already emits, so a long real lecture now shows moving,
consistent progress on Home and Process.

## AD-36: Official Windows candidates fail closed while installed startup degrades only where safe

**Date:** 2026-08-09

**Status:** Implemented on `sol/release-critical-hardening`

**Context:** The integrated Electron candidate could report readiness after
checking only that runtime paths existed. A missing native Study module or
yt-dlp could therefore escape the build, while a missing sidecar, broken
Whisper binary, or unwritable data directory could leave the desktop waiting
without a terminal explanation. Packaging also retained a developer source
tree and allowed an installer-time elevation override.

**Decision:** One ordered packaged-health contract now executes the real
FFmpeg/ffprobe binaries, a real bundled-model Whisper smoke transcription,
data-directory writability, controller initialization, Rust Study Core import,
and yt-dlp import/version checks. The official build fails unless every check
passes and the candidate sidecar re-runs that same contract after packaging.
Installed startup has one 28-second deadline covering spawn, health, and
session restore; every failure enters one terminal screen with Retry, Copy
diagnostics, Open logs, and exact failed-check evidence. Rust and yt-dlp remain
release-required, but an unexpected post-install native load error degrades to
the existing Python Study implementation or a visible disabled Paste Link
action so local-file use is not destroyed. Fatal processing dependencies do
not degrade. Production logs retain only the latest ten sessions, the Electron
package no longer carries the legacy source tree, and Setup is fixed to
per-user installation with no elevation override. Because the bundled
whisper.cpp binaries directly import `MSVCP140.dll`, official builds also
require and deploy that permitted MSVC runtime app-locally; Windows 10's
system UCRT supplies the remaining API-set dependencies.

**Alternatives considered:**

- Treating file existence as runtime health: rejected because it cannot prove
  DLL loading, executable startup, or a real Whisper inference.
- Making Rust or yt-dlp failures fatal after installation: rejected because
  safe local fallbacks already exist and preserve useful offline work; this
  does not relax their official build gate.
- Keeping separate startup, build, and support probes: rejected because their
  verdicts could drift and recreate false readiness.
- Shipping the full Python source tree beside the frozen sidecar: rejected
  because the packaged sidecar is authoritative and the extra copy preserved
  dead resolver paths and unnecessary developer surface.

**Rationale:** Fail-closed candidate creation prevents known incomplete builds,
while bounded, actionable installed behavior preserves recovery and local-file
use when a machine-specific native load fails. A single result schema makes
build evidence, startup gating, and support diagnostics directly comparable.

## AD-35: Study Ask keeps structured prompts and grounded overview answers

**Date:** 2026-08-08

**Status:** Implemented on `luna/study-v1-product-polish`

**Context:** The packaged acceptance run exposed an integration bug at the
Electron/Python boundary: the Study renderer sent Ask as an object, while the
bridge converted the whole object to the literal string `[object Object]`.
The built-in extractor then returned unrelated transcript segments containing
the word "object".

**Decision:** The bridge reads `payload.prompt` when Ask is called with a
structured object. Built-in Ask uses the persisted Study concepts for overview
questions, falls back to early lecture claims when no Study pack is available,
and emits only transcript anchors that exist in the loaded transcript. It does
not expose model/setup language in the student response.

**Alternatives considered:**

- Parsing `[object Object]` in Python: rejected because it hides a renderer
  contract error and cannot recover the student's intended prompt.
- Making every Ask response a generic transcript search: rejected because the
  real acceptance flow needs a useful lecture overview while remaining
  citation-conservative.

**Rationale:** Fixing the payload at the existing bridge boundary preserves
the Study architecture, makes the packaged and source paths agree, and keeps
the response visibly tied to the lecture content the student is studying.

## AD-34: Built-in Study content is claim-led and citation-conservative

**Date:** 2026-08-08

**Status:** Implemented on `luna/study-v1-product-polish`

**Context:** The first real-lecture acceptance run exposed a serious quality
failure in the original deterministic Study path: frequent transcript filler
words became concepts, every card used the same term-definition prompt, and
quiz answers were long, repeated extracts. That made the Study pack look full
without making it useful for exam preparation.

**Decision:** Built-in Study now selects definition-style claims and repeated
subject-matter phrases, removes obvious transcript noise, suppresses narrow
detail phrases and duplicate concepts, creates one retrieval card per concept,
uses varied retrieval prompts, and keeps quiz distractors as compact extracts
from other real lecture claims. Every persisted source reference is still
validated against the actual transcript or accepted slide index. Slide
references use a tight timestamp window so a nearby but unrelated slide is not
presented as evidence. Ask Lecture emits the same real transcript anchors for
the renderer to display as clickable sources.

**Alternatives considered:**

- Generating more items to hit a fixed count: rejected because filler volume
  was the observed failure mode.
- Adding an embedding/NLP pipeline: rejected because simple lexical claim
  filtering and deduplication address the demonstrated problem without
  changing the Study architecture or adding a dependency.
- Treating every nearby slide as supporting evidence: rejected because the
  real lecture showed that section-level proximity can still produce an
  irrelevant citation.

**Rationale:** The content remains deterministic, inspectable, and source
separated while moving the student experience from “term list” toward focused
retrieval practice. When the transcript itself is noisy, the UI exposes the
real source rather than silently presenting an invented correction.

## AD-37: Separate packaged host options from Explorer Send To file arguments

**Date:** 2026-08-10

**Status:** Implemented for the v2.0.0 stable release candidate

**Context:** The final packaged acceptance harness launches LecturePack with
absolute `--results`, `--data-dir`, and Chromium profile paths. The initial
Send To parser previously skipped option names but not their following values,
so those directories could be offered to the media importer as if the user had
sent them from Explorer.

**Decision:** Parse supported value-taking host options as option/value pairs
before collecting absolute file arguments. Keep the pure parser in the existing
`import-path.js` helper so first-launch and existing-instance Send To behavior
can be tested under Node without importing Electron.

**Alternatives considered:**

- Avoiding host flags in release automation: rejected because it would hide a
  real argv ambiguity and make disposable evidence/data isolation weaker.
- Ignoring all tokens after any option: rejected because unrelated Chromium
  switches and legitimate multiple-file Send To arguments can coexist.

**Rationale:** The packaged app now imports only explicit Explorer file
arguments while retaining isolated release profiles and evidence directories.

## AD-38: Persist download recovery state beside job state

**Date:** 2026-08-10

**Status:** Implemented for the v2.0.0 stable release candidate

**Context:** Processing jobs already use atomic JSON state and become
recoverable after a crash, but link-download rows existed only in sidecar
memory. A restart therefore erased waiting, active, failed, and completed
download history and offered no retry path for an interrupted transfer.

**Decision:** Persist the bounded public download queue to
`downloads-state.json` under the selected LecturePack data directory using a
temporary file plus `os.replace()`. On startup, prior waiting/downloading rows
become explicit failed rows with a Retry action; completed, failed, and
cancelled rows retain their terminal state. Retrying restarts through the same
yt-dlp queue and normal import path.

**Alternatives considered:**

- Automatically restarting interrupted network transfers: rejected because a
  restart should not silently resume network work or assume yt-dlp partial-file
  semantics.
- Dropping interrupted rows: rejected because it hides unfinished work and
  defeats the release recovery requirement.

**Rationale:** The existing UI already provides Retry for failed downloads, so
atomic persistence closes the interruption gap without a new scheduler or UI.

## AD-39: Preserve grounded Study output for short factual lectures

**Date:** 2026-08-10

**Status:** Implemented for the v2.0.0 stable release candidate

**Context:** The canonical ten-second Polar Bears demo produced a valid
transcript and two slides, but the claim-led Study filters returned no concepts
because each subject phrase appeared only once and several sentences used
pronouns. The resulting Overview, Flashcards, Quiz, and Quick Study were empty.

**Decision:** When the normal candidate selector returns nothing and the
transcript is at most five segments/eighty words, extract only noun phrases
that occur verbatim as explicit sentence subjects or two-word predicate nouns.
Those candidates still use the existing source validation, exact transcript
extracts, de-duplication, card builder, and quiz builder. Longer lectures remain
on the stricter claim/repetition path.

**Alternatives considered:**

- Special-casing Polar Bears text: rejected because the behavior must work for
  any short factual lecture and must not depend on a demo fixture string.
- Lowering repetition thresholds globally: rejected because it would
  reintroduce filler concepts in normal-length lectures.

**Rationale:** A bounded, verbatim fallback makes short lectures useful without
inventing facts or weakening the quality filters that protect full lectures.

## AD-40: Capture Continue state when navigating Home

**Date:** 2026-08-10

**Status:** Implemented for the v2.0.0 stable release candidate

**Context:** Per-job resume state was captured when switching lectures and on
window unload, but not when a student navigated directly from Transcript,
Review, Study, or Process to Home. The Continue card therefore stayed hidden
during the common same-session workflow.

**Decision:** Before Home changes the active screen, persist the meaningful
workspace screen being left, then render the Continue card after navigation.
Settings and transient surfaces remain excluded by the existing allowlist.

**Rationale:** Continue now reflects the student's last real activity both in
the current session and after relaunch without introducing a second state store.

## AD-41: Stable app tags publish only the Electron release

**Date:** 2026-08-10

**Status:** Implemented for the v2.0.0 stable release

**Context:** The retained `release.yml` workflow builds the historical Qt
desktop installer plus signed runtime-repair archives. Its automatic `v*` tag
trigger used the same `LecturePack-<version>-Setup.exe` asset name as the
validated Electron release. Publishing v2.0.0 would therefore start a second
release path that could replace or conflict with the tested installer.

**Decision:** Keep the signed runtime workflow available through explicit
`workflow_dispatch`, but remove its automatic application-tag trigger. Stable
application tags and assets are published from the Electron release builder
after its packaged self-test, clean-install, negative-path, and updater gates.

**Alternatives considered:**

- Letting both workflows upload similarly named installers: rejected because
  users and the updater could receive an unvalidated legacy UI build.
- Deleting the runtime workflow: rejected because its signed component archive
  procedure remains useful for an explicitly scheduled runtime-repair release.
- Rebuilding the entire Electron runtime in GitHub-hosted CI for v2.0.0:
  rejected for this release because the canonical native runtime and model are
  already locally attested and the CI runner does not contain that frozen input.

**Rationale:** One tag now maps to one validated desktop product. The retained
runtime tooling cannot race or overwrite the Electron installer, while a future
CI migration can replace the manual publication path as a separate decision.

## AD-42: Keep 2.0.1 onboarding and reset state inside existing boundaries

**Date:** 2026-08-11

**Status:** Implemented for the v2.0.1 polish/integration candidate

**Context:** The Electron sidecar already owns the persistent LecturePack data
root and JobQueue, while Electron owns userData and WebEngine session storage.
The renderer-only tour marker could hide a new tour from existing users, and a
generic demo cancel could stop whichever real lecture happened to be active.
Reset also needed to clear both persistence boundaries without following source
paths stored in job manifests.

**Decision:** Store the current/seen guided-tour versions and one of
`not_seen`, `skipped`, or `completed` in the existing atomic `config.json`.
Mark bundled demo jobs with `is_demo`, `bundled_demo`, and a generated
`demo_session_id`, plus a data-root marker for crash reconciliation. Route demo
cleanup through the explicit session/job identity and keep the existing
`JobQueue` as the sole FIFO authority. Expose normalized download aliases while
retaining the sidecar's existing internal state names. Implement reset as an
explicit known-path removal under the canonical data root, followed by clearing
known Electron userData files and WebEngine storage before relaunch.

**Alternatives considered:**

- Inferring tour/demo state from job count, title, or filename: rejected because
  existing users and real lectures are not reliable onboarding markers.
- Adding a second queue, database, or downloader state machine: rejected
  because the current JobQueue and yt-dlp worker already own those lifecycles.
- Deleting the whole data directory or Electron userData recursively: rejected
  because it could remove bundled resources, installed models, or external
  source files referenced by manifests.

**Rationale:** The smallest additions make the current production seams
identity-safe and restartable while preserving the selected local JSON/Qt/
Electron architecture and the existing renderer contract.

## AD-43: Let the sidecar own terminal guided-tour persistence

**Date:** 2026-08-11

**Status:** Implemented for the v2.0.1 polish/integration candidate

**Context:** The merged renderer retains a legacy localStorage marker for the
guided tour while the current renderer/backend contract requires durable
eligibility. A renderer exit can also occur before a demo job exists, so a
cleanup-only hook is insufficient.

**Decision:** The sidecar records only explicit `tour_exit`/`tour_skip` and
`tour_complete` reasons received through `end_demo_job`; operational
cancellation and runtime failure remain retry-eligible. Starting the marked
bundled demo resets only the durable tour offer to `not_seen`, which provides a
safe replay boundary without changing real jobs.

**Alternatives considered:**

- Trusting renderer localStorage: rejected because reset, upgrade, and a
  second profile can disagree with the authoritative persisted state.
- Marking every demo cancellation as skipped: rejected because a failed or
  interrupted demo must remain retryable.
- Adding another tour database/state framework: rejected because the existing
  atomic config and sidecar session marker already provide the needed boundary.

**Rationale:** Explicit reasons preserve the small current command surface and
make the sidecar authoritative even when the renderer's legacy marker is the
only UI-side signal.

## AD-44: Add a packaged state-contract gate beside processing acceptance

**Date:** 2026-08-11

**Status:** Implemented for the v2.0.1 polish/integration candidate

**Context:** The existing packaged processing gate intentionally runs a
bundled demo through completion and then inspects its artifacts. The 2.0.1
demo contract removes that temporary job at its terminal boundary, so that
gate cannot independently prove existing-user eligibility, replay identity,
crash reconciliation, queue idempotency, or reset containment.

**Decision:** Keep the existing processing gate unchanged as a separate
runtime/export signal and add `scripts/polish_packaged_state_acceptance.py`.
It drives the frozen sidecar over the production JSONL protocol with separate
disposable fixtures, uses the real packaged Polar Bears media, records the
external-source and packaged-model hashes, and fails on any state/identity
regression or orphaned sidecar.

**Alternatives considered:**

- Treating the generic processing gate's demo artifact lookup as proof of demo
  lifecycle: rejected because correct cleanup makes that lookup intentionally
  empty.
- Reusing the user's data directory for a richer fixture: rejected by the
  repository safety rules and because it would make reset evidence unsafe.
- Adding a second runtime/queue implementation to make the gate easier:
  rejected; the gate speaks to the existing packaged sidecar contract.

**Rationale:** Separate gates make each acceptance claim observable without
weakening cleanup or contaminating real user state.

## AD-45: Keep packaged readiness and the first-run checklist on one contract

**Date:** 2026-08-11

**Status:** Implemented for the v2.0.1 polish/integration candidate

**Context:** The packaged sidecar returned detailed release-health checks to
the Electron host. That list contains separate ffmpeg/ffprobe and Whisper
smoke records, as well as optional checks, while the renderer's first-run gate
expects exactly five canonical checklist records. The host therefore marked
the runtime healthy and opened the checklist before its rows could receive
their verdicts, leaving the user-facing "You're ready to go" copy above
Pending rows.

**Decision:** Adapt packaged health evidence through the existing backend
`build_first_run_checklist` service, forward the resulting five
`{id, verdict, detail}` records through the sidecar, and consume that field in
both production bootstrap paths. The bridge also groups older raw health
envelopes into the same five records as a compatibility fallback. The waiting
state remains the existing honest checking panel with per-component progress,
a determinate counter, and the existing slower-Whisper notice; no fabricated
percentage or long-running animation is added.

**Alternatives considered:**

- Making the renderer infer groups from raw health checks: rejected because
  backend health ownership already exists and would duplicate verdict logic in
  the UI.
- Showing the checklist heading while verdicts are pending: rejected because
  it communicates readiness before the actionable Done control is valid.
- Adding an indeterminate or decorative progress animation: rejected because
  the startup checks already expose real milestones and an honest count.

**Rationale:** One authoritative checklist reaches the renderer only after
the same checks that establish packaged startup health have completed. The
heading, Ready rows, and Done action therefore appear together, while the
existing progress treatment makes the short local validation wait legible.

## AD-46: Route AI-first Study through a payload-minimizing server gateway

**Date:** 2026-08-12

**Status:** Implemented, deployed, and live-accepted

**Context:** Production Study needs higher-quality lecture analysis, grounded
materials, Ask, Teach Me, and semantic short-answer grading without exposing
provider credentials or provider/model choices in the desktop application.
The approved AI-first Study assignment explicitly introduces this narrow
network boundary; it is an exception to the earlier local-only Study policy,
not a general authorization for telemetry or unrelated network access.

**Decision:** Keep the Electron renderer and Python sidecar provider-neutral.
The desktop sends only task-scoped lecture evidence to the first-party HTTPS
gateway, authenticated by an anonymous installation token. The gateway owns a
fixed task allowlist, server-selected two-to-three-route provider chains,
schema validation, rate limits, safe errors, and payload-free owner alerts.
Its D1 records contain operational metadata only; transcript text, prompts,
responses, and slide images are never persisted by the gateway. The primary
Study build is a two-pass analysis/material flow. Deterministic Basic Study is
available only after an explicit failure or user choice, and never silently
replaces the AI path.

Provider credentials and route selection remain server-side. Provider/model
identifiers appear only inside the student's explicit copied technical
diagnostics and payload-free owner alerts; they are never presented in normal
Study or Settings UI. LecturePack persists only normalized Study artifacts,
provenance, mastery, safe failure diagnostics, and a bounded concept-level
interaction cache in the existing per-job data root. Original videos remain
local and are never read by the gateway client.

**Alternatives considered:**

- Direct provider calls or BYOK in the desktop: rejected because secrets and
  routing policy would ship to every client and create a provider setup UI.
- A bundled local model or vector database: rejected because it changes the
  approved release footprint and is outside this phase.
- One unvalidated provider response: rejected because malformed output could
  cross directly into persisted study state and no route fallback would exist.
- Silent deterministic fallback: rejected because students could believe they
  received the requested AI system when generation had actually failed.
- Storing payloads in D1 for debugging: rejected because lecture evidence is
  not needed for rate limiting or reliability diagnosis.

**Rationale:** One narrow gateway preserves a simple student experience while
keeping secrets, model changes, retries, limits, and provider failover outside
the desktop release. Explicit Basic mode makes failure honest and recoverable,
and the metadata-only server boundary minimizes retained lecture data.

**Initial production deployment record (2026-08-12):** The Worker is deployed at
`https://lecturepack-ai-gateway.discordsammy2.workers.dev` with D1 database
`lecturepack-study-prod` (`0ddaa845-8302-48d9-8fec-7d601f8be82c`). OpenRouter's
`openrouter/free` capability router is paired with the native Workers AI
binding. Workers AI uses `@cf/openai/gpt-oss-20b` for text and
`@cf/google/gemma-4-26b-a4b-it` for selected slide vision. Long-form material
generation puts Workers AI first; other tasks keep OpenRouter first. Identical
same-provider routes are de-duplicated, and bounded route deadlines fit inside
the desktop's 175-second request deadline. AD-47 supersedes this initial
route/model snapshot while preserving the same gateway, D1, and privacy
boundary.

The live packaged Polar Bears gate passed canonical analysis, selected vision,
bounded optional web context, material generation, Ask, Teach Me, semantic
grading, explicit Basic Study, anonymous registration, packaged-default URL,
clean exit, and no-orphan checks. A controlled invalid OpenRouter route also
proved that Workers AI succeeds as an independent fallback. The remote D1
schema was inspected after these calls and contains identifiers, counts,
latency, route/model, status, and token/character totals only—no lecture text,
prompt, completion, or image columns. Native/Resend email delivery remains
disabled because this account has no managed sender domain; alert failure is
intentionally non-blocking and does not affect Study requests.

**Official provider/platform contracts checked 2026-08-12:**

- OpenRouter structured outputs:
  `https://openrouter.ai/docs/guides/features/structured-outputs`
- OpenRouter free router:
  `https://openrouter.ai/docs/guides/routing/routers/free-router`
- OpenRouter web-search server tool:
  `https://openrouter.ai/docs/guides/features/server-tools/web-search`
- Cloudflare Workers AI bindings and JSON mode:
  `https://developers.cloudflare.com/workers-ai/configuration/bindings/` and
  `https://developers.cloudflare.com/workers-ai/features/json-mode/`
- Cloudflare Workers Web Crypto, D1 Worker API, and rate-limit bindings:
  `https://developers.cloudflare.com/workers/runtime-apis/web-crypto/`,
  `https://developers.cloudflare.com/d1/worker-api/d1-database/`, and
  `https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/`

---

## AD-48: The guided demo is a self-contained screen with pre-baked real output

**Date:** 2026-08-12
**Status:** Implemented

**Context:** The guided demo was a spotlight overlay that pointed at the live
application UI. Eight distinct bugs were found and fixed in it across a full
session — overlapping scrim rectangles, a step targeting markup Study V2 had
superseded, a full-width flex row measured as if it were a control, a step
precondition running inside the per-frame measure path (which reverted the
user's clicks within a frame and made buttons look dead), a coach card covering
its own subject, the prominent entry button not starting the tour at all — and
the result was still not usable. The premise was the defect, not the execution.

A tour that measures the live UI at runtime is a second renderer for the app's
layout. It must independently know where everything is, which mode it is in and
what is about to move. Every one of those eight bugs was that coupling failing,
and the class is unbounded: any layout change anywhere can break it silently,
as Study V2 did. "Must work 100% of the time" and "measures the live UI at
runtime" are incompatible requirements.

**Decision:** The demo is its own screen (`data-screen="demo"`), registered like
Home or Review. It measures nothing, mutates nothing outside its own section,
and has no scrim, spotlight, anchoring or z-index band. Five chapters swap with
`[hidden]`.

It shows **pre-baked real output** of the bundled Polar Bears lecture, shipped
as `app/assets/demo/demo.data.js` plus real slide PNGs extracted at the
timestamps the detector actually selected. It is real output, simply not
recomputed.

The real pipeline runs **after** the walkthrough, from an explicit "Process this
lecture for real" button.

**Alternatives considered:**

- Keep fixing the spotlight tour: rejected. Eight fixes did not converge, and
  each only removed one instance of an unbounded class.
- Have the demo run the pipeline live: rejected. It needs ffprobe and a Whisper
  model, takes tens of seconds and can fail — and a failure there reads as the
  *product* failing, on a first impression. Constraint 5 was its own answer.
- Ship the data as `demo.json` loaded with `fetch()`: rejected after testing.
  The renderer is loaded via Electron's `loadFile`, i.e. `file://` with web
  security on, where `fetch()` of a sibling file is blocked. This version
  silently degraded to the fallback on *every* launch, packaged included. A
  `<script>` tag has no such restriction.
- A union hole spanning several disjoint elements: rejected earlier; four-rect
  tiling expresses exactly one rectangle. Moot now — there is no hole.

**Rationale:** The number of ways the demo can break drops from unbounded to
one — a missing bundled asset — and that one has a designed fallback per
chapter. It also removes the pipeline, the network and the AI gateway from the
first-run path entirely, so the demo works offline and before any provider is
configured.

**Consequence:** the demo no longer teaches where the Review controls are. That
is deliberate: the value proposition is what the app produces, not where its
buttons live, and chrome is learned in seconds by using it.

---

## AD-49: Waiting, slide review, and demo state must represent one real system each

**Date:** 2026-08-12

**Status:** Implemented

**Context:** Live evidence showed the Study preparation panel at `0%` while the
lecture pipeline was still detecting slides. No Study stage existed yet, so an
eight-row idle checklist and an AI elapsed clock falsely implied that Study AI
had started and stalled. Review also exposed a Grid/List choice inside a
250-pixel rail where the grid could resolve to only one column, while accepted
selection received a louder full-card fill than the export-changing rejected
state. Finally, AD-48 made the old live-screen spotlight renderer unreachable,
but its geometry, focus, animation, and test contracts remained in production.

**Decision:** Treat lecture processing, Study AI preparation, slide navigation,
and the walkthrough as separate presentation systems with explicit boundaries:

- When Study has no generation stage, render one honest waiting row. While the
  lecture pipeline is active it says that Study is waiting for transcript and
  slides; otherwise it says Study AI is starting. Hide the AI progress bar and
  source list, and do not start the Study elapsed clock until a real stage is
  received.
- Keep Review's narrow slide rail as a list. Its Compact/Roomy control changes
  density only. Put the actual deck grid in a full-window **All slides** dialog
  using `repeat(auto-fill,minmax(168px,1fr))`.
- Encode accepted selection as an unfilled checkbox, rejected as the loud red
  state, and the slide currently being viewed as an orange outline. Keeping a
  slide updates both its accepted state and selected flag immediately.
- Delete the unreachable spotlight renderer, scrim geometry, focus trap,
  lifted-card animation, and the tests that specified them. Keep only the
  provider-neutral demo eligibility contract and the identity-safe real-demo
  session reducer. Reset terminal cleanup guards when starting a new demo
  attempt so a second run can still be stopped safely.

**Alternatives considered:**

- Show the full Study checklist at `0%`: rejected because it assigns lecture
  work and elapsed time to an AI task that does not yet exist.
- Hide Study entirely until the lecture finishes: rejected because an explicit
  waiting state explains what will happen next and confirms the request was
  accepted.
- Keep Grid/List in the rail with smaller cards: rejected because shrinking
  cards does not create useful deck-level scanning in that width.
- Tint every accepted slide card: rejected because acceptance is the normal
  state; rejection and current viewing carry more decision value.
- Leave unreachable tour code for old tests: rejected because those tests made
  deleted behavior an accidental maintenance contract and allowed the second
  renderer to return.

**Rationale:** Every visible progress indicator now belongs to work that has
actually started, every slide control has a layout capable of expressing its
label, and the first-run walkthrough has one renderer rather than two. The UI
therefore communicates backend state without inventing activity and keeps the
highest-consequence review state visually loudest.
