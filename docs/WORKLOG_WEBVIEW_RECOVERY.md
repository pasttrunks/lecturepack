# WebView Functionality Recovery — Worklog

Branch: `feat/desktop-webengine`
Safety tag: `safety/start-webview-functionality-recovery`
Start commit: `d7f4b80`

Concise log of decisions + evidence. Newest first.

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
