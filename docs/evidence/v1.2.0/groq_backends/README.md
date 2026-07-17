# Groq Online and Provider-Neutral Backend Verification Evidence

Verification date: 2026-07-17. The provider-neutral seam and Groq online transcription backends were verified through mock-server integration tests and full test suite execution under Windows.

## Official API assumptions and verification date

* **Endpoint:** `https://api.groq.com/openai/v1/audio/transcriptions` (Verified as of 2026-07-17).
* **Models:** `whisper-large-v3-turbo` (Online Fast, 824M parameters) and `whisper-large-v3` (Online Accurate, 1550M parameters).
* **Upload Limits:** 25 MB size limit for free-tier uploads. LecturePack uses a conservative 23 MiB chunk size ceiling and prepares compressed FLAC audio locally to reduce payload size.
* **Timestamps:** Verbose JSON format is requested to obtain segment and word-level timestamps.

## Backend architecture description

A provider-neutral `TranscriptionBackend` interface defines capabilities, validation, and execution. The system registers three concrete backends:
1. `LocalWhisperCpuBackend`: Local whisper.cpp execution with AVX2 CPU instruction sets.
2. `LocalWhisperVulkanBackend`: Local whisper.cpp execution with Vulkan GPU acceleration.
3. `GroqWhisperBackend`: Online HTTP-based transcription with size-aware overlapping chunks, rate-limit backoff, and local fallback.

## Fake-server failure tests

Mock integration tests verify robust error recovery:
* Rate-limiting (HTTP 429) backoff obeys the `Retry-After` header.
* Quota-exhausted and connection-refused errors initiate automatic local fallback.
* Malformed responses trigger local fallback without destroying existing raw transcripts.

## Focused pytest output

* Focused tests passed: 21 tests in `tests/test_groq_transcription.py` and `tests/test_transcription_backend_contract.py`.
* Log file: [focused_pytest_output.txt](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_backends/focused_pytest_output.txt)

## Complete pytest output

* Full suite passed: 151 tests.
* Log file: [full_pytest_output.txt](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_backends/full_pytest_output.txt)

## Real-video validation blockers (Outcome B)

Real validation with a live API key was blocked because no Groq API key is present in the Windows Credential Store on the host system. The implementation has been validated using the localhost mock server.

## Privacy and secret-storage verification

* **Secret storage:** Stored securely in Windows Credential Manager under target `LecturePack/Groq API Key`.
* **Redaction:** Log manager scans and redacts authorization headers, request bodies, and keys.
* **Opt-inUX:** Online mode is disabled by default and requires explicit per-job consent.

## Fallback result

Provider errors successfully fall back to `Private Local`. Slide detection results are preserved, and canonical raw outputs are promoted only after validation.

## Process cleanup result

Process trees launched during transcription are terminated using taskkill PID-tree matching to ensure no orphaned processes remain.

## Screenshots

* [online-fast-process.png](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_backends/online-fast-process.png)
* [credential-manager-settings.png](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_backends/credential-manager-settings.png)
