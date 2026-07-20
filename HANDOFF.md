# LecturePack — Handoff for Claude (repo-connected session)

You have direct access to the `pasttrunks/lecturepack` repo. This document
explains what was just built (in a separate design-handoff session), how to get
it into the repo, and the one real task left: **wiring the existing engine into
the new app**. Read this top to bottom before touching code.

---

## 1. Context — what the user wants

LecturePack is a **Python desktop app** that turns lecture videos into study
packs: it captures slides from the video, transcribes the audio, and provides a
study workspace with local/free AI. **The engine and backend already exist and
work — do not rewrite them.**

The user designed a new UI in Claude Design ("LecturePack Studio" — refined
neobrutalism, orange + aqua `#B3EBF2`, dark by default, Space Grotesk +
JetBrains Mono). Their pain points were:

1. **The UI was never truly 1:1** with the design. Previous attempts rebuilt it
   in Qt widgets, which can't reproduce the CSS (hard shadows, gradients, the
   camera-iris focus animation, glowing scrollbars, web fonts).
2. **Not a real app** — they had to run a command each time instead of
   double-clicking an installed Windows app.
3. **Laggy / not smooth.**
4. They want **auto-update** that shows the user an overview of what changed.

## 2. What was built (already in this branch/bundle)

The approach that fixes "1:1" for good: **render the actual design HTML in a
GPU-accelerated web view**, bridged to Python. It's pixel-identical by
construction and smooth because Chromium composites on the GPU.

Everything lives under `app/`:

```
app/
├── ui/                 # the design, ported to static HTML/CSS/JS (1:1)
│   ├── index.html      # all 7 screens: Home, Process, Review, Transcript, Study, Exports, Settings
│   ├── app.css         # design tokens + keyframes, copied verbatim from LecturePack.dc.html
│   ├── app.js          # screen switching, focus mode, timeline hover-scrub, study tabs,
│   │                   #   chat streaming, quiz, flashcards, import flow, export state machine
│   ├── bridge.js       # QWebChannel client; falls back to demo mode in a plain browser
│   └── fonts/          # Space Grotesk + JetBrains Mono, bundled offline (no CDN)
├── desktop/            # PySide6 shell
│   ├── main.py         # QMainWindow + QWebEngineView + native drag-and-drop of video files
│   ├── bridge.py       # Backend QObject — the JS<->Python contract (signals + slots)
│   ├── engine_adapter.py  # <<< THE ONLY FILE YOU NEED TO EDIT — see section 5
│   ├── updater.py      # GitHub Releases auto-updater + "what's new" overview
│   ├── paths.py        # source-run vs PyInstaller-frozen path resolution
│   └── version.py      # __version__ + GITHUB_REPO (single source of truth)
├── packaging/          # Windows packaging
│   ├── lecturepack.spec       # PyInstaller (onedir, windowed, icon)
│   ├── lecturepack.iss        # Inno Setup installer (shortcuts, uninstaller)
│   ├── build.py               # one-command build: stamps version -> PyInstaller -> Inno
│   ├── release.py             # one-command release: bump + changelog + tag + push
│   ├── make_icon.py           # regenerates lecturepack.ico from the brand mark
│   └── lecturepack.ico/.png   # app icon (committed; no need to regenerate)
├── requirements.txt / requirements-build.txt
├── README.md           # run/build/release instructions
└── verify_ui.py        # headless render check (Playwright/Chromium)

.github/workflows/release.yml   # tag push -> build installer -> publish GitHub Release
CHANGELOG.md                    # each "## [version]" section = the in-app "what's new"
INTEGRATION.md                  # full engine-wiring contract (READ THIS)
```

**Status:** the app runs *today* on a `DemoAdapter` — every screen renders and
every interaction works with the design's sample content. The UI was verified
rendering 1:1 in headless Chromium (all 7 screens, dark + light, plus quiz,
flashcard flip, chat streaming, import, export, focus mode — all passed).
The real engine is **not yet connected** — that's your job.

## 3. Getting the code into the repo

The build session couldn't `git push` (its GitHub account wasn't linked), so the
user received the work as files. If the branch isn't already in the repo:

**Option A — git bundle (preserves the commit + history):**
```bash
git fetch /path/to/lecturepack-desktop.bundle feat/desktop-app-1to1-ui
git checkout feat/desktop-app-1to1-ui
```

**Option B — zip:** unzip `lecturepack-desktop.zip` at the repo root; it adds
`app/`, `.github/`, `INTEGRATION.md`, `CHANGELOG.md`, `HANDOFF.md`, `.gitignore`.
Then commit on a branch.

Either way, confirm `app/ui/index.html`, `app/desktop/*.py`, and `app/packaging/*`
are present before proceeding.

## 4. First thing to do: run it and see the UI

```bash
cd app
pip install -r requirements.txt      # PySide6
python -m desktop.main               # opens the app on the demo adapter
```

Also open `app/ui/index.html` directly in a browser for a no-Python preview
(runs in demo mode). This is the target look — match it exactly; don't "improve"
the CSS.

## 5. THE MAIN TASK — wire the real engine

**You edit exactly one file: `app/desktop/engine_adapter.py`.** Nothing in `ui/`
or the rest of `desktop/` should change. `INTEGRATION.md` has the complete
contract; the short version:

- The file defines `EngineAdapter` (interface, fully docstringed) and
  `DemoAdapter` (a working simulation you can copy from).
- Create `class LecturePackAdapter(EngineAdapter)` that calls the real engine,
  and return it from `make_adapter(backend)` instead of `DemoAdapter`.
- **Push data to the UI** by emitting signals on `self.backend` (all payloads are
  JSON strings). **Respond to user actions** by implementing the methods the
  shell calls.

Signals available (see the table in `INTEGRATION.md` for exact payloads):
`jobs_changed`, `pipeline_changed`, `log_line`, `status_changed`,
`slides_changed`, `transcript_changed`, `study_changed`, `export_progress`,
`export_done`, `ai_token`, `ai_done`, `ai_status`, `settings_changed`.

Methods to implement: `on_ui_ready`, `browse_video`/`import_video`,
`start_processing(mode)`, `cancel_job`, `set_slide_state`, `save_corrections`,
`repair_selection`, `ask_ai` (stream via `ai_token`/`ai_done`), `export_all`/
`export_one`, `export_folder`, `test_endpoint`, `browse_model`, `save_project`.

**Critical:** run all blocking engine work (transcription, slide detection, AI)
on a worker thread (`QThread` or `threading.Thread`) and emit signals from there.
Qt delivers them to the UI thread safely. Never block the Qt main loop or the
60fps UI stutters.

**Suggested order:**
1. Explore the existing engine code — find where jobs, the pipeline, slides,
   transcript, exports, and the local-AI (Ollama) call live.
2. `on_ui_ready` → push existing jobs (`jobs_changed`) and current settings
   (`settings_changed`: `model_path`, `endpoint`, `export_dir`, `version`).
3. Import + pipeline: `import_video`/`start_processing` → run the pipeline on a
   thread, emit `pipeline_changed` + `log_line` + `status_changed` as it goes.
4. Review: feed `slides_changed` + `transcript_changed`; handle
   `set_slide_state`, `save_corrections`, `repair_selection`.
5. Study: `study_changed` for topics/terms/bookmarks/cards; `ask_ai` streaming to
   the local model.
6. Exports: `export_all`/`export_one` → emit `export_progress` then `export_done`.
7. Delete `DemoAdapter` usage once `LecturePackAdapter` is complete (keep the
   class around as reference if handy).

Add the engine's own Python dependencies to `app/requirements.txt`.

## 6. Verify your work (don't just claim it)

The user's #1 frustration is being told things were fixed when they weren't.
After wiring the engine:

- `python -m desktop.main` and actually drive a real video end-to-end: import →
  watch the pipeline → review slides → read transcript → ask the AI → export.
  Confirm real data appears on each screen, not demo data.
- `python verify_ui.py` still passes (UI didn't regress).
- Report exactly what you tested and what you saw. If something isn't wired yet,
  say so.

## 7. Packaging (Windows only)

```bash
cd app
pip install -r requirements.txt -r requirements-build.txt
python packaging/build.py
#  -> dist/LecturePack/LecturePack.exe            (portable)
#  -> dist/installer/LecturePack-Setup-x.y.z.exe  (installer; needs Inno Setup 6 on PATH)
```

You don't need a Windows machine: pushing a version tag triggers
`.github/workflows/release.yml`, which builds the installer on a Windows runner
and publishes a GitHub Release. It uses the repo's default `GITHUB_TOKEN` — no
secrets to configure.

## 8. Auto-update / shipping an update with a "what's new" overview

```bash
cd app
python packaging/release.py 1.1.0 \
    --note "Wired real transcription engine" \
    --note "Fixed export path on Windows"
```

This bumps `desktop/version.py`, prepends the notes to `CHANGELOG.md`, commits,
tags `v1.1.0`, and pushes → the workflow builds + publishes. Installed apps check
`GITHUB_REPO` (`pasttrunks/lecturepack`, set in `version.py`) on launch, offer the
update, install it, and afterward show your notes as the What's New overview.

## 9. Caveats / open items

- **`GITHUB_REPO` + private repos:** the updater reads the "latest release" via
  the public GitHub API. If the repo is private, the check needs an auth token —
  add one to `updater.py`'s request headers if so. Public repo works as-is.
- **Native drag-drop** ("drop a video anywhere") is handled in `main.py`
  (`WebView.dropEvent`) and calls `backend.import_video(path)`. You only implement
  `import_video`; don't rewire the drop plumbing.
- **`qrc:///qtwebchannel/qwebchannel.js`** in `index.html` only resolves inside
  QtWebEngine — that's expected. In a plain browser it 404s harmlessly and the UI
  runs in demo mode. Don't "fix" it.
- **Keep the UI 1:1.** If the user asks for design changes, ideally make them in
  Claude Design and re-export, or mirror the exact CSS values — match the
  prototype, don't approximate.

## 10. TL;DR for the next session

1. Get the branch into the repo (section 3), run `python -m desktop.main`, see
   the 1:1 UI on demo data.
2. Implement `LecturePackAdapter` in `app/desktop/engine_adapter.py` against the
   real engine (section 5 + `INTEGRATION.md`). This is the whole job.
3. Drive a real video end-to-end and verify honestly (section 6).
4. `python packaging/release.py <ver> --note ...` to ship, with a changelog the
   app shows users.
