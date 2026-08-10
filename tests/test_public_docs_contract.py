"""Keep the public-facing documents describing the product we actually ship.

At v2.0.0 the README still advertised the 0.9.0 public beta, named Qt Widgets
as the production UI, and linked to download URLs for a version that was two
releases old. THIRD_PARTY_NOTICES.txt was headed "v0.2.0" and mislicensed a
bundled component. These tests make that class of rot fail the build instead
of shipping.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
NOTICES = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def _package_version() -> str:
    import json
    return json.loads((ROOT / "electron-spike" / "package.json").read_text(encoding="utf-8"))["version"]


# ----------------------------------------------------------------- README
@pytest.mark.parametrize("claim", [
    "Public Beta",
    "0.9.0-beta",
    "Qt Widgets",
    "PySide6-Qt6",          # the old build badge
])
def test_readme_no_longer_makes_stale_beta_or_qt_claims(claim):
    assert claim not in README, f"README still claims {claim!r}"


def test_readme_has_no_hardcoded_version_download_links():
    """Version-pinned release URLs go stale the moment we ship again."""
    pinned = re.findall(r"releases/download/v[0-9][^\s)\"']*", README)
    assert not pinned, f"README pins download URLs: {pinned}"


def test_readme_describes_the_electron_product():
    assert "Electron" in README
    for promise in ("Windows 10/11", "whisper.cpp", "Rust Study Core", "FFmpeg"):
        assert promise in README, promise


def test_readme_states_no_python_is_required():
    # Strip markdown emphasis so "do **not** need" matches.
    plain = README.replace("*", "").replace("_", "").lower()
    assert "python" in plain
    assert "do not need" in plain, "README must say Python is not required"
    # And Python must appear in the not-required list, not just anywhere.
    assert re.search(r"\|\s*python\s*\|", plain), "Python missing from the 'not needed' table"


def test_readme_documents_every_kind_of_network_activity():
    """Privacy wording must disclose what actually goes out."""
    assert "github.com" in README, "update checks must be disclosed"
    assert "no telemetry" in README.lower()
    # The one case where lecture content can leave the machine.
    assert "Groq" in README, "the optional hosted transcription path must be disclosed"


def test_readme_discloses_the_unsigned_binaries():
    assert "SmartScreen" in README or "not yet Authenticode-signed" in README


def test_readme_links_resolve_to_files_that_exist():
    for target in re.findall(r"\]\((?!https?:)([^)#]+)\)", README):
        assert (ROOT / target).exists(), f"README links to missing path: {target}"


# ---------------------------------------------------------------- notices
def test_notices_are_not_headed_with_an_ancient_version():
    assert "LecturePack v0.2.0" not in NOTICES
    header = NOTICES.splitlines()[1]
    assert header.startswith("THIRD-PARTY NOTICES FOR LecturePack v2."), header


@pytest.mark.parametrize("component", [
    "Electron", "Chromium", "Deno", "yt-dlp", "yt-dlp-ejs",
    "cryptography", "Send2Trash", "tzdata", "pikepdf",
    "Rust Study Core", "PySide6", "FFmpeg", "whisper.cpp",
    "OpenCV", "scikit-image", "Pillow", "imagehash", "img2pdf",
    "ReportLab", "Jinja2",
])
def test_notices_cover_every_shipped_component(component):
    assert component.lower() in NOTICES.lower(), f"{component} is shipped but not in the notices"


def test_img2pdf_is_recorded_with_its_real_licence():
    """img2pdf is LGPL-3.0. The notices previously said GPL-3.0."""
    section = NOTICES[NOTICES.index("\nimg2pdf\n"):]
    section = section[:section.index("---------", 200)]
    assert "Lesser General Public License v3" in section, section[:400]


def test_notices_state_qt_is_not_the_user_interface():
    """Anyone reading the notices must not conclude we ship a Qt UI."""
    assert "does not use Qt for its user interface" in NOTICES


def test_notices_record_the_bundled_model_as_shipped():
    assert "ggml-base.en" in NOTICES


# -------------------------------------------------------------- changelog
def test_changelog_has_a_real_2_0_0_stable_entry():
    assert re.search(r"^## \[2\.0\.0\]", CHANGELOG, re.MULTILINE), "no 2.0.0 entry"


def test_changelog_has_a_2_0_1_hardening_entry():
    assert re.search(r"^## \[2\.0\.1\]", CHANGELOG, re.MULTILINE), "no 2.0.1 entry"


def test_changelog_leads_with_the_current_version():
    headings = re.findall(r"^## \[([^\]]+)\]", CHANGELOG, re.MULTILINE)
    assert headings, "changelog has no version headings"
    assert headings[0].startswith("2."), headings[:3]


def test_changelog_preserves_the_historical_entries():
    """Reorganising must never delete history."""
    for historical in ("0.9.0-beta.13", "1.1.0-ui-speed-ollama", "1.0.1-real-media-verified"):
        assert historical in CHANGELOG, f"lost historical entry {historical}"
