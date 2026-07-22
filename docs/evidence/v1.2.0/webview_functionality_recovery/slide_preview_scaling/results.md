# Slide-preview scaling fix — measured before/after (real backend, offscreen 1360×860)

The center preview was rendering the slide tiny: `#slide-frame` was locked to
`width:74%` + `aspect-ratio:16/9`, and non-16:9 images were letterboxed further
inside that fixed frame. Fixed by turning the frame into a fill-canvas and adding
a zoom/pan controller (`previewCtl`) that fits the full-resolution image to the
canvas (`fit = min(availW/natW, availH/natH)`), re-fitting when Review becomes
visible and on resize.

`imgWidthPctOfCanvas` = slide width as a % of the preview canvas width.

## BEFORE (HEAD 20436b7)
| job | natural | frame | img | width% | area% |
|-----|---------|-------|-----|--------|-------|
| egypt (4:3) | 1024×768 | 336×189 (74%/16:9) | 252×189 | **55%** | **19%** |

## AFTER
| job | natural | frame | img | width% | area% |
|-----|---------|-------|-----|--------|-------|
| egypt (4:3) | 1024×768 | 454×546 (fills) | 422×317 | **92%** | 53% |
| m2 (16:9) | 1920×1080 | 454×546 (fills) | 422×237 | **92%** | 40% |

The slide now fills ~92% of the available width (limited only by aspect ratio and
16px padding), matching the 85–95% target. Area varies with aspect vs. the
portrait-ish canvas — correct behavior for object-fit contain.

## Zoom controls (test_zoom_controls.py → ZOOM_OK)
egypt 1024px-wide image: Fit=422px · 100%=1024px · zoom-in(from 100%)=1280px · Reset=422px.
Also wired: Ctrl+wheel zoom-at-cursor, double-click Fit↔100%, drag-to-pan when zoomed in.

## Full-resolution vs thumbnail
The preview uses the full-resolution candidate image (`cur.img`); the 60×38 list
thumbnails use the same URLs for now. A separate downscaled thumbnail cache
(`thumbnailUrl` vs `fullImageUrl`) is deferred to the thumbnail-performance task
(prompt §5); the readability fix does not depend on it.

## Not machine-verifiable here
Native-window screenshots and 125%/150% DPI passes need a human; the fit math is
resolution-independent (uses the live frame rect + naturalWidth/Height).

## Reproduce
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe <this dir>/measure_preview.py <job_id>
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe <this dir>/test_zoom_controls.py
