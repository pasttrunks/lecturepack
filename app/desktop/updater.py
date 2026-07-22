"""User-controlled in-app updater backed by GitHub Releases.

Flow (never a silent patcher):
    Check -> Explain -> Download -> Verify -> Ask permission -> Launch installer -> Exit

Design:
  * All decisions (version compare, channel filtering, asset selection, hashing)
    live in the pure, unit-tested ``update_service`` module.
  * Network + hashing run on QThreads; the UI is signalled on the main thread.
  * Prereleases are discoverable: we read the releases *list* (not
    /releases/latest) and pick the newest compatible release for the channel.
  * Downloads land in a per-user update cache as ``.partial`` and are only
    renamed + offered after SHA256 verification. An unverified file is deleted.
  * Installed builds launch the Inno installer *visibly* (/CLOSEAPPLICATIONS
    /NORESTART) and quit. Portable/source builds never self-replace — they
    point the user at the download page.

A test-only release feed can be injected via the ``LECTUREPACK_UPDATE_FEED``
env var (and ``LECTUREPACK_UPDATE_HOSTS`` to trust its asset host). These are
env-only — not reachable from the production UI — and when unset the production
GitHub host validation is fully in force.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

from PySide6.QtCore import QObject, QSettings, QThread, Signal

from . import update_service as us
from . import version

_AUTO_CHECK_INTERVAL = 24 * 3600  # seconds
_KEEP_INSTALLERS = 3


def _updates_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    d = os.path.join(base, version.APP_NAME, "Updates")
    os.makedirs(d, exist_ok=True)
    return d


def _emit(sig, payload):
    sig.emit(payload if isinstance(payload, str) else json.dumps(payload))


class _CheckWorker(QThread):
    found = Signal(dict)          # {release, version, portable}
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(self, feed_url, current, channel, skipped, portable, extra_hosts):
        super().__init__()
        self._feed = feed_url
        self._current = current
        self._channel = channel
        self._skipped = skipped
        self._portable = portable
        self._extra_hosts = extra_hosts

    def run(self):
        req = urllib.request.Request(self._feed, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"LecturePack/{self._current}",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        releases = data if isinstance(data, list) else [data]
        sel = us.select_release(releases, self._current, self._channel, self._skipped)
        if not sel:
            self.up_to_date.emit()
            return
        try:
            assets = us.select_asset(sel["release"], sel["version"],
                                     portable=self._portable, extra_hosts=self._extra_hosts)
        except ValueError as exc:
            # A newer version exists but its update assets are missing/invalid.
            self.failed.emit(f"update available but assets unavailable: {exc}")
            return
        self.found.emit({"release": sel["release"], "version": sel["version"],
                         "is_skipped": sel["is_skipped"], "assets_ok": True,
                         "installer": assets["installer"], "checksum": assets["checksum"]})


class _DownloadWorker(QThread):
    progress = Signal(float, int, int)   # pct, read, total
    done = Signal(str)                   # verified installer path
    failed = Signal(str)

    def __init__(self, installer, checksum, dest_name, extra_hosts):
        super().__init__()
        self._installer = installer
        self._checksum = checksum
        self._dest_name = dest_name
        self._extra_hosts = extra_hosts
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _fetch(self, url, dest_path=None):
        req = urllib.request.Request(url, headers={"User-Agent": f"LecturePack/{version.__version__}"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            if dest_path is None:
                return resp.read().decode("utf-8", errors="replace")
            total = int(resp.headers.get("Content-Length", 0) or 0)
            read = 0
            with open(dest_path, "wb") as fh:
                while True:
                    if self._cancel:
                        raise _Cancelled()
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    read += len(chunk)
                    self.progress.emit((read / total * 100.0) if total else 0.0, read, total)
            return read

    def run(self):
        updates = _updates_dir()
        partial = os.path.join(updates, self._dest_name + ".partial")
        final = os.path.join(updates, self._dest_name)
        # Clear any stale partial from a prior interrupted run.
        for p in (partial, final):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        try:
            # 1) checksum file (text)
            sums_text = self._fetch(us._asset_url(self._checksum))
            expected_from_sums = us.parse_sha256sums(sums_text, self._dest_name)
            expected_from_asset = us.digest_from_asset(self._installer)
            expected, agree = us.reconcile_digests(expected_from_sums, expected_from_asset)
            if not expected:
                raise ValueError("no SHA256 digest published for this installer")
            if not agree:
                raise ValueError("published checksum and asset digest disagree")
            # 2) installer -> .partial
            self._fetch(us._asset_url(self._installer), partial)
            if self._cancel:
                raise _Cancelled()
            # 3) verify BEFORE the file can be launched
            if not us.verify_file(partial, expected):
                raise ValueError("checksum mismatch — download rejected")
            # 4) atomic rename only after verification
            os.replace(partial, final)
            _prune_installers(updates, keep=_KEEP_INSTALLERS)
            self.done.emit(final)
        except _Cancelled:
            self._safe_remove(partial)
            self.failed.emit("__cancelled__")
        except Exception as exc:  # noqa: BLE001
            self._safe_remove(partial)   # never leave a partial/unverified file
            self._safe_remove(final)
            self.failed.emit(str(exc))

    @staticmethod
    def _safe_remove(path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


class _Cancelled(Exception):
    pass


def _prune_installers(directory, keep=_KEEP_INSTALLERS):
    """Keep only the most recent ``keep`` verified installers/zips."""
    try:
        files = [os.path.join(directory, n) for n in os.listdir(directory)
                 if n.lower().endswith((".exe", ".zip"))]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for old in files[keep:]:
            try:
                os.remove(old)
            except OSError:
                pass
    except OSError:
        pass


class Updater(QObject):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self._settings = QSettings(version.ORG_NAME, version.APP_NAME)
        self._pending: dict | None = None
        self._verified_path: str | None = None
        self._check_worker: _CheckWorker | None = None
        self._dl_worker: _DownloadWorker | None = None
        self._manual = False

    # -------------------------------------------------- settings/state
    def _bool(self, key, default=True):
        v = self._settings.value(key, default)
        return str(v).lower() in ("1", "true", "yes", "on") if not isinstance(v, bool) else v

    def channel(self) -> str:
        ch = str(self._settings.value("update_channel", "beta") or "beta").lower()
        return "stable" if ch == "stable" else "beta"

    def _skipped(self):
        return self._settings.value("skipped_version", "") or ""

    def is_portable(self) -> bool:
        """Installed = frozen with an Inno uninstaller beside the exe."""
        if not getattr(sys, "frozen", False):
            return True  # source/dev run — treat like portable (no self-install)
        exe_dir = os.path.dirname(sys.executable)
        return not os.path.exists(os.path.join(exe_dir, "unins000.exe"))

    def _feed_url(self):
        override = os.environ.get("LECTUREPACK_UPDATE_FEED")
        if override:
            return override
        return f"https://api.github.com/repos/{version.GITHUB_REPO}/releases?per_page=20"

    def _extra_hosts(self):
        raw = os.environ.get("LECTUREPACK_UPDATE_HOSTS", "")
        return {h.strip() for h in raw.split(",") if h.strip()}

    def _configured(self):
        return os.environ.get("LECTUREPACK_UPDATE_FEED") or (
            version.GITHUB_REPO and "/" in version.GITHUB_REPO)

    # -------------------------------------------------- startup
    def startup_check(self):
        # If we were just updated, show this version's overview once.
        last_seen = self._settings.value("last_seen_version", "")
        if last_seen and us.is_newer(version.__version__, str(last_seen)):
            notes = self._settings.value("last_release_notes", "")
            payload = json.loads(notes) if notes else {"version": version.__version__, "notes": []}
            payload["version"] = version.__version__
            payload["current"] = version.__version__
            _emit(self.backend.whatsnew, payload)
        self._settings.setValue("last_seen_version", version.__version__)
        if not self._configured() or not self._bool("auto_check_enabled", True):
            return
        # Auto-check at most once every 24h (manual bypasses this).
        last = self._settings.value("last_check_at", "")
        try:
            if last and (time.time() - float(last)) < _AUTO_CHECK_INTERVAL:
                return
        except (TypeError, ValueError):
            pass
        self.check(manual=False)

    # -------------------------------------------------- check
    def check(self, manual: bool = False):
        if not self._configured():
            if manual:
                _emit(self.backend.update_state, {"phase": "error", "stage": "check",
                      "message": "No update channel configured", "manual": True})
            return
        self._manual = manual
        self._settings.setValue("last_check_at", str(time.time()))
        if manual:
            _emit(self.backend.update_state, {"phase": "checking"})
        self._check_worker = _CheckWorker(
            self._feed_url(), version.__version__, self.channel(),
            self._skipped(), self.is_portable(), self._extra_hosts())
        self._check_worker.found.connect(self._on_found)
        self._check_worker.up_to_date.connect(self._on_up_to_date)
        self._check_worker.failed.connect(self._on_check_failed)
        self._check_worker.start()

    def _on_found(self, found: dict):
        self._pending = found
        self._verified_path = None
        overview = us.build_overview(found["release"], version.__version__,
                                     installer_asset=found["installer"],
                                     portable=self.is_portable())
        overview["is_skipped"] = found.get("is_skipped", False)
        overview["portable"] = self.is_portable()
        self._settings.setValue("last_release_notes", json.dumps(overview))
        self._settings.setValue("last_available_version", overview["available"])
        # An auto-check for a version the user chose to skip stays silent
        # (a manual check still surfaces it, flagged as skipped).
        if found.get("is_skipped") and not self._manual:
            return
        _emit(self.backend.update_available, overview)

    def _on_up_to_date(self):
        if self._manual:
            _emit(self.backend.update_state, {"phase": "uptodate", "message": "You’re up to date"})

    def _on_check_failed(self, msg: str):
        if self._manual:
            _emit(self.backend.update_state, {"phase": "error", "stage": "check",
                  "message": f"Unable to check right now: {msg}", "manual": True})

    # -------------------------------------------------- download + verify
    def start_download(self):
        if not self._pending:
            _emit(self.backend.update_error, "No update selected.")
            return
        if self.is_portable():
            # Portable/source builds never self-replace.
            _emit(self.backend.update_state, {"phase": "portable",
                  "url": (self._pending["release"].get("html_url") or "")})
            return
        installer = self._pending["installer"]
        checksum = self._pending["checksum"]
        dest_name = us.expected_asset_names(self._pending["version"], portable=False)[0]
        _emit(self.backend.update_state, {"phase": "downloading", "filename": dest_name, "pct": 0})
        self._dl_worker = _DownloadWorker(installer, checksum, dest_name, self._extra_hosts())
        self._dl_worker.progress.connect(self._on_progress)
        self._dl_worker.done.connect(self._on_verified)
        self._dl_worker.failed.connect(self._on_dl_failed)
        self._dl_worker.start()

    def _on_progress(self, pct, read, total):
        self.backend.update_progress.emit(float(pct))

    def _on_verified(self, path: str):
        self._verified_path = path
        _emit(self.backend.update_state, {"phase": "ready",
              "message": "Update verified and ready to install.",
              "path": os.path.basename(path)})
        self.backend.update_ready.emit()

    def _on_dl_failed(self, msg: str):
        self._verified_path = None
        if msg == "__cancelled__":
            _emit(self.backend.update_state, {"phase": "cancelled", "message": "Download cancelled."})
        else:
            _emit(self.backend.update_state, {"phase": "error", "stage": "download", "message": msg})
            self.backend.update_error.emit(msg)

    def cancel_download(self):
        if self._dl_worker is not None:
            self._dl_worker.cancel()

    # -------------------------------------------------- install handoff
    def install_downloaded(self):
        if not self._verified_path or not os.path.exists(self._verified_path):
            _emit(self.backend.update_state, {"phase": "error", "stage": "install",
                  "message": "No verified installer is ready. Download it first."})
            return
        if self._is_processing():
            _emit(self.backend.update_state, {"phase": "blocked",
                  "message": "A lecture is still processing. Let it finish or cancel it, "
                             "then install the update."})
            return
        # Flush UI/app state before handing off.
        try:
            adapter = getattr(self.backend, "_adapter", None)
            if adapter is not None and hasattr(adapter, "save_project"):
                adapter.save_project()
        except Exception:  # noqa: BLE001
            pass
        try:
            if os.name == "nt":
                # Visible installer (NOT silent); closes the running app, no reboot.
                subprocess.Popen([self._verified_path, "/CLOSEAPPLICATIONS", "/NORESTART"])  # noqa: S603
            else:
                subprocess.Popen(["xdg-open", self._verified_path])  # noqa: S603,S607
        except Exception as exc:  # noqa: BLE001
            _emit(self.backend.update_state, {"phase": "error", "stage": "install",
                  "message": f"Couldn't launch the installer: {exc}"})
            return
        self._settings.setValue("last_seen_version", version.__version__)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()
        sys.exit(0)

    def _is_processing(self) -> bool:
        try:
            adapter = getattr(self.backend, "_adapter", None)
            return bool(adapter is not None and adapter.is_processing())
        except Exception:  # noqa: BLE001
            return False

    # -------------------------------------------------- misc user actions
    def open_release_page(self):
        url = ""
        if self._pending:
            url = self._pending["release"].get("html_url") or ""
        if not url and version.GITHUB_REPO:
            url = f"https://github.com/{version.GITHUB_REPO}/releases"
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(url))
        except Exception:  # noqa: BLE001
            pass

    def set_channel(self, channel: str):
        self._settings.setValue("update_channel", "stable" if channel == "stable" else "beta")

    def set_auto_check(self, enabled: bool):
        self._settings.setValue("auto_check_enabled", bool(enabled))

    def skip_current(self):
        v = self._settings.value("last_available_version", "")
        if v:
            self._settings.setValue("skipped_version", v)

    def clear_skipped(self):
        self._settings.setValue("skipped_version", "")

    def updater_state_payload(self) -> dict:
        return {
            "auto_check": self._bool("auto_check_enabled", True),
            "channel": self.channel(),
            "portable": self.is_portable(),
            "skipped_version": self._skipped(),
            "last_available_version": self._settings.value("last_available_version", "") or "",
        }
