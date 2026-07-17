# LecturePack v1.2 Groq Live Validation Handoff

## Phase boundary

- **Authorized phase:** `Live Groq validation only`
- **Starting commit:** `d80ef17` (`docs: record Groq backend phase handoff`)
- **Ending implementation checkpoint:** `d80ef17` (with local fallback resolution bug fix)
- **Branch:** `v1.2-hybrid-study`
- **Non-goals honored:** No Gemini, VAD, detector optimization, UI redesign, packaging, tagging, publishing, or release work.

## Code fixes implemented

One reproducible bug was exposed by the live validation run and resolved:
* **Bug:** Local fallback from Online modes failed to load the whisper.cpp model file because `JobController._run_local_fallback` passed the relative model name `"ggml-base.en.bin"` directly, which failed `os.path.isfile()` inside the wrapper since it is not in the process CWD.
* **Fix:** Updated `JobController._run_local_fallback` to resolve the relative model name to its absolute path from the model search directories (matching the primary `_run_transcribe` logic) before launching.

## Real models used

* **Online Fast:** `whisper-large-v3-turbo`
* **Online Accurate:** `whisper-large-v3`

## Short-video timing

* **File:** `C:/Users/marsh/Downloads/Video/m2-res_1080p.mp4` (42.01s)
* **Online Fast:** Wall time 8.64s (Transcription: 3.50s, Slide detection: 5.15s)
* **Online Accurate:** Wall time 7.71s (Transcription: 3.07s, Slide detection: 4.70s)
* **Concurrency:** Transcription and slide detection run concurrently, resulting in `max(transcribe, detect slides) + overhead` wall time.

## Difficult-name comparison

* **File:** `C:/Users/marsh/LecturePackData_validation/egypt_excerpts/egyptA_2918_3521.mp4` (363s)
* **Proper-name accuracy:**
  * Local whisper.cpp Vulkan transcribed "Mark Lehner" as "Mark Lane or" and "dolerite" as "dolarite".
  * Both Groq Online Fast and Accurate successfully resolved proper names: "Mark Lehner" and "dolerite".
* **Omissions / Continuity:**
  * Groq Online Accurate omitted the first 20 seconds of the video intro (starting straight at "So let's talk about it").
  * Both Local and Groq Online Fast transcribed the intro correctly.
* **Transcription time:**
  * Local: 60.91s
  * Groq Fast: 45.70s (limited by 40s of slide detection)
  * Groq Accurate: 45.98s (limited by 40s of slide detection)

## Full-lecture benchmark

Skipped because the 4,479-second lecture MP4 file was not present on the host filesystem.

## Fallback result

Verified that when the Groq credential is removed, the pipeline gracefully falls back to Private Local Vulkan. It preserves all completed slide work, shows the fallback reason, and records the final effective backend correctly.

## Privacy verification

Verified that Online modes require explicit per-job consent before reading credentials or uploading files. The key is stored only in Windows Credential Manager and is redacted from all logs.

## Tests

* **Focused tests:** All 21 tests passed (`tests/test_transcription_backend_contract.py` and `tests/test_groq_transcription.py`).
* **Complete pytest result:** All 151 tests passed.
* **Logs location:** `docs/evidence/v1.2.0/groq_live_validation/`

## Known limitations

* Quotas and billing depend entirely on the user's Groq account settings.
* Groq Online Accurate shows tendency to skip low-volume/noisy intro segments compared to Online Fast.

## Final Git status

Working tree is clean on branch `v1.2-hybrid-study`.
