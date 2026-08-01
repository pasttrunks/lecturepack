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

**Measured 2026-07-31 during Plan 01-04's D-24 verification build** (orchestrator-run, since
`packaging/build.py` cannot survive an executor agent's context ending). One post-cut build,
one artifact, one sitting — same discipline as the baseline above.

**Build identity:** clean venv at `.venv`, created with `python -m venv` and populated from
`app/requirements.txt` + `app/requirements-build.txt` **plus `tzdata` only** (see the note
below). `torch`, `transformers`, and `sklearn` confirmed absent from the venv before building.
Python 3.12.3, PyInstaller 6.21.0, PySide6 6.11.1, ISCC 6, commit `f7a24a0`,
checkout `C:\Users\marsh\Documents\LecturePack-beta6-plan`.

| Figure | Bytes | MiB | MB (decimal) |
|---|---|---|---|
| `Setup.exe` own byte size | 376,323,704 | 358.9 MiB | 376.3 MB |
| `app/dist/LecturePack/` built-tree byte size | 1,081,124,808 | 1,031.0 MiB | 1,081.1 MB |
| Portable ZIP byte size | 494,736,030 | 471.8 MiB | 494.7 MB |
| Expanded tree byte size | 1,097,762,563 | 1,046.9 MiB | 1,097.8 MB |

**Superseded 2026-07-31 by the BUG-27 correction.** The figures in the table above came from
a build that pruned `Qt6Qml.dll`/`Qt6Quick.dll` and therefore **could not start at all** — the
sizes were real but the artifact was unusable. The authoritative post-cut figures are in
`## Size — after cuts (corrected, BUG-27)` below. The expanded-tree figure was measured from a
real silent install/uninstall of the corrected `Setup.exe`.

**Before → after:**

| Figure | Pre-cut | Post-cut | Δ |
|---|---|---|---|
| `Setup.exe` | 686,684,565 B (654.9 MiB) | 376,323,704 B (358.9 MiB) | **−310,360,861 B / −45.2%** |
| Built tree | 1,919,524,745 B (1,830.6 MiB) | 1,081,124,808 B (1,031.0 MiB) | **−838,399,937 B / −43.7%** |
| Portable ZIP | 884,697,661 B (843.7 MiB) | 494,736,030 B (471.8 MiB) | **−389,961,631 B / −44.1%** |

The built-tree reduction (−799.6 MiB) exceeds the ~658 MB the plan projected from D-01 + D-24
alone. The surplus comes from the clean venv rather than from any additional deliberate cut:
`sklearn` (11.9 MiB) disappeared because it was only ever a global-environment artifact, and
`cv2` shrank because `app/requirements.txt` pins `opencv-python-headless` while the global
environment had the heavier GUI-bearing `opencv-python`. This is D-24's clean-venv clause
paying off beyond its stated scope — recorded as an observation, not claimed as planned work.

**Top contributors (after cuts):**

| Bytes | MiB | Path |
|---|---|---|
| 737,825,337 | 703.6 | `_internal` |
| 204,828,984 | 195.3 | `_internal/PySide6/Qt6WebEngineCore.dll` |
| 182,614,016 | 174.2 | `bin` |
| 147,964,211 | 141.1 | `models` (now a single copy — was 2× pre-cut) |
| 106,290,093 | 101.4 | `_internal/PySide6/resources` |
| 86,481,920 | 82.5 | `bin/ffmpeg.exe` |
| 86,319,616 | 82.3 | `bin/ffprobe.exe` |
| 85,848,064 | 81.9 | `_internal/cv2/cv2.pyd` |
| 75,843,536 | 72.3 | `_internal/PySide6/resources/qtwebengine_devtools_resources.debug.pak` |
| 30,876,160 | 29.4 | `_internal/cv2/opencv_videoio_ffmpeg500_64.dll` |
| 20,639,544 | 19.7 | `_internal/PySide6/opengl32sw.dll` (kept — D-02) |

`Qt6WebEngineCore.dll` is now the largest single file, as CONTEXT's `<measured_baseline>`
expected once `torch` was gone. Note that `qtwebengine_devtools_resources.debug.pak`
(72.3 MiB) is 71% of the `resources/` directory D-04 gated — see `01-FINDINGS-resources.md`,
which recommends keeping it for this phase.

**Pruned-tree audit (after cuts)** — `scripts/measure_package_footprint.py --tree
app/dist/LecturePack --assert-pruned`, **exit 0**:

| Check | Expected | Observed |
|---|---|---|
| `_internal/PySide6/translations` | absent | absent ✓ |
| `_internal/PySide6/qml` | absent | absent ✓ |
| `_internal/PySide6/Qt6Qml.dll` | absent | absent ✓ |
| `_internal/PySide6/Qt6Quick.dll` | absent | absent ✓ |
| `_internal/PySide6/Qt6Quick3DRuntimeRender.dll` | absent | absent ✓ |
| `_internal/PySide6/Qt6Pdf.dll` | absent | absent ✓ |
| `cut_targets_present_count` | 0 | **0** ✓ |
| `opengl32sw.dll` | **present** (D-02 keep) | present ✓ |
| `ggml-base.en.bin` count | exactly 1 (D-05) | **1** ✓ |

**D-24 runtime guards — both satisfied.** `LECTUREPACK_ONEDIR_FIXTURE` pointed at the
post-cut tree, then `pytest tests/test_runtime_packaged_smoke.py tests/test_beta3_packaging.py
tests/test_package_pruning.py` → **33 passed, 0 failed**.

`test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile` is the load-bearing one
and covers both of D-24's required guards in a single real run: it copies the packaged tree to
`runtime 漢 copy` (a Unicode path containing a space), invokes
`build.run_disposable_runtime_smoke()` against the real `bin/whisper-cli.exe`, asserts the
actual argv shape (`-m <model> -f <wav> -t 1 -nt`) with both native paths ASCII-staged, then
constructs `RuntimeBootstrapService(...).assess()` on a fresh profile and requires
`state == "HEALTHY"` with per-component `argv`/`exit_code`/`duration_ms`/`stdout`/`stderr`
evidence for `bin/whisper-cli.exe`, `models/ggml-base.en.bin`, and `smoke/runtime-smoke.wav`.

So this one test is simultaneously: the packaged runtime smoke; **one real local
transcription**; proof that D-05's surviving single model copy resolves; and proof that
AD-18's ASCII native-staging boundary still holds after the cuts. Critically, admission
reached `HEALTHY` with `torch` and `transformers` absent — **neither module is requested at
runtime**, which is the condition D-24 said must hold or else stop and report the importer.
Nothing needed reporting.

**Note on `tzdata`.** The verification venv installed `app/requirements.txt` plus `tzdata`,
not `app/requirements.txt` alone, because `app/requirements.txt` omits three dependencies the
repo-root `requirements.txt` declares (`Send2Trash`, `tzdata`, `yt-dlp`) despite its header
claiming to mirror it. `tzdata` **was** present in the pre-cut baseline, so building without
it would have introduced a regression inside the very step meant to verify a size cut, and
would have made the before/after comparison measure two different things. `Send2Trash` and
`yt-dlp` were already absent from the baseline and were deliberately left absent, since
adding them would change shipped behaviour (deletion semantics; a new UI affordance) rather
than measure a cut. See `deferred-items.md` — the `Send2Trash` gap means packaged builds
hard-delete user files where the source intends a recycle-bin move.

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

## Launch timing — cold / warm

Measured — see `## Launch timing — measured 2026-07-31` and `## Plan 01-08` below.

---

## Single instance — two-process proof

Measured — see `## Plan 01-08` below.

---

## Packaged clean-profile launch

Measured — see `## First-run behaviour — observed 2026-07-31` and `## Plan 01-08` below.

---

## Packaged runtime smoke after the cuts

Measured — see `## Size — after cuts` D-24 runtime guards section above.


---

## Size — after cuts (corrected, BUG-27)

The build measured here is the authoritative post-cut artifact: built from a clean venv, from
committed source at `73e93a9`, with `Qt6Qml.dll`/`Qt6Quick.dll` **restored** after physical
verification proved the earlier build could not start (BUG-27). Verified to launch.

| Figure | Bytes | MiB | MB (decimal) |
|---|---|---|---|
| `Setup.exe` own byte size | 379,849,962 | 362.3 | 379.8 |
| Expanded tree byte size (real silent install) | 1,097,762,563 | 1,046.9 | 1,097.8 |
| `app/dist/LecturePack/` built-tree byte size | 1,093,117,786 | 1,042.5 | 1,093.1 |
| Portable ZIP byte size | 499,831,377 | 476.7 | 499.8 |

Expanded minus built tree = 4,644,777 bytes (~4.4 MiB) — the uninstaller and install metadata.

**Before → after (authoritative):**

| Figure | Pre-cut | Post-cut | Δ |
|---|---|---|---|
| `Setup.exe` | 686,684,565 B (654.9 MiB) | 379,849,962 B (362.3 MiB) | **−306,834,603 B / −44.7%** |
| Built tree | 1,919,524,745 B (1,830.6 MiB) | 1,093,117,786 B (1,042.5 MiB) | **−826,406,959 B / −43.1%** |
| Portable ZIP | 884,697,661 B (843.7 MiB) | 499,831,377 B (476.7 MiB) | **−384,866,284 B / −43.5%** |

Restoring the two load-bearing DLLs cost 11.4 MiB against ~826 MiB reclaimed — 1.4% of the win.

**Pruned-tree audit — `--assert-pruned`, exit 0** (verified unmasked; a trailing pipe had
previously hidden a non-zero exit):

| Check | Expected | Observed |
|---|---|---|
| `translations`, `qml`, `Qt6Quick3DRuntimeRender.dll`, `Qt6Pdf.dll` | absent | all absent ✓ |
| `Qt6Qml.dll`, `Qt6Quick.dll` | **present** (BUG-27) | both present ✓ |
| `opengl32sw.dll` | present (D-02) | present ✓ |
| `ggml-base.en.bin` count | exactly 1 (D-05) | 1 ✓ |

---

## Launch timing — measured 2026-07-31

Three runs, all on the corrected build, all with a fresh `LECTUREPACK_DATA_DIR`. **The three
numbers do not mean the same thing** and must not be averaged or quoted as one figure:

| Run | Profile | Windows file cache | Time to window |
|---|---|---|---|
| first launch of a freshly built tree | fresh | **cold** | **9.43 s** |
| later launch, fresh profile | fresh (full validation path) | warm | 2.58 s |
| relaunch, same profile | acknowledged (light path) | warm | 2.38 s |
| installed build, fresh profile | fresh | cold-ish | 10.87 s |

**What this shows.** Cold-profile and warm-profile times are now nearly identical (2.58 vs
2.38 s) — which is 01-06 working as designed. The window is shown *before* the validation
work runs, so time-to-window no longer carries the validation cost, and D-07's sharp
cold/warm split has moved out of the startup path and into the progress panel. The remaining
spread between 9.43 s / 10.87 s and ~2.5 s is Windows' **file cache**, not validation: the
first launch of a freshly written ~1 GB tree pages DLLs in from disk.

**Still not measured — time to *ready*.** Every figure above is time-to-first-window
(Success Criterion 3's "visible feedback"). Time-to-fully-validated is a different number and
needs observing when the progress panel completes; it was not captured. Criterion 3's second
half ("the remaining runtime validation reports honest itemized progress") is therefore
recorded as observed-qualitatively, not timed.

---

## First-run behaviour — observed 2026-07-31 on the packaged build

Verified by launching the corrected packaged build on a fresh profile:

- **D-12** — the first-run checklist appeared automatically, titled "Runtime setup", heading
  "You're ready to go", subtitle "LecturePack checked everything it needs on this device."
- **D-13** — exactly five rows, no more: Windows version · Media tools (FFmpeg) · Speech
  engine (Whisper) · Speech model · Storage folder. Each carried a **Ready** badge.
- **D-14** — no download or install wording anywhere in the panel.
- **D-17** — `Continue` and `Skip` offered; clicking `Continue` dismissed the checklist and
  *then* revealed the guided-demo card ("Polar Bears 10s Demo.mp4 · 10 seconds · local only",
  "Use demo video"). The demo was not offered before the checklist was cleared.
- **D-16** — after `Continue`, `setup_acknowledged` was present in the profile's
  `config.json`. The flag is in the data directory, not WebEngine `localStorage`.
- **D-05** — the status bar read `whisper.cpp · CPU AVX2 · ggml-base.en.bin`, confirming the
  single surviving model copy resolves in the real app.
- Initial keyboard focus landed on `Continue` (`has_focused: 1` in the accessibility tree).

Not verified: the four UI-SPEC backstop rows (reduced-motion timing, focus/keyboard
containment under Tab cycling, real-width layout at other window sizes, whisper slow-notice
text) — these need deliberate interaction beyond a single launch.

---

## Single instance — two-process proof (superseded)

Measured in Plan 01-08 — see `## Plan 01-08` section below. The guard was implemented in
commit `79225df` and verified to pass: second launch exits, minimized window restores and
focuses.

---

## D-20 taskbar icon diagnosis

Complete — see `01-FINDINGS-icon.md`. Candidate (b) (`setWindowIcon` failing silently) is
**ruled out** by Win32 icon-handle evidence on the installed build. Candidate (a) (missing
`SetCurrentProcessExplicitAppUserModelID`, confirmed absent from source) is the only remaining
explanation. **The blank-icon symptom did not reproduce** in either the direct or installed
launch — both showed a correct icon in title bar and taskbar — so the fix is justified by
mechanism, not by reproduction.


---

## Plan 01-08 — final artifact evidence (2026-07-31)

Build: clean venv, committed source `79225df`, first artifact containing the single-instance
guard, the AppUserModelID call, and the checklist UI together. `--assert-pruned` exit 0.

| Figure | Bytes | MiB |
|---|---|---|
| `Setup.exe` | 379,799,777 | 362.2 |
| Expanded tree (real silent install) | 1,097,778,827 | 1,046.9 |
| Portable ZIP | 499,838,479 | 476.7 |

### Single instance (D-18 / D-19) — PASS

| Check | Result |
|---|---|
| Second launch starts a second process | No — PID exited code 0, one process remained |
| Minimized existing window restored | Yes — `IsIconic` True → False |
| Existing window focused | Yes — foreground became the target handle |

First attempt showed foreground unchanged, but the window was already visible so nothing needed
to change, and Windows withholds focus changes without recent user input. Minimized is the real
scenario (it is *why* a user clicks again) and it passes.

### Icon (D-20 / D-21) — PASS, symptom never reproduced

| Launch path | Icon |
|---|---|
| onedir exe directly | present (title bar + taskbar) |
| installed build | present |
| installed via Start Menu shortcut (AUMID declared) | present — `ICON_BIG 0x355D064B`, taskbar `LecturePack - 1 running window` |

Shortcut carries `AppUserModelID: "LecturePack.LecturePack"` (`lecturepack.iss:70`), matching
`main.py:80`. The blank icon was **not reproduced on any path**, including the Start Menu route
that was the leading hypothesis. The fix stands on mechanism, not on a reproduction.

### Launch timing

| Run | Time to window |
|---|---|
| fresh tree, cold file cache | 9.43 s |
| fresh profile, warm cache | 2.58 s |
| acknowledged profile, warm cache | 2.38 s |
| installed build, fresh profile | 10.87 s |
| installed via Start Menu shortcut | 9.27 s |

Cold and warm profiles are now nearly identical on a warm cache — validation moved off the
startup path (01-06), so time-to-window no longer carries it. The 9–11 s figures are file-cache
cost on a freshly written ~1 GB tree.

### Not measured — remaining gaps

1. **Clean machine.** Every number above came from the developer box: `torch`/`transformers`
   installed globally, warm file cache, prior LecturePack history. Not clean-device evidence.
2. **Time to *ready*.** All timings are time-to-first-window. Time-to-fully-validated was
   never captured, so Criterion 3's "honest itemized progress" half is qualitative only.
3. **Four UI-SPEC backstops** — reduced-motion timing, Tab focus containment, layout at other
   window sizes, whisper slow-notice text. Need deliberate interaction.
4. **~455 MB of the owner-vs-measured size gap** remains unexplained (see reconciliation above).
