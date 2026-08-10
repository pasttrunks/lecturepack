"""URL importer (lecturepack/services/media_fetch.py).

Every test drives an injected fake yt-dlp -- NO network access, so the suite
stays offline and deterministic.
"""

from __future__ import annotations

import os

import pytest

from lecturepack.services import media_fetch as mf
from lecturepack.services.media_fetch import (
    MediaFetchCancelled,
    MediaFetcher,
    MediaFetchError,
    looks_like_url,
    safe_filename,
)


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: a context manager with extract_info."""

    def __init__(self, opts, info=None, raises=None, writes=None):
        self.opts = opts
        self._info = info if info is not None else {"title": "T", "duration": 10}
        self._raises = raises
        self._writes = writes or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        if self._raises is not None:
            raise self._raises
        if download:
            for name, pct in self._writes:
                path = os.path.join(os.path.dirname(self.opts["outtmpl"]), name)
                with open(path, "wb") as fh:
                    fh.write(b"video-bytes")
                for h in self.opts.get("progress_hooks", []):
                    h({"status": "downloading", "downloaded_bytes": pct,
                       "total_bytes": 100, "speed": 1024.0, "eta": 3})
                for h in self.opts.get("progress_hooks", []):
                    h({"status": "finished", "filename": path,
                       "downloaded_bytes": 100, "total_bytes": 100})
        return self._info


def factory(**kw):
    return lambda opts: FakeYDL(opts, **kw)


# ------------------------------------------------------------------ validation

@pytest.mark.parametrize("url", [
    "https://example.com/watch?v=abc",
    "http://example.com/v/1",
    "  https://example.com/x  ",
])
def test_looks_like_url_accepts_http(url):
    assert looks_like_url(url)


@pytest.mark.parametrize("bad", [
    "", None, 42, "not a url", "example.com/x", "ftp://example.com/x",
    "file:///C:/secret.txt", "javascript:alert(1)", "data:text/html,x",
    "https://", "lpasset://poster/x/poster",
])
def test_looks_like_url_rejects_everything_else(bad):
    assert not looks_like_url(bad)


def test_probe_and_download_refuse_non_http_before_touching_ydl():
    called = []
    f = MediaFetcher(ydl_factory=lambda opts: called.append(opts))
    for bad in ("file:///C:/x.mp4", "not a url"):
        with pytest.raises(MediaFetchError):
            f.probe(bad)
        with pytest.raises(MediaFetchError):
            f.download(bad, "out")
    assert called == []          # never constructed a downloader


# ------------------------------------------------------------------- filenames

@pytest.mark.parametrize("title,expected", [
    ("Lecture 4: Egypt/Archaeology", "Lecture 4_ Egypt_Archaeology"),
    ("a\\b<c>d|e?f*g", "a_b_c_d_e_f_g"),
    ("  spaced   out  ", "spaced out"),
    ("", "lecture"),
    (None, "lecture"),
    ("...", "lecture"),
    ("trailing dots...", "trailing dots"),
])
def test_safe_filename(title, expected):
    assert safe_filename(title) == expected


def test_safe_filename_truncates_and_strips_control_chars():
    out = safe_filename("x" * 400)
    assert len(out) <= 120
    assert "\x00" not in safe_filename("a\x00b\x1fc")


# ----------------------------------------------------------------------- probe

def test_probe_returns_normalised_metadata():
    info = {"title": "Lec 1", "duration": 3600.7, "uploader": "Prof",
            "extractor_key": "Generic", "is_live": False,
            "webpage_url": "https://example.com/w"}
    got = MediaFetcher(ydl_factory=factory(info=info)).probe("https://example.com/w")
    assert got == {"title": "Lec 1", "duration": 3600, "uploader": "Prof",
                   "extractor": "Generic", "is_live": False,
                   "webpage_url": "https://example.com/w"}


def test_youtube_probe_does_not_force_a_player_client():
    """This test used to require player_client=["android"].

    That override predates yt-dlp's EJS system. YouTube now presents
    JavaScript challenges that yt-dlp solves with a real JS runtime, and
    pinning the Android client bypasses that path entirely -- which would
    defeat the Deno runtime LecturePack now bundles. Letting yt-dlp pick its
    own clients is the supported configuration.
    """
    captured = {}

    def make_ydl(opts):
        captured.update(opts)
        return FakeYDL(opts, info={"title": "AP Microeconomics"})

    MediaFetcher(ydl_factory=make_ydl).probe(
        "https://www.youtube.com/watch?v=2xK_bL_GqZs&t=1s"
    )

    youtube_args = (captured.get("extractor_args") or {}).get("youtube") or {}
    assert "player_client" not in youtube_args


def test_probe_does_not_download():
    holder = {}

    def fac(opts):
        holder["opts"] = opts
        return FakeYDL(opts)
    MediaFetcher(ydl_factory=fac).probe("https://example.com/x")
    assert holder["opts"]["skip_download"] is True
    assert holder["opts"]["noplaylist"] is True


def test_probe_handles_unknown_duration():
    got = MediaFetcher(ydl_factory=factory(info={"title": "x"})).probe("https://e.com/x")
    assert got["duration"] == 0


def test_probe_takes_first_entry_of_a_playlist():
    info = {"_type": "playlist", "entries": [
        {"title": "First", "duration": 5}, {"title": "Second"}]}
    got = MediaFetcher(ydl_factory=factory(info=info)).probe("https://e.com/list")
    assert got["title"] == "First"


def test_probe_rejects_empty_playlist_and_non_dict():
    with pytest.raises(MediaFetchError):
        MediaFetcher(ydl_factory=factory(info={"_type": "playlist", "entries": []})).probe("https://e.com/l")

    class NoneYDL(FakeYDL):
        def extract_info(self, url, download=False):
            return None            # extractor returned nothing usable
    with pytest.raises(MediaFetchError):
        MediaFetcher(ydl_factory=lambda o: NoneYDL(o)).probe("https://e.com/l")


def test_probe_reports_live_streams():
    got = MediaFetcher(ydl_factory=factory(info={"title": "x", "is_live": True})).probe("https://e.com/x")
    assert got["is_live"] is True


# -------------------------------------------------------------------- download

def test_download_returns_path_and_reports_progress(tmp_path):
    seen = []
    f = MediaFetcher(ydl_factory=factory(writes=[("out.mp4", 50)]))
    path = f.download("https://e.com/x", str(tmp_path), progress_cb=seen.append,
                      title="My Lecture")
    assert os.path.isfile(path)
    assert os.path.basename(path) == "out.mp4"
    assert [s["status"] for s in seen] == ["downloading", "finished"]
    assert seen[0]["pct"] == 50 and seen[0]["total"] == 100


def test_download_uses_safe_title_in_output_template(tmp_path):
    holder = {}

    def fac(opts):
        holder["opts"] = opts
        return FakeYDL(opts, writes=[("out.mp4", 100)])
    MediaFetcher(ydl_factory=fac).download(
        "https://e.com/x", str(tmp_path), title="Lec 1: A/B")
    assert "Lec 1_ A_B" in holder["opts"]["outtmpl"]
    assert os.path.dirname(holder["opts"]["outtmpl"]) == str(tmp_path)


def test_download_creates_dest_dir(tmp_path):
    dest = tmp_path / "nested" / "dir"
    f = MediaFetcher(ydl_factory=factory(writes=[("v.mp4", 100)]))
    f.download("https://e.com/x", str(dest))
    assert dest.is_dir()


def test_download_cancel_raises_cancelled(tmp_path):
    f = MediaFetcher(ydl_factory=factory(writes=[("v.mp4", 10)]))
    with pytest.raises(MediaFetchCancelled):
        f.download("https://e.com/x", str(tmp_path), cancel_check=lambda: True)


def test_progress_callback_errors_never_kill_the_transfer(tmp_path):
    def boom(_):
        raise RuntimeError("ui exploded")
    f = MediaFetcher(ydl_factory=factory(writes=[("v.mp4", 100)]))
    assert os.path.isfile(f.download("https://e.com/x", str(tmp_path), progress_cb=boom))


def test_cancel_check_errors_are_ignored(tmp_path):
    def boom():
        raise RuntimeError("flaky")
    f = MediaFetcher(ydl_factory=factory(writes=[("v.mp4", 100)]))
    assert os.path.isfile(f.download("https://e.com/x", str(tmp_path), cancel_check=boom))


def test_download_falls_back_to_newest_file_when_info_path_missing(tmp_path):
    """yt-dlp can report a pre-merge name; the newest real file is the answer."""
    class NoFilenameYDL(FakeYDL):
        def extract_info(self, url, download=False):
            path = os.path.join(str(tmp_path), "actual.mp4")
            with open(path, "wb") as fh:
                fh.write(b"x")
            for h in self.opts.get("progress_hooks", []):
                h({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2})
            return {"title": "t"}          # no filename anywhere
    f = MediaFetcher(ydl_factory=lambda opts: NoFilenameYDL(opts))
    assert os.path.basename(f.download("https://e.com/x", str(tmp_path))) == "actual.mp4"


def test_download_raises_when_nothing_written(tmp_path):
    f = MediaFetcher(ydl_factory=factory(writes=[]))
    with pytest.raises(MediaFetchError):
        f.download("https://e.com/x", str(tmp_path))


def test_newest_media_ignores_partial_files(tmp_path):
    (tmp_path / "a.part").write_bytes(b"x")
    (tmp_path / "b.ytdl").write_bytes(b"x")
    assert mf._newest_media(str(tmp_path)) == ""
    (tmp_path / "c.mp4").write_bytes(b"x")
    assert os.path.basename(mf._newest_media(str(tmp_path))) == "c.mp4"


# ---------------------------------------------------------------- error text

@pytest.mark.parametrize("raw,needle", [
    ("ERROR: Private video. Sign in", "private"),
    ("Video unavailable", "unavailable"),
    ("Unsupported URL: https://x", "recognised"),
    ("This content is DRM protected", "DRM"),
    ("[Errno 11001] getaddrinfo failed: could not resolve host", "connection"),
    ("Video blocked on copyright grounds", "blocked"),
])
def test_friendly_error_messages(raw, needle):
    assert needle.lower() in mf._friendly(Exception(raw)).lower()


def test_friendly_strips_error_prefix_and_caps_length():
    assert not mf._friendly(Exception("ERROR: weird thing")).startswith("ERROR:")
    assert len(mf._friendly(Exception("z" * 900))) <= 300


def test_friendly_never_returns_empty():
    assert mf._friendly(Exception("")) != ""


def test_probe_wraps_ydl_exception_as_fetch_error():
    f = MediaFetcher(ydl_factory=factory(raises=RuntimeError("ERROR: Video unavailable")))
    with pytest.raises(MediaFetchError) as e:
        f.probe("https://e.com/x")
    assert "unavailable" in str(e.value)


def test_download_wraps_ydl_exception_as_fetch_error(tmp_path):
    f = MediaFetcher(ydl_factory=factory(raises=RuntimeError("boom")))
    with pytest.raises(MediaFetchError):
        f.download("https://e.com/x", str(tmp_path))


def test_download_maps_cancel_shaped_errors_to_cancelled(tmp_path):
    f = MediaFetcher(ydl_factory=factory(raises=RuntimeError("Download cancelled")))
    with pytest.raises(MediaFetchCancelled):
        f.download("https://e.com/x", str(tmp_path))


# -------------------------------------------------------------- availability

def test_is_available_and_version_are_consistent():
    if mf.is_available():
        assert mf.version() != ""
    else:
        assert mf.version() == ""


def test_default_format_prefers_muxed_mp4_to_avoid_merge_step():
    assert mf.DEFAULT_FORMAT.startswith("best[ext=mp4]")


def test_no_drm_or_cookie_options_are_ever_set(tmp_path):
    """Guard: the fetcher must not acquire credentials or decryption options."""
    holder = {}

    def fac(opts):
        holder["opts"] = opts
        return FakeYDL(opts, writes=[("v.mp4", 100)])
    MediaFetcher(ydl_factory=fac).download("https://e.com/x", str(tmp_path))
    keys = set(holder["opts"])
    for forbidden in ("cookiefile", "cookiesfrombrowser", "username",
                      "password", "videopassword", "allow_unplayable_formats"):
        assert forbidden not in keys
