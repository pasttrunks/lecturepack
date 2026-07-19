# LecturePack v1.2 Groq Online Transcription Handoff

## Phase boundary

- **Authorized phase:** `Provider-neutral transcription backends + Groq Online Fast/Accurate`
- **Starting commit:** `8c13e7d` (`docs: record v1.2 Study handoff`)
- **Ending implementation checkpoint:** `ca62965` (`docs: record Groq transcription handoff`)
- **Branch:** `v1.2-hybrid-study`
- **Non-goals honored:** No Gemini/enrichment generation, VAD/detector tuning, packaging, release, tag, push, or publish.

## Changed files

- `lecturepack/constants.py`
- `lecturepack/controllers/job_controller.py`
- `lecturepack/infrastructure/whisper_wrapper.py`
- `lecturepack/services/transcription_backends.py` (new)
- `lecturepack/infrastructure/config_manager.py`
- `lecturepack/infrastructure/process_tree.py`
- `lecturepack/infrastructure/secret_store.py` (new)
- `lecturepack/services/groq_transcription.py` (new)
- `lecturepack/ui/main_window.py`
- `lecturepack/ui/pages/process_page.py`
- `lecturepack/ui/pages/settings_page.py`
- `tests/test_transcription_backend_contract.py` (new)
- `tests/test_groq_transcription.py` (new)
- `tests/fixtures/process_tree_parent.py`
- `tests/test_stability_phase.py`
- `docs/evidence/v1.2.0/groq_backends/`

## Backend architecture

The transcription pipeline uses a provider-neutral `TranscriptionBackend` interface, allowing unified control of local and online engines. Concrete implementations:
* `LocalWhisperCpuBackend`: Local whisper.cpp CPU.
* `LocalWhisperVulkanBackend`: Local whisper.cpp Vulkan.
* `GroqWhisperBackend`: Online Groq API.

Requested provider, selected compute engine, and loaded backend are stored separately in the job state to ensure clear provenance.

## Local backend regression result

No regression. All local CPU and Vulkan benchmarks remain fully functional, passing the existing and new local verification tests.

## Groq models actually tested

* **Online Fast:** `whisper-large-v3-turbo`
* **Online Accurate:** `whisper-large-v3`

## Current verified API limits

* **Upload size:** 25 MB. LecturePack chunks audio under a 23 MiB limit.
* **Format:** FLAC compression is used to minimize network payloads.

## Chunking and merging behavior

Audio is split into overlapping chunks, transcribed concurrently, adjusted for global offsets, sorted chronologically, and merged. Duplicated segments and words at boundary overlaps are filtered and de-duplicated.

## Fallback behavior

If connection fails, the API key is missing, or quota is exhausted, the pipeline falls back to `Private Local`. Fallback preserves slide detection, redacts secrets from error messages, and promotes canonical files only after complete validation.

## Privacy and secret-storage proof

* **Storage:** Windows Credential Manager under `LecturePack/Groq API Key`.
* **Privacy consent:** Online mode is disabled by default, and a per-job audio-only upload notice must be confirmed before secret read or upload occurs.
* **Redaction:** Scans automatically remove keys, headers, and secret URL components from logs.

## Focused tests

* **Command:** `.venv\Scripts\pytest tests/test_transcription_backend_contract.py tests/test_groq_transcription.py`
* **Result:** `21 passed in 13.67s`

## Complete pytest result

* **Command:** `.venv\Scripts\pytest`
* **Result:** `151 passed in 158.63s`

## Real validation results

* **Short video:** Blocked by lack of live API key.
* **Difficult-name comparison:** Blocked by lack of live API key.
* **Full-lecture benchmark:** Blocked by lack of live API key.

## Known limitations

No paid Groq transcription was performed during this run. Real-account quota limits, billing, and network connectivity depend on the user providing a valid key.

## Final Git status

Working tree is clean on branch `v1.2-hybrid-study`. All commits are committed, and HEAD is at commit `ca62965`.

## Exit outcome used

**Outcome B:** Architecture succeeds, real Groq validation is blocked by missing API key.
