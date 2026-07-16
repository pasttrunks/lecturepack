# Local AI (Ollama) Setup — optional

LecturePack can use a **locally installed** [Ollama](https://ollama.com)
server to propose transcript corrections (Context Repair), section headings
and summaries. This is entirely optional:

* Nothing is bundled — no Ollama runtime, no models.
* Everything works without it (the deterministic offline repair provider is
  always available).
* No internet is required at runtime; requests go to `http://localhost:11434`.
* Exports never wait for AI, and AI can never modify the raw transcript or
  apply anything without your review.

## Setup

1. Install Ollama from https://ollama.com/download (Windows installer).
2. Pull a model. Recommended default for this app:

   ```
   ollama pull qwen3:1.7b
   ```

   Alternatives: `qwen3:0.6b` (ultra-light), `gemma3:1b` (low memory),
   `qwen3.5:4b` / `qwen3.5:9b` (stronger, slower), `ministral-3:3b`
   (use the explicit `:3b` tag — `ministral-3:latest` is far larger).
3. In LecturePack: **Settings → AI (Ollama)** → check *Enable AI assistance*,
   click **Refresh** (lists installed models with size/quantization), pick a
   model, click **Test model**, **Save settings**.

### Why qwen3:1.7b?

Benchmarked on this machine against installed alternatives with a
schema-constrained repair task containing 8 planted transcription errors
(`docs/evidence/v1.1.0/ollama_model_benchmark.json`):

| Model | Correct fixes | False proposals on clean text | Total time |
|---|---|---|---|
| qwen3:1.7b | 5/8 | 2 | 21.9 s |
| qwen3.5:4b | 3/8 | 0 | 45.7 s |
| qwen3.5:9b | 5/8 | 0 | 51.0 s |

qwen3:1.7b matches the 9B model's recall at a fraction of the time and
memory. Its occasional extra proposals are harmless in this workflow because
**no AI proposal is ever auto-accepted** — each one is shown with a word-level
diff, explanation and confidence for you to accept, reject or edit.

## How LecturePack talks to Ollama

* `POST /api/chat` with `stream: true`, **`format` set to a strict JSON
  schema**, `temperature 0`, `think: false`, low `num_predict`, and limited
  context (chunks of ~12 segments with your approved names/glossary).
* Model list from `GET /api/tags`; version from `/api/version`.
* `keep_alive` is configurable (default 10m; `0` unloads immediately).
* Responses are cached on disk per job
  (`transcript/ai_cache.json`, keyed by transcript hash + context + model +
  prompt version), so re-running proposals is instant and offline.

## Fault isolation (what happens when things go wrong)

Ollama being down, a connection refusal, a timeout, malformed output, or the
model unloading mid-generation can never crash LecturePack. Generation always
runs in a background worker; failures surface as an inline message with:

* **Retry**
* **Use deterministic repair only** (offline, approved-names matching)
* **Open Ollama settings**
* **Copy diagnostic details**

Closing the dialog or the app mid-request cancels the stream safely. These
failure modes are covered by automated tests
(`tests/test_ollama_and_repair.py`).

## Scope of AI assistance

May: propose spelling/proper-name corrections with explanations and
confidence; suggest section headings (marked “(AI)”, editable); generate
optional summaries.

May not: modify the raw transcript; apply corrections silently; invent
quotes; change numbers/dates without review; regenerate the transcript as
prose; block exports when unavailable.
