# WebView Functionality Recovery — Worklog

Branch: `feat/desktop-webengine`
Safety tag: `safety/start-webview-functionality-recovery`
Start commit: `d7f4b80`

Concise log of decisions + evidence. Newest first.

---

## Home job management — delete + grouping (user-requested, DONE)

**Delete (user-confirmed, recoverable):** Home card trash button → confirmation
modal → `delete_job(job_id)`. Backend prefers `send2trash` (Recycle Bin —
recoverable + frees space), hard `shutil.rmtree` fallback. Guarded by safe job-id
regex + must resolve directly under `jobs/` (traversal/absolute rejected). Never
automatic — only from explicit UI confirm. Reports freed size via `job_deleted`.

**Grouping:** tag button → input modal → `set_job_group(job_id, group)` persisted
in the manifest; blank reverts to title-derived default (`_derive_group`:
"CL100 - Day 3 -…"→CL100). `_list_jobs` emits `group`; Home renders a section per
group (header + count).

**Files:** `engine_adapter.py` (delete_job/set_job_group/_derive_group/guards +
group in _list_jobs), `bridge.py` (slots + job_deleted signal), `bridge.js`
(signal), `app.js` (grouped renderJobs, lpModal/toast helpers, per-card
delete/group buttons), `requirements.txt` (Send2Trash).

**Safety:** no real job deleted/modified in dev or tests — `tests/test_webview_jobs.py`
(12) use a TEMP data dir with send2trash monkeypatched; UI smoke only opens modals
and clicks Cancel. Evidence: `docs/evidence/.../home_jobs/`.

---

## §5 — Lazy thumbnail cache (DONE)

**Issue:** list/grid decoded full-res ~2.5 MB PNGs into 60×38 boxes (167×2.5 MB ≈
400 MB on a long job).

**Fix (assets.py + engine_adapter + app.js):** new `lpasset://thumb/...` host;
`resolve_thumb` is non-blocking — serves fresh cached WebP if present, else serves
full-res immediately and generates the thumbnail on a 2-worker background pool
(deduped). Thumbs: WebP (JPEG fallback), max 320px, cached at
`frames/thumbs/v1/<name>.webp`, fresh when `thumb.mtime>=src.mtime`, schema-dir
bump invalidates; live+archived; originals untouched. Slides payload carries
`img` (full-res, preview/export) + `thumb` (list/grid/hover).

**Why non-blocking:** first attempt generated synchronously in the handler →
starved the main thread (2/167 thumbs + preview naturalWidth=0 in the harness).
Background generation fixed it (16/16 ALL_OK again).

**Evidence:** `docs/evidence/.../thumbnail_cache/` — WebP reduction **192×** (m2
1080p), **63×** (Mesopotamia sample). Tests: `test_webview_assets.py` (+5). Live
harness 16/16.

**Remaining risk:** first (cold) open still renders full-res while thumbs warm in
background; a real windowed cold-vs-warm scroll timing needs a human. Executor is
app-lifetime (not explicitly shut down).

---

## P0 — Main slide preview was tiny (FIXED)

**Issue:** the slide image loaded but rendered tiny in the center preview,
surrounded by unused canvas — text unreadable.

**Graph path (from prior sessions, no re-scan):** `renderSlides` (app.js) →
`#slide-frame` (index.html) → image element/CSS.

**Root cause (measured):** `#slide-frame` was locked to `width:74%` +
`aspect-ratio:16/9`; a 4:3 image was letterboxed inside that fixed 16:9 frame, so
it occupied only **55% width / 19% area** of the canvas (egypt, 1024×768). Not the
thumbnail URL/component — purely the fixed frame sizing.

**Fix (app.js + index.html):** `#slide-frame` is now a fill-canvas
(`width/height:100%`, 16px padding, `overflow:hidden`). New `previewCtl` module
renders the full-resolution `cur.img` and fits it with
`fit = min(availW/natW, availH/natH)`, re-fitting on Review-show (`setScreen`) and
on resize (ResizeObserver) — needed because `renderSlides` can run while Review is
`display:none` (0×0), which otherwise clamped to min zoom. Adds Fit / 100% / − / +
/ Reset controls, Ctrl+wheel zoom-at-cursor, double-click Fit↔100%, drag-pan when
zoomed. Zoom range 25–400% (natural-pixel scale). Missing image → `#preview-ph`
marker + red label.

**Evidence:** `docs/evidence/.../slide_preview_scaling/` — after: **92% width**
(egypt 4:3 + m2 16:9); zoom probe ZOOM_OK (Fit 422 / 100% 1024 / +1280 / reset 422).
Live acceptance harness re-run **16/16 ALL_OK** (missing-file check updated to
`#preview-ph`; harness made path-robust).

**Note:** full-res vs downscaled-thumbnail split (`thumbnailUrl`/`fullImageUrl`)
deferred to the thumbnail-perf task (§5); preview already uses full-res `cur.img`.

**Remaining risk:** native-window screenshots + 125/150% DPI need a human; fit math
is resolution-independent.

---

## Phase 2 — Packaged WebEngine validation (2 frozen blockers FIXED)

Rebuilt the onedir package and found the packaged app was **dead on arrival**
(both bugs pre-existing, not from this recovery):

1. **Startup ImportError** — PyInstaller ran `desktop/main.py` as `__main__`, so
   `from . import version` crashed with "attempted relative import with no known
   parent package". Fix: new entry wrapper `app/lecturepack_desktop.py`
   (`from desktop.main import main`); spec Analysis now points at it.
2. **UI not found when frozen** — `paths.app_root()` returned `dirname(exe)` but
   PyInstaller 6 bundles data under `sys._MEIPASS` (onedir `_internal/`). Fix:
   `app_root()` returns `_MEIPASS` when it contains `ui/`, else exe-dir fallback.

**Files:** `app/desktop/paths.py`, `app/lecturepack_desktop.py` (new),
`app/packaging/lecturepack.spec`, `tests/test_webview_packaging.py` (new, 4).

**Evidence:** `docs/evidence/.../packaged/` — `PACKAGED_SMOKE_OK`: bundle copied to
a spaces path, `_internal/ui/{index.html,app.js}` current, exe boots offscreen and
stays alive with no startup traceback.

**Remaining risk:** interactive packaged acceptance (clicking thumbnails/settings/
ollama/hover in the native window) still needs a human — can't drive a packaged
GUI from tooling. The startup blockers that prevented ALL of it are fixed.

---

## Phase 1 — Live slide-preview acceptance (PASSED) + open-job fix

**Validation:** Built a real-backend headless harness (`docs/evidence/.../live_slide_acceptance/`)
that boots the actual `MainWindow` (Backend + QWebChannel + lpasset handler +
LecturePackAdapter over `~/LecturePackData`) offscreen at 1360×860 and drives the
production UI. **16/16 checks ALL_OK** across 3 real jobs: egypt (11), Mesopotamia
(167), m2-1080p (7) — every thumbnail + preview renders, correct job attribution,
prev/next, job-switch clears stale, open_job via Home card, missing-file marker.

**Finding 1 (perf, P2):** m2 job stores 1920×1080 ~2.5 MB PNGs; on a cold 1.1 s
settle 0/7 had decoded, but all rendered with more time (naturalWidth=1920).
Correctness fine — off-critical-path thumbnail generation is a P2 win.

**Finding 2 (FIXED): no open-job control.** Home job cards had `cursor:pointer`
but no handler/bridge slot — only the latest completed job was reachable.
- `engine_adapter`: added `open_job(job_id)` (loads Job, pushes review+study) and
  `id` to `_list_jobs` rows (both running + done branches); base interface stub.
- `bridge`: `@Slot(str) open_job`.
- `app.js`: `#jobs-grid` click handler → `open_job` + jump to Review (or Process
  if running); job cards carry `data-job`.
- Tests: `test_open_missing_job_is_safe` (guard); happy path via the harness.

**Files touched:** `app/desktop/engine_adapter.py`, `app/desktop/bridge.py`,
`app/ui/app.js`, `tests/test_webview_settings_bridge.py`,
`docs/evidence/.../live_slide_acceptance/*`.

**Remaining risk:** validated headless (offscreen) — a real windowed pass on the
user's GPU is still worthwhile; large-PNG thumbnail perf (Finding 1) open for P2.

---

## P1.7 — Timeline hover popup clipped above the app (FIXED)

**Issue:** The timeline scrub preview rendered `position:absolute; bottom:34px`
inside `#timeline-strip`, always above the strip. On the Review page the timeline
sits near the top of the window, so the popup was clipped off the top; it also had
no horizontal clamping (half off-screen at the ends).

**Fix (app.js + index.html):** Portal `#scrub-preview` to `<body>` (escapes the
timeline card's overflow), switch it to `position:fixed`, and compute placement in
`onScrub`: prefer above, flip below when there isn't room, clamp left to
`[pad, vw-pw-pad]`. Show the real slide image in the preview thumb. Hide on
mouseleave, screen change (`setScreen`), job change (`slides_changed`), and
scroll/resize.

**Evidence:** headless real-viewport validation
`docs/evidence/v1.2.0/webview_functionality_recovery/timeline_hover_result.txt`
— viewport 1360×860, hover near the left edge of a top-anchored timeline →
`parentBody:true, display:block`, rect fully inside the viewport, **flipped below**
the strip (top 152 > stripTop 114). No console errors on load.

**Remaining risk:** DPI scaling (125/150%) and both themes not explicitly checked;
placement math is resolution-independent so low risk.

---

## P0.3 / P0.4 / P1.4 — Settings controls wired to the backend (FIXED)

**Issue:** Visible Settings controls were dead. The Vulkan GPU button, the endpoint
field, the accent swatches and the (absent) model picker did nothing — only the
Whisper "Browse", "Test", and theme toggle were wired.

**Root cause:** The desktop `Backend` persists every setting in **QSettings** (UI
state), while the engine reads its own **config.json** (`ConfigManager`).
`LecturePackAdapter` never overrode `on_setting_changed`, so nothing bridged the
two. The only `set_setting` call in app.js was for `theme`. So the compute engine,
endpoint, and model chosen in Settings never reached processing/AI — selecting
Vulkan literally did nothing.

**Fix:**
- `engine_adapter.py`: override `on_setting_changed` to map UI keys →
  ConfigManager (`engine` cpu/vulkan/auto with validation; `ollama_base_url` /
  `ollama_model` merged into the `ollama` dict without clobbering; `whisper_model`;
  `theme` is a deliberate no-op). New `_settings_payload()` (used by `on_ui_ready`
  and re-emitted after each change) now includes `engine` + `ollama_model`.
- `start_processing`: apply `config.engine` → `job.settings["whisper"]["engine"]`
  so a Vulkan selection actually reaches the transcription backend.
- `_on_backend_info`: emit `actual_backend` so the UI footer shows the **actual**
  loaded backend (not the requested one) + fallback text.
- Ollama model discovery: new `list_ollama_models()` (adapter, threaded) using the
  existing `OllamaClient.list_models()` (/api/tags); emits `ollama_models`. Bridge
  gains the `ollama_models` signal + `list_ollama_models` slot; base + interface
  stubs added. qwen3:1.7b is no longer hardcoded as the only option.
- UI: compute CPU/Vulkan buttons wired (`reflectEngine` + `set_setting engine`);
  endpoint made an editable `<input>` committed on blur/Enter; added a model
  `<select>` + Refresh populated from `ollama_models`, selection persisted via
  `set_setting ollama_model`; footer updates from `actual_backend`.

**Files touched:** `app/desktop/engine_adapter.py`, `app/desktop/bridge.py`,
`app/ui/index.html`, `app/ui/app.js`, `app/ui/bridge.js`,
`tests/test_webview_settings_bridge.py` (new).

**Tests:** `tests/test_webview_settings_bridge.py` — 9 passing (engine persist +
survive reload, invalid→auto, ollama base/model merge, whisper model, theme no-op,
payload reflection).

**Remaining risk / not done in this session:**
- **Vulkan live activation** needs GPU hardware + the `whisper_vulkan_exe` binary
  configured; wiring + actual-backend reporting are in place but a real Vulkan run
  (command/output evidence, benchmark/validate action) is unverified → Outcome C
  for that sub-item.
- Ollama model `keep_alive`, per-model `show`/unload state, and enabling AI when a
  model is picked are not yet surfaced.
- Accent swatches: still present but inert — recommend removing per spec (P0/P3);
  not touched yet.

---

## P0.5 — Inappropriate bundled demo content (VERIFIED CLEAN + guarded)

**Finding:** No inappropriate content exists in tracked product/demo files. The
strings "dashcam"/"vulgar" appear nowhere in readable text (confirmed via
`strings`, `grep -ao`, and `git grep` — the one binary "match" in
`tests/fixtures/synthetic_lecture.mp4` was a non-printable byte coincidence; that
fixture is a legitimate geometric slide-detection test video referenced across the
suite). The shipped demo/placeholder content (app.js, index.html) is the wholesome
"Great Pyramid of Giza" educational sample matching the screenshots. The premise
of bundled inappropriate content predates the current tree state.

**Action:** Added `tests/test_content_hygiene.py` — a regression tripwire that
scans tracked product/demo text files (app/, lecturepack/, assets/, tests text
fixtures) and fails if banned substrings ("dashcam", "vulgar") or whole-word
profanity reappear. No product code changed (nothing to remove). Real user data
in ~/LecturePackData is never touched.

**Tests:** 2 passing.

---

## P0.1 — Blank slide thumbnails & preview (FIXED)

**Issue:** Slide detection completes and timestamps/acceptance states render, but
every thumbnail box and the large preview are blank. The user cannot tell what to
accept/reject. Release-blocking.

**Root cause:** The `slides_changed` payload built in
`LecturePackAdapter._push_review_data` (engine_adapter.py) carried only
`pct / time / state / frame` — **no image reference at all**. The UI (`renderSlides`
in app.js) had nothing to draw, so it rendered placeholder SVG icons for both the
thumbnails and the large preview. On-disk the candidate images exist at
`jobs/<id>/frames/candidates/<image_filename>` and each `candidates.json` entry has
an `image_filename`, but that field never reached the frontend.

**Fix (central asset resolver, not scattered path conversion):**
- New `app/desktop/assets.py`: a security-checked custom WebEngine URL scheme
  `lpasset://job/<job_id>/<filename>`.
  - Pure-Python `AssetResolver` (no Qt, unit-tested): validates job-id shape,
    rejects traversal/absolute/separator filenames, confirms the resolved file is
    inside that job's `frames/` tree (live `jobs/` or `archive/`), returns
    `(mime, bytes)`. Spaces/Unicode in the data dir are handled by the filesystem
    on the Python side — never passed through a URL.
  - `register_asset_scheme()` (called before QApplication in main.py) +
    `install_asset_handler(profile, resolver, logger)` (thin
    `QWebEngineUrlSchemeHandler`).
- `main.py`: register scheme pre-app; install handler on the page profile with a
  logger that surfaces missing/blocked assets in the UI log.
- `bridge.py`: `Backend.log_asset_error()` diagnostics hook (stderr + `log_line`).
- `engine_adapter.py`: slides payload now includes
  `"img": asset_url(job.job_id, image_filename)`.
- `app.js`: `slideImg()` helper renders `<img>` with an `onerror` fallback to an
  explicit placeholder (missing-file marker), used for both thumbnails and the
  large preview.

**Files touched:** `app/desktop/assets.py` (new), `app/desktop/main.py`,
`app/desktop/bridge.py`, `app/desktop/engine_adapter.py`, `app/ui/app.js`,
`tests/test_webview_assets.py` (new).

**Tests:** `tests/test_webview_assets.py` — 17 passing (URL shape/encoding, MIME,
happy paths incl. spaces-in-data-dir + Unicode + archived job, and rejections:
missing file, traversal `../` and `..\\`, absolute path, bad job-id, cross-job).

**Scheme wiring proven headless:** a real `QWebEngineView` loading a `file://`
page successfully rendered an `<img src="lpasset://…">` (naturalWidth=1) via the
handler. Initial attempt with `SecureScheme | LocalAccessAllowed | CorsEnabled`
**failed** — `requestStarted` never fired because a `file://` page may not request
a plain secure scheme. Adding **`LocalScheme`** fixed it (puts lpasset in the same
local bucket as file://). Evidence:
`docs/evidence/v1.2.0/webview_functionality_recovery/asset_scheme_result.txt`
(+ `smoke_asset_scheme.py`).

**Remaining risk:** headless offscreen render differs slightly from a real GPU
window; a live GUI smoke test on a completed job (thumbnails + preview + job
switch + missing-file marker) is still the final acceptance step. Resolver logic
and scheme flags are both proven.
