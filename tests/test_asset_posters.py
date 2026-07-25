"""Job-card poster frames (lpasset://poster/<job_id>/poster).

Posters are generated lazily and cached at the job root. Two sources, cheapest
first: an existing slide frame (plain downscale) else one ffmpeg frame grab.
Resolution must be NON-BLOCKING -- the scheme handler runs on the main thread.

Uses a temp data dir; never touches real LecturePackData.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from desktop import assets  # noqa: E402
from desktop.assets import POSTER_HOST, AssetResolver, poster_url  # noqa: E402


def _make_job(root, job_id="job1", video_path=None, frames=()):
    job = os.path.join(root, "jobs", job_id)
    os.makedirs(job, exist_ok=True)
    manifest = {"schema_version": 1, "job_id": job_id, "source": {}}
    if video_path is not None:
        manifest["source"] = {"original_path": str(video_path),
                              "filename": os.path.basename(str(video_path))}
    with open(os.path.join(job, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
    for sub, name in frames:
        d = os.path.join(job, "frames", sub) if sub else os.path.join(job, "frames")
        os.makedirs(d, exist_ok=True)
        _write_png(os.path.join(d, name))
    return job


def _write_png(path):
    """A real 2x2 PNG so QImage can actually decode it."""
    import base64
    png = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGP8z8DAwMDAxMDAwMAA"
        b"AB4AAqEA/xUAAAAASUVORK5CYII=")
    with open(path, "wb") as fh:
        fh.write(png)


# ------------------------------------------------------------------ URL shape

def test_poster_url_shape():
    assert poster_url("abc") == "lpasset://poster/abc/poster"
    assert poster_url("abc", "7") == "lpasset://poster/abc/poster?v=7"


def test_poster_url_quotes_job_id():
    assert "/" not in poster_url("a b/c").split("://", 1)[1].split("/", 1)[1].rsplit("/", 1)[0]


# ------------------------------------------------------------------ job roots

def test_job_root_finds_live_and_archived(tmp_path):
    r = AssetResolver(str(tmp_path))
    _make_job(str(tmp_path), "live")
    os.makedirs(os.path.join(str(tmp_path), "archive", "old"))
    assert r._job_root("live") is not None
    assert r._job_root("old") is not None
    assert r._job_root("missing") is None


@pytest.mark.parametrize("bad", ["..", "../../etc", "a/b", "a\\b", "", "."])
def test_job_root_rejects_traversal_and_separators(tmp_path, bad):
    r = AssetResolver(str(tmp_path))
    assert r._job_root(bad) is None
    assert r.resolve_poster(bad) is None
    assert r.poster_path(bad) is None


# ------------------------------------------------------------------ sources

def test_source_video_requires_the_file_to_exist(tmp_path):
    r = AssetResolver(str(tmp_path))
    _make_job(str(tmp_path), "j", video_path=str(tmp_path / "gone.mp4"))
    assert r.source_video("j") is None          # path recorded but file deleted
    real = tmp_path / "there.mp4"
    real.write_bytes(b"x")
    _make_job(str(tmp_path), "k", video_path=str(real))
    assert r.source_video("k") == str(real)


def test_source_video_survives_missing_or_broken_manifest(tmp_path):
    r = AssetResolver(str(tmp_path))
    job = os.path.join(str(tmp_path), "jobs", "j")
    os.makedirs(job)
    assert r.source_video("j") is None           # no manifest at all
    with open(os.path.join(job, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert r.source_video("j") is None           # unparseable manifest


def test_existing_frame_prefers_accepted_over_candidates(tmp_path):
    r = AssetResolver(str(tmp_path))
    _make_job(str(tmp_path), "j", frames=[("candidates", "c.png"), ("accepted", "a.png")])
    assert os.path.basename(r._existing_frame("j")) == "a.png"


def test_existing_frame_ignores_non_images(tmp_path):
    r = AssetResolver(str(tmp_path))
    job = _make_job(str(tmp_path), "j")
    d = os.path.join(job, "frames", "accepted")
    os.makedirs(d)
    with open(os.path.join(d, "notes.txt"), "w") as fh:
        fh.write("x")
    assert r._existing_frame("j") is None


# ------------------------------------------------------------------ resolution

def test_resolve_poster_is_non_blocking_and_returns_none_first(tmp_path, monkeypatch):
    """First request must not decode inline -- it schedules and returns None."""
    r = AssetResolver(str(tmp_path))
    _make_job(str(tmp_path), "j", frames=[("accepted", "a.png")])
    scheduled = []
    monkeypatch.setattr(r, "_schedule_thumb", lambda src, dst: scheduled.append((src, dst)))
    assert r.resolve_poster("j") is None
    assert len(scheduled) == 1
    assert scheduled[0][1] == r.poster_path("j")


def test_resolve_poster_serves_cache_when_present(tmp_path):
    r = AssetResolver(str(tmp_path))
    _make_job(str(tmp_path), "j")
    dst = r.poster_path("j")
    with open(dst, "wb") as fh:
        fh.write(b"POSTERBYTES")
    mime, data = r.resolve_poster("j")
    assert data == b"POSTERBYTES"
    assert mime in ("image/webp", "image/jpeg")


def test_resolve_poster_uses_ffmpeg_only_when_no_frames(tmp_path, monkeypatch):
    r = AssetResolver(str(tmp_path), ffmpeg_exe="ffmpeg.exe")
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    _make_job(str(tmp_path), "vid", video_path=str(vid))
    _make_job(str(tmp_path), "framed", video_path=str(vid), frames=[("accepted", "a.png")])
    calls = []
    monkeypatch.setattr(r, "_schedule_poster_extract", lambda v, d: calls.append(("ffmpeg", v)))
    monkeypatch.setattr(r, "_schedule_thumb", lambda s, d: calls.append(("downscale", s)))
    r.resolve_poster("framed")
    r.resolve_poster("vid")
    assert [c[0] for c in calls] == ["downscale", "ffmpeg"]


def test_resolve_poster_none_when_no_frames_and_no_video(tmp_path):
    r = AssetResolver(str(tmp_path))
    _make_job(str(tmp_path), "j")
    assert r.resolve_poster("j") is None


def test_ffmpeg_resolver_accepts_callable_and_survives_raising(tmp_path):
    r = AssetResolver(str(tmp_path), ffmpeg_exe=lambda: "C:/x/ffmpeg.exe")
    assert r._resolve_ffmpeg() == "C:/x/ffmpeg.exe"

    def boom():
        raise RuntimeError("no config yet")
    r2 = AssetResolver(str(tmp_path), ffmpeg_exe=boom)
    assert r2._resolve_ffmpeg() == ""          # must not propagate
    assert AssetResolver(str(tmp_path))._resolve_ffmpeg() == ""


def test_extract_poster_refuses_without_ffmpeg_or_video(tmp_path):
    dst = str(tmp_path / "p.jpg")
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    assert assets._extract_poster(str(vid), dst, "") is False
    assert assets._extract_poster(str(vid), dst, str(tmp_path / "nope.exe")) is False
    assert assets._extract_poster(str(tmp_path / "nope.mp4"), dst, "ffmpeg.exe") is False


def test_probe_duration_returns_zero_without_ffprobe(tmp_path):
    assert assets._probe_duration(str(tmp_path / "v.mp4"), "") == 0.0
    assert assets._probe_duration(str(tmp_path / "v.mp4"), str(tmp_path / "ffmpeg.exe")) == 0.0


def test_poster_cached_at_job_root_not_under_frames(tmp_path):
    """frames/ is owned by slide detection and cleaned between runs."""
    r = AssetResolver(str(tmp_path))
    _make_job(str(tmp_path), "j")
    p = r.poster_path("j")
    assert os.path.dirname(p) == os.path.join(str(tmp_path), "jobs", "j")
    assert "frames" not in os.path.relpath(p, str(tmp_path)).split(os.sep)


def test_poster_host_constant_matches_url_builder():
    assert poster_url("x").startswith("lpasset://" + POSTER_HOST + "/")
