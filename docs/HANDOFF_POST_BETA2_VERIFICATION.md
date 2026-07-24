# Handoff — Post-beta.2 Verification (LecturePack)

_Verification pass 2026-07-23. Branch `feat/cuda-engine`._

Evidence (do not repeat here):
- `docs/evidence/current_session_status.json`
- `docs/evidence/public_beta_release/final/beta2_packaged_runtime.json`

## TL;DR
**beta.2 is already public and is verified release-ready as a product.** Its tag
(`v0.9.0-beta.2` → `deca663`) was **not** touched. Every machine-checkable release
gate passes. The only defect found was a **stale test double** (beta.2 shipped
with 1 failing test, no user impact); it is fixed and committed at `8fa428f` and
the full suite is green again. Two named validations remain **human/VM** steps.

## Git / version
- Starting HEAD: `de550c8` · Ending HEAD: `8fa428f` · Branch: `feat/cuda-engine`
- Safety tag: `safety/post-beta2-verify-de550c8`
- Published beta.2 = `deca663`; branch already carried **two post-beta.2 fixes**
  before this run (`4abc961` reset orphaned running jobs; `de550c8` window icon
  in frozen EXE + study-packs badge overflow). These are **beta.3 material**.
- `app/desktop/version.py` still reads `0.9.0-beta.2` (correct — do not bump until
  beta.3 is actually cut).

## What AGY did (accepted, not redone)
`deca663` fixed the beta.1 clean-machine failure: bundled the CPU whisper runtime
(`ffmpeg/ffprobe/whisper-cli`, `whisper.dll`, `ggml*.dll`, `ggml-base.en.bin`) and
made frozen-mode binary detection resolve `dirname(sys.executable)/bin`. Verified
present in the published Portable.zip and functional on real media. Published all
three assets; hashes are byte-for-byte identical to the local gate-verified build.

## The one defect (fixed)
`deca663` switched `FFmpegWrapper.detect_binaries()` from `config_manager.get(...)`
to `config_manager.autodetect_ffmpeg()`, but `test_study_workflow.py`'s
`MockConfigManager` was never updated → `test_retranscribe_only_stages` raised
`AttributeError` (1 failed / 347 passed at HEAD). Product code was always correct
(real `ConfigManager.autodetect_ffmpeg` exists; real transcription works). Fix
(`8fa428f`): add `autodetect_ffmpeg`/`autodetect_whisper` to the mock, mirroring
the real fallback contract. **Full suite at `8fa428f`: 348 passed, exit 0.**

## Gate status
| Gate | Result |
|---|---|
| Full suite @ final commit `8fa428f` | ✅ 348 passed (191.52s) |
| Real packaged transcription | ✅ bundled ffmpeg+whisper-cli+base.en on `m2-res_1080p.mp4`, 11 segs, valid timestamps, CPU only, no dev tools |
| Setup.exe / Portable.zip / SHA256SUMS exist | ✅ public + local |
| Published hashes match | ✅ local == SHA256SUMS.txt == GitHub digests (byte-for-byte) |
| Updater live discovery | ✅ public feed 200; beta.1→beta.2 selected; stable ignores prerelease; asset digest == verified artifact |
| No secrets | ✅ dist + source scanned |
| Upgrade preserves data | ✅ structural (stable AppId, `LecturePackData` outside `{app}`) — live upgrade is human |
| Clean-profile install | ⚠️ HUMAN/VM pending |
| Updater GUI click-through | ⚠️ HUMAN pending (logic covered by 22 tests) |
| Working tree | `README.md` modified pre-run (unrelated to release) |

## Recommended beta.3 scope (do NOT auto-publish)
beta.3 = the two post-beta.2 product fixes (`4abc961`, `de550c8`) + the test fix
(`8fa428f`). Cutting it is a deliberate, user-authorized step:
1. Bump `app/desktop/version.py` → `0.9.0-beta.3` (+ `win_version_info.txt`).
2. Build on a box with Inno Setup 6 (`app/packaging/build.py`) — release-asset gate.
3. Tag `v0.9.0-beta.3`, publish pre-release, upload 3 assets, verify published hashes.
4. Human: clean-VM install + live beta.2→beta.3 in-app upgrade preserving data.

## Rollback
`git reset --hard de550c8` (this run's start). Does not touch `LecturePackData`.
