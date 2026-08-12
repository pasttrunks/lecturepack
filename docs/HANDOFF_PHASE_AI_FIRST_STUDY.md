# Handoff — AI-first Study production upgrade

**Date:** 2026-08-12
**Branch:** `codex/ai-first-study`
**Starting HEAD:** `3dc4febd67aee42c16a276b95a4d8e15ca655c67`
**Release status:** BLOCKED pending deployed-gateway and real-provider quality acceptance

## Authorized phase and goal

Implement the first production-ready AI-first Study system for LecturePack: automatic grounded Study generation after lecture processing, six student-facing Study modes, anonymous server-controlled AI routing with independent fallback, safe failure recovery, provenance, mastery persistence, packaged-app acceptance, and release hardening.

The work remained within the AI-first Study/gateway, desktop bridge and UI, packaging/acceptance harness, tests, and required architecture/product/decision documentation. It did not deploy infrastructure, publish a release, add desktop provider keys, change the lecture-processing stack, or modify original lecture videos.

## Completed

- Added a dependency-free Cloudflare Worker gateway with HMAC installation tokens, an eight-task allowlist, bounded request/response schemas, per-installation and network rate limits, content-free D1 operational telemetry, cooldown-bounded owner alerts, and OpenRouter/NVIDIA/openai-compatible routing.
- Required every task to have at least two routes on independent endpoint hosts. Provider rejection, malformed responses, and transient failures advance to the next server-controlled route.
- Kept provider credentials, model names, and route selection out of the packaged desktop. Normal success responses expose no attempted routes; sanitized failure diagnostics retain only safe route descriptors and failure metadata.
- Added automatic two-pass Study generation with hierarchical analysis for long lectures, compact material generation, at most three selected vision calls and three web-enrichment calls, strict grounding/provenance, and verified web citation URLs.
- Added Study Guide, Flashcards, mixed Quiz, live short-answer grading, Ask, Teach Me, and Quick Study (5/10/20/full) to the six-mode Study workspace.
- Added manual mastery, progress persistence, concept-linked response caching, dependency-aware concept deletion, and transcript-triggered partial regeneration that preserves unaffected concepts and mastery.
- Added Retry, sanitized Copy Diagnostics, and deterministic Basic Study recovery. Malformed partial regeneration settles into an explicit failed state rather than remaining stuck in preparing.
- Updated Home and Settings privacy language to distinguish local lecture processing from gateway-assisted Study. Legacy provider/model/API-key controls remain hidden.
- Added a packaged acceptance harness that runs the actual frozen sidecar and bundled Polar Bears lecture against a deterministic loopback gateway. It checks the complete Study flow, failure recovery, payload privacy, clean exit, and orphan processes.

## Verification evidence

- Gateway: `npm test` — **14 passed**.
- Focused Python: **70 passed, 1 skipped**. The skip is the opt-in real-gateway provider test.
- Desktop JavaScript: `npm run validate` — **passed**.
- Rust Study Core: `cargo test -- --nocapture` — **11 passed, 0 failed**. Rust source was not changed in the final UI/harness correction.
- Full Python suite: **1,507 passed, 2 skipped, 6 failed** in 210.53 seconds. All AI-first Study tests passed. The six failures are listed below.
- Windows package: `npm run package:win` — **passed**.
- Package: `C:\LecturePackScratch\builds\ai-study-final-20260812\dist\LecturePack-win32-x64`
- Packaged Study report: `C:\LecturePackScratch\results\ai-study-packaged-final2-20260812\ai-study-packaged-acceptance.json` — **passed**.
- Packaged acceptance had all checks true, including ready content, every Study interaction, lecture/web citations, selective vision, bounded web, mastery, retry, safe diagnostics, Basic fallback, payload privacy, clean exit, and zero orphan processes.
- Earlier six-mode visual QA found equal-width tabs, no horizontal overflow, complete failure/provenance/Teach UI, and no visible provider/model/API-key controls.

## Packaged quality observations

The deterministic acceptance fixture produced and persisted:

- “Polar bears are Arctic marine mammals whose physical adaptations and reliance on sea ice work together.”
- Concepts: “Transparent fur and black skin” and “Sea-ice hunting ecology.”
- Flashcards: “Is polar-bear fur actually white?” and “Why are polar bears classed as marine mammals?”

These observations prove packaged orchestration and content-shape behavior. They are not evidence of live-provider quality.

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

## Release blocker and deployment checklist

The gateway was intentionally not deployed because this workspace has no production Cloudflare bindings or provider/Resend secrets, and no authority was given to create external infrastructure. Therefore the mandatory opt-in real-provider content-quality test remains skipped.

Before release:

1. Create/bind D1 and apply `ai-gateway/migrations/0001_init.sql`.
2. Configure the HMAC signing secret, OpenRouter/NVIDIA provider secrets, and Resend alert secret/sender.
3. Configure all eight task route sets with at least two independent endpoint hosts each.
4. Deploy the Worker and point the desktop gateway URL at the deployment.
5. Run the opt-in real-gateway test and manually review grounded Study quality, lecture citations, verified web citations, selective vision, fallback behavior, usage limits, and owner alerts.
6. Supply a verified signed onedir through `LECTUREPACK_ONEDIR_FIXTURE` for the two external runtime tests.

## Final status

**BLOCKED — the production AI gateway is not deployed/configured, so mandatory live-provider content-quality and operational acceptance cannot run.**
