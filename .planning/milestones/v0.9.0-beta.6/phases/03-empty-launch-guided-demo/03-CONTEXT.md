# Phase 3: Empty Launch & Guided Demo - Context

**Gathered:** 2026-07-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 establishes an empty owned Home screen on healthy launch and provides a replayable, isolated guided onboarding tour. It ensures zero automatic job opening on boot, keeps existing user jobs visible in the library side panel, isolates demo processing into a dedicated session-scoped temporary directory, and guarantees idempotent demo cleanup.

This phase owns the empty Home UI presentation, guided tour overlay spotlighting, tour step progression and controls, synthetic demo asset packaging, demo session workspace isolation, and Settings replay entrypoint. It does not alter Phase 1/2 runtime health gating or Phase 4 visual artifact reliability.

</domain>

<decisions>
## Implementation Decisions

### Guided Tour UI & Interaction
- **D-01:** Implement guided tour overlay using the studio design language (dark translucent scrim, rounded spotlight cutout over target elements with an orange structural border glow).
- **D-02:** Tour step sequence follows a 4-step workflow: (1) Empty Home & New Job button, (2) Processing pipeline view, (3) Slide & Transcript Review, (4) Study Assistant & Exports.
- **D-03:** Step cards include Next/Back buttons, keyboard arrow key navigation, and a persistent, visible **Exit demo** action on every step.
- **D-04:** Add a **Replay guided tour** action in Settings under the Onboarding section.

### Synthetic Demo Asset Packaging
- **D-05:** Bundle demo assets under `app/assets/demo/demo_lecture.mp4` with extractable slides and crisp audio.
- **D-06:** Demo video is a 60-second rights-clear computer science lecture containing zero third-party copyrighted materials.
- **D-07:** Demo processing runs through the real local pipeline using fast CPU Whisper transcription and slide detection presets.
- **D-08:** Demo assets are bundled locally in the distribution; no network request is made.

### Demo Isolation & Workspace Cleanup
- **D-09:** Demo session operates in a dedicated temporary workspace (`%TEMP%\LecturePack\demo_<session_id>`).
- **D-10:** Demo jobs, transcript corrections, and generated artifacts are marked as session-scoped and never pollute `library.json` or persistent user job storage.
- **D-11:** Idempotent demo cleanup triggers automatically on tour exit, app exit, or launch sweep during next boot.
- **D-12:** Interrupted or crashed demo runs leave zero residual data in the main user profile.

### Empty Home Surface UI
- **D-13:** Healthy startup opens a clean Home screen with no active job automatically opened.
- **D-14:** Home displays clear call-to-action buttons: **Import lecture video** and **Try guided demo**.
- **D-15:** On first clean launch, a non-blocking prompt offers **Take guided tour** or **Skip to app**.
- **D-16:** Existing user jobs remain listed in the library panel and load only upon explicit user selection.

### Discretion
- Microcopy and wording of tour step guidance cards.
- Exact spotlight animation duration and easing curve matching the Studio motion system.
- Internal session ID generation and temporary folder naming schema.

</decisions>

<specific_guidance>
## Specific Guidance for Research and Planning

1. Verify `app/ui/app.js` and `app/ui/index.html` spotlight overlay integration for non-destructive DOM element highlighting.
2. Ensure `app/desktop/main.py` and `bridge.py` enforce session workspace isolation for demo jobs.
3. Validate that `library.json` writes are strictly skipped during demo session execution.
4. Verify sweep logic in `app/desktop/paths.py` or startup routine to clear leftover `demo_*` directories.
</specific_guidance>
