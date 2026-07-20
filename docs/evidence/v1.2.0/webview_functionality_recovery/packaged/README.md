# Phase 2 — Packaged WebEngine validation

Rebuilt the onedir package from current source:
`cd app && python -m PyInstaller packaging/lecturepack.spec --noconfirm` → `dist/LecturePack/`.

## Two frozen-only blockers found and FIXED (both pre-existing, packaged app was DOA)

1. **Startup crash — relative imports in the entry script.** PyInstaller ran
   `desktop/main.py` as `__main__`, so `from . import version` raised
   `ImportError: attempted relative import with no known parent package` before any
   window appeared. Fix: new package wrapper `app/lecturepack_desktop.py`
   (`from desktop.main import main`) is now the spec's Analysis entry.

2. **UI not found — wrong frozen resource root.** `paths.app_root()` returned
   `dirname(sys.executable)`, but PyInstaller 6 places bundled data under
   `sys._MEIPASS` (the onedir `_internal/` folder). Fix: `app_root()` returns
   `sys._MEIPASS` when it contains `ui/`, else falls back to the exe dir.

## Smoke result (smoke_output.txt) — PACKAGED_SMOKE_OK

- bundle copied to `…\LP Packaged Test dir\LecturePack` (path WITH SPACES)
- `_internal/ui/index.html` and `app.js` present and current (contain lpasset/open_job)
- exe launched offscreen from the spaces path, stayed alive 12 s, **no startup
  traceback** (only harmless offscreen GLES warnings, filtered out)

Path logic covered by `tests/test_webview_packaging.py` (4). Entry wrapper covered
by this smoke launch.

## Still requires a human (cannot drive a native packaged GUI from tooling)
Interactive packaged acceptance: open the exe, confirm `lpasset://` thumbnails +
large preview render, job switching, Settings bridge, Ollama picker, timeline
hover. The startup blockers that made all of this impossible are now fixed.

## Reproduce
    cd app && ..\.venv\Scripts\python.exe -m PyInstaller packaging\lecturepack.spec --noconfirm --distpath ..\dist --workpath ..\build
    .venv\Scripts\python.exe docs\evidence\v1.2.0\webview_functionality_recovery\packaged\smoke_packaged_launch.py
