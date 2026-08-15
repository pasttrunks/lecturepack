import { buildMessages, maxOutputTokens, schemaForTask, validateTaskResult } from './tasks.js';

const ROUTE_SLOTS = Object.freeze(['primary', 'secondary', 'tertiary']);

export class ProviderError extends Error {
  constructor(code, message, status = 502, retryable = true) {
    super(message);
    this.name = 'ProviderError';
    this.code = String(code || 'provider_error');
    this.status = Number(status) || 502;
    this.retryable = retryable !== false;
  }
}

function taskEnvName(task) {
  return String(task || '').replace(/[^A-Za-z0-9]/g, '_').toUpperCase();
}

function configuredTasks(value) {
  return new Set(
    String(value || '')
      .split(',').map((item) => item.trim()).filter(Boolean),
  );
}

function routeTimeouts(task) {
  if (task === 'vision_slide') {
    return { nvidia: 25000, gemini: 25000, workers_ai: 30000, openrouter: 25000 };
  }
  if (task === 'web_enrichment') {
    return { nvidia: 12000, gemini: 15000, workers_ai: 15000, openrouter: 20000 };
  }
  if (['ask', 'teach_me', 'grade_short_answer'].includes(task)) {
    return { nvidia: 12000, gemini: 15000, workers_ai: 25000, openrouter: 20000 };
  }
  // The three-route worst case is 160 seconds, leaving room inside the
  // desktop client's 175-second request deadline for gateway/D1 overhead.
  return { nvidia: 50000, gemini: 45000, workers_ai: 65000, openrouter: 45000 };
}

function defaultRoutes(env, task) {
  const suffix = taskEnvName(task);
  const vision = task === 'vision_slide';
  const interactive = ['ask', 'teach_me', 'grade_short_answer'].includes(task);
  const timeouts = routeTimeouts(task);
  const geminiFirst = configuredTasks(env.GEMINI_FIRST_TASKS).has(task);
  const nvidiaFirst = configuredTasks(env.NVIDIA_FIRST_TASKS).has(task);
  const workersFirst = configuredTasks(env.WORKERS_AI_FIRST_TASKS).has(task);
  const geminiModel = vision
    ? (env.GEMINI_VISION_MODEL || '')
    : (env[`GEMINI_${suffix}_MODEL`]
      || (interactive ? env.GEMINI_INTERACTIVE_MODEL : env.GEMINI_PRIMARY_MODEL)
      || '');
  const openRouterPrimary = vision
    ? (env.OPENROUTER_VISION_MODEL || '')
    : (env[`OPENROUTER_${suffix}_MODEL`] || env.OPENROUTER_PRIMARY_MODEL || '');
  const workersAiModel = vision
    ? (env.WORKERS_AI_VISION_MODEL || '')
    : (env[`WORKERS_AI_${suffix}_MODEL`]
      || (interactive ? env.WORKERS_AI_INTERACTIVE_MODEL : env.WORKERS_AI_PRIMARY_MODEL)
      || '');
  const nvidiaModel = vision
    ? (env.NVIDIA_VISION_MODEL || '')
    : (env[`NVIDIA_${suffix}_MODEL`]
      || (interactive ? env.NVIDIA_INTERACTIVE_MODEL : env.NVIDIA_PRIMARY_MODEL)
      || '');
  const openRouterFallback = vision
    ? (env.OPENROUTER_VISION_FALLBACK_MODEL || '')
    : (env[`OPENROUTER_${suffix}_FALLBACK_MODEL`] || env.OPENROUTER_FALLBACK_MODEL || '');
  const geminiRoute = {
    id: `${task}-gemini`,
    provider: 'openai_compatible',
    endpoint: 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
    secret_env: 'GEMINI_API_KEY',
    model: geminiModel,
    structured_outputs: false,
    timeout_ms: timeouts.gemini,
  };
  const openRouterRoute = {
    id: `${task}-openrouter`,
    provider: 'openrouter',
    endpoint: 'https://openrouter.ai/api/v1/chat/completions',
    secret_env: 'OPENROUTER_API_KEY',
    model: openRouterPrimary,
    structured_outputs: true,
    timeout_ms: timeouts.openrouter,
  };
  const nvidiaRoute = {
    id: `${task}-nvidia`,
    provider: 'nvidia',
    endpoint: 'https://integrate.api.nvidia.com/v1/chat/completions',
    secret_env: 'NVIDIA_API_KEY',
    model: nvidiaModel,
    structured_outputs: true,
    timeout_ms: timeouts.nvidia,
  };
  const workersAiRoute = {
    id: `${task}-workers-ai`,
    provider: 'workers_ai',
    model: workersAiModel,
    structured_outputs: true,
    timeout_ms: timeouts.workers_ai,
  };
  const openRouterFallbackRoute = {
    id: `${task}-openrouter-fallback`,
    provider: 'openrouter',
    endpoint: 'https://openrouter.ai/api/v1/chat/completions',
    secret_env: 'OPENROUTER_API_KEY',
    model: openRouterFallback,
    structured_outputs: true,
    timeout_ms: timeouts.openrouter,
  };
  if (geminiFirst) {
    return [geminiRoute, nvidiaRoute, workersAiRoute, openRouterRoute, openRouterFallbackRoute];
  }
  if (nvidiaFirst) {
    return [nvidiaRoute, geminiRoute, workersAiRoute, openRouterRoute, openRouterFallbackRoute];
  }
  if (workersFirst) {
    return [workersAiRoute, geminiRoute, nvidiaRoute, openRouterRoute, openRouterFallbackRoute];
  }
  // OpenRouter remains first by default because web_enrichment depends on its
  // bounded server-side search annotations. Other production tasks opt into
  // the measured NVIDIA-first route explicitly through NVIDIA_FIRST_TASKS.
  return [openRouterRoute, geminiRoute, nvidiaRoute, workersAiRoute, openRouterFallbackRoute];
}

export function prioritizeHealthyRoutes(routes, healthRows, now = Date.now(), options = {}) {
  const threshold = Math.max(1, Number(options.failureThreshold) || 2);
  const cooldownMs = Math.max(1000, Number(options.cooldownMs) || 300000);
  const health = new Map((Array.isArray(healthRows) ? healthRows : []).map((row) => [
    String(row && row.route_id || ''), row || {},
  ]));
  return routes.map((route, index) => {
    const row = health.get(route.id) || {};
    const failures = Math.max(0, Number(row.consecutive_failures) || 0);
    const lastFailure = Math.max(0, Number(row.last_failure_at) || 0);
    const lastSuccess = Math.max(0, Number(row.last_success_at) || 0);
    const coolingDown = failures >= threshold
      && lastFailure > now - cooldownMs
      && lastFailure >= lastSuccess;
    return { route, index, coolingDown };
  }).sort((left, right) => (
    Number(left.coolingDown) - Number(right.coolingDown) || left.index - right.index
  )).map(({ route }) => route);
}

function safeRoute(route, index, task, env) {
  if (!route || typeof route !== 'object') return null;
  const provider = String(route.provider || '').toLowerCase();
  if (!['openrouter', 'nvidia', 'openai_compatible', 'workers_ai'].includes(provider)) return null;
  const model = String(route.model || (route.model_env && env[String(route.model_env)]) || '').trim();
  if (provider === 'workers_ai') {
    if (!model || !env.AI || typeof env.AI.run !== 'function') return null;
    return {
      id: String(route.id || `${task}-route-${index + 1}`).replace(/[^A-Za-z0-9_.:-]/g, '-').slice(0, 96),
      provider,
      endpoint: '',
      failureDomain: 'workers-ai.cloudflare.com',
      secretEnv: '',
      model,
      structuredOutputs: route.structured_outputs !== false,
      timeoutMs: Math.max(10000, Math.min(180000, Number(route.timeout_ms) || 90000)),
    };
  }
  const endpoint = String(route.endpoint || '').trim();
  if (!endpoint.startsWith('https://')) return null;
  const secretEnv = String(route.secret_env || '').trim();
  if (!secretEnv || !model || !env[secretEnv]) return null;
  return {
    id: String(route.id || `${task}-route-${index + 1}`).replace(/[^A-Za-z0-9_.:-]/g, '-').slice(0, 96),
    provider,
    endpoint,
    failureDomain: new URL(endpoint).hostname.toLowerCase(),
    secretEnv,
    model,
    structuredOutputs: route.structured_outputs === true,
    timeoutMs: Math.max(10000, Math.min(180000, Number(route.timeout_ms) || 90000)),
  };
}

export function resolveRoutes(env, task) {
  let configured = null;
  if (env.AI_ROUTE_CONFIG) {
    try {
      const parsed = JSON.parse(env.AI_ROUTE_CONFIG);
      configured = parsed && Array.isArray(parsed[task]) ? parsed[task] : null;
    } catch (_) {
      throw new ProviderError('route_config_invalid', 'The gateway route configuration is invalid.', 503, false);
    }
  }
  const raw = configured || defaultRoutes(env, task);
  const seen = new Set();
  return raw
    .map((route, index) => safeRoute(route, index, task, env))
    .filter(Boolean)
    .filter((route) => {
      const key = `${route.provider}|${route.failureDomain}|${route.model}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 3)
    .map((route, index) => ({ ...route, slot: ROUTE_SLOTS[index] }));
}

function responseFormat(task) {
  const schema = schemaForTask(task);
  if (!schema) return null;
  return {
    type: 'json_schema',
    json_schema: {
      name: `lecturepack_${task}`.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 64),
      strict: true,
      schema,
    },
  };
}

function workersAiResponseFormat(task) {
  const schema = schemaForTask(task);
  return schema ? { type: 'json_schema', json_schema: schema } : null;
}

function stripJsonFence(value) {
  const text = String(value || '').trim();
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return fenced ? fenced[1].trim() : text;
}

function messageText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map((part) => (part && (part.text || part.content)) || '').join('');
  }
  if (content && typeof content === 'object') return JSON.stringify(content);
  return '';
}

function extractCitations(message) {
  const citations = [];
  for (const annotation of (message && message.annotations) || []) {
    const item = annotation && annotation.url_citation;
    if (!item || !/^https:\/\//i.test(String(item.url || ''))) continue;
    citations.push({
      title: String(item.title || new URL(item.url).hostname).slice(0, 300),
      url: String(item.url).slice(0, 2000),
      claim: String(item.content || '').slice(0, 1200),
    });
  }
  return citations;
}

function mergeWebCitations(task, result, citations) {
  if (task !== 'web_enrichment') return result;
  // Provider annotations are the source of truth. Model-authored URLs are not
  // accepted as verified web citations, even when they look syntactically valid.
  const seen = new Set();
  result.sources = citations.filter((source) => {
    if (seen.has(source.url)) return false;
    seen.add(source.url);
    return true;
  });
  result.facts = (Array.isArray(result.facts) ? result.facts : []).filter(
    (fact) => fact && seen.has(String(fact.url || '')),
  );
  return result;
}

async function readBoundedResponseText(response, maximumBytes) {
  const declared = Number(response.headers.get('content-length') || 0);
  if (declared > maximumBytes) {
    throw new ProviderError('provider_response_too_large', 'The AI route returned too much data.', 502, true);
  }
  if (!response.body || typeof response.body.getReader !== 'function') {
    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > maximumBytes) {
      throw new ProviderError('provider_response_too_large', 'The AI route returned too much data.', 502, true);
    }
    return text;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let total = 0;
  let text = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maximumBytes) {
      try { await reader.cancel(); } catch (_) { /* best effort */ }
      throw new ProviderError('provider_response_too_large', 'The AI route returned too much data.', 502, true);
    }
    text += decoder.decode(value, { stream: true });
  }
  return text + decoder.decode();
}

function normalizedProviderResult(payload, task) {
  const message = payload && payload.choices && payload.choices[0] && payload.choices[0].message;
  const value = message ? message.content : payload && payload.response;
  const raw = messageText(value);
  let result;
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    result = value;
  } else {
    try {
      result = JSON.parse(stripJsonFence(raw));
    } catch (_) {
      throw new ProviderError('provider_invalid_json', 'The AI route returned an invalid structured response.', 502, true);
    }
  }
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    throw new ProviderError('provider_invalid_shape', 'The AI route returned an invalid response shape.', 502, true);
  }
  mergeWebCitations(task, result, extractCitations(message));
  try {
    validateTaskResult(task, result);
  } catch (_) {
    throw new ProviderError('provider_invalid_shape', 'The AI route returned an invalid response shape.', 502, true);
  }
  return { result, raw };
}

async function callWorkersAi(env, route, task, input) {
  const body = {
    messages: buildMessages(task, input),
    stream: false,
    temperature: task === 'grade_short_answer' ? 0 : 0.2,
    max_tokens: maxOutputTokens(task),
  };
  if (route.structuredOutputs) body.response_format = workersAiResponseFormat(task);
  const started = Date.now();
  let timer;
  try {
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new ProviderError(
        'provider_timeout', 'The AI route timed out.', 502, true,
      )), route.timeoutMs);
    });
    const payload = await Promise.race([env.AI.run(route.model, body), timeout]);
    const normalized = normalizedProviderResult(payload, task);
    return {
      result: normalized.result,
      latencyMs: Math.max(0, Date.now() - started),
      outputChars: normalized.raw.length,
      usage: payload && payload.usage && typeof payload.usage === 'object' ? {
        prompt_tokens: Number(payload.usage.prompt_tokens) || 0,
        completion_tokens: Number(payload.usage.completion_tokens) || 0,
      } : { prompt_tokens: 0, completion_tokens: 0 },
    };
  } catch (error) {
    if (error instanceof ProviderError) throw error;
    throw new ProviderError('provider_unavailable', 'The AI route did not complete the request.', 502, true);
  } finally {
    clearTimeout(timer);
  }
}

export async function callProvider(fetchImpl, env, route, task, input) {
  if (route.provider === 'workers_ai') return callWorkersAi(env, route, task, input);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), route.timeoutMs);
  const body = {
    model: route.model,
    messages: buildMessages(task, input),
    stream: false,
    temperature: task === 'grade_short_answer' ? 0 : 0.2,
    max_tokens: maxOutputTokens(task),
  };
  if (route.structuredOutputs) body.response_format = responseFormat(task);
  if (route.provider === 'openrouter') {
    body.provider = {
      allow_fallbacks: false,
      require_parameters: route.structuredOutputs,
      data_collection: 'deny',
    };
    if (task === 'web_enrichment') {
      body.tools = [{
        type: 'openrouter:web_search',
        parameters: {
          max_results: 3,
          max_total_results: 3,
          max_uses: 1,
          search_context_size: 'low',
        },
      }];
      body.max_tool_calls = 1;
    }
  }
  let response;
  let payloadText = '';
  const started = Date.now();
  try {
    response = await fetchImpl(route.endpoint, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env[route.secretEnv]}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...(route.provider === 'openrouter' ? {
          'HTTP-Referer': 'https://lecturepack.app',
          'X-Title': 'LecturePack Study',
        } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    payloadText = await readBoundedResponseText(response, 16 * 1024 * 1024);
  } catch (error) {
    if (error instanceof ProviderError) throw error;
    const timeout = error && error.name === 'AbortError';
    throw new ProviderError(timeout ? 'provider_timeout' : 'provider_network', timeout ? 'The AI route timed out.' : 'The AI route could not be reached.', 502, true);
  } finally {
    clearTimeout(timer);
  }
  let payload = null;
  try { payload = JSON.parse(payloadText); } catch (_) { /* normalized below */ }
  if (!response.ok) {
    const code = response.status === 429 ? 'provider_rate_limited' : response.status >= 500 ? 'provider_unavailable' : 'provider_rejected';
    // A provider-side 4xx can mean a retired model, unsupported parameter, or
    // invalid route credential. The desktop input has already been validated,
    // so a rejection is route-specific and must not suppress the configured
    // fallback providers.
    throw new ProviderError(code, 'The AI route did not complete the request.', response.status, true);
  }
  const normalized = normalizedProviderResult(payload, task);
  return {
    result: normalized.result,
    latencyMs: Math.max(0, Date.now() - started),
    outputChars: normalized.raw.length,
    usage: payload && payload.usage && typeof payload.usage === 'object' ? {
      prompt_tokens: Number(payload.usage.prompt_tokens) || 0,
      completion_tokens: Number(payload.usage.completion_tokens) || 0,
    } : { prompt_tokens: 0, completion_tokens: 0 },
  };
}
