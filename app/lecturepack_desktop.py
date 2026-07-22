"""Frozen/packaged entry point for the LecturePack desktop shell.

PyInstaller runs its entry script as ``__main__`` with no package context, so a
script that uses relative imports (``from . import ...``) crashes at startup with
"attempted relative import with no known parent package". desktop/main.py is such
a module, so the packaged build must enter through this thin wrapper, which uses
an absolute import — ``desktop`` resolves both from the frozen archive and, in a
source run, from this file's own directory (app/).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from desktop.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
