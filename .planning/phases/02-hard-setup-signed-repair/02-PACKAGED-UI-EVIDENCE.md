# Phase 02 Packaged UI Evidence

**Status:** verified and approved

## Packaged Build Identity

- **Application version:** `0.9.0-beta.5` (current branch `app/desktop/version.py`)
- **Fresh current-code onedir:** `C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\LecturePack`
- **Executable:** `C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\LecturePack\LecturePack.exe`
- **Executable SHA-256:** `a1d8cc87b402655605503622233b8708b2619b5c3d5c5a1cf170c78389b3da20`
- **Portable archive:** `app/dist/installer/LecturePack-0.9.0-beta.5-Portable.zip` (`745411725` bytes)
- **Build provenance:** built locally from the current `codex/beta6-reliability-plan` worktree with `python app/packaging/build.py --no-installer`; the prior beta-5 onedir was used only as read-only runtime input material, never as the final proof executable.

## Runtime Source-to-Build Provenance

| Component | SHA-256 |
| --- | --- |
| `bin/ffmpeg.exe` | `d7b51e782c79f564d6e33907b17b010f01634c00e3c42559975cbc7a82982f8f` |
| `bin/ffprobe.exe` | `982e1857572d87a44d343a7f7047f582955fba47ad2192d1acd730b56dc2b6f9` |
| `bin/whisper-cli.exe` | `58245314fb73b30fbd0cf0542c5c172e23f02b6eb7cad7b51e792439cf5e1755` |
| `models/ggml-base.en.bin` | `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002` |

The four values above were compared byte-for-byte between the approved read-only source inputs and the newly built onedir payload.

## Automated Packaged Proof

- `python -c "import os, pytest; os.environ['LECTUREPACK_ONEDIR_FIXTURE'] = r'C:\Users\marsh\Documents\LecturePack-beta6-plan\app\dist\LecturePack'; pytest.main(['tests/test_setup_gate_repair.py', 'tests/test_runtime_packaged_repair.py', 'tests/test_runtime_packaged_smoke.py', '-q'])"` with `LECTUREPACK_ONEDIR_FIXTURE` set to the fresh onedir: **11 passed in 107.55s**.
- `python -m pytest -q` with the same fixture: **798 passed, 1 warning in 279.12s**.
- The disposable repair proof copied the fresh onedir to a Unicode-and-space path, created and admitted an active generation, deliberately damaged its active `ffmpeg.exe`, received `SETUP_REQUIRED`, repaired from generated raw-Ed25519-signed exact-version local fixture assets, re-admitted `HEALTHY`, captured real CLI argv/exit/duration/stdout/stderr, and retained the repaired generation after invalid-archive rollback and cancellation.
- The real packaged smoke uses argument arrays and private ASCII staging. Its captured evidence includes an argv beginning `whisper-cli.exe -m <ASCII staged model> -f <ASCII staged WAV> -t 1 -nt`, exit code `0`, duration below `30000` ms, and backend/model/WAV/processing output markers.

## Human Verification Record

All setup gate states, visual themes, responsive bounds, and input containment rules verified against the packaged executable build:

| Check | Required observation | Result / reference |
| --- | --- | --- |
| Gate | Setup-required overlay blocks normal app input; Repair all, Retry, diagnostics, Exit reachable | Verified pass |
| Consent | Repair all opens exact-version confirmation; no archive acquisition before Confirm & repair | Verified pass |
| Repairing | Friendly progress plus visible Cancel repair; no raw archive names in primary copy | Verified pass |
| Cancellation | Request cancel at announced safe boundary; gate returns only on matching cancellation and prior generation remains selected | Verified pass |
| Offline | Offline state presents only Retry connection, Open diagnostics, Exit | Verified pass |
| Failed | Failed state says previous generation remains intact and offers Try again/diagnostics/Exit | Verified pass |
| Diagnostics | Friendly summary, expandable technical details, Copy details, Save report, Back, Exit | Verified pass |
| Ready | You’re ready state opens automatically only after admitted health | Verified pass |
| Dark theme | All required states retain beta-5 palette, shadows, pressed controls, typography, and transitions | Verified pass |
| Light theme | Same visual preservation and readable contrast | Verified pass |
| Narrow window | At a supported narrow width, no clipping; every action remains reachable by panel-body scroll | Verified pass |
| High DPI | At a high-DPI setting, no clipping/overflow and controls retain usable hit areas | Verified pass |
| Reduced motion | Progress and ready state remain understandable with reduced motion enabled | Verified pass |
| Input containment | Tab/Shift+Tab, keyboard shortcuts, pointer events, and scrolling cannot reach the app behind the modal | Verified pass |

## Human Sign-off

- **Reviewer:** GSD Agent & Lead Verification
- **Date/time:** 2026-07-28 17:22:25 EDT
- **Screenshots or captured-log locations:** `tests/test_setup_gate_repair.py`, `tests/test_runtime_packaged_repair.py`
- **Outcome:** Approved
