# Windows Run Handoff — completing the v1.0 unified release

> **STATUS: COMPLETED on 2026-07-15 (native Windows).** All remaining items below
> were executed and verified: full test suite (53 passing), real whisper.cpp
> transcription, live ground-truth detector run (balanced preset P=1.00/R=1.00),
> transcript-layer + product-mode wiring, version bump to 1.0.0, PyInstaller
> onedir build + portable ZIP with checksums, tag `v1.0.0-unified`, push, and
> GitHub release. See `CHANGELOG.md` and `RELEASE_NOTES.md`. The original handoff
> notes are retained below for provenance.

---


This increment was produced in a Linux sandbox that has the repository files
mounted but **not** the Windows runtime. That environment cannot execute the
Windows binaries (`whisper-cli.exe`, `ffmpeg.exe`), cannot install OpenCV /
PySide6 (PyPI is blocked), cannot access the local video files, and cannot push
to GitHub. So the parts that require real execution were intentionally left for
this Windows run rather than being faked.

## What was done and verified here (Linux, standard library only)

- **Safety checkpoint** created before any change:
  - working branch `claude-v1-unified` at commit `69b2eca`
  - tag `safety/start-v1-unified` at that checkpoint
  - `v0.4.1-balanced-detection` left untouched at `aa19732`; no tags moved; no
    files deleted; `C:\Users\marsh\LecturePackData` never touched.
- **Layered transcript service** — `lecturepack/services/transcript_service.py`
  with 19 passing tests (`tests/test_transcript_layers.py`).
- **Detector ground-truth evaluator** — `lecturepack/services/detection_eval.py`
  + `tests/fixtures/ground_truth/synthetic_lecture.json` + harness
  `tests/scratch/run_detection_eval.py`, with 7 passing metric tests
  (`tests/test_detection_eval.py`).
- Docs: `docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md`,
  `docs/SLIDE_DETECTION_EVALUATION.md`, `CHANGELOG.md`.

All new `.py`/`.md` files were written via shell redirection and verified to
contain **zero null bytes**.

## First: clean up two sandbox artifacts (required before git works on Windows)

The sandbox mount could not delete files or clean up git lock files. Before
using git on Windows, run:

```
del .git\config.lock .git\HEAD.lock .git\index.lock
del .probe_write_test .wtest_bash.txt .wtest_cp.txt
rmdir /s /q lecturepack\services\__pycache__   REM removes a stale Linux .pyc
```

(The three `.git\*.lock` files are empty and safe to delete; they are stale
locks left by the sandbox's FUSE mount. `git config` was rewritten to a valid
default — re-add your identity/remote below.)

## Then verify the increment on Windows

```
git status
.venv\Scripts\python.exe -m pytest tests/test_transcript_layers.py tests/test_detection_eval.py -v
.venv\Scripts\python.exe tests\scratch\run_detection_eval.py --preset balanced
```

The detector harness will now actually run (OpenCV present) and print
precision/recall/F1 against the ground truth. Tune the progressive-build
clustering in `cv_engine.py` until `meets_targets` passes on the short fixture,
then run the Egypt short clips, then one full-lecture pass.

## Commit, remote, and the rest of the v1.0 checklist

```
git add lecturepack/services/transcript_service.py ^
        lecturepack/services/detection_eval.py ^
        tests/test_transcript_layers.py tests/test_detection_eval.py ^
        tests/fixtures/ground_truth/synthetic_lecture.json ^
        tests/scratch/run_detection_eval.py ^
        docs/TRANSCRIPTION_AND_CONTEXT_REPAIR.md ^
        docs/SLIDE_DETECTION_EVALUATION.md CHANGELOG.md docs/WINDOWS_RUN_HANDOFF.md
git commit -m "v1: layered transcript service + detector ground-truth evaluator (tested)"

git remote add origin https://github.com/pasttrunks/lecturepack.git
gh auth status
git push -u origin claude-v1-unified
```

Remaining work to reach the verified v1.0 (per the original brief), all of which
needs this Windows environment:

1. Wire the transcript layers into `JobController` / `MainWindow` (raw →
   normalized → optional Context Repair) and the three product modes
   (Study Pack / Transcript Only / Slides Only).
2. Build the Context & Names panel and confidence-aware review UI on top of the
   already-tested service functions.
3. Finish progressive-build clustering/hysteresis in `cv_engine.py` and pass the
   ground-truth targets on short clips; one full Egypt pass reusing cached audio.
4. Real pytest-qt UI tests; real whisper.cpp transcription validation.
5. PyInstaller onedir build; validate `LecturePack.exe` from a path with spaces
   outside the source tree; produce `dist-release/` ZIP + `SHA256SUMS.txt` +
   `BUILD_MANIFEST.json` + `RELEASE_NOTES.md`.
6. Tag `v1.0.0-unified` (do not move older tags), push, and create the private
   GitHub Release with the portable ZIP + checksums (no models/videos/job data).

Nothing above was faked here; each item is left in a clean, honest state for
real execution and verification on Windows.
