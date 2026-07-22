# §8 Flashcard system

Mirrors §7 quizzes. Replaces the static 3-card demo with a configurable, navigable
flashcard deck.

## Backend
- `generate_flashcards(opts)` → `StudyAssistantWorker("flashcards", count)` when
  Ollama on, else deterministic `_fallback_flashcards` from key terms (labeled
  "Built-in (no AI)"). `_normalize_flashcards` accepts term/definition (+ front/back,
  q/a aliases), drops incomplete, caps to count. Cards + session persist in
  `study.json` `flashcards` key; `_emit_stored_flashcards` restores on reopen;
  `cancel_flashcards`; `save_flashcard_session`. Signals
  `flashcards_changed`/`flashcards_status`.

## Frontend
Setup: card count (5/10/20/30/custom), depth (Basic/Detailed/Exam-focused), style,
Generate/Cancel + provider. Session: flip card (tap / Space), Prev/Next (← →),
Known / Unsure (border colors), Bookmark, Shuffle (Fisher-Yates), progress
(✓/? counts), Restart, Summary. Summary: known/unsure/total tiles, Review unsure,
Restart, New settings. Session persisted via `save_flashcard_session`.

## Evidence
- `tests/test_webview_flashcards.py` (6): fallback shape/count, normalize aliases/cap,
  generate fallback + persistence, no-job error, save/restore session.
- E2E `flash_smoke.py` → FLASH_OK (real WebEngine + backend, TEMP data dir, no real
  job touched): generate → card → flip → mark known → summary.
