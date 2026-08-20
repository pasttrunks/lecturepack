# Handoff — LecturePack v2.0.9: the lost update the 2.0.8 review found but did not fix

**Date:** 2026-08-20
**Branch:** `claude/release-2-0-8-maintenance-13e69e`
**Base:** `b58f8f7` = v2.0.8 (tagged)
**Status:** **RELEASED** 2026-08-20 — https://github.com/pasttrunks/lecturepack/releases/tag/v2.0.9
(stable, not draft, not prerelease; four assets). Installer, portable zip, hashes and manifest all
produced from a clean release venv; packaged self-test green on all twelve checks.
Not signed (no Authenticode credentials — accepted by the owner for this release).

## What this was

Maintenance TLC on what 2.0.8 shipped, then the 2.0.9 version bump. 2.0.8's own commit
message logged BUG-47 as OPEN — a lost update that ships in the released build. That was
the whole target.

## Commits

| Commit | What |
| --- | --- |
| `7f05d10` | BUG-47 merge-on-save + BUG-48 unique atomic temp files, with regression tests |
| `8ff567e` | 2.0.9 version bump, changelog, handoff |
| `844a5e0` | UI polish pass: transient layer, shortcut discoverability, DEF-043 |

## The two findings

**BUG-47 — a background pass could throw away an answer the student cached.** The Study
expansion pass does `load_content` → gateway call (up to ~50s) → `save_content`. The pack
is `STUDY_READY` and live in the UI for that entire window, so an Ask or Teach Me answer
cached in it gets written back over by a snapshot that predates it. `_job_lock` does not
help: it protects each writer individually, not the interleaving.

Fixed by merge-on-save (`study_v2.save_content_preserving_cache`), **not** by widening the
lock — holding `_job_lock` across the gateway call would stall every UI read for ~50s,
which is exactly what the ledger entry warned against. The merge re-reads under the lock
and re-adds only the `cached_responses` keys its snapshot never saw, then drops any of
those whose concepts are absent from the content being written. All four slow-window
writers in `ai_study_service` use it.

**BUG-48 — every atomic JSON write shared one temp file name.** `write_json_atomic` used a
fixed `<name>.tmp`. `os.replace` is atomic, but the scratch file was a shared resource
across processes: the sidecar and the UI both persist job state, and two writers interleave
into one buffer before either rename happens. Each write now gets its own `mkstemp` buffer;
`reset_data_root` sweeps both the new `.<name>.<random>.tmp` shape and the historical one.

## The thing worth carrying forward

**The first version of the BUG-47 regression test passed against the unfixed code.** The
shared fixture gateway client returns one fixed flashcard that the pack built in `_prepare`
already contained, so dedup skipped every save in the expansion loop and the hazard was
never reached. It became a real test only once the client served unique material per call.
A concurrency test must be run against the unfixed line before it is trusted — a green
test on broken code is worse than no test, because it retires the suspicion.

## The UI polish pass (`844a5e0`)

Six small additions, designed against the existing system rather than invented —
Claude Design was consulted for the visual integration and its guidance is what
the code follows. No new tokens: the toast action reuses the pill it lives in,
the cheat sheet's key caps reuse `.lp-press-sm`'s resting shape, and Study's
stamp flash reuses Review's keyframes at a narrower box.

- **toast** — click to dismiss; an optional trailing action; 5s → 8s when it
  carries one; the countdown stops on hover.
- **Review undo** — stamping is undoable, runs coalesce into one offer, `Ctrl+Z`
  works with no toast on screen, and undo returns the cursor to the mistake.
- **shortcut discoverability** — `?` opens a cheat sheet; palette rows show their
  binding as quiet mono metadata. Same information, two registers.
- **Copy** on Ask / Teach Me answers, confirming in place.
- **Study stamp flash** — grading a card or answering a question flashes the
  graded region green/red the way Review flashes a slide.

**DEF-043, found while doing it:** `Space` advanced two slides per press, because
`btn-keep` grew its own advance in beta.5 and the Space branch — written later
against a J that did not advance — clicked `btn-next-slide` as well. Every second
slide was kept at its detector default without ever being displayed. Every test
passed: they all asserted the stamped state (correct) and none asserted the
cursor moved one step (the actual defect).

## Verified

- Full Python suite: **1937 passed, 25 skipped** (was 1917 at v2.0.8; +20 new tests).
  The 25 skips are the documented build-asset gates (packaged onedir fixture, the 148 MB
  Whisper model), absent on a bare checkout.
- `npm run validate` in `electron-spike/` — clean, and reports `lecturepack@2.0.9`.
- BUG-47's regression test confirmed **failing** with the fix reverted at the expansion
  save site, passing with it.
- **The UI additions were driven in a real Chromium**, not just asserted against the
  source: the renderer was served over HTTP and exercised through its own handlers.
  Space moves the cursor exactly one slide (0→1→2); a run of rejects coalesces to
  "Rejected 2 slides / Undo all"; `Ctrl+Z` restores both slides and returns the cursor
  to slide 0; the toast action undoes **and** dismisses; Copy copies the answer text
  without its own button label and swaps to "Copied" with the orange border for 1400ms;
  the cheat sheet lays out at 520px with keys flush right, key caps carrying the 2px ink
  border and hard offset shadow, an `rgba` backdrop, and no horizontal overflow. The
  only console error is `qrc:///qtwebchannel/qwebchannel.js` failing to load, which is
  expected outside Qt.

## NOT verified

- **Nothing was built or packaged.** No installer, no portable zip, no hashes, no manifest.
- **The fix has never run against a real pack on a real gateway.** Both entries are 🟡 in
  the ledger for that reason. The hazard is a race whose window is a live gateway call;
  the test drives it deterministically, which is not the same as observing it in the app.
- **No screenshot of the new UI.** The browser pane would not composite frames in this
  session, so every visual claim above is computed-style and geometry, not a picture.
  Worth one look at the cheat sheet and the toast action in the built app.
- **The runtime setup gate had to be hidden** to reach the app in a plain browser (no
  bridge means its checks never pass). That is the known dev-only workaround, not a
  finding.
- **Step 14 was verified from the feed, not from a running old build.** The published
  release is what the updater reads (latest, non-draft, x64 Setup asset present), the
  served manifest's SHA-256 matches the published installer byte-for-byte, and
  `updater.compareVersions` puts the installed build below 2.0.9. What was NOT done is
  launching the installed copy and watching it offer, download and apply the update.
  Note the machine's installed build is **2.0.2**, not 2.0.8 as assumed earlier.
- **No Authenticode signing.** `AUTHENTICODE SIGNING: NOT AVAILABLE` — unchanged, no valid
  credentials exist in this repo.
- Steps 4–14 of `RELEASING.md` (Rust Study Core build, sidecar package, installer build,
  packaged self-test, updater E2E, release gates, tag, publish) are all outstanding.

## Building it: two traps, both worth knowing before the next release

**Never build the sidecar with the system interpreter.** The first attempt used the
system Python and PyInstaller collected everything installed on the machine — the
candidate carried `jedi`, `django-stubs` and `sklearn` into `LecturePackSidecar`. It was
only caught because those deeply nested stub paths blew MAX_PATH and aborted ISCC; on a
shorter path it would have built and shipped. Build from a `.venv` created solely from
`requirements-release.txt` (plus the Study Core wheel), as `RELEASING.md` says.

**Inno Setup cannot build from a worktree path.** `…/.claude/worktrees/<name>/` adds ~50
characters over a normal checkout, and ISCC has no long-path support, so it aborts part
way through compression with "The system cannot find the path specified" — the D-23
failure recurring for a new reason. The fix used here: copy the packaged candidate to a
short path (`C:\lp29\cand`, verified byte-identical), run ISCC against that, then
`build_electron_release.py --hashes-only` so the published hashes describe the real
bytes. Everything before the installer step builds fine in place.

**`smoke/runtime-smoke.wav` is a build asset that exists in no checkout.** The runtime
inventory requires it, so a build cannot proceed without one. It was regenerated for this
release from 4 seconds of the demo lecture's own audio — real speech, which Whisper
transcribes correctly ("Behold the polar bear. Its fur is not white, but…"). Do NOT
substitute a tone: `_whisper_smoke_check` only asserts the process exits cleanly, so a
tone passes even against a broken model and quietly weakens the gate.

## To cut 2.0.9

Version surfaces are already at `2.0.9` — `app/desktop/version.py`,
`app/packaging/lecturepack.iss`, `electron-spike/package.json` and its lockfile. Pick up
`RELEASING.md` at step 3 and run it through. Do not move the `v2.0.8` tag.
