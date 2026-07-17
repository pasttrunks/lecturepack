# LecturePack v1.2 Groq online transcription handoff

## Phase boundary

- Authorized phase: `feat: Groq online transcription`
- Starting commit: `cef5771d65b682d38f24bf08a8425a213e2ec120`
- Ending implementation checkpoint: `a98969a402d9d24efbaad401ffca0396f77d45d7`
- Branch: `v1.2-hybrid-study`
- Non-goals honored: no Gemini, enrichment generation, VAD/detector tuning,
  packaging, release, tag, push, publish, or paid provider transcription.

## Changed files

- `lecturepack/services/groq_transcription.py` (new)
- `lecturepack/infrastructure/secret_store.py` (new)
- `lecturepack/services/transcription_backends.py`
- `lecturepack/controllers/job_controller.py`
- `lecturepack/infrastructure/process_tree.py`
- `lecturepack/infrastructure/config_manager.py`
- `lecturepack/constants.py`
- `lecturepack/ui/main_window.py`
- `lecturepack/ui/pages/process_page.py`
- `lecturepack/ui/pages/settings_page.py`
- `tests/test_groq_transcription.py` (new)
- `tests/test_transcription_backend_contract.py`
- `tests/test_stability_phase.py`
- `tests/fixtures/process_tree_parent.py`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md` (AD-13)
- `docs/evidence/v1.2.0/groq/README.md`
- `docs/evidence/v1.2.0/groq/online-fast-process.png`
- `docs/evidence/v1.2.0/groq/credential-manager-settings.png`

## Bugs and risks reproduced

- Online selection did not exist above the provider-neutral seam.
- There was no current-limit-aware audio chunking, provider retry, resume cache,
  overlap merge, or typed quota/network failure behavior.
- No privacy acknowledgement guarded credential read/upload.
- No Windows-native key Set/Test/Remove/status workflow existed.
- A provider failure could not retry only transcription through Private Local.
- Writing local fallback directly to canonical `raw.*` could endanger a valid
  transcript if fallback also failed; the final implementation uses a pending
  prefix and promotes complete output only.
- Sustained full-suite load exposed a pre-existing Windows race where the real
  process-tree test observed a newly created PID path before readable numeric
  content. The fixture now uses flush, `fsync`, atomic replace, and a bounded
  readable-content wait.

## Fixes implemented

- Added opt-in Online Fast (`whisper-large-v3-turbo`) and Online Accurate
  (`whisper-large-v3`) backends; Private Local remains the new/old-job default.
- Added conservative 23 MiB size-aware overlapping FLAC chunks, configurable
  concurrency, timestamp offsets, chronological merge, overlap de-duplication,
  and input-fingerprinted per-chunk response resume.
- Added bounded retries, exponential backoff, `retry-after`, 429/quota/network
  classification, secret redaction, and cooperative cancellation.
- Added Windows Credential Manager storage without a config/job/environment
  plaintext fallback and native Set/Test/Remove/status actions.
- Added a per-job audio-only consent gate that runs before secret access. No
  video, slide, transcript, job metadata, or glossary prompt is uploaded.
- Added online-to-local branch fallback that preserves slide detection,
  records sanitized online failure, and promotes local pending artifacts only
  after JSON/SRT/TXT all exist.
- Persisted/displayed the requested/effective/provider/runtime backend and
  online metrics through existing job state and Study/status surfaces.
- Added exact-PID cleanup for FFmpeg `Popen` trees; no name-based termination.

## Before/after evidence

- Before: only Private Local appeared and the neutral registry intentionally
  had no network adapter.
- After: native Process page exposes Online Fast/Accurate, concurrency,
  fallback, audio-only notice, and correct selected-backend status.
- After: native Settings exposes Credential Manager Set/Test/Remove/status and
  renders no secret value.
- Screenshots, official source review, reproduction steps, security evidence,
  and machine-readable result excerpts are in
  `docs/evidence/v1.2.0/groq/`.

## Verification

Focused command:

`python -m pytest tests/test_groq_transcription.py tests/test_transcription_backend_contract.py -q -s`

Focused result: `21 passed in 12.30s`.

Full command:

`python -m pytest`

Full result: `148 passed in 149.47s (0:02:29)`.

The first full attempts exposed the PID-file publication/read race described
above. That test reliability defect was fixed rather than hidden or weakened;
the final full run is completely green.

## Process cleanup and close latency

- Owned encoder tree: root PID `4392`, child PID `21784`, strategy
  `taskkill-pid-tree`, `finished=true`.
- Separately launched unrelated Python process survived the cleanup.
- Active mocked-provider application close:
  `groq_active_app_close_seconds=0.010779`.
- Cooperative backend cancellation completed inside the bounded native close
  path; no `QThread` was destroyed while running in the final suite.

## Settings, backend, and secret results

- Old jobs with no backend field resolve to Private Local unchanged.
- New UI defaults to Private Local; online is an explicit per-job selection.
- Requested Groq backend, effective backend, provider, metrics, online failure,
  and ultimately loaded backend persist in stage state and display on restart.
- A transient dummy Windows credential round-tripped, was removed in `finally`,
  and was confirmed absent afterward.
- Runtime config/job/cache scans found no dummy key; source/docs scans found no
  real-key pattern. No real credential was read or used.

## Resume and canonical-output proof

- A 22-second source under the test upload ceiling produced multiple ordered
  chunks; a second identical run made zero additional HTTP uploads and reported
  every chunk resumed.
- Mock responses were offset into global time, chronologically sorted, and
  overlap-de-duplicated before canonical raw JSON/SRT/TXT publication.
- Provider failure left an existing `raw.json` byte-identical. A simulated
  partial local fallback was removed from the exact pending prefix and the
  canonical transcript remained byte-identical.
- The stability re-export proof remains green: audio, raw transcript,
  candidates metadata, and candidate-frame hashes/sizes/mtimes did not change.

## Known limitations

- No paid Groq transcription was sent. API compatibility is proven with the
  current official contract and localhost mock server; real-account quota,
  billing, and network behavior remain for packaged acceptance when the user
  chooses to provide/use a key.
- Provider prices and limits are mutable. LecturePack uses a conservative
  free-tier-compatible ceiling and warns rather than promising free usage.
- Glossary prompting is deliberately disabled online to uphold the strict
  audio-only upload statement; it remains available to Private Local fallback.
- The pre-existing broad `.gitignore` `models/` rule still ignores
  `lecturepack/models/job.py`; packaging audit remains responsible for that
  repository-layout issue.

## Final Git status

The implementation checkpoint was clean at `a98969a`. This handoff is a
documentation-only follow-up; no implementation changed after the final full
test gate.
