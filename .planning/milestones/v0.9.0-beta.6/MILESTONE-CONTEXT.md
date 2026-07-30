# Milestone v0.9.0-beta.6: Clean-Machine Reliability and Onboarding

**Gathered:** 2026-07-27
**Status:** Approved for requirements and roadmap planning
**Authoritative baseline:** `v0.9.0-beta.5`, tag `v0.9.0-beta.5`, commit `459faf5`

## Milestone Boundary

Beta 6 makes the portable beta dependable on clean Windows machines and teaches the main LecturePack workflow. It covers bundled-runtime initialization and verification, empty launch ownership, a hard setup/repair gate, concise guided onboarding with a real synthetic demo lecture, visual-artifact fixes that preserve beta 5's design language, and a real clean-machine release gate.

No implementation begins until the roadmap and the current phase plan receive explicit user approval.

## Locked Decisions

### Release boundary

- Beta 6 is the full onboarding release, not a narrow hotfix.
- The obsolete `.planning` v1.2 packaging roadmap is historical metadata; beta 5 and the current `app/` package are authoritative.
- Work is split into approval-gated phases. Only one phase may be implemented at a time.

### Required-runtime setup gate

- Required processing components are FFmpeg, ffprobe, CPU Whisper CLI plus required DLLs, and the bundled base English model.
- If any required component is missing or corrupt, the app uses a hard setup gate; users cannot enter the main app until checks pass.
- Healthy first launches initialize silently and continue to the empty Home screen.
- Failed checks offer one consented **Repair all** action showing source and download details.
- If online repair is unavailable, users may retry, open diagnostics, or exit. Beta 6 will not include offline repair-package import or manual per-file browsing.
- A successful repair revalidates everything and enters LecturePack automatically without restart.

### Runtime selection and validation

- A healthy optional CUDA or custom engine remains selected across upgrade, while the bundled CPU runtime is always verified as the recovery path.
- A broken optional engine falls back to bundled CPU and produces a visible notice; it never triggers the hard gate when bundled CPU is healthy.
- On beta-6 upgrade, `ggml-base.en.bin` becomes the default selected model. Other installed models remain available for manual reselection.
- Lightweight checks run every launch. Full executable/DLL/model smoke checks run on first launch, after update or repair, or when payload identity changes.

### Empty launch and ownership

- Startup never auto-opens the latest completed lecture.
- Home begins with no active lecture. Existing jobs remain visible in the library and open only after an explicit user action.
- No design-time, packaged, or demo lecture may appear as a permanent normal job.

### Guided onboarding

- After the first successful runtime check, show a welcome choice: **Start guided demo** or **Skip for now**. Do not auto-start the tour.
- The tour is concise and covers only LecturePack's main value and core workflow.
- Use user-controlled Next and Back steps with arrows, circles, and spotlights anchored to the actual interface.
- Keep a persistent, obvious **Exit demo** action.
- The demo is replayable from Settings.
- Bundle an original synthetic 45–90 second lecture with simple slides and narration. It must contain no university, student, or third-party copyrighted content.
- Process the demo through the real offline pipeline: import, process, transcript/slide review, study-pack generation, and export-location explanation.
- Demo work uses an isolated temporary workspace, never appears in the library, is deleted on normal exit, and is swept safely after cancellation or crash.

### Visual preservation

- Preserve beta 5's existing animation language, timing, transitions, hard dark shadows, and pressed/embedded button effect.
- Do not redesign, simplify, modernize, or reduce the intentional visual character.
- Visual changes are limited to removing unintended flicker, flashes, repaint artifacts, overflow, and layout jumps.
- Theme switching is atomic so the whole palette changes in one frame without unintended per-element color flashes.
- Long local-model names use ellipsis with the full value available by tooltip on hover/focus.
- Keep standard motion; do not add reduced-motion behavior in this milestone.
- Visual regression checks compare beta 6 against the beta-5 appearance and motion contracts.

### Repair trust and installation

- Repair downloads come only from the official LecturePack GitHub release for the exact running app version.
- Beta 6 embeds a project public key, verifies a project-signed manifest, and checks every payload with SHA-256 before installation.
- Never mix runtime components across LecturePack releases.
- Repair is transactional: download and verify into staging, replace only after the full set passes, and restore the previous runtime on any failure.
- Repair network access requires the explicit user action already described; no telemetry or unrelated network requests are permitted.

### Clean-machine release gate

- Public beta 6 is blocked until physical Windows coverage exists for CPU-only, NVIDIA, and AMD/Intel graphics machines, with both fresh and upgraded profiles.
- A fully offline fresh-profile test must launch, pass bundled-runtime checks, process the bundled demo, review results, and export successfully.
- Mandatory hostile-path cases include non-admin portable folders, spaces, non-ASCII usernames/paths, and a separate writable data directory.
- In disposable package copies, each required component is separately removed or corrupted. Tests must prove the hard gate, one-click repair, signature/hash verification, transactional recovery, and successful entry afterward.
- Completion evidence includes targeted test output, the full pytest output, actual packaged subprocess smoke output, GUI fresh-profile smoke evidence, and the physical-machine matrix.

## Research Findings Already Confirmed

- `ConfigManager` initializes all four core paths as empty.
- FFmpeg auto-detects during controller construction; Whisper discovery exists but is called only by diagnostics.
- The desktop adapter validates empty Whisper paths before processing reaches engine discovery.
- Packaging copies the required CPU runtime/model but only checks presence and nonzero size.
- Startup currently calls `_load_latest_completed_job()` and activates an existing lecture.
- No general signed/transactional core-runtime repair path exists today.
- `LECTUREPACK_DATA_DIR` is an existing disposable-profile seam suitable for packaged tests.

## Non-Goals

- No new transcription provider, cloud workflow, account system, telemetry, or analytics.
- No change to the selected PySide6/PyInstaller architecture or dependency stack without a separately approved ADR.
- No redesign of the web desktop UI.
- No offline repair-package import or manual browsing for required runtime files.
- No permanent demo job or fake persisted lecture.
- No implementation of later phases before the current phase passes tests and receives explicit approval.

## Canonical References

- `AGENTS.md` — phase discipline, safety, testing evidence, and Git rules.
- `docs/PRODUCT_SPEC.md` — product behavior, local-first constraints, privacy rules, and first-release boundaries.
- `docs/ARCHITECTURE.md` — approved layer/process architecture and historical addenda.
- `docs/DECISIONS.md` — locked technical decisions; any new material decision must be recorded here.
- `docs/IMPLEMENTATION_PLAN.md` — original system plan and safety constraints; version claims that conflict with beta 5 require reconciliation.
- `app/desktop/engine_adapter.py` — startup ownership, processing gate, and desktop bridge integration.
- `lecturepack/infrastructure/config_manager.py` — persisted runtime paths and current discovery logic.
- `lecturepack/infrastructure/transcription_engines.py` — bundled CPU and optional engine discovery.
- `app/packaging/build.py` — current portable payload and presence-only validation gate.
- `tests/test_packaging_and_safety.py`, `tests/test_beta3_packaging.py`, `tests/test_adapter_startup.py`, `tests/test_workspace_ownership.py` — reusable test coverage and seams.

