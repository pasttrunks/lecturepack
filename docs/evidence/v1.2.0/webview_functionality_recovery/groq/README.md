# §6 Groq online transcription (WebView integration)

The Groq BACKEND already existed from prior work and is sound (contract tests pass:
`tests/test_groq_transcription.py` — 12): `WindowsCredentialStore` (OS Credential
Manager), `_GroqWorker` (audio-only chunked upload, per-job privacy consent,
retries/Retry-After, 429/quota handling, cancellation, local fallback), and the
"Online Fast (Groq)" / "Online Accurate (Groq)" backends selected via
`job.settings["whisper"]["transcription_backend"]`. §6 exposes that in the new
WebView UI.

## Added (WebView)
- Settings "Transcription" card: mode selector **Private Local / Online Fast /
  Online Accurate** (persists `transcription_backend` in config, applied to the
  job at `start_processing`), plus **Set / Test / Remove** Groq key controls and a
  status line.
- Adapter: `set_groq_key` / `remove_groq_key` (via `WindowsCredentialStore`),
  `test_groq_key` (threaded, via `GroqHttpClient.test_key`), `_emit_groq_status`
  (has-key + selected backend); `on_setting_changed('transcription_backend')`;
  `start_processing` applies the backend; `on_ui_ready` emits status.
- Bridge: `groq_status` signal + `set_groq_key`/`remove_groq_key`/`test_groq_key`
  slots. The user types their own key; it is stored only in the OS Credential
  Manager (never in config/logs/Git).

## Tests
`tests/test_webview_groq.py` (6, store + Groq client monkeypatched → no real
credential-manager writes, no network): set/remove, empty-key error, status
reflection, backend-mode persistence + invalid→local fallback, test-key no-key
path, test-key pass path.

## Live validation — BLOCKED (no API key here) → Outcome C
Online Fast/Accurate can be exercised end-to-end only with a real Groq key. Steps:
1. Settings → Transcription → paste a `gsk_…` key → Set → Test (expect "passed").
2. Pick Online Fast (or Accurate), process a lecture, accept the per-job privacy
   consent; the footer/manifest should show the Groq provider/model.
3. Compare wall time vs Private Local on the same media (record in
   `performance/final.json`). Not fabricated here.
