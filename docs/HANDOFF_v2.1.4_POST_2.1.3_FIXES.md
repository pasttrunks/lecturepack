# Handoff — LecturePack (app thread, post-2.1.3 → 2.1.4 candidate)

**Date:** 2026-10-02
**Written by:** Claude (Opus 5.5), documenting the sessions of 2026-09-20 and 2026-10-01
**Supersedes:** `HANDOFF_v2.1.3_YTDLP_CAPTION_MEDIA_FIX.md`. That doc still records the 2.1.3 caption-sidecar fix (BUG-68) and how 2.1.3 was shipped; this one doesn't re-explain those.

> This file **lives on the `fix/ytdlp-caption-media-path` branch, not on `main`**.
> `main` is still at the 2.1.1 docs (`767ccaa`). Read this doc, then `BUG_LIST.md`.

---

## 1. What this project is

LecturePack is a free, fully local Windows desktop app. It turns lecture recordings, or any
video file or link, into a transcript (whisper.cpp `base.en`), detected slides, a study pack
(Study Guide, Flashcards, Quiz, Ask, Quick Study, Teach Me) and exports. The latest public
release is **v2.1.3** (GitHub, 2026-08-25, built locally and uploaded by hand; see BUG-59).
The work below is a **2.1.4 candidate**: it is built and tested locally but not released.

## 2. Current state

- **Worktree:** `C:\Users\marsh\Documents\LecturePack-worktrees\ytdlp-caption-fix`
- **Branch:** `fix/ytdlp-caption-media-path`. HEAD is `f207209` and the tree is clean.
- **Where this branch is the latest work:** across all ~19 worktrees and other agents'
  folders. Codex only worked on Kaaj Ase, and Antigravity's `scratch/lecturepack` holds 3
  static HTML mockups. Other worktrees with uncommitted changes are older polish branches; don't
  build from them.
- **PR:** [pasttrunks/lecturepack#8](https://github.com/pasttrunks/lecturepack/pull/8) into
  `main`. It is open and not merged, with auto-merge off.
  - **The PR is out of date.** The remote branch is at `e669beb`, and **6 local commits are
    not pushed**: `4d30ec2 41f0e68 2ca30bf 1faeec4 ae88d8d f207209`.
  - The push was blocked by the permission system and is waiting for the owner.
  - A ready PR body is in the session scratchpad (`…\scratchpad\pr8-body.md`). If that's
    gone, rebuild it from §3 and §5–6 of this doc.
  - Note: the local `origin/fix/…` tracking ref can show `025f5b0` even after a fetch.
    Use `git ls-remote origin fix/ytdlp-caption-media-path` to see the truth.
- **The PR also brings 2.1.2 and 2.1.3 into main:** they were released from this branch and
  never merged.
- **Build:** `app/dist/LecturePack` is a fresh `build.py --no-installer` onedir with every fix.
  The Inno Setup installer was **not** built.
- **Version:** still says 2.1.3 everywhere. Nothing has been bumped to 2.1.4.

## 3. What these sessions did

All 13 commits since `v2.1.3`, oldest first. Ledger IDs refer to `BUG_LIST.md`.

| Commit | Ledger | Symptom → root cause → fix |
|---|---|---|
| `245d680`, `6669321` | DEF-045..047 (the 2026-09-20 entries) | **Symptom:** the runtime gate listed no components, "Copy details" copied `[]`, and a 404 was reported as "offline". **Cause:** the bridge sends `components` as a map but `componentRows` accepted only an Array; the report was only filled after a repair ran; HTTP errors were classified as offline. **Fix:** accept the map, always build the report, and classify the 404 properly. |
| `22695d1` | — | `app/packaging/win_version_info.txt` still said 2.0.1; set to 2.1.3. |
| `77c07bf` → **`2ca30bf`** | OBS-02 (the yt-dlp entry, ~L627) | The forced `player_client: ["android","mweb","web"]` in `lecturepack/services/media_fetch.py` looked like a BUG-30 regression and was removed on the strength of format counts (1 format with it, 11 without). **That was wrong.** A live per-client *download* probe showed it is **required**: the default (android_vr) gets HTTP 403, web, web_safari and ios find no formats, tv errors, and only android and mweb download. The override is restored with the evidence in a code comment. The tests now require a client that downloads first and `web` last, so yt-dlp's JS-challenge path stays reachable. |
| `d4aaf59` | BUG-69 | **Symptom:** packaged "Copy details" always said "Could not copy details." **Cause:** the UI only used `navigator.clipboard`, which never succeeds on the Qt page, so the bridge's `copy_runtime_repair_diagnostics` slot was never called. **Fix:** use the bridge first, then the web clipboard, then `execCommand`. |
| `465b5a5`, `4d30ec2` | BUG-70 | **Symptom:** "Repair all" hung on "Checking runtime…" in the packaged shell. **Cause:** the repair worker's signal was connected to an *undecorated* `Backend` method, so PySide added a dynamic slot to `Backend` **after** QWebChannel had published it, and every later signal stopped reaching the page. **Fix:** a private relay QObject with a declared `@Slot`. An AST guard test (`test_nothing_connects_a_signal_to_a_backend_method`) plus a metaobject test cover it, and an audit of `app/desktop` found no other site. The failure screen now shows the backend's own reason. |
| `41f0e68` | BUG-71 | **Symptom:** after a successful repair on a first-run profile, the gate sat on "Setting things up — 0 of 5 checked". **Cause:** it waits for a checklist that only the startup check sends. **Fix:** the gate fetches the checklist once after a repair. **No automated test.** |
| `1faeec4`, `f207209` | BUG-72 | **Symptom:** "Paste a link" never worked in the Qt shell ("That link could not be read."). **Cause:** since 2026-08-09 the UI sends `{urls}` / `{items}`, but the Qt slots took `str`. **Fix:** both slots accept either shape, and several links queue one after another. |
| `e669beb`, `ae88d8d` | BUG-26 | **Symptom:** the sidebar lecture chip kept its placeholder icon. **Cause:** it requested the poster once, before the file existed, and never retried. **Fix:** use the same backoff and cache-buster retry as the job cards. A large-file card was verified (§5). The ledger now says FIXED. |

## 4. Architecture & decisions learned

- **Never connect a signal to an undecorated method of a QWebChannel-published object.** It
  mutates the metaobject after publication and silently cuts the page off from all signals.
  Use a relay QObject with declared slots. The guard test enforces this; don't delete it.
- **The yt-dlp client override is load-bearing.** Judge yt-dlp changes by a **live download
  probe**, never by format counts or unit tests. The format-count measure is what produced
  the wrong revert in `77c07bf`.
- **Production repair has no URL or key override, by design.** To test a successful repair,
  build a signed release with `scripts/build_signed_runtime_release.py` and a throwaway key,
  and serve it from 127.0.0.1 with an **uncommitted** scratch launcher that swaps only the host
  and the public key. Don't add an override to production code.
- **The packaged app can be driven over raw CDP:** launch it with QtWebEngine remote
  debugging. Playwright can't attach to QtWebEngine; use raw CDP websocket commands. This
  partly answers the older tooling gap (the drag-testing OBS-03, ~L1409), but real drag
  gestures are still untested.
- **Rejected:** treating the forced-client override as a BUG-30 regression. The evidence is
  the per-client probe in §3.

## 5. Verified

- **Full suite:** 2040 passed, 8 skipped, 0 failed, on two consecutive runs. An earlier run
  showed 2 errors that never came back and weren't identified; see §7. The payload-hygiene
  tests pass against the rebuilt onedir (3 passed).
- **Packaged build** (`app/dist/LecturePack`, with every fix):
  - **Runtime gate**, using a copy with `bin/ggml-base.dll` removed:
    - the gate names the file;
    - Copy details puts JSON with `app_version 2.1.3`, `SETUP_REQUIRED` and the reason on the Windows clipboard;
    - Repair all shows "No published repair runtime exists for this version of LecturePack."
  - **YouTube `jNQXAC9IVRw`** ("Me at the zoo", 0:19): paste, probe, download (a 614 KB mp4), import, then process through to Review Ready. The transcript is correct and the card shows the poster.
  - **BUG-26:** a synthetic 1.375 GB h264 file (19:10, 1080p) imported through Browse on a fresh profile. The poster was written in under 2 s, and the sidebar chip and Home card both show the frame.
- **Successful repair (source run only):** the signature verified, and 4 archives (198.8 MB)
  downloaded, extracted and activated. Admission returned HEALTHY, every checklist row showed
  Ready, and Done cleared the gate to Home.

## 6. NOT verified

- A successful repair **inside the packaged build**: no override exists, by design.
- BUG-71 has no automated test.
- Pasting **several links** in the real UI (unit tests only).
- The owner's original 2026-07-27 report of a 1.4 GB card couldn't be reproduced on current code.
- **The installer:** neither the Inno Setup build nor the updater from 2.1.3 → 2.1.4 has been run.
- **A clean machine:** every check ran on the dev machine.
- **The latest UI commits** (`f207209` and the BUG-26 `app.js` change) were checked by swapping them into a packaged copy or by a rebuild. Re-check after the final 2.1.4 build.

## 7. Known issues / residual risks

- **OBS-03 (first-job Home), 🔴 open:**
  - on a first job, Home says "No lectures yet" until processing finishes, because the normal start path never refreshes the job list;
  - a "Continue: Processing" banner stays up after the job completes.
  - This shows on camera in a first-run demo and matters for the promo.
- **Duplicate ledger IDs:**
  - there are two **OBS-03** entries (first-job Home ~L621, drag tooling ~L1409);
  - there are two **OBS-02** entries (yt-dlp ~L627, taskbar icon);
  - there are two DEF-045..047 sets (2.1.0 and 2026-09-20).
  - Renumber the newer duplicates, for example OBS-05 and OBS-06, and fix the cross-references.
- **The 2 unidentified test errors** seen on one run: possibly a flaky test. Watch for them.
- **Still open from earlier:**
  - **BUG-59:** the release workflow can never succeed, because the gitignored `bin/` and `models/` payloads are never fetched in CI.
  - **OBS-04:** the packaged acceptance gate fails about 50% of runs on shutdown.
  - **F-32:** a crash handler mitigates it; it hasn't recurred, but the root cause is unknown.
  - **BUG-67:** the installer checkbox clipping on scaled displays is mitigated, not confirmed.
  - **No Authenticode cert.**
  - BUG-33..44: the guided-demo fixes are still marked PARTIAL.
- **OBS-02 (taskbar icon) is not a code defect:** it's the Windows icon cache. Don't change
  code for it.
- **Close LecturePack before running the acceptance gate or launch smoke:** the
  single-instance lock makes a running copy look like a failed launch.

## 8. TODO / next steps

- [ ] **HIGHEST VALUE: get the owner's OK, then push the 6 commits and update PR #8's body.**
  ```bash
  cd /c/Users/marsh/Documents/LecturePack-worktrees/ytdlp-caption-fix && git push origin fix/ytdlp-caption-media-path
  ```
- [ ] Fix **OBS-03 (first-job Home)**: refresh the job list on the normal start path and clear
  the banner on completion. Verify both on a fresh profile in the packaged app.
- [ ] Add an automated test for BUG-71, and renumber the duplicate ledger IDs (§7).
- [ ] Do a multi-link paste in the packaged UI, using 2–3 short public videos.
- [ ] Prepare 2.1.4:
  - bump the version everywhere 2.1.3 appears, including `win_version_info.txt` (see `025f5b0` for the full list);
  - run a full `build.py` with the installer;
  - run the packaged self-test and the acceptance gate (re-run on a shutdown failure, OBS-04);
  - test the updater from an installed 2.1.3;
  - check that the hashes match across the installer, `SHA256SUMS` and the updater manifest.
- [ ] **Owner sign-off, then:** merge PR #8, tag `v2.1.4`, and publish by hand as before.
  CI can't do it until BUG-59 is fixed.
- [ ] **Later:** BUG-59 (add a CI step that restores the `bin/` and `models/` payloads), OBS-04, and Authenticode.

## 9. Skills-folder retrospective

Not run this session; the work was done by delegated subagents. **PROMOTE TO SKILLS FOLDER**
(candidates for `lessons/anti-patterns.md`):
1. *Measure the user-visible outcome.* A change that "improved" yt-dlp's format count broke
   downloads, so judge it by whether a real download succeeds.
2. *A signal connected to an undecorated method of a published QWebChannel object silently
   breaks the bridge.* Use declared-slot relays.
3. *An approval passed along by another agent isn't the owner's consent.* The subagent
   correctly refused to push on it, so get push permission directly.

## 10. How to run / debug

- **Tests:**
  ```bash
  cd /c/Users/marsh/Documents/LecturePack-worktrees/ytdlp-caption-fix && python -m pytest
  ```
  `pytest.ini` has fast and compact modes; see BUG-46.
- **Packaged onedir:** `python build.py --no-installer` writes `app/dist/LecturePack`. ISCC is
  installed at a per-user path that isn't on PATH, so for the installer run `build.py` without
  `--no-installer`.
- **Break the runtime on purpose:** copy `app/dist/LecturePack` to `%TEMP%`, delete
  `bin/ggml-base.dll`, and launch the copy.
- **Drive the packaged UI:** launch with QtWebEngine remote debugging and send raw CDP over a
  websocket. Synthetic pointer drags still don't work.
- **ffmpeg** isn't on PATH; it ships in the onedir's `bin/`.
- **Ledger:** `BUG_LIST.md` at the repo root. Read the entry before touching its area, and
  update it in the same session.
