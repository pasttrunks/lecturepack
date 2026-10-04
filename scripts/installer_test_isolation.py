"""Restore per-user shell integration around disposable Windows installs."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess


GUARD = Path(__file__).with_suffix(".ps1")
POWERSHELL = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe")


class InstallerTestIsolation:
    """Snapshot before mutation; always uninstall and restore in that order."""

    def __init__(self, install_dir: Path, state_path: Path):
        self.install_dir = Path(install_dir).resolve()
        self.state_path = Path(state_path).resolve()

    def _guard(self, action: str) -> None:
        subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(GUARD),
             "-Action", action, "-InstallDir", str(self.install_dir), "-StatePath", str(self.state_path)],
            check=True, shell=False, timeout=120,
        )

    def __enter__(self):
        self._guard("Snapshot")
        return self

    def __exit__(self, exc_type, exc, traceback):
        errors = []
        try:
            uninstaller = self.install_dir / "unins000.exe"
            if uninstaller.is_file():
                subprocess.run(
                    [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                    check=True, shell=False, timeout=300,
                )
            if (self.install_dir / "LecturePack.exe").exists():
                raise RuntimeError(f"Disposable app remains after uninstall: {self.install_dir}")
        except Exception as error:
            errors.append(error)
        finally:
            try:
                self._guard("Restore")
            except Exception as error:
                errors.append(error)
        if errors:
            # Keep both the original failure and every cleanup failure visible.
            if exc is not None:
                errors.insert(0, exc)
            raise ExceptionGroup("Installer acceptance or host restoration failed", errors)
        return False
