# Named-scenario acceptance — quiz & flashcards (§7/§8)

**Type:** headless backend acceptance (NOT an interactive click-through).
**Data:** throwaway `tempfile.TemporaryDirectory()` — `~/LecturePackData` untouched.
**AI:** off — exercises the deterministic grounded-cloze fallback, so it is
reproducible on any machine with no Ollama.

Run:

```
.venv/Scripts/python.exe docs/evidence/v1.2.0/webview_functionality_recovery/named_scenario_acceptance/harness.py result.txt
```

## What it proves (the sizes the acceptance prompt names)
| Scenario | Expected | Observed (result.txt) |
|---|---|---|
| Quiz, 3 questions | 3 delivered, `state=ready`, valid shape | 3, ready, shape_ok |
| Quiz, 20 questions | ≥15 grounded (fallback caps at usable terms) | 20 |
| Quiz session | save → reload restores `index` | index=2 restored |
| Flashcards, 5 cards | 5 delivered, `state=ready` | 5, ready |
| Flashcards, 20 cards | ≥15 grounded | 20 |
| Flashcard session | save → reload restores `index` | index=3 restored |

`RESULT: NAMED_SCENARIOS_OK` (exit 0).

Provider is honestly labelled **"Built-in (no AI)"** because no Ollama is
running in this harness; with a local model selected in Settings the same path
labels it `Local · <model>` (see `engine_adapter.generate_quiz`).

## Scope / honesty
This validates the **adapter + persistence contract** at the named sizes. It is
not a substitute for a human windowed click-through of the native/packaged app
(mouse-driven Generate/Submit/Next/Flip/Shuffle etc.), which remains the final
human acceptance step — see the handoff's "Remaining" section.
