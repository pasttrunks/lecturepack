# Groq Live Validation Evidence

Verification date: 2026-07-17. Real live validation with the Groq API key configured in Windows Credential Manager has been completed successfully.

## Connection-test result

The connection test from the settings page succeeds:
* Action: Test key
* Status: `Testing Groq credentials...` followed by `Groq credential test passed. Account limits and billing still apply.`
* Logs show the authentication headers and keys are correctly redacted, using `Bearer [redacted]`.

## Short video results

* **File:** `C:/Users/marsh/Downloads/Video/m2-res_1080p.mp4` (42.01s)
* **Online Fast (`whisper-large-v3-turbo`):**
  * Wall time: 8.64s (Transcription: 3.50s, Slide detection: 5.15s)
  * Word count: 37 words
  * Accuracy: Excellent transcription with correct spelling and zero hallucinations.
* **Online Accurate (`whisper-large-v3`):**
  * Wall time: 7.71s (Transcription: 3.07s, Slide detection: 4.70s)
  * Word count: 33 words
  * Accuracy: Similar quality to Fast.

## Difficult-name comparison

* **File:** `C:/Users/marsh/LecturePackData_validation/egypt_excerpts/egyptA_2918_3521.mp4` (363s)
* **Comparison results:**
  * **Private Local (`Vulkan`):** 60.91s total, 1153 words. Transcribed "Mark Lehner" as "Mark Lane or", and "dolerite" as "dolarite" and "dola right".
  * **Online Fast (`whisper-large-v3-turbo`):** 45.70s total, 1162 words. Correctly transcribed proper names: "Mark Lehner" and "dolerite".
  * **Online Accurate (`whisper-large-v3`):** 45.98s total, 1065 words. Correctly transcribed proper names, but omitted the first 20 seconds of the video intro.

## Fallback result

With the Groq API key temporarily removed, starting Online Fast successfully falls back to Private Local Vulkan:
* State: Resolves status to `completed` using backend `local-whispercpp`.
* Preservation: Slide detection is preserved.
* Output: No partial or duplicate segments.

## Full-lecture benchmark

Skipped because the 4,479-second lecture MP4 file was not present on the host filesystem.

## Privacy verification

Online mode requires explicit opt-in. A per-job confirmation dialog asks:
`Do you consent to this audio upload for this job?`
No request is made to Groq before consent. Keys are never saved to job manifests, configs, or logs.

## Process-cleanup verification

All background FFmpeg process trees are terminated immediately on job cancellation or application close, leaving no orphaned helper processes.

## Screenshots

* [online-fast-process.png](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_live_validation/online-fast-process.png)
* [credential-manager-settings.png](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_live_validation/credential-manager-settings.png)

## Timing JSON

* [results.json](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_live_validation/results.json)

## Pytest outputs

* [focused_pytest_output.txt](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_live_validation/focused_pytest_output.txt)
* [full_pytest_output.txt](file:///c:/Users/marsh/Documents/LecturePack/docs/evidence/v1.2.0/groq_live_validation/full_pytest_output.txt)
