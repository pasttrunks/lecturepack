# Privacy & Data Storage

Lecture Pack is a **local-first** desktop application. It does not require an
account, does not phone home, and does not upload your video, audio, or
transcript anywhere.

## Where data lives

All job data is stored under your user profile:

```
%USERPROFILE%\LecturePackData\
  config.json                 app configuration (binary/model paths, data dir)
  jobs\<job-id>\
    manifest.json             source path, title, app version
    settings.json             preset, product mode, whisper + Context & Names
    state.json                per-stage status
    candidates.json           detected slide candidates + your keep/reject decisions
    audio\lecture-16khz-mono.wav
    candidates\slide_*.png     detected slide images
    transcript\
      raw.json / raw.srt / raw.txt      Layer 1 — immutable raw Whisper output
      normalized.json                   Layer 2 — deterministic normalization
      context_candidates.json           deterministic Context & Names proposals
      corrections.json                  Layer 3 — reversible correction set
      corrected.json                    user-approved corrected transcript
      edited.json                       inline transcript edits
    exports\                            generated study pack / transcripts
```

Your job data is yours. The app never deletes another job's data, and re-export
never deletes candidate images.

## Network access

- **Transcription and slide detection are entirely offline** (bundled FFmpeg and
  whisper.cpp; no network).
- **Context Repair (Layer 3)** is optional and, by default, uses a
  **deterministic offline** proposal source (approved-name matching) — no network.
- If you explicitly configure a local LLM endpoint (LM Studio / Ollama), Context
  Repair will POST transcript segments to **that endpoint only**. Nothing is sent
  to any third-party cloud service. Point it at `http://localhost:...` to keep
  everything on your machine.

## What is never sent anywhere

Your video, extracted audio, raw transcript, slide images, and corrections stay
on disk under `LecturePackData`. Removing a job is a manual action you take in
your file manager; the app does not perform destructive cleanup of your data.

## Telemetry

None. There is no analytics, crash reporting, or usage tracking.
