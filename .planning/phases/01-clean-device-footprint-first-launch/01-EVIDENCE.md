# Phase 1: Clean-Device Footprint & First Launch — Evidence

**Phase:** 01-clean-device-footprint-first-launch
**Milestone:** v0.9.0-beta.7
**Seeded:** 2026-07-30 (Plan 01-01)

## Preamble

Every unfilled sentinel marker below is a **blocking gap**, not a placeholder to be
inferred, estimated, or waived. This phase's approval/evidence gate (`.planning/ROADMAP.md`
Phase 1 "Approval/evidence gate") cannot be claimed satisfied while any marker in a
required section remains unfilled.

Rules that apply to every section in this file:

- **No averaging.** Where two figures disagree (owner-reported vs. measured, before vs.
  after cuts), both numbers are recorded distinctly, with a stated cause for the gap. An
  averaged figure is never an acceptable resolution — see `01-CONTEXT.md`
  `<open_measurement>`.
- **No stale numbers.** `app/dist/` may carry build residue from a prior run (PyInstaller,
  ISCC, or manual edits). A number in this file must come from the specific build
  identified in `## Machine and build identity` for that section — it may not be carried
  over from a different build date, a different git commit, or a different machine.
- **No missing machine identity.** Beta-6's Phase 5 release gate
  (`.planning/milestones/v0.9.0-beta.6/phases/05-packaged-physical-release-gate/05-UAT.md`)
  named no physical machine, no OS build number, and no git commit for any of its "PASS"
  rows. This file exists so that failure mode cannot recur in beta-7.

---

## Machine and build identity

- OS build number: Windows 10.0.26200 (`sys.getwindowsversion()` → `major=10, minor=0, build=26200, platform=2`; marketed as Windows 11, the Win32 API still reports major version 10 — this is expected and not a measurement error).
- CPU: Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz
- Python: 3.12.3 (`C:\Users\marsh\AppData\Local\Programs\Python\Python312`)
- ISCC: Inno Setup 6 Command-Line Compiler (resolved via `_find_iscc()` at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`, confirmed present and runnable — the `where.exe`-only check that produced the earlier wrong claim in `01-CONTEXT.md` `<open_measurement>` is not how this was confirmed).
- Checkout path (matters per D-23): `C:\Users\marsh\Documents\LecturePack-beta6-plan` — 12 characters longer than the `Documents\LecturePack` path D-23 also references. This is the path the D-23 MAX_PATH failure and fix were both verified against.
- Profile clean (fresh disposable profile, not the developer's daily profile): **No.** This build ran in the developer's normal working environment on the primary checkout above, not a disposable profile. Recorded honestly rather than implied clean — this is a gap relative to the ideal evidence standard, not a hidden one.
- Git commit measured: `1b6059d5087edf7eb4abf786dfe4ee2ea4775ceb` ("fix(01-01): normalize ISCC source/output dirs per D-23", committed 2026-07-31 00:06:47 -0400) — this is `HEAD` at measurement time and includes the D-23 fix. The build log's ISCC invocation (`/DSourceDir=...\app\dist\LecturePack /DOutputDir=...\app\dist\installer`) confirms the normalized-path fix was active for this build, not the pre-D-23 code path.
- Build artifact timestamps: `app/dist/LecturePack/` and `LecturePack.exe` at 2026-07-31 00:15 local; `app/dist/installer/` (Setup.exe, Portable.zip, SHA256SUMS.txt) at 2026-07-31 00:23 local — after the measured commit, consistent with a build run at that commit.
- Exact `python packaging/build.py` invocation used: `python packaging/build.py` (run from the `app/` directory, no `--no-installer` flag — a full build producing all three release assets). Internally this drove `python -m PyInstaller app/packaging/lecturepack.spec --noconfirm`, `bundle_engine()`, `make_portable_zip()`, and `ISCC.exe /DAppVersion=0.9.0-beta.6 /DSourceDir=...\app\dist\LecturePack /DOutputDir=...\app\dist\installer app\packaging\lecturepack.iss`.
- Build result: **success.** Build log's final line: `Release gate OK — validated: ['LecturePack-0.9.0-beta.6-Portable.zip', 'LecturePack-0.9.0-beta.6-SHA256SUMS.txt', 'LecturePack-0.9.0-beta.6-Setup.exe']`. All three assets `expected_asset_names()` (`update_service.py:117-120`) requires were produced by this **local** build — relevant to D-22/`<updater_regression>`: only the current CI `release.yml` (`build.py --no-installer`) fails to produce them, not `build.py` itself.

---

## Size — baseline (pre-cut)

Measured from **one** freshly built `Setup.exe` in a single sitting (Plan 01-01 Task 3),
before Plan 01-04 changes any packaging code.

Measured with `scripts/measure_package_footprint.py` (Task 1 of this plan) against
`git 1b6059d`'s build, all four figures kept **distinct** — never averaged together:

| Figure | Bytes | MiB (binary) | MB (decimal) |
|---|---|---|---|
| `Setup.exe` own byte size | 686,684,565 | 654.9 MiB | 686.7 MB |
| Expanded tree byte size (what `Setup.exe` installs to — measured via `--expand-to`, a real `/VERYSILENT /DIR=<scratch>` install, measured, then `unins000.exe /VERYSILENT` uninstall; scratch dir outside the repo, confirmed removed afterward) | 1,926,039,216 | 1,836.5 MiB (1.79 GiB) | 1,926.0 MB (1.93 GB) |
| `app/dist/LecturePack/` built-tree byte size (pre-install, PyInstaller + `bundle_engine()` output) | 1,919,524,745 | 1,830.8 MiB (1.79 GiB) | 1,919.5 MB (1.92 GB) |
| Portable ZIP byte size | 884,697,661 | 843.7 MiB | 884.7 MB (0.88 GB) |

**Expanded vs. built-tree delta:** 1,926,039,216 − 1,919,524,745 = **6,514,471 bytes (~6.5 MB)
larger once installed than the raw built tree.** Cause: Inno Setup writes its own
uninstaller stub (`unins000.exe`) and compressed uninstall metadata (`unins000.dat`) into
the install directory during a real install — these two files are not part of
`app/dist/LecturePack/` and did not appear in this run's top-12 contributor list because
each falls below the other listed entries, not because they don't exist. This is a normal,
well-documented Inno Setup behavior, not a new packaging defect.

**Top contributors (baseline, from `app/dist/LecturePack/`, `top_contributors(limit=12)`):**

| Contributor | Bytes | MiB | MB (decimal) |
|---|---|---|---|
| `_internal` (rollup) | 1,509,317,894 | 1,439.4 | 1,509.3 |
| `_internal/torch/lib/torch_cpu.dll` | 305,081,856 | 290.9 | 305.1 |
| `_internal/PySide6/Qt6WebEngineCore.dll` | 204,828,984 | 195.4 | 204.8 |
| `bin` (rollup) | 182,614,016 | 174.2 | 182.6 |
| `models` (rollup, duplicate copy 1) | 147,964,211 | 141.1 | 148.0 |
| `models/ggml-base.en.bin` | 147,964,211 | 141.1 | 148.0 |
| `_internal/models/ggml-base.en.bin` (duplicate copy 2) | 147,964,211 | 141.1 | 148.0 |
| `_internal/PySide6/resources` | 106,290,093 | 101.4 | 106.3 |
| `bin/ffmpeg.exe` | 86,481,920 | 82.5 | 86.5 |
| `bin/ffprobe.exe` | 86,319,616 | 82.3 | 86.3 |
| `_internal/cv2/cv2.pyd` | 86,293,504 | 82.3 | 86.3 |
| `LecturePack.exe` | 79,578,936 | 75.9 | 79.6 |

**Directory-level rollups not in the top-12 list above but requested by the reconciliation
reference** (measured directly with `tree_size()` against the same build, to reconcile
against the reference table in this plan's dispatch — reconciled, not overwritten):

| Item | Bytes | MiB | MB (decimal) |
|---|---|---|---|
| `_internal/PySide6` | 557,351,232 | 531.5 | 557.4 |
| `_internal/torch` | 378,347,026 | 360.8 | 378.3 |
| `_internal/cv2` | 117,183,874 | 111.8 | 117.2 |
| `_internal/scipy` | 53,512,704 | 51.0 | 53.5 |
| `_internal/transformers` | 38,128,476 | 36.4 | 38.1 |
| `_internal/sklearn` | 12,485,607 | 11.9 | 12.5 |

Reconciliation note on this reference table (not part of the discrepancy this plan is
required to explain, but caught in the course of reconciling): every row above matches the
reference figures given for this run when the reference is read as **MiB** (e.g. `531.5` =
557,351,232 bytes ÷ 1024²), **except** `_internal/PySide6/resources`, whose reference value
of `106.3` matches only when read as **decimal MB** (106,290,093 ÷ 1,000,000 = 106.29) —
its MiB value is 101.4. The reference table itself mixes unit conventions row-to-row. This
is exactly the class of confusion `01-CONTEXT.md`'s `<open_measurement>` warns about, and
is recorded here rather than silently normalized, since it was found by measuring rather
than assumed.

**Pruned-tree audit (baseline, pre-cut) — `audit_pruned_tree(app/dist/LecturePack)`:**

| Target | Present? |
|---|---|
| `_internal/PySide6/translations` | Yes |
| `_internal/PySide6/qml` | Yes |
| `_internal/PySide6/Qt6Qml.dll` | Yes |
| `_internal/PySide6/Qt6Quick.dll` | Yes |
| `_internal/PySide6/Qt6Quick3DRuntimeRender.dll` | Yes |
| `_internal/PySide6/Qt6Pdf.dll` | Yes |
| `opengl32sw.dll` | Yes — expected-and-correct (D-02 software GL fallback kept) |
| `ggml-base.en.bin` count | 2 |

All six D-01 cut targets present (count 6/6), `opengl32sw.dll` present as expected per D-02,
and `ggml-base.en.bin` duplicated exactly as CONTEXT.md's baseline described. This is the
"before" state Plan 01-04 must change; `--assert-pruned` was deliberately **not** run here
per Task 3's instruction (it is designed to fail pre-cut).

---

## Size — after cuts

Filled by Plan 01-08, from one post-cut build. Do not fill from this plan.

| Figure | Value |
|---|---|
| `Setup.exe` own byte size | NOT YET MEASURED |
| Expanded tree byte size | NOT YET MEASURED |
| `app/dist/LecturePack/` built-tree byte size | NOT YET MEASURED |
| Portable ZIP byte size | NOT YET MEASURED |

**Top contributors (after cuts):**

NOT YET MEASURED

**Pruned-tree audit (after cuts) — all six D-01 targets expected absent, `opengl32sw.dll`
expected present (D-02 keep), `ggml-base.en.bin` count expected exactly 1:**

NOT YET MEASURED

---

## Size — reconciliation

**Owner-reported figures (2026-07-30, installed a locally built beta-6 `Setup.exe`):**

- Installer (`Setup.exe`): ~800 MB
- Expanded/installed size: ~900 MB

**Dev-tree figures (measured directly in the `codex/phase4-visual-artifact-reliability`
worktree, `01-CONTEXT.md` `<measured_baseline>`, 2026-07-30):**

- `LecturePack-0.9.0-beta.6-Portable.zip`: 841.2 MB
- `app/dist/LecturePack/` installed footprint: 1.9 GB

**Freshly measured baseline figures (this plan, Task 3, from `1b6059d`):**

- `Setup.exe`: 686,684,565 bytes = 654.9 MiB = 686.7 MB
- Expanded tree (real silent install): 1,926,039,216 bytes = 1,836.5 MiB (1.79 GiB) = 1,926.0 MB (1.93 GB)
- `app/dist/LecturePack/` built tree: 1,919,524,745 bytes = 1,830.8 MiB (1.79 GiB) = 1,919.5 MB (1.92 GB)
- Portable ZIP: 884,697,661 bytes = 843.7 MiB = 884.7 MB

These four numbers are kept **distinct** — they are never averaged into a single figure.

- **Measured answer:** The owner's two figures move in **opposite directions** relative to
  what this build actually produces, and neither gap closes under a unit-convention
  reinterpretation:
  - **Installer:** owner recalled **~800 MB**. Measured `Setup.exe` is **smaller** than that
    in both conventions — 654.9 MiB or 686.7 MB, roughly 14-18% below 800 depending on which
    convention "800" was meant in. Unit convention alone cannot flip a measured-smaller
    result into a measured-larger recollection; the gap is not a MiB/MB artifact.
  - **Installed/expanded:** owner recalled **~900 MB**. Measured expanded size is
    1,836.5 MiB or 1,926.0 MB — **more than double** the recollection under either
    convention. The ~5% MiB-vs-MB gap this project keeps running into is nowhere near large
    enough to explain a >2x difference.
  - Both directions were tested against both unit conventions explicitly (not assumed) and
    neither closes the gap. This confirms `01-CONTEXT.md` `<open_measurement>`'s instruction
    to test rather than assert.
- **Cause:**
  - **Installed/expanded gap — partially explained, not closed.** Per D-24, `torch`
    (378.3 MB / 360.8 MiB) and `transformers` (38.1 MB / 36.4 MiB) are packaged despite
    being unreferenced by any project import, and per D-01 one of the two
    `ggml-base.en.bin` copies (148.0 MB / 141.1 MiB) is pure duplication. Removing all three
    from the built-tree decimal-MB figure: 1,919.5 − 378.3 − 38.1 − 148.0 = **1,355.1 MB
    (≈1.36 GB)**. That is still **~455 MB above** the owner's ~900 MB recollection — over a
    third larger than the target even after removing the single largest known-undeclared
    contributor and the known duplication. **This hypothesis is evaluated, not adopted: it
    is insufficient on its own to close the gap.** The remaining ~455 MB is recorded here as
    an **explicitly open question**, not resolved:
    - *Known:* the tree total (1.92 GB), the torch/transformers contribution (~416 MB
      decimal), the duplicate-model contribution (148 MB), and that these three together
      close roughly 40% of the gap between measured and recalled.
    - *Ruled out:* build residue in `app/dist/` — this run's 1,919,524,745-byte figure was
      measured from a build produced in this same session from a known commit, not an
      inherited stale tree, and it matches `01-CONTEXT.md`'s independently-measured
      1,919,524,745-byte figure exactly. The 1.9 GB number was **not** an artifact of
      residue (this retires that candidate cause outright).
    - *What would close it:* either the owner's original build predates a dependency that
      isn't `torch`/`transformers` (D-24 explicitly scoped only those two — `cv2` 117.2 MB,
      `scipy` 53.5 MB, and `sklearn` 12.5 MB were left as out-of-scope observations, not
      investigated as candidates here), or the owner's recollection itself used a different
      reference point (e.g. Windows Explorer's on-disk "Size on disk" after cluster
      rounding, or a different, older build entirely). Neither can be confirmed from
      evidence available to this plan. Resolving this further is out of this plan's scope.
  - **Installer-size gap — open, no hypothesis offered.** Nothing in this plan's evidence
    explains why the owner recalled a **larger** installer than the one just measured. The
    dev-tree portable ZIP (884.7 MB) is closer to the owner's "~800 MB" than the actual
    solid-LZMA2 `Setup.exe` (686.7 MB) is — i.e., if the owner's recollection was actually of
    the ZIP rather than the installer, that would move the gap in the right direction, but
    this plan has no evidence the owner ever ran the ZIP path, and asserting that would be
    exactly the kind of unverified inference this file exists to prevent. Recorded as open:
    *known* — today's `Setup.exe` from `1b6059d` is 686.7 MB; *ruled out* — this is not a
    build-residue or stale-artifact question, since the file was produced fresh this
    session; *what would close it* — the actual `Setup.exe` the owner installed no longer
    exists to re-measure directly, so this can only be closed by the owner confirming which
    artifact (installer vs. portable ZIP) they actually ran, or by a future beta-7 release
    build being independently confirmed against a fresh owner-side measurement.
  - **ZIP delta (observation, not part of the discrepancy above):** this build's Portable
    ZIP (884,697,661 bytes / 884.7 MB) is 43.5 MB **larger** than the 841.2 MB portable ZIP
    figure recorded in `01-CONTEXT.md` `<measured_baseline>` on 2026-07-30. Both are dev-tree
    measurements from the same worktree; the delta is recorded as an observation for later
    plans, not explained further here.
  - **D-22/updater relevance (observation):** this plan's local `python packaging/build.py`
    run produced all three assets `expected_asset_names()` requires (see `## Machine and
    build identity` above). Only the current CI `release.yml` (`build.py --no-installer`)
    fails to produce them. This sharpens D-22: the regression is specific to the CI job
    definition, not to `build.py` itself.

Averaging the owner-reported and dev-tree figures is **not** an acceptable resolution, and
none was performed above. Reusing the 1.9 GB dev-tree figure as-is was also avoided — it was
independently re-measured from this session's fresh build (1,919,524,745 bytes, exact match)
rather than carried over, confirming it was not build residue (`01-CONTEXT.md`
`<open_measurement>`).

---

## D-04 resources/ investigation

Pointer to `01-FINDINGS-resources.md` (Plan 01-04). NOT YET MEASURED — not produced by this
plan.

---

## D-20 taskbar icon diagnosis

Pointer to `01-FINDINGS-icon.md` (Plan 01-05). NOT YET MEASURED — not produced by this plan.

---

## Launch timing — cold

Per D-07, cold and warm launches take architecturally different paths
(`RuntimeBootstrapService._requires_full()`) and must be measured and recorded separately.

- Time to first visible on-screen feedback: NOT YET MEASURED
- Time to ready (fully validated, usable): NOT YET MEASURED
- Which validation path ran (full / light): NOT YET MEASURED

---

## Launch timing — warm

- Time to first visible on-screen feedback: NOT YET MEASURED
- Time to ready (fully validated, usable): NOT YET MEASURED
- Which validation path ran (full / light): NOT YET MEASURED

---

## Single instance — two-process proof

- Process count observed after a second launch attempt: NOT YET MEASURED
- Which window received focus: NOT YET MEASURED

---

## Packaged clean-profile launch

- Icon visible in title bar: NOT YET MEASURED
- Icon visible in taskbar: NOT YET MEASURED
- Rendered WebEngine content observed: NOT YET MEASURED

---

## Packaged runtime smoke after the cuts

- Exact pytest invocation: NOT YET MEASURED
- Result: NOT YET MEASURED
