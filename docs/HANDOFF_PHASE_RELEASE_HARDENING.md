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
passes all 9 matrix cases with exact client/scroll equality.

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
  --output-dir C:\LecturePackScratch\builds\release-final-epochfix-20260812
```

The final build completed in 434 seconds and its embedded self-test passed FFmpeg,
ffprobe, Whisper runtime/smoke/model, Rust Study Core, yt-dlp, EJS, Deno, data
directory, and controller admission.

Artifacts:

- Portable ZIP:
  `C:\LecturePackScratch\builds\release-final-epochfix-20260812\LecturePack-2.0.1-Portable.zip`
  - SHA-256:
    `8f89fc99810e56ff1caee130e746340236ec7907266c571edf6ce49f87ce599a`
- Installer:
  `C:\LecturePackScratch\builds\release-final-epochfix-20260812\LecturePack-2.0.1-Setup.exe`
  - SHA-256:
    `6adbd9824676f9fe80f40c0d879bb33fb513d8ff9785b03a4ac31fc2bebd5bea`
- Hash manifest:
  `C:\LecturePackScratch\builds\release-final-epochfix-20260812\LecturePack-2.0.1-SHA256SUMS.txt`
- Release manifest:
  `C:\LecturePackScratch\builds\release-final-epochfix-20260812\LecturePack-2.0.1-release-manifest.json`
- Exact unpacked candidate:
  `C:\Users\marsh\Documents\LecturePack\electron-spike\dist\LecturePack-win32-x64`

## Verification evidence

### Complete repository suite

With
`LECTUREPACK_ONEDIR_FIXTURE=C:\LecturePackScratch\builds\release-hardening-final-8a65dd6\exact-final-onedir-fixture`:

```text
1514 passed, 2 skipped, 1 warning in 354.26s
```

There were zero failures. The skips are the explicitly opt-in real-provider
test and one environment-specific package-pruning case. The warning is the
intentional duplicate-ZIP corruption fixture.

After the final validator cleanup guard was added, the complete changed-area
set (`test_release_hardening`, `test_polish_backend`, `test_ai_study_service`,
and `test_ui_tokens_motion_responsive`) also passed: `75 passed in 8.44s`.

### Packaged stable/visual gate

Evidence:
`C:\LecturePackScratch\results\release-final-epochfix-20260812\stable-acceptance-r7\stable-release-acceptance.json`

Result: `PASS`, no failures, 21 screenshots. It proves:

- packaged startup and first-run runtime acknowledgement;
- five-chapter guided demo, real processing handoff, Review Ready route, and
  cleanup that remains final after normal Smart Study reaches ready;
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
- all 9 responsive cases at 640x480, 820x600, and 1024x720;
- clean shutdown and zero final orphan processes.

### Exact installer clean-machine gate

Evidence:
`C:\LecturePackScratch\results\release-final-epochfix-20260812\clean-install-r2\clean-machine-result.json`

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
`C:\LecturePackScratch\results\release-final-epochfix-20260812\clean-install-forced-failure-r1`

An additional run deliberately set the active-job completion timeout to zero.
It reached the installed packaged sidecar, failed at the intended assertion
with exit 1, terminated that exact spawned process tree, and uninstalled. A
post-run audit again found zero LecturePack/runtime processes and no install
directory, registry entry, or Send To shortcut.

### Exact portable fault-injection gate

Evidence:
`C:\LecturePackScratch\results\release-final-epochfix-20260812\clean-negative-r1\negative-test-result.json`

Result: `PASS`, all 9 scenarios, zero remaining processes. In a disposable
extraction of the exact portable ZIP, missing FFmpeg, ffprobe, Whisper model,
Whisper executable, and unwritable data correctly failed startup. Missing Rust
Study Core and unavailable yt-dlp remained launchable but made the self-test
honestly fail, preserving the intended optional-degradation boundary. Missing
and immediately exiting sidecars both produced explicit startup failure in
under one second. Every temporarily held packaged file was restored.

### Live production AI gate

Evidence:
`C:\LecturePackScratch\results\release-final-epochfix-20260812\ai-live-r3\ai-study-live-packaged-acceptance.json`

Result: all 27 checks passed in 38.3 seconds. The exact packaged sidecar proved
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
- Gateway local checks: 21/21 tests, syntax checks, and Wrangler 4.122.0
  `deploy --dry-run` passed.

No secret value was printed, stored in the repository, or copied into the
desktop. No production gateway change was needed or deployed during this final
audit.

## Remaining external release gate

Both `LecturePack.exe` and the installer currently report `NotSigned`.
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
