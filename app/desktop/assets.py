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
from urllib.parse import quote, unquote

SCHEME = "lpasset"
SCHEME_BYTES = b"lpasset"
HOST = "job"

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
    """Build the ``lpasset://`` URL the UI puts in an <img src>."""
    return f"{SCHEME}://{HOST}/{quote(str(job_id))}/{quote(str(filename))}"


class AssetResolver:
    """Resolves ``(job_id, filename)`` to an on-disk slide image, safely."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

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
            # path is "/<job_id>/<filename>"
            parts = [p for p in url.path().split("/") if p]
            if len(parts) < 2:
                if logger:
                    logger("asset", f"bad asset url: {url.toString()}", "error")
                job.fail(not_found)
                return
            job_id, filename = parts[0], "/".join(parts[1:])
            result = resolver.resolve(job_id, filename)
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
