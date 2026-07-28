# Phase 1: Packaging & Release - Pattern Map

**Mapped:** 2026-07-18  
**Files classified:** 6 implementation/test files  
**Analogs found:** 6 / 6  
**Constraint:** Analysis only. This map does not authorize implementation or any Phase 2 reliability work.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `lecturepack/__init__.py` | package config / canonical metadata | transform (one version value to consumers) | `lecturepack/app.py:134-150` | role-match |
| `lecturepack/constants.py` | application config | transform (canonical version re-export) | `lecturepack/models/job.py:4-7,36-40` | exact consumer-flow match |
| `build_release.py` | release utility | batch + external-process + file-I/O | `build_release.py:70-76,97-106,165-240` | exact in-place pattern |
| `LecturePack.spec` | build config | batch dependency collection | `LecturePack.spec:14-63,67-93` | exact in-place pattern |
| `tests/test_packaging_and_safety.py` | release regression test | file-I/O + request-response | `tests/test_packaging_and_safety.py:8-19` | exact |
| `tests/test_packaging_and_safety.py` (self-test smoke coverage) | subprocess smoke test | request-response / external-process | `tests/test_stability_phase.py:54-58`; `lecturepack/__main__.py:1-4` | role-match |

The phase also produces build/evidence artifacts (`dist-release/`, portable ZIP,
`SHA256SUMS.txt`, `BUILD_MANIFEST.json`, and captured pytest/self-test output),
but these are outputs of the established release flow rather than source files
whose implementation pattern needs a separate analog.

## Pattern Assignments

### `lecturepack/__init__.py` (package config, transform)

**Analog:** `lecturepack/app.py:134-150`

The self-test already treats `lecturepack.__version__` as the package-level
version authority and reports it directly:

```python
import cv2, numpy, PySide6  # noqa: F401
from lecturepack import __version__
from lecturepack.services import transcript_service, detection_eval  # noqa: F401
# ...
print(f"SELFTEST PASS: LecturePack v{__version__} launched, "
      f"cv2 {cv2.__version__}, PySide6 {PySide6.__version__}, offscreen OK")
```

**Apply:** Keep a plain, import-safe `__version__ = "1.2.0"` assignment in
`lecturepack/__init__.py`. Do not import application modules from the package
initializer; `app.py` imports the initializer during headless/frozen startup,
so the authority must remain dependency-free.

**Current target:** `lecturepack/__init__.py:1-2` is already the minimal shape;
only its stale value is wrong.

---

### `lecturepack/constants.py` (application config, transform)

**Analog:** `lecturepack/models/job.py:4-7,36-40`

Downstream code consumes `APP_VERSION` through the constants module and writes
it into every new job manifest:

```python
from lecturepack.constants import (
    STAGE_INSPECT, PRESETS, STAGES, STAGE_REVIEW_READY,
    APP_VERSION, PRODUCT_MODE_STUDY_PACK, PRODUCT_MODES
)
# ...
self.manifest = {
    "schema_version": 1,
    "job_id": self.job_id,
    "created_at": datetime.datetime.now().isoformat(),
    "app_version": APP_VERSION,
```

**Apply:** Preserve `APP_VERSION` as the public constants-layer name, but bind
it to the package authority with the same absolute-import convention used
throughout the codebase:

```python
from lecturepack import __version__

APP_NAME = "Lecture Pack"
APP_VERSION = __version__
```

This avoids touching consumers such as `Job` and keeps the manifest contract
unchanged. `lecturepack/constants.py:1-4` is the only affected import/assignment
area; all stage, backend, mode, and preset constants below it are unrelated.

---

### `build_release.py` (release utility, batch + external-process + file-I/O)

**Analog:** the existing five-step release pipeline in the same file.

**Absolute-path and process failure pattern** (`build_release.py:23-28,70-76`):

```python
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
RELEASE_DIR = os.path.join(PROJECT_ROOT, "dist-release")

def run(cmd, **kwargs):
    print(f"  > {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, **kwargs)
    if result.returncode != 0:
        print(f"  FAILED (exit {result.returncode})")
        sys.exit(1)
    return result
```

**PyInstaller invocation pattern** (`build_release.py:97-106`):

```python
run([
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--distpath", DIST_DIR,
    "--workpath", BUILD_DIR,
    "LecturePack.spec",
])
```

**Portable archive pattern** (`build_release.py:165-177`):

```python
zip_name = f"{APP_NAME}-portable-{VERSION}.zip"
zip_path = os.path.join(RELEASE_DIR, zip_name)
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            fp = os.path.join(root, fn)
            arcname = os.path.join(APP_NAME, os.path.relpath(fp, app_dir))
            zf.write(fp, arcname)
```

**Integrity artifact pattern** (`build_release.py:179-240`): calculate SHA-256
from the completed ZIP/binaries, write `SHA256SUMS.txt`, serialize
`BUILD_MANIFEST.json`, and copy both into the packaged app directory.

**Apply:** Reuse the package authority rather than retain a fourth literal:

```python
from lecturepack import __version__

VERSION = __version__
```

Do not restructure the five build steps or binary directory conventions. The
research found the existing v1.1 copy pipeline still matches the approved
release layout: FFmpeg under `bin/`, CPU whisper runtime beside the EXE, and
optional Vulkan under `bin/vulkan/`.

**Error handling:** Preserve the explicit non-zero exit boundary in `run()`
and the existing required-output guard at `build_release.py:108-111`.

---

### `LecturePack.spec` (build config, batch dependency collection)

**Analog:** the existing `Analysis` / `EXE` / `COLLECT` onedir layout in the
same file (`LecturePack.spec:14-93`).

**Collection pattern** (`LecturePack.spec:14-21`):

```python
a = Analysis(
    [os.path.join(spec_root, 'lecturepack', 'app.py')],
    pathex=[spec_root],
    binaries=[],
    datas=[
        (os.path.join(spec_root, 'lecturepack', 'constants.py'), 'lecturepack'),
    ] + pyside6_datas,
    hiddenimports=[
```

**Hidden-import style** (`LecturePack.spec:21-53`): one fully qualified module
string per line, with LecturePack modules first and third-party imports after
them. Preserve that grouping and append current modules to the LecturePack
section.

**Required v1.2 additions:**

```text
lecturepack.ui.pages.home_page
lecturepack.ui.pages.process_page
lecturepack.ui.pages.review_page
lecturepack.ui.pages.transcript_page
lecturepack.ui.pages.exports_page
lecturepack.ui.pages.settings_page
lecturepack.ui.pages.study_page
lecturepack.ui.widgets.slide_grid
lecturepack.ui.widgets.context_repair_panel
lecturepack.services.transcript_store
lecturepack.services.groq_transcription
lecturepack.services.ai_repair_service
lecturepack.services.study_service
lecturepack.services.transcription_backends
lecturepack.infrastructure.video_reader
lecturepack.infrastructure.transcription_engines
lecturepack.infrastructure.ollama_client
lecturepack.infrastructure.process_tree
lecturepack.infrastructure.secret_store
lecturepack.infrastructure.whisper_detector
```

This list combines the research audit with the explicit
`REQ-packaging-spec-audit` list. `crop_selector` is already present at
`LecturePack.spec:39`; do not duplicate it. A mechanical comparison against
the 42 current Python modules finds additional omitted package/entry/theme
modules (`lecturepack.__main__`, package `__init__` modules, and
`lecturepack.ui.theme`), but these are statically reachable from the `app.py`
entry graph. The acceptance requirement is to add the named dynamically risky
v1.1/v1.2 modules above and then prove the frozen executable, not to treat raw
module-count equality as sufficient validation.

**Assertion preservation** (`LecturePack.spec:57-63`):

```python
excludes=[
    'tkinter', 'test', 'pdb',
    'IPython', 'jupyter', 'notebook',
],
noarchive=False,
optimize=1,
```

**Apply:** Change only `optimize=1` to `optimize=0`. The self-test uses an
assertion at `lecturepack/app.py:146`; optimization level 1 removes it and
invalidates the sanity check. Preserve the approved onedir construction
(`exclude_binaries=True` plus `COLLECT`) at `LecturePack.spec:67-93`.

---

### `tests/test_packaging_and_safety.py` (release regression tests)

**Analog:** its existing packaged-layout test (`tests/test_packaging_and_safety.py:8-19`).

```python
def test_bundled_binary_resolution_next_to_exe(tmp_path):
    app = tmp_path / "app"
    (app / "bin").mkdir(parents=True)
    (app / "whisper-cli.exe").write_text("x")
    (app / "bin" / "ffmpeg.exe").write_text("x")

    cfg = ConfigManager(str(tmp_path / "data"))
    cfg.app_dir = str(app)  # simulate frozen app_dir
    assert cfg._find_bundled_binary("whisper-cli.exe") == str(app / "whisper-cli.exe")
```

**Apply for version/spec checks:** Extend this focused packaging module rather
than scattering release assertions across UI or service tests. Follow its
plain `tmp_path` setup and direct assertions. Verify at minimum:

- `lecturepack.__version__ == "1.2.0"`;
- `lecturepack.constants.APP_VERSION == lecturepack.__version__`;
- a new `Job` manifest receives `"app_version": "1.2.0"` (consumer pattern is
  `lecturepack/models/job.py:36-40`);
- the spec contains all required v1.2 module names and `optimize=0`.

Static spec assertions guard configuration drift; they do not replace the real
PyInstaller build and packaged self-test acceptance steps.

---

### `tests/test_packaging_and_safety.py` (self-test subprocess smoke coverage)

**Analogs:** `tests/test_stability_phase.py:54-58`,
`lecturepack/__main__.py:1-4`, and `lecturepack/app.py:121-156,187-194`.

The established subprocess test style uses an argument list, captures output,
sets a finite timeout, and inspects the return code/output instead of using a
shell:

```python
result = subprocess.run(
    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
    capture_output=True, text=True, timeout=5, check=False)
```

The module entry point delegates directly to `app.main`:

```python
from lecturepack.app import main

if __name__ == "__main__":
    main()
```

**Apply:** Invoke the real development entry path with a list such as
`[sys.executable, "-m", "lecturepack", "--selftest"]`, force/retain
`QT_QPA_PLATFORM=offscreen` in a copied environment, use a finite timeout, and
assert all three observable outcomes:

1. return code is 0;
2. stdout contains `SELFTEST PASS`;
3. stdout reports `LecturePack v1.2.0`.

On failure, include captured stdout/stderr in the assertion message. Do not
mock `run_selftest`; the purpose is to exercise import routing, Qt
initialization, `MainWindow` construction, transcript normalization, cleanup,
and the CLI exit boundary together. The same contract must then be run against
`LecturePack.exe --selftest` after packaging.

## Shared Patterns

### Version flow

```text
lecturepack.__version__
    -> constants.APP_VERSION
        -> Job.manifest["app_version"]
    -> build_release.VERSION
        -> ZIP name, checksums header, BUILD_MANIFEST.json
    -> app.run_selftest output / MainWindow title
```

There should be exactly one semantic-version literal after the change. Cache
fingerprints `DETECTOR_VERSION` (`job_controller.py:48`) and
`REPAIR_PROMPT_VERSION` (`ollama_client.py:258`) are algorithm/prompt cache
keys, not release metadata; do not change them for a version-only release.

### External process safety

- Pass command arguments as a list; never execute through a shell.
- Use absolute or project-root-resolved paths.
- Capture output for diagnostic assertions and apply a finite timeout.
- Preserve `build_release.run()` as the fail-fast boundary for build commands.

### Release proof hierarchy

1. Static regression tests verify version wiring and spec contents.
2. `python -m pytest -v` proves the source test suite.
3. `python -m lecturepack --selftest` proves the development entry point.
4. `build_release.py` proves PyInstaller and archive generation.
5. Extracted `LecturePack.exe --selftest` from a clean path proves the frozen
   bundle rather than mocked packaging behavior.

### Test-count reconciliation

The apparent `149` versus `151` discrepancy is counting methodology, not
evidence that two tests were deleted:

- Current source scan: **149 test functions**.
- `tests/test_stability_phase.py:272` parametrizes
  `test_real_wrappers_terminate_their_owned_trees` over two wrapper kinds,
  adding one collected case beyond its single function.
- `tests/test_ui_v11.py:157` parametrizes
  `test_current_slide_drives_preview_and_scroll` over grid/list modes, adding
  one more collected case.
- Therefore pytest should collect **151 items**.
- Historical v1.2 evidence confirms this at
  `docs/evidence/v1.2.0/groq_backends/full_pytest_output.txt:9,163` and
  `docs/evidence/v1.2.0/groq_live_validation/full_pytest_output.txt:9,163`.

Re-run `python -m pytest --collect-only -q` and the full suite in the current
environment, then document the actual current output. Do not rewrite or weaken
tests merely to make a stale count match.

## No Analog Found

No classified source/test file lacks an analog. There is, however, no second
independent PyInstaller spec or release script in the repository. For those
two targets, preserve the current in-place `Analysis`/`EXE`/`COLLECT` and
five-step release patterns, and use `01-RESEARCH.md` plus real build evidence
for the v1.2-specific additions.

## Scope Guardrails / Non-Goals

- Do not implement Phase 2 cooperative cancellation for Align/Export workers.
- Do not move ffprobe inspection off the GUI thread or add its timeout here.
- Do not add the Phase 2 non-ASCII image-I/O and cancellation fixtures.
- Do not alter stage scheduling, transcription providers, cache fingerprints,
  or source/AI provenance boundaries.
- Do not add dependencies, telemetry, external network calls, or credential
  handling.
- Never modify/delete an original lecture video; self-test uses a temporary
  data directory and no media.
- Do not claim clean-machine success from static tests or mocks. The actual
  packaged executable and extracted ZIP are required release evidence.

## Metadata

**Analog search scope:** project root, `lecturepack/`, `tests/`, `docs/evidence/`  
**Python modules compared with spec:** 42  
**Current explicit LecturePack hidden imports:** 18  
**Current test functions:** 149  
**Expected collected cases:** 151  
**Pattern extraction date:** 2026-07-18
