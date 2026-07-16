#!/usr/bin/env python3
"""
LecturePack v0.2.1 - Build & Package Script
Builds a PyInstaller onedir distribution and creates a portable ZIP.

Usage:
    python build_release.py

Prerequisites:
    - .venv with pyinstaller, PySide6, opencv-python-headless, etc.
    - bin/ffmpeg.exe, bin/ffprobe.exe, bin/Release/whisper-cli.exe + DLLs
"""

import os
import sys
import shutil
import subprocess
import hashlib
import json
import zipfile
import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
RELEASE_DIR = os.path.join(PROJECT_ROOT, "dist-release")
APP_NAME = "LecturePack"
VERSION = "1.1.0"

# Binaries to include from bin/Release/ (whisper runtime)
WHISPER_BINS = [
    "whisper-cli.exe",
    "whisper.dll",
    "ggml.dll",
    "ggml-base.dll",
]

# All ggml-cpu variants - whisper.cpp auto-selects at runtime
WHISPER_CPU_DLLS = [
    "ggml-cpu-alderlake.dll",
    "ggml-cpu-cannonlake.dll",
    "ggml-cpu-cascadelake.dll",
    "ggml-cpu-haswell.dll",
    "ggml-cpu-icelake.dll",
    "ggml-cpu-sandybridge.dll",
    "ggml-cpu-skylakex.dll",
    "ggml-cpu-sse42.dll",
    "ggml-cpu-x64.dll",
]

FFMPEG_BINS = ["ffmpeg.exe", "ffprobe.exe"]

# Optional Vulkan engine (bin/vulkan/) -- whisper.cpp v1.9.1 built with
# GGML_VULKAN + GGML_BACKEND_DL. Shipped alongside (never replacing) the
# verified CPU binary; the engine registry falls back to CPU automatically.
VULKAN_BINS = [
    "whisper-cli.exe",
    "libwhisper.dll",
    "ggml.dll",
    "ggml-base.dll",
    "ggml-cpu.dll",
    "ggml-vulkan.dll",
    "libgcc_s_seh-1.dll",
    "libstdc++-6.dll",
    "libwinpthread-1.dll",
    "libgomp-1.dll",
]


def run(cmd, **kwargs):
    print(f"  > {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, **kwargs)
    if result.returncode != 0:
        print(f"  FAILED (exit {result.returncode})")
        sys.exit(1)
    return result


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    print(f"=== LecturePack {VERSION} Build ===\n")

    # Clean previous builds
    for d in [DIST_DIR, BUILD_DIR, RELEASE_DIR]:
        if os.path.isdir(d):
            print(f"Cleaning {d}")
            shutil.rmtree(d)
    os.makedirs(RELEASE_DIR, exist_ok=True)

    # Step 1: PyInstaller build
    print("[1/5] Running PyInstaller...")
    run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        "LecturePack.spec",
    ])

    app_dir = os.path.join(DIST_DIR, APP_NAME)
    if not os.path.isdir(app_dir):
        print(f"ERROR: Expected output dir not found: {app_dir}")
        sys.exit(1)

    # Step 2: Copy external binaries
    print("[2/5] Copying binaries...")
    bin_dir = os.path.join(app_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    # FFmpeg
    src_bin = os.path.join(PROJECT_ROOT, "bin")
    for fn in FFMPEG_BINS:
        src = os.path.join(src_bin, fn)
        dst = os.path.join(bin_dir, fn)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  Copied {fn} ({os.path.getsize(dst) / 1024 / 1024:.1f} MB)")
        else:
            print(f"  WARNING: {fn} not found in bin/")

    # Whisper CLI + DLLs
    whisper_src = os.path.join(src_bin, "Release")
    for fn in WHISPER_BINS + WHISPER_CPU_DLLS:
        src = os.path.join(whisper_src, fn)
        dst = os.path.join(app_dir, fn)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  Copied {fn}")
        else:
            print(f"  WARNING: {fn} not found in bin/Release/")

    # Optional Vulkan engine
    vulkan_src = os.path.join(src_bin, "vulkan")
    if os.path.isdir(vulkan_src):
        vulkan_dst = os.path.join(bin_dir, "vulkan")
        os.makedirs(vulkan_dst, exist_ok=True)
        for fn in VULKAN_BINS:
            src = os.path.join(vulkan_src, fn)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(vulkan_dst, fn))
                print(f"  Copied vulkan/{fn}")
            else:
                print(f"  WARNING: {fn} not found in bin/vulkan/")
    else:
        print("  NOTE: bin/vulkan/ not present; packaging CPU engine only.")

    # Step 3: Copy release documentation
    print("[3/5] Copying documentation...")
    docs = ["README-FIRST.txt", "THIRD_PARTY_NOTICES.txt", "RELEASE_NOTES.md"]
    for fn in docs:
        src = os.path.join(PROJECT_ROOT, fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(app_dir, fn))
        else:
            print(f"  WARNING: {fn} not found, skipping")

    # Step 4: Create portable ZIP
    print("[4/5] Creating portable ZIP...")
    zip_name = f"{APP_NAME}-portable-{VERSION}.zip"
    zip_path = os.path.join(RELEASE_DIR, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(app_dir):
            # Skip __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                fp = os.path.join(root, fn)
                arcname = os.path.join(APP_NAME, os.path.relpath(fp, app_dir))
                zf.write(fp, arcname)
    print(f"  ZIP: {zip_path} ({os.path.getsize(zip_path) / 1024 / 1024:.1f} MB)")

    # Step 5: Generate SHA256SUMS and BUILD_MANIFEST
    print("[5/5] Generating checksums and manifest...")
    manifest_entries = []
    sha256_lines = []

    # Checksum the ZIP
    digest = sha256_file(zip_path)
    sha256_lines.append(f"{digest}  {zip_name}")
    manifest_entries.append({
        "file": zip_name,
        "sha256": digest,
        "size_bytes": os.path.getsize(zip_path),
    })

    # Also checksum individual binaries for reference
    for fn in FFMPEG_BINS + WHISPER_BINS:
        fp = os.path.join(bin_dir, fn)
        if os.path.isfile(fp):
            digest = sha256_file(fp)
            sha256_lines.append(f"{digest}  bin/{fn}")
            manifest_entries.append({
                "file": f"bin/{fn}",
                "sha256": digest,
                "size_bytes": os.path.getsize(fp),
            })
    for fn in VULKAN_BINS:
        fp = os.path.join(bin_dir, "vulkan", fn)
        if os.path.isfile(fp):
            digest = sha256_file(fp)
            sha256_lines.append(f"{digest}  bin/vulkan/{fn}")
            manifest_entries.append({
                "file": f"bin/vulkan/{fn}",
                "sha256": digest,
                "size_bytes": os.path.getsize(fp),
            })

    # Write SHA256SUMS.txt
    sha_path = os.path.join(RELEASE_DIR, "SHA256SUMS.txt")
    with open(sha_path, "w") as f:
        f.write(f"LecturePack {VERSION} Release Checksums\n")
        f.write(f"Generated: {datetime.datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n")
        for line in sha256_lines:
            f.write(line + "\n")

    # Copy SHA256SUMS into the app dir too
    shutil.copy2(sha_path, os.path.join(app_dir, "SHA256SUMS.txt"))

    # Write BUILD_MANIFEST.json
    manifest = {
        "app": APP_NAME,
        "version": VERSION,
        "build_time": datetime.datetime.now().isoformat(),
        "python": sys.version,
        "platform": sys.platform,
        "pyinstaller": "6.21.0",
        "files": manifest_entries,
    }
    manifest_path = os.path.join(RELEASE_DIR, "BUILD_MANIFEST.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    shutil.copy2(manifest_path, os.path.join(app_dir, "BUILD_MANIFEST.json"))

    # Copy RELEASE_NOTES into release dir
    rn_src = os.path.join(PROJECT_ROOT, "RELEASE_NOTES.md")
    if os.path.isfile(rn_src):
        shutil.copy2(rn_src, os.path.join(RELEASE_DIR, "RELEASE_NOTES.md"))

    print(f"\n=== Build Complete ===")
    print(f"  App dir:   {app_dir}")
    print(f"  Release:   {RELEASE_DIR}")
    print(f"  ZIP:       {zip_path}")
    print(f"  Manifest:  {manifest_path}")


if __name__ == "__main__":
    main()
