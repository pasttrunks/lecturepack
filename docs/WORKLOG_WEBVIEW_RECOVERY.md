# WebView Functionality Recovery — Worklog

Branch: `feat/desktop-webengine`
Safety tag: `safety/start-webview-functionality-recovery`
Start commit: `d7f4b80`

Concise log of decisions + evidence. Newest first.

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
