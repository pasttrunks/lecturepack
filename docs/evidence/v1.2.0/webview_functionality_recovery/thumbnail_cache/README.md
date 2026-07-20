# §5 Lazy thumbnail cache

Long jobs were decoding full-resolution ~2.5 MB PNGs into 60×38 list/grid boxes
(167 × 2.5 MB ≈ 400 MB decoded). Now the slide list/grid loads a compact cached
thumbnail; the main preview and exports still use the full-resolution image.

## Design
- New `lpasset://thumb/<job_id>/<file>` scheme host (full-res stays `lpasset://job/...`).
- `AssetResolver.resolve_thumb` is **non-blocking**: serves a fresh cached
  thumbnail if present, else serves the full-resolution original immediately and
  generates the thumbnail on a background thread (2 workers, deduped) for next
  time. This keeps the scheme handler (Qt main thread) from stalling on 100+
  decodes on first open, and never starves the full-resolution preview request.
- Thumbnails: WebP (JPEG fallback if the WebP writer isn't bundled), longest side
  `THUMB_MAX=320`, cached at `frames/thumbs/<schema>/<name>.webp`. Fresh if
  `thumb.mtime >= source.mtime`; schema-version dir bump invalidates all. Works
  for live and archived jobs; originals are never modified.
- Payload: slides now carry both `img` (full-res) and `thumb`; the UI list/grid
  and timeline hover use `thumb || img`, the preview uses `img`.

## Measured size reduction (real candidates, WebP)
| job | n | source | thumbs | reduction |
|-----|---|--------|--------|-----------|
| m2-1080p (1920×1080) | 7 | 15.7 MB | 0.08 MB | **192×** |
| Mesopotamia (sample 30) | 30 | 23.2 MB | 0.37 MB | **63×** |

Extrapolated full Mesopotamia (167): ~130 MB source → ~2 MB thumbs.

## Behavior notes
- First open of a not-yet-cached job renders from full-res (unchanged cost) while
  thumbs generate in the background; subsequent opens serve tiny cached WebP.
- Live acceptance harness re-run: 16/16 ALL_OK (thumbnails via `lpasset://thumb`).
- Tests: `tests/test_webview_assets.py` — thumb URL, make_thumb_now downscale+cache,
  cold full-res fallback + background generation, warm cached serve, missing source.

## Reproduce
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe (see measure snippet in git log)
