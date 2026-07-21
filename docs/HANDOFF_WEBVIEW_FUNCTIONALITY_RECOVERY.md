# Handoff — WebView Functionality Recovery

## Repository / branch
- Path: `C:\Users\marsh\Documents\LecturePack`
- Branch: `feat/desktop-webengine`
- Original starting commit: `d7f4b80` (session 1)
- Ending commit: `08f649f` (+ docs)
- Last fully green commit: `08f649f` (full suite **291 passed**, exit 0)
- Safety tags: `safety/start-webview-functionality-recovery` (= d7f4b80),
  `safety/start-post-e504551-continuation` (= e504551),
  `safety/start-post-6d847d0-continuation` (= 6d847d0)
- Working tree: clean.

## Exit outcome
**All V3 phases (P0/P1 + §3–§10) IMPLEMENTED + tested; full suite 291 passed;
packaged exe boots.** Three items remain **live-validation-blocked (Outcome C)**,
with architecture + tests complete and exact steps documented:
- §3 live CPU-vs-Vulkan wall-time benchmark (user-runnable; Vulkan confirmed working)
- §4 cold `baseline.json` (needs a real unprocessed 60–75 min lecture run; the
  instrumentation writes it automatically)
- §6 live Groq Online Fast/Accurate (needs a real Groq API key)
Interactive native-window/packaged click-through still benefits from a human pass
(everything so far is headless/offscreen-validated).

## Completed (with evidence)
| # | Item | Status | Evidence |
|---|------|--------|----------|
| P0.1 | Blank slide thumbnails + large preview | **FIXED + LIVE-VALIDATED** | `tests/test_webview_assets.py` (17); `live_slide_acceptance/` **16/16 ALL_OK** on 3 real jobs (egypt 11, Mesopotamia 167, m2 7) |
| P0 | Main preview tiny (unreadable) | **FIXED** | `slide_preview_scaling/` — 55%→**92%** width; zoom ZOOM_OK; fill-canvas + zoom/pan `previewCtl` |
| — | Open job from Home grid | **FIXED** | `open_job` bridge/adapter + click handler; harness `open_job via Home card` |
| P0.4 | Settings controls not wired to backend | **FIXED** | `tests/test_webview_settings_bridge.py` (10) |
| P0.3 | Vulkan selection did nothing | **WIRED** (live GPU run unverified → C) | settings-bridge tests; `start_processing` applies `engine` |
| P1.4 | Ollama model discovery/selection | **FIXED** | `list_ollama_models`/`ollama_models` + UI picker |
| P0.5 | Inappropriate bundled demo content | **VERIFIED CLEAN + guarded** | `tests/test_content_hygiene.py` (2) |
| P1.7 | Timeline hover popup clipped | **FIXED** | `docs/evidence/.../timeline_hover_result.txt` (HOVER_OK) |
| Ph2 | Packaged exe was dead on arrival | **FIXED (boots)** | `docs/evidence/.../packaged/` PACKAGED_SMOKE_OK; `tests/test_webview_packaging.py` (4) |
| §5 | Full-res PNGs decoded for tiny thumbs | **FIXED** | `thumbnail_cache/` WebP 192× smaller; non-blocking bg gen; `test_webview_assets.py` |
| user | Delete jobs (free space) | **DONE** | Recycle Bin (send2trash) + confirm modal; `test_webview_jobs.py` (delete tests) |
| user | Group lectures by course/subject | **DONE** | manifest `group` + derived default; grouped Home; `test_webview_jobs.py` |

Details for each in `docs/WORKLOG_WEBVIEW_RECOVERY.md`.

## This session's commits
- `9c5dc62` feat(review): open-job from Home + live slide-preview acceptance (16/16)
- `6d847d0` fix(packaging): frozen WebEngine app boots (entry wrapper + _MEIPASS ui path)
- `2bba754` fix(review): fit full-resolution slides to preview canvas (+ zoom/pan)
- `655aed6` perf(review): lazy background thumbnail cache (WebP, 192× smaller)
- `a1ff43d` feat(home): delete jobs to Recycle Bin + group lectures by course
- `b760fef` feat(study): configurable quiz sessions (§7)
- `70897f9` feat(study): configurable flashcard sessions (§8)
- `1b2ece7` feat(study): Ask/Notes tabs, model indicator, copy/export (§9)
- `7b6b0c0` feat(study): progress bar + ETA, grounded quizzes, remove key-terms
- `e1894b9` fix(theme): deep-blue secondary surfaces + cyan text (§10)
- `40d759c`+`b5832ba` fix(backends): Vulkan validate action + honest status (§3)
- `daf7281` feat(perf): per-stage timing instrumentation → performance.json (§4)
- `08f649f` feat(transcription): expose secure Groq online modes in WebView (§6)

## Untracked / dirty
- `tests/scratch/live_slide_acceptance.py`, `tests/scratch/smoke_packaged_launch.py`
  (working copies; tracked equivalents live under `docs/evidence/.../`).
- `dist/`, `build/` are gitignored PyInstaller output (freshly rebuilt from source).

## Changed files
- `app/desktop/assets.py` (new) — central `lpasset://` asset resolver + scheme.
- `app/desktop/main.py` — register scheme, install handler on profile.
- `app/desktop/bridge.py` — `log_asset_error`, `ollama_models` signal, `list_ollama_models` slot.
- `app/desktop/engine_adapter.py` — slides `img`; `on_setting_changed` bridge;
  `_settings_payload`; engine applied to job; `actual_backend`; `list_ollama_models`.
- `app/ui/index.html` — slide-frame img target; editable endpoint; model picker; hover portal markup.
- `app/ui/app.js` — `slideImg`, real slide images, compute/endpoint/model wiring, collision-aware hover.
- `app/ui/bridge.js` — register `ollama_models` signal.
- `tests/test_webview_assets.py`, `tests/test_webview_settings_bridge.py`, `tests/test_content_hygiene.py` (new).

## Test commands / results (current HEAD 6d847d0)
- `.venv/Scripts/python.exe -m pytest -q` → **245 passed** (~205s) at `6d847d0`.
- Live acceptance: `python docs/evidence/.../live_slide_acceptance/harness.py <out.json>` → **16/16 ALL_OK**.
- Packaged smoke: `python docs/evidence/.../packaged/smoke_packaged_launch.py` → **PACKAGED_SMOKE_OK**.
- Headless WebEngine smokes: asset scheme `ASSET_OK`, timeline hover `HOVER_OK`.

## Remaining (live-validation only — implementation complete)
All feature phases are implemented, tested, and committed. What's left needs
resources this environment lacks; each has complete code + tests + documented steps:
1. **§3 Vulkan live benchmark** — `validate_vulkan` reports honest status and
   Vulkan is confirmed working here; a fresh CPU-vs-Vulkan wall-time run writes a
   job (user-initiated). `docs/evidence/.../vulkan/`.
2. **§4 cold `baseline.json`** — instrumentation writes `<job>/performance.json`
   on every completed run; process a real unprocessed 60–75 min lecture to capture
   cold timings. `docs/evidence/.../performance/`.
3. **§6 live Groq** — WebView key mgmt + mode selector wired to the (contract-
   tested) backend; needs a real `gsk_…` key to run Online Fast/Accurate.
   `docs/evidence/.../groq/`.
4. **Interactive native/packaged click-through** — headless/offscreen-validated;
   a human pass on the real window / packaged exe is the final acceptance.

## §7 Quiz plan — READY TO EXECUTE (contract already learned this session)
Existing infra to reuse (do NOT reinvent):
- `lecturepack/services/study_assistant_service.py`: `StudyAssistantWorker(task, transcript_text, ollama, history=, question=, count=)`
  with `task="quiz"` → `finished_ok(task, result)` / `failed(kind,msg,details)`;
  `_quiz_prompt(text, count)` defines the question schema. QThread — wire exactly
  like `LecturePackAdapter.ask_ai` (engine_adapter.py ~890).
- `lecturepack/services/study_service.py`: `save_quiz(job, questions)` /
  `load_quiz(job)` persist under `study.json` `"quiz"` key (separate from the raw
  transcript — satisfies the "persist separately" requirement). Also
  `load_study_data`/`save_study_data` for session state (add a `"quiz_session"` key).
Steps:
1. engine_adapter: `generate_quiz(opts)` — build transcript_text (respect scope
   later; start with entire lecture), run `StudyAssistantWorker("quiz", …, count)`;
   on ok → `save_quiz` + emit `quiz_changed` {questions, provider, model}; on
   fail/AI-off → deterministic fallback quiz from `study_service.build_overview`
   key_terms/sections (no LLM) so it always works. Add `cancel` (worker.stop).
2. bridge.py: `@Slot(str) generate_quiz(json)`, `@Slot() cancel_quiz`,
   `@Slot(str) save_quiz_session(json)`; signals `quiz_changed`, `quiz_status`.
   Add both to bridge.js SIGNALS.
3. app.js: replace the static demo quiz (renderQuiz, `#quiz-options`,
   `quizPicked/quizAnswered`, `btn-retry-quiz`) with a session state machine over
   `LP.data.quiz.questions`: index/total, Previous/Next, Submit, score, correct
   answer ENABLES Next (fixes "correct answer doesn't advance"), explanation,
   finish, retry-incorrect, restart; persist via `save_quiz_session`.
   Setup controls (count now; difficulty/scope/type/source next) + Generate/
   Regenerate/Cancel + provider/model indicator.
4. Tests (tests/test_study_workflow.py style): deterministic fallback generation
   (no Ollama), save/load round-trip, session scoring/navigation logic. AI path via
   the existing worker tests / mock.
Then §8 flashcards mirror this (StudyAssistantWorker "flashcards", save_flashcards).

Design note (deterministic fallback): a *good* no-AI quiz is hard (no semantics
from key terms alone). Recommended: when AI is unavailable, generate honest
"recall" questions from `build_overview` key_terms/sections and LABEL the quiz
"Built-in (no AI)" in the provider indicator, rather than pretending it's
LLM-quality. Persist quiz + live session under `study.json` via
`load_study_data`/`save_study_data` (it preserves unknown keys, so a
`quiz`={questions,meta,session} shape works without changing the service).
Quiz item schema (from QUIZ_SCHEMA): `{question, options[], correct_index, explanation}`.

## Exact next steps
- Next graph query: `quiz generate -> Study bridge -> enrichment service -> UI state` (contract above).
- Next files: `app/desktop/engine_adapter.py` (`ask_ai`, `_push_study_data`,
  study.json around lines 760–830) and `app/ui/app.js` quiz render (`#quiz-question`,
  `#quiz-*`, study tabs ~line 260+) + `app/ui/index.html` quiz markup (~line 288).
- Next command: `.venv/Scripts/python.exe -m pytest tests/test_study_workflow.py tests/test_study_workspace_v12.py -q`
  to learn the existing study/enrichment contract before extending quizzes.
- For Vulkan (Phase 3): trace `engine` in `job_controller.py:463`
  (`self.engine_registry.resolve`) and `whisper_vulkan_exe` in ConfigManager.

## Process state
No long-running LecturePack/FFmpeg/Whisper/asset-server/pytest processes left
running. All background builds/suites (ids bx20g3eah, bi0vhfeeb, b7m5yjkfz, …)
completed (exit 0). Headless smokes and packaged smoke launches terminated and
cleaned up their temp copies.

## Risks
- `lpasset` scheme relies on `LocalScheme` flag — verified on Qt 6.11 headless AND
  in the frozen build (packaged smoke). Re-check after any Qt upgrade.
- Live acceptance is headless/offscreen; a real windowed pass on the user's GPU is
  still worthwhile. Large-PNG thumbnail decode latency is a real perf item (P2).
- Timeline hover unchecked at 125/150% DPI (math is resolution-independent).
- Packaging: entry is now `app/lecturepack_desktop.py`; keep the spec in sync.

## Rollback
- Revert a single commit: `git revert <sha>` (e.g. `git revert 6d847d0`).
- Return to this session's start: `git reset --hard safety/start-post-e504551-continuation`
  (= e504551; keeps session-1 work).
- Return to session-1 start: `git reset --hard safety/start-webview-functionality-recovery`
  (= d7f4b80). Neither touches `~/LecturePackData`.
