"""Focused tests for Phase 9 Feature Group 2: paste link / yt-dlp import.

Uses the injectable ``MediaFetcher`` with a fake yt-dlp factory so no
public internet is required.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.services import media_fetch  # noqa: E402


# --------------------------------------------------------------------------- #
# Fake yt-dlp
# --------------------------------------------------------------------------- #
class _FakeYDL:
    """Mimics yt_dlp.YoutubeDL for the injectable factory."""

    def __init__(self, opts, info=None, fail=None, cancel_from=None):
        self.opts = opts
        self._info = info or {}
        self._fail = fail
        self._cancel_from = cancel_from
        self._extract_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        self._extract_calls += 1
        if self._fail:
            raise self._fail
        if self._cancel_from is not None and self._extract_calls >= self._cancel_from:
            raise media_fetch.MediaFetchCancelled()
        if download:
            # Simulate writing a file via the progress hook.
            outtmpl = self.opts["outtmpl"]
            dest = Path(outtmpl.replace("%(ext)s", "mp4"))
            dest.write_bytes(b"fake-video")
            for hook in self.opts.get("progress_hooks", []):
                hook({
                    "status": "finished",
                    "filename": str(dest),
                    "downloaded_bytes": 100,
                    "total_bytes": 100,
                })
            return {"_filename": str(dest), "requested_downloads": [{"filepath": str(dest)}]}
        return self._info


def _make_fetcher(info=None, fail=None, cancel_from=None):
    return media_fetch.MediaFetcher(
        ydl_factory=lambda opts: _FakeYDL(opts, info=info, fail=fail,
                                          cancel_from=cancel_from))


# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #
def test_looks_like_url_rejects_non_http():
    assert media_fetch.looks_like_url("not a url") is False
    assert media_fetch.looks_like_url("ftp://example.com/video") is False
    assert media_fetch.looks_like_url("") is False
    assert media_fetch.looks_like_url(None) is False


def test_looks_like_url_accepts_http():
    assert media_fetch.looks_like_url("https://example.com/video") is True
    assert media_fetch.looks_like_url("http://example.com/video") is True


# --------------------------------------------------------------------------- #
# Probe
# --------------------------------------------------------------------------- #
def test_probe_returns_metadata():
    fetcher = _make_fetcher(info={
        "title": "Lecture 1",
        "duration": 3600,
        "uploader": "Prof",
        "extractor_key": "youtube",
        "is_live": False,
        "webpage_url": "https://example.com/video",
    })
    info = fetcher.probe("https://example.com/video")
    assert "ok" not in info  # probe() sets no ok; the sidecar adds it
    assert info["title"] == "Lecture 1"
    assert info["duration"] == 3600
    assert info["uploader"] == "Prof"


def test_probe_rejects_invalid_url():
    fetcher = _make_fetcher()
    with pytest.raises(media_fetch.MediaFetchError):
        fetcher.probe("not a url")


def test_probe_surfaces_friendly_error():
    fetcher = _make_fetcher(fail=RuntimeError("ERROR: This video is private"))
    with pytest.raises(media_fetch.MediaFetchError) as exc:
        fetcher.probe("https://example.com/private")
    assert "private" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def test_download_writes_file_and_reports_progress(tmp_path):
    dest = str(tmp_path)
    progress = []
    fetcher = _make_fetcher()
    path = fetcher.download(
        "https://example.com/video", dest,
        progress_cb=lambda p: progress.append(p))
    assert Path(path).exists()
    assert progress and progress[-1]["status"] == "finished"


def test_download_cancelled_raises(tmp_path):
    fetcher = _make_fetcher(cancel_from=1)
    with pytest.raises(media_fetch.MediaFetchCancelled):
        fetcher.download("https://example.com/video", str(tmp_path))
    # The .part / partial files should be cleaned by the caller; the fake
    # writes nothing on cancel, so nothing to assert beyond the exception.


def test_download_error_raises_friendly(tmp_path):
    fetcher = _make_fetcher(fail=RuntimeError("ERROR: Unsupported URL"))
    with pytest.raises(media_fetch.MediaFetchError) as exc:
        fetcher.download("https://example.com/nope", str(tmp_path))
    assert "recognised" in str(exc.value).lower()


def test_download_invalid_url(tmp_path):
    fetcher = _make_fetcher()
    with pytest.raises(media_fetch.MediaFetchError):
        fetcher.download("bad url", str(tmp_path))