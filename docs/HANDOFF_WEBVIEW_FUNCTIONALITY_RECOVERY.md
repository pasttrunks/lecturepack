# Handoff — WebView Functionality Recovery

> **Corrected 2026-07-21** during the post-`08f649f` verification & live-acceptance
> pass. All stale sections (HEAD `6d847d0`, `245 passed`, the "Quiz plan — READY TO
> EXECUTE" block, and the contradictory clean/dirty scratch-file notes) were removed
> because current-code inspection + a green suite prove those features are shipped.
> This file now contains only verified current truth.

## Repository / branch / state (verified)
- Path: `C:\Users\marsh\Documents\LecturePack`
- Branch: `feat/desktop-webengine`
- **HEAD: `76d69e8`** — one docs-only commit above `08f649f`
  (`git diff --stat 08f649f 76d69e8` = only this handoff + `status.json`).
  The **code under test is byte-identical to `08f649f`**.
- **Last fully green commit: `76d69e8`** — full suite **291 passed in 200s, exit 0**
  (run this session; supersedes the old "245 at 6d847d0").
- Working tree: **clean**. The scratch files a prior handoff listed as untracked
  (`tests/scratch/live_slide_acceptance.py`, `.../smoke_packaged_launch.py`) **do
  not exist**; the tracked copies live under `docs/evidence/...`.
- Safety tags: `safety/start-08f649f-live-acceptance` (=`08f649f`, this pass),
  plus prior `safety/start-webview-functionality-recovery` (=`d7f4b80`),
  `safety/start-post-e504551-continuation` (=`e504551`),
  `safety/start-post-6d847d0-continuation` (=`6d847d0`).

## Exit outcome
All P0/P1 + §3–§10 features are **implemented, tested, and committed**; suite is
green at HEAD. Automated/headless acceptance is complete. **Three items remain
live-validation-blocked (Outcome C)** — real GPU benchmark, a real long-lecture
cold run, and a real Groq key — and a **human windowed/packaged click-through**
is the remaining manual acceptance. None of these are code gaps.

## Feature-by-feature verified status (this pass)
Verified by code inspection (paths below) + the green suite + the named-scenario
harness. "UI control" = present in the rendered `#quiz-root`/`#flash-root` markup.

### Quiz (§7) — VERIFIED WORKING
- Controls present: **count** (3/5/10/20 + custom 1–50), **difficulty**
  (Easy/Medium/Hard/Mixed), **type** (Multiple choice / True-false / Mixed),
  **source** (Transcript/Slides/Both), **Generate**, **Resume last**, **Cancel**
  (in the progress bar → `cancel_quiz`), **Prev/Next**, **Submit**, **Finish**,
  **Flag**, **auto-advance**, live **score**, **explanation reveal**,
  **Retry incorrect**, **Restart**, **Copy**, **New quiz settings** (= regenerate),
  **persistence/resume** (`save_quiz_session` → `study.json`).
- Correct answer ENABLES Next (the old "correct answer doesn't advance" bug is gone).
- Model handling: `generate_quiz` resolves the model from Settings via
  `_ollama_settings()`; provider shown as `Local · <model>` or **`Built-in (no AI)`**
  for the deterministic grounded-cloze fallback — no hardcoded model override.
- Named-scenario acceptance: **3-question and 20-question** runs deliver 3 and 20,
  `state=ready`, valid shape, session save/restore OK
  (`named_scenario_acceptance/result.txt` → `NAMED_SCENARIOS_OK`).
- **Documented gaps (enhancement, not defects — not fixed in this verify pass):**
  `scope` is recorded in settings but has **no UI selector**; questions carry an
  `explanation` but **no explicit transcript/slide source citation**.
- Code: `app/desktop/engine_adapter.py` `generate_quiz`/`cancel_quiz`/`_save_quiz`/
  `_fallback_quiz_questions`/`_normalize_quiz`; `app/ui/app.js` `renderQuiz`/
  `renderQuizQuestion`/`renderQuizSummary`/`quizAction`; tests `tests/test_webview_quiz.py`.

### Flashcards (§8) — VERIFIED WORKING
- Controls present: **count** (5/10/20/30 + custom 1–60), **depth/difficulty**
  (Basic/Detailed/Exam-focused), **style** (Term→def / Q→A / Concept→explanation /
  Mixed), **Generate**, **Resume**, **Cancel** (`cancel_flashcards`), **Flip**,
  **Prev/Next**, **Known**, **Unsure**, **Shuffle**, **Restart**, **Review unsure**
  (retry), progress counts, **persistence/resume** (`save_flashcard_session`).
- Named-scenario acceptance: **5-card and 20-card** runs deliver 5 and 20,
  `state=ready`, session save/restore OK.
- **Documented gap:** `scope` recorded but no UI selector; cards use the grounding
  sentence as the back but no explicit clickable source link.
- Code: `engine_adapter.generate_flashcards`/`_fallback_flashcards`/
  `_normalize_flashcards`; `app.js` `renderCard`/`renderCardSession`/`flashAction`;
  tests `tests/test_webview_flashcards.py`.

### Study Assistant tabs (§9) — VERIFIED
- Tabs: Ask / Quiz / Flashcards / Notes. Selected Ollama model is used
  (`ask_ai` builds the worker from `_ollama_settings()`); provider/model indicator
  reflects real provider; notes autosave (`save_notes`); copy/export present.
- Generation shows a **progress bar + ETA + Cancel** (replaces the old spinner —
  `_genBar` in `app.js`). Key-terms panel removed per request.

### Groq online transcription (§6) — VERIFIED WIRED; live run = Outcome C
- Settings "Transcription" card: Private Local / Online Fast / Online Accurate
  selector persists to `transcription_backend`; Set / Test / Remove key via the OS
  Credential Manager (`WindowsCredentialStore`). `test_groq_key` performs a **real**
  `GroqHttpClient().test_key()`; with no key it honestly reports "No API key stored".
- Backend reused from the contract-tested Groq service. **No live transcription is
  claimed** — needs a real `gsk_…` key (see blockers).
- Code: `engine_adapter` `set_groq_key`/`remove_groq_key`/`test_groq_key`/
  `_emit_groq_status`; tests `tests/test_webview_groq.py` (6, network/OS mocked).

### Vulkan validate (§3) — VERIFIED HONEST; live speed = Outcome C
- `validate_vulkan` reports **available / selected / loaded / unavailable+reason**
  via the real `EngineRegistry.detect_engines()` + `resolve()`; never silently CPU.
- Vulkan is genuinely present on this machine (registry resolves Vulkan). A
  **CPU-vs-Vulkan wall-time comparison is NOT claimed** — needs a same-video run.
- Code: `engine_adapter.validate_vulkan`; tests `tests/test_webview_vulkan.py` (3).

### Earlier items (unchanged, still verified)
- Slide thumbnails + large preview via `lpasset://` resolver, fill-canvas fit +
  zoom/pan (`app/desktop/assets.py`); live 16/16 on 3 real jobs.
- Settings↔engine bridge; Ollama model discovery; timeline hover; open-job from
  Home; content hygiene; **packaged exe boots** (entry wrapper + `_MEIPASS`).
- Home job **delete** (Recycle Bin via send2trash) + course **grouping**.
- §5 lazy WebP thumbnail cache; §4 per-stage timing → `<job>/performance.json`;
  §10 deep-blue/cyan dark-theme secondary palette.

## Acceptance performed this pass
1. **Git truth check** — branch/HEAD/status/log/tags recorded above.
2. **Full suite at HEAD `76d69e8`** — `291 passed in 200.36s`, exit 0.
3. **Named-scenario headless acceptance** — 3-q + 20-q quiz, 5 + 20-card flashcards,
   session save/restore, all against a temp dir with AI off →
   `docs/evidence/.../named_scenario_acceptance/` (`NAMED_SCENARIOS_OK`).
4. **Code inspection** of every claimed control (bridge slots/signals, adapter
   methods, `app.js` render functions, `index.html` markup).

## Remaining work (honest — nothing is a code gap)
### Live-validation blocked (Outcome C) — need resources this env lacks
1. **§3 CPU-vs-Vulkan benchmark** — run the same short video once with
   `engine=cpu` and once with `engine=vulkan`; record backend/exe/model/wall-time/
   word-count/first+final timestamps/exit code/fallback reason/footer-manifest
   backend. Evidence dir: `docs/evidence/.../vulkan/`.
2. **§4 cold `baseline.json`** — process a genuinely unprocessed 60–75 min A/V
   lecture (must contain an audio track — the synthetic clip has none). The §4
   instrumentation auto-writes `<job>/performance.json`; copy it to
   `docs/evidence/.../performance/baseline.json`. My earlier run hit the content
   cache (`cached=true`), so it is **not** a cold baseline.
3. **§6 live Groq** — store a real `gsk_…` key (Set key), then run Online Fast and
   Online Accurate on the same short video; verify local fallback, privacy consent,
   no secret leakage, and a timing/quality comparison. No key available here.

### Human manual acceptance
4. **Windowed + packaged click-through** — everything above is headless/offscreen
   or unit-tested. A human should open the source app AND the packaged exe and
   click through Home → grouping → delete-to-Recycle-Bin (disposable data only) →
   Review thumbnails/preview/zoom/pan → timeline hover → Transcript → Study
   (Quiz/Flashcards/Ask/Notes) → Settings (Ollama picker, Vulkan validate, theme)
   → Exports, on the m2 / Egypt / Mesopotamia jobs. Save shots under
   `docs/evidence/.../final_interactive_source/` and `.../final_interactive_packaged/`.
   *(Not performed here: this environment cannot drive the native Qt window, and
   fabricating screenshots is not acceptable.)*

## Never touch
`C:\Users\marsh\LecturePackData` — read-only for inspection; destructive tests use
temp copies. No real job was deleted or modified in any verification here.

## Rollback
- Undo the docs commit only: `git reset --hard 08f649f` (code unchanged either way).
- Revert one commit: `git revert <sha>`.
- Back to this pass's baseline: `git reset --hard safety/start-08f649f-live-acceptance`.
- Back to session-1 start: `git reset --hard safety/start-webview-functionality-recovery`
  (=`d7f4b80`). None of these touch `~/LecturePackData`.

## Process state
No long-running LecturePack/FFmpeg/Whisper/pytest processes left running; the
verification suite (`b451xikb2`) exited 0 and the acceptance harness exited 0.
