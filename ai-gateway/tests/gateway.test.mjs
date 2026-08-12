import assert from 'node:assert/strict';
import test from 'node:test';

import { issueInstallationToken, verifyInstallationToken } from '../src/auth.js';
import { createGateway } from '../src/index.js';
import { callProvider, ProviderError, resolveRoutes } from '../src/providers.js';
import { countRecentUsage } from '../src/storage.js';

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
    async claimAlertWindow() { return false; },
    async cleanupTelemetry() {},
  };
}

function baseEnv() {
  return {
    TOKEN_SIGNING_SECRET: TOKEN_SECRET,
    NETWORK_HASH_SECRET: NETWORK_SECRET,
    OPENROUTER_API_KEY: 'openrouter-secret',
    NVIDIA_API_KEY: 'nvidia-secret',
    OPENROUTER_PRIMARY_MODEL: 'server/primary',
    NVIDIA_PRIMARY_MODEL: 'server/secondary',
    OPENROUTER_FALLBACK_MODEL: 'server/fallback',
    OPENROUTER_VISION_MODEL: 'server/vision-primary',
    NVIDIA_VISION_MODEL: 'server/vision-secondary',
    OPENROUTER_VISION_FALLBACK_MODEL: 'server/vision-fallback',
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
  assert.deepEqual(routes.map((route) => route.id), ['ask-primary', 'ask-secondary', 'ask-tertiary']);
  assert.deepEqual(routes.map((route) => route.model), ['server/primary', 'server/secondary', 'server/fallback']);
});

test('a task is rejected unless the server configures a fallback route', async () => {
  const gateway = createGateway({
    storage: fakeStorage(),
    fetchImpl: async () => { throw new Error('provider must not be called'); },
    now: () => 1700000000000,
  });
  const env = baseEnv();
  delete env.NVIDIA_API_KEY;
  delete env.NVIDIA_PRIMARY_MODEL;
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
  const gateway = createGateway({ storage: store, fetchImpl, now: () => 1700000000000, randomUUID: () => `event-${store.calls.length}` });
  const response = await gateway(await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: { concepts: [] } }), baseEnv(), { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.result.answer, 'Grounded answer');
  assert.deepEqual(body.diagnostics.attempted_routes, []);
  assert.equal(body.diagnostics.retry_count, 1);
  assert.equal(JSON.stringify(body).includes('server/primary'), false);
  assert.equal(JSON.stringify(body).includes('server/secondary'), false);
  assert.equal(outbound[0].model, 'server/primary');
  assert.equal(outbound[1].model, 'server/secondary');
  const usage = store.calls.filter(([name]) => name === 'recordUsage').map(([, value]) => value);
  assert.equal(usage.length, 2);
  assert.deepEqual(usage.map((event) => event.attemptNumber), [1, 2]);
  assert.equal(usage[0].provider, 'openrouter');
  assert.equal(usage[0].model, 'server/primary');
  assert.equal(usage[0].result, 'failure');
  assert.equal(usage[0].failureCode, 'provider_unavailable');
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
    return responseJson({
      choices: [{ message: { content: JSON.stringify({
        answer: 'Fallback answer', concept_ids: ['c1'],
        lecture_sources: [], web_sources: [], provenance: 'lecture',
      }) } }],
    });
  };
  const gateway = createGateway({ storage: fakeStorage(), fetchImpl, now: () => 1700000000000 });
  const response = await gateway(
    await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: {} }),
    baseEnv(),
    { waitUntil() {} },
  );
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.result.answer, 'Fallback answer');
  assert.equal(attempts, 2);
  assert.deepEqual(body.diagnostics.provider_codes, ['provider_rejected']);
});

test('malformed provider shape is rejected before the next route succeeds', async () => {
  let attempts = 0;
  const fetchImpl = async () => {
    attempts += 1;
    const result = attempts === 1
      ? { answer: 'missing required grounding fields' }
      : { answer: 'Grounded answer', concept_ids: ['c1'], lecture_sources: [], web_sources: [], provenance: 'lecture' };
    return responseJson({ choices: [{ message: { content: JSON.stringify(result) } }] });
  };
  const gateway = createGateway({ storage: fakeStorage(), fetchImpl, now: () => 1700000000000 });
  const response = await gateway(await authorizedRequest('ask', { prompt: 'What matters?', retrieved_context: {} }), baseEnv(), { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.result.answer, 'Grounded answer');
  assert.deepEqual(body.diagnostics.attempted_routes, []);
  assert.equal(body.diagnostics.retry_count, 1);
  assert.equal(attempts, 2);
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
  const gateway = createGateway({ storage: fakeStorage(), fetchImpl, now: () => 1700000000000 });
  const response = await gateway(await authorizedRequest('ask', { prompt: 'hello', retrieved_context: {} }), baseEnv(), { waitUntil() {} });
  const text = await response.text();
  const body = JSON.parse(text);
  assert.equal(response.status, 503);
  assert.equal(body.error.code, 'ai_routes_failed');
  assert.deepEqual(body.diagnostics.provider_codes, [
    'provider_unavailable', 'provider_unavailable', 'provider_unavailable',
  ]);
  assert.deepEqual(body.diagnostics.provider_status, [503, 503, 503]);
  assert.equal(body.diagnostics.retry_count, 2);
  assert.equal(text.includes('openrouter-secret'), false);
  assert.equal(text.includes('nvidia-secret'), false);
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
  delete incomplete.NVIDIA_API_KEY;
  delete incomplete.NVIDIA_PRIMARY_MODEL;
  const unhealthy = await gateway(
    new Request('https://gateway.test/v1/health'), incomplete, { waitUntil() {} });
  const unhealthyBody = await unhealthy.json();
  assert.equal(unhealthyBody.configured, false);
  assert.equal(unhealthyBody.configured_tasks, 0);
});
