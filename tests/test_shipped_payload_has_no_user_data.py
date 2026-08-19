"""A release must ship the demo lecture and nothing else of anyone's.

Set LECTUREPACK_ONEDIR_FIXTURE to a built app/dist/LecturePack to run these.
Skipped otherwise, like the rest of the packaged-fixture family.

The risk is mundane and permanent: builds are cut from a working tree on a machine
that has real lectures in it, and a published installer cannot be unpublished. So
the packaged tree is checked for media it has no business carrying, for job data
(manifests, transcripts, slide sets), and for a stray absolute home path.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURE = os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "").strip()

pytestmark = pytest.mark.skipif(
    not FIXTURE or not Path(FIXTURE).is_dir(),
    reason=(
        "needs a packaged onedir: set LECTUREPACK_ONEDIR_FIXTURE to a built "
        "app/dist/LecturePack. Not a failure: that payload is gitignored and "
        "absent on a bare checkout."
    ),
)

ROOT = Path(FIXTURE) if FIXTURE else Path(".")

MEDIA_SUFFIXES = {".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi", ".mp3", ".m4a", ".flac"}

# Everything the product is allowed to carry, by path relative to the onedir.
ALLOWED_MEDIA = {
    "_internal/assets/demo/demo_lecture.mp4",   # the shipped demo
    "smoke/runtime-smoke.wav",                  # runtime self-test clip
}


def _relative(paths):
    return sorted(p.relative_to(ROOT).as_posix() for p in paths)


def test_only_the_demo_and_smoke_media_ship():
    found = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES]
    unexpected = [p for p in found if p.relative_to(ROOT).as_posix() not in ALLOWED_MEDIA]
    assert not unexpected, (
        "media in the packaged tree that is not the demo:\n  " + "\n  ".join(_relative(unexpected))
    )


def test_no_lecture_job_data_ships():
    """Job dirs carry a manifest; that is the cheapest reliable marker."""
    manifests = list(ROOT.rglob("manifest.json"))
    jobs_dirs = [p for p in ROOT.rglob("jobs") if p.is_dir()]
    transcripts = [p for p in ROOT.rglob("transcript.json")]
    offenders = manifests + jobs_dirs + transcripts
    assert not offenders, (
        "lecture/job data in the packaged tree:\n  " + "\n  ".join(_relative(offenders))
    )


def test_no_absolute_home_path_is_baked_into_the_shipped_ui():
    """A build machine's own paths must not travel with the product.

    Only the UI payload is scanned: it is text, it is what the user sees, and it
    is where a debug string or a hardcoded example would end up.
    """
    ui = ROOT / "_internal" / "ui"
    if not ui.is_dir():
        pytest.skip("no _internal/ui in this fixture")
    home = Path.home()
    needles = [str(home), str(home).replace("\\", "/"), str(home).replace("\\", "\\\\")]
    hits = []
    for path in ui.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".html", ".js", ".css"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle and needle in text:
                hits.append(f"{path.relative_to(ROOT).as_posix()} contains {needle}")
    assert not hits, "build-machine paths in the shipped UI:\n  " + "\n  ".join(hits)
