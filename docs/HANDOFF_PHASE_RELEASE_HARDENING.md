# Handoff - v2.0.1 release hardening

**Date:** 2026-08-12
**Branch:** `codex/ai-first-study`
**Canonical repository:** `C:\Users\marsh\Documents\LecturePack`
**Method:** direct release hardening; GSD was not used

## Task restatement

- **Authorized phase:** LecturePack v2.0.1 release hardening after the guided
  demo and AI-first Study integration.
- **Exact goal:** make the packaged Electron app, guided demo, Study AI,
  recovery paths, and compact-window UI reliable enough for release; configure
  and verify NVIDIA as the fastest-first production AI route.
- **Files permitted:** directly implicated Electron packaging/sidecar files,
  Study service, renderer CSS/markup, release acceptance scripts, tests,
  `LICENSE`, and release/decision documentation.
- **Required tests:** focused regressions, complete pytest suite, Electron and
  gateway syntax/tests, official release build self-test, packaged stable gate,
  compact-window visual gate, live production-gateway Study gate, artifact
  hashes, and orphan-process checks.
- **Non-goals:** no new product feature, no stack replacement, no customer-data
  access, no credential persistence, no provider controls in the desktop, no
  tag/push/publication, and no production gateway redeploy without a discovered
  defect.
- **Required completion evidence:** exact artifact paths/hashes plus
  machine-readable packaged, visual, AI, test, runtime, and deployment evidence.

## What changed

### The packaged guided demo now contains its promised output

The Windows package previously omitted `demo.data.js`, the hero, and both
prebuilt slide images even though the source walkthrough used them. Packaged
users therefore saw fallback copy in every content chapter while the old gate
tested only navigation. The packager now copies the curated app-owned demo
directory to the renderer's exact `resources\assets\demo` path (without
duplicating the canonical video), and the release validator requires every
file before publishing an artifact.

The packaged gate now proves decoded hero/slide images, transcript rows,
flashcard content, four quiz options, and zero fallback panels. It enters
responsive demo cases through the real Settings replay control and covers
Demo, Home, Review, and Study at 640x480, 820x600, and 1024x720: 12 cases.

### First-run and demo completion states are release-safe

The zero-job demo action is asserted at 1024x720 both before the first tour and
after completing/cleaning it up. At short desktop heights, the completed-tour
empty card uses a compact horizontal layout so `Try the demo lecture` remains
in the opening viewport. Reopening a completed tour starts at chapter 1 while
an interrupted tour still resumes its saved chapter.

The demo quiz now exposes `aria-pressed`, per-choice correct/incorrect labels,
and a textual live result instead of relying on red/green alone. Demo cleanup
also restores the authoritative runtime label, so the footer cannot pair
`Idle` with a stale `Detecting slides` stage.

### NVIDIA-first production routing was stressed repeatedly

Three clean packaged installations completed the full live Study flow against
the shipped production HTTPS gateway in 38.3s, 41.3s, and 41.4s. Every run
produced grounded Study material and exercised Ask, Teach Me, semantic grading,
Basic fallback, clean shutdown, and orphan checks. Production D1 telemetry for
the 15 resulting provider calls showed NVIDIA for every attempt and 15/15
successes, with averages of 1.13s for Ask, 1.35s for grading, 1.59s for Teach
Me, 4.38s for lecture analysis, and 12.32s for full material generation. No
fallback provider was invoked.

### Study deletion is now final

The sidecar now gives each job a Study cancellation epoch. Demo cleanup,
single/bulk deletion, and reset advance that epoch. Full Study generation,
partial regeneration, Ask, Teach Me, and grading reject late completion after
cancellation. `AIStudyService` also checks cancellation around provider calls
and before persistence, so a late provider failure is not written to a deleted
job.

A defensive tombstone cleanup removes only the exact safe job directory and
only when it has no manifest. It cannot delete a valid recreated job. Regression
tests deliberately force the old late-write race and prove the demo directory
does not return.

### Packaged visual evidence is no longer obscured

The stable harness had imported through the host but started the canonical job
programmatically, leaving the real batch setup dialog over several screenshots.
It now closes that dialog through its visible Close control and fails if an
unexpected dialog obscures the core screens.

The same gate now resizes the real BrowserWindow to 640x480, 820x600, and
1024x720, then measures and captures Home, Review, and Study. It rejects
horizontal overflow in the document/header/main/screen/footer and clipped
controls. This exposed a real 640x480 Review defect: its timeline header was
544 pixels wide in a 400-pixel main pane. Review metadata and legend now wrap,
and the lecture switcher receives a full compact row. The rebuilt candidate
passes all 12 Demo/Home/Review/Study matrix cases with exact client/scroll
equality.

### Release licensing

The repository now carries the MIT `LICENSE`. The Windows packager requires and
copies it to `resources\LICENSE`; release-hardening tests enforce membership.

### Clean-machine validation matches product lifecycle

The installed-artifact validator previously imported its sample as a temporary
guided demo, then requested transcript state after the demo correctly cleaned
itself up. It now uses a normal persisted job for transcript/export inspection;
the packaged stable gate remains responsible for the transient demo lifecycle.
The validator also uninstalls its exact disposable test installation in a
`finally` path, so a failed assertion cannot leave registry or shell residue.

## Exact release candidate

Built from the current source with:

```powershell
.\.venv\Scripts\python.exe scripts\build_electron_release.py `
  --runtime-root . `
  --output-dir C:\LecturePackScratch\builds\release-final-guided-demo-c4a1efb-20260812
```

The final build completed in 539 seconds and its embedded self-test passed FFmpeg,
ffprobe, Whisper runtime/smoke/model, Rust Study Core, yt-dlp, EJS, Deno, data
directory, and controller admission.

Artifacts:

- Portable ZIP:
  `C:\LecturePackScratch\builds\release-final-guided-demo-c4a1efb-20260812\LecturePack-2.0.1-Portable.zip`
  - SHA-256:
    `52d957bb07392290c5ca9261f33c230005fcc987fe23dc5a2cbd0f8dc5dea472`
- Installer:
  `C:\LecturePackScratch\builds\release-final-guided-demo-c4a1efb-20260812\LecturePack-2.0.1-Setup.exe`
  - SHA-256:
    `915e510b90aad11b8e766f73ccecc4d6311c15d04026cf4b6e7345f1e9ad0be2`
- Hash manifest:
  `C:\LecturePackScratch\builds\release-final-guided-demo-c4a1efb-20260812\LecturePack-2.0.1-SHA256SUMS.txt`
- Release manifest:
  `C:\LecturePackScratch\builds\release-final-guided-demo-c4a1efb-20260812\LecturePack-2.0.1-release-manifest.json`
- Exact unpacked candidate:
  `C:\Users\marsh\Documents\LecturePack\electron-spike\dist\LecturePack-win32-x64`

## Verification evidence

### Complete repository suite

With
`LECTUREPACK_ONEDIR_FIXTURE=C:\LecturePackScratch\builds\release-hardening-final-8a65dd6\exact-final-onedir-fixture`:

```text
1519 passed, 2 skipped, 1 warning in 386.04s
```

There were zero failures. The skips are the explicitly opt-in real-provider
test and one environment-specific package-pruning case. The warning is the
intentional duplicate-ZIP corruption fixture.

The final guided-demo/release focused set also passed: `66 passed`; the final
quiz gate additions passed their 29-test focused set with warnings treated as
errors for Python compilation.

### Packaged stable/visual gate

Evidence:
`C:\LecturePackScratch\results\release-final-guided-demo-c4a1efb-20260812\stable-r2\stable-release-acceptance.json`

Result: `PASS`, 43 checks, no failures, 26 screenshots. It proves:

- packaged startup and first-run runtime acknowledgement;
- decoded prebuilt hero and slide assets, transcript rows, flashcard and quiz
  content, zero fallback panels, textual/semantic wrong-answer feedback;
- five-chapter guided demo, real processing handoff, Review Ready route,
  settled cleanup footer, and cleanup that remains final after normal Smart
  Study reaches ready;
- canonical import/progress/completion, slides, transcript, grounded Study,
  flashcards, correct quiz handling, and Quick Study;
- exact 13-file export;
- folder/multi-file/junk/duplicate import and existing-instance Send To;
- continued screen/job state and session/window restore;
- 21-minute workload ETA, power-save blocker, close-to-tray, restore,
  cancellation, retry, and blocker release;
- interrupted job/download recovery and download retry/cancel;
- update-available and missing-sidecar actionable failure UI;
- unobscured Review/Transcript/Study captures;
- the demo action in view at 1024x720 both before first use and after a
  completed tour with zero jobs;
- all 12 Demo/Home/Review/Study responsive cases at 640x480, 820x600, and
  1024x720;
- clean shutdown and zero final orphan processes.

### Exact installer clean-machine gate

Evidence:
`C:\LecturePackScratch\results\release-final-guided-demo-c4a1efb-20260812\clean-install-r1\clean-machine-result.json`

Result: `PASS`. The exact installer and installed application proved:

- per-user silent install exit 0 and product version 2.0.1;
- packaged startup/self-test health without using a development Python, Node,
  Rust, or Git runtime;
- a real normal lecture completed with 2 slides and 2 transcript segments;
- Study data and exactly 13 export files were produced;
- sidecar shutdown, Electron host startup, and session/window restore passed;
- zero orphan processes;
- uninstall exit 0, with no remaining install directory, uninstall registry
  entry, or Send To shortcut.

Cleanup failure-path evidence:
`C:\LecturePackScratch\results\release-final-guided-demo-c4a1efb-20260812\clean-install-forced-failure-r1`

An additional run deliberately set the active-job completion timeout to zero.
It reached the installed packaged sidecar, failed at the intended assertion
with exit 1, terminated that exact spawned process tree, and uninstalled. A
post-run audit again found zero LecturePack/runtime processes and no install
directory, registry entry, or Send To shortcut.

### Exact portable fault-injection gate

Evidence:
`C:\LecturePackScratch\results\release-final-guided-demo-c4a1efb-20260812\clean-negative-r1\negative-test-result.json`

Result: `PASS`, all 9 scenarios, zero remaining processes. In a disposable
extraction of the exact portable ZIP, missing FFmpeg, ffprobe, Whisper model,
Whisper executable, and unwritable data correctly failed startup. Missing Rust
Study Core and unavailable yt-dlp remained launchable but made the self-test
honestly fail, preserving the intended optional-degradation boundary. Missing
and immediately exiting sidecars both produced explicit startup failure in
under one second. Every temporarily held packaged file was restored.

### Live production AI gate

Evidence:
`C:\LecturePackScratch\results\release-final-guided-demo-c4a1efb-20260812\ai-live-r1\ai-study-live-packaged-acceptance.json`

Result: every check passed in 38.0 seconds. The exact packaged sidecar proved
runtime health, local processing, production HTTPS gateway use, anonymous
registration, opaque installation token, grounded summary/concepts/guide,
flashcards, mixed quiz, valid citations, Teach foundations, manual mastery,
Quick Study, Ask with sources, Teach Me, semantic grading, explicit Basic
fallback, clean exit, and zero orphans.

### Gateway/configuration audit

- Production origin:
  `https://lecturepack-ai-gateway.discordsammy2.workers.dev`
- Deployed version:
  `d9e2dbcb-369b-4a4e-a895-e8ff75ea4fc5` at 100 percent
- Health: configured, 8/8 required tasks
- D1: `lecturepack-study-prod`, no pending migrations, metadata-only schema
- Secrets present by name only: `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`,
  `TOKEN_SIGNING_SECRET`, `NETWORK_HASH_SECRET`
- Exact NVIDIA-first tasks:
  `lecture_analysis,study_material_generation,ask,teach_me,grade_short_answer,regenerate_concept,vision_slide`
- NVIDIA text: `meta/llama-3.1-8b-instruct`
- NVIDIA vision: `nvidia/nemotron-nano-12b-v2-vl`
- Production audit window: NVIDIA text 43/43 successes (~5.0 s average),
  NVIDIA vision 1/1 (~4.1 s), Workers AI 20/21 (~19.7 s), OpenRouter 7/26
  (~16.3 s). NVIDIA remains the fastest healthy configured route.
- Fresh post-hardening stress window: all 15 calls across three clean
  installations used NVIDIA and succeeded. Mean latency was 1.13 s Ask,
  1.35 s grading, 1.59 s Teach Me, 4.38 s lecture analysis, and 12.32 s full
  study-material generation; no fallback route was invoked.
- Gateway local checks: 21/21 tests, syntax checks, and Wrangler 4.122.0
  `deploy --dry-run` passed.

No secret value was printed, stored in the repository, or copied into the
desktop. No production gateway change was needed or deployed during this final
audit.

## Remaining external release gate

`LecturePack.exe`, `LecturePackSidecar.exe`, and the exact installer currently
report `NotSigned`.
`Cert:\CurrentUser\My` and `Cert:\LocalMachine\My` contain no code-signing
certificate. There is also no signing-related environment variable or private
key/certificate file in the repository. This cannot be repaired in source or
configured on NVIDIA/Cloudflare; a trusted Authenticode certificate with its
private key must be supplied before a signed public installer can be produced.

Until that credential exists:

- the code/content candidate is fully built and acceptance-green;
- do not label the current installer as signed;
- do not publish/tag the release as the final trusted Windows installer;
- do not weaken the signing expectation or create a self-signed production
  substitute.

After a certificate is supplied, rebuild/sign the exact passing source, verify
`Get-AuthenticodeSignature` reports `Valid` for both executable and installer,
recompute hashes, rerun packaged startup/smoke, and publish only those signed
artifacts.

## Process hygiene

All acceptance profiles and lecture data used above are under
`C:\LecturePackScratch`. No original lecture video or normal user data was
modified. The disposable installer was fully uninstalled; its install
directory, registry entry, and Send To shortcut are absent. The packaged,
installed, portable-negative, and live-AI gates all report zero orphan
LecturePack, sidecar, Whisper, or FFmpeg processes.
