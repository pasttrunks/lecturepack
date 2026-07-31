# D-04 Investigation: `_internal/PySide6/resources/` — Findings

**Phase:** 01-clean-device-footprint-first-launch, Plan 01-04, Task 3
**Measured:** 2026-07-31, against the pre-cut `app/dist/LecturePack/` tree left on disk by
Plan 01-01's Task 3 build (commit `1b6059d`).

**Scope reminder (D-04):** this directory is **not pre-approved for cutting**. This document
investigates and reports; it deletes nothing. The keep/cut decision stays deferred to a
possible future slice, per `01-CONTEXT.md` `<deferred>`.

---

## Measured inventory

Re-measured directly from the on-disk tree with a fresh walk (not copied from
`01-RESEARCH.md`), all 10 files present, largest first:

| File | Bytes | MB (decimal) |
|---|---:|---:|
| `qtwebengine_devtools_resources.debug.pak` | 75,843,536 | 75.8 |
| `qtwebengine_devtools_resources.pak` | 11,609,304 | 11.6 |
| `icudtl.dat` | 10,467,680 | 10.5 |
| `v8_context_snapshot.debug.bin` | 2,447,687 | 2.4 |
| `qtwebengine_resources.pak` | 2,267,897 | 2.3 |
| `qtwebengine_resources.debug.pak` | 2,266,392 | 2.3 |
| `v8_context_snapshot.bin` | 693,957 | 0.7 |
| `qtwebengine_resources_200p.debug.pak` | 195,754 | 0.2 |
| `qtwebengine_resources_200p.pak` | 195,754 | 0.2 |
| `qtwebengine_resources_100p.debug.pak` | 151,066 | 0.2 |
| `qtwebengine_resources_100p.pak` | 151,066 | 0.2 |
| **Total** | **106,290,093** | **106.3 MB (101.4 MiB)** |

Cross-checked with `scripts/measure_package_footprint.py --tree app/dist/LecturePack/_internal/PySide6/resources` (`tree_bytes: 106290093`, exact match). This is the same 106.3 MB figure `01-CONTEXT.md`'s measured baseline reported for this directory (that table's row happens to be the one row expressed in decimal MB rather than MiB — see `01-EVIDENCE.md` "Size — baseline (pre-cut)" reconciliation note).

---

## Debug/release pairing

Every file in this directory falls into one of two buckets:

**`.debug.*` files and their non-debug sibling (5 pairs/singletons):**

| Debug file | Bytes | Release sibling | Bytes | Delta |
|---|---:|---|---:|---:|
| `qtwebengine_devtools_resources.debug.pak` | 75,843,536 | `qtwebengine_devtools_resources.pak` | 11,609,304 | debug is **6.5x larger** |
| `v8_context_snapshot.debug.bin` | 2,447,687 | `v8_context_snapshot.bin` | 693,957 | debug is **3.5x larger** |
| `qtwebengine_resources.debug.pak` | 2,266,392 | `qtwebengine_resources.pak` | 2,267,897 | effectively identical (1.5 KB smaller) |
| `qtwebengine_resources_200p.debug.pak` | 195,754 | `qtwebengine_resources_200p.pak` | 195,754 | **byte-identical** |
| `qtwebengine_resources_100p.debug.pak` | 151,066 | `qtwebengine_resources_100p.pak` | 151,066 | **byte-identical** |

Every `.debug.*` file has a same-named non-debug sibling present in this tree — there is no
orphaned debug file with no release counterpart. Two of the five pairs (the scaled `100p`/`200p`
resource packs) are byte-for-byte identical between debug and release, meaning those two debug
files contribute zero unique content over their sibling. The `.debug.pak` for DevTools is the
one file that dominates the directory (75.8 MB of the 106.3 MB total, ~71%).

`icudtl.dat` (10.5 MB, ICU locale/timezone tables) has **no debug/release naming variant at
all** — it is not part of the debug/release pairing pattern and is unconditionally required by
Qt WebEngine regardless of build flavor.

**Total `.debug.*` bytes:** 75,843,536 + 2,447,687 + 2,266,392 + 195,754 + 151,066 =
**80,904,435 bytes (80.9 MB)** — larger than the entire D-01 Qt cut list combined (101.0 MB Qt
cuts is close but this is a separate, larger single-category finding worth naming precisely:
80.9 MB is 76% of this directory's 106.3 MB total).

**No `d`-suffixed (debug-build) Qt DLL exists anywhere under `_internal/PySide6/`.** Checked
against Qt's own debug-DLL naming convention (`Qt6Cored.dll`, `Qt6WebEngineCored.dll`, etc.) —
confirmed present as `Qt6Core.dll` and `Qt6WebEngineCore.dll` (release names, no `d` suffix) and
no debug-suffixed counterpart for any of the six core/WebEngine modules exists in the tree. Four
filenames that superficially end in `...d.dll` (`Qt63DQuickScene2D.dll`, `Qt63DQuickScene3D.dll`,
`Qt6Quick3D.dll`, `Qt6VirtualKeyboard.dll`) are false positives — the trailing `d` belongs to the
module name itself (`3D`, `Keyboard`), not the debug-suffix convention. **This build ships only
Release Qt6 DLLs.**

---

## Reachability preflight (RESEARCH Open Question 3)

Searched all of `app/` and `lecturepack/` (source, not built `app/dist/` artifacts) for:

- `QTWEBENGINE_REMOTE_DEBUGGING`
- `QTWEBENGINE_CHROMIUM_FLAGS`
- `QTWEBENGINE_DISABLE_SANDBOX`
- any other `QTWEBENGINE_`-prefixed environment variable
- any code opening a DevTools panel or setting a remote-debugging port
- case-insensitive `devtools` / `remote debugging` occurrences generally

Commands run:
```
grep -rniE "QTWEBENGINE_|remote.?debugging|devtools" --include="*.py" --include="*.js" --include="*.json" app lecturepack
```

**Result: no occurrences found.** Zero matches across every `.py`/`.js`/`.json` file under
`app/` and `lecturepack/` (excluding the built `app/dist/` tree, which only contains Qt's own
shipped resource files, not project code). This is recorded as a finding — the search was
performed and returned empty — not assumed from absence of evidence elsewhere.

This directly bears on RESEARCH Assumption A2 below: since no code path in this application
sets a WebEngine debug/remote-debugging flag, there is no *known* reachable trigger for the
`.debug.*` resources in this app's own code. It does not, on its own, prove Qt's Release
`Qt6WebEngineCore.dll` can never reference them internally (see Recommendation).

---

## Recommendation

**Keep, do not cut, in this phase.** Risk-weighted reasoning:

- **Evidence for cutting:** every `.debug.*` file has a release sibling; no debug-suffixed Qt
  DLL exists anywhere in the tree (confirming a Release-only Qt build); the app's own source has
  zero references to any `QTWEBENGINE_*` env var or DevTools/remote-debugging code path. This is
  consistent with the `.debug.*` files being genuinely unreachable dead weight.
- **Evidence against cutting now:** RESEARCH Assumption A2 is **not resolved by this
  investigation** — Qt's documentation confirms the debug/release *naming* convention, but no
  authoritative source was found (in this investigation or in `01-RESEARCH.md`) proving a
  Release `Qt6WebEngineCore.dll` can *never* reference a `.debug.*` file under any code path
  (e.g. a user-set `QTWEBENGINE_CHROMIUM_FLAGS=--enable-logging=stderr` or similar flag set
  outside this app's own code, in the user's environment). The reachability preflight above
  proves this *app* never sets such a flag; it does not prove Qt itself never reads the file
  absent such a flag under some other internal condition.
- **Cost of being wrong asymmetric with D-04's own instruction:** D-04 explicitly requires
  investigate-then-report, not delete-then-verify, specifically because a missing Qt resource
  surfaces only on a packaged clean-machine launch — the slowest environment to iterate in, and
  exactly the failure mode `01-RESEARCH.md`'s Pitfall 1 and this plan's threat register
  (T-01-04-01) already flag for the D-01 Qt DLL cuts, which **do** have an explicit backstop
  verification (Plan 01-08's packaged WebEngine render check). No equivalent backstop exists yet
  for a `resources/` cut.

**The verification that would settle A2, if this becomes its own future slice:** a packaged
launch that reaches Qt WebEngine's DevTools panel (if reachable at all in this app — the
reachability preflight above found no code path that opens one) with the `.debug.*` files
removed, confirming DevTools still functions or confirming this app has no reachable DevTools
surface at all (in which case the `.debug.pak`/`.debug.bin` files could be cut with only the
resource-pack-loading fallback behavior as residual risk, not a DevTools regression). This is
explicitly **not** performed here — D-04 defers the decision, and this phase's only backstop
verification (Plan 01-08) is scoped to the six approved D-01 targets, not `resources/`.

**If a future slice pursues this cut:** target `.debug.*` files specifically (80.9 MB), not the
whole directory — `icudtl.dat` (10.5 MB) has no debug/release pairing at all and is
unconditionally required, and the two non-debug `.pak` files plus `v8_context_snapshot.bin`
(the release siblings) are actively loaded by this build's Release Qt6WebEngineCore.dll.

---

## Scope statement

**This phase removes nothing from `_internal/PySide6/resources/`.** The 106.3 MB measured here
(and the 80.9 MB `.debug.*` subset specifically) is recorded for a possible future slice per
`01-CONTEXT.md` `<deferred>` — "Trimming `PySide6/resources/` (102 MB) — not rejected, but gated
behind D-04's investigation; may become its own slice." Tasks 1 and 2 of this plan (the D-01 Qt
component removals plus the D-05 model dedupe, and the D-24 `torch`/`transformers` excludes
recorded separately) stand on their own regardless of what happens to `resources/`.

**Measured interaction, so the owner can judge whether D-03's "revisit only if D-01 proves
insufficient" trigger has fired:**

| Contributor | Bytes | MB |
|---|---:|---:|
| D-01 Qt component cuts (`translations/`, `qml/`, 4 DLLs) | 100,964,806 | 101.0 |
| D-01 model dedupe (one `ggml-base.en.bin` copy removed) | 147,964,211 | 148.0 |
| **D-01 total (this plan's Tasks 1–2)** | **248,929,017** | **248.9** |
| D-24 `torch`/`transformers` excludes (this plan, beyond D-01's original scope) | 416,475,502 | 416.5 |
| **Combined reduction landed by this plan** | **665,404,519** | **665.4** |
| `_internal/PySide6/resources/` (D-04, untouched, reported only) | 106,290,093 | 106.3 |
| — of which `.debug.*` subset specifically | 80,904,435 | 80.9 |

Against the pre-cut built-tree baseline of 1,919,524,745 bytes (`01-EVIDENCE.md`), this plan's
Tasks 1–2 plus the D-24 excludes are projected to reduce the built tree to approximately
**1,254,120,226 bytes (~1.25 GB)** — a **~34.7% reduction** from the pre-cut baseline — without
touching `resources/` at all. The untouched `resources/` directory would then represent **~8.5%**
of the projected post-cut tree, and its `.debug.*` subset alone ~6.5%. These are projections from
summing measured pre-cut component sizes against the known baseline, not a second real build;
Plan 01-08 will measure the actual post-cut tree and confirm or correct this projection.

Whether an 8.5% remaining single-directory contributor is enough to fire D-03's "revisit only if
D-01 proves insufficient" trigger is an owner judgment call this document does not make — D-01's
own combined cut (Tasks 1-2 + D-24) already reduces the tree by more than a third, which is a
substantial result on its own. This document's job is to hand the owner the measured number, not
to decide the trigger for them.

---

*Investigation performed: 2026-07-31, Plan 01-04 Task 3.*
*Deletion decision: deferred, per D-04.*
