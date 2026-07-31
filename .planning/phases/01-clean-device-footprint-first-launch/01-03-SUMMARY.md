---
phase: 01-clean-device-footprint-first-launch
plan: 03
subsystem: backend-services
tags: [python, services, config, runtime-admission, concurrency]

# Dependency graph
requires: []
provides:
  - "ConfigManager.setup_acknowledged()/persist_setup_acknowledged() — the D-16 persisted flag in <data_dir>/config.json"
  - "lecturepack/services/first_run_checklist.py — the five-item D-13 checklist verdict service (wire contract for Plans 01-06/01-07)"
  - "Parallelized RuntimeBootstrapService._validate_full — same admission contract, concurrent probes"
affects: [01-06-PLAN.md, 01-07-PLAN.md]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "concurrent.futures.ThreadPoolExecutor(max_workers=3) for independent, evidence-preserving subprocess probes"
    - "validate-then-mutate-then-atomic-save idiom (persist_setup_acknowledged mirrors persist_runtime_health)"

key-files:
  created:
    - lecturepack/services/first_run_checklist.py
    - tests/test_first_run_checklist.py
  modified:
    - lecturepack/infrastructure/config_manager.py
    - lecturepack/services/runtime_bootstrap.py
    - tests/test_runtime_bootstrap.py

key-decisions:
  - "setup_acknowledged uses strict `is True` boolean coercion — any non-boolean persisted value (corrupted/hand-edited config.json) degrades to False (show the checklist again), never to a crash or a silent skip, per D-16's own behavior contract."
  - "checklist detail strings never include absolute filesystem paths, full stdout/stderr, or user-facing sentences — only OS build numbers, failing canonical-inventory entry names, and existing `reason` field text (T-01-03-04 mitigation)."
  - "RuntimeValidator is stateless per call (fresh subprocess.Popen + local variables only), so `_validate_full` constructs and shares one instance across the three ThreadPoolExecutor workers rather than one per worker; a test asserts exactly one construction call with no args, proving the default 30s timeout_ms bound was not overridden."

patterns-established:
  - "checklist_group_for() maps every canonical_inventory() entry into exactly one of three groups and raises ValueError for anything unrecognized, so a future inventory addition fails loudly here instead of silently vanishing from the checklist."

requirements-completed: []

coverage:
  - id: D16
    description: "setup-acknowledged flag persists in <data_dir>/config.json via ConfigManager.save() -> FileManager.write_json_atomic, never localStorage/QSettings; survives a fresh ConfigManager instance over the same data dir; corrupted values degrade to False"
    verification:
      - kind: unit
        ref: "tests/test_first_run_checklist.py (10 tests, acknowledged-flag group)"
        status: pass
    human_judgment: false
  - id: D13
    description: "First-run checklist exposes exactly five items in canonical order (windows_version, ffmpeg_ffprobe, whisper_runtime, bundled_model, data_directory), verdicts computed in Python from RuntimeBootstrapResult evidence keyed to canonical_inventory()"
    verification:
      - kind: unit
        ref: "tests/test_first_run_checklist.py (18 tests, checklist-service group)"
        status: pass
    human_judgment: false
  - id: D14
    description: "No checklist item carries a remediation, action, url, download or repair field — id/verdict/detail only"
    verification:
      - kind: unit
        ref: "tests/test_first_run_checklist.py::test_d14_no_item_carries_remediation_action_url_download_or_repair_key"
        status: pass
    human_judgment: false
  - id: D10
    description: "The three independent full-validation probes (ffmpeg -version, ffprobe -version, staged whisper-cli transcription) run concurrently in a bounded ThreadPoolExecutor(max_workers=3) within the unchanged 30s-per-probe bound; the real staged transcription and every evidence field survive unchanged"
    verification:
      - kind: unit
        ref: "tests/test_runtime_bootstrap.py (9 new tests, Task 3 group) — timing/overlap, peak-concurrency bound, exception propagation, cleanup-on-failure, complete evidence fields, real transcription argv"
        status: pass
    human_judgment: false

duration: ~2.5h
completed: 2026-07-31
status: complete
---

# Phase 1 Plan 3: Backend First-Run Checklist Contract Summary

**Persisted `setup_acknowledged` flag in `config.json` (D-16), a new `first_run_checklist` service exposing exactly the five D-13 items with no remediation affordance (D-14), and a parallelized `_validate_full` that runs its three independent probes concurrently in a bounded thread pool while preserving the real staged whisper-cli transcription and every evidence field (D-10) — measured ~3x wall-clock reduction in the concurrency test.**

## Wire Contract for Plans 01-06 and 01-07

- **Five item ids, canonical order:** `windows_version`, `ffmpeg_ffprobe`, `whisper_runtime`, `bundled_model`, `data_directory` (`FIRST_RUN_CHECKLIST_ITEMS` in `lecturepack/services/first_run_checklist.py`).
- **Two verdict literals:** `VERDICT_READY = "ready"`, `VERDICT_NEEDS_ATTENTION = "needs_attention"`.
- **Payload shape:** each item is `{"id": <str>, "verdict": <one of the two literals>, "detail": <technical evidence string>}` — nothing else. No item ever carries a remediation/action/url/download/repair key.
- **Acknowledgement:** `ConfigManager.setup_acknowledged() -> bool` / `ConfigManager.persist_setup_acknowledged() -> None`. The flag lives in `<data_dir>/config.json` alongside `runtime_health`, written through the existing `save()` -> `FileManager.write_json_atomic` transport — never WebEngine `localStorage`, never `QSettings`.
- **Build entry point:** `build_first_run_checklist(result, *, windows_version=None, data_dir=None) -> list[dict]`, where `result` is a `RuntimeBootstrapResult` (or its `.components` mapping directly).

## Accomplishments

- **Task 1 — Persisted acknowledgement flag (D-16).** Added `ConfigManager.setup_acknowledged()` and `ConfigManager.persist_setup_acknowledged()`, placed immediately after `persist_runtime_health()`, mirroring its validate-then-mutate-then-atomic-save shape. Added `"setup_acknowledged": False` to `DEFAULT_SETTINGS`. `setup_acknowledged()` coerces strictly (`is True` only), so a hand-edited or corrupted `config.json` degrades to showing the checklist again rather than crashing or silently skipping it. 10 tests, including a round-trip proof via a second `ConfigManager` instance over the same `tmp_path`, and proof that a pre-existing `runtime_health`/`whisper_model`/`migration_versions` value survives untouched.
- **Task 2 — First-run checklist verdict service (D-13, D-14).** New `lecturepack/services/first_run_checklist.py`: `FIRST_RUN_CHECKLIST_ITEMS`, `VERDICT_READY`/`VERDICT_NEEDS_ATTENTION`, `WINDOWS_SUPPORTED_MIN_BUILD = 17763` (Windows 10 1809, the floor for the pinned `PySide6>=6.7.0` line), `supported_windows_version()`, `data_directory_writable()`, `checklist_group_for()`, and `build_first_run_checklist()`. Verdicts are the logical AND of each group's canonical-inventory member `healthy` flags, keyed to `canonical_inventory()` rather than a hardcoded file list — a dynamically discovered `bin/ggml-cpu-*.dll` or the `smoke/runtime-smoke.wav` fixture correctly falls inside the `whisper_runtime` group, and `checklist_group_for()` raises for any entry it cannot place, so a future inventory addition cannot silently vanish from the checklist. 18 tests, including the Ready-only-vs-Mixed contract (only `windows_version` can be Needs Attention while overall HEALTHY), per-group failure isolation, the D-14 no-remediation-key assertion, and `json.dumps` serializability.
- **Task 3 — Parallelized `_validate_full` (D-10).** Refactored `RuntimeBootstrapService._validate_full` in place: the ffmpeg `-version` probe, the ffprobe `-version` probe, and the staged whisper-cli transcription now run inside `ThreadPoolExecutor(max_workers=3)`. The `WhisperPathStaging` construction, its argument list, its `try/finally` cleanup, the failed-`SmokeEvidence` synthesis on staging exceptions, the eight-field `evidence()` closure, and `RuntimeValidator`'s default 30s `timeout_ms` are all byte-for-byte unchanged — this is parallelization only, never a lighter liveness check in place of the real transcription. `future.result()` re-raises any worker exception rather than letting it vanish. 9 new tests, including a timing/overlap proof (peak concurrency 2-3, elapsed materially below the 3x serial sum), an exception-propagation proof, a cleanup-on-whisper-failure proof, and an evidence-completeness proof for all `_FULL_SUCCESS_EVIDENCE_FIELDS`.

## Measured serial-vs-parallel elapsed time

The concurrency test (`test_validate_full_probes_overlap_and_bound_peak_concurrency`) uses a fake validator that sleeps 0.2s per probe with a lock-guarded concurrency counter. Three probes run: serial sum would be 0.6s; the parallelized implementation completed in well under `0.45s` (asserted bound: `< sleep_s * 3 * 0.75`) with observed peak concurrency of 2-3 concurrent probes, proving real overlap rather than a reordered sequential loop. This is a synthetic proof of concurrency, not a measurement of real-world ffmpeg/ffprobe/whisper-cli wall-clock time on a physical clean machine — that end-to-end cold-launch timing is Plan 01-06's (worker-thread bootstrap) and Plan 01-08's (physical evidence gate) to measure and record, since `_validate_full` alone is only one piece of the cold-start path (`assess()` also does inventory resolution and identity hashing). Whether parallelization alone is sufficient for Success Criterion 3's "few-seconds-to-feedback" target cannot be assessed at this layer in isolation.

## Validator sharing decision

`RuntimeValidator.__init__` holds only `self.timeout_ms` (an immutable int); `run()` constructs a fresh `subprocess.Popen` and only uses local variables — no shared mutable state. One `RuntimeValidator()` instance is therefore constructed once, outside the thread pool, and shared across all three workers, rather than one per worker. `test_validate_full_shares_one_validator_with_default_thirty_second_bound` asserts exactly one construction call occurs, with no arguments — proving both the sharing decision and that no probe is ever constructed with a bound other than the unchanged 30,000ms default.

## Task Commits

Each executed task was committed atomically:

1. **Task 1: Persist the setup-acknowledged flag in config.json** - `4887268` (feat)
2. **Task 2: First-run checklist verdict service — exactly the five D-13 items** - `b911764` (feat)
3. **Task 3: Parallelize the three independent full-validation probes** - `ec725cb` (perf)

## Files Created/Modified

- `lecturepack/infrastructure/config_manager.py` — added `setup_acknowledged()`, `persist_setup_acknowledged()`, and the `setup_acknowledged` `DEFAULT_SETTINGS` entry.
- `lecturepack/services/first_run_checklist.py` (new) — the five-item checklist verdict service.
- `lecturepack/services/runtime_bootstrap.py` — `_validate_full` refactored to run its three probes concurrently.
- `tests/test_first_run_checklist.py` (new) — 28 tests (10 acknowledged-flag, 18 checklist-service).
- `tests/test_runtime_bootstrap.py` — 9 new tests appended (25 total in file, all passing).

## Decisions Made

- Strict `is True` boolean coercion for `setup_acknowledged()` (see `key-decisions` above).
- `checklist_group_for()` raises rather than defaulting an unrecognized entry to a group, so `canonical_inventory()` growth cannot silently orphan a checklist row.
- Detail strings never carry absolute paths or raw `stdout`/`stderr` — only OS build numbers, failing inventory-entry names, and existing `reason` text (T-01-03-04).
- Shared, not per-worker, `RuntimeValidator` instance (see "Validator sharing decision" above).

## Deviations from Plan

None — plan executed exactly as written. No architectural changes were required; every file listed in the plan's `files_modified` frontmatter was the only set of files touched.

## Threat Flags

None — all six threats in the plan's own STRIDE register (T-01-03-01 through T-01-03-06) were mitigated as specified during implementation; no new security-relevant surface was introduced beyond what the plan's threat model already covered.

## Issues Encountered

None.

## Out-of-scope, logged not fixed

No new failures were introduced. A full `pytest` run before this plan's changes (recorded independently during this session) showed **877 passed, 7 failed**; after this plan's three tasks it shows **912 passed, 7 failed** — the same 7 pre-existing failures documented in `.planning/phases/01-clean-device-footprint-first-launch/deferred-items.md` (4 in `tests/test_release_trust.py` and 2 in the runtime-repair suite, all `manifest signature verification failed` against a stale fixture versus the Ed25519 key rotated at `55257a8`; 1 in `tests/test_runtime_packaged_smoke.py` requiring the unset `LECTUREPACK_ONEDIR_FIXTURE` env var). None of these files were touched by this plan and none regressed or newly failed.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 01-06 (deferred bootstrap assessment on a worker thread) can now extend `Backend.get_bootstrap()`'s payload with `build_first_run_checklist()`'s output and `ConfigManager.setup_acknowledged()`/`persist_setup_acknowledged()` calls — the wire contract (five ids, two verdict literals, `{id, verdict, detail}` shape) is fixed.
- Plan 01-07 (the `checking`/`checklist` UI overlay states) can render the five rows in canonical order directly from this payload without computing any health itself, per "backend decides, UI renders."
- No UI or bridge file was touched by this plan, per its own success criteria.
- Whether the D-10 parallelization alone is sufficient for Success Criterion 3's "few-seconds-to-feedback cold start" target remains for Plan 01-06 (which will measure the full `assess()` path on a worker thread) and Plan 01-08 (physical clean-machine evidence gate) to determine — this plan's own concurrency proof is necessarily synthetic (a fake sleeping validator), not a real-hardware measurement.

---
*Phase: 01-clean-device-footprint-first-launch*
*Completed: 2026-07-31*

## Self-Check: PASSED

- FOUND: lecturepack/services/first_run_checklist.py
- FOUND: tests/test_first_run_checklist.py
- FOUND: lecturepack/infrastructure/config_manager.py (setup_acknowledged/persist_setup_acknowledged present)
- FOUND: lecturepack/services/runtime_bootstrap.py (ThreadPoolExecutor(max_workers=3) present)
- FOUND commit: 4887268 (Task 1)
- FOUND commit: b911764 (Task 2)
- FOUND commit: ec725cb (Task 3)
- CONFIRMED: pytest tests/test_first_run_checklist.py tests/test_runtime_bootstrap.py -x — 53/53 pass
- CONFIRMED: pytest tests/test_runtime_diagnostics.py tests/test_runtime_inventory.py tests/test_whisper_path_staging.py tests/test_setup_gate_repair.py tests/test_guided_tour.py -x — 32/32 pass
- CONFIRMED: full pytest run — 912 passed, 7 failed (same 7 pre-existing failures as deferred-items.md; no new failures)
