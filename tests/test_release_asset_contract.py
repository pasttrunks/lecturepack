"""Contract test guarding the published LecturePack release asset names.

Producer side: the authoritative Electron desktop workflow
(.github/workflows/release-electron.yml) must publish exactly the asset names
the updater consumer contract expects, and the retained runtime-repair
workflow must keep publishing its six signed AD-19 assets.

History: this test previously asserted the OPPOSITE of the current invariant.
It required the runtime-repair workflow (then release.yml) to install Inno
Setup, to NOT pass --no-installer, and to publish LecturePack-<v>-Setup.exe.
That is exactly what made the published installer ambiguous between the Qt
PyInstaller build and the Electron build. Those producer assertions now point
at release-electron.yml, and tests/test_release_pipeline_authority.py guards
the separation itself.

The updater's own consumer contract is `expected_asset_names()`
(app/desktop/update_service.py); this test derives the required filenames from
that function rather than hardcoding them a second time.

No YAML parser is used or required -- plain text-membership assertions over
exact filenames (never globs) are sufficient to guard this contract.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import update_service as us  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ELECTRON_PATH = WORKFLOWS / "release-electron.yml"
RUNTIME_PATH = WORKFLOWS / "release-runtime-repair.yml"
ELECTRON_TEXT = ELECTRON_PATH.read_text(encoding="utf-8")
RUNTIME_TEXT = RUNTIME_PATH.read_text(encoding="utf-8")

# The literal GitHub Actions expression the workflows use for the version --
# not a real version string.
WORKFLOW_VERSION_EXPR = "${{ env.APP_VERSION }}"

# A concrete version, used only for the select_asset() payload tests below.
REAL_VERSION = "0.9.0-beta.6"

SIGNED_RUNTIME_ASSET_NAMES = (
    "LecturePack-{V}-RuntimeManifest-v1.json",
    "LecturePack-{V}-RuntimeManifest-v1.json.sig",
    "LecturePack-{V}-Runtime-ffmpeg.zip",
    "LecturePack-{V}-Runtime-whisper-cpu.zip",
    "LecturePack-{V}-Runtime-model-base-en.zip",
    "LecturePack-{V}-Runtime-smoke-fixture.zip",
)


def _files_block(text: str, marker: str) -> str:
    """Isolate the `files:` list of a named publishing step.

    Assertions operate on this block (not the whole file) so a name that
    merely appears elsewhere (e.g. in a comment) cannot make the test pass.
    """
    assert marker in text, f"workflow is missing the {marker!r} step"
    after_marker = text[text.index(marker):]
    files_marker = "files: |"
    assert files_marker in after_marker, f"{marker!r} has no files: list"
    after_files = after_marker[after_marker.index(files_marker) + len(files_marker):]
    lines = []
    for line in after_files.splitlines()[1:]:
        if line.strip() == "" or line.lstrip().startswith("- name:"):
            break
        lines.append(line)
    assert lines, f"{marker!r} files: list parsed empty"
    return "\n".join(lines)


ELECTRON_FILES_BLOCK = _files_block(ELECTRON_TEXT, "- name: Publish the stable desktop release")
RUNTIME_FILES_BLOCK = _files_block(
    RUNTIME_TEXT, "- name: Release exactly the six signed runtime-repair assets"
)


def test_expected_asset_names_returns_two_tuple_shape():
    """The producer-side workflow assertion depends on this exact shape:
    (primary_asset_name, checksum_asset_name)."""
    installer_names = us.expected_asset_names(WORKFLOW_VERSION_EXPR)
    portable_names = us.expected_asset_names(WORKFLOW_VERSION_EXPR, portable=True)
    for names in (installer_names, portable_names):
        assert isinstance(names, tuple)
        assert len(names) == 2
    # Both channels share the same checksum file name.
    assert installer_names[1] == portable_names[1]


def test_electron_release_publishes_all_updater_required_asset_names():
    """Deleting either updater asset name from the authoritative desktop
    release step must turn this test red."""
    required = set(us.expected_asset_names(WORKFLOW_VERSION_EXPR))
    assert len(required) == 2, f"expected exactly 2 required updater asset names, got {required!r}"
    missing = [name for name in required if name not in ELECTRON_FILES_BLOCK]
    assert not missing, f"desktop release step is missing required updater asset(s): {missing!r}"


def test_electron_release_also_publishes_the_portable_build():
    portable_name, _ = us.expected_asset_names(WORKFLOW_VERSION_EXPR, portable=True)
    assert portable_name in ELECTRON_FILES_BLOCK


def test_ad19_six_signed_runtime_assets_still_published_not_swapped_away():
    """The runtime-repair workflow must keep publishing all six signed
    component assets."""
    names = [n.format(V=WORKFLOW_VERSION_EXPR) for n in SIGNED_RUNTIME_ASSET_NAMES]
    assert len(names) == 6
    missing = [name for name in names if name not in RUNTIME_FILES_BLOCK]
    assert not missing, f"AD-19 signed runtime asset(s) missing: {missing!r}"


def test_runtime_repair_release_publishes_only_those_six():
    """The desktop installer must never ride along on the runtime release."""
    for name in ("Setup.exe", "Portable.zip", "SHA256SUMS.txt", "release-manifest.json"):
        assert name not in RUNTIME_FILES_BLOCK, (
            f"runtime-repair workflow must not publish {name}"
        )


def test_release_step_asset_paths_use_exact_names_never_globs():
    """A `*` glob could pick up a stale artifact from a different version."""
    assert "*" not in ELECTRON_FILES_BLOCK
    assert "*" not in RUNTIME_FILES_BLOCK


def test_runtime_repair_workflow_cannot_produce_an_installer():
    """Inverted from the original assertion, which required the opposite and
    is what allowed a Qt-built Setup.exe to be published."""
    assert "packaging/build.py --no-installer" in RUNTIME_TEXT
    assert "choco install innosetup" not in RUNTIME_TEXT


def test_electron_workflow_installs_inno_setup_before_building():
    """The desktop workflow is the one that legitimately needs ISCC; without
    it build_electron_release.py cannot produce Setup.exe."""
    assert "choco install innosetup" in ELECTRON_TEXT


def test_electron_release_asserts_assets_exist_before_publishing():
    """A pre-publish existence/agreement assertion must run before publish."""
    marker = "Assert exactly the four desktop assets exist and agree"
    assert marker in ELECTRON_TEXT
    publish_idx = ELECTRON_TEXT.index("- name: Publish the stable desktop release")
    assert ELECTRON_TEXT.index(marker) < publish_idx


def test_prerelease_channel_preserved_for_suffixed_versions():
    """A beta tag (containing a '-' suffix) must not land on the stable
    auto-update channel."""
    for text in (ELECTRON_TEXT, RUNTIME_TEXT):
        assert "prerelease:" in text
        assert "contains(env.APP_VERSION, '-')" in text


# --------------------------------------------------------------------------- #
# Consumer-side proof: this is the exact failure the workflow change closes.
# --------------------------------------------------------------------------- #
def _asset(name: str, *, size: int = 1024) -> dict:
    return {
        "name": name,
        "state": "uploaded",
        "size": size,
        "browser_download_url": f"https://github.com/pasttrunks/lecturepack/releases/download/v{REAL_VERSION}/{name}",
    }


def _six_signed_assets(version: str) -> list[dict]:
    return [_asset(n.format(V=version)) for n in SIGNED_RUNTIME_ASSET_NAMES]


def test_select_asset_raises_for_six_signed_assets_only_release():
    """This is the exact regression: a release produced by the pre-fix
    workflow (only the six signed runtime assets) is unusable by the
    updater."""
    release = {"assets": _six_signed_assets(REAL_VERSION)}
    with pytest.raises(ValueError):
        us.select_asset(release, REAL_VERSION)
    with pytest.raises(ValueError):
        us.select_asset(release, REAL_VERSION, portable=True)


def test_select_asset_succeeds_once_installer_assets_are_also_present():
    """Once the three updater assets are added alongside the six signed
    assets (the add-back this plan performs), select_asset() must succeed
    for both the installer and portable channels."""
    setup_name, sums_name = us.expected_asset_names(REAL_VERSION)
    portable_name, _ = us.expected_asset_names(REAL_VERSION, portable=True)
    assets = _six_signed_assets(REAL_VERSION) + [
        _asset(setup_name),
        _asset(portable_name),
        _asset(sums_name),
    ]
    release = {"assets": assets}

    installer_selection = us.select_asset(release, REAL_VERSION)
    assert installer_selection["installer"]["name"] == setup_name
    assert installer_selection["checksum"]["name"] == sums_name

    portable_selection = us.select_asset(release, REAL_VERSION, portable=True)
    assert portable_selection["installer"]["name"] == portable_name
    assert portable_selection["checksum"]["name"] == sums_name
