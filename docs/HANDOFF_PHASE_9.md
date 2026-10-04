# Handoff: hosted Electron candidate build gate, 2026-10-04

Branch: `codex/hosted-electron-build-gate`, based on ea806ec. Existing worktree
and owner automatic approval remain in force. Production Electron is the focus.

Authorized phase: verify real hosted candidate packaging without release
publication. Permitted files: ci.yml, release-electron.yml, Rust Cargo.lock and
its ignore rule, focused CI tests, RELEASING and decision/handoff documentation.
Required evidence: focused contracts, full pytest, real Rust test/wheel build,
then the actual PR Windows candidate job. Non-goals: new dependencies, product
features, Qt changes, original media writes, merge/tag/publication.

Implemented read-only PR candidate build using the official builder and pinned
runtime, mandatory packaged health, installer/portable creation and visible
window launch. Evidence artifacts contain logs/locks/hashes, no exe/ZIP assets.
Both candidate and release jobs now build/install the Rust Python extension;
cargo test alone never installed the .pyd required by sidecar.spec. Committed
the pre-existing tested dependency lock and use --locked in both operations.

Local focused result: 44 passed in 0.65s. Fresh Rust build compiled, but the
first test launch returned STATUS_DLL_NOT_FOUND because the deliberately
restricted local PATH omitted Python312. Adding the actual interpreter root
made all 11 Rust tests pass. Fresh release wheel built and installed into an
isolated scratch target; imported module reports Rust 0.1.0 available.
Full pytest: 2074 passed, 8 skipped, 1 warning in 328.40s (0:05:28).
Logs preserved under C:\LecturePackScratch\results\hosted-electron-gate.
Hosted candidate gate passed on d839c71, run 37175987746:
https://github.com/pasttrunks/lecturepack/actions/runs/37175987746
Windows candidate job completed in 6m24s. Verified downloaded audit evidence:
20 pinned runtime files restored; 12 required packaged checks passed, including
actual Whisper smoke and Rust core; installer/portable built; visible window
appeared in 1.00s. Manifest agrees with SHA256SUMS. Hosted hashes:
- Portable: 83f0e5438671dbbd6f759bcbfd435f4715103073cc7cc3bcf5dff631616c1209
- Setup: fb9e4d5e4fd07cfe8b7dcbdcfcdf2322a80683217b2b6c398a8cd1aeb5e30126
Evidence artifacts intentionally contain no installer/portable bytes, so these
hashes were cross-checked against each other, not a separately downloaded exe.
Hosted unit pytest: 2055 passed, 27 skipped, 2 warnings in 263.32s (0:04:23).
Logs, downloaded evidence and verification.json retained in the scratch results
root. Window smoke forcibly terminates its launched process; it does not prove
clean close or lecture processing. Exact-tag release execution remains pending.
PR body updated with this phase and evidence. Follow-up documentation checkpoint
does not change the verified builder code; inspect its current PR checks too.

Previous final-head unit CI for ea806ec passed (run 37174839847):
2051 passed, 27 skipped, 2 warnings in 258.78s. This was unit CI, not hosted
Electron packaging. Remaining gates include final-tag release execution,
Electron runtime failure/reinstall recovery, historical shutdown linger,
affected/clean-machine and scaled installer checks, and live Study AI quality.
Authenticode remains unavailable. Nothing was merged, tagged or published.

Prior handoffs follow unchanged.

---

# Handoff: PR #8 reconciliation, 2026-10-03

Branch: `codex/pr8-reconciliation`, based on `9a19ed1`, existing worktree.
This phase follows the pasted handoff's explicit request to push the outstanding
commits and update PR #8. Owner approved and authorized automatic subsequent
approval. No merge/tag/publication is part of this phase.

## Scope and completed remote actions

Permitted work: read current remote state, fast-forward the existing PR branch,
rewrite title/body around the verified 2.1.4 candidate, attach the PR, watch its
checks, and update this handoff. No product implementation/dependency changes.
Required evidence: remote ancestry/head verification, accurate PR body, current
head CI outcome and retained evidence. The preceding phase's local full pytest
output remains `2070 passed, 8 skipped, 1 warning in 255.88s (0:04:15)`.

- PR https://github.com/pasttrunks/lecturepack/pull/8 was open at e669beb.
  Its old body incorrectly claimed the load-bearing yt-dlp client override was
  removed and only cited old verification. Actual remote head was confirmed
  through gh and ls-remote, and is an ancestor of our verified 9a19ed1.
- Normal push (no force) advanced fix/ytdlp-caption-media-path to 9a19ed1.
  It includes the previously unpushed handoff fixes and all passing subsequent
  Home/checklist/installer/shutdown/batch-link/CI-runtime checkpoints.
- Updated title: Prepare 2.1.4 Electron candidate: import, startup, packaging
  and CI fixes. Body explains real resulting behavior and local verification,
  required client selection, production Electron vs retained Qt compatibility,
  and explicit remaining gates. Exact submitted body retained in scratch.
- PR is attached to this chat, open, non-draft, with autoMergeRequest=null.
  No merge, public tag or release was created.
- First new unit CI started for 9a19ed1: run 37174758037, workflow CI,
  test (3.12). This is the ordinary Windows PR suite, not the exact-tag desktop
  release workflow. No hosted release-build success is claimed.

## Evidence and next validation

C:\LecturePackScratch\results\pr8-reconciliation contains the submitted
pr-body.md and current-head/check result receipts saved after verification.
This handoff-only checkpoint will be pushed normally too. Query gh pr view 8
and the actual current-head CI run for the latest outcome rather than using
an older green check. Current hosted check failures must be inspected and fixed;
check status was not yet terminal when this handoff entry was written.

Remaining original handoff work includes successful GitHub-hosted release
execution, production-appropriate packaged repair validation, the historical
OBS-04 session_closed-then-linger variant, affected/clean-machine and scaled
installer checks. Authenticode is unavailable. Local 2.1.4 artifacts remain
unsigned and unpublished. Historical installer-registration preservation and
live Study AI/provider content-quality are not proven by local Basic gates.
Canonical repository and other worktree edits remain untouched.

Prior handoffs follow unchanged.

---

# Handoff: production Electron CI runtime restoration, 2026-10-03

Branch: `codex/ci-runtime-restoration`, based on `3136287`, existing worktree
`ytdlp-caption-fix`. Automatic approval remains authorized; production Electron
is the current focus. Previous turn completed the real three-link UI gate.

## Authorized phase and scope

Address BUG-59's missing gitignored native inputs in release CI. Permitted:
release-electron.yml, build-only restore script/lock, focused tests and related
release/ledger/decision/handoff documentation. Required evidence: pinned public
archive download, complete restore, negative tests, official Electron build
using restored runtime/MSVC roots and relevant pytest. Non-goals: publication,
version/dependency changes, product download overrides, Qt changes or replacing
mandatory packaged health checks. GitHub-hosted end-to-end success is separate.

## Implemented

- scripts/ci-runtime-lock.json pins public v2.1.3 Portable.zip, size 513776556,
  SHA-256 06c4b2f6030db420a698d23148f7df0799e5f615603813549572b8ee0be9c339,
  and 20 allowlisted native CPU/model/Deno/MSVCP140 members with size/SHA-256.
- Real public GitHub download verified against that archive pin. Individual
  CPU/model/Deno files all match the pre-existing local release runtime; Deno
  equals the independently enforced 2.9.5 sidecar pin. No stack change.
- scripts/restore_ci_runtime.py uses standard-library HTTPS/ZIP/file handling,
  streams data/hashes, rejects corrupt cache/archive/member hash/size, ambiguous
  members, unsafe paths/types and existing runtime outputs. Copies only locked
  runtime members; prior UI/Python/user files cannot enter this extraction.
  Keeps partials and failed restoration evidence instead of deleting/retrying.
- Desktop workflow caches the source by lock hash, verifies even cache hits,
  restores before the official builder and configures runner-temp runtime and
  app-local MSVC roots. Restore audit and lock join retained release evidence.
- 40 focused tests passed in 0.51s (restoration + release authority/assets).
  Regression fixtures prove only pinned members are copied, tampering fails,
  unsafe/missing inputs are rejected and prior evidence is retained.

## Current verification and evidence

C:\LecturePackScratch\results\ci-runtime: archive.txt, restore.json,
focused.txt and full.txt. Source public ZIP/cache/restored output under
C:\LecturePackScratch\data\ci-runtime. Official build uses only that
restored CPU/model/MSVC input and writes sidecar/Electron/installer/portable to
C:\LecturePackScratch\builds\ci-runtime-candidate. Build log:
C:\LecturePackScratch\logs\ci-runtime\build.txt.

Official clean Electron build completed: sidecar, Electron package, mandatory
packaged health checks, Inno installer and portable ZIP. Inno completed in
77.563s with fast local-test compression. Actual rebuilt sidecar processed the
bundled real lecture through transcript/slides/export (13 files), and two
Electron launches restored the completed job and exited cleanly with zero
orphans/errors. Evidence: packaged/result.json and per-launch JSONL; explicit
Basic input was selected so this is not live Study AI evidence.

Full actual pytest: `2070 passed, 8 skipped, 1 warning in 255.88s (0:04:15)`
(full.txt). No tests were removed or weakened. New local unsigned artifacts:
- Portable SHA-256: 1bdad82bc3607e1e80e234fb54e3d14b3f6430caefdfd4b4c395a10c1746dfff
- Setup SHA-256: 90d150d54b2aca67d73a3eb8cedf4f721602cbd5a9ea3d10a6206728e49d34a1
Both match SHA256SUMS; updater manifest agrees with the installer bytes.
Previous release-test artifacts remain preserved in their original scratch
root. These rebuilt bits are still local, unsigned and unpublished.

Final committed restorer cold-cache path passed against the real public
GitHub download: cold-restore.json. All 20 member hashes exactly match the
cache-hit restore/build inputs. This verifies both network fetch and cache
verification paths; no mock was used for these integration checks.
No original media or canonical/other-worktree edits were changed.

## Remaining

BUG-59 is implemented but a successful GitHub-hosted release execution remains
unverified. No public tag/release/hosted success is claimed from a local build.
The source ZIP is deliberately large; a smaller dedicated runtime asset would
require future reviewed publication and new pins. Continue final package gates,
PR #8 reconciliation/push and remaining handoff work. Historical OBS-04 linger,
clean-machine/affected-laptop/scaled-installer checks and Authenticode remain
outstanding. Current builds remain local, unsigned and unpublished.

Prior handoffs follow unchanged.

---

# Handoff: production Electron batch-link acceptance, 2026-10-03

Branch: `codex/electron-batch-link-gate`, based on `3205907`, existing
`ytdlp-caption-fix` worktree. Auto approval continues; Electron is the current
production focus. Previous turn made progress with a committed shutdown gate
fix and 10/10 real close/restore checks.

## Authorized phase

Complete the handoff's real multi-link UI verification and save repeatable
coverage. Permitted files: new Electron acceptance script/focused tests,
BUG_LIST.md, RELEASING.md, DECISIONS.md and this handoff. Required evidence:
real public-video downloads through packaged Electron, separate persisted jobs,
restart restoration, relevant pytest and clean shutdown. Non-goals: Qt changes,
new dependencies, changed yt-dlp clients, speculative product edits, video
processing/AI claims, version changes or publication.

## Delivered and verified

- Added scripts/electron_batch_link_acceptance.py with explicit opt-in URLs,
  fresh profiles/results, real Paste/Check/Download flow, duplicate/whitespace
  coverage, actual inspected file/manifest checks and SHA-256, renderer IDs on
  first launch/restart, screenshots and clean-close/orphan requirements.
- Shipped 2.1.4 executable/sidecar fetched YouTube Me at the zoo (18.947483s,
  629172 bytes), Samplelib 5s-360p (5.758005s, 1137884 bytes) and 10s-360p
  (10.216009s, 2185013 bytes). Exactly three downloads despite four pasted
  entries. Three real jobs appeared ready to process and restored unchanged
  after restart, with real card posters. Both launches exited naturally,
  zero orphans. Gate result.json passed=true, errors=[] and stable file hashes.
- No production defect appeared in this case, so product code/artifacts stayed
  unchanged. The load-bearing yt-dlp client override stayed unchanged.
- Six evidence regressions require correct order/count, nonempty recordings,
  media inspection and one persisted job per recording. Focused actual output:
  `47 passed in 3.73s` (new gate + packaged gate + media adapter tests).

Evidence root: C:\LecturePackScratch\results\electron-batch-link.
Final live evidence: gate/result.json, confirmation.txt, launch-0/1.txt/png,
production JSONL and gate.txt. Source data: corresponding scratch data root
`electron-batch-link-gate`. Original media was not changed or deleted.

Exploratory driver failures are preserved separately: initial inspect.py
shadowed Python inspect, then a guessed CDP helper name failed, and console
encoding rejected Unicode. The first live driver used a DOM-object wait (fixed
to a boolean); its next attempt selected the Downloads header via a broad label
prefix and assumed normalized persisted status instead of legacy complete.
Those attempts did not prove a completed gate. The final script uses exact
button labels and actual persisted vocabulary and passed independently.
This verifies importing/restoration, not transcript/Study-generation quality.

## Remaining

Full pytest output: `2061 passed, 8 skipped, 1 warning in 268.21s (0:04:28)`
(full.txt). The final streaming-hash/read-encoding cleanup was verified with
`6 passed in 1.77s` and direct revalidation of the real gate files against the
recorded hashes. No tests were removed or weakened. Commit the passing
checkpoint; the worktree should then be clean. Next handoff
items: BUG-59 CI payload restoration, historical OBS-04 linger variant and
packaged repair where applicable to Electron. Clean-machine, affected-laptop,
scaled-installer and Authenticode checks remain outstanding. Previous installed
updater/host-isolation gates passed; 2.1.4 stays unsigned and unpublished.
Canonical/other worktrees unchanged. Historical Qt batch UI is still unverified
and was not part of this production Electron phase.

Prior handoffs follow unchanged.

---

# Handoff: packaged Electron shutdown gate, 2026-10-03

Branch: `codex/packaged-shutdown-gate`, based on `4f780f0` in the existing
`ytdlp-caption-fix` worktree. Owner clarified that current work is the production
Electron app, not the Qt fallback. Automatic phase approval remains authorized.

## Authorized phase and scope

Diagnose OBS-04 with repeated real packaged launches and correct the demonstrated
shutdown defect. Permitted files: scripts/electron_packaged_acceptance.py, its
focused tests, BUG_LIST.md, DECISIONS.md and this handoff. Required evidence:
behavioral regressions, full pytest output and repeated real Electron close/
restore runs. Non-goals: speculative quit/updater changes, timeout increases,
Qt work, dependencies, version changes or publication.

## Confirmed cause and correction

The baseline used the actual 2.1.4 Electron candidate executable and Python
sidecar, with a real completed Basic Study lecture restored in every launch.
One of ten runs failed: native window inventory proved the gate posted WM_CLOSE
to a hidden Chrome_WidgetWin_0 helper before the visible LecturePack window.
The product never received its main-window close and the gate killed it at the
20-second bound. Nine correctly targeted baseline runs closed in 0.656–0.969s.

The driver now selects the visible Chrome_WidgetWin_1 LecturePack window for
its PID and checks PostMessage success. Missing targets and forced termination
are explicit failures, including when a forced process reports exit zero.
No packaged app code or artifacts changed; the 20-second bound is retained.
Five behavioral regressions exercise hidden/foreign/IME/unrelated windows,
failed post, absent main window and forced termination. Focused output:
`16 passed in 0.47s`.

## Verification evidence

Scratch logs/results: C:\LecturePackScratch\results\shutdown-gate.
Baseline output: baseline.txt; native inventory and classifications: baseline/
results.json. The first corrected ten launches all closed naturally in
0.734–1.031s, but six orphan observations overlapped independent pytest FFmpeg
subprocesses. Those process observations are contaminated and do not prove
product orphans or a clean gate. Original event logs are retained in the baseline
results directory; separate baseline/fixed JSON was reconstructed from saved
stdout because the exploratory fixed runner reused that results directory.
The final repeated gate runs alone after pytest; its evidence is fixed-isolated.
Full pytest output: `2055 passed, 8 skipped, 1 warning in 251.19s (0:04:11)`.
Log: full.txt. Eight existing skips include the explicit live-AI opt-in and
checkout-only packaged-payload tests; no tests were removed or weakened.
Final isolated gate: **10/10 clean exits, 10/10 completed-job restores,
10/10 session_closed events, zero orphan processes**, 0.687–0.921 seconds
after WM_CLOSE. Evidence: fixed-isolated/results.json and per-launch JSONL logs.
Same unchanged production Electron 2.1.4 candidate used before and after.
Committed passing checkpoint on the branch above; canonical checkout untouched.

## Remaining work

OBS-04's historical session_closed-then-linger variant has not been reproduced
or explained; ledger remains partially resolved. Continue Electron-focused
polish, real multiple-link UI paste and BUG-59 CI runtime restoration. Installed
2.1.4/updater acceptance and test-host isolation already passed in prior phases.
Clean-machine, affected-laptop, scaled installer and Authenticode evidence remain
outstanding. Artifacts remain unsigned and unpublished. Preserve canonical and
other worktree edits. No original lecture media was modified.

Prior handoffs follow unchanged.

---

# Handoff: installer acceptance isolation, 2026-10-03

Branch: `codex/installer-test-isolation`, based on `1d076e6` in the existing
`ytdlp-caption-fix` worktree. Canonical repository and unrelated edits untouched.

## User authorization and current scope

The owner instructed: "auto approve for me from now on." Future phase gates are
approved by that instruction; do not repeatedly ask for phase approval. Continue
one coherent phase at a time and verify it before advancing. The latest owner
request is an update after this pass covering polish, bug fixes and upgrades.

This pass addresses OBS-07: protect test-host integration around real installer
acceptance, including errors. Permitted files are the two acceptance runners,
new shared native PowerShell/Python isolation helpers, focused tests, RELEASING.md,
BUG_LIST.md, DECISIONS.md and this handoff. No product features, dependencies,
version bump, original media edits, or publication were part of this pass.

## Implemented

- Snapshot actual per-user LecturePack uninstall records in both registry views;
  preserve typed values, nested keys and exact shortcut bytes.
- Serialize installer gates through an exclusive recovery lease. Preserve
  conflicting foreign registry changes and keep the snapshot for recovery;
  shortcut restoration still runs if registry restoration raises.
- Uninstall the exact scratch app and restore prior integration in finally on
  both runners. Keep original and cleanup errors visible. Write successful
  acceptance evidence only after verified restoration.
- Refuse existing acceptance data instead of deleting prior directories.
- Use literal paths and environment data for quoted version paths. Resolve
  Windows PowerShell directly instead of relying on PATH.
- Keep the PowerShell validator native and include the helper beside it in kits.
  UTF-8 BOM preserves its intended Unicode profile path in Windows PowerShell.
- Local runtime/export gate explicitly selects Basic Study; live Study AI is
  separate. The updater harness now describes its configuration/synthetic
  sentinel honestly; it does not claim a real study-progress migration.

## Verified real behavior

- Guarded actual 2.1.3 → 2.1.4 install/update: both packaged health checks passed,
  actual updater selected and hash-verified the real installer, no orphans,
  and original registry/shortcut snapshots restored. real-upgrade.json.
- Deliberate one-second job timeout after a real 2.1.4 install: expected exit 1,
  original failure reported, scratch app uninstalled and host restoration
  verified. real-failure/clean-machine-result.json.
- Final normal installed acceptance: real processed lecture, 13 export files,
  restored completed job, exit 0, no orphan processes, Unicode/space profile,
  and verified registry/shortcut recovery. real-success/clean-machine-result.json.
- These are local development-host checks, not a clean Windows-machine claim.
  Earlier OBS-07 uninstall-registration preservation remains historically
  unverified because that original snapshot was never captured.

## Tests and retained diagnostics

Results: `C:\LecturePackScratch\results\installer-isolation`.
Data/state snapshots: corresponding scratch data folder and real test results.
- Focused: `22 passed in 1.99s`; expanded native/fault guard: `5 passed in 2.21s`.
- First focused failure was missing PowerShell on restricted PATH; direct Windows
  binary resolution fixed it. focused.txt is retained beside focused-2.txt.
- First full run: `3 failed, 2047 passed, 8 skipped, 1 warning in 268.45s`.
  Its restricted PATH omitted Git; two content-hygiene subprocesses and their
  nested checklist regression failed with WinError 2. No test was changed or
  weakened. Corrected PATH full run is in full-2.txt; final result recorded below.
- Final full suite: `2050 passed, 8 skipped, 1 warning in 251.46s (0:04:11)`.
  Log: full-2.txt. Native conflict/recovery and typed registry tests passed in
  this full run. No test was hidden, deleted or weakened.

## Next work

Current verification is complete; commit the passing checkpoint and provide
the requested categorized update. Continue toward the original handoff goals
under automatic phase approval: investigate OBS-04 with repeated measured
packaged shutdown runs, verify real multiple-link paste, verify packaged repair,
and resolve BUG-59 runtime restoration for CI. Clean-machine/affected-laptop/
scaled-installer checks and Authenticode remain unverified. Local 2.1.4 artifacts
remain unchanged, unsigned and unpublished. See AD-57 and the updated OBS-07.

Prior candidate and polish reports follow unchanged.

---

# Handoff: approved 2.1.4 installer/updater validation, 2026-10-03

Branch: `fix/ytdlp-caption-media-path`; worktree: existing `ytdlp-caption-fix`.
Polish checkpoint: `1abe82d`. User explicitly approved this next phase.
Canonical checkout and its unrelated edits remain untouched.

## Authorized phase and scope

Local 2.1.4 candidate build, installed acceptance, checksums, and a real
2.1.3 → 2.1.4 updater migration. Permitted changes: version metadata, changelog,
narrow packaging/test fixes, decision/bug records and this handoff. No new
features, dependencies, live AI provider calls, deployment, push, merge or tag.
Evidence: actual pytest output and real packaged runtime/installer results.

## Completed and verified

- Version surfaces are 2.1.4: Qt desktop, Windows resources, Inno fallback,
  Electron package and root lock metadata. Historical engine version retained.
- Official Electron + Python sidecar built with canonical CPU runtime, bundled
  Rust Study Core, yt-dlp/EJS/Deno and a clean PATH excluding Codex Poppler DLLs.
- Found/fixed DEF-064: release builder ignored LECTUREPACK_BUILD_ROOT and packaged
  an older repository candidate. Initial build log retained as build.txt; fresh
  corrected artifacts are from rebuild.txt. Regression verifies new ZIP bytes
  even when the stale default directory exists. See AD-56.
- Full pytest output: `2044 passed, 8 skipped, 1 warning in 268.74s (0:04:28)`.
  Log: `C:\LecturePackScratch\results\release-2.1.4-candidate\pytest.txt`.
  This run preceded the new packaging regression; the subsequently changed
  packaging/authority area passed `22 passed in 0.51s`, packaging-tests.txt.
  Skips include opt-in live provider and Qt-specific payload fixtures; the
  actual Electron installer was verified separately below.
- Installed real 2.1.3 in scratch, processed its bundled video as an ordinary
  persistent lecture with explicit Basic Study, produced slides/transcript and
  13 exports. Input hash stayed unchanged.
- Production updater module selected 2.1.4 from a controlled localhost feed,
  verified its real manifest, downloaded 465226669 actual installer bytes,
  matched SHA-256, and left no temporary download files.
- Installed those verified bytes over A: executable reports 2.1.4; all 30 saved
  lecture files remained byte-identical across installation; all 12 packaged
  health checks passed. Completed job restored as done on two real host launches.
- Fresh data profile on installed B passed all 12 local packaged acceptance
  requirements, including real processing, 13 exports, restore and clean exit.
  No renderer/bridge errors or orphan processes were observed.
- Portable executable/sidecar bytes match the built candidate; renderer app.js
  and bridge.js match current source. Only canonical demo video is shipped,
  no jobs/data directories or incompatible Poppler ICU DLL were found.

## Local artifacts (unsigned, fast compression)

`C:\LecturePackScratch\builds\release-2.1.4-candidate\artifacts`

- Setup SHA-256: `0f65eaeed6260be5bce8dd5a40976f1be709be685a4a7f04650026d130769062`
- Portable SHA-256: `ce22bece11c74afe3b3d212c2c3a0f92faf58c7a4c80d214dbd2036931a1d712`
- SHA256SUMS and release manifest describe those exact local artifacts.
- Scratch evidence: installer-upgrade.json, installed-fresh/acceptance-result.json,
  portable-identity.json, host-cleanup.json, installation/uninstall logs under
  `C:\LecturePackScratch\results\release-2.1.4-candidate`.
- Reproduction wrapper: real_installer_upgrade.py under the corresponding scratch
  logs folder. It uses shipped JSONL commands and real binaries, selects Basic
  before start_job, and uninstalls in finally. No synthetic lecture output.

## Test-host cleanup limitation (OBS-07)

The test uninstaller exited 0, removed the scratch app and actual enumerated
LecturePack uninstall keys, and left no processes. /NOICONS nevertheless rewrote
existing Start Menu/SendTo launchers. They were restored to the existing 2.0.2
installation and its uninstaller; that old installed binary was not updated.
The wrapper's preliminary registry guard used a literal key spelling different
from Inno's actual key. Prior registry values were not captured; original
uninstall-registration preservation is unverified. Do not claim pristine host
restoration. Future installer acceptance needs an isolated VM or a complete
snapshot of actual keys and shortcuts before mutation.

## Approval gate and unfinished work

The approved local installer/updater phase passed its functional gates. Stop
before another phase under AGENTS.md. Not published, signed, pushed, merged or
tagged. These artifacts are local fast-compression candidates, not final signed
release bytes. Signing/rebuilding requires regenerating hashes and repeating
artifact gates. Clean-machine/affected-laptop/scaled-installer tests, real multiple
link paste, BUG-59 CI payload restoration, OBS-04 shutdown flakiness, and the new
OBS-07 harness isolation remain outstanding. The successful local Basic Study
acceptance does not establish live provider health.

Prior polish and historical phase reports follow unchanged.

---

# Handoff: 2.1.4 candidate polish, 2026-10-03

Branch: `fix/ytdlp-caption-media-path` in the existing `ytdlp-caption-fix` worktree.
Base: `76ed1ce`. Canonical checkout remains on `codex/ai-first-study`; its unrelated
uncommitted edits were preserved. The pasted Oct 2 handoff remains the release context.

## Authorized maintenance scope

Fix first-job Home lifecycle, add BUG-71 regression coverage, reconcile duplicate
ledger IDs, and verify locally. Touched files: Qt engine adapter, shared app.js,
focused tests, BUG_LIST.md, DECISIONS.md, and this handoff. No dependencies,
version changes, original media changes, deployment, push, merge or publication.

## Completed

- Normal Qt starts publish the real library after the controller starts its stage.
- Continue hides a saved Process destination for done jobs while retaining paused
  processing and meaningful Review/Study resume destinations.
- BUG-71 executes the shipped closeReady callback and reducer against deferred
  object/JSON bootstrap responses. It fetches once and renders five Ready rows.
- Duplicate newer ledger IDs are DEF-061/062/063 and OBS-05/06. Old IDs remain on
  old defects; the ledger alias note resolves historical handoffs and code comments.
- Settings fixture storage timer stub corrected for its existing fake backend;
  assertions were retained.
- Full suite: `2044 passed, 8 skipped, 1 warning in 255.17s (0:04:15)`.
  Log: `C:\LecturePackScratch\results\handoff-polish\full.txt`.
- Initial focused run: 67 passed, 1 failed because the nested settings test used
  MagicMock as a Qt timer context. Its storage stub was corrected before the
  successful full run; original failure log retained as focused.txt.

## Packaged verification completed

Isolated PyInstaller candidate: `C:\LecturePackScratch\builds\handoff-polish\dist\LecturePack`.
Canonical CPU runtime copied from this worktree and standard Qt pruning applied.
- `30 passed in 103.58s (0:01:43)` for packaged smoke/repair, payload hygiene,
  and pruning with the isolated candidate as LECTUREPACK_ONEDIR_FIXTURE.
- Fresh-profile real Browse import of the bundled Polar Bears video as a normal
  persistent job: HEALTHY admission; one running Home card, empty state hidden;
  Processing Continue visible during the run and hidden after completion;
  two real detected slides; original video SHA-256 unchanged; exit 0;
  no LecturePack/FFmpeg/Whisper processes remained.
- Report: `C:\LecturePackScratch\results\handoff-polish\packaged-home.json`.
- Logs and scratch harness: `C:\LecturePackScratch\logs\handoff-polish`.

### Build-environment findings

The first build invocation lacked repository PYTHONPATH during hidden-import
collection; it was rebuilt with PYTHONPATH set explicitly. The rebuilt app then
failed importing QtCore because PyInstaller collected `icuuc.dll` from the Codex
runtime's Poppler folder on PATH. Source Qt loads `C:\Windows\System32\icuuc.dll`.
The generated incompatible DLL was moved to scratch logs as `poppler-icuuc.dll`;
the same candidate then launched and passed. No production packaging code or
runtime stack was changed. Final release packaging must use a clean PATH and
re-run launch acceptance; this disposable, corrected candidate is not an installer
or a published release. Failure reports remain beside the successful report.

The first CDP harness Browse call also timed out on the native modal dialog;
using the existing acceptance harness's threaded CDP pattern fixed the test driver.
The app itself required no change for that modal behavior.

## Remaining release gates

Owner approval before moving to the next phase. Push/update PR #8 needs owner
authorization; merge, stable tag and publication remain separate sign-off gates.
The version is still 2.1.3. Installer build, installed 2.1.3 updater migration,
checksum reconciliation, real multiple-link paste, clean machine acceptance,
successful repair inside the packaged build, BUG-59 CI payload restoration and
OBS-04 shutdown flakiness remain outstanding. No live provider/network integration
was claimed by the local regression suite.


---

# LecturePack Phase 9 Handoff

**Branch:** `luna/phase9-product-app`
**Date:** 2026-08-04
**Status:** Desktop implementation and packaged acceptance complete; affected-laptop gate pending

## Completed

- Production Electron shell uses the existing HTML/CSS/JavaScript UI, a
  context-isolated preload, and the packaged JSONL Python sidecar.
- DeepSeek commits integrated: `a218438`, `115c66d`, `a897690`, `fed6b29`,
  `cc82367`, `2e43eba`, and `3d09f06`.
- Renderer adapter maps implemented queue, local/URL import, settings, study,
  AI/provider, runtime, notification, review, and export operations to exact
  contract payloads. DEFERRED operations remain untouched.
- Renderer queue handling now preserves the contract's active/rows/schedules
  envelope, consumes study-progress checkpoints, refreshes jobs after deletes,
  and keeps title-based grouping visible when no explicit group is stored.
- `jobs_changed` remains a direct array at the renderer boundary; `ai_token`
  remains plain text; sidecar JSONL uses ASCII-safe escaping.
- The Electron adapter now exposes the historical runtime-recheck/repair
  methods without crossing the deferred sidecar boundary. Recheck uses
  `health_check`; an unavailable in-place repair produces an explicit
  reinstall-required UI state instead of a renderer exception.
- Packaged sidecar includes PySide6 only as an internal backend dependency, with
  no Qt window or WebEngine view, plus FFmpeg, whisper.cpp, the bundled model,
  demo video, and frozen yt-dlp provider support.
- Portable ZIP, Inno Setup EXE, and SHA256 manifest were generated.
- The refreshed candidate excludes legacy Electron entrypoints and ignores
  nested build-time `node_modules`/`__pycache__` directories in the ASAR.

## Evidence

- Renderer/contract parity repairs are committed as `081cbea`, with the
  ownership-test stability follow-up `fa58eda`; runtime-boundary repair is
  committed as `30d87bf`.
- Focused bridge/study/runtime/release tests: `83 passed, 1 skipped`.
- Full suite with the disposable legacy onedir fixture:
  `1174 passed, 3 skipped, 1 warning`.
- Packaged acceptance result:
  `C:\LecturePackPhase9Results-luna-beta15-final5\acceptance-result.json`
  reports `passed: true`, 13 export files, `restore_passed: true`, empty
  renderer/bridge error lists, and `orphan_processes: []`.
- Packaged URL capability probe: `media_link_support` returned
  `available: true`, version `2026.07.04`, and the sidecar shut down with exit
  code 0.
- The final-candidate URL probe used the host shutdown drain and returned
  `ready: true`, `available: true`, and `exit_code: 0` from
  `C:\LecturePackPhase9UrlProbe-final5b-disposable`.
- `npm run validate`: passed; final ASAR audit found only
  `electron-bridge.js`, `production-main.js`, and `production-preload.js`
  among the Electron entrypoints.

## Artifacts

- Candidate:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\LecturePack-win32-x64`
- Portable:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-Portable.zip`
- Setup:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-Setup.exe`
- Hashes:
  `C:\Users\marsh\Documents\LecturePack-luna-phase9\electron-spike\dist\releases\0.9.0-beta.15\LecturePack-0.9.0-beta.15-SHA256SUMS.txt`

Portable SHA-256: `99668ac31498e1253054d84327a9e0916abcaba5f063c5561061c8cc66c3c605`
Setup SHA-256: `99c089612157dbaf51cf53c01e42ca2f43d90949ce2e1f4e595c6d726b63a65e`

## Remaining gate

Run the portable candidate on the affected laptop with a newly deleted data
directory: cold launch, import a real lecture, process to completion, review
slides/transcript, export Study Pack, close, reopen, confirm restoration, and
check ten-minute idle, resizing/theme switching, no flicker/black interval,
no renderer crash, and no orphan Python/FFmpeg/whisper processes. Do not call
the build Beta 15 until that manual result is recorded.

Updater, historical spike modes, and other contract operations marked
DEFERRED remain outside this handoff.

---

## Desktop QoL polish pass — 2026-08-09

**Branch:** `sol/qol2.0`
**Base HEAD:** `655975f9deccd557ae511a24b8f06ce0c0865c1e`

### Completed

- Conservative display-title cleanup now applies at normal `Job` creation;
  exact source path/filename remain unchanged, and manifest-backed rename is
  available inline and from lecture context menus.
- The header title opens the recent/current lecture switcher and continues to
  use the existing viewed-job state independently from the processing slot.
- The global processing strip shows authoritative percent, a guarded smoothed
  ETA, and queued count; Process navigation shows the active/waiting workload.
- State-aware renderer context menus reuse existing navigation, queue, retry,
  cancel, export, reveal, rename, and delete commands.
- Electron restores safe visible window bounds/maximized state. Existing
  per-job resume state is paired with the selected lecture/main screen and
  explicit navigation retains priority.
- Multi-line URL input queues sequential background transfers around the
  existing `MediaFetcher`. The compact Downloads panel supports collapse,
  active cancel, waiting removal, retry, details, and clearing completed rows;
  successful transfers enter the unchanged normal import path.

### Follow-up audit hardening

- Each background download now uses an item-specific destination directory,
  preventing repeated or same-title URLs from reusing another transfer's file.
- Probed media titles survive the handoff into the normal import path.
- The lecture switcher always retains both the selected and actively processing
  lectures even when they are older than the 12-row recent list.
- Download action replies include the current authoritative snapshot, reliable
  yt-dlp speed is visible in the panel, long indicator titles truncate safely,
  and Escape closes the lecture switcher/context menu cleanly.
- The obsolete blocking single-download modal code was removed; live progress
  now updates the compact background panel and remains reconciled by
  `downloads_changed` events.

### Evidence

- Follow-up audit: `npm run validate` passed; the expanded bridge,
  queue/import, media, and QoL set passed `187 passed`; the corrected full run
  returned `1303 passed, 1 skipped, 2 failed`, with only the same two missing
  `LECTUREPACK_ONEDIR_FIXTURE` gates failing.
- Follow-up packaged rebuild and launch smoke passed. Disposable candidate:
  `C:\LecturePackScratch\builds\desktop-qol-audit-touchups\LecturePack-win32-x64`;
  executable SHA-256:
  `7604E2D5B9F0CA7CED960FD128C4D112E6298658ED116A3404307435538AC3CA`.
- JS validation: `npm run validate` passed.
- Focused desktop/bridge/queue/import set: `108 passed`.
- Final full-suite run: `1303 passed, 1 skipped, 2 failed`. Both failures are
  legacy runtime-fixture gates: the Electron onedir intentionally does not have
  legacy-root `bin/ffmpeg.exe` or `smoke/runtime-smoke.wav`. All product and QoL
  tests passed.
- Electron packaged rebuild succeeded. Portable ZIP and hashes are under
  `C:\LecturePackScratch\builds\desktop-qol-pass`.
- Packaged acceptance: PASS for launch, sidecar/runtime readiness, processing,
  slides/transcript, 13 exports, restart restore, renderer/bridge errors, and
  orphan processes. Evidence:
  `C:\LecturePackScratch\results\desktop-qol-pass\acceptance-result.json`.
- Packaged UI check used
  `C:\LecturePackScratch\data\desktop-qol-pass-acceptance`: ugly local filename
  cleaned while source remained visible; rename survived restart; header
  switcher selected another lecture while its row showed `Processing 86%`;
  maximized bounds and Transcript screen restored after restart.
- Real batch check used two license-unrestricted Samplelib MP4 links. The UI
  confirmed `Download 2`, remained navigable on Transcript while the indicator
  showed `70% · 1 waiting`, and both completed files became normal imported jobs.
  Clean shutdown left no LecturePack, sidecar, yt-dlp, FFmpeg, or whisper process.

### Known limitations

- The legacy QtWebEngine visual-acceptance helper cannot attach its DevTools
  port to the Electron candidate; the Electron packaged acceptance gate passed.
- Cancel/retry is covered by focused regression tests but was not manually
  timed against the fast public sample transfers.

---

## QOL/Productivity stabilization re-audit — 2026-08-08

**Branch:** `kimi/qol-productivity-pass`

### Fixed

- Global transcript search is reachable from the header and Ctrl+K, waits for
  the selected lecture payload, then centers/highlights the exact timestamp.
- Queue all applies the selected batch mode/quality and starts the first job
  immediately when the active slot is idle; FIFO promotion remains unchanged.
- Windows taskbar progress keeps the authoritative overall percent instead of
  being overwritten by indeterminate pipeline events. The global strip now
  refreshes on every live status update.
- Resume state stores the transcript section's real scroll offset, saves on
  app close, and continues to honor explicit navigation overrides.
- Completed lectures opened from Ctrl+K route to Review; live/queued lectures
  route to Process.
- Search, palette, batch import, and the global processing strip now participate
  in native keyboard semantics, dialog labeling, live announcements, and the
  shared focus trap. The header no longer overflows at the 640px minimum width.

### Verification

- `npm run validate`: passed.
- Focused Electron/QOL suite: `96 passed`.
- Full suite: `1279 passed, 1 skipped`; the only two failures require the
  external `LECTUREPACK_ONEDIR_FIXTURE` and are unrelated to this pass.
- Packaged Electron acceptance: PASS for launch, sidecar/runtime readiness,
  real demo processing, slides, transcript, 13 exports, clean exit,
  relaunch/restore, no renderer/bridge/unexpected errors, and no orphan
  processes. Evidence:
  `C:\LecturePackScratch\results\qol-packaged-acceptance-20260808\acceptance-result.json`.

### Correct release artifact

- Portable Electron ZIP:
  `C:\LecturePackScratch\builds\qol-electron-release-20260808\LecturePack-0.9.0-beta.15-Portable.zip`
- SHA-256:
  `18780b972386d3d915bd7c650b5b43dce8c4f26e2cc887ac5a12f7cd78fd5caa`
- Manifest:
  `C:\LecturePackScratch\builds\qol-electron-release-20260808\LecturePack-0.9.0-beta.15-SHA256SUMS.txt`

`dist-release\LecturePack-portable-1.2.0.zip` is a legacy PyInstaller/Qt
artifact and does not contain the Electron QOL implementation. Do not use it
as the Phase 9/QOL candidate.

### Remaining manual gate

The affected-laptop fresh-data acceptance gate remains required before calling
the candidate Beta 15. This re-audit does not replace the separate physical
flicker/idle/resize observation.
