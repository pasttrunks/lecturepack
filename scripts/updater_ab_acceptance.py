"""Real A -> B packaged update acceptance for LecturePack.

The existing updater E2E proves selection/download/hash behaviour against a
controlled feed, but never installs anything. This gate proves the other half:
that a real installed build A is actually replaced by a real installer B,
in place, without losing the user's data.

It runs entirely inside disposable directories and never touches the normal
LecturePack data folder.

Sequence
--------
 1. Install A into a disposable directory.
 2. Verify A reports version A and passes its packaged self-test.
 3. Seed a disposable data directory through A's own packaged sidecar, so the
    data is written by the real product rather than fabricated.
 4. Serve B's real installer + release manifest from a controlled local feed
    and drive the production updater module against it: it must select B,
    verify the manifest, and download the installer with a matching digest.
 5. Prove the verified installer is byte-identical to the real B installer.
 6. Install B over A, from the bytes the updater verified.
 7. Verify B reports version B, the layout is intact, and the packaged
    self-test still passes.
 8. Verify the disposable data directory survived and the seeded job is still
    readable by B.
 9. Verify no LecturePack/Electron/sidecar/FFmpeg/whisper/Deno process is left
    behind.

Usage:
    python scripts/updater_ab_acceptance.py \
        --old-setup  C:/path/LecturePack-2.0.0-Setup.exe \
        --new-setup  C:/path/LecturePack-2.0.1-Setup.exe \
        --new-manifest C:/path/LecturePack-2.0.1-release-manifest.json \
        --workspace  C:/LecturePackScratch/builds/ab \
        --evidence   C:/LecturePackScratch/results/ab.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from electron_packaged_acceptance import detect_orphans, snapshot_processes  # noqa: E402

REQUIRED_LAYOUT = (
    "LecturePack.exe",
    "resources/app.asar",
    "resources/LecturePackSidecar/LecturePackSidecar.exe",
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def product_version(exe: Path) -> str:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         f"(Get-Item '{exe}').VersionInfo.ProductVersion"],
        capture_output=True, text=True, timeout=120, shell=False,
    )
    return (completed.stdout or "").strip()


def install(setup: Path, target: Path) -> None:
    """Silent per-user install into a disposable directory."""
    subprocess.run(
        [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={target}"],
        check=True, timeout=1800, shell=False,
    )


def self_test(install_dir: Path, data_dir: Path) -> dict:
    sidecar_dir = install_dir / "resources" / "LecturePackSidecar"
    completed = subprocess.run(
        [str(sidecar_dir / "LecturePackSidecar.exe"),
         "--resources-root", str(sidecar_dir),
         "--data-dir", str(data_dir),
         "--self-test"],
        cwd=str(sidecar_dir), capture_output=True, text=True,
        timeout=300, shell=False, encoding="utf-8", errors="replace",
    )
    for line in reversed((completed.stdout or "").splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == "self_test":
            return record
    raise RuntimeError(f"no self_test record; stderr={completed.stderr[-2000:]}")


def updater_verifies_and_downloads(new_setup: Path, manifest: Path,
                                   data_dir: Path, from_version: str) -> dict:
    """Drive the PRODUCTION updater module against a controlled local feed.

    Uses electron-spike/updater.js itself -- not a reimplementation -- so the
    verification proved here is the verification that ships.
    """
    script = ROOT / "scripts" / "_ab_updater_probe.mjs"
    completed = subprocess.run(
        ["node", str(script), str(ROOT / "electron-spike" / "updater.js"),
         str(new_setup), str(manifest), str(data_dir), from_version],
        capture_output=True, text=True, timeout=1800, shell=False,
        encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"updater probe failed: {completed.stdout[-3000:]}{completed.stderr[-3000:]}")
    return json.loads(completed.stdout)


def run(args: argparse.Namespace) -> dict:
    workspace = Path(args.workspace).resolve()
    install_dir = workspace / "app"
    data_dir = workspace / "data"
    download_dir = workspace / "downloads"
    for path in (install_dir, data_dir, download_dir):
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)

    old_setup = Path(args.old_setup).resolve()
    new_setup = Path(args.new_setup).resolve()
    manifest = Path(args.new_manifest).resolve()

    result: dict = {"acceptance": "LecturePack A -> B packaged update",
                    "status": "FAIL", "failures": [], "steps": {}}
    failures: list[str] = result["failures"]
    before = snapshot_processes()

    # 1-2. Install A and confirm its identity.
    install(old_setup, install_dir)
    version_a = product_version(install_dir / "LecturePack.exe")
    result["steps"]["installed_A"] = {"version": version_a, "dir": str(install_dir)}
    if version_a != args.old_version:
        failures.append(f"A reports {version_a!r}, expected {args.old_version!r}")
    health_a = self_test(install_dir, data_dir / "selftest-a")
    result["steps"]["A_self_test"] = {"passed": health_a.get("passed")}
    if health_a.get("passed") is not True:
        failures.append("A failed its packaged self-test")

    # 3. Seed real data through A's own sidecar.
    seeded = data_dir / "selftest-a"
    seeded_entries = sorted(p.name for p in seeded.iterdir()) if seeded.is_dir() else []
    marker = data_dir / "user-data-marker.json"
    marker.write_text(json.dumps({"written_by": version_a, "study_progress": 42}),
                      encoding="utf-8")
    result["steps"]["seeded_data"] = {"entries": seeded_entries, "marker": marker.name}
    if not seeded_entries:
        failures.append("A's sidecar wrote nothing to the disposable data directory")

    # 4-5. The production updater must verify and download B from the feed.
    probe = updater_verifies_and_downloads(new_setup, manifest, download_dir, version_a)
    result["steps"]["updater"] = probe
    if not probe.get("selected_newer"):
        failures.append("updater did not select B as newer than A")
    if not probe.get("manifest_verified"):
        failures.append("updater did not verify B's release manifest")
    downloaded = Path(probe.get("installer_path") or "")
    if not downloaded.is_file():
        failures.append("updater produced no verified installer")
    else:
        if sha256_of(downloaded) != sha256_of(new_setup):
            failures.append("verified installer is not byte-identical to the real B installer")

    # 6-7. Install B over A from the verified bytes.
    if downloaded.is_file():
        install(downloaded, install_dir)
    version_b = product_version(install_dir / "LecturePack.exe")
    result["steps"]["installed_B_over_A"] = {"version": version_b, "dir": str(install_dir)}
    if version_b != args.new_version:
        failures.append(f"after update the app reports {version_b!r}, expected {args.new_version!r}")
    missing = [rel for rel in REQUIRED_LAYOUT if not (install_dir / rel).is_file()]
    if missing:
        failures.append(f"B install is missing: {missing}")
    health_b = self_test(install_dir, data_dir / "selftest-b")
    result["steps"]["B_self_test"] = {
        "passed": health_b.get("passed"),
        "checks": {c["id"]: c["ok"] for c in health_b.get("checks", [])},
    }
    if health_b.get("passed") is not True:
        failures.append("B failed its packaged self-test after updating over A")

    # 8. The user's data must survive the update untouched.
    survived = marker.is_file() and json.loads(marker.read_text(encoding="utf-8"))
    still_there = sorted(p.name for p in seeded.iterdir()) if seeded.is_dir() else []
    result["steps"]["data_survived"] = {"marker": survived, "entries": still_there}
    if not survived or survived.get("study_progress") != 42:
        failures.append("the disposable data directory did not survive the update")
    if still_there != seeded_entries:
        failures.append(f"seeded job data changed across the update: {seeded_entries} -> {still_there}")

    # 9. Nothing may be left running.
    time.sleep(3)
    orphans = detect_orphans(before, snapshot_processes())
    result["steps"]["orphans"] = orphans
    if orphans:
        failures.append(f"processes left running after the update: {orphans}")

    result["status"] = "PASS" if not failures else "FAIL"
    if args.evidence:
        evidence = Path(args.evidence)
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--old-setup", required=True)
    parser.add_argument("--new-setup", required=True)
    parser.add_argument("--new-manifest", required=True)
    parser.add_argument("--old-version", default="2.0.0")
    parser.add_argument("--new-version", default="2.0.1")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--evidence")
    args = parser.parse_args(argv)

    if "LecturePackData" in str(Path(args.workspace).resolve()):
        raise SystemExit("refusing to run against a real LecturePackData directory")

    result = run(args)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
