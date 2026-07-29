"""Filesystem locations, source-run and PyInstaller-frozen aware."""

from __future__ import annotations

import os
import sys
import json
import re
import shutil
import stat
import tempfile
from pathlib import Path


def app_root() -> str:
    """Directory containing bundled resources (ui/, packaging assets).

    Frozen: PyInstaller collects data files under ``sys._MEIPASS`` — that is the
    onedir ``_internal/`` folder (PyInstaller >= 6) or the onefile temp extract,
    NOT ``dirname(sys.executable)``. Falling back to the exe dir only for older
    layouts that placed data beside the exe.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.isdir(os.path.join(meipass, "ui")):
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ui_dir() -> str:
    return os.path.join(app_root(), "ui")


# Kept in sync with lecturepack.constants.DATA_DIR_ENV_VAR; this module stays
# import-light (no engine imports) because main.py loads it before Qt is up.
DATA_DIR_ENV_VAR = "LECTUREPACK_DATA_DIR"


def data_dir() -> str:
    """Per-user mutable data (jobs, models, exports) — mirrors ~/LecturePackData.

    ``LECTUREPACK_DATA_DIR`` overrides the location so packaged-GUI acceptance
    and upgrade tests can run against a disposable profile instead of mutating
    the user's real jobs.
    """
    override = os.environ.get(DATA_DIR_ENV_VAR, "").strip()
    if override:
        d = os.path.abspath(os.path.expanduser(override))
    else:
        d = os.path.join(os.path.expanduser("~"), "LecturePackData")
    os.makedirs(d, exist_ok=True)
    return d


_DEMO_DIR_RE = re.compile(r"demo_([0-9a-f]{32})\Z")
_DEMO_SENTINEL = ".lecturepack-demo-session.json"


def _is_reparse_point(path: Path) -> bool:
    """Return true for a symlink or Windows reparse point without following it."""
    try:
        info = path.lstat()
    except OSError:
        return True
    return (
        stat.S_ISLNK(info.st_mode)
        or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    )


def _demo_root_path() -> Path:
    """Return the dedicated temp root, refusing an attacker-controlled link."""
    root = Path(tempfile.gettempdir()) / "LecturePack"
    if root.exists():
        if _is_reparse_point(root) or not root.is_dir():
            raise RuntimeError("demo temp root is not a real directory")
    else:
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
    return root


def demo_temp_root() -> str:
    """Root directory for isolated demo session workspaces under %TEMP%."""
    return str(_demo_root_path())


def create_demo_session_dir(session_id: str) -> str:
    """Create a sentinel-owned isolated workspace for one demo session.

    The id is deliberately constrained to the UUID4 hex representation the
    adapter generates.  This makes a session name incapable of escaping the
    dedicated root and gives cleanup a simple, auditable ownership boundary.
    """
    if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        raise ValueError("demo session id must be 32 lowercase hexadecimal characters")
    root = _demo_root_path()
    path = root / f"demo_{session_id}"
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as exc:
        # Reusing a directory would make its ownership ambiguous.  The caller
        # always creates a fresh UUID, so fail closed instead.
        raise FileExistsError("demo session directory already exists") from exc
    sentinel = path / _DEMO_SENTINEL
    sentinel.write_text(json.dumps({
        "schema_version": 1,
        "session_id": session_id,
        "directory": path.name,
    }, sort_keys=True), encoding="utf-8")
    return str(path)


def _owned_demo_dir(path: Path, root: Path, session_id: str | None = None) -> bool:
    """Validate that *path* is a direct, sentinel-owned child of *root*.

    This intentionally does not resolve paths: resolving follows links, which
    is exactly what cleanup must never do.
    """
    match = _DEMO_DIR_RE.fullmatch(path.name)
    if match is None or path.parent != root or _is_reparse_point(path) or not path.is_dir():
        return False
    expected = session_id or match.group(1)
    if match.group(1) != expected:
        return False
    sentinel = path / _DEMO_SENTINEL
    if _is_reparse_point(sentinel) or not sentinel.is_file():
        return False
    try:
        payload = json.loads(sentinel.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return payload == {
        "schema_version": 1,
        "session_id": expected,
        "directory": path.name,
    }


def _tree_is_real_directory(path: Path) -> bool:
    """Ensure recursive cleanup cannot traverse a symlink/reparse point."""
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                child = Path(entry.path)
                if _is_reparse_point(child):
                    return False
                if entry.is_dir(follow_symlinks=False) and not _tree_is_real_directory(child):
                    return False
    except OSError:
        return False
    return True


def cleanup_demo_session(session_path: str, session_id: str | None = None) -> bool:
    """Delete one fully validated demo workspace, never following a link.

    A malformed, foreign, or reparse-containing tree is left untouched.  This
    is deliberately fail-closed: preserving an unexpected temp directory is
    safer than risking deletion outside the demo sandbox.
    """
    try:
        root = _demo_root_path()
        path = Path(session_path)
    except (OSError, RuntimeError):
        return False
    if not _owned_demo_dir(path, root, session_id) or not _tree_is_real_directory(path):
        return False
    try:
        shutil.rmtree(path)
    except OSError:
        return False
    return not path.exists()


def sweep_demo_sessions() -> list[str]:
    """Idempotently clean only direct sentinel-owned demo workspaces.

    Returns removed paths for diagnostics/tests.  Foreign files, broad
    ``demo_*`` names, and any reparse points stay untouched.
    """
    try:
        root = _demo_root_path()
        entries = list(root.iterdir())
    except (OSError, RuntimeError):
        return []
    removed = []
    for path in entries:
        if cleanup_demo_session(str(path)):
            removed.append(str(path))
    return removed


def demo_asset_path() -> str:
    """Path to the locally bundled, rights-clear demo lecture."""
    return os.path.join(app_root(), "assets", "demo", "demo_lecture.mp4")
