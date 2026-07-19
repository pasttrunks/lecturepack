# Windows Portable Installation

Lecture Pack ships as a self-contained **onedir** portable package. No Python
installation is required.

## Steps

1. **Download** `LecturePack-portable-1.0.1.zip` from the private GitHub release.
2. **Verify the checksum** (optional but recommended):
   ```powershell
   Get-FileHash .\LecturePack-portable-1.0.1.zip -Algorithm SHA256
   ```
   Compare the value against `SHA256SUMS.txt` from the same release.
3. **Extract** the ZIP anywhere you like — Desktop, a USB drive, or a folder
   whose path contains spaces (that is fully supported and tested).
4. **Run** `LecturePack.exe`.

## First run

- On first launch the app auto-detects the bundled `ffmpeg.exe`, `ffprobe.exe`,
  and `whisper-cli.exe`. The **Diagnostics** bar shows each dependency's status.
- A Whisper **model** (`.bin`) is **not** bundled (models are large). Download
  one — e.g. `ggml-base.en.bin` — and select it via **Whisper Model** on the
  setup screen. `base.en` is a good starting point; larger models are more
  accurate but slower and need more RAM.
- Choose an **Output** mode (Study Pack / Transcript Only / Slides Only), set the
  slide-detection **Sensitivity** (Balanced is the default), optionally set crop /
  ignore regions, then **Start Processing**.

## What's in the package

- `LecturePack.exe` + `_internal\` (PyInstaller runtime, PySide6, OpenCV, numpy).
- `whisper-cli.exe`, `whisper.dll`, `ggml*.dll` (9 CPU variants — whisper.cpp
  auto-selects the best for your CPU at runtime).
- `bin\ffmpeg.exe`, `bin\ffprobe.exe`.
- `README-FIRST.txt`, `RELEASE_NOTES.md`, `THIRD_PARTY_NOTICES.txt`,
  `SHA256SUMS.txt`, `BUILD_MANIFEST.json`.

## Headless self-check

You can confirm the package launches without opening the GUI:

```powershell
.\LecturePack.exe --selftest      # exits 0 on success
```

## Requirements

- Windows 10/11 x64.
- A CPU with SSE4.2 or newer (whisper.cpp requirement).
- Disk space for job data under `%USERPROFILE%\LecturePackData` (slide images for
  a full lecture can be a few hundred MB).

## Notes

- The binary is **unsigned**; Windows SmartScreen may warn on first launch
  ("More info" → "Run anyway").
- Whisper runs on **CPU only** in this build (no GPU acceleration).
