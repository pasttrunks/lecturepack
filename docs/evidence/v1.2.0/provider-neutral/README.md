# Provider-neutral transcription checkpoint evidence

Phase: `refactor: provider-neutral transcription backends`

Date: 2026-07-16
Starting commit: `7a7f000`

No Groq/Gemini adapter, HTTP client, API key, credential store, upload path, or
network mode is enabled in this checkpoint. The registry exposes only
`local-whispercpp`, whose capabilities state `is_local: true`,
`uploads_audio: false`, and `requires_secret: false`.

## Verified contracts

- capabilities serialize to JSON-safe data
- unknown provider selection fails closed to Private Local
- local wrapper arguments, progress, runtime backend, results, and cancel are
  preserved through the adapter
- failures use structured, path-redacted result data
- `JobController` accepts an injected provider without provider-specific code
- cooperative cancellation reaches both the backend and cancellation token
- CPU is recorded only after runtime output proves it loaded
- mock-QProcess pipeline writes the same canonical seven-segment raw JSON
- old job settings remain unchanged and implicitly resolve to local
- implicit/explicit local stage fingerprints match
- unavailable-provider fallback and later provider availability have distinct
  fingerprints
- state stores requested/effective provider and engine separately

## Test results

- Focused contract/scheduler/stability run: `29 passed in 68.43s`
- Full suite: `136 passed in 143.62s`

Exact output is in `focused_pytest_output.txt` and `full_pytest_output.txt`.
`results.json` is the machine-readable contract summary.

## Privacy/source safety

The new service contains no HTTP/URL client or secret value. No API key field
is written to job state/config. The canonical local raw transcript remains the
source of truth and the existing raw/normalized/working separation is
unchanged.
