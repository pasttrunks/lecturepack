"""Frozen/packaged entry point for the LecturePack desktop shell."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    import site
    candidates = [
        os.path.join(sys.prefix, "Lib", "site-packages"),
        os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages")
    ]
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    for sp in candidates:
        pyside = os.path.join(sp, "PySide6")
        shiboken = os.path.join(sp, "shiboken6")
        if os.path.isdir(pyside):
            try:
                os.add_dll_directory(pyside)
            except Exception:
                pass
        if os.path.isdir(shiboken):
            try:
                os.add_dll_directory(shiboken)
            except Exception:
                pass

from desktop.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
