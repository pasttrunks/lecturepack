# LecturePack AI Gateway

This directory is the server-side proxy/router for AI-first Study. It is a
dependency-free ES module Cloudflare Worker and does not contain desktop UI or
lecture-processing code.

The gateway accepts anonymous installation tokens, routes a fixed allowlist of
Study task types across a server-controlled 2-3 route chain, normalizes
provider failures, applies install/network limits, and writes only operational
metadata to D1. It never stores transcript text, prompts, completions, or slide
images.

## Configure and deploy

1. Copy `wrangler.toml.example` to `wrangler.toml` and configure the D1 binding.
2. Apply `migrations/0001_init.sql` to the D1 database.
3. Bind Workers AI and configure 2-3 routes for every task across NVIDIA,
   native Workers AI, and OpenRouter. Models and route ordering remain
   server-side; `AI_ROUTE_CONFIG` can still supply explicit per-task route
   arrays. The gateway fails closed if a task has no independent fallback.
4. Add `TOKEN_SIGNING_SECRET`, `NETWORK_HASH_SECRET`, `NVIDIA_API_KEY`, and
   `OPENROUTER_API_KEY` with `wrangler secret put`. Optional Resend alerts also
   require `RESEND_API_KEY` and a verified `ALERT_FROM_EMAIL`.
5. Run `npm test`, use `wrangler deploy --dry-run` to validate bindings, then
   deploy with Wrangler.

`GET /v1/health` reports `configured: true` only when D1/auth secrets exist and
all eight task types have an independent fallback. It never returns route
names, model names, credentials, or lecture data.

Daily installation usage counts the first provider attempt for every task,
including failed tasks; fallback attempts do not consume additional daily
units. D1 retains only bounded operational metadata and is sampled for cleanup
using `TELEMETRY_RETENTION_DAYS`.

Production text and vision routes are fastest-first based on complete
LecturePack schema benchmarks, not a token-only microbenchmark. Two consecutive
route failures open a five-minute metadata-only cooldown, moving that route
behind healthy independent fallbacks without removing it from the chain.
OpenRouter remains first for `web_enrichment` because its bounded search
annotations are the citation authority for that task.

The production desktop default is
`https://lecturepack-ai-gateway.discordsammy2.workers.dev`. The
`LECTUREPACK_AI_GATEWAY_URL` override remains available for controlled tests.
Plain HTTP is accepted only for loopback integration tests.

Provider contracts were checked against the official NVIDIA NIM chat,
structured-generation, and model documentation; OpenRouter free-router,
structured-output, and web-search documentation; plus Cloudflare Workers AI,
Web Crypto, D1, and rate-limit binding documentation. Direct links and the
production acceptance records are in `docs/DECISIONS.md` (AD-46 and AD-47).
