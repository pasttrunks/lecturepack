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

PRODUCTION_MAIN_JS = os.path.join(WORKTREE, "electron-spike", "production-main.js")


def _production_main_source() -> str:
    with open(PRODUCTION_MAIN_JS, encoding="utf-8") as handle:
        return handle.read()


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
def _manifest(**overrides) -> dict:
    """A well-formed v2.0.1 release manifest, optionally corrupted per test."""
    doc = {
        "version": "2.0.1",
        "platform": "win32",
        "architecture": "x64",
        "installers": [{"filename": "LecturePack-2.0.1-Setup.exe", "sha256": "a" * 64}],
    }
    doc.update(overrides)
    return doc


_WANT = {"version": "v2.0.1", "filename": "LecturePack-2.0.1-Setup.exe"}


def test_expected_installer_sha256_from_manifest():
    manifest = _manifest()
    assert _call("expectedInstallerSha256", manifest,
                 "LecturePack-2.0.1-Setup.exe", "2.0.1") == "a" * 64


def test_expected_installer_sha256_rejects_malformed():
    assert _call("expectedInstallerSha256", {"installers": []},
                 "LecturePack-2.0.1-Setup.exe", "2.0.1") is None


# ------------------------------------------- release-manifest trust gates
def test_verify_release_manifest_accepts_a_matching_manifest():
    verdict = _call("verifyReleaseManifest", _manifest(), _WANT)
    assert verdict == {"ok": True, "sha256": "a" * 64, "reason": "verified"}


def test_verify_release_manifest_accepts_the_real_published_v2_0_0_manifest():
    """The tightened gate must still accept genuine LecturePack manifests."""
    published = {
        "version": "2.0.0",
        "platform": "win32",
        "architecture": "x64",
        "installers": [{
            "filename": "LecturePack-2.0.0-Setup.exe",
            "sha256": "5c36408b31af79221329ca8e3ad54d547a319d4dba077b4be9b925676c648be6",
        }],
    }
    verdict = _call("verifyReleaseManifest", published,
                    {"version": "v2.0.0", "filename": "LecturePack-2.0.0-Setup.exe"})
    assert verdict["ok"] is True
    assert verdict["sha256"] == published["installers"][0]["sha256"]


@pytest.mark.parametrize(
    ("manifest", "reason"),
    [
        (None, "manifest_unparseable"),
        (_manifest(version="2.0.2"), "manifest_version_mismatch"),
        (_manifest(platform="darwin"), "manifest_platform_mismatch"),
        (_manifest(architecture="arm64"), "manifest_architecture_mismatch"),
        (_manifest(installers=[]), "manifest_missing_installers"),
        (_manifest(installers=[{"filename": "LecturePack-2.0.1-Setup.exe", "sha256": "nope"}]),
         "manifest_invalid_sha256"),
    ],
)
def test_verify_release_manifest_rejects_every_bad_field(manifest, reason):
    verdict = _call("verifyReleaseManifest", manifest, _WANT)
    assert verdict["ok"] is False
    assert verdict["sha256"] is None
    assert verdict["reason"] == reason


def test_verify_release_manifest_refuses_a_digest_for_a_different_setup_exe():
    """A hash published for some other Setup.exe must never be accepted."""
    foreign = _manifest(installers=[
        {"filename": "LecturePack-9.9.9-Setup.exe", "sha256": "b" * 64},
    ])
    verdict = _call("verifyReleaseManifest", foreign, _WANT)
    assert verdict["ok"] is False
    assert verdict["reason"] == "manifest_installer_not_listed"


def test_verify_release_manifest_ignores_unbound_top_level_digests():
    """Legacy 'installer_sha256'/'sha256' shortcuts bind to no filename."""
    loose = {
        "version": "2.0.1", "platform": "win32", "architecture": "x64",
        "installer_sha256": "c" * 64, "sha256": "d" * 64,
    }
    verdict = _call("verifyReleaseManifest", loose, _WANT)
    assert verdict["ok"] is False
    assert verdict["sha256"] is None


def test_verify_release_manifest_rejects_ambiguous_duplicate_entries():
    entry = {"filename": "LecturePack-2.0.1-Setup.exe", "sha256": "a" * 64}
    other = {"filename": "LecturePack-2.0.1-Setup.exe", "sha256": "b" * 64}
    verdict = _call("verifyReleaseManifest", _manifest(installers=[entry, other]), _WANT)
    assert verdict["ok"] is False
    assert verdict["reason"] == "manifest_duplicate_installer_entry"


# --------------------------------------------- skip / auto-check settings
def test_skipped_version_persists_and_expires_when_something_newer_ships(tmp_path):
    data_dir = str(tmp_path).replace("\\", "/")
    assert _call("setSkippedVersion", data_dir, "v2.0.1") == "2.0.1"
    assert _call("isVersionSkipped", data_dir, "2.0.1") is True
    # Anything newer than the skipped version must still be offered.
    assert _call("isVersionSkipped", data_dir, "2.0.2") is False
    # Clearing the skip restores normal behaviour.
    assert _call("setSkippedVersion", data_dir, "") == ""
    assert _call("isVersionSkipped", data_dir, "2.0.1") is False


def test_auto_check_preference_persists_and_suppresses_background_checks(tmp_path):
    data_dir = str(tmp_path).replace("\\", "/")
    assert _call("shouldAutoCheck", data_dir) is True
    _call("setAutoCheckEnabled", data_dir, False)
    assert _call("loadState", data_dir)["autoCheck"] is False
    assert _call("shouldAutoCheck", data_dir) is False
    _call("setAutoCheckEnabled", data_dir, True)
    assert _call("shouldAutoCheck", data_dir) is True


def test_parse_manifest_rejects_bad_json():
    assert _call("parseManifest", "not json") is None
    assert _call("parseManifest", '{"version":"2.0.0"}') == {"version": "2.0.0"}

# ---------------------------------------------------- global rollout matrix
# These exist because an update has to be correct for EVERY installed version
# in the wild, not just the one on the release engineer's machine. The GitHub
# tag carries a "v" prefix while every internal surface is bare semver, so each
# case below is written with the prefix exactly as the real feed serves it.

@pytest.mark.parametrize("installed", ["0.9.0-beta.3", "0.9.0-beta.13", "2.0.0", "2.0.1", "2.0.2"])
def test_every_shipped_version_is_offered_the_current_stable(installed):
    """No user is stranded: every version ever shipped must see a newer stable."""
    assert _call("isNewer", "v2.0.3", installed) is True


def test_current_version_is_never_offered_to_itself():
    """The nag loop that a v-prefixed lexicographic compare would cause.

    "v2.0.3" > "2.0.3" as plain strings, so a naive compare would tell every
    up-to-date user, forever, that an update is available.
    """
    assert _call("isNewer", "v2.0.3", "2.0.3") is False
    assert _call("compareVersions", "v2.0.3", "2.0.3") == 0


def test_updates_never_go_backwards():
    assert _call("isNewer", "v2.0.2", "2.0.3") is False


def test_double_digit_patch_is_not_compared_lexicographically():
    """2.0.10 must beat 2.0.9 — this breaks the day the patch number rolls over."""
    assert _call("isNewer", "v2.0.10", "2.0.9") is True
    assert _call("isNewer", "v2.10.0", "2.9.0") is True


def test_stable_users_are_never_offered_a_prerelease():
    assert _call("isStable", "v2.0.3") is True
    assert _call("isStable", "v2.1.0-rc.1") is False
    assert _call("isNewer", "2.0.3", "2.0.3-rc.1") is True


def test_release_without_an_installer_asset_fails_closed():
    """A release published with notes but no Setup.exe must not half-update."""
    picked = _call("selectInstallerAsset", {"assets": [{"name": "notes.txt"}]})
    assert picked["installer"] is None


# ------------------------------------------------- installer launch ordering
def test_installer_is_launched_after_shutdown_not_before():
    """The app must release its files BEFORE the installer runs.

    Windows cannot replace a running .exe. production-main.js used to spawn the
    installer and then quit, so the installer could start while this app and
    its sidecar still held resources\LecturePackSidecar open. Reproduced by
    installing over a running app: Inno exits 5 and installs NOTHING, so the
    user clicks "Download and Install", the app closes, and they reopen on the
    old version with no error. The installer is now deferred to requestQuit(),
    after stopSession() has shut the sidecar down.
    """
    source = _production_main_source()
    install_fn = source[source.index("async function installDownloadedUpdate"):]
    install_fn = install_fn[: install_fn.index("\nasync function handleCommand")]
    assert "updater.install(installerPath)" not in install_fn, (
        "installDownloadedUpdate spawns the installer directly again; that races the app's "
        "own shutdown and the update silently fails"
    )
    assert "pendingInstaller = {" in install_fn

    # ...and requestQuit must launch it only inside the post-shutdown callback.
    quit_fn = source[source.index("function requestQuit()"):][:1600]
    assert "launchPendingInstaller()" in quit_fn
    assert "stopSession(session)" in quit_fn
    # A hung shutdown must not swallow the update.
    assert "INSTALLER_SHUTDOWN_GRACE_MS" in quit_fn


def test_pending_installer_is_consumed_exactly_once():
    source = _production_main_source()
    fn = source[source.index("function launchPendingInstaller()"):]
    fn = fn[: fn.index("\n}\n") + 3]
    assert "pendingInstaller = null;" in fn, "a re-entrant quit could launch two installers"
