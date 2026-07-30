# Phase 1: Clean-Device Footprint & First Launch - Research

**Researched:** 2026-07-30
**Domain:** PyInstaller/Qt6 packaging size reduction; Qt desktop startup sequencing; Windows single-instance/AppUserModelID; WebEngine-hosted first-run UX
**Confidence:** HIGH for the size-cut mechanism, model dedupe, taskbar-icon cause, and updater-regression facts (all directly verified against the actual dist tree, PyInstaller source, and git history in this repo). MEDIUM for the single-instance mechanism recommendation and the exact `resources/` cut (verified against Qt's own docs, not yet proven on a rebuilt tree). LOW/ASSUMED only where explicitly marked below.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Package size**
- **D-01:** Cut scope is fixed at: dedupe `ggml-base.en.bin` to a single location, and remove `translations/`, `qml/`, the Quick/Quick3D DLLs, and `Qt6Pdf.dll`. Each is provably unused by this application.
- **D-02:** `opengl32sw.dll` stays. The software GL fallback is what keeps the app working on VMs and old GPUs — exactly the clean-device population this phase serves.
- **D-03:** An aggressive Qt allowlist was **considered and rejected** for this phase. A missing module surfaces only in the packaged build on a clean machine, which is the slowest environment available to iterate in. Revisit only if D-01 proves insufficient.
- **D-04:** `resources/` (102 MB) is not pre-approved for cutting. Investigate what is actually loaded before removing anything from it; report findings rather than guessing.
- **D-05:** Whichever copy of `ggml-base.en.bin` survives, the guided demo and the runtime admission smoke must both resolve it. Deduplication must not be done by deleting one path and hoping — the resolution logic is the deliverable, not the deletion.

**Startup**
- **D-06:** Root cause is established and must not be re-litigated: `RuntimeBootstrapService.assess()` is called synchronously on the UI thread in `Backend.__init__` (`app/desktop/bridge.py:119`), before the window is shown. On a fresh profile it takes the full path — `ffmpeg -version`, `ffprobe -version`, and a real staged whisper-cli transcription of the smoke WAV — each bounded at 30s (`runtime_validation.py:24`). Worst case ~90s of subprocess work with nothing on screen.
- **D-07:** This is a **one-time** cost, not per-launch. `_requires_full()` (`runtime_bootstrap.py:110-126`) sends subsequent launches down a light path that only stats files. Cold and warm launches are therefore expected to differ sharply, and both must be measured separately.
- **D-08:** Fix both sides. Show the window first and run validation behind honest, itemized per-component progress; **and** reduce the validation cost itself where it can be done without weakening admission evidence.
- **D-09:** Progress must name the real work in progress ("Checking Whisper runtime…"), not a generic bar. This is the distinction between honest feedback and the splash screen the owner explicitly ruled out.
- **D-10:** Any speed work must preserve the admission contract. Parallelizing the three independent probes is permitted. Replacing the real transcription with a weaker liveness check is **not** — that is the evidence AD-18 and the Phase 1 runtime contract rest on. If parallelization alone is insufficient, report that rather than weakening the check.

**First-run setup checklist**
- **D-11:** The existing gate is a **failure** gate — it renders only when assessment returns not-`HEALTHY`, so a healthy fresh profile correctly skips it today. The owner's report is a request for new behavior, not a bug report. Plan it as a behavior change.
- **D-12:** On a first-ever launch the checklist always appears, showing Ready / Needs Attention per requirement, then a Continue action leads to the demo offer. Existing failure-gate behavior is unchanged.
- **D-13:** The checklist verifies only: supported Windows version; bundled FFmpeg and ffprobe; bundled Whisper executable and required DLLs; bundled model; writable LecturePack data directory. Nothing else.
- **D-14:** The checklist never downloads or reinstalls a component that is already bundled. Remediation stays the existing consented signed-repair path.
- **D-15:** It lives in the existing WebEngine UI (`#runtime-setup-overlay`, `app/ui/app.js`), reusing the app's own vocabulary. A native Qt pre-window was considered and rejected — it would introduce a second visual language for the first thing a new user sees.
- **D-16:** "Setup acknowledged" persists alongside `runtime_health` in `<data_dir>/config.json`, not in WebEngine `localStorage`. The existing guided-tour flag (`lecturepack.guided-tour.seen.v1`) is in localStorage and therefore dies with the WebEngine profile — the setup flag must survive that.
- **D-17:** The demo is offered only after the user continues past the checklist or deliberately skips it. Existing demo isolation guarantees (DEMO-04, DEMO-05) are untouched.

**Single instance and icon**
- **D-18:** A second launch raises and focuses the existing window rather than exiting silently — silent exit is indistinguishable from a failed launch, which is what prompted the owner's repeated clicking.
- **D-19:** The guard runs **before** `RuntimeBootstrapService.assess()`. A guard placed after it would let a second process sit invisible for up to 90s, which is the exact symptom being fixed.
- **D-20:** The blank taskbar icon has two candidate causes and the phase must determine which before fixing: (a) no `SetCurrentProcessExplicitAppUserModelID` call exists anywhere in `app/`, so Windows may not associate the window with the installed exe; and (b) `setWindowIcon` at `app/desktop/main.py:107` is guarded by an `os.path.exists` check with no else-branch, so a missing `.ico` fails silently. The `.ico` *is* present in the built output (17,644 bytes) and *is* stamped into the exe, which makes (a) the stronger suspect — but confirm on the packaged build rather than assuming.
- **D-21:** Whatever the cause, the missing-icon path must stop failing silently.

### Claude's Discretion

- The single-instance mechanism (`QLocalServer`/`QSharedMemory`/named mutex) and its wire format, provided it satisfies D-18 and D-19 and cleans up after a crash.
- Internal helper names, module placement, and test organization matching existing Python and JS conventions.
- The exact visual treatment of the checklist and its progress states, within the existing design language and the beta-5 motion vocabulary preserved by beta-6 Phase 4.
- Whether size cuts are expressed as PyInstaller `excludes`, post-build pruning in `bundle_engine()`, or both — provided the packaged runtime smoke still passes.

### Deferred Ideas (OUT OF SCOPE)

- **Aggressive Qt module allowlist** (~600 MB potential vs ~380 MB from D-01) — rejected for this phase per D-03; revisit if the approved cuts prove insufficient.
- **Trimming `PySide6/resources/`** (102 MB) — not rejected, but gated behind D-04's investigation; may become its own slice.
- **Re-verifying beta-6's Phase 5 claims properly** — the archived milestone's release gate never ran on a physical machine. Broader than this phase; belongs to a beta-7 release gate phase if one is opened.
- Beta-6 deferred items FUTR-01..04 (offline repair import, per-file selection, alternate tour modes, reduced-motion preference) remain deferred.
</user_constraints>

<phase_requirements>
## Phase Requirements

No `REQUIREMENTS.md` IDs are mapped to this phase (it is confirmed "TBD in ROADMAP" — beta-7's `REQUIREMENTS.md` has not yet been authored; the beta-6 `REQUIREMENTS.md` in `.planning/REQUIREMENTS.md` is a different, already-shipped milestone and does not cover this phase). The authoritative acceptance criteria for this phase are the six numbered Success Criteria in `ROADMAP.md` under "Phase 1: Clean-Device Footprint & First Launch." This research maps each of those instead of REQ-IDs:

| Success Criterion | Research Support |
|---|---|
| 1. Installer/installed size measured and discrepancy resolved | See "The Measurement Discrepancy" below — exact command sequence, what a fresh build requires, and why the existing `app/dist/LecturePack/` tree in this worktree is usable evidence for the "before" state but not a substitute for a clean rebuild. |
| 2. `ggml-base.en.bin` once; `translations/`, `qml/`, Quick/Quick3D, `Qt6Pdf.dll` absent; packaged smoke still passes | See "Size Cuts — The Mechanism" and "Model Dedupe" below. |
| 3. Cold/warm launch visible in seconds, honest itemized progress | See "Startup" below. |
| 4. Single instance raises existing window before slow validation | See "Single Instance" below. |
| 5. Setup checklist before demo offer, no re-download of bundled components | See "First-Run Checklist" below. |
| 6. Icon in window/taskbar | See "Taskbar Icon" below. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Prefer `code-review-graph` MCP tools** over Grep/Glob/Read for codebase exploration. Those MCP tools were not present in this session's toolset; all exploration below fell back to Grep/Read/Bash per the documented fallback rule. The planner should invoke `code-review-graph` directly where available.
- **Read `BUG_LIST.md` during session start**, and check the relevant entry before touching a historically bug-prone area. BUG-04, BUG-07, and BUG-15 are the referenced entries for this phase (see "Common Pitfalls" below for what they establish).
- `AGENTS.md` phase discipline applies: one phase at a time, no unapproved dependencies, real `pytest` output required before claiming completion, no `git reset --hard`/force operations, dedicated branch, task restatement (authorized phase / exact goal / permitted files / required tests / non-goals / required evidence) before any implementation request.

## Summary

This phase fixes five defects the owner found on a clean device after beta-6 was certified complete. All five root causes are already established with file:line citations in `01-CONTEXT.md`; this research verifies those citations against the actual code and the actual (existing, unrebuilt) `app/dist/LecturePack/` tree in this worktree, and answers the specific mechanism questions CONTEXT.md left open.

The single highest-value finding: **the current `lecturepack.spec` already contains `excludes=["tkinter", "PySide6.QtQuick3D", "PySide6.Qt3DCore"]` (line 87) and has since the file's first commit — yet the on-disk `app/dist/LecturePack/_internal/PySide6/` tree in this worktree (built 2026-07-29, matching CONTEXT.md's measured 538 MB/1.9 GB figures exactly) still contains `Qt63DCore.dll`, `Qt6Quick3D.dll`, `Qt6Quick3DRuntimeRender.dll`, the full `qml/` tree, `Qt6Charts.dll`, `Qt6DataVisualization.dll`, and dozens more Qt add-on DLLs the app never uses.** This is direct, in-repo, empirical proof — not inference — that PyInstaller `Analysis.excludes` cannot remove these components: `excludes` blocks *Python-importable modules* from the module graph, but `Qt6WebEngineCore.dll`/`Qt6WebEngineWidgets.dll` pull in `Qt6Quick.dll` and `Qt6Qml.dll` as genuine native link-time dependencies (confirmed by reading PyInstaller's own `PySide6` Qt hook machinery), and DLLs with no Python-module counterpart at all (like `Qt6Quick3DRuntimeRender.dll`) can never be named in `excludes` in the first place. **The only viable lever is post-build pruning inside/after `bundle_engine()`, not `excludes`.** This directly answers Research Priority 2 and confirms the correct discretion choice under D-01's "excludes, post-build pruning, or both."

A second, unrequested but significant finding for D-04's `resources/` investigation: of the 102 MB `PySide6/resources/` folder, **73 MB is `qtwebengine_devtools_resources.debug.pak`** alone, plus smaller `.debug.pak`/`.debug.bin` siblings (~78 MB total) that Qt's own documentation confirms are the **Debug**-build counterparts of the Release `.pak`/`.bin` files this build actually uses (`icudtl.dat`, `qtwebengine_resources*.pak`, `v8_context_snapshot.bin`). Since this PyInstaller build only ships Release Qt6 DLLs (no `d`-suffixed debug DLL exists anywhere in the tree), the `.debug.*` variants are provably dead weight — larger than the entire D-01 Qt cut list combined.

The model-dedupe question (D-05) resolves cleanly by reading `engine_adapter.py`: `_bundled_demo_model_path()` already tries the `_internal/models/` copy first and **falls through to the canonical `resource_dir/models/ggml-base.en.bin` path** (the same path `RuntimeBootstrapService`/`bundle_engine()` use) if the first candidate is absent. No new resolution logic is needed — only removing the `datas` duplication in `lecturepack.spec:66-69`, with a new test proving the fallback actually reaches the survivor.

The taskbar-icon root cause (D-20) is confirmable in-repo with HIGH confidence: `SetCurrentProcessExplicitAppUserModelID` appears nowhere under `app/`, matching a well-documented Windows/PyInstaller/Qt failure mode (cited from Microsoft Learn and practitioner guides below) where a frozen exe's taskbar icon renders blank/generic without this call, regardless of `setWindowIcon()`.

The updater regression is confirmed byte-for-byte via `git diff f3d713d HEAD -- .github/workflows/release.yml`: the old workflow ran `choco install innosetup` + `python packaging/build.py` and published `Setup.exe`/`Portable.zip`/`SHA256SUMS.txt`; the current workflow runs `build.py --no-installer` and publishes exactly six signed runtime component assets. `update_service.py`'s `select_asset()` requires the exact installer/portable + SHA256SUMS names and will raise `ValueError` against every release the current workflow produces.

**Primary recommendation:** Do the size cuts as post-build pruning in `bundle_engine()` (not `excludes`), extend that pruning to the `.debug.*` resource files after confirming their non-use, dedupe the model by deleting the spec `datas` entry (not adding new resolution code), fix startup by moving a single-instance guard to the very top of `main()` before `Backend()` construction and refactoring `Backend.__init__`'s validation to run after `show()` with progress signals over the existing `get_bootstrap()`/bridge transport, call `SetCurrentProcessExplicitAppUserModelID` as the first statement in `main()` with a matching Inno Setup `AppUserModelID`, and surface the updater-regression tradeoff to the owner rather than deciding it inside this phase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Package size (PyInstaller collection, Qt module pruning) | Build/Packaging | — | Entirely a build-time artifact-composition concern (`lecturepack.spec`, `build.py`); no runtime code owns it. |
| Startup validation ordering & progress | Desktop Shell (Backend/MainWindow) | Engine/Services (`RuntimeBootstrapService`) | `Backend.__init__` (shell) currently owns *when* validation runs; `RuntimeBootstrapService` (service layer) owns *what* validation checks. Sequencing fix belongs in the shell; probe parallelization belongs in the service. |
| Single-instance guard | Desktop Shell (`main.py`) | OS Integration (`win_integration.py` pattern) | Must run before any `Backend`/window construction — this is shell-level process bootstrap, not an engine concern. The existing hand-rolled ctypes pattern in `win_integration.py` is the established in-repo precedent for OS-level Windows APIs. |
| Taskbar icon / AppUserModelID | Desktop Shell (`main.py`) + Installer (`lecturepack.iss`) | — | The AUMID must be set process-side (before `QApplication`) AND matched shortcut-side (Inno Setup `[Icons]`) — a single-tier fix is insufficient. |
| First-run setup checklist | Frontend UI (`app/ui/app.js`, WebEngine) | Backend bridge (`bridge.py`, `ConfigManager`) | Per existing pattern ("the gate is decided in Python before the UI asks"), the *routing decision* (show checklist vs. skip) is a bridge/config-layer fact; the UI only renders the verdict. The new "setup acknowledged" flag is a config-layer (persisted) concern, not a UI-layer (localStorage) one — this is explicit in D-16. |
| Model dedupe / resolution | Build/Packaging (spec `datas`) | Desktop Shell (`engine_adapter.py` resolution chain) | The *file placement* is a packaging concern; the *resolution order* that finds the surviving copy is already shell-layer code and needs no change, only a verifying test. |
| Updater asset contract | CI/Release (`.github/workflows/release.yml`) | Desktop Shell (`update_service.py`) | The workflow publishes assets; the shell's `expected_asset_names()`/`select_asset()` consume them. Fixing one without the other leaves a mismatch — this is why the decision must be explicit, not implicit. |

## Standard Stack

This phase does not introduce new external dependencies. It changes how already-approved tooling is used.

### Core (already present, versions verified in this environment)

| Tool | Version | Purpose | Why Standard |
|---|---|---|---|
| PyInstaller | 6.21.0 installed (repo pins `>=6.3` in `app/requirements-build.txt:2`) `[VERIFIED: pip/local install]` | Freezes the app into `dist/LecturePack/` onedir | Already the project's packaging tool; changing tools is out of scope and would violate `AGENTS.md`'s "do not silently replace the selected technology stack." |
| PySide6 | 6.11.1 installed (repo pins `>=6.7.0` in `app/requirements.txt:8`) `[VERIFIED: pip/local install]` | Qt6 bindings, WebEngine host | Same as above. |
| Inno Setup 6 | Installed at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` `[VERIFIED: file exists, confirmed in 01-CONTEXT.md's corrected open_measurement section]` | Produces `Setup.exe` | Already wired via `_find_iscc()` (`build.py:275-286`); no alternative installer tool is in scope. |
| `ctypes` (stdlib) | N/A | `SetCurrentProcessExplicitAppUserModelID` call, single-instance primitives if a named-mutex approach is chosen | Zero new dependency; `win_integration.py` already hand-rolls `ITaskbarList3` via ctypes for exactly this reason ("no new dependency… comtypes/pywin32 are PyInstaller hazards" — `win_integration.py:93-95`). |
| `PySide6.QtNetwork` (`QLocalServer`/`QLocalSocket`) or `PySide6.QtCore` (`QSharedMemory`) | Already bundled | Single-instance IPC primitive | Both ship in the PySide6 wheel already collected by the spec; no new binary weight. |

### Supporting

| Library | Version | Purpose | When to Use |
|---|---|---|---|
| `comtypes` | Not installed; referenced only defensively in `win_integration.py:109` (`try: import comtypes.client`) | ITaskbarList3 COM activation | Already optional/no-op if absent — do not add as a hard dependency for this phase's icon fix; the AUMID fix needs only `ctypes.windll.shell32`. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Post-build pruning in `bundle_engine()` | A hand-written custom PyInstaller hook overriding `hook-PySide6.QtWebEngineCore.py` | Rejected: overriding a third-party hook is fragile across PySide6/PyInstaller version bumps and duplicates logic already correctly expressed as "these files exist after COLLECT; delete them." Post-build deletion is simpler, more auditable, and matches the discretion CONTEXT.md already grants. |
| `QLocalServer`/`QLocalSocket` for single instance | `QSharedMemory` lock, or a raw Windows named mutex via `ctypes.windll.kernel32.CreateMutexW` | See "Single Instance" section below for the full comparison; `QLocalServer` is recommended because it is the only one of the three that also gives the second process a channel to ask the first process to raise/focus (the other two only detect duplication, they don't communicate). |
| Restoring installer publication inside this phase | A separate, later slice | See "Updater Regression" section — this is a decision to surface to the owner, not one this research makes. |

**Installation:** None required — no new packages.

**Version verification:** `pip show pyinstaller` / `pip show PySide6` in the environment used to actually build should be re-run at build time, since this session's verification used the globally installed interpreter (`C:\Users\marsh\AppData\Local\Programs\Python\Python312`), not necessarily the exact interpreter/venv `build.py` will be invoked from. `[VERIFIED: local environment, not yet confirmed against the project's actual build venv]`

## Package Legitimacy Audit

**Not applicable.** This phase adds zero new external packages (npm/PyPI/crates or otherwise). All work uses already-approved, already-installed dependencies (`PyInstaller`, `PySide6`, Inno Setup, stdlib `ctypes`) or removes bundled files. The Package Legitimacy Gate protocol is skipped per its own trigger condition ("whenever this phase installs external packages").

**Packages removed due to [SLOP] verdict:** none (N/A — no packages evaluated)
**Packages flagged as suspicious [SUS]:** none (N/A)

## Architecture Patterns

### System Architecture Diagram — current (defective) startup flow

```
[User double-clicks LecturePack.exe / Start Menu shortcut]
            │
            ▼
   main.py: main()
     - register_asset_scheme()
     - QApplication(sys.argv)
            │
            ▼
   MainWindow.__init__()
            │
            ├── setWindowIcon() from icon_path (guarded, no else — D-20b)
            │
            ▼
   self.backend = Backend(self)      ◄── BLOCKS HERE, nothing on screen
            │
            ▼
   Backend.__init__()
     - RuntimeBootstrapService(config).assess()   [bridge.py:119]
            │
            ▼
   RuntimeBootstrapService.assess()
     - _requires_full() → True on fresh profile [runtime_bootstrap.py:110]
            │
            ▼
   _validate_full(paths)                          [runtime_bootstrap.py:128]
     - ffmpeg -version        (bounded 30s)
     - ffprobe -version       (bounded 30s)
     - whisper-cli.exe staged transcription (bounded 30s)
       worst case: ~90s of subprocess work, UI thread blocked, no window
            │
            ▼
   Backend.__init__() returns → MainWindow.__init__() continues
            │
            ▼
   self.view.load(index.html) → win.show_when_ready() → window finally appears
            │
            ▼
   JS boot(): lpBridge.get_bootstrap() → RuntimeSetupGate.admit(bootstrap)
     - if HEALTHY and no active repair op: setUnderlyingInert(false); RETURN
       (checklist never renders — this is the "failure gate" behavior, D-11)
            │
            ▼
   syncDemoAdmission() → demo offer becomes available immediately
```

### System Architecture Diagram — target flow after this phase

```
[User double-clicks LecturePack.exe]
            │
            ▼
   main.py: main()
     - SetCurrentProcessExplicitAppUserModelID(AUMID)   ◄── FIRST statement (D-20/21)
     - register_asset_scheme()
     - single-instance guard (QLocalServer probe)        ◄── BEFORE Backend() (D-19)
       ├── if another instance owns the socket: send "raise", exit immediately
       └── else: claim the socket, continue
     - QApplication(sys.argv)
            │
            ▼
   MainWindow.__init__()  → window constructed, SHOWN EARLY (before validation)
            │
            ▼
   Backend.__init__()  → constructs WITHOUT calling assess() synchronously
            │
            ▼
   window.show()                                         ◄── visible within seconds (D-08)
            │
            ▼
   Backend kicks off assess() on a worker thread/QThread, emitting
   itemized progress signals over the existing bridge signal pattern
   (get_bootstrap()/new progress signal) → JS renders
   "Checking FFmpeg…" / "Checking Whisper runtime…" (D-09)
            │
            ▼
   assess() completes → HEALTHY + first-ever-launch flag not yet acknowledged
            │
            ▼
   JS: RuntimeSetupGate renders the NEW first-run checklist
     (Ready / Needs Attention per D-13 item) — Continue or Skip (D-12)
            │
            ▼
   ConfigManager.persist_setup_acknowledged() (D-16, alongside runtime_health)
            │
            ▼
   Demo offer becomes available (unchanged DEMO-04/05 isolation)
```

### Recommended Project Structure

No new top-level directories. Changes land in existing files:
```
app/desktop/main.py             # AUMID call, single-instance guard, window-first ordering
app/desktop/bridge.py           # Backend.__init__ validation deferred off the constructor
app/packaging/build.py          # bundle_engine() gains post-build pruning + spec datas fix
app/packaging/lecturepack.spec  # remove demo_model_datas duplicate entry (keep the build-time existence check)
app/packaging/lecturepack.iss   # AppUserModelID on [Icons] entries
app/ui/app.js                   # RuntimeSetupGate extended for the first-run checklist state
lecturepack/infrastructure/config_manager.py   # persist_setup_acknowledged() alongside persist_runtime_health()
lecturepack/services/runtime_bootstrap.py      # optional: parallelize the three independent probes (D-10)
tests/test_runtime_packaged_smoke.py           # extend for post-cut packaged smoke
tests/test_beta3_packaging.py                  # extend clean-state gate assertions for absent translations/qml/Pdf
```

### Pattern 1: Post-build pruning instead of PyInstaller excludes
**What:** After `PyInstaller.__main__.run([...lecturepack.spec...])` completes and `bundle_engine()` copies the engine payload, delete `_internal/PySide6/translations/`, `_internal/PySide6/qml/`, `Qt6Qml.dll`, `Qt6Quick.dll`, `Qt6Quick3DRuntimeRender.dll`, and `Qt6Pdf.dll` from the collected onedir tree, before `validate_clean_state()`/`make_portable_zip()` run.
**When to use:** Any Qt6/PySide6 component that (a) is a native DLL with no corresponding importable Python module (cannot be named in `excludes` at all), or (b) is pulled in as a genuine native link-time dependency of a module the app *does* need (WebEngine needs `Qt6Quick.dll`/`Qt6Qml.dll` internally; `excludes` cannot separate "the DLL PyInstaller must load to satisfy WebEngineCore's link table" from "the DLL a Python import would pull in").
**Example:**
```python
# Source: verified against PyInstaller/utils/hooks/qt/__init__.py in the local
# environment (site-packages) — collect_module() walks the PE import table of
# every already-included Qt binary and adds any linked Qt shared library that
# HAS an associated python module to hiddenimports, recursively. It special-
# cases only qt5qml/qt6qml (skipping it unless the analyzed module IS
# QtQml/QtQuick) to avoid double-collecting the full QtQml tree — but it does
# NOT skip qt6quick, qt6quick3d, qt6pdf, or any Qt add-on library, and DLLs
# with NO associated python module (e.g. Qt6Quick3DRuntimeRender.dll) have no
# name that `excludes` could ever target.
#
# Empirical proof from this repo (app/dist/LecturePack/_internal/PySide6/),
# built 2026-07-29, WITH excludes=["tkinter","PySide6.QtQuick3D","PySide6.Qt3DCore"]
# already present in lecturepack.spec since its first commit (6c76fe3):
#   Qt63DCore.dll, Qt6Quick3D.dll, Qt6Quick3DRuntimeRender.dll, and the whole
#   qml/ tree are STILL PRESENT despite being named (or a sibling of a named
#   module) in excludes.
def prune_unused_qt_components(dist_app: Path) -> None:
    pyside6 = dist_app / "_internal" / "PySide6"
    for rel in ("translations", "qml"):
        target = pyside6 / rel
        if target.exists():
            shutil.rmtree(target)
    for dll in ("Qt6Qml.dll", "Qt6Quick.dll", "Qt6Quick3DRuntimeRender.dll", "Qt6Pdf.dll"):
        target = pyside6 / dll
        if target.exists():
            target.unlink()
```
**Verification gate this pattern needs that the existing packaged smoke does NOT provide:** `tests/test_runtime_packaged_smoke.py` only exercises the offline FFmpeg/ffprobe/Whisper CLI subprocess path — it never launches `QWebEngineView`. Deleting `Qt6Quick.dll`/`Qt6Qml.dll` (which WebEngineCore's native link table references) risks breaking WebEngine's internal compositor at the binary-load level, which nothing currently automated would catch. See "Common Pitfalls" and "Validation Architecture" below — this must be verified with an actual packaged GUI launch showing rendered WebEngine content, not just the FFmpeg/Whisper smoke passing.

### Pattern 2: Deferred bootstrap assessment with progress transport
**What:** Move `RuntimeBootstrapService(...).assess()` out of `Backend.__init__` (called synchronously before the window shows) into a method invoked after `window.show()`, running on a worker thread (`QThread` or Python `threading.Thread` + `QTimer.singleShot(0, self, ...)` marshalling per the established pattern — see BUG-09 in "Common Pitfalls"), emitting a new progress signal per probe.
**When to use:** Any first-run/cold-start validation sequence where the UI must be visible before slow work starts.
**Example:**
```python
# Source: existing pattern already in this repo, engine_adapter.py / bridge.py —
# Qt signals crossing a worker-thread boundary MUST be marshalled onto the
# main thread via a QObject context (see BUG-09 in BUG_LIST.md: a bare
# QTimer.singleShot(0, fn) from a plain threading.Thread silently never fires
# because the timer starts in the CALLING thread, not the main thread).
class Backend(QObject):
    def __init__(self, window):
        super().__init__()
        ...
        # do NOT call assess() here anymore
        self._start_bootstrap_async()

    def _start_bootstrap_async(self):
        def worker():
            for name, probe in ordered_probes:
                self.bootstrap_progress.emit(json.dumps({"component": name, "state": "checking"}))
                # ... run probe ...
            result = RuntimeBootstrapService(self._runtime_config).assess()
            QTimer.singleShot(0, self, lambda: self._on_bootstrap_complete(result))
        threading.Thread(target=worker, daemon=True).start()
```
**Constraint from D-10:** the three probes inside `_validate_full()` (`runtime_bootstrap.py:146-174`) — ffmpeg `-version`, ffprobe `-version`, and the staged whisper-cli transcription — are independent of each other (none consumes another's output) and can be parallelized with a thread pool inside `_validate_full()` itself; this is a *service-layer* change (not shell-layer) and is separate from the shell-layer "move assess() off the constructor" change above. Both are needed per D-08.

### Anti-Patterns to Avoid
- **Do not add a splash screen** to cover the validation delay — explicitly ruled out by the phase's cross-cutting constraints and by the owner's stated rejection of concealment.
- **Do not replace the real staged whisper-cli transcription with a lighter liveness check** to make startup faster (D-10) — this destroys the actual evidence AD-18's staging boundary and the runtime admission contract depend on.
- **Do not rely on `excludes` for any future Qt trimming** — proven ineffective in this repo for native-linked or module-less Qt binaries (see Pattern 1). Any future Qt cut must be verified against the actual post-COLLECT tree, not assumed from the spec's `excludes` list.
- **Do not treat the existing packaged smoke test passing as proof the app still works after Qt DLL removal** — it does not exercise WebEngine at all (see Pattern 1's verification gate and "Validation Architecture" below).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Single-instance detection + IPC to the running instance | A custom lock-file + polling scheme | `QLocalServer`/`QLocalSocket` (already in the PySide6 wheel) | Handles stale-socket cleanup, is already a dependency, and gives a message channel for "raise and focus" that a bare file lock or mutex does not. |
| AppUserModelID / taskbar identity | Reverse-engineering Windows shell registration by trial and error | `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID` (documented Win32 API) + Inno Setup's built-in `AppUserModelID` `[Icons]` parameter | Both are the sanctioned, documented mechanism (Microsoft Learn, Inno Setup docs) — no custom registry-key writing needed. |
| Determining which Qt DLLs a WebEngine app truly needs at runtime | Guessing from file names or deleting until it breaks | Reading PyInstaller's own `PyInstaller/utils/hooks/qt/__init__.py` `collect_module()` dependency walk (already done in this research) + verifying post-cut with an actual packaged GUI launch | The mechanism is fully documented in PyInstaller's own source; empirical delete-and-pray risks silently breaking WebEngine's internal compositor since nothing currently automated launches the GUI. |
| Progress-per-component UI during bootstrap | A new bespoke overlay/signal channel | Extend the existing `#runtime-setup-overlay`/`RuntimeSetupGateModel` and `Backend.get_bootstrap()` transport (D-15, already re-used for the setup checklist) | The codebase already has a working backend-decides/UI-renders pattern for exactly this kind of per-component status; a parallel channel would violate the established "gate is decided in Python before the UI asks" convention noted in `01-CONTEXT.md`'s `<code_context>`. |

**Key insight:** every one of this phase's five defects already has an established, in-repo mechanism it should extend (the WebEngine overlay, the ctypes OS-integration pattern, the canonical runtime inventory, the worker-thread-to-main-thread marshalling pattern) — the risk in this phase is inventing a parallel mechanism instead of extending the existing one, which is exactly the class of mistake BUG_LIST.md's cross-cutting lesson #2 ("a single global keydown handler needs a modal-state concept... keep it centralised") warns about.

## Common Pitfalls

### Pitfall 1: Verifying the packaged smoke test is not verifying the packaged GUI
**What goes wrong:** Success Criterion 2 says "Offline processing... still passes the packaged runtime smoke" — but `tests/test_runtime_packaged_smoke.py` and `test_beta3_packaging.py` never construct a `QApplication` or load `QWebEngineView`. A build that passes every existing automated test could still ship a WebEngine window that fails to render (blank/crashed) if `Qt6Quick.dll`/`Qt6Qml.dll` removal breaks WebEngineCore's internal compositor.
**Why it happens:** The smoke tests were built for the *offline processing* runtime contract (AD-18/AD-19's concern), which predates this phase's Qt-trimming work and was never designed to catch a WebEngine rendering regression.
**How to avoid:** Treat "one packaged clean-profile launch with the icon visible" (the evidence gate) as also requiring **visible rendered WebEngine content**, not just an icon and a non-crashed process. Add this as an explicit, separately-called-out verification step in the plan, not folded silently into the existing smoke test's scope.
**Warning signs:** A build that silently fails to load `Qt6WebEngineCore.dll` at process start typically manifests as an immediate crash-on-launch or a permanently blank/white `QWebEngineView` — both are easy to miss if the plan only checks "process exit code 0" instead of actually observing the window.

### Pitfall 2: Design-time placeholder content and empty-state ownership (BUG-04, BUG-07, BUG-15)
**What goes wrong:** `app/ui/index.html` and `app.js` ship real default values/content for every visible element (it's a static-mockup-first architecture), so any NEW UI surface (the first-run checklist) that doesn't explicitly own its empty/loading/ready states will either show stale demo content or leak "?preview=1" seed data.
**Why it happens:** BUG-07 (fixed) shows the demo-jobs seed is opt-in behind `?preview=1` specifically because it is "one bridge-failure away from being user-visible." BUG-15 (fixed) shows that even after gating one data source, sibling literals (`pipeline`/`slides`/`transcript`/`study`) can remain live and leak fabricated content into a fresh, empty profile. BUG-04 (fixed) shows hardcoded idle-state markup with **no JS writer at all** for some ids (`storage-label`, `proc-source-name`) shipped for months undetected.
**How to avoid:** For every new element the first-run checklist introduces, grep `app.js` to confirm there is an actual writer (not just markup with a plausible-looking default), and decide its empty/loading/Ready/Needs-Attention state explicitly before implementation, per BUG_LIST.md's cross-cutting lesson #1.
**Warning signs:** Any checklist item whose "Ready" or "Needs Attention" text renders correctly in a live-bridge dev session but was never tested against a truly fresh profile with zero prior `config.json`.

### Pitfall 3: Assuming the existing `dist/LecturePack/` tree in this worktree is safe to reuse as the "after" measurement
**What goes wrong:** The tree currently on disk (`app/dist/LecturePack/`, built 2026-07-29 23:01, matching CONTEXT.md's 538 MB/1.9 GB figures) is a legitimate, current-spec build and is useful as the verified "before" baseline (see "The Measurement Discrepancy" below) — but it must **not** be reused as the post-cut "after" measurement. Any pruning step this phase adds needs a genuinely fresh `python packaging/build.py` run afterward, in the same sitting, to produce comparable before/after numbers on freshly built trees.
**Why it happens:** `build.py`'s `main()` already does `shutil.rmtree(APP_DIR / d)` for `build`/`dist` at the very start of every invocation (`build.py:503-504`), so the existing tree IS the result of the last full run — but a plan that measures "before" from this tree and "after" from a differently-configured or partial rebuild would not be comparing like-for-like.
**How to avoid:** The plan should do one clean `python packaging/build.py` run before the cuts (or reuse this exact evidenced tree as "before," since it is confirmed current-spec) and exactly one more full clean run after the cuts land, in the same sitting, per the `<open_measurement>` mandate in CONTEXT.md.
**Warning signs:** Mixing numbers from different build dates/commits without re-verifying they used the identical spec and identical `excludes`/pruning code.

### Pitfall 4: Single-instance guard placed after any slow work
**What goes wrong:** D-19 explicitly requires the guard to run before `assess()`. If the guard is added inside `MainWindow.__init__` (after `Backend(self)` has already been constructed and already blocked for up to 90s), the exact symptom being fixed (a second click appearing to do nothing for up to 90s) recurs.
**Why it happens:** It is natural to reach for "wire it up in MainWindow" since that's where the window and backend both live — but the guard must run in `main()`, before `MainWindow()` is even constructed.
**How to avoid:** Place the single-instance check as the very first meaningful action in `main()`, before `QApplication(sys.argv)` is even created if possible (a `QLocalSocket` connection attempt does not require a `QApplication` to exist, though `QCoreApplication`/event-loop-free usage needs verification against the exact PySide6 version — flagged as an open question below).

## Code Examples

### AppUserModelID (Windows, ctypes) — confirmed working pattern from multiple independent sources
```python
# Source: pattern corroborated by Microsoft Learn (SetCurrentProcessExplicitAppUserModelID
# function docs) and pythonguis.com's PyInstaller/PyQt packaging guide (both cited in Sources).
# Must run BEFORE any window is presented / before QApplication in practice.
import ctypes
import sys

if sys.platform == "win32":
    APP_USER_MODEL_ID = "LecturePack.LecturePack"  # stable across versions — changing
                                                     # this breaks pinned taskbar/Start icons
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass  # never let OS-integration failure block startup
```

### Inno Setup — matching AppUserModelID on shortcuts
```ini
; Source: jrsoftware.org/ishelp/topic_iconssection.htm ([Icons] section reference,
; "AppUserModelID" parameter) — must match the string passed to
; SetCurrentProcessExplicitAppUserModelID for correct taskbar/Start grouping.
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "LecturePack.LecturePack"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "LecturePack.LecturePack"
```

### Model dedupe — verified fallback chain (no new code needed, only removing the duplicate)
```python
# Source: app/desktop/engine_adapter.py:1374-1389, read directly in this session.
# Candidate 1 (app_root()/models/... == _internal/models/...) is the PyInstaller
# `datas` duplicate from lecturepack.spec:66-69. Candidates 2/3 already resolve to
# config.resource_dir == os.path.dirname(sys.executable) (config_manager.py:24-28),
# i.e. the SAME top-level models/ggml-base.en.bin that bundle_engine() (build.py:373-410)
# and RuntimeBootstrapService/canonical_inventory (runtime_inventory.py:10) already use.
def _bundled_demo_model_path(self, config) -> str:
    candidates = [
        os.path.join(app_root(), "models", self._DEMO_MODEL_FILENAME),          # removed by D-05 fix
        os.path.join(getattr(config, "resource_dir", ""), "models",
                     self._DEMO_MODEL_FILENAME),                                 # survives — canonical
        os.path.join(getattr(self.config, "resource_dir", ""), "models",
                     self._DEMO_MODEL_FILENAME),                                 # survives — canonical
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return ""
```
**Required plan action:** remove `demo_model_datas = [(DEMO_WHISPER_MODEL, "models")]` from `lecturepack.spec:69`'s `datas=` concatenation (keep the build-time existence check at spec:66-68, since `bundle_engine()` still needs the source file to exist at `REPO_ROOT/models/ggml-base.en.bin` to copy it). Add a test asserting `_bundled_demo_model_path()` returns the canonical path when only the top-level copy exists on disk (proving the fallback, not just assuming it — this is what D-05 means by "the resolution logic is the deliverable, not the deletion").

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `excludes=[...]` in `Analysis()` as the presumed lever for Qt bloat removal | Post-build deletion of collected files/DLLs after `COLLECT`/`bundle_engine()` | N/A — this is a correction of an assumption already baked into the current spec (excludes has been present since the spec's first commit and has never worked for this purpose in this repo) | Confirms the plan must implement pruning as a `build.py` step, not a spec tweak. |
| Installer publishing via `choco install innosetup` + `build.py` (full install) in CI | `build.py --no-installer` + six signed runtime component assets, per commit `a6164b1` | beta-6 Phase 2 Plan 05 (already shipped, this repo's current `HEAD`) | Confirmed via `git diff f3d713d HEAD` — the updater's required assets (`Setup.exe`/`Portable.zip`/`SHA256SUMS.txt`) are no longer published by any current workflow run. |

**Deprecated/outdated:** None of the project's own architecture is deprecated by this research; the only "outdated" item is the assumption (visible in the spec's own `excludes` list) that Analysis-level excludes control Qt binary bloat for a WebEngine app — this assumption predates this phase and this research corrects it with direct evidence.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | The single-instance mechanism recommendation (`QLocalServer`) is the best fit; a `QLocalSocket` connection attempt can run before `QApplication` exists in PySide6 6.11 without requiring an event loop. | Single Instance / Pattern 1 diagrams | If a `QLocalSocket`/`QLocalServer` genuinely requires a running Qt event loop to complete a connection attempt synchronously, the guard may need a small local event loop (`QEventLoop().exec()` scoped to the probe) or a named-mutex (`CreateMutexW`) fallback instead. This is flagged as an Open Question below rather than asserted as fact, since it was not empirically tested in this session (no PySide6 code was executed). |
| A2 | `.debug.pak`/`.debug.bin` files in `PySide6/resources/` are never loaded because this build ships only Release Qt6 DLLs (no `d`-suffixed debug DLL exists in the tree). | Summary / Priority 4 (`resources/`) | If Qt WebEngine selects debug resources by some mechanism other than DLL debug/release pairing (e.g., an env var, a build-time compile flag baked into the Release DLL itself) rather than purely by which DLL variant loaded, removing `.debug.*` could break DevTools or a v8-snapshot fallback path. Qt's own docs (cited) confirm the debug/release *naming* convention but this session did not find an authoritative statement that Release Qt6WebEngineCore.dll can *never* reference the `.debug.*` files under any code path (e.g. via `QTWEBENGINE_CHROMIUM_FLAGS=--enable-logging=stderr` or similar debug flags a user could set). Recommend the plan verify with a packaged launch (DevTools panel open, if reachable) before deleting, not just delete-on-faith. |
| A3 | `Qt6WebEngineCore.dll`/`Qt6WebEngineWidgets.dll` link natively to `Qt6Quick.dll`/`Qt6Qml.dll` at the PE-import-table level (rather than loading them dynamically via `LoadLibrary` at runtime only when a QML-based API path is exercised). | Pattern 1 / Common Pitfall 1 | This claim is corroborated by a WebSearch citation (PyInstaller's own hook comment about "extension modules linked against libQt5Qml/libQt6Qml... pulls in the whole QtQml module") but this session did not run `dumpbin /imports` (or equivalent) directly against `Qt6WebEngineCore.dll` in this repo's tree to confirm the exact import-table entries. If the link is actually a soft/delay-load or runtime `LoadLibrary` rather than a hard PE import, removing the DLLs might fail more gracefully (feature-degrade) or might fail identically (hard crash) — either way, the plan's verification step (actually launching packaged WebEngine) is the correct mitigation regardless of which mechanism is true. |
| A4 | The recommended AppUserModelID string format (`"LecturePack.LecturePack"`) is a reasonable, Microsoft-convention-following value; the *exact* string chosen doesn't matter functionally as long as it is stable and matches between `main.py` and `lecturepack.iss`. | Code Examples / Taskbar Icon | If a different AUMID convention is required for Windows Store/MSIX-style packaging in the future, this string might need to change — but per-user Inno Setup installs (the current distribution model, `PrivilegesRequired=lowest`) have no such constraint. Low risk. |

**If this table is empty:** N/A — see entries above.

## Open Questions

1. **Does a `QLocalSocket` connection probe work before `QApplication` is constructed, or does it need a running Qt event loop?**
   - What we know: `QLocalServer`/`QLocalSocket` are Qt objects; typical PySide6/PyQt single-instance recipes construct `QApplication` first, then immediately probe a `QLocalSocket` synchronously with `waitForConnected(timeout)`, which does NOT require an already-running `app.exec()` event loop (per widely-documented Qt single-instance patterns) — but this was not verified against this repo's exact PySide6 6.11.1 build in this session.
   - What's unclear: whether `QApplication` itself must exist first (it likely must, since `QLocalSocket` is a `QObject` requiring `QCoreApplication` machinery), which would mean the guard runs immediately after `QApplication(sys.argv)` but still before `MainWindow()`/`Backend()` construction — this ordering still satisfies D-19.
   - Recommendation: the plan should place `QApplication(sys.argv)` construction, then the single-instance probe, then `MainWindow()` — verify empirically during implementation with a quick two-process manual test before committing to the final ordering in code.

2. **What is the exact, current byte-for-byte size of a freshly built `Setup.exe` and its expanded install footprint, post-cuts?**
   - What we know: the portable ZIP is 841.2 MB and the current (pre-cut, but current-spec) installed tree is 1.9 GB (measured directly in this session from the existing `app/dist/LecturePack/` tree, matching CONTEXT.md's figures exactly). No `Setup.exe` currently exists in `app/dist/installer/` in this worktree (only the portable ZIP and SHA256SUMS from the last `--no-installer` CI-style run).
   - What's unclear: the owner's reported ~800 MB/~900 MB figures still are not fully reconciled against the measured 841 MB ZIP / 1.9 GB installed — CONTEXT.md's `<open_measurement>` section explicitly defers this to a fresh, single-sitting build+measure, which this research does not perform (per this task's explicit constraint not to run a full build).
   - Recommendation: the plan's first task should be exactly the sequence in "The Measurement Discrepancy" below — a clean `python packaging/build.py` (no `--no-installer`) run, then measuring the resulting `Setup.exe` size, silently expanding it (`{iss}/{app.exe} /VERYSILENT /DIR=<throwaway>` or `/SP-` extraction to a scratch directory), and diffing that against the onedir tree size, all in one sitting.

3. **Does removing `.debug.pak`/`.debug.bin` from `PySide6/resources/` actually break anything reachable in this app (e.g., a user-triggered DevTools shortcut)?**
   - What we know: Qt's own docs confirm `.debug.*` files are the debug-build counterparts, and this build ships only Release DLLs.
   - What's unclear: whether any code path in `app/desktop/` ever sets a Qt WebEngine debug/DevTools flag (e.g., `QTWEBENGINE_REMOTE_DEBUGGING`) that might reference these files regardless of DLL flavor. A quick grep of `app/desktop/` for `QTWEBENGINE_` env vars found none in this session, but this should be re-confirmed by the planner before deleting.
   - Recommendation: grep `app/` for `QTWEBENGINE_REMOTE_DEBUGGING`/`QTWEBENGINE_CHROMIUM_FLAGS` as a cheap pre-flight check; if none found (as this session's spot-check suggests), proceed with removal and verify via a packaged launch.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Python | Build script (`build.py`), local exploration | ✓ | 3.12.3 `[VERIFIED]` | — |
| PyInstaller | Freeze step | ✓ | 6.21.0 `[VERIFIED]` (repo pins `>=6.3`) | — |
| PySide6 | Qt bindings/WebEngine | ✓ | 6.11.1 `[VERIFIED]` (repo pins `>=6.7.0`) | — |
| Inno Setup 6 (ISCC.exe) | `Setup.exe` production | ✓ | Found at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`, 1.4 MB `[VERIFIED: file exists, per 01-CONTEXT.md's corrected finding]` | `_find_iscc()` already probes this exact path (`build.py:275-286`); no PATH dependency. |
| `ffmpeg.exe`/`ffprobe.exe`/`whisper-cli.exe` source binaries | `bundle_engine()`/packaged smoke | ✓ (present in `repo/bin/`, confirmed via the existing `app/dist/LecturePack/bin/` tree) | — | `ensure_bundled_engine_binaries()` (`build.py:460-491`) downloads from the beta-5 GitHub release if absent. |
| `models/ggml-base.en.bin` source file | Demo bundling, dedupe fix | ✓ (present at `REPO_ROOT/models/ggml-base.en.bin`, 147,964,211 bytes, confirmed both as source and as the two current copies in `app/dist/LecturePack/`) | — | `ensure_demo_whisper_model()` (`build.py:445-457`) downloads from HuggingFace if absent. |
| A genuinely clean Windows profile/VM for cold-launch measurement | Success Criteria 3, 5, 6 | Unknown — not established in this session | — | This is the one dependency this research cannot verify from the codebase; the plan must confirm access to a disposable/clean Windows profile (or full VM) before claiming the cold-launch and taskbar-icon evidence gates. |

**Missing dependencies with no fallback:**
- A genuinely clean Windows user profile (or VM snapshot) for the cold-launch, single-instance, first-run-checklist, and taskbar-icon evidence gates — none of these can be honestly demonstrated on a profile that already has `config.json`/`runtime_health` state from prior runs of this same repo.

**Missing dependencies with fallback:**
- None of the build-time tool dependencies are missing; all have either direct availability or an existing automatic-download fallback already coded into `build.py`.

## Validation Architecture

### Test Framework
| Property | Value |
|---|---|
| Framework | pytest (per `AGENTS.md`'s "provide the actual pytest output" requirement and existing `tests/` layout) |
| Config file | `pytest.ini` at repo root (referenced in BUG_LIST.md BUG-10 re: `QT_QPA_PLATFORM=offscreen`); `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` for headless Qt test runs |
| Quick run command | `pytest tests/test_beta3_packaging.py tests/test_runtime_packaged_smoke.py -x` (packaging-specific subset) |
| Full suite command | `pytest` (repo-root, from `app/` or wherever `pytest.ini` roots it — confirm exact invocation directory during planning; BUG_LIST.md references "677 passed"/"684 tests pass" as recent full-suite baselines) |

### Phase Requirements → Test Map
(Using ROADMAP Success Criteria as the effective requirement IDs, since no `REQUIREMENTS.md` IDs are mapped to this phase yet — see `<phase_requirements>` above.)

| Req (Success Criterion) | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| SC-1 (size measured) | Fresh `Setup.exe` produced; size + expansion measured; contributors listed | manual/scripted measurement, NOT a pytest assertion | `python packaging/build.py` then `du`/`Get-ChildItem -Recurse \| Measure-Object Length -Sum` on the extracted tree | ❌ — no existing test measures artifact size; this is an evidence-gate deliverable, not a unit test |
| SC-2 (`ggml-base.en.bin` once; Qt files absent; packaged smoke passes) | Post-build tree assertions + existing smoke | unit + integration | `pytest tests/test_beta3_packaging.py -k clean_dist` (extend with new assertions for absent `translations/`/`qml/`/`Qt6Pdf.dll`/single model copy) + `pytest tests/test_runtime_packaged_smoke.py` (existing, requires `LECTUREPACK_ONEDIR_FIXTURE`) | 🟡 partially — existing clean-state gate (`check_clean_state`, `build.py:316-360`) needs new assertions added; existing smoke test needs no change but must still pass post-cut |
| SC-2 (WebEngine still renders after Qt cuts) | Packaged GUI actually shows rendered content | manual/physical, NOT currently automated | Launch packaged `LecturePack.exe` on a clean profile, confirm UI paints (screenshot or CDP check) | ❌ Wave 0 gap — no existing automated test launches the real GUI; see Common Pitfall 1 |
| SC-3 (cold/warm launch timing + honest progress) | Window visible in seconds; itemized progress text | manual timing + a driven-app assertion for progress text | Manual stopwatch on a clean profile (cold) and a second launch (warm); optionally a CDP-driven check that `#runtime-setup-overlay`/progress element text updates per component during a real cold run | ❌ Wave 0 gap — no existing test drives a real cold bootstrap and asserts progress text; this is inherently closer to integration/manual than unit |
| SC-4 (single instance raises existing window) | Second launch focuses first instance, no second process | integration (two real process launches) | A new test that spawns the packaged exe twice and asserts only one process survives and the window is focused (Windows-specific, likely manual/physical rather than pytest-automatable in CI) | ❌ Wave 0 gap — new test/tooling needed; likely manual verification given the constraint against sandboxed process/window manipulation in CI |
| SC-5 (setup checklist before demo; no re-download) | Ready/Needs Attention checklist renders on healthy first run before demo offer | Node-side unit test against `RuntimeSetupGateModel` (pure JS reducer, already testable per its own comment "the one mutable lifecycle reducer used by the DOM controller and Node tests") + a Python-side test on the new "setup acknowledged" persistence | 🟡 partially — `RuntimeSetupGateModel` already has a test-friendly design; a new state/transition for "first-run checklist" needs new reducer tests, and `persist_setup_acknowledged()`-equivalent needs a `ConfigManager` test | ❌ Wave 0 gap — new reducer states, new persistence method, no existing tests reference them yet |
| SC-6 (icon in window + taskbar) | Icon renders correctly in title bar and Windows taskbar for the installed build | manual/physical (Windows shell behavior cannot be reliably asserted headlessly) | Launch the installed build, screenshot the taskbar | ❌ — inherently physical; not automatable in CI |

### Sampling Rate
- **Per task commit:** `pytest tests/test_beta3_packaging.py tests/test_runtime_packaged_smoke.py -x` (fast packaging subset) plus any new focused test file for the task just completed.
- **Per wave merge:** full `pytest` suite green (baseline ~677-684 tests per BUG_LIST.md's most recent recorded runs; re-confirm current count during planning).
- **Phase gate:** full suite green AND the four physical/manual evidence artifacts (measured size table, measured cold/warm launch, single-instance two-process proof, packaged clean-profile launch with visible icon + rendered WebEngine content) all captured before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] A new automated (or explicitly manual-with-script-assist) size-measurement step: build `Setup.exe`, extract it to a scratch directory, measure both, diff top contributors — currently nothing in `tests/` does this.
- [ ] Extended `check_clean_state`/`test_beta3_packaging.py` assertions: absent `translations/`, absent `qml/`, absent `Qt6Qml.dll`/`Qt6Quick.dll`/`Qt6Quick3DRuntimeRender.dll`/`Qt6Pdf.dll`, exactly one `ggml-base.en.bin` in the whole tree (currently two).
- [ ] A packaged-GUI-launch verification step (screenshot or CDP-driven) proving WebEngine still renders after the Qt cuts — this is the single most important net-new test-infrastructure gap this research surfaces, since no existing test launches the real window.
- [ ] `RuntimeSetupGateModel` reducer tests for the new first-run-checklist state/transition.
- [ ] A `ConfigManager` test for the new "setup acknowledged" persistence field living alongside `runtime_health` (per D-16).
- [ ] A two-process single-instance integration test (or documented manual procedure, given CI/sandbox constraints on spawning real GUI processes).
- [ ] A test proving `_bundled_demo_model_path()`'s fallback chain reaches the canonical copy once the `_internal/models/` duplicate is removed (per D-05's "resolution logic is the deliverable" instruction).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | no | This phase touches no auth surface. |
| V3 Session Management | no | N/A. |
| V4 Access Control | no | N/A — single-instance guard is a process-liveness concern, not an authorization boundary. |
| V5 Input Validation | marginal | The single-instance IPC channel (whatever message the second process sends the first, e.g. "raise") must be a fixed, minimal, non-parsed sentinel — do not deserialize arbitrary data received on the local socket/pipe from an untrusted local sender. |
| V6 Cryptography | no (this phase) | The signed-repair Ed25519 verifier (AD-19) is explicitly out of scope for this phase's changes; this phase must not touch `release_trust.py`/`runtime_repair.py`'s crypto surface even incidentally. |
| V14 Configuration | yes | The updater-regression finding (`release.yml`) is fundamentally a release-configuration correctness issue — restoring or explicitly deferring installer-asset publication is a configuration decision, not a code vulnerability, but it directly affects whether users can trust the in-app update mechanism at all. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| A local, unauthenticated IPC channel (single-instance socket/pipe) accepting arbitrary commands from any local process | Spoofing / Elevation of Privilege | Use a fixed, minimal message set (e.g., a single literal "raise" sentinel) with no free-form deserialization; `QLocalServer` on Windows uses named pipes scoped to the current user by default — do not widen that scope. Never execute or `eval()` anything received on this channel. |
| A frozen exe path change silently breaking the AppUserModelID-to-shortcut match, causing Windows to associate the taskbar icon/pinned shortcut with the WRONG (or no) app identity | Tampering (identity confusion, low severity) | Keep the AUMID string a stable literal independent of install path/version; verify it after any install-path change (this app is `PrivilegesRequired=lowest`, i.e. per-user `%LOCALAPPDATA%\Programs\LecturePack`, which is a fixed, predictable location). |
| Deleting Qt DLLs post-build without verifying WebEngine's sandboxed renderer process can still start | Denial of Service (self-inflicted, not attacker-driven, but still a shipped-defect risk) | Always verify with an actual packaged GUI launch after any binary removal from `_internal/PySide6/`, not just the offline-processing smoke test (see Common Pitfall 1). |

## Sources

### Primary (HIGH confidence — verified directly against files/tools in this session)
- `app/packaging/lecturepack.spec`, `app/packaging/build.py`, `app/packaging/lecturepack.iss` — read directly, cited by line number throughout.
- `app/desktop/bridge.py`, `app/desktop/main.py`, `app/desktop/win_integration.py`, `app/desktop/paths.py`, `app/desktop/engine_adapter.py`, `app/desktop/update_service.py` — read directly, cited by line number throughout.
- `lecturepack/services/runtime_bootstrap.py`, `lecturepack/infrastructure/runtime_validation.py`, `lecturepack/infrastructure/runtime_inventory.py`, `lecturepack/infrastructure/config_manager.py`, `lecturepack/infrastructure/runtime_generation.py`, `lecturepack/infrastructure/transcription_engines.py` — read directly, cited by line number throughout.
- `app/ui/app.js` (lines 1980-2400 region) — read directly, cited by line number throughout.
- `PyInstaller/utils/hooks/qt/__init__.py`, `PyInstaller/utils/hooks/qt/_modules_info.py`, and the individual `hook-PySide6.*.py` files — read directly from the locally installed PyInstaller 6.21.0 package (`site-packages`), used to establish the exact Qt-dependency-collection mechanism described in "Size Cuts — The Mechanism."
- `app/dist/LecturePack/_internal/PySide6/` (actual on-disk tree, `du`/`ls` measured directly in this session) and `app/dist/LecturePack/_internal/PySide6/resources/` — direct measurement, cross-checked against `01-CONTEXT.md`'s cited figures (538 MB PySide6, 1.9 GB installed, 53 MB translations, 102 MB resources, 20 MB opengl32sw, 4.4 MB Qt6Pdf, ~45 MB qml family) — all matched exactly.
- `git diff f3d713d HEAD -- .github/workflows/release.yml` and `git log --oneline -- app/packaging/lecturepack.spec` — direct git history inspection, confirming both the updater-regression delta and that `excludes` has been present since the spec's first commit.
- `app/requirements.txt`, `app/requirements-build.txt`, and local `pip`/`python -c "import X; print(X.__version__)"` checks — direct version verification (PyInstaller 6.21.0, PySide6 6.11.1, Python 3.12.3).
- `tests/test_runtime_packaged_smoke.py`, `tests/test_beta3_packaging.py` — read directly, confirming existing coverage and its scope boundary (offline processing only, no GUI launch).
- `.planning/phases/01-clean-device-footprint-first-launch/01-CONTEXT.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `BUG_LIST.md`, `CLAUDE.md`, `AGENTS.md`, `docs/DECISIONS.md` (AD-18, AD-19 excerpts) — read directly.

### Secondary (MEDIUM confidence — WebSearch/WebFetch, corroborated by an official/authoritative source)
- Qt official docs, "Deploying Qt WebEngine Applications" (`doc.qt.io/qt-6/qtwebengine-deploying.html`) — confirms the purpose of each `resources/` file and that debug builds use separate `.debug.bin`/implicitly `.debug.pak`-style snapshots.
- Microsoft Learn, `SetCurrentProcessExplicitAppUserModelID` function docs (`learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid`) and Application User Model IDs overview (`learn.microsoft.com/en-us/windows/win32/shell/appids`) — confirms the API's purpose, the "call before presenting any UI" requirement, and the shortcut-property-store matching mechanism.
- Inno Setup `[Icons]` section reference (`jrsoftware.org/ishelp/topic_iconssection.htm`) — confirms the `AppUserModelID` shortcut parameter exists and its intended use.
- pythonguis.com, "Fix Missing Icons in PyInstaller PyQt6 Apps on Windows" and related packaging guides — practitioner corroboration of the AUMID + `setWindowIcon` combination as the standard fix for blank/generic taskbar icons in frozen PySide6/PyQt apps.
- PyInstaller GitHub issue #4177 discussion summary (via WebSearch snippet; the issue page itself did not fully load via WebFetch) — corroborates that QtWebEngineWidgets-based apps pull in QtQml/QtQuick due to native extension-module linkage, independent of this research's own direct reading of `PyInstaller/utils/hooks/qt/__init__.py`.

### Tertiary (LOW confidence — not independently verified this session, flagged in Assumptions Log)
- The exact PE-import-table linkage claim for `Qt6WebEngineCore.dll` → `Qt6Quick.dll` (A3 in Assumptions Log) — inferred from PyInstaller hook source comments and corroborating WebSearch results, not confirmed with a binary-inspection tool (`dumpbin`/`objdump`) against the actual DLL in this session.
- Whether `.debug.pak`/`.debug.bin` removal is unconditionally safe (A2 in Assumptions Log).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all versions directly verified in this environment.
- Architecture (size-cut mechanism, model dedupe, taskbar icon, updater regression): HIGH — each is backed by direct code reads, direct on-disk measurement, or direct git history diffing performed in this session, not inference from training data.
- Architecture (single-instance mechanism specifics, startup-parallelization exact implementation): MEDIUM — the recommended approach is well-established Qt practice and has in-repo precedent (`win_integration.py`'s ctypes pattern), but the exact PySide6 6.11.1 behavior around `QLocalSocket` before an event loop is running was not executed/tested in this session (see Open Question 1).
- Pitfalls: HIGH for the packaging/Qt/model/icon/updater findings (all directly evidenced); MEDIUM for the WebEngine-rendering-regression risk (logically sound given the verified DLL dependency, but not proven by an actual packaged launch in this session — that launch is explicitly reserved for the plan's execution phase, not this research phase, per the task's "read-only, do not run a full build" constraint).

**Research date:** 2026-07-30
**Valid until:** 30 days for the Qt-mechanism/PyInstaller findings (stable across patch versions of PyInstaller 6.x/PySide6 6.x, but re-verify if either is bumped past a minor version before this phase executes); 7 days for anything tied to the exact current `app/dist/LecturePack/` tree contents (that tree will be overwritten by the plan's own rebuild work).
