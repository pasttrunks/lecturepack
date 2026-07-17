# LecturePack v1.2 provider-neutral transcription handoff

## Phase boundary

- Authorized phase: `refactor: provider-neutral transcription backends`
- Starting commit: `7a7f000` (`docs: record v1.2 Study handoff`)
- Ending implementation checkpoint: `42782b4`
- Branch: `v1.2-hybrid-study`
- Non-goals honored: no Groq/Gemini HTTP, API keys, Credential Manager,
  enrichment, VAD/detector tuning, packaging, release, tag, push, or publish.

## Changed files

- `lecturepack/services/transcription_backends.py` (new)
- `lecturepack/controllers/job_controller.py`
- `lecturepack/infrastructure/whisper_wrapper.py`
- `lecturepack/constants.py`
- `tests/test_transcription_backend_contract.py` (new)
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md` (AD-12)
- `docs/evidence/v1.2.0/provider-neutral/`

## Implementation

- Added JSON-safe backend capabilities, immutable request/result objects,
  cooperative cancellation token, Qt-signal backend base, and registry.
- Wrapped the existing WhisperWrapper plus CPU/Vulkan EngineRegistry in the
  only registered backend, `local-whispercpp`.
- Routed controller start/progress/result/cancel through the provider contract
  while retaining the public wrapper for diagnostics and process cleanup.
- Separated requested provider, effective provider, selected compute engine,
  and runtime-proven loaded backend in job state.
- Kept implicit and explicit local cache fingerprints byte-identical to v1.1.
  Non-local requested/effective keys isolate fallback output and invalidate it
  when a missing provider later becomes available.
- Fixed CPU runtime detection for the existing `loaded CPU backend` log line.

## Verification

- Focused contract/scheduler/stability: `29 passed in 68.43s`.
- Full pytest: `136 passed in 143.62s`.
- Canonical local mock transcript retained seven ordered raw segments.
- Old job settings remained byte-identical and resolved implicitly to local.
- Registry contained only Private Local; no HTTP client, secret field, or
  upload path was enabled.
- Exact output and machine-readable results are under
  `docs/evidence/v1.2.0/provider-neutral/`.

## Known limitations

- This checkpoint defines the adapter seam only. No online backend exists yet.
- Local language remains carried in the neutral request but the wrapper keeps
  its pre-refactor argument behavior; provider-specific language handling is
  implemented by each adapter according to its supported API/CLI.
- The pre-existing broad `.gitignore` `models/` rule also ignores
  `lecturepack/models/job.py`. This phase deliberately avoided modifying that
  ignored source file; repository-layout correction remains a packaging audit
  item and is not needed for the neutral default.

## Final Git status

The implementation checkpoint was clean. This handoff and a Markdown
whitespace normalization are committed as a documentation-only follow-up so
the exact implementation hash remains reviewable.
