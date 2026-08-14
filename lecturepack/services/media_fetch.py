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
import shutil
import subprocess
import sys
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


# --------------------------------------------------------------------------- #
# Bundled runtime discovery.
#
# Modern yt-dlp cannot fully extract YouTube without an external JavaScript
# runtime: YouTube presents JS challenges that yt-dlp solves through its EJS
# ("External JS Scripts") system, which needs both the `yt_dlp_ejs` package and
# a real JS runtime process. Deno is upstream's default and recommended
# runtime. LecturePack ships both so a customer never has to install Python,
# Node, Deno or FFmpeg themselves.
# --------------------------------------------------------------------------- #

def _runtime_roots() -> list[str]:
    """Directories that may hold the bundled bin/ folder.

    Mirrors video_reader.detect_ffmpeg_path: next to the executable when
    frozen, the project root in a dev checkout.
    """
    override = os.environ.get("LECTUREPACK_RUNTIME_ROOT", "").strip()
    if override:
        # An explicit runtime root is authoritative. Falling through to the
        # dev checkout would let a packaged build silently pick up binaries
        # from somewhere other than its own bundle.
        return [override]
    roots: list[str] = []
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(sys.executable))
        # PyInstaller onedir keeps payload under _internal/.
        roots.append(os.path.join(os.path.dirname(sys.executable), "_internal"))
    else:
        roots.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return [r for r in roots if r]


def _bundled(*parts: str) -> str:
    for root in _runtime_roots():
        candidate = os.path.join(root, *parts)
        if os.path.isfile(candidate):
            return candidate
    return ""


def ffmpeg_location() -> str:
    """Directory holding the bundled ffmpeg/ffprobe, for yt-dlp.

    yt-dlp takes a DIRECTORY here and finds both binaries inside it. Handing it
    our bundle explicitly means merges and remuxes never depend on the customer
    having FFmpeg on PATH.
    """
    ffmpeg = _bundled("bin", "ffmpeg.exe")
    if ffmpeg:
        return os.path.dirname(ffmpeg)
    system = shutil.which("ffmpeg")
    return os.path.dirname(system) if system else ""


def js_runtime_path() -> str:
    """Path to the bundled Deno executable, or '' when it is not present."""
    name = "deno.exe" if os.name == "nt" else "deno"
    return _bundled("bin", name)


def js_runtime_version() -> str:
    """Version string of the bundled JS runtime; '' when it cannot run."""
    deno = js_runtime_path()
    if not deno:
        return ""
    try:
        completed = subprocess.run(
            [deno, "--version"],
            capture_output=True, text=True, timeout=20,
            shell=False, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    first = (completed.stdout or "").strip().splitlines()
    return first[0].strip() if first else ""


def ejs_available() -> bool:
    """True when the yt-dlp EJS support package can be imported."""
    try:
        import yt_dlp_ejs  # noqa: F401
    except Exception:
        return False
    return True


def ejs_version() -> str:
    """Installed yt-dlp-ejs version.

    The package does not export __version__ at module level, so read the
    distribution metadata and fall back to its private _version module (which
    is what PyInstaller ends up freezing).
    """
    try:
        import importlib.metadata as metadata
        return str(metadata.version("yt-dlp-ejs"))
    except Exception:
        pass
    try:
        from yt_dlp_ejs import _version
        return str(getattr(_version, "__version__", "") or "")
    except Exception:
        return ""


def youtube_support() -> dict:
    """Report the distinct capabilities that URL import depends on.

    Deliberately four separate answers rather than one boolean: "yt-dlp
    imports" is NOT the same as "YouTube works". Diagnostics that conflate
    them hide exactly the failure this reports.
    """
    runtime = js_runtime_version()
    return {
        "yt_dlp": is_available(),
        "yt_dlp_version": version(),
        "ejs": ejs_available(),
        "ejs_version": ejs_version(),
        "js_runtime": bool(runtime),
        "js_runtime_version": runtime,
        "js_runtime_path": js_runtime_path(),
        "ffmpeg_location": ffmpeg_location(),
    }


def _js_runtime_env() -> None:
    """Make the bundled Deno discoverable by yt-dlp's EJS runtime lookup.

    yt-dlp spawns the runtime by name, resolved through PATH. Prepending our
    own bin/ is idempotent and only ever adds a directory we ship.
    """
    deno = js_runtime_path()
    if not deno:
        return
    bin_dir = os.path.dirname(deno)
    current = os.environ.get("PATH", "")
    entries = [part for part in current.split(os.pathsep) if part]
    if any(os.path.normcase(part) == os.path.normcase(bin_dir) for part in entries):
        return
    os.environ["PATH"] = os.pathsep.join([bin_dir, *entries]) if entries else bin_dir


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
        # Ensure the bundled Deno is on PATH before yt-dlp looks for a runtime.
        _js_runtime_env()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,       # a lecture link, not someone's whole channel
            "restrictfilenames": False,
            # Never reach out for extra components at runtime on a customer
            # machine: everything EJS needs is bundled in the installer.
            "remote_components": [],
        }
        # Point yt-dlp at LecturePack's own FFmpeg so merges/remuxes work on a
        # machine with no system FFmpeg.
        location = ffmpeg_location()
        if location:
            opts["ffmpeg_location"] = location
        # No forced player_client. The Android client override that used to
        # live here predates EJS; it bypasses the JS-challenge path that
        # YouTube now requires, so it would defeat the bundled runtime.
        return opts

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
            # Take the captions the publisher already wrote. Transcribing a
            # video that ships with a transcript is the slowest stage of the
            # pipeline redoing finished work; see services/source_captions.py.
            # Publisher-written subtitles are preferred, machine-generated ones
            # are accepted as a second choice, and NEITHER is required -- a
            # video without captions still transcribes locally as before.
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB", "en-orig"],
            "subtitlesformat": "vtt/srt/best",
            # A caption failure must never cost the download itself.
            "ignoreerrors": "only_download",
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

        # A TRANSLATED track is not a transcript of this lecture. YouTube will
        # happily serve English subtitles for a German talk, and adopting those
        # would give a "transcript" that does not match a single spoken word --
        # breaking slide alignment and making Study cite lines the lecturer
        # never said. Captions are only safe when they are in the video's own
        # language, so anything else is discarded and whisper transcribes the
        # audio as before.
        _discard_translated_captions(dest_dir, info)

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


SIDECAR_SUFFIXES = (".vtt", ".srt", ".ass", ".ssa", ".lrc", ".json3", ".srv1",
                    ".srv2", ".srv3", ".ttml", ".description", ".info.json")
CAPTION_SUFFIXES = (".vtt", ".srt")


def _discard_translated_captions(dest_dir: str, info) -> None:
    """Remove caption files that are a TRANSLATION rather than a transcript.

    Captions are time-synced text of what is actually said, in the video's own
    language. Subtitles may be a translation of it. Only the former is a
    transcript of this lecture: an English track over German audio matches no
    spoken word, so slide alignment and Study citations would both be wrong.

    The language is only trusted when the extractor states it. When it says
    nothing, the captions are kept -- English is requested, English is what the
    pipeline expects, and the usability check downstream is the next guard.
    """
    language = ""
    if isinstance(info, dict):
        language = str(info.get("language") or "").strip().lower()
    if not language or language.split("-")[0] == "en":
        return
    try:
        for name in os.listdir(dest_dir):
            if name.lower().endswith(CAPTION_SUFFIXES):
                try:
                    os.remove(os.path.join(dest_dir, name))
                except OSError:
                    pass
    except OSError:
        pass


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
        # Caption sidecars are written AFTER the media, so "newest file wins"
        # would hand back a .vtt as though it were the lecture.
        if p.lower().endswith(SIDECAR_SUFFIXES):
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
