# Handoff — WebView Functionality Recovery

## Repository / branch
- Path: `C:\Users\marsh\Documents\LecturePack`
- Branch: `feat/desktop-webengine`
- Starting commit: `d7f4b80` (clean tree at session start)
- Ending commit: `e504551`
- Safety tag: `safety/start-webview-functionality-recovery` (= d7f4b80)
- Working tree: clean, all work committed.

## Exit outcome
**Outcome B — P0 core complete, P1 partial.** A safe checkpoint. All committed
work is green (full suite 240 passed after the Python changes; the frontend-only
timeline commit is node-checked + headless-validated).

## Completed (with evidence)
| # | Item | Status | Evidence |
|---|------|--------|----------|
| P0.1 | Blank slide thumbnails + large preview | **FIXED** | `tests/test_webview_assets.py` (17); `docs/evidence/.../asset_scheme_result.txt` (headless render ASSET_OK) |
| P0.4 | Settings controls not wired to backend | **FIXED** | `tests/test_webview_settings_bridge.py` (9) |
| P0.3 | Vulkan selection did nothing | **WIRED** (live GPU run unverified → C) | settings-bridge tests; `start_processing` applies `engine` |
| P1.4 | Ollama model discovery/selection | **FIXED** | `list_ollama_models`/`ollama_models` + UI picker |
| P0.5 | Inappropriate bundled demo content | **VERIFIED CLEAN + guarded** | `tests/test_content_hygiene.py` (2) |
| P1.7 | Timeline hover popup clipped | **FIXED** | `docs/evidence/.../timeline_hover_result.txt` (HOVER_OK) |

Details for each in `docs/WORKLOG_WEBVIEW_RECOVERY.md`.

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

## Test commands / results
- `.venv/Scripts/python.exe -m pytest -q` → **240 passed** (206s) as of commit 8eb83a4.
- `.venv/Scripts/python.exe -m pytest tests/test_webview_assets.py tests/test_webview_settings_bridge.py tests/test_content_hygiene.py -q` → **28 passed**.
- Headless WebEngine smokes (evidence dir): asset scheme `ASSET_OK`, timeline hover `HOVER_OK`.

## Not done / incomplete (next work, in priority order)
1. **P0.1 live GUI acceptance** — open the real app on ≥3 completed jobs; confirm
   thumbnails + full preview render, job-switch clears old image, missing-file
   marker shows. (Logic + scheme proven headless; needs a real window pass.)
2. **P0.3 Vulkan LIVE** — needs GPU + `whisper_vulkan_exe` set. Run a short video
   with `engine=vulkan`; capture command/output; add benchmark/validate + a visible
   fallback reason when unsupported. → Outcome C until hardware-validated.
3. **P0.2 / online transcription + speed** — NOT started. Profile first and write
   `docs/evidence/webview_recovery/baseline_performance.json`. Prior Groq work
   exists in history (`docs/HANDOFF_PHASE_V1_2_GROQ*.md`, `tests/test_groq_transcription.py`,
   `lecturepack` groq backend) — reuse it; expose Private Local / Online Fast /
   Online Accurate; secure key in Windows Credential Manager; needs a live key → C.
4. **P1.1–1.3 Quizzes** — still fixed 3 Qs, no count/difficulty/scope, no next/prev,
   correct answer doesn't advance. Needs setup controls + session state persisted in
   versioned study data + navigation + provider fallback + tests.
5. **P1 Flashcards** — configurable count/scope/style + flip/known/unsure + persistence.
6. **P1 Study assistant tabs** — Ask/Quiz/Flashcards/Notes, provider/model/scope pickers.
7. **P3 dark-mode secondary palette** — replace bright cyan fills with deep-blue
   surfaces + cyan text (tokens in the prompt); icons to `currentColor`.
8. **Accent swatches** — inert; remove from Settings per spec (keep theme only).
9. **Packaged (.exe) validation** — mandatory; WebEngine asset paths differ frozen.
   Verify `lpasset://` images, Settings, Ollama picker from a clean space-containing path.

## Exact next steps
- Graph query: `slide preview click -> JS handler -> bridge -> asset resolver` is
  DONE; next: `quiz generate -> Study bridge -> enrichment service -> UI state`.
- Next file: `app/desktop/engine_adapter.py` (`ask_ai`, `_push_study_data`, study.json)
  and `app/ui/app.js` quiz render (`#quiz-question`, study tabs ~line 260+).
- Next command: `.venv/Scripts/python.exe -m pytest tests/test_study_workflow.py -q`
  to learn the existing study/enrichment contract before extending quizzes.

## Process state
No long-running LecturePack/FFmpeg/Whisper/asset-server processes left running.
Background full-suite run (id bcmye3di7) completed (exit 0). Headless smokes exited.

## Risks
- `lpasset` scheme relies on `LocalScheme` flag — verified on Qt 6.11 headless;
  re-check after any Qt upgrade and in the frozen build.
- Timeline hover unchecked at 125/150% DPI (math is resolution-independent).

## Rollback
- Revert a single commit: `git revert <sha>` (e.g. `git revert e504551`).
- Return to the pre-session state: `git reset --hard safety/start-webview-functionality-recovery`
  (destructive to these commits only; does not touch `~/LecturePackData`).
