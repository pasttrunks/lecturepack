# Groq online transcription evidence

Evidence date: 2026-07-16. No paid transcription request was made. Provider
behavior was exercised against a localhost Groq-compatible HTTP server; the
native Set/Test/Remove UI was captured without displaying a key.

## Official contract revalidation

- [Speech to Text](https://console.groq.com/docs/speech-to-text): the current
  transcription endpoint is `/openai/v1/audio/transcriptions`; the approved
  models are `whisper-large-v3-turbo` and `whisper-large-v3`; direct uploads are
  documented as 25 MB for free tier and 100 MB for developer tier; FLAC is the
  recommended lossless size reduction; long audio should use overlapping
  chunks; `verbose_json` supports segment and word timestamps.
- [Rate limits](https://console.groq.com/docs/rate-limits): limits are
  organization/account-specific, 429 indicates rate limiting, and
  `retry-after` is provided on 429.
- [API errors](https://console.groq.com/docs/errors): 413, 429, 498, 499, and
  server errors were reviewed for typed failure and retry behavior.
- Official model pages report current per-audio-hour prices of $0.04 for Turbo
  and $0.111 for Large V3. LecturePack does not promise free usage and shows an
  account-limit/billing warning before consent.

## Reproduction and visible native UI

1. Launch `python app.py` from PowerShell.
2. Open Process and select `Online Fast (Groq)` or
   `Online Accurate (Groq)` under Processing.
3. Confirm local engine/VAD controls disable, online concurrency and local
   fallback appear, and the status bar names the selected online backend.
4. Open Settings. Confirm Groq shows Set API key, Test key, Remove key, and a
   status only; no key text field/value is rendered.
5. Start an online job. Without a stored key it stops before processing. With
   a stored key, the per-job audio-only notice must be accepted before the
   backend can read the secret or issue an HTTP request.

Screenshots:

- `online-fast-process.png` — native PySide6 Process page with Online Fast,
  concurrency, fallback, and audio-only notice.
- `credential-manager-settings.png` — native PySide6 Settings page with the
  Credential Manager actions and status-only display.

## Focused verification

Command:

`python -m pytest tests/test_groq_transcription.py tests/test_transcription_backend_contract.py -q -s`

Result: `21 passed in 12.30s`.

Full command: `python -m pytest`

Full result: `148 passed in 149.47s (0:02:29)`.

The suite proves:

- size-aware ordered chunks with overlap;
- global timestamp offsets and chronological ordering;
- overlap word de-duplication;
- multipart requests contain prepared audio and no slide/transcript/glossary;
- `retry-after` and 429 retry;
- provider error secret redaction;
- privacy failure occurs before credential access;
- completed chunk responses resume without a second upload;
- cancellation and active-application close are non-blocking;
- online failure starts local fallback without stopping the slide branch or
  overwriting an existing raw transcript;
- old/implicit jobs still resolve Private Local.

Measured active mocked-provider application close:
`groq_active_app_close_seconds=0.010779`.

## Process-tree and secret evidence

The real Windows cleanup test launched a LecturePack-owned parent plus child
and a separate unrelated Python process. Result:

`{"child_pid":21784,"finished":true,"root_pid":4392,"strategy":"taskkill-pid-tree","unrelated_survived":true}`

A transient dummy credential was written to a unique test target, read back,
removed in `finally`, and checked absent afterward:

`{"present_after_remove":false,"present_before_remove":true,"removed":true,"roundtrip":true,"target_prefix":"LecturePack/Codex Verification/"}`

No real Groq key was read, logged, screenshotted, committed, or used for a paid
request. Runtime config/job/cache scans in the focused tests confirm the dummy
key is absent from persisted JSON.

During the full-suite gate, sustained Windows/antivirus load exposed a race in
the real process-tree fixture: tests observed the PID path before its content
was readable. The fixture now publishes the PID with flush, `fsync`, and atomic
replace, and the assertions wait for readable numeric content. The final full
run passed all 148 tests.
