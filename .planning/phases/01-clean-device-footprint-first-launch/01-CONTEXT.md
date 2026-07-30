# Phase 1: Clean-Device Footprint & First Launch - Context

**Gathered:** 2026-07-30
**Milestone:** v0.9.0-beta.7
**Branch:** `codex/phase4-visual-artifact-reliability` (all beta-6 implementation and planning lives here; `main` is 153 commits behind and describes a different, legacy application)
**Status:** Ready for research and planning

<domain>
## Phase Boundary

Close the five clean-device defects the owner found on 2026-07-30 after beta 6 was
certified complete: oversized package, ~2 minute invisible launch, no duplicate-instance
protection, no setup checklist on a healthy first run, and a blank taskbar icon.

Smallest verified changes only. Preserve existing user data, existing processing
behavior, and beta-6 updater behavior. Do not weaken the AD-19 signed-manifest repair
contract or the AD-18 ASCII native-staging boundary.

**Out of scope:** new product features; a benchmark framework; a broad compatibility
matrix; re-architecting the runtime admission contract; the deferred beta-6 items
(FUTR-01..04); the unrelated detector/worker technical debt.
</domain>

<measured_baseline>
## Measured Baseline — established during discussion, 2026-07-30

Measured directly from the built output in the `codex/phase4-visual-artifact-reliability`
worktree. These numbers replace estimates; planning must not re-derive them.

| Artifact | Size |
|---|---|
| `app/dist/installer/LecturePack-0.9.0-beta.6-Portable.zip` | **841.2 MB** |
| `app/dist/LecturePack/` (installed footprint) | **1.9 GB** |
| └ `_internal/PySide6/` | **538 MB** |

Largest contributors inside `_internal/PySide6/`:

| Item | Size | Disposition |
|---|---|---|
| `Qt6WebEngineCore.dll` | 196 MB | Required — keep |
| `resources/` | 102 MB | Partly trimmable — investigate, not pre-approved |
| `translations/` (210 locale files) | 53 MB | **Cut** |
| `qml/` + `Qt6Qml` + `Qt6Quick` + `Qt6Quick3DRuntimeRender` | ~45 MB | **Cut** — no QML anywhere in `app/desktop/` |
| `opengl32sw.dll` | 20 MB | **Keep** — software GL fallback matters on VMs and old GPUs |
| `Qt6Pdf.dll` | 4.4 MB | **Cut** — unused |

Plus, outside PySide6:

- **`ggml-base.en.bin` is bundled twice**, 147,964,211 bytes each — `_internal/models/`
  (via PyInstaller `datas`, `app/packaging/lecturepack.spec:66`) and top-level `models/`
  (via `bundle_engine()`, `app/packaging/build.py:373`). ~141 MB of pure duplication.
  Deliberate per a spec comment, but it is the same file, not a demo-specific model.

**Cleared of suspicion — do not spend planning effort here:**

- No Vulkan or CUDA payload is bundled (`build.py:377`); CUDA is an on-demand download.
- The signed-repair archives from `scripts/build_signed_runtime_release.py` are published
  as separate GitHub release assets and are **never** copied into the installer.
  `lecturepack.iss:47` installs only `..\dist\LecturePack\*`.
- Compression is already maxed: `Compression=lzma2/max`, `SolidCompression=yes`
  (`lecturepack.iss:34-35`). There is no win available in compression settings.

<open_measurement>
**Corrected 2026-07-30 after owner review.** An earlier draft of this section claimed no
`Setup.exe` could be produced. That was wrong, and the method behind it was bad — the check
was `where.exe ISCC`, which only tests PATH.

Established facts:

- **ISCC 6 is installed** at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (1.4 MB).
  `_find_iscc()` (`app/packaging/build.py:275-286`) probes exactly that path, so
  `build.py` finds it without PATH. A local `python packaging/build.py` **does** produce
  `LecturePack-<version>-Setup.exe` (`build.py:532-540`).
- The artifact the owner installed was therefore almost certainly a **locally built
  `LecturePack-0.9.0-beta.6-Setup.exe`**. `app/dist/installer/` currently holds only the
  portable ZIP and SHA256SUMS, so that build's installer was cleared or its last run used
  `--no-installer`.

**Still unresolved and still blocking Success Criterion 1.** A solid-LZMA2 `Setup.exe`
should land near the 841 MB portable ZIP, which matches the owner's "~800 MB". The figure
that does not fit is the **~900 MB extraction vs. the 1.9 GB measured `app/dist/LecturePack/`**.

Planning must build the installer locally and measure, in one sitting and on one artifact:
Setup.exe size, the size it expands to, and the top contributors. Do not average the
figures, do not assume the owner misread, and do not reuse the 1.9 GB number without
re-measuring it against a freshly built tree (the existing `dist/` may carry build residue).
</open_measurement>

<updater_regression>
## Blocking discovery — the release workflow no longer feeds the updater

Found while verifying the measurement question. **Not caused by this phase's work, and
larger than this phase's scope, but it collides directly with the owner's constraint
"preserve existing beta.6 updater behavior."**

- `expected_asset_names()` (`app/desktop/update_service.py:117-120`) has the updater look
  for exactly `LecturePack-<version>-Setup.exe` (or `-Portable.zip`) plus
  `LecturePack-<version>-SHA256SUMS.txt` among the GitHub release assets.
- Until `f3d713d`, `release.yml` ran `choco install innosetup`, then
  `python packaging/build.py`, and published `Setup.exe`, `Portable.zip`, and
  `SHA256SUMS.txt` — exactly what the updater consumes.
- Commit **`a6164b1`** ("feat(02-05): automate signed runtime release assets", beta-6
  Phase 2 Plan 05) replaced that job. Current `release.yml` runs
  `build.py --no-installer` (line 58) and publishes **only six signed runtime component
  assets** (lines 80-85): the manifest, its signature, and four component ZIPs.
- Consequently a release produced by the current workflow contains **none** of the three
  assets the updater needs, and `select_asset` fails → `"update available but assets
  unavailable"` (`updater.py:88`).

The signed-runtime assets serve the *repair* path (AD-19). The installer assets serve the
*update* path. Plan 02-05 appears to have swapped one for the other rather than adding to it.

**Planning must decide and surface, not silently absorb:** whether restoring installer
publication belongs in this phase (it is a packaging change, and this phase is already
rebuilding and measuring the installer) or in its own slice. Either way it must not weaken
the AD-19 signed-manifest repair contract, and this phase must not claim "updater behavior
preserved" while this stands.
</updater_regression>
</measured_baseline>

<decisions>
## Implementation Decisions

### Package size

- **D-01:** Cut scope is fixed at: dedupe `ggml-base.en.bin` to a single location, and
  remove `translations/`, `qml/`, the Quick/Quick3D DLLs, and `Qt6Pdf.dll`. Each is
  provably unused by this application.
- **D-02:** `opengl32sw.dll` stays. The software GL fallback is what keeps the app
  working on VMs and old GPUs — exactly the clean-device population this phase serves.
- **D-03:** An aggressive Qt allowlist was **considered and rejected** for this phase. A
  missing module surfaces only in the packaged build on a clean machine, which is the
  slowest environment available to iterate in. Revisit only if D-01 proves insufficient.
- **D-04:** `resources/` (102 MB) is not pre-approved for cutting. Investigate what is
  actually loaded before removing anything from it; report findings rather than guessing.
- **D-05:** Whichever copy of `ggml-base.en.bin` survives, the guided demo and the runtime
  admission smoke must both resolve it. Deduplication must not be done by deleting one
  path and hoping — the resolution logic is the deliverable, not the deletion.

### Startup

- **D-06:** Root cause is established and must not be re-litigated:
  `RuntimeBootstrapService.assess()` is called synchronously on the UI thread in
  `Backend.__init__` (`app/desktop/bridge.py:119`), **before the window is shown**. On a
  fresh profile it takes the full path — `ffmpeg -version`, `ffprobe -version`, and a real
  staged whisper-cli transcription of the smoke WAV — each bounded at 30 s
  (`runtime_validation.py:24`). Worst case ~90 s of subprocess work with nothing on screen.
- **D-07:** This is a **one-time** cost, not per-launch. `_requires_full()`
  (`runtime_bootstrap.py:110-126`) sends subsequent launches down a light path that only
  stats files. Cold and warm launches are therefore expected to differ sharply, and both
  must be measured separately.
- **D-08:** Fix both sides. Show the window first and run validation behind honest,
  itemized per-component progress; **and** reduce the validation cost itself where it can
  be done without weakening admission evidence.
- **D-09:** Progress must name the real work in progress ("Checking Whisper runtime…"),
  not a generic bar. This is the distinction between honest feedback and the splash screen
  the owner explicitly ruled out.
- **D-10:** Any speed work must preserve the admission contract. Parallelizing the three
  independent probes is permitted. Replacing the real transcription with a weaker liveness
  check is **not** — that is the evidence AD-18 and the Phase 1 runtime contract rest on.
  If parallelization alone is insufficient, report that rather than weakening the check.

### First-run setup checklist

- **D-11:** The existing gate is a **failure** gate — it renders only when assessment
  returns not-`HEALTHY`, so a healthy fresh profile correctly skips it today. The owner's
  report is a request for new behavior, not a bug report. Plan it as a behavior change.
- **D-12:** On a first-ever launch the checklist always appears, showing Ready / Needs
  Attention per requirement, then a Continue action leads to the demo offer. Existing
  failure-gate behavior is unchanged.
- **D-13:** The checklist verifies only: supported Windows version; bundled FFmpeg and
  ffprobe; bundled Whisper executable and required DLLs; bundled model; writable
  LecturePack data directory. Nothing else.
- **D-14:** The checklist never downloads or reinstalls a component that is already
  bundled. Remediation stays the existing consented signed-repair path.
- **D-15:** It lives in the existing WebEngine UI (`#runtime-setup-overlay`,
  `app/ui/app.js`), reusing the app's own vocabulary. A native Qt pre-window was
  considered and rejected — it would introduce a second visual language for the first
  thing a new user sees.
- **D-16:** "Setup acknowledged" persists alongside `runtime_health` in
  `<data_dir>/config.json`, not in WebEngine `localStorage`. The existing guided-tour flag
  (`lecturepack.guided-tour.seen.v1`) is in localStorage and therefore dies with the
  WebEngine profile — the setup flag must survive that.
- **D-17:** The demo is offered only after the user continues past the checklist or
  deliberately skips it. Existing demo isolation guarantees (DEMO-04, DEMO-05) are
  untouched.

### Single instance and icon

- **D-18:** A second launch raises and focuses the existing window rather than exiting
  silently — silent exit is indistinguishable from a failed launch, which is what prompted
  the owner's repeated clicking.
- **D-19:** The guard runs **before** `RuntimeBootstrapService.assess()`. A guard placed
  after it would let a second process sit invisible for up to 90 s, which is the exact
  symptom being fixed.
- **D-20:** The blank taskbar icon has two candidate causes and the phase must determine
  which before fixing: (a) no `SetCurrentProcessExplicitAppUserModelID` call exists
  anywhere in `app/`, so Windows may not associate the window with the installed exe; and
  (b) `setWindowIcon` at `app/desktop/main.py:107` is guarded by an `os.path.exists` check
  with no else-branch, so a missing `.ico` fails silently. The `.ico` *is* present in the
  built output (17,644 bytes) and *is* stamped into the exe, which makes (a) the stronger
  suspect — but confirm on the packaged build rather than assuming.
- **D-21:** Whatever the cause, the missing-icon path must stop failing silently.

### the agent's Discretion

- The single-instance mechanism (`QLocalServer`/`QSharedMemory`/named mutex) and its
  wire format, provided it satisfies D-18 and D-19 and cleans up after a crash.
- Internal helper names, module placement, and test organization matching existing
  Python and JS conventions.
- The exact visual treatment of the checklist and its progress states, within the existing
  design language and the beta-5 motion vocabulary preserved by beta-6 Phase 4.
- Whether size cuts are expressed as PyInstaller `excludes`, post-build pruning in
  `bundle_engine()`, or both — provided the packaged runtime smoke still passes.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**
All paths are relative to the repository root on `codex/phase4-visual-artifact-reliability`.

### Branch and prior-milestone truth

- `.planning/milestones/v0.9.0-beta.6/README.md` — why beta 6's "complete" certification
  is not trustworthy, and what its release gate did not measure. **Read before citing any
  beta-6 verification claim.**
- `.planning/milestones/v0.9.0-beta.6/MILESTONE-CONTEXT.md` — beta-6 milestone context;
  still canonical for the runtime contract and repair architecture.
- `.planning/milestones/v0.9.0-beta.6/phases/01-runtime-contract-bootstrap/01-CONTEXT.md` —
  the runtime admission contract this phase must not weaken.
- `.planning/milestones/v0.9.0-beta.6/phases/03-empty-launch-guided-demo/03-CONTEXT.md` —
  guided demo isolation guarantees that must survive the new routing.
- `.planning/milestones/v0.9.0-beta.6/phases/05-packaged-physical-release-gate/05-UAT.md` —
  the evidence that was accepted; useful as a counter-example of what this phase's gate
  must actually record.

### Architecture decisions

- `docs/DECISIONS.md` AD-18 — Unicode paths end-to-end, whisper.cpp native CLI arguments
  staged under private ASCII paths. Constrains any startup speed work.
- `docs/DECISIONS.md` AD-19 — `cryptography==49.0.0`, pure Ed25519 detached signatures
  over exact canonical manifest bytes. Constrains anything touching repair.
- `docs/ARCHITECTURE.md` — four-layer architecture and privacy boundaries.

### Packaging

- `app/packaging/lecturepack.spec` — PyInstaller spec; `excludes` at line 87, duplicate
  model `datas` at line 66, demo asset gate at lines 52-56, `icon=` at line 108.
- `app/packaging/build.py` — `bundle_engine()` at lines 373-410 (the second model copy at
  373, the `.ico` copy at 406-408); GPU-exclusion rationale at line 377.
- `app/packaging/lecturepack.iss` — `[Files]` at line 47, compression at lines 34-35,
  `SetupIconFile` at line 32.
- `app/packaging/build.py:275-286` — `_find_iscc()`; probes `%LOCALAPPDATA%\Programs\Inno
  Setup 6\ISCC.exe`, so ISCC does not need to be on PATH. Installer build at 532-540.
- `.github/workflows/release.yml` — line 58 `build.py --no-installer`; lines 80-85 the six
  published assets. Compare against `git show f3d713d:.github/workflows/release.yml` to see
  what `a6164b1` removed.
- `app/desktop/update_service.py:117-120` — `expected_asset_names()`; the three asset names
  the updater requires and CI no longer publishes.
- `scripts/build_signed_runtime_release.py` — the four signed component archives; external
  release assets only, not bundled.

### Startup, gate, and demo

- `app/desktop/bridge.py:119` — the synchronous `assess()` call before window show.
- `lecturepack/services/runtime_bootstrap.py:61-107` — `assess()`; `_requires_full()` at
  110-126; `_validate_full()` at 128-175.
- `lecturepack/infrastructure/runtime_validation.py:24` — the 30 s per-probe bound.
- `lecturepack/infrastructure/runtime_inventory.py:10` — canonical inventory; the
  definitive list of what must survive the size cuts.
- `lecturepack/infrastructure/config_manager.py:106-133` — `persist_runtime_health()`;
  where the setup-acknowledged flag belongs (D-16).
- `app/desktop/main.py:107` — the silently-guarded `setWindowIcon`; `main()` at 236-237.
- `app/ui/app.js:1995-2210` — `RuntimeSetupGateModel` / `RuntimeSetupGate`, the overlay to
  extend; `syncDemoAdmission` at 2175; `setDemoAdmissionAvailable` at 2359-2379;
  `tourSeen()` / localStorage flag at 2336-2347.

### Project discipline

- `BUG_LIST.md` — cumulative bug ledger. **BUG-04, BUG-07, BUG-15 are the same class as
  the demo-content concern here** and record two failed attempts; read them before
  touching first-run UI state.
- `AGENTS.md` — phase discipline, safety constraints, test evidence, Git rules.
- `docs/HANDOFF-2026-07-27-1930.md` — beta-5 motion vocabulary and hard-won gotchas
  (inline styles beat class rules; CDP verification method).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `#runtime-setup-overlay` and `RuntimeSetupGateModel` (`app/ui/app.js:1995-2210`) already
  render per-component status from a backend JSON payload. The first-run checklist is an
  extension of this, not a new surface.
- `RuntimeBootstrapService.assess()` already produces per-component health records with
  evidence fields — the data the Ready / Needs Attention checklist needs already exists.
- `ConfigManager.persist_runtime_health()` (`config_manager.py:106-133`) writes atomically
  via `FileManager.write_json_atomic`; the setup-acknowledged flag should ride the same path.
- `canonical_inventory` (`runtime_inventory.py:10`) is the single authoritative list of
  required runtime files — use it to assert the size cuts broke nothing.
- `tests/test_runtime_packaged_smoke.py` and `tests/test_beta3_packaging.py` already drive
  a packaged onedir fixture (`LECTUREPACK_ONEDIR_FIXTURE`, `build.py:60-64`) — the natural
  home for packaging-exclusion tests.
- `WindowsIntegration` (`app/desktop/win_integration.py`) already hand-rolls `ITaskbarList3`
  via ctypes, so the ctypes pattern for `SetCurrentProcessExplicitAppUserModelID` is
  established in-repo.

### Established Patterns

- Runtime health is persisted as JSON in `<data_dir>/config.json`, never QSettings.
  QSettings holds only theme, update prefs, and notification prefs.
- The gate is decided in Python before the UI asks; the UI renders a backend verdict rather
  than deciding for itself. Keep this direction — the checklist must not compute status in JS.
- Demo state is sentinel-scoped and must never write normal job, library, or profile state.
- External process paths are passed as argument lists, never `shell=True`.

### Integration Points

- `Backend.__init__` (`bridge.py:119`) is the single chokepoint for startup ordering — the
  single-instance guard, the window show, and the validation reordering all land around it.
- `Backend.get_bootstrap()` (`bridge.py:318-328`) is the existing transport for gate state;
  extend its payload rather than adding a parallel channel.
- `bundle_engine()` (`build.py:373-410`) owns both the duplicate model copy and the `.ico`
  copy — two of this phase's fixes touch the same function.

### Known Traps (from BUG_LIST.md and the beta-5 handoff)

- Inline `style` attributes beat class rules regardless of pseudo-class — the button
  character work is built from `box-shadow` + `transform` only for this reason.
- Balanced brace and comment counts do **not** prove CSS validity; stray prose after a
  `*/` silently kills following rules. This has bitten twice.
- Any audit of interactive elements must not filter by tag name — interactive `<label>`
  and `<span>` elements exist and were missed once.
- 125 buttons render at runtime vs 88 in the markup; static-only sweeps are incomplete.
</code_context>

<specifics>
## Specific Ideas

- The owner's repeated clicking is itself the diagnostic: a launch with no feedback is
  indistinguishable from a failed launch. Both D-09 (honest progress) and D-18 (raise the
  existing window) exist to remove that ambiguity, and either alone leaves it partly intact.
- The size story should be told as a before/after table with per-contributor lines, since
  "installer vs installed" was the owner's first question and a single number cannot answer it.
- Cold and warm launch are architecturally different paths in this app (full vs light
  admission). Reporting a single "launch time" would hide the thing that actually matters.
</specifics>

<deferred>
## Deferred Ideas

- **Aggressive Qt module allowlist** (~600 MB potential vs ~380 MB from D-01) — rejected
  for this phase per D-03; revisit if the approved cuts prove insufficient.
- **Trimming `PySide6/resources/`** (102 MB) — not rejected, but gated behind D-04's
  investigation; may become its own slice.
- **Re-verifying beta-6's Phase 5 claims properly** — the archived milestone's release gate
  never ran on a physical machine. Broader than this phase; belongs to a beta-7 release
  gate phase if one is opened.
- Beta-6 deferred items FUTR-01..04 (offline repair import, per-file selection, alternate
  tour modes, reduced-motion preference) remain deferred.
</deferred>

---

*Phase: 01-clean-device-footprint-first-launch*
*Milestone: v0.9.0-beta.7*
*Context gathered: 2026-07-30*
