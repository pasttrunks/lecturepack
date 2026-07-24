"""Pure update-logic tests (§14): versions, channel filtering, assets, hashing.

No Qt, no network. Exercises desktop/update_service.py directly.
"""
from __future__ import annotations

import hashlib
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import update_service as us  # noqa: E402


# ------------------------------------------------------------------ versions
def test_prerelease_ordering_not_string_ordering():
    assert us.is_newer("0.9.0-beta.2", "0.9.0-beta.1")
    assert us.is_newer("0.9.0", "0.9.0-beta.2")          # stable > its prerelease
    assert us.is_newer("0.9.1", "0.9.0")
    assert us.is_newer("1.0.0", "0.9.1")
    assert not us.is_newer("0.9.0-beta.1", "0.9.0-beta.2")
    # Plain string ordering would wrongly say "0.9.0" < "0.9.0-beta.2".
    assert "0.9.0" < "0.9.0-beta.2"                       # sanity: strings lie
    assert us.is_newer("0.9.0", "0.9.0-beta.2")           # our compare is correct


def test_v_prefix_normalization_and_channel():
    assert us.parse_version("v0.9.0-beta.2") == us.parse_version("0.9.0-beta.2")
    assert us.channel_of("0.9.0-beta.2") == "beta"
    assert us.channel_of("0.9.0") == "stable"
    assert us.channel_of("v1.0.0") == "stable"


def test_malformed_tags_rejected():
    assert us.parse_version("garbage") is None
    assert us.parse_version("") is None
    assert us.is_newer("not-a-version", "0.9.0") is False


# --------------------------------------------------------------- filtering
def _rel(tag, *, draft=False, prerelease=False, assets=None, body="", name=None):
    return {"tag_name": tag, "name": name or tag, "draft": draft,
            "prerelease": prerelease, "assets": assets or [],
            "published_at": "2026-07-22T10:00:00Z", "html_url": f"https://github.com/x/y/releases/{tag}",
            "body": body}


def test_draft_ignored_and_newest_selected():
    releases = [
        _rel("v0.9.0-beta.1", prerelease=True),
        _rel("v0.9.0-beta.3", prerelease=True, draft=True),   # draft -> ignored
        _rel("v0.9.0-beta.2", prerelease=True),
    ]
    sel = us.select_release(releases, "0.9.0-beta.1", channel="beta")
    assert sel["version"] == "0.9.0-beta.2" and sel["parsed"] == "0.9.0b2"


def test_stable_channel_ignores_prereleases():
    releases = [_rel("v1.0.0-rc.1", prerelease=True), _rel("v0.9.0")]
    sel = us.select_release(releases, "0.9.0-beta.1", channel="stable")
    assert sel["version"] == "0.9.0"


def test_beta_channel_accepts_prerelease():
    releases = [_rel("v0.9.0-beta.2", prerelease=True)]
    sel = us.select_release(releases, "0.9.0-beta.1", channel="beta")
    assert sel and sel["version"] == "0.9.0-beta.2"


def test_older_or_equal_releases_ignored():
    releases = [_rel("v0.9.0-beta.1", prerelease=True)]
    assert us.select_release(releases, "0.9.0-beta.1", channel="beta") is None


def test_skipped_flag_set_but_still_selected():
    releases = [_rel("v0.9.0-beta.2", prerelease=True)]
    sel = us.select_release(releases, "0.9.0-beta.1", channel="beta", skipped="0.9.0b2")
    assert sel["version"] == "0.9.0-beta.2" and sel["is_skipped"] is True
    # A newer version than the skipped one is not suppressed.
    releases2 = [_rel("v0.9.0-beta.3", prerelease=True)]
    sel2 = us.select_release(releases2, "0.9.0-beta.1", channel="beta", skipped="0.9.0b2")
    assert sel2["is_skipped"] is False


# ------------------------------------------------------------------ assets
def _asset(name, size=1000, url_host="github.com", state="uploaded", digest=None):
    a = {"name": name, "size": size, "state": state,
         "browser_download_url": f"https://{url_host}/x/y/releases/download/{name}"}
    if digest:
        a["digest"] = digest
    return a


def test_correct_setup_and_portable_assets_selected():
    rel = _rel("v0.9.0-beta.2", assets=[
        _asset("LecturePack-0.9.0-beta.2-Setup.exe"),
        _asset("LecturePack-0.9.0-beta.2-Portable.zip"),
        _asset("LecturePack-0.9.0-beta.2-SHA256SUMS.txt", size=200),
    ])
    got = us.select_asset(rel, "0.9.0-beta.2", portable=False)
    assert got["installer"]["name"].endswith("Setup.exe")
    got_p = us.select_asset(rel, "0.9.0-beta.2", portable=True)
    assert got_p["installer"]["name"].endswith("Portable.zip")


def test_source_archives_ignored_and_missing_checksum_rejected():
    rel = _rel("v0.9.0-beta.2", assets=[
        {"name": "Source code (zip)", "size": 5000, "state": "uploaded",
         "browser_download_url": "https://github.com/x/y/archive/refs/tags/v.zip"},
        _asset("LecturePack-0.9.0-beta.2-Setup.exe"),
    ])
    with pytest.raises(ValueError, match="checksum"):
        us.select_asset(rel, "0.9.0-beta.2")


def test_wrong_filename_zero_size_and_unsafe_url_rejected():
    with pytest.raises(ValueError, match="missing expected asset"):
        us.select_asset(_rel("v0.9.0-beta.2", assets=[_asset("Setup.exe")]), "0.9.0-beta.2")
    rel_zero = _rel("v0.9.0-beta.2", assets=[
        _asset("LecturePack-0.9.0-beta.2-Setup.exe", size=0),
        _asset("LecturePack-0.9.0-beta.2-SHA256SUMS.txt", size=100)])
    with pytest.raises(ValueError, match="zero"):
        us.select_asset(rel_zero, "0.9.0-beta.2")
    rel_bad = _rel("v0.9.0-beta.2", assets=[
        _asset("LecturePack-0.9.0-beta.2-Setup.exe", url_host="evil.example.com"),
        _asset("LecturePack-0.9.0-beta.2-SHA256SUMS.txt", size=100)])
    with pytest.raises(ValueError, match="trusted host"):
        us.select_asset(rel_bad, "0.9.0-beta.2")


def test_extra_hosts_allows_test_feed():
    rel = _rel("v0.9.0-beta.2", assets=[
        _asset("LecturePack-0.9.0-beta.2-Setup.exe", url_host="127.0.0.1:8999"),
        _asset("LecturePack-0.9.0-beta.2-SHA256SUMS.txt", size=100, url_host="127.0.0.1:8999")])
    got = us.select_asset(rel, "0.9.0-beta.2", extra_hosts={"127.0.0.1"})
    assert got["installer"]["name"].endswith("Setup.exe")
    # http is accepted ONLY for an explicitly configured host, never in prod.
    assert us._url_ok("http://127.0.0.1:8999/a", extra_hosts={"127.0.0.1"}) is True
    assert us._url_ok("http://127.0.0.1:8999/a") is False
    assert us._url_ok("http://github.com/a") is False


# ------------------------------------------------------------------ hashing
def test_sha256sums_parse_and_verify(tmp_path):
    f = tmp_path / "LecturePack-0.9.0-beta.2-Setup.exe"
    f.write_bytes(b"hello world")
    digest = hashlib.sha256(b"hello world").hexdigest()
    body = f"{digest.upper()}  LecturePack-0.9.0-beta.2-Setup.exe\n" \
           "deadbeef  other.zip\n"
    found = us.parse_sha256sums(body, "LecturePack-0.9.0-beta.2-Setup.exe")
    assert found == digest                     # case-insensitive match
    assert us.verify_file(str(f), found) is True
    assert us.verify_file(str(f), "0" * 64) is False


def test_digest_from_asset_and_reconcile():
    good = hashlib.sha256(b"x").hexdigest()
    assert us.digest_from_asset({"digest": f"sha256:{good}"}) == good
    assert us.digest_from_asset({"digest": "md5:abc"}) is None
    assert us.reconcile_digests(good, good) == (good, True)
    assert us.reconcile_digests(good, "f" * 64) == (good, False)   # disagreement
    assert us.reconcile_digests(good, None) == (good, True)
    assert us.reconcile_digests(None, None) == (None, False)


def test_verify_rejects_missing_or_malformed_digest(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"data")
    assert us.verify_file(str(f), None) is False
    assert us.verify_file(str(f), "not-hex") is False


# ------------------------------------------------------------------ overview
def test_build_overview_fields_and_safe_notes():
    rel = _rel("v0.9.0-beta.2", prerelease=True, name="Public Beta 2",
               body="## Improvements\n- Faster slides\n## Fixes\n- Fixed export\n"
                    "## Known limitations\n- No installer test\n"
                    "<script>alert(1)</script>",
               assets=[_asset("LecturePack-0.9.0-beta.2-Setup.exe", size=326000000)])
    ov = us.build_overview(rel, "0.9.0-beta.1",
                           installer_asset=rel["assets"][0])
    assert ov["available"] == "0.9.0-beta.2" and ov["current"] == "0.9.0-beta.1"
    assert ov["channel"] == "Beta" and ov["title"] == "Public Beta 2"
    assert "Faster slides" in ov["improvements"]
    assert "Fixed export" in ov["fixes"]
    assert any("installer test" in n for n in ov["limitations"])
    assert ov["size"].endswith("MB")
    # The raw <script> line is not turned into executable markup — it is only
    # ever plain text (a non-bullet, non-heading line is dropped from notes).
    assert all("<script>" not in n for n in ov["notes"])
