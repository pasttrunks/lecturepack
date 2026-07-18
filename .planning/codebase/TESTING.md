# Testing Patterns

**Analysis Date:** 2026-07-17

## Test Framework

**Runner:**
- pytest >= 8.0 with pytest-qt >= 4.4 (`requirements-dev.txt`)
- Config: `pytest.ini` (repo root):
  ```ini
  [pytest]
  testpaths = tests
  python_files = test_*.py
  python_classes = Test*
  python_functions = test_*
  addopts = -v
  ```
- **No `conftest.py` exists anywhere** — every fixture is defined locally inside the test module that uses it. Do not add shared fixtures to a conftest without explicit approval; follow the existing local-fixture pattern.
- **No coverage tooling configured** (no pytest-cov, no `.coveragerc`).
- **No custom markers registered.** `@pytest.mark.parametrize` is the only marker in use.

**Assertion Library:**
- Plain `assert` with f-string messages: `assert success, f"Slide detector failed with error: {error}"` (`tests/test_slide_detection.py:42`)

**Run Commands:**
```bash
python -m pytest                 # all tests (verbose, from pytest.ini)
python -m pytest tests/test_ui_v11.py            # one module
python -m pytest tests/test_ui_v11.py::test_selection_visuals_pure_state
```
Historical evidence of full runs is archived under `docs/evidence/v*/full_pytest_output.txt` (e.g. `docs/evidence/v1.2.0/stability/full_pytest_output.txt`).

## Test File Organization

**Location:**
- All tests in the flat `tests/` directory; tests are **not** co-located with source.
- `tests/fixtures/` — mock executable shims, generated media, ground truth:
  - `tests/fixtures/mock_whisper.py`, `mock_ffmpeg.py`, `mock_ffprobe.py` — CLI shims
  - `tests/fixtures/synthetic_lecture.mp4` — deterministic 65 s generated lecture video (built by `tests/fixtures/generate_test_video.py`)
  - `tests/fixtures/ground_truth/synthetic_lecture.json` — expected slide events/distractors for detection scoring
  - `tests/fixtures/sapi_*` — real whisper output samples used by transcript-format tests
  - `tests/fixtures/process_tree_parent.py` — helper spawn script for process-tree kill tests
- `tests/scratch/` — manual evaluation/screenshot scripts (`egypt_detector_eval.py`, `gen_screenshots.py`); not collected (names don't match `test_*.py`).
- Root-level helper scripts `tests/generate_study_evidence.py`, `tests/generate_ui_evidence.py`, `tests/validate_real_video.py` are **not collected** (don't match `test_*.py`) — they are evidence-generation drivers, not tests.

**Naming:**
- Modules: `test_<area>.py` — `test_integration.py`, `test_scheduler_and_engines.py`, `test_transcription_backend_contract.py`, `test_ui_v11.py`, `test_stability_phase.py`, `test_study_workspace_v12.py`
- Functions: `test_<behavior_in_words>` — `test_stage_cache_invalidated_by_setting_change`, `test_export_and_reexport_never_delete_job_or_candidates`, `test_provider_error_redacts_secret`
- Tests are **plain functions**, not classes (despite `python_classes = Test*` in `pytest.ini`, no test classes exist).

**Structure:**
- Many modules open with a docstring stating the phase and scope:
  ```python
  # tests/test_ollama_and_repair.py:1-10
  """
  Phase 4/5 fault-isolation tests: the Ollama client and the Context Repair
  worker must survive every failure mode without crashing anything ...
  """
  ```
- Long modules are grouped with ruled section banners (`tests/test_ui_v11.py:76-78`, `tests/test_scheduler_and_engines.py:42-44`):
  ```python
  # --------------------------------------------------------------------------- #
  # concurrent scheduler
  # --------------------------------------------------------------------------- #
  ```

## Test Structure

**Suite Organization:**
- Arrange inside the test body; heavy setup is factored into module-level `_make_*` builder helpers, not fixtures:
  ```python
  # tests/test_scheduler_and_engines.py:27-39
  def _make_controller(data_dir):
      config = ConfigManager(str(data_dir))
      config.set("whisper_exe", MOCK_WHISPER)
      config.set("whisper_model", "ggml-base.bin")
      controller = JobController(config)
      controller.ffmpeg_wrapper.ffmpeg_path = MOCK_FFMPEG
      controller.ffmpeg_wrapper.ffprobe_path = MOCK_FFPROBE
      return controller

  def _run(controller, qtbot, timeout=120000):
      with qtbot.waitSignal(controller.pipeline_completed, timeout=timeout):
          controller.run_pipeline()
  ```
- Module-level constants point at fixtures via absolute paths (tests must run from the repo root):
  ```python
  # tests/test_product_modes.py:23-26
  MOCK_WHISPER = os.path.abspath("tests/fixtures/mock_whisper.py")
  VIDEO = os.path.abspath("tests/fixtures/synthetic_lecture.mp4")
  ```
  Newer modules use `Path(__file__).parent` instead (`tests/test_stability_phase.py:24-28`) — prefer this form in new tests.
- Assertions carry intent-revealing messages: `assert files_before == files_after, "reject must never delete image files"` (`tests/test_ui_v11.py:206`).

**Local fixtures (the only 4 in the suite):**
```python
# tests/test_ui_v11.py:61-73
@pytest.fixture()
def window(qtbot, tmp_path):
    data_dir, job = _make_job(tmp_path)
    config = ConfigManager(data_dir)
    win = MainWindow(config)
    qtbot.addWidget(win)
    win.current_job = job
    win.controller.set_job(job)
    win._load_review_data()
    win.stack.setCurrentIndex(PAGE_REVIEW)
    win.show()
    qtbot.waitExposed(win)
    return win
```
The others: `window` in `tests/test_stability_phase.py:31`, `mock_groq_server` in `tests/test_groq_transcription.py:116`, and the FakeOllama fixture in `tests/test_ollama_and_repair.py:120`. Note the `window` fixture is **duplicated per module** (stability re-loads `_make_job` via `importlib.util` from `test_ui_v11.py` rather than sharing a fixture).

**Shared builders across modules** are imported directly: `from tests.test_ui_v11 import _make_job` (`tests/test_study_workspace_v12.py:17`, `tests/generate_study_evidence.py:21`).

## Mocking

**Framework:** `unittest.mock` (`patch`, `MagicMock`) + pytest's `monkeypatch` + hand-rolled fakes. Hand-rolled fakes are preferred over heavy mock framework usage.

**Pattern 1 — Mock executable shims (external tools: ffmpeg / ffprobe / whisper).**
The suite never mocks `subprocess`/`QProcess` for end-to-end pipeline tests. Instead, `tests/fixtures/mock_*.py` are **stand-in executables implementing the real CLI contract**: they parse `sys.argv` and write real output files.
```python
# tests/fixtures/mock_ffprobe.py (whole file, abridged)
def main():
    metadata = {"streams": [{"codec_type": "video", "codec_name": "h264",
                             "width": 640, "height": 480, "avg_frame_rate": "25/1"},
                            {"codec_type": "audio", "codec_name": "aac"}],
                "format": {"duration": "65.0", "size": "1000000"}}
    print(json.dumps(metadata))
```
`tests/fixtures/mock_whisper.py` parses `-m/-f/-of` and writes `<prefix>.json/.srt/.txt` with deterministic segments; `tests/fixtures/mock_ffmpeg.py` writes a valid-PCM-header WAV.

The production wrappers route `.py` paths through `sys.executable` (`lecturepack/infrastructure/ffmpeg_wrapper.py:67-70`, `lecturepack/infrastructure/whisper_wrapper.py:146-152`), so tests inject shims by config + direct attribute override:
```python
# tests/test_integration.py:26-32
config.set("whisper_exe", mock_whisper)
config.set("whisper_model", "ggml-base.bin")
controller = JobController(config)
controller.ffmpeg_wrapper.ffmpeg_path = mock_ffmpeg
controller.ffmpeg_wrapper.ffprobe_path = mock_ffprobe
```
`cv_engine` explicitly detects shim paths and falls back to its legacy decoder for them (`lecturepack/infrastructure/cv_engine.py:77-80`).

**Pattern 2 — In-process HTTP servers for provider APIs (Groq, Ollama).**
A `ThreadingHTTPServer` bound to `("127.0.0.1", 0)` on a daemon thread; the fixture yields the base URL and shuts down:
```python
# tests/test_groq_transcription.py:116-128
@pytest.fixture
def mock_groq_server():
    _MockGroqHandler.calls = 0
    ...
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockGroqHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/openai/v1/audio/transcriptions"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
```
Handler state (calls, auth headers, bodies, failure modes) is class-level and reset per test (`tests/test_groq_transcription.py:85-113`). The Ollama fake supports modes `ok | slow | malformed | drop_midstream | http_error | slow_stream` to exercise every failure class (`tests/test_ollama_and_repair.py:30-117`).

**Pattern 3 — Hand-rolled Qt fakes with real Signals.**
When the contract is Qt-signal-based, the fake is a real `QObject` so signal wiring works unmodified:
```python
# tests/test_transcription_backend_contract.py:22-37
class FakeWhisperWrapper(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)
    backend_detected = Signal(str)

    def start_transcription(self, *args, **kwargs):
        self.calls.append((args, kwargs))
```
Other fakes: `MemorySecretStore`, `CopyEncoder` (`tests/test_groq_transcription.py:26-45`), `FakeClipboard` (`tests/test_ui_v11.py:268-273`), `FakeEngineRegistry` (`tests/test_transcription_backend_contract.py:40-44`).

**Pattern 4 — `unittest.mock.patch` for arg-construction verification.**
```python
# tests/test_study_workflow.py:46-71
with patch('lecturepack.infrastructure.whisper_wrapper.QProcess') as MockQProcess:
    mock_proc_instance = MagicMock()
    MockQProcess.return_value = mock_proc_instance
    wrapper.start_transcription(audio_path="audio.wav", ...)
    mock_proc_instance.start.assert_called_once()
    program, args = mock_proc_instance.start.call_args[0]
    assert "--vad" in args
```

**Pattern 5 — `monkeypatch` for module functions, env vars, and instance methods.**
```python
# tests/test_scheduler_and_engines.py:183-185
monkeypatch.setattr(
    "lecturepack.infrastructure.transcription_engines._app_root",
    lambda: str(tmp_path))
# tests/test_stability_phase.py:220
monkeypatch.setenv("LECTUREPACK_TREE_PID_FILE", str(child_pid_file))
# tests/test_ui_v11.py:173 — instance method replacement
monkeypatch.setattr(view, "scrollToItem", record_scroll)
```

**What to Mock:**
- External executables (ffmpeg/ffprobe/whisper) → `.py` shims in `tests/fixtures/`
- Network providers (Groq, Ollama) → localhost `ThreadingHTTPServer`
- OS clipboard → `FakeClipboard` (the real clipboard is contended on CI/Windows — see comment at `tests/test_ui_v11.py:265`)
- `QMessageBox.question` and other modal dialogs → `monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: ...)` (`tests/test_groq_transcription.py:278`)
- Secret stores → `MemorySecretStore` / `monkeypatch.setattr(WindowsCredentialStore, "has_secret", ...)`

**What NOT to Mock:**
- The CV pipeline — slide detection tests run the real `SlideDetectorWorker` against the synthetic video (`tests/test_slide_detection.py:27-37`)
- Persistence — real `FileManager` reads/writes under `tmp_path`
- Qt widgets — real `MainWindow`/pages via pytest-qt, including pixel-level rendering checks
- `AGENTS.md` rule: "Do not use mocked output as proof that an external integration works. Mock external tools for unit tests but verify real integration separately" (real-integration checks live in `tests/validate_real_video.py` and `docs/evidence/v*/groq_live_validation/`).

## Fixtures and Factories

**Test Data:**
- **Job factory:** `_make_job(tmp_path, n_slides=4)` builds a fully "completed" job on disk — candidate PNGs written with cv2, `candidates.json`, `raw.json`, `normalized.json`, all stages marked completed (`tests/test_ui_v11.py:28-58`). This is the canonical way to get a review-ready job.
- **Raw transcript constants** at module top:
  ```python
  # tests/test_ui_v11.py:19-25
  RAW_JSON = {"result": {"language": "en", "transcription": [
      {"offsets": {"from": 0, "to": 4000}, "text": " Welcome to the lecture on Egypt."},
      ...]}}
  ```
- **Synthetic media:** `tests/fixtures/generate_test_video.py` renders the deterministic 65 s lecture (slides, pointer motion, webcam overlay, captions, progressive builds) so detection behavior is reproducible; expected events are in `tests/fixtures/ground_truth/synthetic_lecture.json`, and `lecturepack/services/detection_eval.py` scores candidates against it (`tests/test_detection_eval.py`).
- **Minimal dicts** for targeted units: `_minimal_norm()` (`tests/test_stability_phase.py:76-84`).
- All file artifacts go under `tmp_path`; jobs get `data_dir = tmp_path / "data"`. Some tests deliberately use paths with spaces (`tmp_path / "Lecture Pack Data"`, `tests/test_job_persistence.py:7`) to guard the Windows path-safety rules.

**Location:** fixture data builders live at the top of the consuming module; media/shims in `tests/fixtures/`.

## Coverage

**Requirements:** None enforced — no coverage config, no thresholds.

**View Coverage:** Not configured. If needed ad hoc:
```bash
python -m pip install pytest-cov   # not in requirements-dev.txt; needs approval per AGENTS.md
python -m pytest --cov=lecturepack
```

## Test Types

**Unit Tests:**
- Pure-logic modules tested without Qt: `tests/test_transcript_formats.py` (serializers), `tests/test_detection_eval.py` (metric logic on hand-built candidate lists), `tests/test_context_repair.py` (engine on in-memory transcripts), chunk-plan/merge tests in `tests/test_groq_transcription.py:48-82`.
- Argument/contract construction: `tests/test_study_workflow.py:19-133`, `tests/test_transcription_backend_contract.py`.
- Characteristic style: direct function calls, plain asserts, no Qt.

**Integration Tests:**
- Full pipeline through the **real** `JobController` + real wrappers against mock executables, synchronized on Qt signals:
  ```python
  # tests/test_integration.py:49-50
  with qtbot.waitSignal(controller.pipeline_completed, timeout=20000):
      controller.run_pipeline()
  ```
  Then assert on persisted job state and output files (`slides.pdf`, `study-pack.html`, `transcript.srt`, `tests/test_integration.py:71-75`). Same harness reused by `tests/test_product_modes.py` and `tests/test_scheduler_and_engines.py` (concurrency, cache keys, cancellation).

**UI Tests (pytest-qt):**
- Real native windows (not offscreen) built by the `window` fixture; interactions via `qtbot.mouseClick` / `qtbot.keyClick` with modifiers (`tests/test_ui_v11.py:126-154`), `qtbot.wait(ms)` for event-loop settling, `qtbot.waitExposed(win)`.
- **Pixel-level assertions** where visuals are the contract: grab the viewport and count accent-colored pixels (`tests/test_ui_v11.py:99-123`); pure-state visual contracts are tested without rendering via `theme.selection_visuals()` (`tests/test_ui_v11.py:80-96`).
- Parametrized display modes: `@pytest.mark.parametrize("mode", ["grid", "list"])` (`tests/test_ui_v11.py:157`).
- Gotcha documented in-code: synthetic modifier clicks leave Qt's `keyboardModifiers()` sticky — send one unmodified event to normalize (`tests/test_ui_v11.py:151-154`).

**Safety/Invariant Tests:**
- No-deletion guarantees: `tests/test_packaging_and_safety.py:52-68` (export/re-export never deletes job dir or candidate images), `tests/test_ui_v11.py:193-220` (reject never deletes files).
- RAW immutability: byte-identical comparison after edits (`tests/test_ui_v11.py:359-360`).
- Secret hygiene: redaction of API keys and "audio only, no slide/transcript text in upload body" (`tests/test_groq_transcription.py:131-160`).
- Process-tree kills scoped to owned PIDs; orphan checks via `tasklist` (`tests/test_stability_phase.py:54-58`).
- Artifact signatures (sha256/size/mtime) compared before/after operations (`tests/test_stability_phase.py:94-106`).

**E2E / Packaged Tests:**
- Not pytest. Headless drivers inside the app itself: `--selftest` and `--run-acceptance` in `lecturepack/app.py:121-184`, plus `lecturepack/acceptance.py`. `tests/validate_real_video.py` runs real media outside pytest.

## Common Patterns

**Async / Signal Testing:**
```python
# wait for a specific signal with a payload filter
def check_export_finished(stage, success, err):
    return stage == STAGE_EXPORT

with qtbot.waitSignal(controller.stage_finished, timeout=15000,
                      check_params_cb=check_export_finished):
    controller.export_now()
# tests/test_integration.py:62-66
```
- Synchronous worker execution when timing matters: call `worker.run()` directly and capture signal emissions in a list (`tests/test_slide_detection.py:30-40`).
- Cancellation tests use `QTimer.singleShot(50, controller.cancel)` from a signal handler, then `qtbot.wait(1500)` and assert terminal states + `worker.isFinished()` (`tests/test_scheduler_and_engines.py:87-106`).
- Retry-through-Windows-races helper with deadline loop: `_read_pid_file` (`tests/test_stability_phase.py:61-73`).
- Long timeouts are normal: 20–150 s (`tests/test_integration.py:49`, `tests/test_scheduler_and_engines.py:37`, `lecturepack/app.py:103`).

**Error Testing:**
```python
# provider failure modes are parameterized via fake-server mode flags
_MockGroqHandler.fail_first = True
client = GroqHttpClient(mock_groq_server, max_retries=1, sleep=lambda _s: None)
result = client.transcribe(str(audio), api_key="gsk_super_secret", ...)
assert _MockGroqHandler.calls == 2   # retried exactly once
# tests/test_groq_transcription.py:131-144
```
- Injected `sleep=lambda _s: None` keeps backoff tests instant — follow this pattern for any retry logic.
- Typed errors are asserted by `kind`/attributes, not by message text (`tests/test_ollama_and_repair.py` raises/asserts `OllamaTimeout`, `OllamaBadResponse`, `OllamaCancelled`).
- Fault-injection via `monkeypatch.setattr(urllib.request, "urlopen", fail)` for transport errors (`tests/test_groq_transcription.py:147-160`).

**Qt Test Boilerplate (copy this shape for new UI tests):**
```python
def test_something(window, qtbot, tmp_path):
    view = window.slides_view
    view.clearSelection()
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.ControlModifier, rect.center())
    qtbot.wait(50)
    assert window.selected_count_lbl.text() == "Selected: 1"
```
Always `qtbot.addWidget(win)` for top-level widgets so they are destroyed between tests.

---

*Testing analysis: 2026-07-17*
