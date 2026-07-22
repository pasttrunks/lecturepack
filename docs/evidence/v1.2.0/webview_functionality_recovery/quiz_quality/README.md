# Quiz/flashcard quality + generation progress bar

Three improvements requested by the user.

## 1. Progress bar + ETA (replaces the spinning circle)
Quiz and flashcard generation now show a determinate-style progress bar with a
percent and a rough "~Ns remaining" ETA (estimate = 3.5 + 1.6·count seconds),
capped at ~93% until the real result lands, then it completes. Shared `_genBar`/
`startGen`/`stopGen` in app.js; a 250ms timer animates it; Cancel still works.
The old `lpspin` circle is gone from both generating states.

## 2. Genuinely better quizzes
### AI path (Ollama)
`_quiz_prompt` rewritten (lecturepack/services/study_assistant_service.py): demands
questions grounded in a SPECIFIC transcript fact/name/number, exactly one correct
option, plausible on-topic distractors, no meta questions about "the lecture", no
"all/none of the above". Difficulty and question type are now threaded through the
worker into the prompt (were previously ignored). Flashcard prompt similarly
strengthened (grounding + depth).

### Deterministic fallback (no AI) — the big fix
Replaced the weak "Which of the following is a key term?" quiz with **grounded
cloze (fill-in-the-blank) questions built from real transcript sentences**: a
sentence mentioning a key term is blanked, and distractors are other key terms
that do NOT appear in that sentence (so the answer is unambiguous). Key terms are
cleaned first (`_clean_terms` drops stopwords/filler like "one", "it's", "see",
"know", "world"). Flashcard fallback backs each term with the actual lecture
sentence that introduces it, not a generic prompt.

Real-transcript sample (Mesopotamia job, READ-ONLY, no data written):
    cleaned terms: ['Babylon', 'city', 'Mesopotamia', 'gardens', 'ancient']
    Q: Fill in the blank: ...the empires of Assyria and _____.        → Babylon
    Q: Fill in the blank: ...a constellation of competing _____ states. → city
    Q: Fill in the blank: ...when the Ottoman state ... ruled over _____ → Mesopotamia
(Before: every question was "Which of the following is a key term from this lecture?"
with unrelated generic distractors.)

## 3. Key-terms panel removed
The low-value "Key terms" chip list (which showed junk like "one"/"see") is gone
from the Study overview, giving the assistant/quiz more vertical space. Key terms
are still computed internally to seed the fallback generators.

## Tests
tests/test_webview_quiz.py (8) + tests/test_webview_flashcards.py (6) updated for
the grounded design (cloze shape, unambiguous distractors, stopword dropping,
grounded flashcard definitions). Existing study/worker tests still green.
