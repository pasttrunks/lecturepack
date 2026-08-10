"""Fail closed if the authoritative LecturePack version surfaces disagree.

An official release is only coherent when every place that states a version
states the same one. This script is the single gate for that, used by the
canonical Electron release workflow and by the version-surface test.

Surfaces:
  * app/desktop/version.py           __version__
  * electron-spike/package.json      version   (drives the Electron product
                                                version and every artifact
                                                filename)
  * electron-spike/package-lock.json version + packages[""].version
  * app/packaging/lecturepack.iss    the #define AppVersion fallback

Usage:
    python scripts/verify_release_versions.py                 # surfaces agree?
    python scripts/verify_release_versions.py --expect 2.0.1  # ...and match tag
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def _python_version() -> str:
    text = (ROOT / "app" / "desktop" / "version.py").read_text(encoding="utf-8")
    match = re.search(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    if not match:
        raise RuntimeError("app/desktop/version.py does not define __version__")
    return match.group(1)


def _package_json_version() -> str:
    path = ROOT / "electron-spike" / "package.json"
    value = json.loads(path.read_text(encoding="utf-8")).get("version", "")
    if not value:
        raise RuntimeError(f"{path} does not define a version")
    return str(value)


def _iss_version() -> str:
    path = ROOT / "app" / "packaging" / "lecturepack.iss"
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'#define\s+AppVersion\s+"([^"]+)"', text)
    if not match:
        raise RuntimeError(f"{path} does not define AppVersion")
    return match.group(1)


def collect() -> dict[str, str]:
    """Every authoritative version surface, keyed by a stable label."""
    surfaces = {
        "app/desktop/version.py": _python_version(),
        "electron-spike/package.json": _package_json_version(),
        "app/packaging/lecturepack.iss": _iss_version(),
    }
    lock_path = ROOT / "electron-spike" / "package-lock.json"
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        surfaces["electron-spike/package-lock.json"] = str(lock.get("version", ""))
        root_package = (lock.get("packages") or {}).get("", {})
        if "version" in root_package:
            surfaces['electron-spike/package-lock.json packages[""]'] = str(root_package["version"])
    return surfaces


def verify(expected: str | None = None) -> tuple[bool, str]:
    surfaces = collect()
    problems: list[str] = []

    for label, value in sorted(surfaces.items()):
        if not SEMVER.match(value):
            problems.append(f"  {label}: {value!r} is not a valid semantic version")

    distinct = sorted(set(surfaces.values()))
    if len(distinct) > 1:
        problems.append(f"  version surfaces disagree: {distinct}")

    if expected is not None:
        want = expected.lstrip("vV")
        mismatched = {k: v for k, v in surfaces.items() if v != want}
        if mismatched:
            problems.append(f"  expected {want!r}, but: {json.dumps(mismatched, indent=4)}")

    listing = "\n".join(f"  {label}: {value}" for label, value in sorted(surfaces.items()))
    if problems:
        return False, "Release version surfaces are inconsistent:\n" + "\n".join(problems) + \
                      "\n\nSurfaces:\n" + listing
    return True, f"All release version surfaces agree on {distinct[0]}:\n{listing}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expect", help="version (with or without a leading v) every surface must match")
    args = parser.parse_args(argv)
    ok, message = verify(args.expect)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
