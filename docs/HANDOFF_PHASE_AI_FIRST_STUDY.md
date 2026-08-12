# Handoff — AI-first Study production upgrade

**Date:** 2026-08-12
**Branch:** `codex/ai-first-study`
**Starting HEAD:** `3dc4febd67aee42c16a276b95a4d8e15ca655c67`
**Release status:** READY FOR USER TEST (gateway deployed and live packaged acceptance passed)

## Authorized phase and goal

Implement the first production-ready AI-first Study system for LecturePack: automatic grounded Study generation after lecture processing, six student-facing Study modes, anonymous server-controlled AI routing with independent fallback, safe failure recovery, provenance, mastery persistence, packaged-app acceptance, and release hardening.

The work remained within the AI-first Study/gateway, desktop bridge and UI, packaging/acceptance harness, tests, and required architecture/product/decision documentation. The completion session deployed the approved Cloudflare gateway but did not publish a desktop release, add desktop provider keys, change the lecture-processing stack, or modify original lecture videos.

## Completed

- Added and deployed a dependency-free Cloudflare Worker gateway with HMAC installation tokens, an eight-task allowlist, bounded request/response schemas, per-installation and network rate limits, content-free D1 operational telemetry, cooldown-bounded optional owner alerts, OpenRouter routing, and a native Workers AI fallback.
- Required every task to have at least two routes on independent endpoint hosts. Provider rejection, malformed responses, and transient failures advance to the next server-controlled route.
- Kept provider credentials, model names, and route selection out of the packaged desktop. Normal success responses expose no attempted routes; sanitized failure diagnostics retain only safe route descriptors and failure metadata.
- Added automatic two-pass Study generation with hierarchical analysis for long lectures, compact material generation, at most three selected vision calls and three web-enrichment calls, strict grounding/provenance, and verified web citation URLs.
- Added Study Guide, Flashcards, mixed Quiz, live short-answer grading, Ask, Teach Me, and Quick Study (5/10/20/full) to the six-mode Study workspace.
- Added manual mastery, progress persistence, concept-linked response caching, dependency-aware concept deletion, and transcript-triggered partial regeneration that preserves unaffected concepts and mastery.
- Added Retry, sanitized Copy Diagnostics, and deterministic Basic Study recovery. Malformed partial regeneration settles into an explicit failed state rather than remaining stuck in preparing.
- Updated Home and Settings privacy language to distinguish local lecture processing from gateway-assisted Study. Legacy provider/model/API-key controls remain hidden.
- Added a packaged acceptance harness that runs the actual frozen sidecar and bundled Polar Bears lecture against a deterministic loopback gateway. It checks the complete Study flow, failure recovery, payload privacy, clean exit, and orphan processes.
- Added a second packaged acceptance harness that runs the frozen sidecar and bundled Polar Bears lecture against the production HTTPS gateway with real providers and no gateway environment override.

## Verification evidence

- Gateway: `npm test` — **17 passed**.
- Focused gateway/contract Python: **18 passed**.
- Opt-in live-provider smoke: **1 passed** against the production Worker.
- Desktop JavaScript: `npm run validate` — **passed**.
- Rust Study Core: `cargo test -- --nocapture` — **11 passed, 0 failed**. Rust source was not changed in the final UI/harness correction.
- Full Python suite: **1,507 passed, 2 skipped, 6 failed** in 268.74 seconds. All AI-first Study tests passed. The six inherited/external-fixture failures are listed below.
- Windows package: `npm run package:win` — **passed**.
- Package: `C:\LecturePackScratch\builds\ai-study-production-20260812-r2\dist\LecturePack-win32-x64`
- Deterministic packaged Study report: `C:\LecturePackScratch\results\ai-study-production-r2-deterministic-20260812\ai-study-packaged-acceptance.json` — **passed**.
- Live packaged Study report: `C:\LecturePackScratch\results\ai-study-production-r2-live-20260812\ai-study-live-packaged-acceptance.json` — **passed**.
- Packaged acceptance had all checks true, including ready content, every Study interaction, lecture/web citations, selective vision, bounded web, mastery, retry, safe diagnostics, Basic fallback, payload privacy, clean exit, and zero orphan processes.
- Earlier six-mode visual QA found equal-width tabs, no horizontal overflow, complete failure/provenance/Teach UI, and no visible provider/model/API-key controls.

## Packaged quality observations

The deterministic acceptance fixture produced and persisted:

- “Polar bears are Arctic marine mammals whose physical adaptations and reliance on sea ice work together.”
- Concepts: “Transparent fur and black skin” and “Sea-ice hunting ecology.”
- Flashcards: “Is polar-bear fur actually white?” and “Why are polar bears classed as marine mammals?”

The live packaged provider run produced three grounded concepts, two guide
sections, two flashcards, and three mixed quiz items. Its summary was: “The
lecture explains that polar bear fur is not white but transparent, with black
skin underneath, and that polar bears are marine mammals.” Ask, Teach Me, and
semantic short-answer grading also passed against the persisted live content.

## Known failures and limitations

The full suite still has four inherited guided-demo/UI contract failures:

1. `test_tour_completion_card` expects old “stay available to explore” copy.
2. `test_job_cards_are_not_draggable` finds existing draggable-card markup.
3. `test_tour_spotlight_keeps_minimum_box_after_navigation` expects an older spotlight implementation literal.
4. `test_d01_zero_jobs_renders_all_first_run_surfaces` expects an older first-run visibility expression.

Two packaged-runtime tests require an external signed onedir fixture and fail when `LECTUREPACK_ONEDIR_FIXTURE` is unset:

5. `test_disposable_packaged_repair_proof_uses_signed_current_onedir`.
6. `test_real_packaged_smoke_uses_unicode_space_path_and_fresh_profile`.

The package health report also records existing optional YouTube degradation because `yt_dlp_ejs` and a JavaScript runtime are absent. Core local-video processing, ffmpeg/ffprobe, Whisper, the model, Rust Study Core, yt-dlp, and the controller all passed startup checks.

## Production deployment completion

- Worker: `https://lecturepack-ai-gateway.discordsammy2.workers.dev`
- D1: `lecturepack-study-prod` (`0ddaa845-8302-48d9-8fec-7d601f8be82c`), migration current.
- Secrets: independent generated signing/network-hash secrets plus a newly validated OpenRouter production key, all stored only as Worker secrets.
- Routes: OpenRouter `openrouter/free` plus native Workers AI; long-form generation uses Workers AI first, while interactive tasks use OpenRouter first and fail over independently.
- Health: configured for all eight required tasks.
- Packaged candidate: `C:\LecturePackScratch\builds\ai-study-production-20260812-r2\dist\LecturePack-win32-x64`.
- Deterministic packaged report: `C:\LecturePackScratch\results\ai-study-production-r2-deterministic-20260812\ai-study-packaged-acceptance.json` (passed).
- Live packaged report: `C:\LecturePackScratch\results\ai-study-production-r2-live-20260812\ai-study-live-packaged-acceptance.json` (passed).
- Live quality: three concepts, two guide sections, two flashcards, and three mixed quiz items; Ask, Teach Me, live grading, and Basic Study all passed.
- Privacy: the remote D1 schema contains operational metadata only and no transcript, prompt, completion, or image column.
- Owner email: disabled without a verified sender domain; alert delivery remains optional and non-blocking.

The two external signed-onedir tests still require a verified fixture through
`LECTUREPACK_ONEDIR_FIXTURE`; this is unrelated to the deployed Study gateway
and does not block user testing of the packaged candidate above.

## Final status

**READY FOR USER TEST**
