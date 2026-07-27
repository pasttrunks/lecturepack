"""Central asset resolver for job media (slide frames).

The web UI cannot load raw ``file://`` paths reliably: Windows backslashes,
spaces/Unicode, packaged-vs-source path differences and WebEngine's local
content restrictions all conspire to leave slide thumbnails blank. Instead we
expose a single, security-checked custom URL scheme:

    lpasset://job/<job_id>/<image_filename>

Every slide image the UI needs is addressed through this one resolver, which:

  * verifies the file belongs to the addressed job (no arbitrary FS access),
  * rejects directory traversal (``..``, absolute paths, separators),
  * works identically in source and packaged (frozen) builds — it only ever
    joins ``data_dir / jobs / <job_id> / frames`` on the Python side, so spaces
    and Unicode in the data directory are handled by the filesystem, never by
    the browser,
  * returns correct MIME types.

The pure-Python :class:`AssetResolver` carries all of that logic and is fully
unit-testable without Qt. The thin :class:`AssetSchemeHandler` wraps it for
QtWebEngine.
"""

from __future__ import annotations

import os
import re
import threading
import uuid
from urllib.parse import quote, unquote

# Poster/thumb generation is reachable from MORE THAN ONE AssetResolver: main.py
# owns one (wired to jobs_changed -> prewarm_posters) and the engine adapter
# kicks one on import. Each instance's own _pending set only dedups calls on
# THAT instance, so the same destination could be generated twice at once. This
# module-level guard is shared by every instance in the process.
_INFLIGHT: set[str] = set()
_INFLIGHT_LOCK = threading.Lock()


def _claim(dst: str) -> bool:
    """True if this caller now owns generating *dst*; False if someone else does."""
    with _INFLIGHT_LOCK:
        if dst in _INFLIGHT:
            return False
        _INFLIGHT.add(dst)
        return True


def _release(dst: str) -> None:
    with _INFLIGHT_LOCK:
        _INFLIGHT.discard(dst)


def _tmp_for(dst: str) -> str:
    """A UNIQUE temp path beside *dst*.

    These were deterministic (dst + '.tmp'), so two concurrent generators wrote
    the same temp file and could tear it -- one truncating while the other was
    mid-write, then both os.replace()ing. Unique names make each write private,
    so the replace is atomic and the loser is simply discarded.
    """
    return f"{dst}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}{os.path.splitext(dst)[1]}"

SCHEME = "lpasset"
SCHEME_BYTES = b"lpasset"
HOST = "job"
THUMB_HOST = "thumb"
POSTER_HOST = "poster"

# Job-card poster frames. Cached at the job root (NOT under frames/, which is
# owned by slide detection and gets cleaned between runs).
POSTER_NAME = "poster"
POSTER_MAX = 480          # cards render at 118px tall; 480 covers 3x DPI
POSTER_SEEK_FRACTION = 0.10   # 10% in — past titles/black leader, still early

# Downscaled thumbnail cache: longest side in px, dir schema version (bump to
# invalidate all cached thumbnails). Kept off the processing critical path —
# generated lazily on first request and cached to disk beside the frames.
THUMB_MAX = 320
THUMB_SCHEMA = "v1"
THUMB_QUALITY = 80

# job ids are UUIDs or validation slugs — never contain path separators.
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

# Sub-directories under a job's frames/ tree where slide images may live.
_FRAME_SUBDIRS = ("candidates", "accepted", "rejected", "")


def guess_mime(filename: str) -> str:
    return _MIME_BY_EXT.get(os.path.splitext(filename)[1].lower(),
                            "application/octet-stream")


def asset_url(job_id: str, filename: str) -> str:
    """Build the full-resolution ``lpasset://`` URL (main preview / decode)."""
    return f"{SCHEME}://{HOST}/{quote(str(job_id))}/{quote(str(filename))}"


def thumb_url(job_id: str, filename: str) -> str:
    """Build the thumbnail ``lpasset://`` URL (slide list/grid)."""
    return f"{SCHEME}://{THUMB_HOST}/{quote(str(job_id))}/{quote(str(filename))}"


def poster_url(job_id: str, version: str = "") -> str:
    """Build the job-card poster URL.

    ``version`` is an optional cache-buster the UI appends when it wants a
    re-fetch after a poster has been generated in the background.
    """
    # safe="" so a separator in job_id cannot inject extra path segments.
    # (resolve_poster refuses such ids anyway -- this is defence in depth.)
    url = f"{SCHEME}://{POSTER_HOST}/{quote(str(job_id), safe='')}/{POSTER_NAME}"
    return f"{url}?v={quote(str(version), safe='')}" if version else url


_THUMB_FMT = None  # cached (qt_format, mime, ext); resolved once at runtime


def _thumb_format():
    """Prefer WebP; fall back to JPEG if the WebP writer isn't available
    (e.g. the imageformats plugin wasn't bundled in a packaged build)."""
    global _THUMB_FMT
    if _THUMB_FMT is None:
        try:
            from PySide6.QtGui import QImageWriter
            fmts = {bytes(f).decode().lower()
                    for f in QImageWriter.supportedImageFormats()}
        except Exception:
            fmts = set()
        if "webp" in fmts:
            _THUMB_FMT = ("WEBP", "image/webp", ".webp")
        else:
            _THUMB_FMT = ("JPG", "image/jpeg", ".jpg")
    return _THUMB_FMT


class AssetResolver:
    """Resolves ``(job_id, filename)`` to an on-disk slide image, safely."""

    def __init__(self, data_dir: str, ffmpeg_exe=None):
        self.data_dir = data_dir
        # Callable or plain path to ffmpeg, used only for poster extraction when
        # a job has no slide frames yet. Injected so tests need no real binary.
        self._ffmpeg_exe = ffmpeg_exe
        self._pool = None            # lazy background thumbnail generator
        self._pending = set()        # dst paths currently being generated
        self._lock = threading.Lock()

    def _schedule_thumb(self, src: str, dst: str) -> None:
        """Generate a thumbnail off the main thread (deduped by dst path)."""
        with self._lock:
            if dst in self._pending:
                return
            self._pending.add(dst)
            if self._pool is None:
                from concurrent.futures import ThreadPoolExecutor
                self._pool = ThreadPoolExecutor(max_workers=2,
                                                thread_name_prefix="lp-thumb")

        def work():
            try:
                _make_thumb(src, dst)
            finally:
                with self._lock:
                    self._pending.discard(dst)
        self._pool.submit(work)

    def _job_frames_roots(self, job_id: str) -> list[str]:
        """Candidate frames/ directories for a job (live, then archived)."""
        roots = []
        for base in ("jobs", "archive"):
            roots.append(os.path.join(self.data_dir, base, job_id, "frames"))
        return roots

    def resolve_path(self, job_id: str, filename: str) -> str | None:
        """Return the validated absolute path for an asset, or None.

        Rejects unknown job-id shapes, path traversal and any file that does
        not resolve *inside* the addressed job's frames directory.
        """
        job_id = unquote(str(job_id))
        filename = unquote(str(filename))

        if not _JOB_ID_RE.match(job_id):
            return None
        # Only a bare filename is allowed — no separators, no traversal.
        if not filename or filename != os.path.basename(filename):
            return None
        if filename in (".", "..") or "\\" in filename or "/" in filename:
            return None

        for frames_root in self._job_frames_roots(job_id):
            if not os.path.isdir(frames_root):
                continue
            safe_root = os.path.realpath(frames_root)
            for sub in _FRAME_SUBDIRS:
                candidate = os.path.join(frames_root, sub, filename) if sub \
                    else os.path.join(frames_root, filename)
                if not os.path.isfile(candidate):
                    continue
                real = os.path.realpath(candidate)
                # Confirm the resolved file is still inside the job frames tree.
                if real == safe_root or real.startswith(safe_root + os.sep):
                    return real
        return None

    def resolve(self, job_id: str, filename: str) -> tuple[str, bytes] | None:
        """Return ``(mime, bytes)`` for an asset, or None if missing/invalid."""
        path = self.resolve_path(job_id, filename)
        if path is None:
            return None
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return None
        return guess_mime(filename), data

    def thumb_path(self, src_path: str) -> str:
        """Cache path for a source frame's thumbnail (inside frames/thumbs/<v>)."""
        d = os.path.dirname(src_path)
        while os.path.basename(d) != "frames" and d != os.path.dirname(d):
            d = os.path.dirname(d)
        _, _, ext = _thumb_format()
        return os.path.join(d, "thumbs", THUMB_SCHEMA,
                            os.path.basename(src_path) + ext)

    def resolve_thumb(self, job_id: str, filename: str) -> tuple[str, bytes] | None:
        """Return ``(mime, bytes)`` for a downscaled thumbnail.

        NON-BLOCKING: if a fresh cached thumbnail exists it is served; otherwise
        the full-resolution original is served immediately and the thumbnail is
        generated in a background thread for next time. This keeps the scheme
        handler (main thread) from stalling on 100+ decodes when a long job is
        first opened, and never starves the full-resolution preview request.
        """
        src = self.resolve_path(job_id, filename)
        if src is None:
            return None
        _, mime, _ = _thumb_format()
        dst = self.thumb_path(src)
        try:
            if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
                with open(dst, "rb") as fh:
                    return mime, fh.read()
        except OSError:
            pass
        # Not cached yet — generate in the background, serve full-res meanwhile.
        self._schedule_thumb(src, dst)
        try:
            with open(src, "rb") as fh:
                return guess_mime(filename), fh.read()
        except OSError:
            return None

    # ------------------------------------------------------------ posters

    def _job_root(self, job_id: str) -> str | None:
        """Validated job directory (live, then archived), or None."""
        if not _JOB_ID_RE.match(unquote(str(job_id))):
            return None
        job_id = unquote(str(job_id))
        for base in ("jobs", "archive"):
            root = os.path.join(self.data_dir, base, job_id)
            if os.path.isdir(root):
                return root
        return None

    def poster_path(self, job_id: str) -> str | None:
        root = self._job_root(job_id)
        if root is None:
            return None
        _, _, ext = _thumb_format()
        return os.path.join(root, POSTER_NAME + ext)

    def source_video(self, job_id: str) -> str | None:
        """The job's original video path from manifest.json, if it still exists."""
        root = self._job_root(job_id)
        if root is None:
            return None
        try:
            import json
            with open(os.path.join(root, "manifest.json"), encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError):
            return None
        src = (manifest.get("source") or {}).get("original_path") or ""
        return src if src and os.path.isfile(src) else None

    def _existing_frame(self, job_id: str) -> str | None:
        """Cheapest poster source: a slide image this job already produced."""
        root = self._job_root(job_id)
        if root is None:
            return None
        # accepted slides first (they are the meaningful ones), then candidates
        for sub in ("accepted", "candidates", ""):
            d = os.path.join(root, "frames", sub) if sub else os.path.join(root, "frames")
            if not os.path.isdir(d):
                continue
            try:
                names = sorted(n for n in os.listdir(d)
                               if os.path.splitext(n)[1].lower() in _MIME_BY_EXT)
            except OSError:
                continue
            if names:
                return os.path.join(d, names[0])
        return None

    def resolve_poster(self, job_id: str) -> tuple[str, bytes] | None:
        """Return ``(mime, bytes)`` for a job's card poster, or None.

        NON-BLOCKING, like :meth:`resolve_thumb`: a cached poster is served
        immediately; otherwise generation is scheduled on the background pool
        and None is returned so the UI keeps its placeholder icon for now. The
        card re-requests with a cache-buster once the job list next refreshes.
        """
        dst = self.poster_path(job_id)
        if dst is None:
            return None
        _, mime, _ = _thumb_format()
        if os.path.isfile(dst):
            try:
                with open(dst, "rb") as fh:
                    return mime, fh.read()
            except OSError:
                return None
        frame = self._existing_frame(job_id)
        if frame is not None:
            self._schedule_thumb(frame, dst)     # plain downscale, no ffmpeg
            return None
        video = self.source_video(job_id)
        if video is not None:
            self._schedule_poster_extract(video, dst)
        return None

    def _schedule_poster_extract(self, video: str, dst: str) -> None:
        with self._lock:
            if dst in self._pending:
                return
            self._pending.add(dst)
            if self._pool is None:
                from concurrent.futures import ThreadPoolExecutor
                self._pool = ThreadPoolExecutor(max_workers=2,
                                                thread_name_prefix="lp-thumb")

        def work():
            try:
                _extract_poster(video, dst, self._resolve_ffmpeg())
            finally:
                with self._lock:
                    self._pending.discard(dst)
        self._pool.submit(work)

    def _resolve_ffmpeg(self) -> str:
        f = self._ffmpeg_exe
        if callable(f):
            try:
                f = f()
            except Exception:
                return ""
        return f or ""

    def prewarm_posters(self, job_ids) -> list[str]:
        """Start generating any missing posters NOW, off the main thread.

        Called when the job list changes so a freshly imported lecture has its
        poster ready by the time its card paints, instead of showing the icon
        placeholder until the next refresh. Cached posters are skipped, so this
        is cheap to call on every list update. Returns the ids it scheduled.
        """
        scheduled = []
        for job_id in job_ids or ():
            dst = self.poster_path(job_id)
            if dst is None or os.path.isfile(dst):
                continue
            frame = self._existing_frame(job_id)
            if frame is not None:
                self._schedule_thumb(frame, dst)
                scheduled.append(job_id)
                continue
            video = self.source_video(job_id)
            if video is not None:
                self._schedule_poster_extract(video, dst)
                scheduled.append(job_id)
        return scheduled

    def make_poster_now(self, job_id: str, fast: bool = False) -> tuple[str, bytes] | None:
        """Synchronous generate+return — for tests/prewarming, not the handler.

        Guarded by the module-level in-flight set, not just this instance's
        _pending: more than one AssetResolver exists in the process (main.py owns
        one for prewarming, the engine adapter kicks one on import), and running
        two ffmpeg extractions over the same multi-hundred-MB video at once is
        pure waste during processing. If another caller already owns this
        destination we return whatever is on disk rather than racing it.
        """
        dst = self.poster_path(job_id)
        if dst is None:
            return None
        if not _claim(dst):
            return self._read_poster(dst)
        try:
            return self._make_poster_locked(job_id, dst, fast=fast)
        finally:
            _release(dst)

    def _read_poster(self, dst: str) -> tuple[str, bytes] | None:
        _, mime, _ = _thumb_format()
        try:
            if os.path.isfile(dst):
                with open(dst, "rb") as fh:
                    return mime, fh.read()
        except OSError:
            pass
        return None

    def _make_poster_locked(self, job_id: str, dst: str, fast: bool = False) -> tuple[str, bytes] | None:
        _, mime, _ = _thumb_format()
        frame = self._existing_frame(job_id)
        data = None
        if frame is not None:
            data = _make_thumb(frame, dst, POSTER_MAX)
        if data is None:
            video = self.source_video(job_id)
            # fast=True grabs the frame at t=0 instead of seeking to
            # POSTER_SEEK_FRACTION. Seeking into a multi-hundred-MB file takes
            # longer than the UI is willing to wait for a first thumbnail, and a
            # first frame is a perfectly good placeholder.
            extract = _extract_poster_at_start if fast else _extract_poster
            if video is not None and extract(video, dst, self._resolve_ffmpeg()):
                try:
                    with open(dst, "rb") as fh:
                        data = fh.read()
                except OSError:
                    data = None
        return (mime, data) if data is not None else None

    def make_thumb_now(self, job_id: str, filename: str) -> tuple[str, bytes] | None:
        """Synchronous generate+return — for tests/prewarming, not the handler."""
        src = self.resolve_path(job_id, filename)
        if src is None:
            return None
        _, mime, _ = _thumb_format()
        data = _make_thumb(src, self.thumb_path(src))
        return (mime, data) if data is not None else None


def _make_thumb(src: str, dst: str, max_px: int = THUMB_MAX) -> bytes | None:
    """Generate a downscaled thumbnail from ``src`` into ``dst`` (atomic) and
    return its bytes, or None on failure. Requires a running QApplication."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
    except Exception:
        return None
    img = QImage(src)
    if img.isNull():
        return None
    scaled = img.scaled(max_px, max_px,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    fmt, _, _ = _thumb_format()
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = _tmp_for(dst)
        if not scaled.save(tmp, fmt, THUMB_QUALITY):
            return None
        os.replace(tmp, dst)
        with open(dst, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _probe_duration(video: str, ffmpeg_exe: str) -> float:
    """Duration in seconds via ffprobe (sibling of ffmpeg), or 0.0 if unknown."""
    if not ffmpeg_exe:
        return 0.0
    d, name = os.path.dirname(ffmpeg_exe), os.path.basename(ffmpeg_exe)
    probe = os.path.join(d, name.replace("ffmpeg", "ffprobe", 1))
    if not os.path.isfile(probe):
        return 0.0
    try:
        import subprocess
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
        return max(0.0, float(out))
    except Exception:
        return 0.0


def _extract_poster(video: str, dst: str, ffmpeg_exe: str) -> bool:
    """Grab one frame ~10% into ``video`` and write it to ``dst`` atomically.

    Seeks before -i (input seeking) so long lectures cost ~constant time instead
    of decoding from the start. Returns True on success.
    """
    if not ffmpeg_exe or not os.path.isfile(ffmpeg_exe) or not os.path.isfile(video):
        return False
    seek = _probe_duration(video, ffmpeg_exe) * POSTER_SEEK_FRACTION
    tmp = _tmp_for(dst)
    try:
        import subprocess
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        cmd = [ffmpeg_exe, "-y", "-hide_banner", "-loglevel", "error"]
        if seek > 1.0:
            cmd += ["-ss", f"{seek:.2f}"]
        cmd += ["-i", video, "-frames:v", "1",
                "-vf", f"scale='min({POSTER_MAX},iw)':-2",
                "-f", "image2", tmp]
        rc = subprocess.run(cmd, capture_output=True, timeout=90,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if rc.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
            # A seek past the end of a short/variable-fps file yields no frame —
            # retry once from the very start before giving up.
            if seek > 1.0:
                return _extract_poster_at_start(video, dst, ffmpeg_exe)
            return False
        os.replace(tmp, dst)
        return True
    except Exception:
        return False
    finally:
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _extract_poster_at_start(video: str, dst: str, ffmpeg_exe: str) -> bool:
    tmp = _tmp_for(dst)
    try:
        import subprocess
        cmd = [ffmpeg_exe, "-y", "-hide_banner", "-loglevel", "error",
               "-i", video, "-frames:v", "1",
               "-vf", f"scale='min({POSTER_MAX},iw)':-2", "-f", "image2", tmp]
        rc = subprocess.run(cmd, capture_output=True, timeout=90,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if rc.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
            return False
        os.replace(tmp, dst)
        return True
    except Exception:
        return False
    finally:
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- Qt

def register_asset_scheme() -> None:
    """Register the ``lpasset`` scheme. MUST run before QApplication is built."""
    from PySide6.QtWebEngineCore import QWebEngineUrlScheme

    if QWebEngineUrlScheme.schemeByName(SCHEME_BYTES).name():
        return  # already registered (e.g. re-entry in tests)

    scheme = QWebEngineUrlScheme(SCHEME_BYTES)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    # LocalScheme puts lpasset in the same "local" bucket as file://, so the
    # file:// index page is allowed to load lpasset:// subresources;
    # LocalAccessAllowed permits that cross-scheme access; CorsEnabled lets the
    # response satisfy fetch/XHR too. (Mirrors Qt's own custom-scheme recipe.)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)


def install_asset_handler(profile, resolver: AssetResolver, logger=None):
    """Install the scheme handler on a QWebEngineProfile. Returns the handler
    (keep a reference alive for the profile's lifetime)."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtWebEngineCore import (
        QWebEngineUrlRequestJob,
        QWebEngineUrlSchemeHandler,
    )

    not_found = QWebEngineUrlRequestJob.Error.UrlNotFound

    class AssetSchemeHandler(QWebEngineUrlSchemeHandler):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._buffers = []  # keep reply devices alive until consumed

        def requestStarted(self, job):  # noqa: N802 (Qt override)
            url = job.requestUrl()
            # host selects full-res ("job"), thumbnail ("thumb") or card poster
            # ("poster"); path is "/<job_id>/<filename>"
            host = url.host()
            is_thumb = host == THUMB_HOST
            is_poster = host == POSTER_HOST
            parts = [p for p in url.path().split("/") if p]
            if len(parts) < 2:
                if logger:
                    logger("asset", f"bad asset url: {url.toString()}", "error")
                job.fail(not_found)
                return
            job_id, filename = parts[0], "/".join(parts[1:])
            if is_poster:
                result = resolver.resolve_poster(job_id)
            elif is_thumb:
                result = resolver.resolve_thumb(job_id, filename)
            else:
                result = resolver.resolve(job_id, filename)
            if result is None:
                # A missing poster is EXPECTED on first paint (generated in the
                # background) -- fail quietly so it doesn't spam the log.
                if logger and not is_poster:
                    logger("asset", f"asset missing: {job_id}/{filename}", "error")
                job.fail(not_found)
                return
            mime, data = result
            ba = QByteArray(data)
            buf = QBuffer(job)
            buf.setData(ba)
            buf.open(QIODevice.OpenModeFlag.ReadOnly)
            self._buffers.append(buf)
            job.reply(QByteArray(mime.encode("ascii")), buf)

    handler = AssetSchemeHandler(profile)
    profile.installUrlSchemeHandler(SCHEME_BYTES, handler)
    return handler
