# LecturePack desktop app

A real Windows application wrapping the LecturePack engine. The UI is the exact
LecturePack Studio design (from Claude Design), rendered in a fast, GPU-accelerated
web view and bridged to Python. Dark by default, orange + aqua neobrutalist.

```
app/
├── ui/                 # the 1:1 design, ported to static HTML/CSS/JS
│   ├── index.html      # all 7 screens (Home, Process, Review, Transcript, Study, Exports, Settings)
│   ├── app.css         # design tokens + animations, copied verbatim from the design
│   ├── app.js          # screen logic, focus mode, timeline scrub, study tabs, import/export flows
│   ├── bridge.js       # QWebChannel client (falls back to demo mode in a plain browser)
│   └── fonts/          # Space Grotesk + JetBrains Mono, bundled offline
├── desktop/            # PySide6 shell
│   ├── main.py         # window + QWebEngineView + native drag-drop
│   ├── bridge.py       # QWebChannel backend object (JS <-> Python contract)
│   ├── engine_adapter.py  # <<< INTEGRATION SEAM — wire the real engine here
│   ├── updater.py      # GitHub Releases auto-updater + "what's new"
│   ├── paths.py        # source-run vs frozen paths
│   └── version.py      # __version__ + GITHUB_REPO (single source of truth)
└── packaging/          # PyInstaller spec + Inno Setup installer + build/release scripts
```

## Run from source

```bash
cd app
pip install -r requirements.txt      # PySide6 (plus your engine's own deps)
python -m desktop.main
```

Without the engine wired, the shell runs on `DemoAdapter` — every screen is
fully clickable with the design's sample content, so you can see the exact UI
immediately.

## Preview just the UI (no Python)

Open `ui/index.html` in any browser. `bridge.js` detects there's no backend and
the UI runs in demo mode. This is what the headless render check drives:

```bash
python verify_ui.py        # walks every screen in dark+light, exercises interactions
```

## Build the Windows app

On Windows with [Inno Setup 6](https://jrsoftware.org/isdl.php) installed:

```bash
cd app
pip install -r requirements.txt -r requirements-build.txt
python packaging/build.py
#  -> dist/LecturePack/LecturePack.exe          (portable folder)
#  -> dist/installer/LecturePack-Setup-x.y.z.exe (installer)
```

## Ship an update (with a "what's new" overview)

```bash
cd app
python packaging/release.py 1.1.0 \
    --note "Faster slide detection" \
    --note "Fix transcript scroll jump"
```

That bumps `version.py`, writes the notes into `CHANGELOG.md`, commits, tags
`v1.1.0`, and pushes. The `release.yml` workflow then builds the installer and
publishes a GitHub Release. Installed apps detect it on next launch, offer to
install, and after updating show your notes as the What's New overview.

See [`INTEGRATION.md`](../INTEGRATION.md) for wiring the real engine.
