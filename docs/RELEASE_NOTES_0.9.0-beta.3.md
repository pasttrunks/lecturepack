# LecturePack 0.9.0-beta.3

**Reliability, Queueing, Scheduling, Notifications, and Polish**

Beta.3 retains the bundled zero-setup local engine from beta.2 — transcription,
slides, transcript, exports, and built-in quizzes/flashcards still work
immediately after installation with no account, API key, GPU, or Ollama.

## New
- Persistent processing queue with reorder and Run Now controls
- Local scheduling with missed-schedule options (run when opened / skip / ask)
- Safe checkpoint-based pause and resume
- Windows notifications for completion, failure, and updates
- Windows taskbar processing progress
- Keep-awake while processing (your display may still sleep)
- Better completion panel with real metrics, plus retry and folder shortcuts
- Redacted diagnostics you can copy without leaking keys or transcript text
- Smoother animations with reduced-motion support

## Reliability
- Fresh installs start with no stale jobs
- Old-session running jobs become **Interrupted** and leave the active views,
  with Resume / Restart / View Details / Remove
- Stage-specific retries preserve completed work
- Orphaned-running-job reset; frozen Windows executable icon fix; Study Packs
  badge overflow fix

## Notes
- No cloud scheduling, no background service execution, and no notifications
  while the app is fully closed. A schedule that comes due while LecturePack is
  closed is handled the next time you open it.
- Upgrading from beta.2: run the new Setup installer directly; your lectures,
  transcripts, notes, and settings are preserved.

## Verify your download
Compare the SHA-256 of the file you downloaded against
`LecturePack-0.9.0-beta.3-SHA256SUMS.txt`.
