"""Guard rails for the two locked-dependency files (Phase 1.1 item 1).

The root `requirements.txt` and `app/requirements.txt` had drifted: root declared
`Send2Trash`, `tzdata`, and `yt-dlp`, and `app/requirements.txt` (the file CI
installs) did not. Packaged builds therefore lacked `send2trash`, so
`engine_adapter.py` fell back to hard `rmtree` on user deletes -- a BUG-14
regression that reintroduced permanent deletion where the user asked for a
Recycle Bin move.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT_REQS = REPO / "requirements.txt"
APP_REQS = REPO / "app" / "requirements.txt"


def _parse(path: Path) -> dict[str, str]:
    """Return {package_name_lower: version_spec} from a pip requirements file."""
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", line)
        if m:
            name, spec = m.group(1).lower(), m.group(2).strip()
            result[name] = spec
    return result


def test_root_and_app_requirements_agree():
    """app/requirements.txt's own header claims it mirrors root -- enforce that."""
    root = _parse(ROOT_REQS)
    app = _parse(APP_REQS)
    missing_in_app = sorted(set(root) - set(app))
    missing_in_root = sorted(set(app) - set(root))
    disagreeing_specs = sorted(
        name for name in set(root) & set(app) if root[name] != app[name]
    )
    assert not missing_in_app, f"declared in root but not in app: {missing_in_app}"
    assert not missing_in_root, f"declared in app but not in root: {missing_in_root}"
    assert not disagreeing_specs, (
        "same package pinned differently in the two files: "
        + ", ".join(f"{n} (root={root[n]!r} app={app[n]!r})" for n in disagreeing_specs)
    )


def test_send2trash_is_a_declared_runtime_dependency():
    """BUG-14 regression guard: send2trash MUST be in the packaged dep set."""
    assert "send2trash" in _parse(APP_REQS)


def test_send2trash_is_importable():
    """Prove the currently-installed environment can satisfy the dependency.

    A green suite with send2trash missing from the env would be a false pass;
    engine_adapter.py's fallback path silently loses user data.
    """
    import send2trash  # noqa: F401
