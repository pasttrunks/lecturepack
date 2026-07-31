"""Contract test guarding D-22: the release workflow must publish the exact
three assets the in-app updater requires, additively alongside the six signed
AD-19 runtime-repair assets.

The updater's own consumer contract is `expected_asset_names()`
(app/desktop/update_service.py); this test derives the required filenames from
that function rather than hardcoding them a second time, so it follows any
future change to `APP_NAME` or the filename template automatically, and the
workflow must keep up.

No YAML parser is used or required — PyYAML is not pinned in
app/requirements.txt or app/requirements-build.txt, and AGENTS.md forbids
adding unapproved third-party dependencies. Plain text-membership assertions
over exact filenames (never globs) are sufficient to guard this contract.
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
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
WORKFLOW_TEXT = WORKFLOW_PATH.read_text(encoding="utf-8")

# The literal GitHub Actions expression release.yml uses for the version —
# not a real version string. expected_asset_names() only formats it into an
# f-string, so passing this literal is exactly what proves the workflow's
# published names track the updater's consumer contract.
WORKFLOW_VERSION_EXPR = "${{ env.APP_VERSION }}"

# A concrete version, used only for the select_asset() payload tests below,
# where a real (non-template) version string is required.
REAL_VERSION = "0.9.0-beta.6"

SIGNED_RUNTIME_ASSET_NAMES = (
    f"LecturePack-{{V}}-RuntimeManifest-v1.json",
    f"LecturePack-{{V}}-RuntimeManifest-v1.json.sig",
    f"LecturePack-{{V}}-Runtime-ffmpeg.zip",
    f"LecturePack-{{V}}-Runtime-whisper-cpu.zip",
    f"LecturePack-{{V}}-Runtime-model-base-en.zip",
    f"LecturePack-{{V}}-Runtime-smoke-fixture.zip",
)


def _release_step_files_block(text: str) -> str:
    """Isolate the `files:` list of the 'Release exact signed assets' step.

    Assertions below operate on this block (not the whole file) so a name
    that merely appears elsewhere in the workflow (e.g. in a comment) cannot
    make the contract test pass.
    """
    marker = "- name: Release exact signed assets"
    assert marker in text, "release.yml is missing the 'Release exact signed assets' step"
    after_marker = text[text.index(marker):]
    files_marker = "files: |"
    assert files_marker in after_marker, "release step has no files: list"
    after_files = after_marker[after_marker.index(files_marker) + len(files_marker):]
    lines = []
    for line in after_files.splitlines()[1:]:
        if line.strip() == "" or line.lstrip().startswith("- name:"):
            break
        lines.append(line)
    assert lines, "release step files: list parsed empty"
    return "\n".join(lines)


RELEASE_FILES_BLOCK = _release_step_files_block(WORKFLOW_TEXT)


def test_expected_asset_names_returns_two_tuple_shape():
    """The producer-side workflow assertion depends on this exact shape:
    (primary_asset_name, checksum_asset_name). If this ever drifted to a
    different arity, the workflow's derived assertions below would silently
    stop matching the real consumer contract."""
    installer_names = us.expected_asset_names(WORKFLOW_VERSION_EXPR)
    portable_names = us.expected_asset_names(WORKFLOW_VERSION_EXPR, portable=True)
    for names in (installer_names, portable_names):
        assert isinstance(names, tuple)
        assert len(names) == 2
    # Both channels share the same checksum file name.
    assert installer_names[1] == portable_names[1]


def test_release_step_publishes_all_updater_required_asset_names():
    """Deleting any one of the three updater asset names from the release
    step's files: list must turn this test red."""
    required = set(us.expected_asset_names(WORKFLOW_VERSION_EXPR)) | set(
        us.expected_asset_names(WORKFLOW_VERSION_EXPR, portable=True)
    )
    assert len(required) == 3, f"expected exactly 3 required updater asset names, got {required!r}"
    missing = [name for name in required if name not in RELEASE_FILES_BLOCK]
    assert not missing, f"release step is missing required updater asset(s): {missing!r}"


def test_ad19_six_signed_runtime_assets_still_published_not_swapped_away():
    """D-22 is an add-back, never a re-swap. If a future change replaced the
    six signed runtime component assets with the installer assets (the
    a6164b1 shape this plan corrects), this test must fail."""
    names = [n.format(V=WORKFLOW_VERSION_EXPR) for n in SIGNED_RUNTIME_ASSET_NAMES]
    assert len(names) == 6
    missing = [name for name in names if name not in RELEASE_FILES_BLOCK]
    assert not missing, f"AD-19 signed runtime asset(s) missing from release step: {missing!r}"


def test_release_step_asset_paths_use_exact_names_never_globs():
    """A `*` glob could pick up a stale artifact from a different version;
    every published path must be an exact, version-pinned filename."""
    assert "*" not in RELEASE_FILES_BLOCK


def test_workflow_no_longer_builds_with_no_installer_flag():
    """--no-installer is what stopped Setup.exe from ever being produced;
    its presence anywhere in the workflow reopens the regression."""
    assert "--no-installer" not in WORKFLOW_TEXT


def test_workflow_installs_inno_setup_before_building():
    """build.py silently skips the installer (prints a WARNING and returns)
    when ISCC is not found — a runner without Inno Setup must fail loudly
    instead of shipping an updater-blind release."""
    assert "choco install innosetup" in WORKFLOW_TEXT


def test_release_step_asserts_updater_assets_exist_before_publishing():
    """A pre-publish existence/non-empty assertion must run before the
    release-publish step, mirroring the existing six-asset count idiom."""
    assert "Assert updater assets exist" in WORKFLOW_TEXT
    publish_idx = WORKFLOW_TEXT.index("- name: Release exact signed assets")
    assert_idx = WORKFLOW_TEXT.index("Assert updater assets exist")
    assert assert_idx < publish_idx, "updater asset assertion must run before the release-publish step"


def test_prerelease_channel_preserved_for_suffixed_versions():
    """A beta tag (containing a '-' suffix) must not land on the stable
    auto-update channel."""
    assert "prerelease:" in WORKFLOW_TEXT
    assert "contains(env.APP_VERSION, '-')" in WORKFLOW_TEXT


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
