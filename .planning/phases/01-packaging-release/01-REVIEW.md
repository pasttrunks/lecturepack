---
phase: 01-packaging-release
reviewed: 2026-07-18T17:49:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - lecturepack/__init__.py
  - lecturepack/constants.py
  - build_release.py
  - LecturePack.spec
  - tests/test_packaging_and_safety.py
  - tests/test_alignment.py
findings:
  critical: 2
  warning: 2
  info: 0
  total: 4
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-07-18T17:49:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

The canonical version flow, assertion-preserving PyInstaller setting, and added
alignment tests are internally consistent, and the retained evidence proves the
current source suite and current generated package passed their recorded gates.
However, the documented `python build_release.py` entry point does not encode
the fail-closed cleanup and input-validation guarantees used for that one build.
It can delete unapproved content and can report success for an incomplete future
release. The generated checksum inventory also demonstrably omits the primary
CPU Whisper runtime, and one human-facing build label remains stale.

## Critical Issues

### CR-01: Direct release builds can recursively delete unapproved files

**File:** `build_release.py:92-97`

**Issue:** `main()` passes `dist`, `build`, and `dist-release` directly to
`shutil.rmtree()` after only an `isdir()` check. The allowlisted pre-deletion
inventory recorded for the current release was an external, one-off execution
guard; it is not part of the build entry point advertised at line 7. A later
operator can therefore lose manually placed or unexpected files under those
directories, and the script does not itself prove that each deletion target is
the expected non-reparse child of the repository. This is a data-loss risk even
though the current build was run with a safe external preflight.

**Fix:** Move the cleanup contract into `build_release.py`. Before deleting,
resolve and normalize each target, require its parent to equal the resolved
project root and its leaf to be exactly `build`, `dist`, or `dist-release`,
reject symlinks/junctions/reparse points, inventory `dist-release`, and abort on
any root entry outside an explicit generated-release allowlist. Add a unit test
that proves unknown entries and redirected targets fail before any removal.

### CR-02: Missing required release inputs are downgraded to warnings

**File:** `build_release.py:120-165`

**Issue:** Missing FFmpeg executables, the CPU Whisper executable/DLL set, and
all three release documents only print warnings; a partially present Vulkan
directory is also copied piecemeal. The script then creates the ZIP and exits
successfully. Consequently, a future build can be labeled complete while core
transcription/media functions or required notices are absent. The current
1168-entry onedir and dual frozen self-tests prove only that this particular
input tree happened to be complete; the self-test does not exercise FFmpeg or
Whisper processing.

**Fix:** Validate the entire required FFmpeg, CPU Whisper, and documentation
input inventory before cleanup or PyInstaller execution, report all missing
paths, and exit nonzero if any are absent. Treat Vulkan as optional only when
its directory is absent; if present, require the full `VULKAN_BINS` set or omit
the engine atomically with an explicit result. Add tests for missing required
inputs and a partial Vulkan set.

## Warnings

### WR-01: CPU Whisper files are silently omitted from checksum metadata

**File:** `build_release.py:195-205`

**Issue:** CPU Whisper files are copied to `app_dir` at lines 131-140, but the
checksum loop looks for every `WHISPER_BINS` entry under `bin_dir`. It also never
iterates `WHISPER_CPU_DLLS`. The current `BUILD_MANIFEST.json` confirms the
effect: it contains the ZIP, FFmpeg, and Vulkan entries but no primary
`whisper-cli.exe`, `whisper.dll`, `ggml*.dll`, or CPU-variant DLL entries. The
whole-ZIP digest still protects the archive as a unit, but the advertised
per-binary inventory is incomplete and cannot be used to diagnose or verify the
primary local engine independently.

**Fix:** Build checksum entries from explicit `(absolute_path, archive_path)`
pairs: FFmpeg under `bin/`, `WHISPER_BINS + WHISPER_CPU_DLLS` under the app root,
and Vulkan under `bin/vulkan/`. Fail if any required checksum source is missing,
and test that every required runtime appears exactly once in both checksum
outputs.

### WR-02: The build script retains a stale release label

**File:** `build_release.py:3`

**Issue:** The module header still identifies the tool as `LecturePack v0.2.1`
while its canonical executable version and generated artifacts are 1.2.0. This
contradicts AD-14's requirement that human-facing build labels remain
synchronized and creates avoidable release-review ambiguity.

**Fix:** Remove the version from the static header, or generate/display it from
`VERSION` so future version bumps cannot leave this label stale.

---

_Reviewed: 2026-07-18T17:49:00Z_
_Reviewer: generic-agent workaround (gsd-code-reviewer role)_
_Depth: standard_
