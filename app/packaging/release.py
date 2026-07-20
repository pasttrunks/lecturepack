"""Cut a new LecturePack release in one command.

This is the "each time we work on something, ship an update with an overview of
what changed" workflow. It:

  1. Bumps __version__ in desktop/version.py.
  2. Prepends a new dated section to CHANGELOG.md with the notes you pass.
  3. Commits both, tags v<version>, and pushes.

The push triggers .github/workflows/release.yml, which builds the Windows
installer and publishes a GitHub Release. Users' apps pick it up on next
launch and show your notes as the "What's new" overview.

Usage (from app/):
    python packaging/release.py 1.1.0 \
        --note "Faster slide detection" \
        --note "Fix transcript scroll jump"

    # or pull notes from an editor / file:
    python packaging/release.py 1.1.0 --notes-file notes.txt

Add --no-push to stage the commit and tag locally without pushing.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "app"
VERSION_PY = APP_DIR / "desktop" / "version.py"
CHANGELOG = REPO / "CHANGELOG.md"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def set_version(version: str) -> None:
    text = VERSION_PY.read_text(encoding="utf-8")
    new = re.sub(r'(__version__\s*=\s*)["\'][^"\']+["\']', rf'\1"{version}"', text)
    if new == text:
        sys.exit("failed to update __version__ — check desktop/version.py")
    VERSION_PY.write_text(new, encoding="utf-8")


def prepend_changelog(version: str, notes: list[str], date: str) -> None:
    section = f"## [{version}] - {date}\n\n" + "\n".join(f"- {n}" for n in notes) + "\n"
    if CHANGELOG.exists():
        text = CHANGELOG.read_text(encoding="utf-8")
        idx = text.find("\n## ")
        if idx == -1:
            text = text.rstrip() + "\n\n" + section
        else:
            text = text[: idx + 1] + section + "\n" + text[idx + 1 :]
    else:
        text = "# Changelog\n\n" + section
    CHANGELOG.write_text(text, encoding="utf-8")


def git(*args: str) -> None:
    print("+ git", *args)
    subprocess.run(["git", *args], cwd=REPO, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="new version, e.g. 1.1.0")
    ap.add_argument("--note", action="append", default=[], help="a changelog bullet (repeatable)")
    ap.add_argument("--notes-file", help="read newline-separated notes from this file")
    ap.add_argument("--no-push", action="store_true", help="commit + tag locally, do not push")
    args = ap.parse_args()

    if not SEMVER.match(args.version):
        sys.exit("version must be MAJOR.MINOR.PATCH, e.g. 1.1.0")

    notes = list(args.note)
    if args.notes_file:
        notes += [ln.strip("-* \t") for ln in Path(args.notes_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not notes:
        sys.exit("provide at least one --note or --notes-file")

    date = _dt.date.today().isoformat()
    set_version(args.version)
    prepend_changelog(args.version, notes, date)

    git("add", str(VERSION_PY.relative_to(REPO)), str(CHANGELOG.relative_to(REPO)))
    git("commit", "-m", f"Release v{args.version}")
    git("tag", f"v{args.version}")
    if args.no_push:
        print(f"\nStaged v{args.version}. Push with:  git push && git push origin v{args.version}")
    else:
        git("push")
        git("push", "origin", f"v{args.version}")
        print(f"\nReleased v{args.version}. The release workflow is building the installer now.")


if __name__ == "__main__":
    main()
