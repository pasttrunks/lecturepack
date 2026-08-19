# Changelog

All notable changes to LecturePack are documented here, newest first.

> **A note on the older version numbers below.** Entries are in reverse
> chronological order, but the version numbers are not monotonic: the
> `0.9.0-beta.*` series (July–August 2026) came *after* `1.0.x`/`1.1.0`
> (July 2026). The project renumbered to a `0.9.0-beta` line while preparing
> the first public beta, then shipped stable as 2.0.0. Nothing below has been
> removed; only this explanation was added.

## [2.0.7] — 2026-08-19

**Lectures actually process now.** Everything in 2.0.6 is included.

Two separate faults, both of which ended with nothing happening.

Pressing Start on a lecture already in your library did nothing: the part of the
app that runs the pipeline was never told which lecture to work on, so it stopped
immediately. Only freshly imported videos worked, which is why it went unnoticed.

And anything that reached the queue stayed there. The queue was only ever emptied
when some *other* lecture finished, so with nothing already running there was
nothing to trigger it — a queued lecture sat at "Queued" while the app sat at
Idle, indefinitely. Queue a lecture now and it starts.

**Dragging lectures around works, and lands where you'd expect.** Drop a lecture
on a subject to file it there. Drop it on the queue to line it up behind what is
already waiting. Drop it on nothing and it says so and flies back, instead of
silently doing nothing. Dragging near the edge of a long library scrolls, so you
can reach your target without letting go. Grab a card anywhere that isn't a
button, or use the six dots in its corner.

The queue is only on screen when it is actually holding something, and Process is
no longer a drop target — dropping a lecture onto a sidebar tab never explained
itself.

**Reprocessing still asks first.** Dropping a finished lecture on the queue warns
you that its slides, transcript and Study pack will be replaced before anything
happens.

New in this release:

- Queued lectures have a ▶ button to start them right away, instead of having to
  reorder the queue and wait.
- In Review, arrow keys move between slides, `J` keeps, `K` rejects, and `Space`
  keeps and moves on — so a deck can be triaged one-handed. The buttons work
  exactly as before.
- Slide thumbnails magnify under the pointer while you scan the filmstrip.
- Slide counts roll instead of jumping, and the footer shows a moving bar while
  a lecture is processing.
- Cards tilt as you drag them and land with a stamp.

If you turn off animations in Windows, all of the above holds still — colours
still tell you what happened, nothing moves.

## [2.0.6] — 2026-08-17

**Dragging a video into LecturePack works again.** Everything in 2.0.5 is
included.

Dropping a file did nothing at all — no import, no error, no message. The code
that starts the import could not be reached from the code that handles the
drop, so every drop failed instantly and silently. Dropping a lecture now
imports it, from any folder, including OneDrive.

If drag and drop has never worked for you, this is why. Use 2.0.6.

## [2.0.5] — 2026-08-17

Drag and drop, and deleting lectures. Everything in 2.0.4 is included.

### Dragging
- **Dragging scrolls the list.** A drag that began at the bottom of a long
  library could never reach the Process tab — the mouse button is held down, so
  there was no way to scroll, and letting go to scroll ended the drag. Dragging
  near the top or bottom edge now scrolls, including when you hold still, and
  it works inside the Process queue panes too.
- **The scroll always stops with the drag** — on drop, on moving away from the
  edge, on Esc, and when the drag leaves the window.

### Deleting a lecture
- **Deleting the lecture that is currently processing now works properly.**
  LecturePack stops the work and waits for it to finish letting go of the files
  before removing anything, instead of deleting the folder out from under it.
- **A deleted lecture leaves the queue.** Its queue entry and any schedule went
  on existing after the lecture was gone.
- **The screens update immediately.** Deleting the active lecture used to leave
  Home, Process and Review still showing it.
- **A deleted lecture cannot come back.** Work that was already in flight when
  you deleted it can no longer re-add the lecture to your library.

### Updating
- **The update dialog and the Download and Install button work.** The dialog
  showed a blank version and "No release notes", the progress read
  "Downloading update… NaN%", and the Updates settings answered "Updates are
  not available in this build." All fixed; this is the 2.0.4 work reaching you.

### Build
- Signed: **no.** No Authenticode credentials exist for this project, so
  Windows will warn on first run. Every download is still verified against a
  published SHA-256.

## [2.0.4] — 2026-08-16

Fixes the update experience itself. Everything in 2.0.3 is included.

### Updating
- **The update dialog shows what you are getting again.** It read
  "v2.0.2 → v" with "No release notes", because the update details never
  survived the trip to the window. It now shows the new version, the download
  size as "372.7 MB" rather than a raw byte count, and the release notes.
- **Update status messages work at all.** "Checking…", "You're up to date",
  "Downloading", "Verifying", "Ready to install" and every update error were
  silently doing nothing, for the same reason.
- **Installing an update no longer fails silently.** LecturePack started the
  installer and then closed itself. Windows cannot replace a program that is
  still running, so the installer could fail with nothing installed and no
  message — you would reopen on the old version as if you had never clicked.
  The installer now starts only after LecturePack has fully shut down.

### Build
- Signed: **no.** No Authenticode credentials exist for this project, so
  Windows will warn on first run. Every download is still verified against a
  published SHA-256.

## [2.0.3] — 2026-08-16

A polish release: fourteen reported defects fixed, plus five more found while
verifying them in the real app. No new features.

> **Upgrading from 2.0.2 or earlier fixes a broken link import.** Until now the
> installer only ever added and replaced files, never removed them, so files
> from older versions accumulated. On this upgrade those leftovers stopped
> yt-dlp loading, which disabled importing from a link. The installer now
> clears the payload it re-ships before installing. Your lectures, study
> progress and settings live outside the app folder and are untouched.

### Study — a subject is now actually studyable
- **Marking a concept Mastered from a subject sticks.** Setting mastery in
  subject scope appeared to work and then reverted, and the subject progress
  bar stayed at 0% no matter how much you marked. Subject scope now reads
  progress from the lecture each concept came from, which is where it was
  already being saved.
- **Concept actions work from a subject.** Mastery, Teach Me, Edit, Regenerate
  and Delete all failed with "concept not found" when used from a subject,
  because they addressed the lecture in the switcher rather than the one the
  concept belongs to.
- **They also say so when they cannot.** A rejected action used to do nothing
  quietly — most seriously, a confirmed Delete that deleted nothing. Every
  concept action now reports failure, and refuses outright when it cannot tell
  which lecture a concept belongs to rather than guessing.
- **Choosing one lecture from a subject shows that lecture.** It previously
  cleared the Study panel and left it empty.
- **A renamed subject is renamed everywhere**, instead of leaving the old name
  in the Study heading.

### Export
- **"Export again" re-exports.** It used to reset the banner and write nothing.
- **"Export PDF" and "Export HTML" do something and say so.** They were silent
  no-ops. Both rebuild the study pack — the format is not yet exported on its
  own, and the app now says that plainly instead of implying otherwise.

### Fixed elsewhere
- Slide timestamps in Review no longer show a doubled millisecond
  (`00:01:12.000.500`).
- Subject cards show `2:48`, not `168.321451`.
- A malformed link in Import now gets a visible error instead of silence.
- The Process screen's output mode no longer looks clickable when it is not,
  and now reflects the mode the lecture was actually imported with rather than
  always showing Study Pack.
- Citations and Study Stats are no longer clipped at the bottom of the panel.
- "1 lecture updated", not "1 lectures updated".
- The sidebar storage line no longer wraps "free" onto its own line.
- README documents the 13 files an export actually writes.

### Known limitations
- A concept taught in several lectures records mastery against the first one.
- "Export PDF" and "Export HTML" rebuild the whole study pack rather than that
  one file.

### Build
- Signed: **no.** No Authenticode credentials are available for this project, so
  Windows will warn on first run. The updater verifies every download against a
  published SHA-256 regardless.

## [2.0.2] — released 2026-08-15

Study a whole subject, not one lecture at a time. Built on the 2.0.1
hardening pass, which is included in full.

### Group study — revise a subject as one thing
- **Lectures can belong to a subject.** Lectures can be grouped, renamed and
  tracked for progress from a new Subjects screen, individually or in bulk.
- **A cross-lecture map.** Studying a group builds one map over every ready
  lecture in it: which concepts are the same idea taught more than once, which
  build on an earlier treatment, what runs through the whole subject, and where
  the lectures leave a hole. Study gains a group scope header, a lecture
  switcher and citations that cross lectures.
- **It is a reduce over work already done.** Each lecture stores its own
  analysis when processed, so a group of ten costs one request over ten small
  summaries, not ten transcripts read again. The map is cached against the
  exact set of lectures it was built from, so adding or reprocessing a lecture
  rebuilds it and studying the same group again is free.
- **A group studies what is ready.** A lecture still processing, or whose pack
  failed, is simply absent from the map, which rebuilds when it arrives.

### Gateway
- **Google AI Studio (Gemini) added as a provider and route.**
- **An admin dashboard**, with usage metrics storage behind an authenticated
  endpoint. The dashboard itself is static HTML; every data endpoint requires
  `ADMIN_API_KEY` and fails closed when it is unconfigured.

### Fixed
- **Group study could not work at all.** The cross-lecture map is returned by the
  gateway inside a `result` envelope, which was never unwrapped, so a correct
  answer was discarded and studying a subject always reported that it had no
  material. The production gateway was also missing the route entirely. Both are
  fixed and the path is now verified against the live gateway (BUG-43).
- **Subjects screen.** The mastery percentage was rendered twice per card; an
  ordinary subject name such as "Microeconomics" could break mid-word because the
  Study button crowded it; a long subject name wrapped to five lines and stretched
  its whole row; and the header restated itself over the title.
- **Gateway admin dashboard.** The admin key is no longer accepted from the query
  string, where it would reach access logs and referrers, and the key comparison is
  now constant-time.

### Tests
- The Milestone 3 adversarial suite was passing on fixtures that did not
  exercise the product — a hand-rolled study-content filename, an unknown
  status string that normalised to "ready", and the wrong IPC wire key. See
  BUG-42. It now drives the real packaged binary.

## [2.0.1] — unreleased

Release-hardening pass over 2.0.0. No feature changes.

### Updater — fixed a fail-open path (security)
- **An unverified installer can no longer be installed.** If the release
  manifest was missing, unavailable, malformed, or carried no valid digest,
  the updater previously fell through to `expectedSha256 = null`, skipped
  verification entirely, and reported the download as ready to install.
  Verification is now a single fail-closed gate: the manifest must parse, its
  version must equal the selected release, platform must be `win32`,
  architecture `x64`, and it must contain an entry whose filename exactly
  matches the installer being downloaded, carrying a valid SHA-256. Any
  failure refuses the update, deletes what was downloaded, leaves the
  installation untouched and explains why. There is no "proceed anyway" path.
- **A digest published for a different `Setup.exe` is no longer accepted.**
  The unbound top-level `sha256` / `installer_sha256` shortcuts are gone;
  digests must be bound to the exact installer filename.
- **Installers stream to disk instead of into memory.** A ~350 MB download is
  written to `<name>.tmp` while being hashed incrementally, and promoted only
  after the digest matches. Network errors, timeouts, cancellation and
  checksum mismatches all remove the partial file.
- **Cancel now cancels.** `cancel_update_download`, `skip_update_version` and
  the channel selector previously did nothing. Cancellation is real
  (AbortController), skip persists and expires when something newer ships, and
  the auto-check preference is honoured.
- **Removed the fake Beta/Stable channel selector.** LecturePack 2 ships one
  stable channel.
- **Removed a false claim.** "The update will install when it is idle" is now
  "Update ready. Finish current processing, then install and restart."
  LecturePack never restarts itself when background work finishes.

### YouTube link import — fixed
- **Bundled a JavaScript runtime.** Modern yt-dlp cannot fully extract YouTube
  without one; 2.0.0 shipped yt-dlp alone and its self-test still reported
  "available", which only proved the import succeeded. Measured on the shipped
  configuration, extraction returned 11 formats without a runtime versus 14
  with one. LecturePack now bundles Deno 2.9.5, pinned and checksum-verified
  at build time, plus `yt-dlp-ejs` including its solver JavaScript.
- **Nothing is downloaded on first use.** Remote component fetching is
  explicitly disabled; everything ships in the installer.
- **yt-dlp is given LecturePack's own FFmpeg**, so merges no longer depend on a
  system FFmpeg the user does not have.
- **Health diagnostics split** into `yt_dlp`, `yt_dlp_ejs` and `js_runtime`
  instead of one conflated boolean, so a degraded build is visible.

### Windows integration
- **Explorer "Send to → LecturePack" now exists.** The app already accepted
  file paths and forwarded them to a running instance; the installer now
  creates the per-user shortcut that hands it those paths. Removed on
  uninstall. The source lecture is only ever read.

### Release engineering
- **One authoritative desktop release path.** The legacy workflow built the Qt
  PyInstaller app and published it as `LecturePack-<version>-Setup.exe` — the
  same name the Electron path uses — making the published installer ambiguous.
  It is renamed to `release-runtime-repair.yml`, can no longer compile an
  installer, and fails closed if any desktop asset appears. The new
  `release-electron.yml` is the only workflow that may publish the four
  desktop assets.
- **Signing order corrected.** Final hashes and the updater manifest are now
  generated from the signed installer, never before signing.
- **Version surfaces fail closed** when `version.py`, `package.json`,
  `package-lock.json` and `lecturepack.iss` disagree.
- **Official builds use a pinned dependency set** (`requirements-release.txt`).

### Security
- **Renderer window creation is denied.** Added a `setWindowOpenHandler`
  policy; only `https:` links are handed to the system browser through the
  existing trusted path. Context isolation, sandboxing, disabled Node
  integration and the navigation block are unchanged.

### Documentation
- Rewrote `README.md`, which still described the 0.9.0 beta and named Qt
  Widgets as the production UI.
- Corrected `THIRD_PARTY_NOTICES.txt`: it was headed "v0.2.0", listed img2pdf
  as GPL-3.0 when it is LGPL-3.0, and omitted Electron/Chromium, Deno, yt-dlp,
  yt-dlp-ejs, cryptography, Send2Trash, tzdata, pikepdf and the Rust Study
  Core. Added an authoritative "shipped in 2.x" component list.
- Documented actual network behaviour: update checks, user-initiated link
  imports, and optional user-configured AI endpoints. No telemetry.

## [2.0.0] — 2026-08-10

First stable release. Windows 10/11, 64-bit.

### The product
- **Electron production UI.** Replaces the previous PySide6/Qt Widgets shell as
  the shipped interface. Qt is retained only as a dependency of the packaged
  Python processing service.
- **Nothing else to install.** Bundles FFmpeg and FFprobe, whisper.cpp with the
  `base.en` model, the Rust Study Core, and yt-dlp. No Python, Node, Rust,
  FFmpeg or model download required, and no first-run setup step.
- **Study V2** — study overview, flashcards, quizzes, grounded "Ask" answers
  that cite the transcript passages they came from, Quick Study and Needs
  Review, with scheduling and mastery in a native Rust engine and a Python
  fallback.
- **Import and queue** — multi-file and folder import, background and tray
  processing, live progress and ETA, session/window restore, and crash
  recovery for jobs and downloads.
- **Exports** in 13 formats.
- **Stable-channel updater** with SHA-256 verification.

### Distribution
- Per-user installer (no administrator rights) and a portable ZIP.
- Every release publishes `SHA256SUMS.txt` and a release manifest.
- Binaries are not Authenticode-signed; Windows may show a SmartScreen
  warning.

### Release evidence
- Python suite: 1,350 passed, 1 skipped, 0 failed.
- Rust Study Core: 11 passed.
- Packaged UI acceptance: PASS (29 checks, 11 screenshots).
- Per-user installer acceptance: PASS.
- Development-host negative matrix: PASS.
- Microsoft Defender final-kit scan: zero detections.

## [0.9.0-beta.13] — 2026-08-03

### Rendering — reliability-first across all machines
- **CPU-first rasterization by default.** `app/desktop/main.py` now defaults the
  WebEngine renderer to `--disable-gpu-rasterization` (CPU rasterization on top
  of GPU compositing). Every page tile is fully rasterized before it is
  presented, so the unfilled-tile "flicker" seen on weak or freshly-imaged
  laptop GPUs cannot occur. Page paint is slower on low-end hardware — the
  accepted trade for a flicker-free UI on any PC.
- **Per-machine override.** Set `LECTUREPACK_RENDER_MODE` before launch to pick
  a rendering mode without rebuilding:
  - `safe` (default) — CPU rasterization + GPU compositing; no tile-hole flicker.
  - `auto` — let Chromium decide (fast on good GPUs, may flicker on weak ones).
  - `software` — fully software rendering (`--disable-gpu`); most deterministic.
  - `gpu` — legacy forcing of GPU rasterization (fast on good GPUs, may flicker).
- No overlay CSS or guided-tour compositing was changed; beta.11's opaque
  surfaces, static scrim, and 4 Hz processing coalescing are unchanged.

### Diagnostics (unchanged from beta.12)
- Guided-tour flicker trace still available with `LECTUREPACK_TOUR_TRACE=1`,
  forwarding overlay hidden writes / mutations / frame timestamps to local
  stderr and the UI log. For the laptop acceptance matches, run with this on
  and compare `safe` vs `software` vs `gpu` modes.

## [0.9.0-beta.12] — 2026-08-02

### Fixed
- **Warm-start interactivity:** release the app from inert mode when the
  acknowledged runtime overlay was never opened.
- **Startup progress recovery:** replay the newest bootstrap state for each
  checklist component when the UI becomes ready, so late subscribers do not
  remain at 0 of 5.
- **Runtime setup flash:** keep a hidden checking state off-screen for 600 ms
  before opening the setup overlay, while preserving the full overlay for
  genuinely slow checks.
- **Empty startup surface:** show a themed native “LecturePack · starting…”
  placeholder until the WebChannel UI is ready to accept input.

### Diagnostics
- Add opt-in guided-tour flicker tracing with
  `LECTUREPACK_TOUR_TRACE=1`, routed through the local stderr/log sink. The
  trace records overlay hidden writes, overlay mutations, and frame timestamps;
  it does not change overlay CSS or claim a compositing fix.

## [0.9.0-beta.11] — 2026-08-02

### Fixed
- **Cross-device rendering reliability:** keep the Qt window, WebEngine view,
  WebEngine page, and DOM surfaces on one fully opaque active-theme background.
- **Demo spotlight cost:** use one static translucent scrim with separately
  positioned border and arrow geometry; retain the existing tour motion and
  card design without animated full-window effects.
- **Processing repaint pressure:** throttle visible stage, status, progress, and
  log updates to at most four batches per second, skip identical snapshots, and
  update existing stage/log nodes in place.

## [0.9.0-beta.10] — 2026-08-02

### Fixed
- **Packaged visual reliability:** added a real Windows-window acceptance gate
  covering cold launch, setup, Demo overlays, navigation, resize, themes, real
  video processing, idle, and reopen.
- **Demo processing spotlight:** remeasure the guided-tour border after live
  pipeline DOM growth so its border and arrow remain aligned.
- **Runtime reopen overlay:** close the stale checking overlay after an
  acknowledged healthy bootstrap without changing the first-run checklist or
  motion behavior.
- **Release trust fixtures:** update stale test fixtures and verify the pinned
  cryptography wheel hash without weakening signature or archive checks.

## [0.9.0-beta.9] — 2026-08-01

### Fixed
- **Theme and startup flashing:** theme state now applies at the document root,
  synchronizes the native/WebEngine backgrounds, installs the view before page
  load, and avoids a document-level scrollbar toggle.
- **Runtime setup overlay:** unchanged frames reuse their DOM rows and exit
  through the existing motion helper instead of rebuilding/focusing repeatedly.
- **Processing updates:** pipeline renders coalesce to animation frames,
  duplicate integer progress is suppressed, and live status dots keep their
  animated DOM nodes while labels change.

## [Unreleased]

### Changed
- **`LECTUREPACK_DATA_DIR` environment override** for the data root. When set, it
  overrides the default `~/LecturePackData` and any persisted `data_directory`
  setting, so packaged-GUI acceptance and install-over-upgrade testing can run
  against a disposable profile without mutating real jobs. Precedence: explicit
  argument > `LECTUREPACK_DATA_DIR` > default root; blank/whitespace is ignored.

## [0.9.0-beta.3] — unreleased

Reliability, queueing, scheduling, notifications, and polish. Beta.3 retains the
bundled zero-setup local engine from beta.2.

### New
- **Persistent processing queue** — one active job at a time; additional jobs
  queue FIFO with reorder, Run Now, and remove. Survives restart.
- **Local scheduling** — schedule a lecture for a local date/time with a
  missed-schedule policy (run when the app next opens / skip / ask). No Windows
  service and no cloud scheduling; a schedule due while the app is closed is
  handled at the next launch.
- **Safe checkpoint-based pause & resume** — cooperative pause finishes the
  current step (or cleanly stops a restartable stage), preserves completed work,
  and resumes from the last valid checkpoint; survives an app restart. No unsafe
  process suspension.
- **Windows notifications** for processing complete, processing failed, and
  update available (focus-aware, de-duplicated, with click-through). Only while
  the app is open or minimized — nothing is sent when it is fully closed.
- **Windows taskbar progress**, and **keep-awake while processing** (display may
  still sleep; manual sleep/shutdown is never blocked).
- **Better completion panel** (real duration / word / segment / slide metrics)
  with Open Transcript, Review Slides, Start Studying, and folder shortcuts.
- **Stage-specific retry** that preserves completed upstream work.
- **Redacted diagnostics** (never include keys, credentials, or transcript text).
- Smoother animations that respect the OS **reduce-motion** setting.

### Reliability
- Fresh installs start with no stale jobs (packaging clean-state gate).
- Old-session `running` jobs are reconciled to **Interrupted** at startup and
  leave the active Home/Processing views, with Resume / Restart / View / Remove.
- Per-launch session ownership so reconciliation never clobbers a live job.
- Orphaned-running-job reset; frozen-EXE icon fix; Study Packs badge fix (from
  the post-beta.2 fixes).

## [0.9.0-beta.2] — 2026-07-23

Packaged-engine hotfix for beta.1's clean-machine failure.

### Fixed
- Bundled the complete CPU whisper runtime in the installer (ffmpeg, ffprobe,
  whisper-cli, whisper/ggml DLLs, and the `ggml-base.en.bin` model) and fixed
  frozen-mode binary path detection, so transcription works out of the box with
  no Python, GPU, or external tools.

## [0.9.0-beta.1] — 2026-07-21

First **public beta**. The core lecture workflow works immediately after
installation — no account, no API key, no Ollama, no separate model download.

### Core (works out of the box)
- Local transcription, slide extraction + review with a readable full-size
  preview, transcript viewer/editor, exports, notes, bookmarks, grouped
  lectures, and safe delete-to-Recycle-Bin.
- **Built-in Study** always works with no local AI: deterministic grounded
  quizzes and flashcards, plus a transcript-grounded, source-linked "Ask"
  that cites timestamps. Study controls are never dead when Ollama is absent.

### Smart Study (optional, private, local)
- One-action setup detects Ollama, offers two named presets —
  **Lightweight Study** and **Balanced Study** (recommended) — with a simple
  RAM-based recommendation, downloads the model with progress + cancel, runs a
  structured test request, and persists the choice. Raw model IDs and the
  endpoint live under **Advanced AI details**. If Ollama is missing, the app
  opens the official Ollama download page (it never downloads or runs a binary
  itself).
- Clear provider labels everywhere: **Built-in Study / Local AI / Online
  Enhanced**.

### Online transcription (optional)
- Groq **Online Fast** / **Online Accurate** modes with the key stored only in
  Windows Credential Manager. Online modes stay disabled until a key is set.

### Release
- Versioned `0.9.0-beta.1`; pre-release tags publish as GitHub pre-releases
  with installer + portable ZIP + SHA256SUMS. Installer preserves
  `LecturePackData` across upgrades and never deletes user lectures.

## [1.1.0-ui-speed-ollama] — 2026-07-16

Speed, a redesigned interface, a first-class transcript workspace, and safe
local-AI assistance. No existing job data is migrated destructively; v1.0 jobs
open unchanged.

### Performance
- **Two-pass slide detection decode**: one sequential FFmpeg analysis stream
  (cropped, downscaled, grayscale) replaces thousands of full-resolution
  random seeks; full-resolution frames are decoded only for final accepted
  candidates. Same decision algorithm, verified on synthetic and real-media
  ground truth (P=R=1.0 on the calm Egypt section, identical to v1.0.1).
- **Concurrent pipeline**: transcription and slide detection run in parallel
  after audio extraction (resource-aware; can be disabled in Settings).
- **whisper.cpp Vulkan engine** (optional, `bin/vulkan/`): whisper.cpp v1.9.1
  built with the ggml Vulkan backend for AMD/cross-vendor GPUs. On the
  reference AMD RX Vega 56 it transcribes the 6-minute excerpt in 33.3 s vs
  48.7 s CPU. Auto-selected only after the machine benchmark confirms it is
  faster; the verified CPU binary remains the default and fallback.
- **Stage cache keys**: completed stages re-run automatically when the
  source file, crop/ignore regions, detector version, engine/model, glossary
  or VAD settings changed — and are reported as "Cached" otherwise.
- **Deferred min-time acceptance** in the detector: a slide change that
  passes every content check but lands inside the min-time gate is accepted
  when the gate opens instead of being re-detected seconds late.
- Candidate thumbnails are cached as WebP (~10× smaller than the PNGs) and
  decoded off the GUI thread.

### Interface (new shell)
- Navigation rail (Home · Process · Review · Transcript · Exports · Settings),
  top command bar (job switcher, product mode, Save, Export, status) and a
  status bar showing stage, elapsed time, progress and the ACTUAL loaded
  engine/backend/model. Light and dark themes; window geometry, splitter
  positions, list/grid mode and last page persist between sessions.
- **Review**: slide timeline (compact list or thumbnail grid) + large preview
  + transcript for the selection. Selected slides are unmistakable: ≥3 px
  accent outline, contrasting background, checkmark badge, keyboard focus
  ring, auto scroll-into-view, and a live selection count. Ctrl-click
  toggles, Shift-click selects ranges, Ctrl+A selects all, Delete rejects
  (never deletes files), R restores, Ctrl+Z undoes. Context menu: Keep,
  Reject, Restore, Export selected, Copy image, Open source timestamp.
- **Transcript workspace** (independent of slide review):
  - *Full Transcript*: readable document with section headings, optional
    timestamps, search highlighting, timestamp links that select the
    matching slide, one-click full copy.
  - *Segments*: grid (#, start, end, duration, confidence, status, text)
    with a separate editor for the active segment, split at cursor, merge,
    reset, save, undo/redo. Sorting/filtering never changes chronological
    export order. Structural edits live in a new working layer
    (`working.json`); raw whisper output remains immutable and the legacy
    `edited.json` is still mirrored for old tools.
  - *Sections*: conservative topic sections; headings are renameable and AI
    suggestions are explicitly marked "(AI)" and editable.
  - *Context Repair* tab (also reachable from Review).
- **Stage-by-stage progress** with per-stage elapsed time and ETA, cached/
  skipped markers, collapsible log drawer, and a Cancel that actually kills
  worker processes.

### Local AI (Ollama) — optional, never required
- Fault-isolated Ollama client: finite connect/generation timeouts, streamed
  cancellation, strict JSON-schema constrained requests (temperature 0,
  thinking disabled), typed errors, and a disk response cache keyed by
  transcript hash + context + model + prompt version.
- Context Repair proposals via a worker thread — **never on the GUI thread**
  (fixes the v1.0.1 crash) — with progress, cancel, and an inline recoverable
  error bar (Retry / Use deterministic repair only / Open Ollama settings /
  Copy diagnostics). An Ollama crash, timeout, unload or bad response can no
  longer take the app down; exports never wait for AI.
- Settings → AI (Ollama): availability/version check, model list from
  `/api/tags` with parameter size/quantization/disk size, Test Model,
  keep-alive control, per-job enable. Recommended default on this machine:
  `qwen3:1.7b` (benchmarked; see evidence).
- AI may propose spelling/proper-name fixes, section headings and summaries;
  it can never modify the raw transcript, silently apply anything, or block
  exports.

### Reliability
- Cancel now escalates `terminate()` to `kill()` (Windows console processes
  ignore WM_CLOSE — in v1.0 a cancelled whisper-cli kept running) and a
  cancellation latch prevents late process exits from restarting the
  pipeline; replaced detector workers are reaped safely (fixes a native
  crash under cancel).

### Tests
- 106 automated tests (36 new): selection visuals (including a pixel-level
  accent-outline check), Ctrl/Shift-click, transcript views/copy formats/
  search sync/split/merge/undo, Ollama fault isolation against a scripted
  fake server (10 failure modes), scheduler concurrency and cancellation,
  stage cache keys, engine registry fallback policy, old-job compatibility.

## [1.0.1-real-media-verified] — 2026-07-15

Treats v1.0.0 as an internal beta and adds the missing user-facing Context Repair
workflow, transcript usability, and — most importantly — **real-media verification
through the packaged application** (not just synthetic fixtures).

### Added
- **Context Repair workspace** (`ui/context_repair_dialog.py`): reviews proposed
  corrections with the raw (Layer 1), normalized (Layer 2) and proposed text
  side by side, changed words highlighted (proper names highlighted separately),
  reason + confidence, Accept / Reject / Edit, Accept-all-high-confidence,
  Reject-all, and filters (low confidence / proper names / numbers-dates /
  unresolved / accepted / rejected). Raw Whisper output is never overwritten;
  every action is reversible. Includes a **Context & Names** editor whose terms
  feed both the Whisper prompt and the proposals.
- **Deterministic offline Context Repair provider**
  (`DeterministicNameProvider`): proposes approved-name corrections by fuzzy
  match when no local LLM is configured. It can only ever propose names you
  approved — it cannot invent one.
- **Transcript usability**: a "Copy as" selector (`txt/md/json/jsonl/csv/srt/vtt`),
  Copy Slide / Copy Topic / Copy Selected / Copy Full, semantic sections with
  topic headings, and section/multi-format exports. `transcript_formats.py` is the
  single serializer/section source shared by the UI, exports, and acceptance driver.
- **New exports**: `transcript.md`, `.jsonl`, `.csv`, `.vtt`, `transcript.sections.md`.
- **Packaged acceptance driver** (`lecturepack/acceptance.py`, `--run-acceptance`):
  drives the whole pipeline headlessly from the frozen EXE with bundled binaries;
  supports `--mode` for product-mode verification.

### Verified on real media (native Windows, packaged EXE)
- **Packaged short-video pipeline** (`m2-res_1080p.mp4`): `LecturePack.exe
  --run-acceptance` exit 0 — bundled ffmpeg/whisper, all 11 export formats
  parse, ordered timestamps, Context Repair accept/reject reversible with raw
  hash preserved, restore after reopen, and re-export proven **not** to rerun
  audio/whisper/detection.
- **Context-aware transcription** (Egypt lecture excerpt, base.en): the Whisper
  `--prompt` did **not** fix "Mark Lainer"→*Mark Lehner* or "dolarite"→*dolerite*
  even with the correct terms in the prompt; post-hoc **Context Repair** proposed
  exactly those fixes (from approved names) for user review. Honest finding —
  prompting is a weak bias; review-based repair is more effective and preserves
  user control. (small.en not run — not present locally and not authorized to
  download.)
- **Detector on real lecture material**: calm section (5:00–7:00) scored
  **P=1.00 R=1.00 F1=1.00** (4/4 slide states, 0 false positives) against
  human-labeled ground truth from dense contact sheets; an embedded 6-min video
  section produced 13 distinct scene keyframes with **no** fade/caption/pointer
  clusters. See `docs/evidence/v1.0.1/`.

### Changed
- Version consolidated to **1.0.1**.

### Fixed / Safety
- `robocopy`-based timestamped backup of all existing jobs before any test; no
  job or candidate is ever deleted (regression-tested).

---

## [1.0.0-unified] — 2026-07-15

Unified v1.0. Executed and verified on the native Windows machine
(Python 3.12.3, PySide6 6.11.1, opencv-python-headless 5.0.0). **53 tests pass.**

### Added
- **Product modes** — an *Output* selector (Study Pack / Transcript Only /
  Slides Only). Stage-gating in `JobController` (`STAGES_SKIPPED_BY_MODE`);
  mode-aware export selection in `ExportService`. Covered by
  `tests/test_product_modes.py` (real controller pipeline, mock ffmpeg/whisper).
- **Layered transcript wiring** — after transcription the controller writes
  `transcript/normalized.json` + `transcript/context_candidates.json` from the
  (previously unwired) `transcript_service`, and exports a paragraph-grouped
  `transcript.normalized.txt`. The raw layer is proven immutable by content hash.
- **Slide-detector precision guards** (`cv_engine.py`, preset-gated): bottom
  caption/overlay-band rejection and major-change future-persistence (fade/
  dissolve rejection). Calibrated on measured SSIM (real slides ≥ 0.975, mid-fade
  frame 0.778). New regression tests `tests/test_detection_targets.py`.

### Changed
- **Detector accuracy on the ground-truth fixture** (no masks): default
  **balanced** preset went from P=0.67 R=0.75 F1=0.71 → **P=1.00 R=1.00 F1=1.00**;
  detailed → P=0.89 R=1.00 F1=0.94. Both meet the acceptance targets.
- **Version consolidated to 1.0.0** across `__init__.py`, `constants.APP_VERSION`,
  `build_release.py`, and new-job manifests (previously 0.2.1 / 0.4.0 / 0.1.0).

### Fixed
- Guarded two fire-and-forget `QTimer.singleShot` handlers that cleared the
  transcript status label; a stale timer could fire after the widget was
  destroyed (`RuntimeError: Internal C++ object already deleted`).

### Verified on Windows
- Real whisper.cpp transcription (bundled `whisper-cli.exe` + `ggml-base.en`):
  42 s WAV → full token-level JSON, parsed through all three transcript layers
  with the raw content hash unchanged.
- PyInstaller onedir build + portable ZIP with SHA256SUMS and BUILD_MANIFEST.

---

## [0.4.x foundation] — branch `claude-v1-unified` (pre-1.0 increment)

Foundational, fully unit-tested services (standard-library only) laid down
before the Windows run.

### Added
- **Layered transcript service** (`lecturepack/services/transcript_service.py`):
  - Layer 1 immutable raw parse of whisper.cpp JSON (full and reduced shapes),
    with per-token confidence and a hash guard proving raw is never modified.
  - Layer 2 deterministic, non-generative normalization (whitespace/punctuation
    cleanup, hallucination-loop collapse, exact-duplicate merge, paragraph
    grouping) that never alters words, names, numbers, or facts.
  - Layer 3 optional, auditable **Context Repair** with an OpenAI-compatible
    local provider (LM Studio / Ollama), strict JSON-schema validation,
    invented-name guardrails, and fully reversible per-correction review.
  - Deterministic Context & Names proposals and sanitized whisper-prompt builder.
- **Detector ground-truth evaluation** (`lecturepack/services/detection_eval.py`)
  with construction-derived labels for the synthetic fixture
  (`tests/fixtures/ground_truth/synthetic_lecture.json`) and a runnable harness
  (`tests/scratch/run_detection_eval.py`).
- **Tests**: `tests/test_transcript_layers.py` (19) and
  `tests/test_detection_eval.py` (7) — all passing (standard-library only).
- Documentation: `docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md`,
  `docs/SLIDE_DETECTION_EVALUATION.md`, `docs/WINDOWS_RUN_HANDOFF.md`.

### Notes
- No existing source, tests, tags, or user data were modified or deleted.
- Safety checkpoint: tag `safety/start-v1-unified`; working branch
  `claude-v1-unified`; `v0.4.1-balanced-detection` left untouched at `aa19732`.
