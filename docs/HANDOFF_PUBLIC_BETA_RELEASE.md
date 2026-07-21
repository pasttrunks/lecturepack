# Handoff — LecturePack Public Beta Release (0.9.0-beta.1)

_Prepared 2026-07-21 during the public-beta release-prep pass._

## Repository / branch / state
- Path: `C:\Users\marsh\Documents\LecturePack`
- Branch: `feat/desktop-webengine`
- **Starting HEAD:** `94df546` (fix(study): in-session New quiz / New cards escape)
- **Ending HEAD:** tip of `feat/desktop-webengine` after this pass (see `git log --oneline -8`; recorded in `status.json`)
- **Safety tag:** `safety/start-public-beta-release-94df546` (= starting HEAD)
- Release version: **0.9.0-beta.1** (single source: `app/desktop/version.py`)

## What this pass did (all committed, suite green)
1. **Versioned to 0.9.0-beta.1** — `version.py`, installer `AppVersion`, Windows
   version resource; `build.py` version-stamping made robust to the `-beta.1`
   suffix; `release.py` accepts pre-release versions; the release workflow marks
   pre-release tags as GitHub pre-releases and publishes installer + portable +
   SHA256. (`bd391b5`)
2. **Smart Study (optional, private local AI)** — first-Study onboarding card +
   Settings card: detect Ollama, two named presets (**Lightweight** qwen3:1.7b /
   **Balanced** qwen3:4b) with a RAM-based recommendation, model download with
   progress + cancel, one structured test request, and persistence. Raw model
   IDs + endpoint live under **Advanced AI details**. Missing Ollama opens the
   official download page — the app never downloads or runs a binary itself.
   New: `ollama_client.pull_model`, `desktop/smart_study.py`, adapter/bridge
   slots (`smart_study_status`/`set_study_preset`/`install_smart_study`/
   `cancel_smart_study`/`launch_ollama_installer`) + signal. (`ac50258`)
3. **Built-in Study never a dead control** — provider labels standardized to
   **Built-in Study / Local AI / Online Enhanced**; Ask now answers
   extractively from the transcript (source-linked, timestamped) when no local
   model is set. (`ac50258`)
4. **Live Groq validation** — see below. (`5d68b39` for evidence)
5. **Release docs** — CHANGELOG, release-page copy, README beta banner. (`5d68b39`)

## Tests at final HEAD
- Focused: `tests/test_smart_study.py` — **17 passed** (presets, RAM thresholds,
  `pull_model` stream/cancel/error, install happy-path/need-engine/skip, and the
  built-in extractive answer).
- Full suite: **308 passed in 161.03s, exit 0** (run at final HEAD; command below).
  Prior baseline was 291; +17 new Smart Study tests.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Artifacts (this environment)
- **PyInstaller onedir + portable ZIP + SHA256 — BUILT & smoke-tested.**
  `LecturePack.exe` (15.2 MB) + onedir (~813 MB) + `LecturePack-0.9.0-beta.1-Portable.zip`
  (326.5 MB) + `LecturePack-0.9.0-beta.1-SHA256SUMS.txt`. Version stamping handled
  the `-beta.1` suffix cleanly. Headless offscreen boot smoke passed: the packaged
  exe launched, QtWebEngine initialized and loaded the UI, and it survived 10s with
  only benign headless GPU warnings — no crash on bundled resources / `_MEIPASS`.
  Evidence: `docs/evidence/public_beta_release/build_smoke.json`.
- **Installer (`LecturePack-0.9.0-beta.1-Setup.exe`):** NOT built here — Inno
  Setup (ISCC) is not installed on this machine. The one-command build produces
  it wherever ISCC is present; the release workflow installs ISCC via Chocolatey.
- Artifact directory: `app/dist/installer/`
- Portable ZIP SHA256: `9d1b504eea3c063efbb28be12dc92f6b6e19230841897a8c900931f10a2f9439`

### One-command build (produces all artifacts)
Prerequisites: `pip install -r app/requirements.txt -r app/requirements-build.txt`
and **Inno Setup 6** (`ISCC.exe`) on PATH for the installer step.
```powershell
# from repo root
.\.venv\Scripts\python.exe app/packaging/build.py            # exe + portable + installer + SHA256
.\.venv\Scripts\python.exe app/packaging/build.py --no-installer   # exe + portable + SHA256 (no ISCC)
```
Or tag to let CI build + publish:
```powershell
.\.venv\Scripts\python.exe app/packaging/release.py 0.9.0-beta.1 --note "Public beta"
```

## Groq status
- **Live-validated with the real key already in Windows Credential Manager.**
  Credential test passed; both **Online Fast** (whisper-large-v3-turbo) and
  **Online Accurate** (whisper-large-v3) transcribed a real 20s lecture clip
  (0.61s vs 1.77s wall). The key was never printed, logged, or written; the
  temp clip was deleted. Evidence (metrics only):
  `docs/evidence/public_beta_release/groq/groq_live.json`.

## Not done here (human / VM acceptance — not code gaps)
- **Clean-machine install test** (fresh Windows profile/VM): installer starts →
  completes → app launches with no source-tree dependency → core transcription,
  slides, preview, exports, built-in Study all work → uninstall keeps
  `LecturePackData`. Requires ISCC-built installer + a clean machine.
- **Upgrade test** (earlier beta → this beta): jobs/settings/study sessions
  persist; no duplicate data folder.
- **Smart Study download matrix** (§18): Ollama present/missing/stopped,
  Lightweight/Balanced install, cancel, interrupt, low disk, model removed
  externally, endpoint changed — needs a live Ollama environment.
- **Packaged windowed click-through** on m2 / Egypt / Mesopotamia jobs — needs a
  human driving the native Qt window (this env cannot; screenshots not fabricated).

## Known limitations (disclosed in release notes)
- Installer not built in this environment (no ISCC); the exe/portable path and
  version stamping were built + smoke-tested here.
- Smart Study download flow is wired + unit-tested but not exercised against a
  live Ollama server here.

## Exit outcome
**Outcome B — beta ready with optional AI wired + unit-tested but the live Smart
Study download matrix and clean-machine/packaged click-through remain human/VM
acceptance.** Core works without Ollama; Groq validated live; full suite green.
Do NOT publish as Outcome A until the clean-machine install + packaged
click-through pass on a real machine.

## Rollback
- Back to this pass's start: `git reset --hard safety/start-public-beta-release-94df546` (= `94df546`).
- Undo one commit: `git revert <sha>`.
- None of these touch `C:\Users\marsh\LecturePackData` (never modified here).

## Next exact command
```powershell
# On a machine with Inno Setup 6 installed:
.\.venv\Scripts\python.exe app/packaging/build.py
# then clean-machine install test of app/dist/installer/LecturePack-0.9.0-beta.1-Setup.exe
```

## Final Git status
See `git status` / `git log --oneline` at the bottom of this pass (recorded in
`docs/evidence/public_beta_release/status.json`).
