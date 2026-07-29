# Phase 3 Handoff — Empty Launch & Guided Demo

**Date:** July 29, 2026  
**Status:** Complete; packaged UAT and media-rights attestation recorded  
**Branch:** `codex/phase3-guided-demo-recovery`

## Completed

- Healthy runtime admission reveals the first-run Polar Bears demo; repair-required and pre-admission states do not.
- The user-controlled tour spotlights the real drop zone and real demo card at equal brightness, preserves click/drag behavior, and keeps Exit/Back/Next available where appropriate.
- Skip, Exit, and Finish remove the Home demo tile. Replay remains under Settings > Onboarding.
- The bundled 10-second MP4 runs through the real local detector/transcriber. A demo-only detector calibration finds the four confirmed slide intervals without hard-coded slide output.
- Review shows four real slide images and transcript text; Keep/Reject advances to Study, which reports four kept slides, then to Export.
- Low, Balanced, and High detector controls are semantic buttons backed by the settings bridge. Normal immediate, queued, and scheduled jobs snapshot and preserve the selected preset; the guided demo stays isolated on its fixed calibration.
- Demo work remains isolated from normal jobs/profile state and sentinel-scoped temporary data is cleaned on all terminal paths.
- Intentional beta-5 shadows, pressed controls, palette, transitions, and motion remain intact.

## Verification Evidence

- Full package-backed suite: `842 passed, 1 warning` in 307.16 seconds.
- Final affected package-backed suite: `54 passed` in 3.44 seconds.
- Focused UI suite after final overlay correction: `95 passed`.
- Fresh packaged Windows UAT confirmed equal import highlights, four detector results, four Review thumbnails, four kept Study slides, Export guidance, clean Home dismissal, and Settings replay.
- Packaging gate rebuilt successfully with the canonical CPU runtime, portable ZIP, and checksum manifest.
- Artifact audit confirmed the EXE, demo MP4, thumbnail, Whisper model, ZIP CRC, and SHA-256 manifest are internally consistent.

## Media Provenance Gate

On July 29, 2026, the project owner confirmed that:

1. `app/assets/demo/demo_lecture.mp4` was created through an account they control under terms permitting bundled redistribution.
2. It contains no unlicensed third-party ingredients.
3. `app/assets/demo/polar_bears_thumbnail.jpg` is derived from that MP4.

The dated declaration is recorded in `app/assets/demo/PROVENANCE.md`, bound to these shipped hashes:

- MP4: `24957e863c477cd7ad2ef9228f3bbe943f5038e5ccd18ef7ab92efefee13f55f`
- JPEG: `6120e615b8f5d3006be9bb786b856c15ae1b6ae9c0a80b106d5f48280556795f`

Phase 3 is ready for final verifier closure and transition to Phase 4.
