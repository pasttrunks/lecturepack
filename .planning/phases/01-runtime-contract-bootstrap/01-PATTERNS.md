# Phase 1: Runtime Contract & Bootstrap - Pattern Map

**Mapped:** 2026-07-28  
**Files classified:** 14 proposed/modified files  
**Analogs found:** 14 / 14

## Scope and naming boundary

The symbols below are **proposed Phase-1 symbols**, not existing public APIs, unless an item is explicitly marked *existing*. The plan should not describe them as already implemented. Exact names remain discretionary, but use one canonical inventory export; no second payload list may be introduced.

## File Classification

| New/Modified File | Role | Data Flow | Closest analog | Match quality |
|---|---|---|---|---|
| `lecturepack/infrastructure/runtime_inventory.py` | model/utility | transform + file-I/O | `app/packaging/build.py` | role-match |
| `lecturepack/infrastructure/runtime_validation.py` | service | request-response + file-I/O | `lecturepack/infrastructure/ffmpeg_wrapper.py` | role-match |
| `lecturepack/services/runtime_bootstrap.py` | service | request-response/state transition | `lecturepack/infrastructure/transcription_engines.py` | role-match |
| `lecturepack/infrastructure/config_manager.py` | config | CRUD + migration | `lecturepack/infrastructure/file_manager.py` | exact persistence pattern |
| `lecturepack/infrastructure/transcription_engines.py` | service/model | request-response | existing `EngineRegistry.resolve` | exact extension seam |
| `app/desktop/engine_adapter.py` | adapter/controller | event-driven startup | existing `LecturePackAdapter` lifecycle | exact modification seam |
| `app/desktop/main.py` (and, only if needed, `bridge.py`) | composition/controller | event-driven startup | existing `main()` | exact composition seam |
| `app/packaging/build.py` | build config | batch + file-I/O | existing `check_clean_state`/`bundle_engine` | exact modification seam |
| `docs/DECISIONS.md` | ADR/config | static contract | existing decision-log format | role-match |
| `tests/test_runtime_inventory.py` | test | transform/file-I/O matrix | `tests/test_beta3_packaging.py` | role-match |
| `tests/test_runtime_bootstrap.py` | test | request-response/fault matrix | `tests/test_cuda_engine.py` | role-match |
| `tests/fixtures/mock_runtime_hang.py` | test fixture | process/event-driven | existing mock executable fixture convention (`tests/fixtures/mock_whisper.py`) | partial |
| `tests/test_adapter_startup.py` | test | event-driven startup | existing adapter fixture and fake backend | exact extension seam |
| `tests/test_signing_adr_contract.py` | static-contract test | transform | `tests/test_beta3_packaging.py` static source assertions | role-match |

## Pattern Assignments

### `lecturepack/infrastructure/runtime_inventory.py` (proposed; immutable model/utility, transform + file-I/O)

**Purpose:** own an ordered, bundle-relative definition of `ffmpeg.exe`, `ffprobe.exe`, `whisper-cli.exe`, `whisper.dll`, `ggml.dll`, `ggml-base.dll`, every resolved `ggml-cpu-*.dll`, and `models/ggml-base.en.bin`; resolve paths under one root and compute deterministic payload identity.

**Analog:** `app/packaging/build.py:95-146,159-199`

**Copy the ordered-list/build-validation approach:**

```python
# app/packaging/build.py:132-145
required = [
    "LecturePack.exe",
    "bin/ffmpeg.exe", "bin/ffprobe.exe", "bin/whisper-cli.exe",
    "bin/whisper.dll", "bin/ggml.dll", "bin/ggml-base.dll",
    "models/ggml-base.en.bin",
]
for r in required:
    p = dist_app / r
    if not p.is_file() or p.stat().st_size == 0:
        violations.append(f"missing/empty required payload: {r}")
if not list((dist_app / "bin").glob("ggml-cpu-*.dll")):
    violations.append("missing CPU backend DLLs: bin/ggml-cpu-*.dll")
```

**Required adaptation:** `bundle_engine()` currently derives CPU DLLs via `sorted(...)` at lines 185-189, but `check_clean_state()` only tests that at least one DLL exists. Put both consumers behind the proposed inventory export so package copying, package assertion, startup, diagnostics, and tests receive the same sorted resolved DLL entries. Inventory validation must reject absolute, traversal, and duplicate relative names before joining them to its root.

**Root selection pattern:** frozen UI resources use `sys._MEIPASS` when applicable in `app/desktop/paths.py:17-22`, while the runtime binaries are currently beside the executable in `ConfigManager._app_dir()` at `config_manager.py:17-28`. Preserve the runtime root semantics, rather than copying `paths.app_root()` blindly.

### `lecturepack/infrastructure/runtime_validation.py` (proposed; service, request-response + file-I/O)

**Purpose:** light identity/readability validation plus injected, bounded executable/DLL/model smoke runner. Return evidence-rich component status; it must not persist configuration or trigger optional engines.

**Analog:** `lecturepack/infrastructure/ffmpeg_wrapper.py:112-159` and `lecturepack/infrastructure/whisper_wrapper.py:229-249`

**QProcess process boundary to copy:**

```python
# lecturepack/infrastructure/ffmpeg_wrapper.py:120-145
self.process = QProcess()
self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
...
self.process.start(program, args)

# lecturepack/infrastructure/whisper_wrapper.py:229-244
if self.whisper_exe_path.lower().endswith(".py"):
    program = sys.executable
    args = [self.whisper_exe_path] + whisper_args
else:
    program = self.whisper_exe_path
    args = whisper_args
self.process.start(program, args)
```

**Cancellation pattern to preserve:** `cancel()` only terminates the process tree associated with the wrapper (`ffmpeg_wrapper.py:146-149`; `whisper_wrapper.py:246-249`). The proposed runner must have an equivalent timeout cleanup that never targets unrelated processes.

**Structured status shape:** reuse the dataclass plus `asdict()` convention from `EngineInfo` at `transcription_engines.py:69-80`. Proposed `RuntimeComponentStatus`/`SmokeEvidence` should include component name, resolved path, healthy boolean, reason, identity facts, command argument vector, exit code, stdout, stderr, duration, and timeout/cancel outcome. Do not emit shell command strings as the source of truth: retain `program` plus an argument list.

### `lecturepack/services/runtime_bootstrap.py` (proposed; service, request-response/state transition)

**Purpose:** compose inventory, light/full policy, migration, validation, atomic fact persistence, and post-health optional-engine resolution. It returns a structured result (`ASSESSING`, `HEALTHY`, `SETUP_REQUIRED` or equivalent) and never repairs/downloads.

**Analog:** `lecturepack/infrastructure/transcription_engines.py:180-272`

```python
# transcription_engines.py:230-250
def resolve(self, requested: str = ENGINE_AUTO) -> EngineInfo:
    """Never returns an unavailable engine: unavailable requests degrade to CPU."""
    requested = self._ENGINE_ALIASES.get(requested, requested)
    engines = self.detect_engines()
    cpu = engines[ENGINE_CPU]
    ...
    if requested == ENGINE_CUDA:
        if cuda.available:
            cuda.reason = "explicitly selected"
            return cuda
        cpu.reason = f"CUDA requested but unavailable ({cuda.reason}); using CPU"
        return cpu
```

**Apply it after, not during, admission:** `EngineRegistry.resolve()` is a suitable model for a post-health `FallbackNotice` (requested engine, selected CPU, reason). CPU admission itself must use canonical bundle facts only; it must not accept the existing registry/config/PATH fallback paths.

**Migration source:** model profile ordering already declares base English first at `transcription_engines.py:49-66`; `resolve_profile_model()` searches ordered model names and directories at lines 285-306. Migration should set only the runtime-owned default to the bundled exact `ggml-base.en.bin`, retaining other installed model metadata and a healthy optional engine preference.

### `lecturepack/infrastructure/config_manager.py` (existing; config CRUD + migration)

**Analog:** existing `ConfigManager.load/save/set` at `config_manager.py:54-104`, backed by `FileManager.write_json_atomic()` at `file_manager.py:7-15`.

```python
# config_manager.py:96-104
def save(self):
    FileManager.write_json_atomic(self.config_path, self.settings)

def set(self, key, value):
    self.settings[key] = value
    self.save()

# file_manager.py:7-15
temp_filepath = filepath + ".tmp"
os.makedirs(os.path.dirname(filepath), exist_ok=True)
with open(temp_filepath, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4, ensure_ascii=False)
os.replace(temp_filepath, filepath)
```

**Required adaptation:** do **not** call `set()` once per discovered binary—`autodetect_ffmpeg()` does that today at `config_manager.py:125-145`, and `autodetect_whisper()` does it at `148-172`. Add one method that prepares/migrates settings and writes a single complete `runtime_health` snapshot only when the bootstrap result is healthy. Failed, stale, partial, or mismatched facts stay non-healthy and must not overwrite an otherwise usable record with a partial payload.

### `app/desktop/engine_adapter.py` and `app/desktop/main.py` (existing modifications; composition/controller, event-driven startup)

**Problem seam:** `LecturePackAdapter.__init__` creates `ConfigManager` then `JobController` immediately (`engine_adapter.py:694-720`). `on_ui_ready()` starts normal behavior—including job reconciliation, optional probes, and latest-job activation—at `951-971`.

```python
# engine_adapter.py:694-720
self.config = ConfigManager()
self.controller = JobController(self.config)
...
self._wire_controller()

# engine_adapter.py:951-971
self._reconcile_jobs_on_startup()
self.queue.reconcile_schedules_on_launch()
self._push_jobs()
self._probe_ollama_async()
self.validate_vulkan()
self.validate_cuda()
...
self._load_latest_completed_job()
```

**Composition pattern:** `main()` makes the Qt application and window once (`main.py:182-212`). Introduce a single coordinator/composition point between `ConfigManager` construction and `LecturePackAdapter`/`JobController` construction. Only a `HEALTHY` result may create/enable the normal adapter and call `on_ui_ready()` exactly once. A non-healthy result is returned/emitted as structured state for Phase 2; Phase 1 must not make a setup page, download, repair, navigation, probe, or demo action.

**Visible notice pattern:** adapter payloads are JSON strings through `_emit()` (`engine_adapter.py:750-756`), and CUDA tests demonstrate assertion of parsed structured payload fields (`tests/test_cuda_engine.py:105-130`). Use the same JSON-payload shape for the non-blocking CPU fallback notice after `HEALTHY`; no UI-surface ownership is implied.

### `app/packaging/build.py` (existing; config/batch + file-I/O)

**Analog:** `check_clean_state()` is pure and testable (`build.py:95-156`); `bundle_engine()` performs guarded copies (`159-199`).

**Pattern to retain:** build validation returns violations, the wrapper decides failure:

```python
# build.py:149-156
violations = check_clean_state(dist_app)
if violations:
    sys.exit("CLEAN-STATE GATE FAILED —\n  " + "\n  ".join(violations))
```

Replace the local `required` list and variable-DLL glob with the same inventory consumed by runtime code. Preserve existing clean-state prohibitions; Phase 1 may add an inventory-consumer assertion but must not implement signed-download/repair functionality (Phase 2).

### `docs/DECISIONS.md` (existing documentation; ADR/static contract)

**Proposed ADR content, approval-gated:** decision owner/status; algorithm; signature/key encodings; exact canonical UTF-8 bytes/schema; app version and exact asset filenames; embedded active/rotation key IDs; private-key custody, signing/release ownership, rotation and revocation; PyInstaller collection/frozen validation; known-good and altered-byte vector; explicit Phase-2 dependency gate. `cryptography` is only an unapproved candidate—do not add it to requirements or source in this phase.

**Static-test pattern:** inspect files as text and make targeted contract assertions, as `tests/test_beta3_packaging.py:69-78` already does for package metadata/spec configuration. The test must assert required ADR headings/fields and the literal unapproved/approval state; it must not claim the verifier implementation exists before approval.

### Test files and fixture (proposed; test/fault matrix)

**`tests/test_runtime_inventory.py` — analog `tests/test_beta3_packaging.py:81-104`.** Use `tmp_path`, synthetic tree construction, and a simulated app root. Extend the exact-path checks to blank/missing/unreadable/corrupt entries, all CPU DLLs, duplicate/absolute/traversal inventory entries, identity changes, and proof that package and diagnostic consumers import the one inventory source.

**`tests/test_runtime_bootstrap.py` — analog `tests/test_cuda_engine.py:21-29,32-87`.** Construct a `ConfigManager(tmp_path)`, inject discovery/runner seams with `monkeypatch`, and assert complete result fields. Cover fresh/full, healthy/light, stale/partial rejected, identity changed/full, repair/update force full, nonzero, timeout/hang, atomic persistence only after all components pass, base.en migration, preserved healthy optional engine, and structured fallback notice/no network.

**`tests/fixtures/mock_runtime_hang.py` — proposed fixture.** Mirror the repository mock-tool approach rather than sleeping a real executable; it must produce no output and be run through the injected runner to deterministically exercise the bounded timeout path.

**`tests/test_adapter_startup.py` — extend existing.** Its `_temp_data_dir` fixture patches both constants/config (`18-26`) and `_FakeBackend` records emissions (`29-42`). Add ordering fakes so no `JobController`, `on_ui_ready`, job signal, Ollama probe, CUDA/Vulkan validation, or demo action occurs before `HEALTHY`; assert one normal-ready transition after success.

**`tests/test_signing_adr_contract.py` — proposed static contract.** Follow source/metadata assertion style from `tests/test_beta3_packaging.py`; parse/inspect `docs/DECISIONS.md`, not a mock decision object. Keep verification-vector runtime assertions conditional on a human-approved selection, because no verifier dependency is authorized in Phase 1.

## Shared Patterns

### Disposable-profile safety

**Sources:** `app/desktop/paths.py:29-47`, `tests/test_data_dir_override.py:20-109`.

`LECTUREPACK_DATA_DIR` must remain the test seam. It absolutizes/expands the value and creates only the selected profile directory. Use it for bootstrap and packaged smoke evidence; do not touch user jobs/data or the original lecture video.

### Atomic persistence

**Sources:** `config_manager.py:68-104`, `file_manager.py:7-28`.

Config loading merges unknown keys and performs migration without deleting future data; JSON persistence is temp-file plus `os.replace`. Runtime persistence must be one complete factual record, not a sequence of independently persisted component paths.

### Optional-engine fallback

**Sources:** `transcription_engines.py:230-272`, `tests/test_cuda_engine.py:50-87`.

The registry preserves explicit available selections and degrades unavailable GPU requests to CPU with a reason. Reuse this shape only after required CPU health. Do not let an optional failure control core admission.

### Safe process execution

**Sources:** `ffmpeg_wrapper.py:63-79,112-159`; `whisper_wrapper.py:229-249`.

Pass `program` and an argument vector; never shell-concatenate Unicode paths. Capture output, exit status, duration, and timeout reason in proposed smoke evidence. On cancel/timeout, terminate only the exact process tree started by the probe.

## File Ownership and Plan-Conflict Notes

| File | Phase-1 owner / coordination concern |
|---|---|
| `app/desktop/engine_adapter.py` | One plan must exclusively own lifecycle ordering; it is a large shared adapter and parallel edits will conflict. |
| `app/desktop/main.py` | Coordinate with the adapter owner; composition must not construct a normal adapter before health. |
| `lecturepack/infrastructure/config_manager.py` | Runtime persistence/migration owner must coordinate with inventory/bootstrap owner; do not retain old autodetect side effects on the admission path. |
| `lecturepack/infrastructure/transcription_engines.py` | Only optional-selection behavior belongs here; canonical CPU admission belongs in new inventory/validation modules. |
| `app/packaging/build.py` | Must consume the new inventory and is also the later Phase-5 package-evidence seam; preserve its current clean-state checks. |
| `docs/DECISIONS.md` | ADR writer owns the dated record; no source/dependency change may be coupled to it before explicit approval. |
| `tests/test_adapter_startup.py` | Shared with startup composition plan; tests should land with the coordinator/lifecycle change. |

## No Analog Found

| File/symbol | Role | Data flow | Planning guidance |
|---|---|---|---|
| `RuntimeBootstrapResult` state machine | service status object | state transition | Use `EngineInfo` dataclass/to-dict style, but keep bootstrap states and evidence new. |
| bounded synchronous smoke runner with complete evidence | infrastructure service | process | Compose existing QProcess argument/cancel patterns; no existing timeout/evidence object covers the contract. |
| signing ADR contract test | static contract test | transform | Reuse text assertion style; no existing security ADR test exists. |

## Metadata

**Analog search scope:** `lecturepack/infrastructure`, `app/desktop`, `app/packaging`, `tests`, `docs`  
**Files scanned:** 15 primary implementation/test files plus Phase context, research, validation, roadmap, and requirements  
**Pattern extraction date:** 2026-07-28
