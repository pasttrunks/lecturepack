import { hashIdentifier, issueInstallationToken, validInstallationId, verifyInstallationToken } from './auth.js';
import { DASHBOARD_HTML } from './dashboard_html.js';
import {
  callProvider, prioritizeHealthyRoutes, ProviderError, resolveRoutes,
} from './providers.js';
import { storage as defaultStorage } from './storage.js';
import { isTaskType, TASK_TYPES, validateTaskInput } from './tasks.js';

const encoder = new TextEncoder();
const REQUEST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/;

function jsonResponse(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      ...extraHeaders,
    },
  });
}

function publicError(code, message, retryable, requestId = '', diagnostics = {}) {
  return {
    ok: false,
    error: { code, message, retryable: retryable === true },
    diagnostics: {
      request_id: requestId,
      timestamp: new Date().toISOString(),
      task: safeAlertText(diagnostics.task || ''),
      attempted_routes: Array.isArray(diagnostics.attempted_routes) ? diagnostics.attempted_routes : [],
      provider_codes: Array.isArray(diagnostics.provider_codes) ? diagnostics.provider_codes : [],
      provider_status: Array.isArray(diagnostics.provider_status) ? diagnostics.provider_status : [],
      retry_count: Math.max(0, Number(diagnostics.retry_count) || 0),
      app_version: safeAlertText(diagnostics.app_version || ''),
      last_successful_stage: String(diagnostics.last_successful_stage || ''),
    },
  };
}

function numberSetting(value, fallback, minimum, maximum) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(minimum, Math.min(maximum, parsed)) : fallback;
}

function semverTuple(value) {
  const match = String(value || '').match(/^(\d+)\.(\d+)\.(\d+)/);
  return match ? match.slice(1).map(Number) : [0, 0, 0];
}

function versionAtLeast(value, minimum) {
  const left = semverTuple(value);
  const right = semverTuple(minimum);
  for (let index = 0; index < 3; index += 1) {
    if (left[index] !== right[index]) return left[index] > right[index];
  }
  return true;
}

async function readJsonBody(request, maxBytes) {
  const declared = Number(request.headers.get('content-length') || 0);
  if (declared > maxBytes) throw Object.assign(new Error('request is too large'), { status: 413, code: 'request_too_large' });
  const text = await request.text();
  if (encoder.encode(text).byteLength > maxBytes) throw Object.assign(new Error('request is too large'), { status: 413, code: 'request_too_large' });
  try {
    return { value: JSON.parse(text || '{}'), chars: text.length };
  } catch (_) {
    throw Object.assign(new Error('request body must be valid JSON'), { status: 400, code: 'invalid_json' });
  }
}

function bearerToken(request) {
  const match = String(request.headers.get('authorization') || '').match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : '';
}

function clientVersion(request, body) {
  return String((body && body.client_context && body.client_context.app_version)
    || request.headers.get('x-lecturepack-version') || '0.0.0').slice(0, 40);
}

function corsHeaders(request, env) {
  const origin = String(request.headers.get('origin') || '');
  if (!origin) return {};
  const allowed = String(env.ALLOWED_ORIGINS || '').split(',').map((item) => item.trim()).filter(Boolean);
  const isAllowed = !allowed.length || allowed.includes('*') || allowed.includes(origin) || origin === 'null';
  if (!isAllowed) return {};
  return {
    'Access-Control-Allow-Origin': origin === 'null' ? '*' : origin,
    Vary: 'Origin',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type, X-LecturePack-Version, X-Admin-Key',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  };
}

// Compare a presented credential against the real one without leaking how
// much of it matched. A plain === returns on the first differing byte, so
// response time is a slow oracle for guessing the key one character at a
// time. Length is compared first because it is not itself a secret.
function timingSafeEqual(presented, expected) {
  const a = String(presented ?? '');
  const b = String(expected ?? '');
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function checkAdminAuth(request, env) {
  if (!env.ADMIN_API_KEY) {
    return { ok: false, status: 503, code: 'admin_not_configured', message: 'ADMIN_API_KEY is not configured on this gateway.' };
  }
  const headerKey = request.headers.get('x-admin-key');
  const bearer = bearerToken(request);
  if ((headerKey && timingSafeEqual(headerKey, env.ADMIN_API_KEY))
      || (bearer && timingSafeEqual(bearer, env.ADMIN_API_KEY))) {
    return { ok: true };
  }
  return { ok: false, status: 401, code: 'unauthorized_admin', message: 'Invalid or missing admin key.' };
}

async function fetchOpenRouterBalance(fetchImpl, env) {
  if (!env.OPENROUTER_API_KEY) return null;
  try {
    const res = await fetchImpl('https://openrouter.ai/api/v1/auth/key', {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
      },
    });
    if (!res.ok) return { ok: false, status: res.status };
    const data = await res.json();
    return { ok: true, data: (data && data.data) ? data.data : data };
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : 'fetch failed') };
  }
}

async function rateLimit(binding, key) {
  if (!binding || typeof binding.limit !== 'function') return true;
  try {
    const result = await binding.limit({ key });
    return !!(result && result.success);
  } catch (_) {
    return true;
  }
}

function safeAlertText(value) {
  return String(value || '').replace(/[^A-Za-z0-9_./:@ -]/g, '').slice(0, 160);
}

function diagnosticRoute(route) {
  return `${route.id}@${route.provider}:${route.model}`
    .replace(/[^A-Za-z0-9_./:@-]/g, '')
    .slice(0, 120);
}

function hasIndependentFallback(routes) {
  const failureDomains = new Set(routes.map((route) => {
    if (route.failureDomain) return String(route.failureDomain).toLowerCase();
    try { return new URL(route.endpoint).hostname.toLowerCase(); } catch (_) { return ''; }
  }).filter(Boolean));
  return routes.length >= 2 && failureDomains.size >= 2;
}

async function sendOwnerAlert(fetchImpl, env, storage, now, alert) {
  if (!env.RESEND_API_KEY || !env.ALERT_FROM_EMAIL) return false;
  const cooldown = numberSetting(env.ALERT_COOLDOWN_SECONDS, 3600, 300, 86400);
  const key = `gateway:${safeAlertText(alert.kind)}:${safeAlertText(alert.task || 'global')}`;
  if (!(await storage.claimAlertWindow(env, key, now, cooldown))) return false;
  const to = String(env.OWNER_ALERT_EMAIL || 'discordsammy2@gmail.com');
  const lines = [
    'LecturePack AI Gateway operational alert',
    `Kind: ${safeAlertText(alert.kind)}`,
    `Installation: ${safeAlertText(alert.installationId || 'n/a')}`,
    `Request: ${safeAlertText(alert.requestId || 'n/a')}`,
    `Task: ${safeAlertText(alert.task || 'n/a')}`,
    `Routes: ${(alert.routes || []).map(safeAlertText).join(', ') || 'n/a'}`,
    `Models: ${(alert.models || []).map(safeAlertText).join(', ') || 'n/a'}`,
    `Codes: ${(alert.codes || []).map(safeAlertText).join(', ') || 'n/a'}`,
    `Statuses: ${(alert.statuses || []).map(safeAlertText).join(', ') || 'n/a'}`,
    `Retries: ${Math.max(0, Number(alert.retryCount) || 0)}`,
    `Time: ${new Date(now).toISOString()}`,
    '',
    'No transcript, prompt, response, slide image, token, or provider secret is included in this alert.',
  ];
  try {
    const response = await fetchImpl('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
        'Idempotency-Key': `${key}:${Math.floor(now / (cooldown * 1000))}`.slice(0, 200),
      },
      body: JSON.stringify({
        from: env.ALERT_FROM_EMAIL,
        to: [to],
        subject: `LecturePack gateway: ${safeAlertText(alert.kind)}`,
        text: lines.join('\n'),
      }),
    });
    return response.ok;
  } catch (_) {
    return false;
  }
}

function installAllowed(env, installation) {
  if (!installation || installation.status !== 'active') return false;
  const allowlist = String(env.INSTALLATION_ALLOWLIST || '').split(',').map((item) => item.trim()).filter(Boolean);
  if (!allowlist.length) return true;
  return allowlist.includes(String(installation.installation_id || ''));
}

export function createGateway(options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const nowFn = options.now || (() => Date.now());
  const uuidFn = options.randomUUID || (() => crypto.randomUUID());
  const storage = options.storage || defaultStorage;

  async function register(request, env, cors) {
    const maxBytes = numberSetting(env.MAX_REQUEST_BYTES, 3500000, 10000, 5000000);
    const { value: body } = await readJsonBody(request, Math.min(maxBytes, 20000));
    const installationId = String(body.installation_id || '');
    const appVersion = String(body.app_version || '0.0.0').slice(0, 40);
    if (!validInstallationId(installationId)) return jsonResponse(publicError('invalid_installation', 'LecturePack could not register this installation.', false), 400, cors);
    const now = nowFn();
    const networkHash = await hashIdentifier(env.NETWORK_HASH_SECRET, request.headers.get('cf-connecting-ip') || 'unknown');
    if (!(await rateLimit(env.REGISTRATION_LIMITER, networkHash))) {
      return jsonResponse(publicError('registration_limited', 'Too many installation registrations were attempted. Try again later.', true), 429, { ...cors, 'Retry-After': '60' });
    }
    await storage.upsertInstallation(env, { installationId, appVersion, now });
    const ttlDays = numberSetting(env.TOKEN_TTL_DAYS, 90, 1, 365);
    const token = await issueInstallationToken(env.TOKEN_SIGNING_SECRET, installationId, now, ttlDays * 86400);
    return jsonResponse({
      ok: true,
      installation_token: token,
      expires_at: new Date(now + ttlDays * 86400000).toISOString(),
    }, 200, cors);
  }

  async function tasks(request, env, context, cors) {
    const now = nowFn();
    let claims;
    try {
      claims = await verifyInstallationToken(env.TOKEN_SIGNING_SECRET, bearerToken(request), now);
    } catch (error) {
      const expired = error && error.message === 'expired token';
      return jsonResponse(publicError(expired ? 'token_expired' : 'unauthorized', expired ? 'The installation token expired.' : 'This installation is not authorized.', expired), 401, cors);
    }
    const installation = await storage.getInstallation(env, claims.sid);
    if (!installAllowed(env, installation)) return jsonResponse(publicError('installation_blocked', 'This installation is not currently allowed to use Study AI.', false), 403, cors);

    const maxBytes = numberSetting(env.MAX_REQUEST_BYTES, 3500000, 10000, 5000000);
    const { value: body, chars: inputChars } = await readJsonBody(request, maxBytes);
    const requestId = String(body.request_id || '');
    const task = String(body.task || '');
    if (!REQUEST_ID_RE.test(requestId)) return jsonResponse(publicError('invalid_request_id', 'The Study request identifier is invalid.', false), 400, cors);
    if (!isTaskType(task)) return jsonResponse(publicError('unsupported_task', 'This Study task is not supported.', false, requestId), 400, cors);
    if (Object.prototype.hasOwnProperty.call(body, 'provider') || Object.prototype.hasOwnProperty.call(body, 'model') || Object.prototype.hasOwnProperty.call(body, 'route')) {
      return jsonResponse(publicError('server_routing_only', 'Provider and model selection are controlled by LecturePack.', false, requestId), 400, cors);
    }
    try { validateTaskInput(task, body.input); } catch (error) {
      return jsonResponse(publicError('invalid_task_input', String(error.message || 'The Study input is invalid.'), false, requestId), 400, cors);
    }
    const appVersion = clientVersion(request, body);
    if (env.MIN_APP_VERSION && !versionAtLeast(appVersion, env.MIN_APP_VERSION)) {
      return jsonResponse(publicError('upgrade_required', 'Update LecturePack before using Study AI.', false, requestId), 426, cors);
    }
    const networkHash = await hashIdentifier(env.NETWORK_HASH_SECRET, request.headers.get('cf-connecting-ip') || 'unknown');
    const edgeAllowed = await rateLimit(env.INSTALL_LIMITER, claims.sid)
      && await rateLimit(env.NETWORK_LIMITER, networkHash);
    const dailyLimit = numberSetting(env.DAILY_INSTALL_LIMIT, 250, 20, 5000);
    const dailyUsed = await storage.countRecentUsage(env, claims.sid, now - 86400000);
    if (!edgeAllowed || dailyUsed >= dailyLimit) {
      await storage.recordLimitEvent(env, { id: uuidFn(), installationId: claims.sid, networkHash, kind: edgeAllowed ? 'daily_install' : 'edge', createdAt: now });
      const recent = await storage.countRecentLimits(env, claims.sid, now - 3600000);
      if (recent >= 3) {
        context.waitUntil(sendOwnerAlert(fetchImpl, env, storage, now, {
          kind: 'repeated_limit', installationId: claims.sid, requestId, task,
          codes: ['usage_limited'], statuses: [429], retryCount: recent - 1,
        }));
      }
      return jsonResponse(publicError('usage_limited', 'Study AI is busy for this installation. Your lecture and Basic Study remain available; try again later.', true, requestId), 429, { ...cors, 'Retry-After': edgeAllowed ? '3600' : '60' });
    }
    const retentionDays = numberSetting(env.TELEMETRY_RETENTION_DAYS, 30, 1, 90);
    if (Math.floor(Math.random() * 100) === 0) {
      context.waitUntil(storage.cleanupTelemetry(env, nowFn() - retentionDays * 86400000));
    }

    let routes;
    try { routes = resolveRoutes(env, task); } catch (error) {
      context.waitUntil(sendOwnerAlert(fetchImpl, env, storage, now, {
        kind: 'route_configuration', installationId: claims.sid, requestId, task,
        codes: [error.code || 'gateway_configuration'], statuses: [error.status || 503],
        retryCount: 0,
      }));
      return jsonResponse(publicError(error.code || 'gateway_configuration', error.message, false, requestId), error.status || 503, cors);
    }
    if (!hasIndependentFallback(routes)) {
      const configuredRoutes = routes.map(diagnosticRoute);
      context.waitUntil(sendOwnerAlert(fetchImpl, env, storage, now, {
        kind: 'route_configuration', installationId: claims.sid, requestId, task,
        routes: configuredRoutes, models: routes.map((route) => route.model),
        codes: ['insufficient_ai_routes'], statuses: [503], retryCount: 0,
      }));
      return jsonResponse(publicError(
        'insufficient_ai_routes',
        'Study AI is temporarily unavailable because an independent fallback provider is not configured.',
        true,
        requestId,
        { task, attempted_routes: configuredRoutes, app_version: appVersion },
      ), 503, cors);
    }
    if (typeof storage.getProviderHealth === 'function') {
      try {
        const health = await storage.getProviderHealth(env, routes.map((route) => route.id));
        routes = prioritizeHealthyRoutes(routes, health, now, {
          failureThreshold: numberSetting(env.ROUTE_FAILURE_THRESHOLD, 2, 1, 10),
          cooldownMs: numberSetting(env.ROUTE_FAILURE_COOLDOWN_SECONDS, 300, 30, 3600) * 1000,
        });
      } catch (_) {
        // Provider-health metadata must never make the Study request fail.
        // The measured server-controlled route order remains the safe default.
      }
    }
    const attempted = [];
    const codes = [];
    const statuses = [];
    const models = [];
    for (const route of routes) {
      attempted.push(diagnosticRoute(route));
      models.push(route.model);
      const started = nowFn();
      try {
        const response = await callProvider(fetchImpl, env, route, task, body.input);
        await storage.recordProviderHealth(env, route.id, true, '', nowFn());
        await storage.recordUsage(env, {
          id: uuidFn(), requestId, installationId: claims.sid, task, routeId: route.id,
          provider: route.provider, model: route.model, success: true, result: 'success',
          failureCode: '', retryable: false, attemptNumber: attempted.length,
          statusCode: 200, latencyMs: response.latencyMs,
          inputTokens: response.usage.prompt_tokens, outputTokens: response.usage.completion_tokens,
          inputChars, outputChars: response.outputChars, createdAt: nowFn(),
        });
        await storage.touchInstallation(env, claims.sid, appVersion, nowFn());
        return jsonResponse({
          ok: true,
          request_id: requestId,
          task,
          result: response.result,
          diagnostics: {
            // Successful requests do not expose provider/model identifiers to
            // the desktop. Full route descriptors are returned only in copied
            // technical diagnostics after a failed chain.
            request_id: requestId, task, attempted_routes: [],
            provider_codes: codes, provider_status: statuses,
            retry_count: Math.max(0, attempted.length - 1), app_version: appVersion,
            timestamp: new Date(nowFn()).toISOString(),
          },
        }, 200, cors);
      } catch (error) {
        const normalized = error instanceof ProviderError
          ? error : new ProviderError('provider_error', 'The AI route failed.', 502, true);
        codes.push(normalized.code);
        statuses.push(normalized.status);
        await storage.recordProviderHealth(env, route.id, false, normalized.code, nowFn());
        await storage.recordUsage(env, {
          id: uuidFn(), requestId, installationId: claims.sid, task, routeId: route.id,
          provider: route.provider, model: route.model, success: false, result: 'failure',
          failureCode: normalized.code, retryable: normalized.retryable,
          attemptNumber: attempted.length, statusCode: normalized.status,
          latencyMs: Math.max(0, nowFn() - started), inputTokens: 0, outputTokens: 0,
          inputChars, outputChars: 0, createdAt: nowFn(),
        });
        if (!normalized.retryable) break;
      }
    }
    context.waitUntil(sendOwnerAlert(fetchImpl, env, storage, nowFn(), {
      kind: 'provider_chain_failed', installationId: claims.sid, requestId, task,
      routes: attempted, models, codes, statuses,
      retryCount: Math.max(0, attempted.length - 1),
    }));
    return jsonResponse(publicError(
      'ai_routes_failed',
      'Study AI could not complete this request. Retry, copy diagnostics, or use Basic Study.',
      true,
      requestId,
      {
        task, attempted_routes: attempted, provider_codes: codes,
        provider_status: statuses, retry_count: Math.max(0, attempted.length - 1),
        app_version: appVersion,
      },
    ), 503, cors);
  }

  async function adminStats(request, env, cors) {
    const auth = checkAdminAuth(request, env);
    if (!auth.ok) return jsonResponse(publicError(auth.code, auth.message, false), auth.status, cors);
    const url = new URL(request.url);
    const windowParam = String(url.searchParams.get('window') || '24h').toLowerCase();
    const now = nowFn();
    let since = now - 86400000;
    if (windowParam === '7d') since = now - 7 * 86400000;
    else if (windowParam === '30d') since = now - 30 * 86400000;
    else if (windowParam === 'all') since = 0;
    else if (Number(windowParam)) since = Math.max(0, now - Number(windowParam));

    const [summary, models, tasksList, health, recentEvents, openrouterBalance] = await Promise.all([
      storage.getAdminSummary(env, since),
      storage.getAdminModelStats(env, since),
      storage.getAdminTaskStats(env, since),
      storage.getAllProviderHealth(env),
      storage.getAdminRecentEvents(env, 50),
      fetchOpenRouterBalance(fetchImpl, env),
    ]);

    return jsonResponse({
      ok: true,
      service: 'lecturepack-ai-gateway',
      window: windowParam,
      since: new Date(since).toISOString(),
      timestamp: new Date(now).toISOString(),
      summary,
      models,
      tasks: tasksList,
      health,
      recent_events: recentEvents,
      openrouter_balance: openrouterBalance,
    }, 200, cors);
  }

  function adminDashboard(request, env, cors) {
    return new Response(DASHBOARD_HTML, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-cache',
        'X-Content-Type-Options': 'nosniff',
        ...cors,
      },
    });
  }

  return async function handle(request, env, context = { waitUntil() {} }) {
    const cors = corsHeaders(request, env);
    if (request.method === 'OPTIONS') {
      if (request.headers.get('origin') && !cors['Access-Control-Allow-Origin']) return jsonResponse(publicError('origin_not_allowed', 'This browser origin is not allowed.', false), 403);
      return new Response(null, { status: 204, headers: cors });
    }
    const url = new URL(request.url);
    try {
      if (request.method === 'GET' && url.pathname === '/v1/health') {
        const routeCoverage = TASK_TYPES.filter((task) => {
          try { return hasIndependentFallback(resolveRoutes(env, task)); } catch (_) { return false; }
        }).length;
        return jsonResponse({
          ok: true,
          service: 'lecturepack-ai-gateway',
          configured: !!(
            env.DB && env.TOKEN_SIGNING_SECRET && env.NETWORK_HASH_SECRET
            && routeCoverage === TASK_TYPES.length
          ),
          configured_tasks: routeCoverage,
          required_tasks: TASK_TYPES.length,
        }, 200, cors);
      }
      if (request.method === 'GET' && url.pathname === '/v1/admin/stats') return await adminStats(request, env, cors);
      if (request.method === 'GET' && (url.pathname === '/v1/admin/dashboard' || url.pathname === '/admin' || url.pathname === '/admin/')) return adminDashboard(request, env, cors);
      if (request.method === 'POST' && url.pathname === '/v1/installations/register') return await register(request, env, cors);
      if (request.method === 'POST' && url.pathname === '/v1/tasks') return await tasks(request, env, context, cors);
      return jsonResponse(publicError('not_found', 'Gateway endpoint not found.', false), 404, cors);
    } catch (error) {
      const status = Number(error && error.status) || 500;
      const code = String(error && error.code || 'gateway_error');
      const message = status >= 500 ? 'The Study gateway could not complete the request.' : String(error.message || 'The request is invalid.');
      return jsonResponse(publicError(code, message, status >= 500), status, cors);
    }
  };
}

const gateway = createGateway();

export default {
  fetch(request, env, context) {
    return gateway(request, env, context);
  },
};
