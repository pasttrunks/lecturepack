# Handoff — WebView Functionality Recovery

## Repository / branch
- Path: `C:\Users\marsh\Documents\LecturePack`
- Branch: `feat/desktop-webengine`
- Original starting commit: `d7f4b80` (session 1) → this session started at `b35e743` (= e504551 + docs)
- Ending commit: `2bba754`
- Last fully green commit: `2bba754` (full suite 245 passed)
- Safety tags: `safety/start-webview-functionality-recovery` (= d7f4b80),
  `safety/start-post-e504551-continuation` (= e504551),
  `safety/start-post-6d847d0-continuation` (= 6d847d0)
- Working tree: clean.

## Exit outcome
**Outcome B — P0 usability complete (incl. preview readability), validated live
(source) and packaged app boots; Study tools + speed still pending.** All
committed work is green: full suite **245 passed at `2bba754`**; packaged exe
boots (`PACKAGED_SMOKE_OK`).

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

Details for each in `docs/WORKLOG_WEBVIEW_RECOVERY.md`.

## This session's commits
- `9c5dc62` feat(review): open-job from Home + live slide-preview acceptance (16/16)
- `6d847d0` fix(packaging): frozen WebEngine app boots (entry wrapper + _MEIPASS ui path)
- `2bba754` fix(review): fit full-resolution slides to preview canvas (+ zoom/pan)

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

## Not done / incomplete (next work, in priority order)
1. **P0.3 Vulkan LIVE** (Phase 3) — needs GPU + `whisper_vulkan_exe` set. Run a
   short video with `engine=vulkan`; capture command/output; add a visible
   Benchmark/Validate action + fallback reason. → Outcome C until hardware-validated.
2. **P0.2 / online transcription + speed** (Phase 4) — NOT started. Profile a
   60–75 min lecture first → `docs/evidence/.../performance/baseline.json`. Prior
   Groq work exists (`docs/HANDOFF_PHASE_V1_2_GROQ*.md`,
   `tests/test_groq_transcription.py`, `lecturepack` groq backend + `WindowsCredentialStore`)
   — reuse it; expose Private Local / Online Fast / Online Accurate; needs a live key → C.
   NOTE surfaced by Phase 1: the m2 job stores 1920×1080 ~2.5 MB PNGs; generating
   small thumbnails off the critical path is a concrete P2 win (167×2.5 MB decoded
   for 60×38 thumbnails is heavy).
3. **P1.1–1.3 Quizzes** (Phase 5) — still fixed 3 Qs, no count/difficulty/scope,
   no next/prev, correct answer doesn't advance. Needs setup controls + session
   state persisted separately from the raw transcript + navigation + fallback + tests.
4. **P1 Flashcards** (Phase 6) — configurable count/scope/style + flip/known/unsure + persistence.
5. **P1 Study assistant tabs** (Phase 7) — Ask/Quiz/Flashcards/Notes; use the
   Settings-selected Ollama model.
6. **P3 dark-mode secondary palette** (Phase 8) — deep-blue surfaces + cyan text
   tokens; icons to `currentColor`; remove inert accent swatches.
7. **Interactive packaged acceptance** — open the (now-booting) exe and click
   through thumbnails/Settings/Ollama/hover. Needs a human.

## Exact next steps
- Next graph query: `quiz generate -> Study bridge -> enrichment service -> UI state`.
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
