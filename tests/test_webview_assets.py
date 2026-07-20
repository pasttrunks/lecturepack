"""Tests for the WebView slide-asset resolver (app/desktop/assets.py).

The resolver is the fix for blank slide thumbnails/preview: it maps the
``lpasset://job/<job_id>/<filename>`` URLs the UI puts in <img src> to on-disk
job frame images, with strict job-membership and traversal checks.

Only the pure-Python logic is exercised here (no Qt), so these run headless.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_ASSETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "desktop", "assets.py")


def _load_assets():
    spec = importlib.util.spec_from_file_location("lp_webview_assets", _ASSETS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


assets = _load_assets()


def _make_job(data_dir, job_id, filename, content=b"\x89PNG\r\n", base="jobs"):
    cand = os.path.join(data_dir, base, job_id, "frames", "candidates")
    os.makedirs(cand, exist_ok=True)
    path = os.path.join(cand, filename)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


# --------------------------------------------------------------- URL building
def test_asset_url_shape():
    url = assets.asset_url("abc-123", "slide_45_1500.png")
    assert url == "lpasset://job/abc-123/slide_45_1500.png"


def test_asset_url_encodes_unusual_chars():
    url = assets.asset_url("job1", "slide with space.png")
    assert "%20" in url


# ------------------------------------------------------------------ MIME
@pytest.mark.parametrize("name,mime", [
    ("a.png", "image/png"), ("a.jpg", "image/jpeg"), ("a.jpeg", "image/jpeg"),
    ("a.webp", "image/webp"), ("a.gif", "image/gif"), ("a.bin", "application/octet-stream"),
])
def test_guess_mime(name, mime):
    assert assets.guess_mime(name) == mime


# ------------------------------------------------------------- happy paths
def test_resolves_accepted_slide(tmp_path):
    _make_job(str(tmp_path), "job1", "slide_45_1500.png", b"PNGDATA")
    r = assets.AssetResolver(str(tmp_path))
    out = r.resolve("job1", "slide_45_1500.png")
    assert out is not None
    mime, data = out
    assert mime == "image/png" and data == b"PNGDATA"


def test_resolves_path_with_spaces_in_data_dir(tmp_path):
    data_dir = str(tmp_path / "One Drive Data")
    _make_job(data_dir, "job1", "slide_1.png", b"X")
    r = assets.AssetResolver(data_dir)
    assert r.resolve("job1", "slide_1.png") is not None


def test_resolves_unicode_filename(tmp_path):
    _make_job(str(tmp_path), "job1", "slíde_骨.png", b"U")
    r = assets.AssetResolver(str(tmp_path))
    # URL-encoded on the way in, decoded by the resolver.
    from urllib.parse import quote
    assert r.resolve("job1", quote("slíde_骨.png")) is not None


def test_resolves_archived_job(tmp_path):
    _make_job(str(tmp_path), "job1", "slide_1.png", b"A", base="archive")
    r = assets.AssetResolver(str(tmp_path))
    assert r.resolve("job1", "slide_1.png") is not None


# --------------------------------------------------------------- rejections
def test_missing_file_returns_none(tmp_path):
    r = assets.AssetResolver(str(tmp_path))
    assert r.resolve("job1", "nope.png") is None


def test_rejects_directory_traversal(tmp_path):
    # Put a secret file one level above the frames dir.
    secret = os.path.join(str(tmp_path), "jobs", "job1", "manifest.json")
    os.makedirs(os.path.dirname(secret), exist_ok=True)
    with open(secret, "wb") as fh:
        fh.write(b"SECRET")
    _make_job(str(tmp_path), "job1", "ok.png", b"OK")
    r = assets.AssetResolver(str(tmp_path))
    assert r.resolve("job1", "../../manifest.json") is None
    assert r.resolve("job1", "..\\..\\manifest.json") is None
    assert r.resolve_path("job1", "..") is None


def test_rejects_absolute_path(tmp_path):
    r = assets.AssetResolver(str(tmp_path))
    assert r.resolve("job1", os.path.abspath(__file__)) is None


def test_rejects_bad_job_id(tmp_path):
    _make_job(str(tmp_path), "job1", "ok.png", b"OK")
    r = assets.AssetResolver(str(tmp_path))
    assert r.resolve("../other", "ok.png") is None
    assert r.resolve("a/b", "ok.png") is None


def test_does_not_cross_into_other_job(tmp_path):
    _make_job(str(tmp_path), "job1", "a.png", b"1")
    _make_job(str(tmp_path), "job2", "b.png", b"2")
    r = assets.AssetResolver(str(tmp_path))
    # job1 cannot reach job2's file even via a crafted name
    assert r.resolve("job1", "b.png") is None
