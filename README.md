# LecturePack

Turn a lecture recording into a searchable, study-ready workspace — entirely on your own Windows PC. No account, no cloud, no upload.

![Windows](https://img.shields.io/badge/Windows%2010%2F11-x64-0078D4?logo=windows&logoColor=white)
![Electron](https://img.shields.io/badge/UI-Electron-47848F?logo=electron&logoColor=white)
![Local](https://img.shields.io/badge/Processing-100%25%20local-2ea44f)
![License](https://img.shields.io/badge/License-MIT-green)

<p align="center">
  <a href="https://github.com/pasttrunks/lecturepack/releases/latest">
    <img src="https://img.shields.io/badge/⬇%20Download%20for%20Windows-Setup.exe-2ea44f?style=for-the-badge&logo=windows&logoColor=white" alt="Download LecturePack for Windows" height="46">
  </a>
</p>
<p align="center">
  <sub>Windows 10/11 · 64-bit · per-user install, no admin required · also available as a
  Portable ZIP · <a href="https://github.com/pasttrunks/lecturepack/releases">all releases</a> ·
  every release publishes a <code>SHA256SUMS.txt</code> you can verify</sub>
</p>

---

## Nothing else to install

Download, install, open. LecturePack bundles everything it needs:

| You do **not** need | Because LecturePack ships |
| --- | --- |
| Python | a self-contained processing service |
| Node, Deno | a bundled JavaScript runtime for link import |
| FFmpeg | FFmpeg and FFprobe |
| A speech model | whisper.cpp with the `base.en` model |
| Rust | a prebuilt native Study engine |

No API key, no sign-in, and no first-run download before you can transcribe your first lecture.

---

## What it does

1. **Import** a lecture — pick a file, drag one in, send a whole folder, right-click **Send to → LecturePack**, or paste a link.
2. **Transcribe** locally with whisper.cpp.
3. **Detect slides** from the video and align the transcript to them.
4. **Review** — fix slide boundaries and transcript text.
5. **Study** — flashcards, quizzes, and grounded answers built from your own lecture.
6. **Export** — slides, transcripts and study packs in a range of formats.

Everything above happens on your machine.

---

## Study

LecturePack builds study material out of the lecture you imported, not out of a general-purpose model's guesswork.

- **Study overview** — the lecture broken into topics you can work through.
- **Flashcards** — generated from the transcript, with spaced-repetition scheduling.
- **Quiz** — practice questions drawn from the material.
- **Ask** — ask a question and get an answer with the transcript passages it came from, so you can check it against the lecture.
- **Quick Study** — a short focused session when you have a few minutes.
- **Needs Review** — surfaces what you are getting wrong and schedules it sooner.

Scheduling and mastery tracking run in a native **Rust Study Core** for speed, with a Python fallback if the native module cannot load.

---

## Import and queue

- Import several files or a whole folder at once.
- A processing queue with live progress and estimated time remaining.
- Keeps working in the background and in the tray.
- Restores your session and window on next launch.
- Recovers interrupted jobs and downloads after a crash or restart.
- **Import from a link** for supported public video URLs.

---

## Updates

LecturePack checks GitHub for stable releases and can install them for you.

An update is only ever installed when **all** of the following hold: the release is a published stable release, its version is genuinely newer, the asset is the expected Windows 64-bit installer, and the installer's SHA-256 matches the signed release manifest exactly. If any check fails, LecturePack refuses the update, deletes what it downloaded, leaves your installation untouched, and tells you why. There is no "install it anyway" path.

You can turn automatic checking off, skip a version, cancel a download in progress, or verify the release yourself on GitHub.

> **Note:** LecturePack's Windows binaries are not yet Authenticode-signed, so Windows may show a SmartScreen warning on first run. Every release publishes `SHA256SUMS.txt` so you can verify the download yourself.

---

## Privacy and network use

Your lectures, transcripts, slides and study data stay on your PC. LecturePack has **no telemetry, no analytics, and no account system**.

LecturePack uses the network in exactly these situations:

| When | What it contacts |
| --- | --- |
| Checking for updates | `api.github.com` and `github.com`, to read the release list and download an installer you approve. Can be turned off. |
| You import from a link | Only the site you pasted, to fetch that video. |
| You enable an optional AI feature | Only the endpoint you configure — see below. |

**Optional AI features are off unless you set them up.** You can point LecturePack at a local model server (such as Ollama or LM Studio) running on your own machine, in which case nothing leaves your PC. If you instead supply your own Groq API key for faster transcription, audio is sent to that service — that is the one case where lecture content leaves your machine, it only happens with a key you entered yourself, and the key is never stored on disk.

Transcription, slide detection, alignment, study generation and exports all run locally and need no network at all.

---

## Installing

**Installer** — download `LecturePack-<version>-Setup.exe` from the [latest release](https://github.com/pasttrunks/lecturepack/releases/latest) and run it. It installs for your user only, so it does not ask for administrator rights, and it adds a **Send to → LecturePack** entry to Explorer.

**Portable** — download `LecturePack-<version>-Portable.zip`, unpack it anywhere, and run `LecturePack.exe`.

**Verifying your download** (optional):

```powershell
Get-FileHash .\LecturePack-<version>-Setup.exe -Algorithm SHA256
```

Compare the result with `LecturePack-<version>-SHA256SUMS.txt` from the same release.

**Requirements:** Windows 10 or 11, 64-bit. Transcription is CPU-based and faster on more cores.

---

## Architecture

```
Electron main process          window, tray, updater, file arguments
        |  contextIsolation, sandboxed renderer, narrow preload
        v
Preload / IPC bridge           the only channel the UI can use
        |
        v
Python sidecar (packaged)      one process, JSONL protocol
        |
        v
LecturePack engine (Python)    jobs, transcripts, slides, exports
        |                    \
        v                     v
Rust Study Core          Native tools
scheduling, mastery      FFmpeg · FFprobe · whisper.cpp · yt-dlp + Deno
```

The renderer has no Node integration and no filesystem access: it runs sandboxed with context isolation, cannot navigate away, and cannot open windows of its own. Anything it needs goes through the preload bridge to the main process.

The Python sidecar is frozen into the package, which is why no Python installation is required.

---

## Building from source

Contributors only — users should download a release.

```bash
git clone https://github.com/pasttrunks/lecturepack.git
cd lecturepack
python -m pip install -r requirements.txt -r requirements-dev.txt
npm --prefix electron-spike ci
python -m pytest
```

Producing an official release package additionally needs the pinned dependency set in `requirements-release.txt`, Inno Setup 6, a Rust toolchain for the Study Core, and the bundled native runtimes under `bin/` and `models/`. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and `.github/workflows/release-electron.yml`, which is the single authoritative desktop release path.

---

## Documentation

- [CHANGELOG.md](CHANGELOG.md) — release history
- [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) — bundled components and their licences
- [CONTRIBUTING.md](CONTRIBUTING.md) — development setup
- [docs/](docs/) — architecture and design decisions

## Licence

LecturePack's own source is MIT-licensed. Bundled third-party components keep
their own licences — notably FFmpeg, which is redistributed under the GPL; see
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) for the full list.
