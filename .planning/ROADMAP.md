# Roadmap: LecturePack v0.9.0-beta.7

## Overview

Beta 6 was certified complete on 2026-07-29 without measuring package size, launch time,
or running on a physical clean machine. On 2026-07-30 the owner installed it on a clean
device and found five defects the release gate should have caught: an oversized package,
a ~2 minute invisible launch, no protection against duplicate instances, a setup gate that
never appears on a healthy first run, and a blank taskbar icon.

Beta 7 closes those five defects with the smallest verified changes, preserving beta 6's
runtime contract, signed-repair architecture, processing behavior, updater behavior, and
existing user data.

## Phases

**Phase Numbering:** New milestone; numbering resets to Phase 1.

- [ ] **Phase 1: Clean-Device Footprint & First Launch** - Measure and cut package size, make first launch visibly responsive and single-instance, show a first-run setup checklist before the demo, and fix the taskbar icon.

## Phase Details

### Phase 1: Clean-Device Footprint & First Launch

**Goal**: A clean Windows device installs a materially smaller LecturePack, sees visible feedback within seconds of one click, cannot start a second instance, is shown a Ready / Needs Attention checklist before any demo offer, and sees the correct icon in the window and taskbar.

**Depends on**: Nothing (first beta-7 phase; builds on the shipped beta-6 runtime contract)

**Success Criteria** (what must be TRUE):

  1. Installer size and installed size are recorded as separate measured numbers, sourced from a named artifact, with the largest packaged contributors listed. The reported-vs-measured discrepancy (owner saw ~800 MB / ~900 MB; dev build measures 841 MB ZIP / 1.9 GB installed) is resolved and explained, not averaged.
  2. `ggml-base.en.bin` is present exactly once in the packaged output; `translations/`, `qml/`, the Quick/Quick3D DLLs, and `Qt6Pdf.dll` are absent. Offline processing (FFmpeg, ffprobe, Whisper CPU CLI + DLLs, `ggml-base.en.bin`, `runtime-smoke.wav`) still passes the packaged runtime smoke.
  3. One click on a cold clean profile produces visible on-screen feedback in a few seconds, and the remaining runtime validation reports honest itemized progress rather than an unexplained wait. One cold and one warm launch are measured and recorded.
  4. Launching LecturePack while an instance is running raises the existing window instead of starting a second process; the guard acts before the slow validation path.
  5. A fresh profile shows the setup checklist with Ready / Needs Attention per requirement before the guided demo is offered, and offers the demo only after the user continues or deliberately skips. No component that is already bundled is downloaded or reinstalled.
  6. The LecturePack icon appears in the window title bar and the Windows taskbar for the installed build.

**Plans**: TBD

Cross-cutting constraints: preserve existing user data, existing processing behavior, and beta-6 updater behavior; do not weaken the AD-19 signed-manifest repair contract or the AD-18 ASCII native-staging boundary; do not use a splash screen to conceal an unresolved startup delay; keep the setup checklist in the existing WebEngine UI vocabulary.

Canonical references: `.planning/phases/01-clean-device-footprint-first-launch/01-CONTEXT.md`, `.planning/milestones/v0.9.0-beta.6/README.md`, `.planning/milestones/v0.9.0-beta.6/MILESTONE-CONTEXT.md`, `docs/DECISIONS.md` (AD-18, AD-19), `BUG_LIST.md`.

**Approval/evidence gate**: Measured size table (before/after, per contributor); measured cold and warm launch times on a clean profile; packaged runtime smoke passing after the size cuts; single-instance and first-run-routing tests; one packaged clean-profile launch with the icon visible.

**UI hint**: yes

## Progress

**Execution Order:** Phase 1.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Clean-Device Footprint & First Launch | 0/TBD | Not started | - |
