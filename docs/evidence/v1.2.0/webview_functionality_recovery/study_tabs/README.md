# §9 Study assistant tabs polish

- **Tabs**: renamed "Chat" → **Ask**; added a **Notes** tab (Ask / Quiz /
  Flashcards / Notes).
- **Notes**: a per-job free-text notepad, auto-saved (600ms debounce) to
  `study.json` (`notes` key) via `save_notes`, restored on job open through the
  `study_changed` payload; a **Copy** button copies it to the clipboard.
- **Provider/model indicator**: the study header badge now shows the ACTUAL
  provider + model in use (e.g. "Local · llama3:8b"), driven by `ai_status`, and
  dims to grey for "AI off"/"Unavailable" — confirming the Settings-selected
  Ollama model is what's used (no hardcoded qwen3:1.7b). Quiz/flashcard setup also
  shows the provider of the last generation.
- **Copy/export**: quiz summary and flashcard summary gained **Copy** buttons
  (plain-text export of Q&A / term–definition), plus a `file://`-safe clipboard
  helper (`copyText`).
- Cancel/Regenerate and scope/difficulty/type controls already exist on quiz +
  flashcards; source grounding shows in quiz explanations ("From the lecture: …").

## Evidence
- `tests/test_webview_quiz.py::test_save_notes_persists` (round-trip + clear).
- E2E notes_smoke.py → NOTES_OK (real WebEngine, TEMP job): Notes tab shows,
  textarea + Copy present, typing persists to study.json via the bridge.
