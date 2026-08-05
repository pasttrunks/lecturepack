"""Fetch a lecture recording from a URL so it can be processed in-app.

Wraps yt-dlp. The point is to remove the app-switch: paste a link, get a local
file, hand it to the normal import path. Nothing here is specific to one site --
yt-dlp's extractor list decides what resolves.

Design notes:

* **yt-dlp is optional.** It is imported lazily and :func:`is_available` reports
  whether it is present, so a build without it degrades to "paste a link is
  unavailable" instead of failing at startup.
* **Injectable.** :class:`MediaFetcher` takes a ``ydl_factory`` so tests drive it
  with a fake; no network access in the test suite.
* **No DRM circumvention.** Options never enable any decryption path; a stream
  yt-dlp cannot read plainly simply fails.
* **Cooperative cancel.** A ``cancel_check`` callable is polled from the progress
  hook and raises inside yt-dlp to abort the transfer.
"""

from __future__ import annotations

import os
import time
import re
import unicodedata
from urllib.parse import urlparse

# Enough of a floor to reject nonsense early without pretending to know which
# hosts yt-dlp supports (that list changes constantly).
_ALLOWED_SCHEMES = ("http", "https")

# Keep container choice conservative: prefer an already-muxed mp4 so no
# post-processing/merge step is needed, then fall back to whatever exists.
DEFAULT_FORMAT = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"

_UNSAFE_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class MediaFetchError(RuntimeError):
    """A fetch failed for a reason worth showing the user."""


class MediaFetchCancelled(RuntimeError):
    """The user cancelled the download."""


def is_available() -> bool:
    """True when yt-dlp can be imported in this build."""
    try:
        import yt_dlp  # noqa: F401
    except Exception:
        return False
    return True


def version() -> str:
    try:
        import yt_dlp
        return str(yt_dlp.version.__version__)
    except Exception:
        return ""


def looks_like_url(text: str) -> bool:
    """Cheap client-style validation: an http(s) URL with a host."""
    if not text or not isinstance(text, str):
        return False
    try:
        parsed = urlparse(text.strip())
    except (ValueError, AttributeError):
        return False
    return parsed.scheme.lower() in _ALLOWED_SCHEMES and bool(parsed.netloc)


def safe_filename(title: str, fallback: str = "lecture") -> str:
    """A filesystem-safe base name derived from a media title.

    Titles routinely contain ``/``, ``:``, emoji and RTL marks; this keeps the
    readable part and drops anything that would break a Windows path.
    """
    title = unicodedata.normalize("NFKC", str(title or "")).strip()
    title = _UNSAFE_FS.sub("_", title)
    title = re.sub(r"\s+", " ", title).strip(" .")
    if not title:
        return fallback
    return title[:120].strip(" .") or fallback


class MediaFetcher:
    """Probe and download remote media via yt-dlp."""

    def __init__(self, ydl_factory=None, format_selector: str = DEFAULT_FORMAT):
        self._ydl_factory = ydl_factory
        self._format = format_selector

    # ---------------------------------------------------------------- internals

    def _make_ydl(self, opts):
        if self._ydl_factory is not None:
            return self._ydl_factory(opts)
        try:
            import yt_dlp
        except Exception as exc:                       # pragma: no cover - env
            raise MediaFetchError(
                "The link importer needs yt-dlp, which isn't available in this "
                "build."
            ) from exc
        return yt_dlp.YoutubeDL(opts)

    @staticmethod
    def _base_opts():
        return {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,       # a lecture link, not someone's whole channel
            "restrictfilenames": False,
            # Some public YouTube videos are hidden from yt-dlp's default web
            # client even though they remain playable. The Android client
            # exposes the combined MP4 formats that the default selector can
            # download without a separate merge step.
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                },
            },
        }

    # ------------------------------------------------------------------- probe

    def probe(self, url: str) -> dict:
        """Return metadata for ``url`` WITHOUT downloading the media.

        Keys: ``title``, ``duration`` (seconds, 0 if unknown), ``uploader``,
        ``extractor``, ``is_live``, ``webpage_url``.
        """
        if not looks_like_url(url):
            raise MediaFetchError("That doesn't look like a web link.")
        opts = self._base_opts()
        opts["skip_download"] = True
        try:
            with self._make_ydl(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except MediaFetchError:
            raise
        except Exception as exc:
            raise MediaFetchError(_friendly(exc)) from exc
        if not isinstance(info, dict):
            raise MediaFetchError("Nothing could be read from that link.")
        # A playlist URL still resolves with noplaylist; take the first entry so
        # the caller always describes a single recording.
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
            if not entries:
                raise MediaFetchError("That link has no playable video.")
            info = entries[0]
        duration = info.get("duration")
        return {
            "title": info.get("title") or "",
            "duration": int(duration) if isinstance(duration, (int, float)) else 0,
            "uploader": info.get("uploader") or info.get("channel") or "",
            "extractor": info.get("extractor_key") or info.get("extractor") or "",
            "is_live": bool(info.get("is_live")),
            "webpage_url": info.get("webpage_url") or url,
        }

    # ---------------------------------------------------------------- download

    def download(self, url: str, dest_dir: str, progress_cb=None,
                 cancel_check=None, title: str | None = None) -> str:
        """Download ``url`` into ``dest_dir`` and return the local file path.

        ``progress_cb(dict)`` receives ``{pct, downloaded, total, speed, eta,
        status}``. ``cancel_check()`` returning True aborts the transfer.
        """
        if not looks_like_url(url):
            raise MediaFetchError("That doesn't look like a web link.")
        os.makedirs(dest_dir, exist_ok=True)

        # Floor for the _newest_media fallback: only files written by THIS
        # download may be returned (BUG-17). 1s of slack absorbs clock/FS
        # timestamp granularity.
        started_at = time.time() - 1.0

        state = {"path": "", "cancelled": False}

        def hook(d):
            if cancel_check is not None:
                try:
                    if cancel_check():
                        state["cancelled"] = True
                        raise MediaFetchCancelled()
                except MediaFetchCancelled:
                    raise
                except Exception:
                    pass
            status = d.get("status") or ""
            if status == "finished":
                state["path"] = d.get("filename") or state["path"]
            if progress_cb is None:
                return
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = int(done * 100 / total) if total else 0
            try:
                progress_cb({
                    "status": status,
                    "pct": max(0, min(100, pct)),
                    "downloaded": int(done),
                    "total": int(total),
                    "speed": float(d.get("speed") or 0.0),
                    "eta": int(d.get("eta") or 0),
                })
            except Exception:
                pass            # a UI hiccup must not kill the transfer

        base = safe_filename(title) if title else "%(title).120B"
        opts = self._base_opts()
        opts.update({
            "format": self._format,
            "outtmpl": os.path.join(dest_dir, base + ".%(ext)s"),
            "progress_hooks": [hook],
            "retries": 3,
            "continuedl": True,
        })

        try:
            with self._make_ydl(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except MediaFetchCancelled:
            raise
        except MediaFetchError:
            raise
        except Exception as exc:
            if state["cancelled"] or _is_cancel(exc):
                raise MediaFetchCancelled() from exc
            raise MediaFetchError(_friendly(exc)) from exc

        path = state["path"] or _path_from_info(info)
        if not path or not os.path.isfile(path):
            # yt-dlp may report a pre-merge name; fall back to the newest file.
            path = _newest_media(dest_dir, not_before=started_at) or ""
        if not path or not os.path.isfile(path):
            raise MediaFetchError("The download finished but no file was written.")
        return path


def _path_from_info(info) -> str:
    if not isinstance(info, dict):
        return ""
    reqs = info.get("requested_downloads")
    if isinstance(reqs, list) and reqs and isinstance(reqs[0], dict):
        return reqs[0].get("filepath") or reqs[0].get("_filename") or ""
    return info.get("_filename") or ""


def _newest_media(dest_dir: str, not_before: float = 0.0) -> str:
    """Newest finished media in ``dest_dir``, ignoring anything older than
    ``not_before`` (a time.time() stamp taken when this download started).

    BUG-17: ``dest_dir`` is the SHARED ``<data_dir>/downloads`` folder, not a
    per-download temp dir. Without the timestamp floor, a download that failed
    to report its own filename fell back to "newest file here" and happily
    returned the user's PREVIOUS import -- which the caller then reported as
    ``ok: True`` and imported, creating a new job containing yesterday's
    lecture with no error shown anywhere. A failure must look like a failure.
    """
    try:
        entries = [os.path.join(dest_dir, n) for n in os.listdir(dest_dir)]
    except OSError:
        return ""
    files = []
    for p in entries:
        if not os.path.isfile(p) or p.endswith((".part", ".ytdl", ".tmp")):
            continue
        try:
            if os.path.getmtime(p) < not_before:
                continue          # predates this download; not ours
        except OSError:
            continue
        files.append(p)
    if not files:
        return ""
    return max(files, key=os.path.getmtime)


def _is_cancel(exc) -> bool:
    return isinstance(exc, MediaFetchCancelled) or \
        "cancel" in str(exc).lower()


def _friendly(exc) -> str:
    """Turn a yt-dlp error into something worth putting in the UI."""
    msg = str(exc).strip()
    msg = re.sub(r"^ERROR:\s*", "", msg)
    low = msg.lower()
    if "private" in low or "sign in" in low or "login" in low or "cookies" in low:
        return ("That video is private or needs a sign-in, so it can't be "
                "fetched.")
    if "unavailable" in low or "removed" in low or "not exist" in low:
        return "That video is unavailable or has been removed."
    if "unsupported url" in low or "no video" in low or "extractor" in low:
        return "That link isn't a recognised video page."
    if "drm" in low or "protected" in low:
        return "That video is DRM-protected and can't be fetched."
    if "network" in low or "timed out" in low or "connection" in low or \
            "resolve" in low:
        return "Couldn't reach that link — check your connection."
    if "copyright" in low or "blocked" in low or "geo" in low:
        return "That video is blocked in this region or on copyright grounds."
    return msg[:300] or "The link couldn't be fetched."
