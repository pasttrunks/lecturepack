# Phase 1: Clean-Device Footprint & First Launch - Pattern Map

**Mapped:** 2026-07-30
**Files analyzed:** 10 (all modified, none newly created)
**Analogs found:** 10 / 10 (all analogs are the file's own pre-existing neighboring pattern — this phase extends established code, it does not introduce new architecture)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/packaging/build.py` (`bundle_engine()` pruning step) | utility (build script) | file-I/O / batch | `check_clean_state()` in the same file (`build.py:316-357`) | exact — same file, same "walk tree, collect/act on violations" idiom |
| `app/packaging/lecturepack.spec` (remove `demo_model_datas`) | config | file-I/O | `DEMO_ASSET`/`DEMO_THUMBNAIL` existence-check block immediately above it (`lecturepack.spec:49-58`) | exact — same file, same guard-then-datas-tuple idiom |
| `app/desktop/main.py` (`main()`: AUMID call + single-instance guard) | controller (process entrypoint) | event-driven / request-response | `WindowsIntegration.PowerRequester.set_awake()` (`win_integration.py:73-85`) for the ctypes-call pattern; `main()` itself (`main.py:225-255`) for placement/ordering | role-match (ctypes pattern) + exact (ordering, same function) |
| `app/desktop/bridge.py` (`Backend.__init__` deferred `assess()`) | controller (QObject bridge) | event-driven (worker-thread → signal) | No existing worker-thread-to-signal pattern in `bridge.py` itself; closest in-repo precedent is `engine_adapter.py`'s job-progress signal emission (see Shared Patterns) plus BUG_LIST.md's BUG-09 (`QTimer.singleShot` marshalling) | role-match — pattern must be assembled from two analogs, not copied whole from one file |
| `lecturepack/services/runtime_bootstrap.py` (`_validate_full` parallelization) | service | batch / transform | `_validate_full()` itself (`runtime_bootstrap.py:128-175`) — the three independent probes it already runs sequentially | exact — refactor in place, not a new file |
| `lecturepack/infrastructure/config_manager.py` (`persist_setup_acknowledged()`) | model / persistence | CRUD | `persist_runtime_health()` (`config_manager.py:106-133`) | exact — same file, same atomic-write-after-validate idiom |
| `app/ui/app.js` (`RuntimeSetupGateModel`/`RuntimeSetupGate` extended for first-run checklist) | component (state machine + DOM controller) | event-driven | `RuntimeSetupGateModel()` itself (`app.js:1998-2059`) and `syncDemoAdmission()` (`app.js:2175-2179`) | exact — same reducer, new state/transition added, not a new component |
| `app/packaging/lecturepack.iss` (`AppUserModelID` on `[Icons]`) | config | file-I/O | `SetupIconFile` line (`lecturepack.iss:32`) and `[Files]` entry (`:47`) — same declarative section style | role-match |
| `.github/workflows/release.yml` (restore installer asset publication) | config (CI) | pub-sub (release assets) | The existing "Produce exactly six signed runtime assets" step (lines 58-85) for the assertion-then-publish idiom; `git show f3d713d:.github/workflows/release.yml` for the exact pre-regression job body to restore | exact (historical exact analog exists in git history) |
| `tests/test_runtime_packaged_smoke.py` / `tests/test_beta3_packaging.py` (new assertions for post-cut tree + updater assets) | test | batch / file-I/O | `test_stray_app_json_flagged_but_qt_json_allowed` (`test_beta3_packaging.py:57-66`) and `test_package_membership_uses_canonical_inventory` (`test_runtime_packaged_smoke.py:18-22`) | exact — same fixture harness (`LECTUREPACK_ONEDIR_FIXTURE`, `build.required_runtime_payload`) |

## Pattern Assignments

### `app/packaging/build.py` — post-build Qt pruning inside/after `bundle_engine()` (utility, file-I/O)

**Analog:** `check_clean_state()`, same file, lines 316-357.

**Core pattern to copy** (violation-list / walk-and-act idiom, `build.py:316-346`):
```python
def check_clean_state(dist_app: Path) -> list:
    import fnmatch
    violations = []
    dist_app = Path(dist_app)
    forbidden_name_globs = ["*config.json", "*.job.json", "*.db", "*.sqlite", "*.sqlite3"]
    forbidden_dir_names = {"jobs", "exports", "thumbs", "LecturePackData", "study_packs", "downloads"}
    for path in dist_app.rglob("*"):
        rel = path.relative_to(dist_app)
        ...
    return violations
```

**Existing `bundle_engine()` copy idiom to mirror for pruning** (`build.py:373-410`):
```python
def bundle_engine() -> None:
    repo = APP_DIR.parent
    dist_app = APP_DIR / "dist" / "LecturePack"

    def _copy(src: Path, dst: Path):
        if not src.exists() or src.stat().st_size == 0:
            sys.exit(f"engine bundle FAILED — missing or empty {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if not dst.exists() or dst.stat().st_size == 0:
            sys.exit(f"engine bundle FAILED — copy produced empty {dst}")
    ...
    # App icon — copied next to the EXE so main.py can load it at runtime.
    ico_src = APP_DIR / "packaging" / "lecturepack.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, dist_app / "lecturepack.ico")
    print(f"Bundled canonical CPU runtime: {len(source_payload)} payload files")
```

**Apply this shape:** add a `prune_unused_qt_components(dist_app: Path) -> None` function in `build.py` (per RESEARCH.md's Pattern 1 code, already vetted against this repo's actual PyInstaller output), called from `main()` right after `bundle_engine()` and before `validate_clean_state()` (main.py call site: `build.py:503-524`, same block that already sequences `bundle_engine()` → `validate_clean_state()` → `make_portable_zip()`).

**Where it's invoked** (`build.py` `main()`, ~line 517-524 — exact insertion point):
```python
    bundle_engine()

    # Clean-state gate: fresh install must ship zero jobs/dev data, and the
    # engine payload must actually be present (beta.3 §3).
    validate_clean_state()

    # Portable ZIP is independent of Inno Setup — always produced.
    make_portable_zip(version)
```
Insert `prune_unused_qt_components(dist_app)` between `bundle_engine()` and `validate_clean_state()`.

---

### `app/packaging/lecturepack.spec` — remove `demo_model_datas` duplication (config, file-I/O)

**Analog:** the immediately preceding demo-asset guard block, same file, lines 49-58.

**Pattern already established in this file** (existence-check-then-datas-tuple):
```python
DEMO_ASSET = os.path.join(SPEC_DIR, "assets", "demo", "demo_lecture.mp4")
if not os.path.isfile(DEMO_ASSET) or os.path.getsize(DEMO_ASSET) == 0:
    raise RuntimeError("missing required bundled guided-demo asset")
...
demo_datas = [
    (DEMO_ASSET, os.path.join("assets", "demo")),
    (DEMO_THUMBNAIL, os.path.join("assets", "demo")),
]

DEMO_WHISPER_MODEL = os.path.join(REPO_ROOT, "models", "ggml-base.en.bin")
if not os.path.isfile(DEMO_WHISPER_MODEL) or os.path.getsize(DEMO_WHISPER_MODEL) == 0:
    raise RuntimeError("missing required bundled guided-demo Whisper model")
demo_model_datas = [(DEMO_WHISPER_MODEL, "models")]   # <-- REMOVE this line and its use below

a = Analysis(
    ...
    datas=ui_datas + demo_datas + demo_model_datas + engine_datas + tzdata_datas,   # <-- drop demo_model_datas here
    ...
)
```
**Action:** keep the `DEMO_WHISPER_MODEL` existence check (still required so `bundle_engine()` has a source file to copy from later), delete `demo_model_datas = [...]` and its `+ demo_model_datas` reference in the `datas=` concatenation. This is a 2-line removal, not new code — matches D-05/RESEARCH's "the resolution logic is the deliverable, not the deletion" (the fallback chain in `engine_adapter.py` already handles the removal, see Shared Patterns below).

---

### `app/desktop/main.py` — AUMID call + single-instance guard in `main()` (controller, event-driven)

**Analog 1 — ctypes call-and-degrade-silently idiom:** `PowerRequester.set_awake()`, `app/desktop/win_integration.py:73-85`:
```python
def set_awake(self, on: bool) -> None:
    if on == self._active:
        return
    self._active = on
    if sys.platform != "win32":
        return
    try:
        import ctypes
        flags = self._ES_CONTINUOUS | (self._ES_SYSTEM_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass  # degrade silently
```
**Apply this shape** for `SetCurrentProcessExplicitAppUserModelID` (RESEARCH.md's Code Examples section has the exact call — copy verbatim, wrap in the same `if sys.platform == "win32": try/except: pass` shape shown above).

**Analog 2 — `main()` ordering, exact insertion point** (`app/desktop/main.py:225-237`):
```python
def main() -> int:
    # Custom URL schemes must be registered before the QApplication is created.
    register_asset_scheme()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(version.APP_NAME)
    app.setOrganizationName(version.ORG_NAME)
    app.setApplicationVersion(version.__version__)

    win = MainWindow()
    win.show_when_ready()
```
**Required change per D-19/D-20:** the AUMID call must be the first statement in `main()`, before `register_asset_scheme()`. The single-instance guard must run after `QApplication(sys.argv)` is constructed (per RESEARCH.md Open Question 1 — `QLocalSocket` needs `QCoreApplication` machinery) but strictly before `MainWindow()` / `Backend()` construction — i.e., insert between `app.setApplicationVersion(...)` and `win = MainWindow()`. On guard failure (another instance owns the socket), send a "raise" message and `return 0` immediately without constructing `MainWindow`.

**Icon guard needing an else-branch (D-21)** — current silently-guarded code, `app/desktop/main.py:101-107`:
```python
if getattr(sys, "frozen", False):
    icon_path = os.path.join(os.path.dirname(sys.executable), "lecturepack.ico")
else:
    icon_path = os.path.join(os.path.dirname(__file__), "..", "packaging", "lecturepack.ico")
if os.path.exists(icon_path):
    self.setWindowIcon(QIcon(icon_path))
```
Add an `else:` branch that logs (there is no existing logger call in `MainWindow.__init__`; use the same `log_asset_error`-style callback already passed to `install_asset_handler` at `main.py:120-124`, or a plain `print`/`logging.warning` consistent with how other silent-failure guards in this file are handled — check for a project logger before inventing one).

---

### `app/desktop/bridge.py` — deferred `assess()` off `Backend.__init__` (controller, event-driven)

**Analog — current synchronous call to replace** (`bridge.py:114-137`):
```python
def __init__(self, window):
    super().__init__()
    self._window = window
    self._settings = QSettings(version.ORG_NAME, version.APP_NAME)
    self._runtime_config = ConfigManager()
    self.runtime_health_result = RuntimeBootstrapService(self._runtime_config).assess()   # <-- BLOCKS UI THREAD
    self._runtime_diagnostics = RuntimeDiagnosticsController(
        RuntimeDiagnosticsService(self._runtime_config, self.runtime_health_result)
    )
    ...
    if self.runtime_health_result.state == "HEALTHY":
        self._adapter = make_adapter(...)
        self._updater = Updater(self)
```
**Existing signal-declaration idiom to extend** (`bridge.py:54-113` — every cross-bridge event is a `Signal(str)` carrying JSON, per the file's own docstring: "Everything crossing the bridge is a JSON string"). Add a new `bootstrap_progress = Signal(str)` alongside the existing block (e.g. next to `repair_event = Signal(str)` at line 110), following the exact same naming/typing convention as every other signal in that list.

**Worker-thread → main-thread marshalling constraint (BUG-09, from BUG_LIST.md, cited in RESEARCH.md Pattern 2):** a bare `threading.Thread` + `QTimer.singleShot(0, fn)` silently never fires because the timer starts in the calling thread, not the main thread. Must use `QTimer.singleShot(0, self, callback)` with `self` (a `QObject` already living on the main thread) as the context object — exact signature shown in RESEARCH.md's Pattern 2 code block. Read `BUG_LIST.md`'s BUG-09 entry before implementing this file.

---

### `lecturepack/services/runtime_bootstrap.py` — parallelize independent probes (service, batch)

**Analog:** `_validate_full()` itself, current sequential form (`runtime_bootstrap.py:128-175`):
```python
@staticmethod
def _validate_full(paths: Mapping[str, Path]) -> Mapping[str, Mapping[str, Any]]:
    validator = RuntimeValidator()
    results: dict[str, Mapping[str, Any]] = {}
    def evidence(smoke, *, healthy=None, reason=None) -> dict[str, Any]:
        return {"healthy": smoke.ok if healthy is None else healthy, "reason": reason or smoke.reason,
                "exit_code": smoke.exit_code, "argv": list(smoke.argv), "stdout": smoke.stdout,
                "stderr": smoke.stderr, "duration_ms": smoke.duration_ms, "timed_out": smoke.timed_out}
    for name, path in paths.items():
        if name == "bin/ffmpeg.exe" or name == "bin/ffprobe.exe":
            smoke = validator.run(str(path), ["-version"])
            results[name] = evidence(smoke)
    try:
        staging = WhisperPathStaging(paths["models/ggml-base.en.bin"], paths["smoke/runtime-smoke.wav"], ...)
        staged_model, staged_wav, _ = staging.prepare()
        try:
            whisper_smoke = validator.run(str(paths["bin/whisper-cli.exe"]), ["-m", staged_model, "-f", staged_wav, "-t", "1", "-nt"])
        finally:
            staging.cleanup()
    except Exception as error:
        ...
    for name in paths:
        if name not in results:
            results[name] = evidence(whisper_smoke)
    return results
```
**Apply this shape:** the three probes (`ffmpeg -version`, `ffprobe -version`, staged whisper transcription) are independent — per D-10, parallelize with a bounded thread pool (`concurrent.futures.ThreadPoolExecutor(max_workers=3)`) inside this same static method, preserving every field of the `evidence()` dict and the exact per-probe 30s bound (`runtime_validation.py:24`). Do NOT alter `RuntimeValidator.run()`'s bound or replace the staged whisper-cli transcription with a lighter check (D-10 hard constraint).

---

### `lecturepack/infrastructure/config_manager.py` — `persist_setup_acknowledged()` (model, CRUD)

**Analog:** `persist_runtime_health()`, same file, lines 106-133:
```python
def persist_runtime_health(self, runtime_health, *, bundled_model):
    if not isinstance(runtime_health, dict) or not runtime_health.get("components"):
        raise ValueError("runtime health must contain complete component facts")
    migration_versions = self.settings.get("migration_versions")
    if not isinstance(migration_versions, dict):
        migration_versions = {}
    if migration_versions.get("runtime_contract") != 1:
        ...
        migration_versions["runtime_contract"] = 1
    self.settings["migration_versions"] = migration_versions
    self.settings["runtime_health"] = runtime_health
    self.save()
```
**`save()` is the atomic-write transport to reuse** (`config_manager.py:96-97`):
```python
def save(self):
    FileManager.write_json_atomic(self.config_path, self.settings)
```
**Apply this shape:** add `persist_setup_acknowledged(self) -> None` (or similar) that sets `self.settings["setup_acknowledged"] = True` (or a versioned marker analogous to `migration_versions`) and calls `self.save()` — same validate-then-mutate-then-atomic-save shape, landing "alongside `runtime_health`" per D-16. Do not write this flag to `QSettings`/`localStorage` — `ConfigManager`'s own docstring/established pattern (RESEARCH.md's Established Patterns: "Runtime health is persisted as JSON in `<data_dir>/config.json`, never QSettings") is the binding precedent.

---

### `app/ui/app.js` — first-run checklist extension of `RuntimeSetupGateModel`/`RuntimeSetupGate` (component, event-driven)

**Analog:** the reducer itself, `app.js:1998-2059`:
```javascript
function RuntimeSetupGateModel() {
    var state = 'gate', returnState = 'gate', retryPending = false, cancelPending = false;
    var activeOperation = null, terminal = false, offer = null, bootstrapPending = true, healthy = false;
    ...
    bootstrap: function (bootstrap) {
        bootstrapPending = false;
        if (bootstrap && bootstrap.runtime_health_state === 'SETUP_REQUIRED') {
            healthy = false; terminal = true;
            if (!activeOperation) { state = 'gate'; terminal = false; offer = null; cancelPending = false; }
        } else if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY') {
            healthy = true;
            if (activeOperation && !terminal) this.event({ operation_id: activeOperation, kind: 'admitted' });
        }
        return snapshot();
    },
    ...
}
```
**The failure-gate skip logic to change (D-11/D-12)** — DOM controller call site, `app.js:2170-2173`:
```javascript
syncDemoAdmission(view);
if (bootstrap && bootstrap.runtime_health_state === 'SETUP_REQUIRED') { render(); return; }
if (bootstrap && bootstrap.runtime_health_state === 'HEALTHY' && !before.activeOperation) { setUnderlyingInert(false); return; }
if (view.state === 'ready') ready();
```
This is the exact line that today makes a `HEALTHY` fresh profile skip the overlay entirely (`setUnderlyingInert(false); return;`). Per D-12, this must become conditional on a new "first-ever launch, not yet acknowledged" flag arriving from the backend bootstrap payload (via `Backend.get_bootstrap()`, `bridge.py:318-328` per CONTEXT.md) rather than short-circuiting unconditionally.

**`syncDemoAdmission` — demo-gating pattern to extend for D-17** (`app.js:2175-2179`):
```javascript
function syncDemoAdmission(view) {
    setDemoAdmissionAvailable(!!(view && view.healthy && !view.bootstrapPending &&
        (view.state === 'ready' || !view.activeOperation)));
}
```
Per D-17 the demo offer must gate on "continued past checklist or skipped," not merely `healthy` — extend this same boolean-AND condition with the new acknowledged-flag check, not a parallel gating mechanism.

**`setDemoAdmissionAvailable` — the consumer, unaffected structurally** (`app.js:2359-2379`) — shown for context; no change expected here beyond receiving the already-updated `demoAdmissionAvailable` boolean.

**localStorage anti-pattern to avoid (D-16), for contrast** — `tourSeen()`/`markTourSeen()` (`app.js:2336-2340`):
```javascript
function tourSeen() {
    try { return window.localStorage.getItem(TOUR_STORAGE_KEY) === '1'; } catch (e) { return false; }
}
function markTourSeen() {
    try { window.localStorage.setItem(TOUR_STORAGE_KEY, '1'); } catch (e) {}
}
```
Do NOT copy this pattern for the setup-acknowledged flag — D-16 explicitly requires it survive WebEngine profile loss, so it must round-trip through `Backend`/`ConfigManager.persist_setup_acknowledged()` instead (a new bridge call, not a `localStorage` key).

---

### `app/packaging/lecturepack.iss` — `AppUserModelID` on `[Icons]` entries (config, file-I/O)

**Analog:** existing declarative `[Setup]`/`[Files]` parameter style, `lecturepack.iss:32,47` (exact line text not re-quoted here — both are single-line key=value declarations in the same idiom as the `AppUserModelID` addition RESEARCH.md's Code Examples section already drafts):
```ini
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "LecturePack.LecturePack"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "LecturePack.LecturePack"
```
**Constraint:** the string must byte-for-byte match the value passed to `SetCurrentProcessExplicitAppUserModelID` in `main.py` (RESEARCH.md Assumption A4) — define it once and reference in both places if the build has a shared version-stamping mechanism (see `stamp_version_info()` pattern in `build.py` for how `.iss`/`.spec` values are already parameterized at build time).

---

### `.github/workflows/release.yml` — restore installer asset publication additively (config/CI, pub-sub)

**Analog — the exact pre-regression job to restore, from git history:**
```
git show f3d713d:.github/workflows/release.yml
```
Read this at plan time; it is the byte-for-byte reference for what `a6164b1` removed (`choco install innosetup` + `python packaging/build.py` [no `--no-installer`] + publishing `Setup.exe`/`Portable.zip`/`SHA256SUMS.txt`).

**Current step to add alongside, not replace** (`release.yml:58,80-90` — exact current text):
```yaml
      - name: Build canonical disposable onedir
        working-directory: app
        run: python packaging/build.py --no-installer
```
and the six-asset publish block:
```yaml
      - name: Produce exactly six signed runtime assets
        shell: bash
        env:
          LECTUREPACK_RELEASE_ED25519_PRIVATE_KEY_HEX: ${{ secrets.LECTUREPACK_RELEASE_ED25519_PRIVATE_KEY_HEX }}
        run: |
          python scripts/build_signed_runtime_release.py --app-version "$APP_VERSION" --runtime-root app/dist/LecturePack --output-directory runtime-release-assets > runtime-release-audit.json
          test "$(find runtime-release-assets -maxdepth 1 -type f | wc -l)" = 6
          ...
      - name: Release exact signed assets
        uses: softprops/action-gh-release@v2
        with:
          tag_name: v${{ env.APP_VERSION }}
          files: |
            runtime-release-assets/LecturePack-${{ env.APP_VERSION }}-RuntimeManifest-v1.json
            ...
```
**Owner decision to implement (per orchestrator addendum):** additively restore installer publication — i.e. either (a) change `build.py --no-installer` to a full build (requires `choco install innosetup` step restored from `f3d713d`) and add `Setup.exe`/`Portable.zip`/`SHA256SUMS.txt` to the `softprops/action-gh-release@v2` `files:` list of the SAME job (both asset sets published from one job), or (b) add a second parallel job. Prefer (a) — single build avoids double-building and matches "six signed assets stay, installer assets are added" per the addendum. Follow the exact `test "$(find ... | wc -l)" = N` assertion idiom already present for the six-asset count when adding an analogous assertion for the three installer/updater assets.

**`expected_asset_names()` — the consumer contract this must satisfy** (`app/desktop/update_service.py:117-120`):
```python
def expected_asset_names(version: str, portable: bool = False) -> tuple[str, str]:
    primary = (f"{APP_NAME}-{version}-Portable.zip" if portable
               else f"{APP_NAME}-{version}-Setup.exe")
    return primary, f"{APP_NAME}-{version}-SHA256SUMS.txt"
```
The three published asset filenames in the restored CI step MUST exactly match `f"{APP_NAME}-{version}-Setup.exe"`, `f"{APP_NAME}-{version}-Portable.zip"`, `f"{APP_NAME}-{version}-SHA256SUMS.txt"` (case-sensitive, `APP_NAME` from `app/desktop/version.py`).

---

### `tests/test_runtime_packaged_smoke.py` / `tests/test_beta3_packaging.py` — packaging-exclusion and asset-contract tests (test, batch/file-I/O)

**Fixture harness to reuse** (`app/packaging/build.py:48-64`, referenced by both test files):
```python
def required_runtime_payload(
    runtime_root, cpu_dll_names=(),
):
    ...
    configured = os.environ.get("LECTUREPACK_ONEDIR_FIXTURE", "").strip()
    ...
```
**Analog test for packaging-exclusion assertions** — `tests/test_runtime_packaged_smoke.py:18-22`:
```python
def test_package_membership_uses_canonical_inventory():
    required = build.required_runtime_payload(Path("runtime-root"), cpu_dll_names=("ggml-cpu-test.dll",))
    assert required["smoke/runtime-smoke.wav"].name == "runtime-smoke.wav"
    assert required["bin/ggml-cpu-test.dll"].name == "ggml-cpu-test.dll"
```
**Analog test for synthetic-tree cleanliness assertions** — `tests/test_beta3_packaging.py:57-66` (`test_stray_app_json_flagged_but_qt_json_allowed`) builds a synthetic `_internal/PySide6/qml/propertyGroups.json` tree via a fixture helper at the top of the file (lines 20-35) and asserts on `check_clean_state()`'s violation list. **Apply this exact shape** for a new test asserting `prune_unused_qt_components()` actually removes `translations/`, `qml/`, `Qt6Qml.dll`, `Qt6Quick.dll`, `Qt6Quick3DRuntimeRender.dll`, `Qt6Pdf.dll` from a synthetic onedir tree, and that `ggml-base.en.bin` exists in exactly one location post-dedupe.
**Analog for `check_clean_state()` synthetic-tree fixture builder** — read `tests/test_beta3_packaging.py:1-35` in full at implementation time for the exact `tmp_path`-based tree-construction helper to copy.
**Updater asset-contract test:** no direct existing analog asserts on `.github/workflows/release.yml` contents directly (CI YAML is not currently under test) — the nearest asset-contract analog is `expected_asset_names()`'s own existing unit tests in `tests/` (search `test_update_service.py` or similar at plan time) asserting the three filenames it computes; a new test should assert that whatever asset-publishing logic surfaces (if extracted to a script, per the `build_signed_runtime_release.py` precedent) produces filenames matching `expected_asset_names()` exactly, rather than asserting on YAML text.

## Shared Patterns

### "Backend decides, UI renders" (applies to bridge.py, config_manager.py, app.js)
**Source:** established pattern already stated in `01-CONTEXT.md`'s `<code_context>`: "The gate is decided in Python before the UI asks; the UI renders a backend verdict rather than deciding for itself."
**Apply to:** `bridge.py`'s new `bootstrap_progress` signal, `config_manager.py`'s `persist_setup_acknowledged()`, and `app.js`'s `RuntimeSetupGateModel` extension. The first-run checklist's Ready/Needs-Attention verdict must be computed in Python (from `RuntimeBootstrapService.assess()`'s existing per-component evidence dict) and passed as JSON through `Backend.get_bootstrap()`; `app.js` must not compute health itself.

### Ctypes OS-integration with silent degrade (applies to main.py's AUMID call)
**Source:** `app/desktop/win_integration.py` module docstring (lines 1-12) and `PowerRequester.set_awake()` (lines 73-85): "Real seams import their OS deps lazily and degrade to a silent no-op off Windows or when a subsystem is unavailable — a COM/tray failure must never break the frozen EXE."
**Apply to:** the `SetCurrentProcessExplicitAppUserModelID` call and any single-instance ctypes fallback — wrap in `if sys.platform == "win32": try: ... except Exception: pass`, exactly as every other OS call in `win_integration.py` does.

### Atomic JSON persistence via `FileManager.write_json_atomic` (applies to config_manager.py)
**Source:** `ConfigManager.save()` (`config_manager.py:96-97`), used by every settings mutation in the file including `persist_runtime_health()`.
**Apply to:** `persist_setup_acknowledged()` — call `self.save()`, never write `config.json` directly.

### Existence-check-then-datas-tuple for PyInstaller spec entries (applies to lecturepack.spec)
**Source:** `DEMO_ASSET`/`DEMO_WHISPER_MODEL` guards, `lecturepack.spec:49-69`.
**Apply to:** any spec edits — keep the `if not os.path.isfile(...): raise RuntimeError(...)` guard pattern even when removing a `datas` tuple, since `bundle_engine()` still needs the guarded path to exist at build time.

## No Analog Found

None — every file in scope extends an existing pattern already present in the same file or its immediate neighbor. This phase is fixing defects in established mechanisms, not introducing new architecture (consistent with RESEARCH.md's "Don't Hand-Roll" table: every one of the five defects already has an established in-repo mechanism to extend).

## Metadata

**Analog search scope:** `app/desktop/`, `app/packaging/`, `app/ui/app.js`, `lecturepack/infrastructure/`, `lecturepack/services/`, `.github/workflows/`, `tests/` — scoped directly from CONTEXT.md's `<canonical_refs>` file:line citations, no broader Glob/Grep sweep was needed since the canonical refs already named exact analog locations.
**Files scanned:** 10 target files + 6 analog source files (`win_integration.py`, `runtime_bootstrap.py`, `config_manager.py`, `app.js` overlay section, `test_runtime_packaged_smoke.py`, `test_beta3_packaging.py`) read directly; `build.py`, `lecturepack.spec`, `release.yml`, `update_service.py` read at targeted line ranges.
**Pattern extraction date:** 2026-07-30
