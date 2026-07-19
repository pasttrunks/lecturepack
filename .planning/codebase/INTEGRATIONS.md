# External Integrations

**Analysis Date:** 2026-07-17

LecturePack is local-first: no account, no telemetry, no analytics, no advertising (`AGENTS.md` Safety; `README.md` Privacy). The only network egress in shipped code is (a) an opt-in Groq transcription call and (b) localhost calls to a user-installed Ollama server. Whisper model downloads are manual first-run steps, not in-app network calls.

## APIs & External Services

**Speech-to-text (online, opt-in):**
- **Groq Cloud — Whisper speech-to-text** — optional online transcription provider ("Online Fast" / "Online Accurate" backend keys `groq-fast` / `groq-accurate` in `lecturepack/constants.py`).
  - Endpoint: `https://api.groq.com/openai/v1/audio/transcriptions` (`GROQ_TRANSCRIPTIONS_URL`, `lecturepack/services/groq_transcription.py:28`)
  - Models: `whisper-large-v3-turbo` (`GROQ_FAST_MODEL`) and `whisper-large-v3` (`GROQ_ACCURATE_MODEL`)
  - SDK/Client: none — standard-library multipart client (`urllib.request`) in `lecturepack/services/groq_transcription.py` (`GroqHttpClient`); AD-13 in `docs/DECISIONS.md` records rejecting the Groq SDK.
  - Auth: `Authorization: Bearer <key>` read on demand from Windows Credential Manager (target `"LecturePack/Groq API Key"` — see Authentication & Identity below).
  - Upload policy: lossless FLAC chunks of the existing 16 kHz mono WAV only; 23 MiB ceiling (`DEFAULT_MAX_UPLOAD_BYTES`) under Groq's 25 MB free-tier limit; 5 s overlap, ≤600 s chunks (`plan_audio_chunks`). Glossary text, video, slides, transcript artifacts, and job metadata are never sent (`docs/ARCHITECTURE.md` v1.2 §Groq).
  - Resilience: bounded retries honoring `retry-after` (`parse_retry_after`), per-chunk resumable cache at `transcript/groq-cache/<fingerprint>/responses/`, timestamp offsetting + overlap de-dup, canonical `raw.json/srt/txt` published only after full ordered merge; eligible failures trigger one Private Local fallback (`online_fallback_local` config default True).
  - Consent gate: per-job `online_privacy_accepted` setting must be true before the credential is read.
  - Backend seam: `GroqTranscriptionBackend` registered beside `LocalWhisperCppBackend` via `BackendRegistry` in `lecturepack/services/transcription_backends.py` (AD-12); capability record marks local backend as no-secret/no-upload and Groq as secret-required/uploading.

**LLM (local, optional):**
- **Ollama (localhost)** — powers Context Repair proposals and AI section headings.
  - Default base URL `http://localhost:11434` (`DEFAULT_BASE_URL`, `lecturepack/infrastructure/ollama_client.py:33`); user-configurable in Settings (`lecturepack/ui/pages/settings_page.py`).
  - SDK/Client: none — stdlib `urllib` streaming NDJSON chat client with JSON-schema constrained output (`format`), `think: false`, `keep_alive`, finite connect (4 s) / generation (180 s) / stream-stall (60 s) timeouts, cooperative `cancel_event` (`OllamaClient`). Verified against Ollama v0.32 API per module docstring.
  - Adapter: `OllamaRepairProvider` feeds the guardrailed `ContextRepairEngine` (`lecturepack/services/transcript_service.py`); worker wrapper `AiRepairWorker` QThread with absolute exception boundary + per-job disk cache (`lecturepack/services/ai_repair_service.py`).
  - Recommended model: `qwen3:1.7b` (`README.md`). Without Ollama, a deterministic approved-name provider runs offline and cannot invent names.
  - Docs mention "LM Studio / Ollama, OpenAI-compatible" (`README.md` line 46; `docs/ARCHITECTURE.md` lists LM Studio `localhost:1234` as an optional external), but the shipped client targets the Ollama native API (`/api/chat`); any compatible endpoint is reachable only by changing `base_url`.

**External CLI processes (bundled, no network):**
- **FFmpeg / FFprobe** — `bin/ffmpeg.exe`, `bin/ffprobe.exe`; driven via `QProcess`/`subprocess` in `lecturepack/infrastructure/ffmpeg_wrapper.py` (inspect → JSON, extract → 16 kHz mono WAV) and piped rawvideo decode in `lecturepack/infrastructure/video_reader.py`. Exact-PID FLAC encoding for Groq chunks in `groq_transcription.py`. Process-tree-scoped termination via `lecturepack/infrastructure/process_tree.py`.
- **whisper.cpp `whisper-cli.exe`** — CPU build `bin/Release/` and optional Vulkan build `bin/vulkan/`; QProcess wrapper `lecturepack/infrastructure/whisper_wrapper.py`; engine policy/registry `lecturepack/infrastructure/transcription_engines.py`; capability probe `lecturepack/infrastructure/whisper_detector.py`.

**Model distribution:**
- **HuggingFace `ggerganov/whisper.cpp`** — source for ggml Whisper models (`https://huggingface.co/ggerganov/whisper.cpp`; referenced in `transcription_engines.py:47` and `THIRD_PARTY_NOTICES.txt`). Download is a manual first-run step by the user; the app performs no automated model download and models are not bundled in the release ZIP.

## Data Storage

**Databases:**
- None. AD-3 (`docs/DECISIONS.md`): plain files + JSON manifests. Per-job state under `~/LecturePackData/jobs/<uuid>/` (`manifest.json`, `state.json`, `settings.json`, `stage_fingerprints.json`, `study.json`, transcript layers) with atomic writes (`.tmp` + `os.replace`) via `lecturepack/infrastructure/file_manager.py`.

**File Storage:**
- Local filesystem only. Data root `~/LecturePackData` (configurable; `DEFAULT_DATA_DIR` in `lecturepack/constants.py`; outside the repo — never touch from tooling).

**Caching:**
- No cache service. On-disk JSON caches only: Groq chunk responses (`transcript/groq-cache/`), Ollama response cache (`load_ai_cache`/`save_ai_cache` in `lecturepack/services/ai_repair_service.py`), stage-fingerprint recompute skip cache (`stage_fingerprints.json`).

## Authentication & Identity

**Auth Provider:**
- None for the application itself (no user accounts, no sign-in).

**Third-party credential storage:**
- **Windows Credential Manager** — sole secret store, via raw Win32 `ctypes` calls to `Advapi32.dll` (`CredWriteW`/`CredReadW`/`CredDeleteW`/`CredFree`) in `lecturepack/infrastructure/secret_store.py` (`WindowsCredentialStore`).
  - Credential target: `LecturePack/Groq API Key` (`GROQ_CREDENTIAL_TARGET`), generic credential, local-machine persistence.
  - No plaintext fallback; secrets never pass through `ConfigManager` or job JSON; provider error messages are redacted (`_safe_provider_message` strips the key and Bearer tokens).
  - Non-Windows platforms raise `SecretStoreError` — app is Windows-only.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/analytics; prohibited by `AGENTS.md`).

**Logs:**
- Per-job stage logs under `~/LecturePackData/jobs/<uuid>/logs/` — captured subprocess stdout/stderr streamed through Qt signals to the UI logs drawer (`docs/ARCHITECTURE.md` §3; `ffmpeg_wrapper.py`/`whisper_wrapper.py` `progress` signals).
- In-app Settings → Diagnostics page reports binary/model/data-dir validity (`ConfigManager.check_diagnostics`, `lecturepack/infrastructure/config_manager.py`).
- No Python `logging` module usage and no `app.log` writer found in `lecturepack/` source (the `docs/ARCHITECTURE.md` §10 `logs/app.log` line predates the as-built layout).

## CI/CD & Deployment

**Hosting:**
- Desktop portable app; no hosted service. Distribution = ZIP artifact `dist-release/LecturePack-portable-<version>.zip` produced by `build_release.py` (PyInstaller onedir + bundled binaries + `SHA256SUMS.txt` + `BUILD_MANIFEST.json`).

**CI Pipeline:**
- None. No `.github/`, no CI YAML in repo. Validation is local: `pytest` suite (`pytest.ini`), packaged self-test (`LecturePack.exe --selftest`), packaged acceptance driver (`--run-acceptance`, `lecturepack/acceptance.py`), with evidence archived under `docs/evidence/v*/`.

## Environment Configuration

**Required env vars:**
- None. No `.env` file exists or is read. `QT_QPA_PLATFORM=offscreen` is self-set by the headless self-test (`lecturepack/app.py:132`).

**Runtime configuration:**
- `~/LecturePackData/config.json` — app settings (binary paths, engine, Groq concurrency/upload cap, Ollama block, theme).
- `QSettings("LecturePack", "LecturePack")` — window geometry/splitters (`lecturepack/ui/main_window.py:128`).

**Secrets location:**
- Windows Credential Manager only (Groq key). Nothing secret in files, env, or registry.

## Webhooks & Callbacks

**Incoming:**
- None — the app opens no listening sockets.

**Outgoing:**
- None (no callback URLs, no telemetry beacons). The only outbound HTTP requests are the user-initiated Groq transcription POST and localhost Ollama requests described above.

---

*Integration audit: 2026-07-17*
