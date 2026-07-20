"""Auto-updater backed by GitHub Releases.

On launch the app:
  1. If it just updated (running version > last_seen_version), shows a
     "what's new" overview of this release's notes.
  2. Otherwise checks GitHub for a newer release; if found, emits
     update_available with the release notes so the UI can offer to install.

Installing downloads the release's Windows installer asset, then launches it
in silent-but-visible mode and quits so the installer can replace files.

Everything network-facing runs on a worker thread; the UI is signalled on the
main thread. Failures degrade quietly to update_error — the app still runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from PySide6.QtCore import QObject, QSettings, QThread, Signal

from . import version


def _parse_semver(tag: str) -> tuple[int, int, int]:
    tag = tag.lstrip("vV").split("-")[0]
    parts = (tag.split(".") + ["0", "0", "0"])[:3]
    try:
        return tuple(int(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return (0, 0, 0)


def _is_newer(remote: str, local: str) -> bool:
    return _parse_semver(remote) > _parse_semver(local)


class _CheckWorker(QThread):
    found = Signal(dict)      # release dict for a newer version
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(self, repo: str, current: str):
        super().__init__()
        self._repo = repo
        self._current = current

    def run(self):
        url = f"https://api.github.com/repos/{self._repo}/releases/latest"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                    "User-Agent": "LecturePack-Updater"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        tag = data.get("tag_name", "")
        if tag and _is_newer(tag, self._current):
            self.found.emit(data)
        else:
            self.up_to_date.emit()


class _DownloadWorker(QThread):
    progress = Signal(float)
    done = Signal(str)        # local installer path
    failed = Signal(str)

    def __init__(self, asset_url: str, filename: str):
        super().__init__()
        self._url = asset_url
        self._filename = filename

    def run(self):
        try:
            dest = os.path.join(tempfile.gettempdir(), self._filename)
            req = urllib.request.Request(self._url, headers={"User-Agent": "LecturePack-Updater"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as fh:  # noqa: S310
                total = int(resp.headers.get("Content-Length", 0))
                read = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    read += len(chunk)
                    if total:
                        self.progress.emit(read / total * 100.0)
            self.progress.emit(100.0)
            self.done.emit(dest)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


def _release_to_notes(data: dict) -> dict:
    """Turn a GitHub release into the {version,date,notes[]} payload the UI wants."""
    body = data.get("body", "") or ""
    notes: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith(("- ", "* ", "+ ")):
            notes.append(line[2:].strip())
        elif line.startswith("#") or not line:
            continue
        elif len(notes) < 1:
            notes.append(line)
    if not notes and body.strip():
        notes = [body.strip()[:280]]
    date = (data.get("published_at") or "")[:10]
    return {"version": data.get("tag_name", "").lstrip("vV"), "date": date, "notes": notes[:12]}


class Updater(QObject):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self._settings = QSettings(version.ORG_NAME, version.APP_NAME)
        self._pending: dict | None = None
        self._check_worker: _CheckWorker | None = None
        self._dl_worker: _DownloadWorker | None = None

    # ----------------------------------------------------------- startup
    def startup_check(self):
        last_seen = self._settings.value("last_seen_version", "")
        if last_seen and _is_newer(version.__version__, last_seen):
            # We were just updated — show the changelog overview.
            notes = self._settings.value("last_release_notes", "")
            payload = json.loads(notes) if notes else {"version": version.__version__, "date": "", "notes": []}
            payload["version"] = version.__version__
            self.backend.whatsnew.emit(json.dumps(payload))
            self._settings.setValue("last_seen_version", version.__version__)
        # Always look for something newer (skip in dev / no repo configured).
        if version.GITHUB_REPO and "/" in version.GITHUB_REPO:
            self.check(manual=False)

    # ----------------------------------------------------------- check
    def check(self, manual: bool = False):
        if not (version.GITHUB_REPO and "/" in version.GITHUB_REPO):
            if manual:
                self.backend.settings_changed.emit(json.dumps({"update_status": "No update channel configured"}))
            return
        self._manual = manual
        self._check_worker = _CheckWorker(version.GITHUB_REPO, version.__version__)
        self._check_worker.found.connect(self._on_found)
        self._check_worker.up_to_date.connect(self._on_up_to_date)
        self._check_worker.failed.connect(self._on_check_failed)
        self._check_worker.start()

    def _on_found(self, data: dict):
        self._pending = data
        payload = _release_to_notes(data)
        # Cache notes so the post-install "what's new" can show them.
        self._settings.setValue("last_release_notes", json.dumps(payload))
        self.backend.update_available.emit(json.dumps(payload))

    def _on_up_to_date(self):
        if getattr(self, "_manual", False):
            self.backend.settings_changed.emit(json.dumps({"update_status": "You’re up to date"}))

    def _on_check_failed(self, msg: str):
        if getattr(self, "_manual", False):
            self.backend.settings_changed.emit(json.dumps({"update_status": f"Check failed: {msg}"}))

    # ----------------------------------------------------------- install
    def _installer_asset(self) -> tuple[str, str] | None:
        if not self._pending:
            return None
        for asset in self._pending.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".exe"):
                return asset["browser_download_url"], name
        return None

    def download_and_install(self):
        asset = self._installer_asset()
        if not asset:
            self.backend.update_error.emit("no Windows installer in release")
            return
        url, name = asset
        self._dl_worker = _DownloadWorker(url, name)
        self._dl_worker.progress.connect(self.backend.update_progress.emit)
        self._dl_worker.done.connect(self._run_installer)
        self._dl_worker.failed.connect(self.backend.update_error.emit)
        self._dl_worker.start()

    def _run_installer(self, path: str):
        self.backend.update_ready.emit()
        # Mark so the next launch shows "what's new".
        self._settings.setValue("last_seen_version", version.__version__)
        try:
            if os.name == "nt":
                # Inno Setup: /SILENT shows progress but no wizard pages.
                subprocess.Popen([path, "/SILENT", "/NORESTART"])  # noqa: S603
            else:
                subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
        except Exception as exc:  # noqa: BLE001
            self.backend.update_error.emit(str(exc))
            return
        # Quit so the installer can replace the running executable.
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()
        sys.exit(0)
