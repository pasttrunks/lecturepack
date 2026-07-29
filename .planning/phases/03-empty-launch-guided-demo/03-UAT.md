---
status: passed
phase: 03-empty-launch-guided-demo
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md]
started: 2026-07-29T14:09:54-04:00
updated: 2026-07-29T18:58:00-04:00
---

## Current Test

number: complete
name: Phase 3 UAT complete
expected: |
  All seven Phase 3 acceptance checks pass.
awaiting: none

## Tests

### 1. Cold Start and Empty Home
expected: Launching the packaged app with a fresh profile opens normally on Home with "No lecture loaded", Recent Jobs 0, the Polar Bears demo card, and a friendly Take guided tour / Skip to app prompt. The rest of the app remains clickable.
result: pass

### 2. Guided Demo Import Action
expected: Starting the tour spotlights the lecture drop area and asks the user to move the Polar Bears demo there. The card shows its polar-bear thumbnail, is highlighted at the same brightness as the drop area while waiting, can be clicked or dragged, Exit demo stays visible, and the tour waits instead of advancing by itself.
result: pass
evidence: Packaged UAT confirmed the real Polar Bears card and drop zone remain equally bright above the CSS-only dimmer, the card is clickable, Exit remains visible, and no automatic step advancement occurs. Demo availability is runtime-admission gated; dismissal hides the Home tile while Settings > Onboarding retains replay.

### 3. Real Processing Progress
expected: Using the demo card automatically opens Process and runs the real local 10-second video pipeline. Live stage text, progress, and processing logs update while Next cannot skip ahead.
result: pass
evidence: Packaged UAT ran the bundled MP4 through the real local pipeline. Live detector/transcription logs and stage progress updated; the detector log reported exactly 4 slides before automatic Review navigation.

### 4. Review Choice and Study Transition
expected: When processing finishes, the app automatically opens Review with real Polar Bears slide images and transcript text. Keep and Reject remain clickable; making a review choice advances to Study with a Polar Bears-derived overview.
result: pass
evidence: Packaged UAT displayed four distinct Polar Bears slide thumbnails with transcript text. Keep was clickable and advanced to Study, whose timeline and statistics showed 4 kept slides.

### 5. Study and Export Guidance
expected: The tour explains the Study area, then shows Export with the actual accepted-slide count and friendly wording that exporting unlocks for the user's own lectures. Back and Finish work without leaving stale content.
result: pass
evidence: Packaged UAT reached the Study guidance and Export screen. Export reported 4 accepted slides and the tour retained Back, Finish, and friendly temporary-demo wording.

### 6. Exit, Cleanup, and Replay
expected: Exit demo is available throughout. Exit or Finish returns Home to "No lecture loaded" and Recent Jobs 0, removes temporary demo files without adding a library job, hides the Home demo tile, and leaves replay under Settings > Onboarding.
result: pass
evidence: Packaged UAT confirmed Exit and Finish cleanup. Home returned to No lecture loaded / Recent Jobs 0 with no replay tile; Settings > Onboarding retained Replay guided tour. Automated isolation tests verify temporary files and demo jobs are removed.

### 7. Demo Media Provenance
expected: The project owner confirms that the Polar Bears MP4 was created through an account they control under terms permitting bundled redistribution, contains no unlicensed third-party ingredients, and that the JPEG thumbnail is derived from that MP4. The confirmation will be recorded against the assets' SHA-256 hashes in a provenance file before release.
result: pass
evidence: On July 29, 2026, the project owner answered Yes to the complete redistribution-rights, no-unlicensed-material, and thumbnail-derivation declaration. The declaration is recorded in app/assets/demo/PROVENANCE.md against the exact source and shipped hashes.

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

None.
