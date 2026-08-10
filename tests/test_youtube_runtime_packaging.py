"""Guard the pieces YouTube link import actually depends on.

Modern yt-dlp cannot fully extract YouTube without an external JavaScript
runtime: YouTube presents JS challenges that yt-dlp solves through its EJS
system, which needs the `yt_dlp_ejs` package AND a real runtime process
(Deno is upstream's default). LecturePack 2.0.0 shipped yt-dlp with neither,
and its self-test reported "yt-dlp available" anyway -- healthy-looking, but
degraded in practice.

These tests are NETWORK-FREE by design. The live proof lives in
scripts/release_url_import_probe.py, which is an explicit release gate rather
than part of every pytest run.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lecturepack.services import media_fetch  # noqa: E402
from lecturepack.services import packaged_health  # noqa: E402

SPEC = ROOT / "electron-spike" / "sidecar.spec"
SPEC_TEXT = SPEC.read_text(encoding="utf-8")


# --------------------------------------------------------------- yt-dlp opts
def test_base_opts_hands_yt_dlp_the_bundled_ffmpeg(monkeypatch, tmp_path):
    """Without ffmpeg_location, merges depend on a system FFmpeg the customer
    does not have."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ffmpeg.exe").write_bytes(b"stub")
    monkeypatch.setenv("LECTUREPACK_RUNTIME_ROOT", str(tmp_path))

    opts = media_fetch.MediaFetcher._base_opts()
    assert opts["ffmpeg_location"] == str(bin_dir)


def test_base_opts_never_forces_the_android_player_client():
    """The old android-only override predates EJS and bypasses the JS
    challenge path YouTube now requires, defeating the bundled runtime."""
    opts = media_fetch.MediaFetcher._base_opts()
    youtube_args = (opts.get("extractor_args") or {}).get("youtube") or {}
    assert "player_client" not in youtube_args


def test_base_opts_never_fetches_remote_components_on_a_customer_machine():
    """Everything EJS needs ships in the installer; first use must not pull
    components off npm or GitHub."""
    assert media_fetch.MediaFetcher._base_opts()["remote_components"] == []


# ------------------------------------------------------- runtime discovery
def test_js_runtime_is_discovered_from_the_bundled_bin_directory(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    deno = bin_dir / ("deno.exe" if os.name == "nt" else "deno")
    deno.write_bytes(b"stub")
    monkeypatch.setenv("LECTUREPACK_RUNTIME_ROOT", str(tmp_path))

    assert media_fetch.js_runtime_path() == str(deno)


def test_js_runtime_absent_reports_empty_rather_than_raising(monkeypatch, tmp_path):
    monkeypatch.setenv("LECTUREPACK_RUNTIME_ROOT", str(tmp_path))
    assert media_fetch.js_runtime_path() == ""
    assert media_fetch.js_runtime_version() == ""


def test_js_runtime_env_prepends_bundled_bin_once(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / ("deno.exe" if os.name == "nt" else "deno")).write_bytes(b"stub")
    monkeypatch.setenv("LECTUREPACK_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("PATH", "C:\\already" if os.name == "nt" else "/already")

    media_fetch._js_runtime_env()
    media_fetch._js_runtime_env()  # idempotent

    entries = os.environ["PATH"].split(os.pathsep)
    assert entries[0] == str(bin_dir)
    assert entries.count(str(bin_dir)) == 1


def test_youtube_support_reports_each_capability_separately():
    support = media_fetch.youtube_support()
    for key in ("yt_dlp", "ejs", "js_runtime", "ffmpeg_location"):
        assert key in support, support
    # These are independent answers, never one conflated boolean.
    assert isinstance(support["yt_dlp"], bool)
    assert isinstance(support["ejs"], bool)
    assert isinstance(support["js_runtime"], bool)


# ------------------------------------------------------- health diagnostics
def _health(support: dict) -> dict:
    return packaged_health.run_packaged_health(
        runtime_root=ROOT,
        data_dir=ROOT,
        controller=object(),
        study_core_info=lambda: {"available": True, "implementation": "rust"},
        media_available=lambda: True,
        media_version=lambda: "2026.07.04",
        youtube_support=lambda: support,
    )


def _check(health: dict, check_id: str) -> dict:
    return next(c for c in health["checks"] if c["id"] == check_id)


def test_health_reports_ejs_and_js_runtime_as_distinct_checks():
    health = _health({"yt_dlp": True, "ejs": True, "ejs_version": "0.8.0",
                      "js_runtime": True, "js_runtime_version": "deno 2.9.5"})
    ids = [c["id"] for c in health["checks"]]
    assert "yt_dlp" in ids and "yt_dlp_ejs" in ids and "js_runtime" in ids
    assert _check(health, "yt_dlp_ejs")["ok"] is True
    assert _check(health, "js_runtime")["ok"] is True


def test_health_flags_a_missing_js_runtime_even_when_yt_dlp_imports():
    """This is exactly the v2.0.0 blind spot."""
    health = _health({"yt_dlp": True, "ejs": True, "js_runtime": False})
    assert _check(health, "yt_dlp")["ok"] is True
    assert _check(health, "js_runtime")["ok"] is False
    assert health["passed"] is False


def test_health_flags_missing_ejs_even_when_a_runtime_exists():
    health = _health({"yt_dlp": True, "ejs": False, "js_runtime": True})
    assert _check(health, "yt_dlp_ejs")["ok"] is False
    assert health["passed"] is False


def test_missing_youtube_support_callable_degrades_closed():
    """An older caller that does not pass youtube_support must not be
    reported as having healthy YouTube support."""
    health = packaged_health.run_packaged_health(
        runtime_root=ROOT, data_dir=ROOT, controller=object(),
        study_core_info=lambda: {"available": True, "implementation": "rust"},
        media_available=lambda: True, media_version=lambda: "x",
    )
    assert _check(health, "js_runtime")["ok"] is False
    assert _check(health, "yt_dlp_ejs")["ok"] is False


def test_youtube_checks_are_not_fatal_at_startup():
    """A degraded link importer must not stop LecturePack from launching for
    local lecture files."""
    degraded = _health({"yt_dlp": True, "ejs": False, "js_runtime": False})
    healthy = _health({"yt_dlp": True, "ejs": True, "js_runtime": True})
    assert _check(degraded, "js_runtime")["fatal_at_startup"] is False
    assert _check(degraded, "yt_dlp_ejs")["fatal_at_startup"] is False
    # Losing YouTube support must not change whether the app can start. (The
    # absolute value depends on unrelated packaged binaries being present in
    # the checkout, so compare the two runs rather than asserting True.)
    assert degraded["startup_ok"] == healthy["startup_ok"]
    # It does, however, make the overall health contract fail.
    assert degraded["passed"] is False


# ------------------------------------------------------------ packaging spec
def test_spec_pins_the_bundled_js_runtime_by_digest():
    assert 'DENO_VERSION = "' in SPEC_TEXT
    assert 'DENO_SHA256 = "' in SPEC_TEXT
    digest = SPEC_TEXT.split('DENO_SHA256 = "')[1].split('"')[0]
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), digest
    # The digest must actually be enforced, not merely recorded.
    assert "does not match the pinned digest" in SPEC_TEXT


def test_spec_ships_deno_into_the_bundled_bin_directory():
    assert '(str(deno), "bin")' in SPEC_TEXT


def test_official_build_requires_ejs_and_its_solver_javascript():
    assert "yt_dlp_ejs" in SPEC_TEXT
    # The solver is minified JS data, not Python modules: collecting only
    # submodules would import cleanly and still fail at runtime.
    assert 'collect_data_files("yt_dlp_ejs"' in SPEC_TEXT
    assert "solver JavaScript" in SPEC_TEXT


def test_official_build_requires_the_js_runtime():
    assert "requires the bundled JavaScript runtime" in SPEC_TEXT


def test_release_builder_gates_on_all_three_youtube_checks():
    builder = (ROOT / "scripts" / "build_electron_release.py").read_text(encoding="utf-8")
    for check_id in ("yt_dlp", "yt_dlp_ejs", "js_runtime"):
        assert f'"{check_id}"' in builder, check_id


def test_release_probe_exists_and_is_not_part_of_the_offline_suite():
    probe = ROOT / "scripts" / "release_url_import_probe.py"
    assert probe.is_file()
    text = probe.read_text(encoding="utf-8")
    assert "RELEASE-ONLY" in text
    # It must not be collected by pytest.
    assert not probe.name.startswith("test_")


@pytest.mark.parametrize("dependency_file", ["requirements.txt", "app/requirements.txt"])
def test_requirements_pull_the_ejs_extra(dependency_file):
    text = (ROOT / dependency_file).read_text(encoding="utf-8")
    assert "yt-dlp[default]" in text, (
        f"{dependency_file} must request the [default] extra so yt-dlp-ejs is installed"
    )


def test_release_lock_pins_ejs():
    text = (ROOT / "requirements-release.txt").read_text(encoding="utf-8")
    assert "yt-dlp-ejs==" in text
