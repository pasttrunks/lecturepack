# Coding Conventions

**Analysis Date:** 2026-07-17

## Naming Patterns

**Files:**
- `snake_case.py` throughout: `lecturepack/infrastructure/ffmpeg_wrapper.py`, `lecturepack/controllers/job_controller.py`, `lecturepack/services/transcript_store.py`
- Test files: `test_<feature>.py` in `tests/` (`tests/test_ui_v11.py`)
- Mock shim executables: `mock_<tool>.py` in `tests/fixtures/` (`tests/fixtures/mock_whisper.py`)

**Classes:**
- PascalCase: `FFmpegWrapper` (`lecturepack/infrastructure/ffmpeg_wrapper.py:9`), `JobController` (`lecturepack/controllers/job_controller.py:51`), `BackendCapabilities` (`lecturepack/services/transcription_backends.py:31`)
- Worker classes end in `Worker`: `SlideDetectorWorker`, `AlignWorker`, `ExportWorker`, `AiRepairWorker`, `_GroqWorker`
- Wrappers/adapters end in `Wrapper` / `Backend` / `Registry` / `Manager`: `WhisperWrapper`, `LocalWhisperCppBackend`, `BackendRegistry`, `ConfigManager`, `FileManager`
- Private/helper classes get a leading underscore: `_GroqWorker` (`lecturepack/services/transcription_backends.py:202`), `_NumericItem` (`lecturepack/ui/pages/transcript_page.py:56`), `_MockGroqHandler` (`tests/test_groq_transcription.py:85`)

**Functions / methods:**
- `snake_case`: `detect_binaries()`, `start_transcription()`, `align_and_export()`, `read_json_safe()`
- Private methods: single leading underscore — `_parse_fps()` (`lecturepack/infrastructure/ffmpeg_wrapper.py:99`), `_load_review_data()`, `_stage_fingerprint()`
- Qt slots follow two idioms:
  - `_handle_<source>_<event>`: `_handle_ready_read`, `_handle_ffmpeg_finished`, `_handle_transcription_result`
  - `_on_<action>` for UI triggers: `_on_delete_shortcut`, `_on_undo_shortcut`, `_on_transcript_seek` (`lecturepack/ui/main_window.py`)

**Variables:**
- `snake_case`, including instance attrs: `self.ffmpeg_path`, `self.whisper_exe_path`, `self.last_cancel_report`
- Qt signals are lowercase class attributes with an inline payload comment:
  ```python
  # lecturepack/infrastructure/whisper_wrapper.py:8-10
  progress = Signal(str)
  finished = Signal(bool, str) # success, error_message
  backend_detected = Signal(str)  # actual loaded backend, e.g. "Vulkan (Vulkan0)" or "CPU"
  ```

**Constants:**
- `UPPER_SNAKE_CASE`, centralized in `lecturepack/constants.py` (`STAGE_INSPECT`, `SUPPORTED_VIDEO_EXTENSIONS`, `PRESETS`, `DEFAULT_DATA_DIR`, `PRODUCT_MODE_STUDY_PACK`)
- Module-private constants get a leading underscore: `_COMMON_GUARDS` (`lecturepack/constants.py:72`), `_FMT_MAP` (`lecturepack/ui/pages/transcript_page.py:43`), `_SORT_ROLE` (`lecturepack/ui/pages/transcript_page.py:53`), `_DETACHED_WORKERS` (`lecturepack/services/ai_repair_service.py:41`)
- Timeout/limit tunables are module-level UPPER_SNAKE with unit comments:
  ```python
  # lecturepack/infrastructure/ollama_client.py:33-36
  DEFAULT_BASE_URL = "http://localhost:11434"
  CONNECT_TIMEOUT = 4.0          # seconds -- availability probes
  GENERATION_TIMEOUT = 180.0     # seconds -- hard cap for one chat request
  STREAM_STALL_TIMEOUT = 60.0    # seconds without any streamed byte -> timeout
  ```

## Code Style

**Formatting:**
- No formatter or linter is configured (no `pyproject.toml`, `.flake8`, `.ruff`, `setup.cfg`, or pre-commit config). Style is maintained by convention only.
- 4-space indentation, no tabs.
- Long calls are wrapped with hanging indents; closing paren style varies (older code puts it on its own line, newer code aligns with the call).

**Typing:**
- The codebase is split into an untyped older core (v1.0: wrappers, controller, UI pages) and typed newer modules (v1.1+). Match the module you are editing.
- Newer modules start with `from __future__ import annotations` and use `typing.Any/Dict/List/Optional` plus PEP 604 unions (`str | None`):
  ```python
  # lecturepack/services/groq_transcription.py:58-61
  def plan_audio_chunks(duration_seconds: float, max_upload_bytes: int,
                        overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
                        max_chunk_seconds: float = DEFAULT_MAX_CHUNK_SECONDS
                        ) -> list[AudioChunk]:
  ```
- Frozen dataclasses are the contract type for cross-layer data in newer service code:
  ```python
  # lecturepack/services/transcription_backends.py:66-80
  @dataclass(frozen=True)
  class TranscriptionRequest:
      audio_path: str
      output_prefix: str
      model: str
      language: str = "en"
      ...
      cancel_token: CancellationToken = field(default_factory=CancellationToken,
                                               compare=False, repr=False)
  ```
- Plain JSON-shaped dicts remain the model/persistence format everywhere else (`Job.manifest`, `Job.settings`, candidate dicts, transcript segments). Segment dict shape is documented in `lecturepack/services/transcript_store.py:19-22`.

**Data model idiom:**
- Dict-based records with `"schema_version"` keys for anything persisted to disk (`lecturepack/models/job.py:37`, `lecturepack/infrastructure/config_manager.py:27`).
- Backward compatibility is handled by `setdefault` migrations on load, never by rewriting old files up front — see `Job.load()` (`lecturepack/models/job.py:86-115`) and `ConfigManager.load()` (`lecturepack/infrastructure/config_manager.py:57-83`).

## Import Organization

**Order:**
1. stdlib (`os`, `sys`, `json`, `subprocess`, `threading`)
2. PySide6 (`from PySide6.QtCore import ...`, `QtWidgets`, `QtGui`)
3. Third-party (`cv2`, `numpy`, `skimage`, `img2pdf`)
4. Application, always absolute `lecturepack.*` imports: `from lecturepack.infrastructure.file_manager import FileManager`

No relative imports, no path aliases, no `__all__`. `from __future__ import annotations` (when present) is line 1 after the module docstring.

**Function-local imports** are an accepted idiom to break import cycles and defer heavy/optional deps — do not "hoist" them without checking:
- `lecturepack/services/export_service.py:27-30` imports constants inside `align_and_export()`
- `lecturepack/infrastructure/whisper_wrapper.py:26` imports `WhisperCapabilityDetector` inside a method
- `lecturepack/services/transcription_backends.py:229-235` imports the Groq machinery inside `_GroqWorker.run()` so the frozen bundle and unit tests can import the module without those deps

## Error Handling

**Patterns:**

1. **Typed exception families with a machine-readable `kind`.** Each integration defines a base error plus subclasses; callers branch on `kind`, not on message text:
   ```python
   # lecturepack/infrastructure/ollama_client.py:39-61
   class OllamaError(Exception):
       """Base class; ``kind`` is a stable machine-readable failure category."""
       kind = "error"
   class OllamaUnavailable(OllamaError):
       kind = "unavailable"
   class OllamaTimeout(OllamaError):
       kind = "timeout"
   ```
   Same shape for `GroqError(message, *, kind, status, retryable, retry_after)` (`lecturepack/services/groq_transcription.py:37-44`) and `SecretStoreError(RuntimeError)` (`lecturepack/infrastructure/secret_store.py:19`).

2. **Never raise across the Qt thread/signal boundary.** Workers catch everything in `run()` and emit a result signal:
   ```python
   # lecturepack/controllers/job_controller.py:37-44
   def run(self):
       try:
           service = ExportService(self.job)
           service.align_and_export()
           self.finished.emit(True, "")
       except Exception as e:
           self.finished.emit(False, str(e))
   ```
   The AI repair worker emits a typed triple `failed(kind, message, diagnostic_details)` (`lecturepack/services/ai_repair_service.py:77-80`).

3. **"Absolute boundary" catch-alls at fault-isolation seams, explicitly commented:**
   ```python
   # lecturepack/infrastructure/ollama_client.py:114-120
   def is_available(self) -> Dict[str, Any]:
       """Never raises. Returns {available, version?, error?}."""
       try:
           return {"available": True, "version": self.version()}
       except OllamaError as e:
           return {"available": False, "error": str(e), "kind": e.kind}
       except Exception as e:  # absolute boundary
   ```
   Use bare `except Exception` only at these documented outer boundaries (see also `lecturepack/services/ai_repair_service.py:129`); catch specific types elsewhere.

4. **Safe-IO helpers instead of try/except at call sites.** `FileManager.read_json_safe(path, default)` swallows missing/corrupt/BOM'd JSON and returns the default; `FileManager.write_json_atomic()` writes `<file>.tmp` then `os.replace` (`lecturepack/infrastructure/file_manager.py:6-28`). All job/config persistence goes through these two functions.

5. **Redact secrets and local paths before persisting or displaying errors:**
   ```python
   # lecturepack/services/transcription_backends.py:117-124
   def _safe_error(message: str, request: Optional[TranscriptionRequest]) -> str:
       text = str(message or "Transcription failed.").replace("\r", " ").replace("\n", " ")
       if request is not None:
           for value in (request.audio_path, request.output_prefix, request.model):
               if value:
                   text = text.replace(str(value), "[local path]")
       return text[:1000]
   ```
   Bearer tokens are regex-redacted in `_safe_provider_message` (`lecturepack/services/groq_transcription.py:92-97`).

6. **Fallbacks are fail-closed.** Unknown selections resolve to the private local backend with a human-readable reason (`BackendRegistry.resolve`, `lecturepack/services/transcription_backends.py:431-437`); missing ffmpeg falls back to the legacy cv2 decoder (`lecturepack/infrastructure/cv_engine.py:76-80`).

## Logging

**Framework:** none — the `logging` module is not used anywhere in `lecturepack/`.

**Patterns:**
- Log lines flow as **Qt signals** and are rendered by the UI/status bar:
  - `JobController.stage_log = Signal(str, str)` (stage, message) — `lecturepack/controllers/job_controller.py:54`
  - `Wrapper.progress = Signal(str)` for raw subprocess output (`lecturepack/infrastructure/ffmpeg_wrapper.py:11`)
  - `SlideDetectorWorker.status_message = Signal(str)` (`lecturepack/infrastructure/cv_engine.py:50`)
- Plain services take an injected callback instead of knowing about Qt:
  ```python
  # lecturepack/services/export_service.py:15-17
  def log(self, msg):
      if self.log_callback:
          self.log_callback(msg)
  ```
- `print()` is reserved for CLI drivers (`--selftest`, `--run-acceptance` in `lecturepack/app.py`) and for verbose diagnostics inside tests (`tests/test_integration.py:35-38`).

## Comments

**When to Comment:**
- Explain **why**, referencing the version/phase and the failure class being prevented. Comments frequently cite design history:
  ```python
  # lecturepack/services/ai_repair_service.py:7-10 (module docstring)
  # The v1.0.1 crash class: the Context Repair dialog generated proposals
  # synchronously in its constructor on the GUI thread; a configured provider
  # meant blocking network calls (60 s timeout each) with no exception boundary.
  ```
- Long-form design context lives in **module-level banner docstrings**, not inline:
  ```
  # lecturepack/ui/theme.py:1-12
  """
  lecturepack.ui.theme
  ====================

  Light/dark theme for the v1.1 shell. Uses the Fusion style with an explicit
  QPalette plus a small QSS layer ...
  """
  ```
  Modules using this style: `lecturepack/infrastructure/ollama_client.py`, `lecturepack/services/transcript_store.py`, `lecturepack/ui/main_window.py`, `lecturepack/ui/pages/transcript_page.py`, `lecturepack/infrastructure/cv_engine.py`.
- Section separators inside large files use a ruled banner:
  ```python
  # --------------------------------------------------------------------------- #
  # Plumbing
  # --------------------------------------------------------------------------- #
  ```
  (`lecturepack/infrastructure/ollama_client.py:72-74`, also used to group tests in `tests/test_ui_v11.py:76-78`).

**Docstrings:**
- Triple-double-quoted, one-line summary for functions; parameters described in prose for complex methods:
  ```python
  # lecturepack/infrastructure/ffmpeg_wrapper.py:108-109
  def start_audio_extraction(self, video_path, output_wav_path):
      """Asynchronously extracts 16 kHz mono WAV audio using QProcess."""
  ```
- Not reStructuredText/Google format; no `:param:` blocks. Preserve existing docstrings when editing (required by `AGENTS.md`).

## Function Design

**Size:** No enforced limit. Large files exist (`lecturepack/ui/main_window.py` ~1108 lines, `lecturepack/infrastructure/cv_engine.py` ~850). New code should follow the newer-module norm: short functions with a single responsibility (see `lecturepack/services/groq_transcription.py`).

**Parameters:**
- Plain positional/keyword args with sensible defaults; optional collaborators are injected as constructor args (`config_manager=None`, `log_callback=None`, `secret_store=None`, `client_factory=None`) — this is the primary seam for test doubles (`lecturepack/services/transcription_backends.py:351-360`).
- Boolean feature gates come from config keys with defaults: `config_manager.get("parallel_pipeline", True)` (`lecturepack/controllers/job_controller.py:144-148`).

**Return Values:**
- Status-reporting methods return dicts, not tuples or exceptions: `terminate_qprocess_tree()` returns `{"root_pid", "strategy", "taskkill_returncode", "finished"}` (`lecturepack/infrastructure/process_tree.py:11-48`); `OllamaClient.is_available()` returns `{"available", "version?"/"error", "kind"}`.
- Cross-thread results are frozen dataclasses: `TranscriptionResult(success, backend_key, ..., error_code, retryable)` (`lecturepack/services/transcription_backends.py:83-97`).
- Path lookups return `""` (empty string) for not-found, not `None`: `ConfigManager._find_bundled_binary()` (`lecturepack/infrastructure/config_manager.py:100-110`).

## Module Design

**Exports:**
- Direct class/function imports; no `__all__`, no star imports.
- Shared fixtures/helpers are imported across test modules: `from tests.test_ui_v11 import _make_job` (`tests/test_study_workspace_v12.py:17`).

**Barrel Files:** Not used. Package `__init__.py` files are empty or near-empty (`lecturepack/__init__.py` is 2 lines with `__version__`; `lecturepack/ui/pages/__init__.py` is empty).

**Layering (enforced — see `AGENTS.md` "Stack and Architecture"):**
- `lecturepack/infrastructure/` — OS/process/external-tool adapters (Qt allowed; no job/business logic)
- `lecturepack/services/` — pure logic; Qt only where signals are the contract (`transcription_backends.py`); several modules are deliberately stdlib-only and Qt-free for testability (`ollama_client.py:7-9`, `groq_transcription.py`, `transcript_store.py`, `transcript_formats.py`)
- `lecturepack/controllers/` — orchestration (`JobController`)
- `lecturepack/ui/` — widgets/pages; business logic stays in services (`transcript_store` docstring: "pure functions over plain segment dicts ... unit-testable without Qt", `lecturepack/services/transcript_store.py:19-25`)
- **Source-derived content (raw transcripts, slide images) and AI-generated content must remain strictly separated** (`AGENTS.md`). Concretely: `raw.json` is immutable; edits live in `working.json`/`edited.json` layers.

## Qt-Specific Conventions

**Threading & workers:**
- CPU/process-bound work runs in `QThread` subclasses (`SlideDetectorWorker`, `AlignWorker`, `ExportWorker`, `_GroqWorker`) or a `QObject` with an explicit start method (`AiRepairWorker`, `lecturepack/services/ai_repair_service.py:67`). Never block the GUI thread.
- Cancellation is cooperative: a checked flag (`self._is_cancelled`, `lecturepack/infrastructure/cv_engine.py:66-71`) or the shared `CancellationToken` wrapping `threading.Event` (`lecturepack/services/transcription_backends.py:53-63`).
- Worker lifetime is managed explicitly to avoid "QThread: Destroyed while thread is still running": superseded workers are parked in `self._retired_workers` (`lecturepack/controllers/job_controller.py:93-95`), and closing panels hand workers to the module-level `_DETACHED_WORKERS` set (`lecturepack/services/ai_repair_service.py:38-41`).

**Styling (QSS):**
- All styling is centralized in `lecturepack/ui/theme.py`: Fusion style + explicit `QPalette` + one QSS string. Do not call `setStyleSheet` on individual widgets.
- Widgets opt into styles via **dynamic properties** matched in QSS:
  ```
  QToolButton[navButton="true"]:checked { ... }
  QPushButton[primary="true"] { ... }
  QFrame[card="true"] { ... }
  QLabel[chip="ok"|"warn"|"err"] { ... }
  QLabel[h1|h2|muted="true"] { ... }
  ```
  (`lecturepack/ui/theme.py:103-162`)
- Theme constants (`ACCENT`, `DANGER`, `SELECTION_OUTLINE_WIDTH`) are the single source of truth shared with tests, which assert on them directly (`lecturepack/ui/theme.py:18-28`, consumed by `tests/test_ui_v11.py:80-96`).
- Dark mode is a `QApplication` property: `app.setProperty("lp_dark_theme", dark)` read via `theme.is_dark()` (`lecturepack/ui/theme.py:165-174`).
- UI state (splitters, geometry, last page, list/grid mode) persists via `QSettings` (`lecturepack/ui/main_window.py` header docstring lines 18-22).

**Subprocess invocation safety (absolute rules from `AGENTS.md`):**
- Never `shell=True`; always arg lists.
- `creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0` on sync runs (`lecturepack/infrastructure/ffmpeg_wrapper.py:73`).
- Long-running externals go through `QProcess` (`FFmpegWrapper.start_audio_extraction`, `WhisperWrapper.start_transcription`).
- Process trees are killed only by exact owned PID: `taskkill /PID <pid> /T /F`, never by image name (`lecturepack/infrastructure/process_tree.py:11-48`).
- `.py` paths are executed via `sys.executable` — this is the seam that lets tests substitute mock shim executables (`lecturepack/infrastructure/ffmpeg_wrapper.py:67-70`, `lecturepack/infrastructure/whisper_wrapper.py:146-152`). Preserve this branch in any new wrapper.
- Never modify or delete an original lecture video; rejects/deletions are decision flags in JSON, never filesystem deletes (verified by `tests/test_packaging_and_safety.py:52-68`).

**Secrets:**
- Provider keys live only in Windows Credential Manager via `WindowsCredentialStore` (`lecturepack/infrastructure/secret_store.py`); they never pass through `ConfigManager` or job JSON, and plaintext buffers are zeroed after use (`secret_store.py:72-74`).

---

*Convention analysis: 2026-07-17*
