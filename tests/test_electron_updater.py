"""Focused tests for the Electron production updater (electron-spike/updater.js).

The updater is a Node module in the Electron main. These tests exercise its
pure, network-free logic (semver comparison, stable-channel filtering, asset
selection, manifest verification) by running the module under Node and
asserting on its exported functions. No real GitHub or installer is touched.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATER_JS = os.path.join(WORKTREE, "electron-spike", "updater.js")

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(
    NODE is None,
    reason="Node is required to exercise the Electron updater module.",
)


def _call(function: str, *args) -> object:
    """Run one exported updater function with JSON args under Node."""
    script = (
        "const u=require(process.argv[1]);"
        "const name=process.argv[2];"
        "const args=JSON.parse(process.argv[3]);"
        "const out=u[name](...args);"
        "process.stdout.write(JSON.stringify(typeof out==='object'?out:out));"
    )
    result = subprocess.run(
        [NODE, "-e", script, UPDATER_JS, function, json.dumps(args)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


# ------------------------------------------------------------------ semver
def test_semver_major_minor_patch_ordering():
    assert _call("isNewer", "2.0.1", "2.0.0") is True
    assert _call("isNewer", "2.1.0", "2.0.9") is True
    assert _call("isNewer", "3.0.0", "2.99.99") is True
    assert _call("isNewer", "2.0.0", "2.0.0") is False
    assert _call("isNewer", "2.0.0", "2.0.1") is False


def test_prerelease_ordering_not_string_ordering():
    # Stable beats its prerelease; plain string compare would lie.
    assert _call("isNewer", "2.0.0", "2.0.0-beta.2") is True
    assert _call("isNewer", "2.0.0-beta.2", "2.0.0-beta.1") is True
    assert _call("isNewer", "2.0.0-beta.1", "2.0.0-beta.2") is False


def test_stable_channel_detection():
    assert _call("isStable", "2.0.0") is True
    assert _call("isStable", "2.0.0-beta.1") is False
    assert _call("isStable", "v2.0.0") is True


# ------------------------------------------------------------------ channel
def test_select_stable_release_ignores_draft_prerelease():
    releases = [
        {"tag_name": "v2.0.0", "draft": False, "prerelease": False,
         "assets": [{"name": "LecturePack-2.0.0-Setup.exe"}]},
        {"tag_name": "v2.1.0", "draft": True, "prerelease": False,
         "assets": [{"name": "LecturePack-2.1.0-Setup.exe"}]},
        {"tag_name": "v2.0.1-beta.1", "draft": False, "prerelease": True,
         "assets": [{"name": "LecturePack-2.0.1-beta.1-Setup.exe"}]},
    ]
    selected = _call("selectStableRelease", releases, "2.0.0")
    assert selected is None or selected == {}


def test_select_stable_release_picks_newest_stable():
    releases = [
        {"tag_name": "v2.0.0", "draft": False, "prerelease": False,
         "assets": [{"name": "LecturePack-2.0.0-Setup.exe"}]},
        {"tag_name": "v2.1.0", "draft": False, "prerelease": False,
         "assets": [{"name": "LecturePack-2.1.0-Setup.exe"}]},
    ]
    selected = _call("selectStableRelease", releases, "2.0.0")
    assert selected and selected["tag_name"] == "v2.1.0"


def test_select_stable_release_ignores_runtime_only():
    releases = [
        {"tag_name": "v2.0.0", "draft": False, "prerelease": False,
         "assets": [{"name": "LecturePack-2.0.0-Runtime-ffmpeg.zip"}]},
        {"tag_name": "v2.0.1", "draft": False, "prerelease": False,
         "assets": [{"name": "LecturePack-2.0.1-Setup.exe"}]},
    ]
    selected = _call("selectStableRelease", releases, "2.0.0")
    assert selected and selected["tag_name"] == "v2.0.1"


# ------------------------------------------------------------------ asset
def test_select_installer_asset_and_manifest():
    release = {
        "assets": [
            {"name": "LecturePack-2.0.0-Setup.exe", "browser_download_url": "https://x/exe"},
            {"name": "LecturePack-2.0.0-release-manifest.json", "browser_download_url": "https://x/manifest"},
        ]
    }
    sel = _call("selectInstallerAsset", release)
    assert sel["installer"]["name"] == "LecturePack-2.0.0-Setup.exe"
    assert sel["manifest"]["name"] == "LecturePack-2.0.0-release-manifest.json"


# ------------------------------------------------------------------ manifest
def test_expected_installer_sha256_from_manifest():
    manifest = {
        "version": "2.0.0",
        "installers": [{"filename": "LecturePack-2.0.0-Setup.exe",
                        "sha256": "a" * 64}],
    }
    assert _call("expectedInstallerSha256", manifest) == "a" * 64


def test_expected_installer_sha256_rejects_malformed():
    assert _call("expectedInstallerSha256", {"installers": []}) is None


def test_parse_manifest_rejects_bad_json():
    assert _call("parseManifest", "not json") is None
    assert _call("parseManifest", '{"version":"2.0.0"}') == {"version": "2.0.0"}