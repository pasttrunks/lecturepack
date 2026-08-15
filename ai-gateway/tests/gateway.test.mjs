import assert from 'node:assert/strict';
import test from 'node:test';

import { issueInstallationToken, verifyInstallationToken } from '../src/auth.js';
import { createGateway } from '../src/index.js';
import {
  callProvider, prioritizeHealthyRoutes, ProviderError, resolveRoutes,
} from '../src/providers.js';
import { countRecentUsage, getProviderHealth } from '../src/storage.js';
import { schemaForTask } from '../src/tasks.js';

const INSTALLATION_ID = '123e4567-e89b-42d3-a456-426614174000';
const TOKEN_SECRET = 'test-token-secret-with-at-least-thirty-two-characters';
const NETWORK_SECRET = 'test-network-secret-with-at-least-thirty-two-characters';

function responseJson(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } });
}

function fakeStorage() {
  const calls = [];
  return {
    calls,
    async upsertInstallation(_env, value) { calls.push(['upsertInstallation', value]); },
    async getInstallation() { return { installation_id: INSTALLATION_ID, app_version: '2.0.1', status: 'active' }; },
    async touchInstallation(_env, ...args) { calls.push(['touchInstallation', ...args]); },
    async countRecentUsage() { return 0; },
    async recordUsage(_env, value) { calls.push(['recordUsage', value]); },
    async recordLimitEvent(_env, value) { calls.push(['recordLimitEvent', value]); },
    async countRecentLimits() { return 0; },
    async recordProviderHealth(_env, ...args) { calls.push(['recordProviderHealth', ...args]); },
    async getProviderHealth() { return []; },
    async claimAlertWindow() { return false; },
    async cleanupTelemetry() {},
    async getAdminSummary() {
      return {
        total_calls: 42,
        successful_calls: 40,
        failed_calls: 2,
        total_input_tokens: 15000,
        total_output_tokens: 8500,
        avg_latency_ms: 312.4,
        active_installations: 5,
      };
    },
    async getAdminModelStats() {
      return [
        {
          provider: 'nvidia',
          model: 'meta/llama-3.1-70b-instruct',
          total_calls: 30,
          successful_calls: 30,
          failed_calls: 0,
          input_tokens: 12000,
          output_tokens: 6000,
          avg_latency_ms: 280.0,
        },
        {
          provider: 'openrouter',
          model: 'anthropic/claude-3.5-sonnet',
          total_calls: 12,
          successful_calls: 10,
          failed_calls: 2,
          input_tokens: 3000,
          output_tokens: 2500,
          avg_latency_ms: 450.0,
        },
      ];
    },
    async getAdminTaskStats() {
      return [
        { task: 'study_guide', total_calls: 20, successful_calls: 20, failed_calls: 0, input_tokens: 8000, output_tokens: 5000, avg_latency_ms: 320.0 },
      ];
    },
    async getAdminRecentEvents() {
      return [
        { id: 'evt-1', request_id: 'req-1', task: 'study_guide', route_id: 'r1', provider: 'nvidia', model: 'meta/llama-3.1-70b-instruct', success: 1, status_code: 200, failure_code: '', latency_ms: 250, input_tokens: 400, output_tokens: 200, created_at: 1700000000000 },
      ];
    },
    async getAllProviderHealth() {
      return [
        { route_id: 'nvidia-primary', consecutive_failures: 0, last_error_code: '', last_failure_at: null, last_success_at: 1700000000000 },
      ];
    },
  };
}

function baseEnv() {
  return {
    TOKEN_SIGNING_SECRET: TOKEN_SECRET,
    NETWORK_HASH_SECRET: NETWORK_SECRET,
    OPENROUTER_API_KEY: 'openrouter-secret',
    OPENROUTER_PRIMARY_MODEL: 'server/primary',
    WORKERS_AI_PRIMARY_MODEL: 'workers/secondary',
    WORKERS_AI_INTERACTIVE_MODEL: 'workers/interactive',
    WORKERS_AI_VISION_MODEL: 'workers/vision',
    OPENROUTER_FALLBACK_MODEL: 'server/fallback',
    OPENROUTER_VISION_MODEL: 'server/vision-primary',
    OPENROUTER_VISION_FALLBACK_MODEL: 'server/vision-fallback',
    AI: {
      async run() {
        return {
          response: JSON.stringify({
            answer: 'Workers AI answer', concept_ids: ['c1'],
            lecture_sources: [], web_sources: [], provenance: 'lecture',
          }),
          usage: { prompt_tokens: 10, completion_tokens: 7 },
        };
      },
    },
    MIN_APP_VERSION: '2.0.1',
    DAILY_INSTALL_LIMIT: '250',
  };
}

async function authorizedRequest(task, input, extra = {}) {
  const token = await issueInstallationToken(TOKEN_SECRET, INSTALLATION_ID, 1700000000000, 86400);
  return new Request('https://gateway.test/v1/tasks', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'content-type': 'application/json', 'x-lecturepack-version': '2.0.1' },
    body: JSON.stringify({ request_id: 'request-12345678', task, input, ...extra }),
  });
}

test('installation tokens reject tampering and expiration', async () => {
  const token = await issueInstallationToken(TOKEN_SECRET, INSTALLATION_ID, 1700000000000, 3600);
  const claims = await verifyInstallationToken(TOKEN_SECRET, token, 1700000001000);
  assert.equal(claims.sid, INSTALLATION_ID);
  await assert.rejects(() => verifyInstallationToken(TOKEN_SECRET, `${token.slice(0, -1)}x`, 1700000001000), /invalid token/);
  await assert.rejects(() => verifyInstallationToken(TOKEN_SECRET, token, 1700003601000), /expired token/);
});

test('route order and models come only from server environment', () => {
  const routes = resolveRoutes(baseEnv(), 'ask');
  assert.deepEqual(routes.map((route) => route.id), [
    'ask-openrouter', 'ask-workers-ai', 'ask-openrouter-fallback',
  ]);
  assert.deepEqual(routes.map((route) => route.model), ['server/primary', 'workers/interactive', 'server/fallback']);
  assert.deepEqual(routes.map((route) => route.failureDomain), [
    'openrouter.ai', 'workers-ai.cloudflare.com', 'openrouter.ai',
  ]);
});

test('long-form tasks can put the independent Workers AI route first', () => {
  const env = baseEnv();
  env.WORKERS_AI_FIRST_TASKS = 'study_material_generation,regenerate_concept';
  const routes = resolveRoutes(env, 'study_material_generation');
  assert.deepEqual(routes.map((route) => route.provider), [
    'workers_ai', 'openrouter', 'openrouter',
  ]);
  assert.deepEqual(routes.map((route) => route.id), [
    'study_material_generation-workers-ai',
    'study_material_generation-openrouter',
    'study_material_generation-openrouter-fallback',
  ]);
});

test('NVIDIA is fastest-first for configured text and vision tasks', () => {
  const env = baseEnv();
  env.NVIDIA_API_KEY = 'nvidia-secret';
  env.NVIDIA_PRIMARY_MODEL = 'meta/llama-3.1-8b-instruct';
  env.NVIDIA_INTERACTIVE_MODEL = 'meta/llama-3.1-8b-instruct';
  env.NVIDIA_VISION_MODEL = 'nvidia/nemotron-nano-12b-v2-vl';
  env.NVIDIA_FIRST_TASKS = 'lecture_analysis,study_material_generation,ask,teach_me,grade_short_answer,regenerate_concept,vision_slide';

  const askRoutes = resolveRoutes(env, 'ask');
  assert.deepEqual(askRoutes.map((route) => route.provider), [
    'nvidia', 'workers_ai', 'openrouter',
  ]);
  assert.deepEqual(askRoutes.map((route) => route.model), [
    'meta/llama-3.1-8b-instruct', 'workers/interactive', 'server/primary',
  ]);
  assert.deepEqual(askRoutes.map((route) => route.failureDomain), [
    'integrate.api.nvidia.com', 'workers-ai.cloudflare.com', 'openrouter.ai',
  ]);
  assert.deepEqual(askRoutes.map((route) => route.slot), [
    'primary', 'secondary', 'tertiary',
  ]);

  const visionRoutes = resolveRoutes(env, 'vision_slide');
  assert.equal(visionRoutes[0].provider, 'nvidia');
  assert.equal(visionRoutes[0].model, 'nvidia/nemotron-nano-12b-v2-vl');

  const webRoutes = resolveRoutes(env, 'web_enrichment');
  assert.deepEqual(webRoutes.map((route) => route.provider), [
    'openrouter', 'nvidia', 'workers_ai',
  ]);

  const longRoutes = resolveRoutes(env, 'study_material_generation');
  assert.ok(longRoutes.reduce((total, route) => total + route.timeoutMs, 0) <= 160000);
});

test('Google AI Studio Gemini route is resolved when configured', () => {
  const env = baseEnv();
  env.GEMINI_API_KEY = 'gemini-secret';
  env.GEMINI_PRIMARY_MODEL = 'gemini-3.5-flash';
  env.GEMINI_VISION_MODEL = 'gemini-3.5-flash';
  env.GEMINI_FIRST_TASKS = 'study_material_generation,vision_slide';

  const studyRoutes = resolveRoutes(env, 'study_material_generation');
  assert.equal(studyRoutes[0].provider, 'openai_compatible');
  assert.equal(studyRoutes[0].model, 'gemini-3.5-flash');
  assert.equal(studyRoutes[0].failureDomain, 'generativelanguage.googleapis.com');
  assert.equal(studyRoutes[0].secretEnv, 'GEMINI_API_KEY');

  const visionRoutes = resolveRoutes(env, 'vision_slide');
  assert.equal(visionRoutes[0].id, 'vision_slide-gemini');
  assert.equal(visionRoutes[0].model, 'gemini-3.5-flash');
});

test('routes cooling down after repeated failures move behind healthy fallbacks', () => {
  const routes = [
    { id: 'ask-nvidia' },
    { id: 'ask-workers-ai' },
    { id: 'ask-openrouter' },
  ];
  const now = 1700000000000;
  const health = [{
    route_id: 'ask-nvidia', consecutive_failures: 2,
    last_failure_at: now - 1000, last_success_at: now - 10000,
  }];
  assert.deepEqual(
    prioritizeHealthyRoutes(routes, health, now).map((route) => route.id),
    ['ask-workers-ai', 'ask-openrouter', 'ask-nvidia'],
  );
  assert.deepEqual(
    prioritizeHealthyRoutes(routes, health, now + 301000).map((route) => route.id),
    ['ask-nvidia', 'ask-workers-ai', 'ask-openrouter'],
  );
});

test('identical same-provider fallback routes are removed', () => {
  const env = baseEnv();
  env.OPENROUTER_FALLBACK_MODEL = env.OPENROUTER_PRIMARY_MODEL;
  const routes = resolveRoutes(env, 'lecture_analysis');
  assert.deepEqual(routes.map((route) => route.provider), ['openrouter', 'workers_ai']);
});

test('NVIDIA calls use the Worker secret and strict Study response schema', async () => {
  const env = {
    NVIDIA_API_KEY: 'nvidia-secret',
    NVIDIA_INTERACTIVE_MODEL: 'meta/llama-3.1-8b-instruct',
    NVIDIA_FIRST_TASKS: 'ask',
  };
  const route = resolveRoutes(env, 'ask')[0];
  let outboundUrl = '';
  let outboundHeaders;
  let outboundBody;
  const fetchImpl = async (url, options) => {
    outboundUrl = url;
    outboundHeaders = options.headers;
    outboundBody = JSON.parse(options.body);
    return responseJson({
      choices: [{ message: { content: JSON.stringify({
        answer: 'Large paws help polar bears swim.', concept_ids: ['c1'],
        lecture_sources: [], web_sources: [], provenance: 'lecture',
      }) } }],
      usage: { prompt_tokens: 12, completion_tokens: 8 },
    });
  };
  const response = await callProvider(fetchImpl, env, route, 'ask', {
    prompt: 'What helps polar bears swim?', retrieved_context: {},
  });
  assert.equal(response.result.answer, 'Large paws help polar bears swim.');
  assert.equal(outboundUrl, 'https://integrate.api.nvidia.com/v1/chat/completions');
  assert.equal(outboundHeaders.Authorization, 'Bearer nvidia-secret');
  assert.equal(outboundBody.model, 'meta/llama-3.1-8b-instruct');
  assert.equal(outboundBody.response_format.type, 'json_schema');
  assert.equal(outboundBody.response_format.json_schema.strict, true);
});

test('study material schema requires useful minimum content', () => {
  const properties = schemaForTask('study_material_generation').properties;
  assert.equal(properties.study_guide.minItems, 2);
  assert.equal(properties.flashcards.minItems, 2);
  assert.equal(properties.quiz.minItems, 3);
  assert.equal(properties.teach_me_foundations.minItems, 1);
});

test('a task is rejected unless the server configures a fallback route', async () => {
  const gateway = createGateway({
    storage: fakeStorage(),
    fetchImpl: async () => { throw new Error('provider must not be called'); },
    now: () => 1700000000000,
  });
  const env = baseEnv();
  delete env.AI;
  delete env.OPENROUTER_FALLBACK_MODEL;
  const response = await gateway(
    await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: {} }),
    env,
    { waitUntil() {} },
  );
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.equal(body.error.code, 'insufficient_ai_routes');
  assert.equal(body.error.retryable, true);
});

test('fallback routes must use independent provider failure domains', async () => {
  const gateway = createGateway({ storage: fakeStorage(), now: () => 1700000000000 });
  const env = baseEnv();
  env.AI_ROUTE_CONFIG = JSON.stringify({
    ask: [
      { id: 'same-host-a', provider: 'openrouter', endpoint: 'https://openrouter.ai/api/v1/chat/completions', secret_env: 'OPENROUTER_API_KEY', model: 'server/a' },
      { id: 'same-host-b', provider: 'openrouter', endpoint: 'https://openrouter.ai/api/v1/chat/completions', secret_env: 'OPENROUTER_API_KEY', model: 'server/b' },
    ],
  });
  const response = await gateway(
    await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: {} }),
    env,
    { waitUntil() {} },
  );
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.equal(body.error.code, 'insufficient_ai_routes');
  assert.deepEqual(body.diagnostics.attempted_routes, [
    'same-host-a@openrouter:server/a',
    'same-host-b@openrouter:server/b',
  ]);
});

test('daily usage counts first attempts whether they succeed or fail', async () => {
  let sql = '';
  let bound = [];
  const env = {
    DB: {
      prepare(value) {
        sql = value;
        return {
          bind(...values) {
            bound = values;
            return { async first() { return { count: 7 }; } };
          },
        };
      },
    },
  };
  const count = await countRecentUsage(env, INSTALLATION_ID, 1699913600000);
  assert.equal(count, 7);
  assert.match(sql, /attempt_number = 1/);
  assert.doesNotMatch(sql, /success = 1/);
  assert.deepEqual(bound, [INSTALLATION_ID, 1699913600000]);
});

test('provider health lookup is bounded to configured route identifiers', async () => {
  let sql = '';
  let bound = [];
  const rows = [{ route_id: 'ask-nvidia', consecutive_failures: 2 }];
  const env = {
    DB: {
      prepare(value) {
        sql = value;
        return {
          bind(...values) {
            bound = values;
            return { async all() { return { results: rows }; } };
          },
        };
      },
    },
  };
  assert.deepEqual(await getProviderHealth(env, [
    'ask-nvidia', 'ask-workers-ai', 'ask-openrouter', 'ignored-fourth',
  ]), rows);
  assert.match(sql, /route_id IN \(\?, \?, \?\)/);
  assert.deepEqual(bound, ['ask-nvidia', 'ask-workers-ai', 'ask-openrouter']);
});

test('registration returns an anonymous installation token', async () => {
  const store = fakeStorage();
  const gateway = createGateway({ storage: store, now: () => 1700000000000 });
  const request = new Request('https://gateway.test/v1/installations/register', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ installation_id: INSTALLATION_ID, app_version: '2.0.1' }),
  });
  const response = await gateway(request, baseEnv(), { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.ok, true);
  assert.match(body.installation_token, /^[^.]+\.[^.]+$/);
  assert.equal(store.calls[0][0], 'upsertInstallation');
});

test('provider and model choices in a client task are rejected', async () => {
  const gateway = createGateway({ storage: fakeStorage(), now: () => 1700000000000 });
  const response = await gateway(await authorizedRequest('ask', { prompt: 'why?', context: {}, model: 'attacker/model' }), baseEnv(), { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 400);
  assert.equal(body.error.code, 'invalid_task_input');
});

test('gateway falls back across server routes and stores metadata only', async () => {
  const store = fakeStorage();
  const outbound = [];
  const fetchImpl = async (_url, options) => {
    const payload = JSON.parse(options.body);
    outbound.push(payload);
    if (outbound.length === 1) return responseJson({ error: { message: 'busy' } }, 503);
    return responseJson({
      choices: [{ message: { content: JSON.stringify({ answer: 'Grounded answer', concept_ids: ['c1'], lecture_sources: [], web_sources: [], provenance: 'lecture' }) } }],
      usage: { prompt_tokens: 12, completion_tokens: 8 },
    });
  };
  const env = baseEnv();
  let workersAiBody;
  env.AI = {
    async run(_model, body) {
      workersAiBody = body;
      return {
        response: JSON.stringify({ answer: 'Grounded answer', concept_ids: ['c1'], lecture_sources: [], web_sources: [], provenance: 'lecture' }),
        usage: { prompt_tokens: 12, completion_tokens: 8 },
      };
    },
  };
  const gateway = createGateway({ storage: store, fetchImpl, now: () => 1700000000000, randomUUID: () => `event-${store.calls.length}` });
  const response = await gateway(await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: { concepts: [] } }), env, { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.result.answer, 'Grounded answer');
  assert.deepEqual(body.diagnostics.attempted_routes, []);
  assert.equal(body.diagnostics.retry_count, 1);
  assert.equal(JSON.stringify(body).includes('server/primary'), false);
  assert.equal(JSON.stringify(body).includes('server/secondary'), false);
  assert.equal(outbound[0].model, 'server/primary');
  assert.equal(outbound.length, 1);
  assert.equal(workersAiBody.response_format.type, 'json_schema');
  const usage = store.calls.filter(([name]) => name === 'recordUsage').map(([, value]) => value);
  assert.equal(usage.length, 2);
  assert.deepEqual(usage.map((event) => event.attemptNumber), [1, 2]);
  assert.equal(usage[0].provider, 'openrouter');
  assert.equal(usage[0].model, 'server/primary');
  assert.equal(usage[0].result, 'failure');
  assert.equal(usage[0].failureCode, 'provider_unavailable');
  assert.equal(usage[1].provider, 'workers_ai');
  assert.equal(usage[1].model, 'workers/interactive');
  assert.equal(usage[1].inputTokens, 12);
  assert.equal(usage[1].outputTokens, 8);
  assert.equal(usage[1].result, 'success');
  assert.equal(JSON.stringify(usage).includes('What matters?'), false);
  assert.equal(JSON.stringify(usage).includes('Grounded answer'), false);
});

test('provider 4xx rejection advances to the independent fallback route', async () => {
  let attempts = 0;
  const fetchImpl = async () => {
    attempts += 1;
    if (attempts === 1) return responseJson({ error: { message: 'model retired' } }, 400);
    throw new Error('external tertiary must not be called after Workers AI succeeds');
  };
  const env = baseEnv();
  env.AI = { async run() { return { response: JSON.stringify({
    answer: 'Fallback answer', concept_ids: ['c1'],
    lecture_sources: [], web_sources: [], provenance: 'lecture',
  }) }; } };
  const gateway = createGateway({ storage: fakeStorage(), fetchImpl, now: () => 1700000000000 });
  const response = await gateway(
    await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: {} }),
    env,
    { waitUntil() {} },
  );
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.result.answer, 'Fallback answer');
  assert.equal(attempts, 1);
  assert.deepEqual(body.diagnostics.provider_codes, ['provider_rejected']);
});

test('malformed provider shape is rejected before the next route succeeds', async () => {
  let attempts = 0;
  const fetchImpl = async () => {
    attempts += 1;
    return responseJson({ choices: [{ message: { content: JSON.stringify({ answer: 'missing required grounding fields' }) } }] });
  };
  const gateway = createGateway({ storage: fakeStorage(), fetchImpl, now: () => 1700000000000 });
  const response = await gateway(await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: {} }), baseEnv(), { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.result.answer, 'Workers AI answer');
  assert.deepEqual(body.diagnostics.attempted_routes, []);
  assert.equal(body.diagnostics.retry_count, 1);
  assert.equal(attempts, 1);
});

test('web enrichment uses bounded search and only official provider URL citations', async () => {
  let outbound;
  const fetchImpl = async (_url, options) => {
    outbound = JSON.parse(options.body);
    return responseJson({
    choices: [{ message: {
      content: JSON.stringify({
        summary: 'Verified context',
        facts: [
          { claim: 'Supported', title: 'Primary source', url: 'https://example.edu/source' },
          { claim: 'Invented', title: 'Fake', url: 'https://fake.invalid/source' },
        ],
        sources: [{ title: 'Fake', url: 'https://fake.invalid/source', claim: 'Invented' }],
      }),
      annotations: [{ type: 'url_citation', url_citation: { title: 'Primary source', url: 'https://example.edu/source', content: 'Supported fact' } }],
    } }],
  });
  };
  const gateway = createGateway({ storage: fakeStorage(), fetchImpl, now: () => 1700000000000 });
  const response = await gateway(await authorizedRequest('web_enrichment', { concept_id: 'c1', query: 'source context' }), baseEnv(), { waitUntil() {} });
  const body = await response.json();
  assert.equal(body.result.sources[0].title, 'Primary source');
  assert.equal(body.result.sources[0].url, 'https://example.edu/source');
  assert.deepEqual(body.result.facts.map((fact) => fact.url), ['https://example.edu/source']);
  assert.equal(JSON.stringify(body.result).includes('fake.invalid'), false);
  assert.equal(outbound.max_tool_calls, 1);
  assert.equal(outbound.tools[0].parameters.max_results, 3);
  assert.equal(outbound.tools[0].parameters.max_total_results, 3);
  assert.equal(outbound.tools[0].parameters.max_uses, 1);
});

test('provider response bodies are bounded', async () => {
  const route = resolveRoutes(baseEnv(), 'ask')[0];
  const fetchImpl = async () => new Response('x', {
    status: 200,
    headers: { 'content-length': String(16 * 1024 * 1024 + 1) },
  });
  await assert.rejects(
    () => callProvider(fetchImpl, baseEnv(), route, 'ask', { prompt: 'bounded', retrieved_context: {} }),
    (error) => error instanceof ProviderError && error.code === 'provider_response_too_large',
  );
});

test('all provider failures return safe diagnostics without provider secrets', async () => {
  const fetchImpl = async () => responseJson({ error: { message: 'upstream included secret' } }, 503);
  const env = baseEnv();
  env.AI = { async run() { throw new Error('Workers AI unavailable'); } };
  const gateway = createGateway({ storage: fakeStorage(), fetchImpl, now: () => 1700000000000 });
  const response = await gateway(await authorizedRequest('ask', { prompt: 'hello', retrieved_context: {} }), env, { waitUntil() {} });
  const text = await response.text();
  const body = JSON.parse(text);
  assert.equal(response.status, 503);
  assert.equal(body.error.code, 'ai_routes_failed');
  assert.deepEqual(body.diagnostics.provider_codes, [
    'provider_unavailable', 'provider_unavailable', 'provider_unavailable',
  ]);
  assert.deepEqual(body.diagnostics.provider_status, [503, 502, 503]);
  assert.equal(body.diagnostics.retry_count, 2);
  assert.equal(text.includes('openrouter-secret'), false);
  assert.equal(text.includes('upstream included secret'), false);
});

test('health is configured only when every task has an independent fallback', async () => {
  const gateway = createGateway({ storage: fakeStorage(), now: () => 1700000000000 });
  const complete = { ...baseEnv(), DB: {} };
  const healthy = await gateway(
    new Request('https://gateway.test/v1/health'), complete, { waitUntil() {} });
  const healthyBody = await healthy.json();
  assert.equal(healthyBody.configured, true);
  assert.equal(healthyBody.configured_tasks, healthyBody.required_tasks);

  const incomplete = { ...complete };
  delete incomplete.AI;
  const unhealthy = await gateway(
    new Request('https://gateway.test/v1/health'), incomplete, { waitUntil() {} });
  const unhealthyBody = await unhealthy.json();
  assert.equal(unhealthyBody.configured, false);
  assert.equal(unhealthyBody.configured_tasks, 0);
});

test('admin stats endpoint enforces authentication and returns metrics', async () => {
  const gateway = createGateway({ storage: fakeStorage(), now: () => 1700000000000 });
  const env = { ...baseEnv(), ADMIN_API_KEY: 'super-admin-secret' };

  // 1. Unauthenticated request returns 401
  const unauthorized = await gateway(new Request('https://gateway.test/v1/admin/stats'), env, { waitUntil() {} });
  assert.equal(unauthorized.status, 401);
  const unauthBody = await unauthorized.json();
  assert.equal(unauthBody.ok, false);
  assert.equal(unauthBody.error.code, 'unauthorized_admin');

  // 2. Request with wrong key returns 401
  const wrongKey = await gateway(new Request('https://gateway.test/v1/admin/stats', {
    headers: { 'x-admin-key': 'wrong-key' },
  }), env, { waitUntil() {} });
  assert.equal(wrongKey.status, 401);

  // 3. Authorized request with header returns stats payload
  const authorized = await gateway(new Request('https://gateway.test/v1/admin/stats?window=24h', {
    headers: { 'x-admin-key': 'super-admin-secret' },
  }), env, { waitUntil() {} });
  assert.equal(authorized.status, 200);
  const body = await authorized.json();
  assert.equal(body.ok, true);
  assert.equal(body.summary.total_calls, 42);
  assert.equal(body.models.length, 2);
  assert.equal(body.models[0].provider, 'nvidia');
  assert.equal(body.tasks[0].task, 'study_guide');
  assert.equal(body.health[0].route_id, 'nvidia-primary');
  assert.equal(body.recent_events.length, 1);
});

test('admin dashboard endpoint serves HTML interface', async () => {
  const gateway = createGateway({ storage: fakeStorage(), now: () => 1700000000000 });
  const env = baseEnv();
  const res = await gateway(new Request('https://gateway.test/v1/admin/dashboard'), env, { waitUntil() {} });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('content-type').includes('text/html'), true);
  const html = await res.text();
  assert.equal(html.includes('LecturePack'), true);
  assert.equal(html.includes('Admin Gateway'), true);
  assert.equal(html.includes('ADMIN_API_KEY'), true);
});

