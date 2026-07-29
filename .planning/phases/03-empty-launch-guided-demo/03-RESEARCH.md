# Phase 3: Empty Launch & Guided Demo - Research

**Date:** 2026-07-28
**Phase:** 03-empty-launch-guided-demo

## Executive Summary

Phase 3 implements an empty owned Home screen on healthy startup, a replayable guided onboarding tour with DOM spotlighting, synthetic 60-second demo media packaging, and session-scoped temporary workspace isolation with idempotent cleanup.

## Requirements Mapping & Technical Architecture

### 1. Empty Home Launch (`HOME-01`, `HOME-02`, `HOME-03`)
- **`HOME-01`**: On healthy boot, `Backend.on_ui_ready` emits `active_job` with payload `{"id": "", "title": ""}` ensuring no job opens automatically.
- **`HOME-02`**: Existing jobs remain listed in `jobs_changed` payload; opening a job requires explicit click on a library list item calling `backend.open_job(id)`.
- **`HOME-03`**: Demo and synthetic data are marked `session_scoped: true` and omitted from `library.json` persistence.

### 2. Guided Onboarding Tour (`DEMO-01` to `DEMO-08`)
- **`DEMO-01`**: On first launch (when `onboarding_seen` setting is false), Home displays a non-blocking prompt offering **Start guided demo** and **Skip for now**.
- **`DEMO-02`**: Tour spotlight uses Studio design tokens: `.lp-tour-overlay` with a dark translucent backdrop (`rgba(10,13,20,0.85)`), a spotlight cutout (`box-shadow` or `clip-path`), and a 2px orange structural border (`#FF7A00`).
- **`DEMO-03`**: A persistent **Exit demo** button is present on the tour step card.
- **`DEMO-04`**: Tour teaches 4 steps: (1) Empty Home & New Job button, (2) Processing pipeline view, (3) Slide & Transcript Review, (4) Study Assistant & Exports. Replayable via Settings.
- **`DEMO-05`**: Bundles a 60-second rights-clear synthetic CS lecture MP4 and slides under `app/assets/demo/demo_lecture.mp4`.
- **`DEMO-06`**: Demo processes the synthetic file through the real offline pipeline (Whisper CPU transcription, slide extraction, alignment, export preview).
- **`DEMO-07`**: Demo runs inside `%TEMP%\LecturePack\demo_<session_id>`. Backend overrides data directory for demo calls and bypasses `library.json` writes.
- **`DEMO-08`**: Demo cleanup sweeps any leftover `demo_*` temp directories on exit, tour finish, or next boot.

## Recommended Plan Breakdown

- **Plan 03-01**: Empty Home surface state, active job initialization, and library isolation (`HOME-01`, `HOME-02`, `HOME-03`).
- **Plan 03-02**: Synthetic demo media bundle, isolated temp session manager, and startup/exit sweep (`DEMO-05`, `DEMO-07`, `DEMO-08`).
- **Plan 03-03**: Guided tour overlay, spotlight positioning, step state machine, and Settings replay (`DEMO-01`, `DEMO-02`, `DEMO-03`, `DEMO-04`, `DEMO-06`).
