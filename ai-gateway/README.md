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
3. Configure 2-3 routes for every task across at least two independent
   provider endpoint hosts. Models and route ordering remain server-side.
   `AI_ROUTE_CONFIG` can supply per-task route arrays; the gateway fails closed
   if a task has no independent fallback.
4. Add secrets with Wrangler: `TOKEN_SIGNING_SECRET`, `NETWORK_HASH_SECRET`,
   `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, and optionally `RESEND_API_KEY`.
5. Configure a verified `ALERT_FROM_EMAIL`; alerts go to
   `discordsammy2@gmail.com` by default and contain no lecture content.
6. Run `npm test`, then deploy with the installed Wrangler CLI.

`GET /v1/health` reports `configured: true` only when D1/auth secrets exist and
all eight task types have an independent fallback. It never returns route
names, model names, credentials, or lecture data.

Daily installation usage counts the first provider attempt for every task,
including failed tasks; fallback attempts do not consume additional daily
units. D1 retains only bounded operational metadata and is sampled for cleanup
using `TELEMETRY_RETENTION_DAYS`.

The desktop endpoint is configured with `LECTUREPACK_AI_GATEWAY_URL`. Production
packages should set it to the deployed HTTPS Worker URL. Plain HTTP is accepted
only for loopback integration tests.

Provider contracts were checked against the official OpenRouter structured
outputs and web-search tool documentation, NVIDIA's OpenAI-compatible NIM
inference reference, Cloudflare Workers Web Crypto/D1/rate-limit binding
documentation, and Resend's send-email API before implementation. Direct links
are recorded in `docs/DECISIONS.md` (AD-46).
