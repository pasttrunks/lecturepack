# D-20 taskbar icon diagnosis — findings

**Gathered:** 2026-07-31, by the orchestrator on the real packaged and installed builds.
**Plan:** 01-05, Task 1 (`checkpoint:human-verify`).
**Requirement:** D-20 forbids assuming the cause. It must be *determined on the packaged
build* before any fix is written. D-21 requires that the missing-icon path stop failing
silently regardless of which cause holds.

## The two candidates D-20 named

**(a)** No `SetCurrentProcessExplicitAppUserModelID` call exists anywhere in `app/`, so
Windows may not associate the window with the installed executable's identity.

**(b)** `setWindowIcon` at `app/desktop/main.py:107` is guarded by an `os.path.exists`
check with no `else` branch, so a missing `.ico` fails silently.

CONTEXT called (a) the stronger suspect because the `.ico` *is* present in the built output
and *is* stamped into the exe — but required confirmation rather than assumption.

## Verdict

### (b) is RULED OUT

Measured on the **installed** build (silent per-user install of the post-cut
`LecturePack-0.9.0-beta.6-Setup.exe` into a temp directory, launched with a fresh profile,
window handle `4852118`):

| Query | Result |
|---|---|
| `WM_GETICON` / `ICON_BIG` | `0x109A4` — set |
| `WM_GETICON` / `ICON_SMALL` | `0x309A2` — set |
| `WM_GETICON` / `ICON_SMALL2` | `0x309A2` — set |
| `GetClassLongPtr` / `GCLP_HICON` | `65579` — non-null |
| `GetClassLongPtr` / `GCLP_HICONSM` | `343411077` — non-null |
| `lecturepack.ico` beside the installed exe | present |

All three window icon slots and both class icon slots are populated, and the `.ico` ships.
`setWindowIcon` is doing its job; the guard at `main.py:107` is not silently swallowing a
missing file in this build. Candidate (b) is not the cause.

### (a) is the only remaining explanation — but the symptom did not reproduce

`SetCurrentProcessExplicitAppUserModelID` is confirmed absent:

```
grep -rn "SetCurrentProcessExplicitAppUserModelID\|AppUserModelID" \
    --include=*.py --include=*.iss app/ lecturepack/     ->  no matches
```

Without an explicit Application User Model ID, Windows derives taskbar identity implicitly
from the process's executable path. That is the mechanism by which a taskbar button can
lose its association with an installed app's identity — the documented failure mode matching
the owner's report of a correct title-bar icon alongside a blank taskbar icon.

**However, the blank taskbar icon did NOT reproduce here.** Both launches showed a correct
icon in the title bar *and* the taskbar:

| Launch | Taskbar button name | Icon observed |
|---|---|---|
| onedir exe directly, fresh profile | `LecturePack — lecture transcription & study - 1 running window` | present, correct |
| installed build, fresh profile | `LecturePack - 1 running window` | present, correct |

One observable difference: the direct launch's taskbar button carries the exe's full
`FileDescription`, the installed one only `LecturePack`. That is a naming difference, not an
icon failure, and is consistent with identity being derived implicitly rather than declared.

## What this means for the fix

1. **Do not "fix" `setWindowIcon`'s happy path** — it works. Candidate (b) is closed.
2. **Add `SetCurrentProcessExplicitAppUserModelID`** anyway. It is the correct way to declare
   a stable taskbar identity, it is the only mechanism left that explains the reported
   symptom, and it must be called *before* the first window is created to take effect. The
   ctypes idiom is already established in-repo by `WindowsIntegration`
   (`app/desktop/win_integration.py`), which hand-rolls `ITaskbarList3` — follow that file's
   lazy-import / try-except / silent-degrade-off-Windows shape so an OS-integration failure
   can never block startup.
3. **D-21 is independent of the diagnosis and still required.** The `os.path.exists` guard at
   `main.py:107` must stop failing silently — log or surface a missing `.ico` rather than
   skipping `setWindowIcon` without a word. This is worth doing precisely *because* (b) was
   ruled out here: the guard is currently untested against a genuinely missing file, and a
   future packaging change that drops the `.ico` would reintroduce a silent failure.

## Honest limits of this diagnosis

- **The owner's symptom was not reproduced**, so the fix is justified by mechanism and by
  the absence of any competing explanation — not by a reproduction. Say so in the SUMMARY;
  do not claim the blank icon was observed and fixed.
- The owner's report was made against a **beta-6** installed build. This diagnosis ran against
  a **beta-7 post-cut** build, which differs (D-01 cuts, D-24 excludes, the BUG-27 correction,
  and 01-06/01-07's startup changes). A cause that was present in beta-6 and is masked here
  cannot be excluded.
- Conditions not tested: a **pinned** taskbar shortcut; launching via a **Start Menu**
  shortcut (the silent install created none at
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\LecturePack.lnk`); and the state
  immediately after an **in-app update** replaces the executable. Any of these could surface
  the identity problem that a direct launch does not. If a reproduction is wanted before
  shipping the fix, a pinned shortcut is the most likely trigger.
- Taskbar icon presence was determined from Win32 icon handles and the accessibility tree
  rather than from pixels, because an unrelated fullscreen application occupied the display
  during the installed-build run. Handle-level evidence is stronger than a screenshot for
  "is an icon set", but it does not prove what a human sees rendered.
