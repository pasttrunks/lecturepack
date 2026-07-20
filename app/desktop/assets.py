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
from urllib.parse import quote, unquote

SCHEME = "lpasset"
SCHEME_BYTES = b"lpasset"
HOST = "job"
THUMB_HOST = "thumb"

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

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
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

    def make_thumb_now(self, job_id: str, filename: str) -> tuple[str, bytes] | None:
        """Synchronous generate+return — for tests/prewarming, not the handler."""
        src = self.resolve_path(job_id, filename)
        if src is None:
            return None
        _, mime, _ = _thumb_format()
        data = _make_thumb(src, self.thumb_path(src))
        return (mime, data) if data is not None else None


def _make_thumb(src: str, dst: str) -> bytes | None:
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
    scaled = img.scaled(THUMB_MAX, THUMB_MAX,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    fmt, _, _ = _thumb_format()
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".tmp"
        if not scaled.save(tmp, fmt, THUMB_QUALITY):
            return None
        os.replace(tmp, dst)
        with open(dst, "rb") as fh:
            return fh.read()
    except OSError:
        return None


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
            # host selects full-res ("job") vs thumbnail ("thumb");
            # path is "/<job_id>/<filename>"
            is_thumb = url.host() == THUMB_HOST
            parts = [p for p in url.path().split("/") if p]
            if len(parts) < 2:
                if logger:
                    logger("asset", f"bad asset url: {url.toString()}", "error")
                job.fail(not_found)
                return
            job_id, filename = parts[0], "/".join(parts[1:])
            result = (resolver.resolve_thumb(job_id, filename) if is_thumb
                      else resolver.resolve(job_id, filename))
            if result is None:
                if logger:
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
