# §7 Quiz system

Replaces the static 3-question demo with a configurable, navigable quiz.

## Generation (backend)
- `generate_quiz(opts)` builds a quiz via `StudyAssistantWorker("quiz", …, count)`
  (Ollama) when local AI is on; otherwise a **deterministic built-in fallback**
  from the lecture's key terms — always works, clearly labeled "Built-in (no AI)".
- `_normalize_quiz` validates/repairs LLM output (clamps correct_index, drops
  malformed, caps to count). Questions + session persist in `study.json`
  (`quiz` key) — separate from the immutable transcript. `_emit_stored_quiz`
  restores questions + session when a job is reopened. `cancel_quiz` stops an
  in-flight generation. Signals: `quiz_changed`, `quiz_status`.

## Session (frontend)
Setup: question count (3/5/10/20/custom), difficulty, type, source, Generate /
Cancel + provider indicator. Session: Question X of N, options A–D, **Submit
reveals correct/incorrect + explanation and enables Next** (fixes "correct answer
doesn't advance"), Previous/Next, flag-for-review, score, auto-advance toggle,
Finish. Summary: score + per-question result, Retry incorrect / Restart / New
settings. Session persisted via `save_quiz_session` (resume after reopen).

## Evidence
- Unit tests `tests/test_webview_quiz.py` (8): fallback shape/count, distractors ∉
  lecture terms, correct-index varies, normalize repair/cap, generate fallback
  when AI off + persistence, no-job error, save/restore session.
- End-to-end `quiz_smoke.py` → QUIZ_OK (real WebEngine + backend, TEMP data dir):
  generate → session (Q1/N, 4 opts) → pick+Submit reveals + Next enabled → Finish
  → summary score 2/5. No real job touched.

## Not yet (documented next)
Difficulty/type/source are recorded with the quiz but the AI prompt currently
varies by count only (fallback ignores them); short-answer type and slide-sourced
questions are future work. §8 flashcards mirror this design.
