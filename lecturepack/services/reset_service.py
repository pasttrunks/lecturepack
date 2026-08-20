"""Safe, explicit removal of LecturePack-owned data-root state."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any


# These are app-owned persistence/artifact locations observed in the current
# Electron sidecar.  Bundled runtimes and models intentionally do not appear.
OWNED_DIRECTORIES = (
    "jobs",
    "archive",
    "downloads",
    "demo-inputs",
    "temp",
    "tmp",
    "cache",
    "logs",
    "generated",
    "exports",
    "study",
    "study-v2",
)
OWNED_FILES = (
    "config.json",
    "queue.json",
    "downloads-state.json",
    "demo-session.json",
    "guided-tour.json",
    "session.json",
    "runtime-health.json",
    "bookmarks.json",
    "progress.json",
    "mastery.json",
    "settings.json",
)


def _canonical(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _contained(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _remove_owned(root: Path, target: Path) -> None:
    """Remove a known target only after checking its canonical containment.

    Symlinks/junctions are never recursively followed.  An unsafe link fails
    the reset visibly instead of guessing whether its target is disposable.
    """
    if not target.exists() and not target.is_symlink() and not os.path.islink(target):
        return
    resolved = _canonical(target)
    if not _contained(root, resolved):
        raise RuntimeError(f"refusing to remove path outside data root: {target}")
    if target.is_symlink() or os.path.islink(target):
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def reset_data_root(data_dir: str | Path) -> dict[str, Any]:
    """Clear known LecturePack-owned state beneath ``data_dir``.

    The root itself and unknown files are preserved.  In particular, a job's
    manifest may name a source under a user's Videos folder; this routine never
    resolves or deletes that source path.
    """
    root = _canonical(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    failed: list[dict[str, str]] = []

    targets = [root / name for name in OWNED_DIRECTORIES]
    targets.extend(root / name for name in OWNED_FILES)
    # Atomic writers can leave a sibling temporary file after a process crash.
    # Two shapes exist: the historical fixed ``<name>.tmp`` and the unique
    # ``.<name>.<random>.tmp`` that FileManager.write_json_atomic writes now.
    targets.extend(root / f"{name}.tmp" for name in OWNED_FILES)
    for name in OWNED_FILES:
        targets.extend(sorted(root.glob(f".{name}.*.tmp")))

    for target in targets:
        try:
            existed = target.exists() or target.is_symlink() or os.path.islink(target)
            _remove_owned(root, target)
            if existed:
                removed.append(str(target.relative_to(root)))
        except (OSError, RuntimeError) as exc:
            failed.append({"path": str(target), "error": f"{type(exc).__name__}: {exc}"})

    return {
        "ok": not failed,
        "data_dir": str(root),
        "removed": removed,
        "failed": failed,
        "preserved": [
            "bundled application resources",
            "installed runtimes and models",
            "unknown data-root files",
            "source files outside the LecturePack data root",
        ],
    }

