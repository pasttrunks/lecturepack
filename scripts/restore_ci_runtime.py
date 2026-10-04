"""Restore only pinned native build inputs from a verified public release ZIP.

Build tooling only: no application download override or credentials. Existing
runtime roots are refused; incomplete downloads/restores are preserved on error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import urllib.request
import zipfile

LOCK = Path(__file__).with_name("ci-runtime-lock.json")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_archive(archive: Path, lock: dict) -> None:
    if archive.stat().st_size != lock["archive_size"] or sha256(archive) != lock["archive_sha256"]:
        raise ValueError("runtime source archive does not match its pinned size/SHA-256")


def fetch_archive(cache: Path, lock: dict) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "runtime-source.zip"
    if archive.exists():
        verify_archive(archive, lock)
        return archive
    url = lock["url"]
    if not url.startswith("https://github.com/pasttrunks/lecturepack/releases/download/"):
        raise ValueError("runtime lock must reference an HTTPS LecturePack release asset")
    partial = archive.with_suffix(".zip.partial")
    with partial.open("xb") as destination:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "LecturePack-CI-runtime"}), timeout=60) as response:
            if not response.url.startswith("https://"):
                raise ValueError("runtime source redirected away from HTTPS")
            received = 0
            while block := response.read(1024 * 1024):
                received += len(block)
                if received > lock["archive_size"]:
                    raise ValueError("runtime source exceeds its pinned size")
                destination.write(block)
    verify_archive(partial, lock)
    partial.rename(archive)
    return archive


def restore_runtime(archive: Path, destination: Path, lock: dict) -> dict:
    if destination.exists():
        raise ValueError("runtime destination must not exist; preserve earlier evidence")
    verify_archive(archive, lock)
    files = lock["files"]
    prepared = []
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        for relative, pin in files.items():
            path = PurePosixPath(relative)
            member = PurePosixPath(pin["member"])
            for value, parsed in ((relative, path), (pin["member"], member)):
                if parsed.is_absolute() or ".." in parsed.parts or "\\" in value or ":" in value:
                    raise ValueError("unsafe runtime path in lock")
            if not relative.startswith(("bin/", "models/", "msvc/")):
                raise ValueError("lock contains a non-runtime destination")
            matches = [entry for entry in entries if entry.filename == pin["member"]]
            if len(matches) != 1:
                raise ValueError(f"runtime member missing or duplicated: {relative}")
            entry = matches[0]
            if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.file_size != pin["size"]:
                raise ValueError(f"runtime member type/size differs from lock: {relative}")
            prepared.append((relative, entry, pin))
        destination.mkdir(parents=True)
        evidence = {}
        for relative, entry, pin in prepared:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output, length=1024 * 1024)
            digest = sha256(target)
            if digest != pin["sha256"]:
                raise ValueError(f"runtime member SHA-256 differs from lock: {relative}")
            evidence[relative] = {"sha256": digest, "size": target.stat().st_size}
    return {"source_release": lock["source_release"], "archive_sha256": lock["archive_sha256"],
            "runtime_root": str(destination.resolve()), "files": evidence}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    locked = json.loads(LOCK.read_text(encoding="utf-8"))
    restored = restore_runtime(fetch_archive(args.cache_dir, locked), args.output_dir, locked)
    print(json.dumps(restored, indent=2))
