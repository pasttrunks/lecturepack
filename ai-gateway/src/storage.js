function db(env) {
  if (!env || !env.DB || typeof env.DB.prepare !== 'function') throw new Error('D1 binding DB is required');
  return env.DB;
}

export async function upsertInstallation(env, record) {
  await db(env).prepare(
    'INSERT INTO installations (installation_id, created_at, last_seen_at, app_version, status) VALUES (?, ?, ?, ?, ?) '
      + 'ON CONFLICT(installation_id) DO UPDATE SET last_seen_at = excluded.last_seen_at, app_version = excluded.app_version',
  ).bind(record.installationId, record.now, record.now, record.appVersion, 'active').run();
}

export async function getInstallation(env, installationId) {
  return db(env).prepare(
    'SELECT installation_id, app_version, status FROM installations WHERE installation_id = ?',
  ).bind(installationId).first();
}

export async function touchInstallation(env, installationId, appVersion, now) {
  await db(env).prepare(
    'UPDATE installations SET last_seen_at = ?, app_version = ? WHERE installation_id = ?',
  ).bind(now, appVersion, installationId).run();
}

export async function countRecentUsage(env, installationId, since) {
  const row = await db(env).prepare(
    'SELECT COUNT(*) AS count FROM usage_events WHERE installation_id = ? AND created_at >= ? AND attempt_number = 1',
  ).bind(installationId, since).first();
  return Number(row && row.count) || 0;
}

export async function recordUsage(env, event) {
  await db(env).prepare(
    'INSERT INTO usage_events (id, request_id, installation_id, task, route_id, provider, model, success, result, failure_code, retryable, attempt_number, status_code, latency_ms, input_tokens, output_tokens, input_chars, output_chars, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
  ).bind(
    event.id, event.requestId, event.installationId, event.task, event.routeId,
    event.provider, event.model, event.success ? 1 : 0, event.result,
    event.failureCode, event.retryable ? 1 : 0, event.attemptNumber,
    event.statusCode, event.latencyMs, event.inputTokens, event.outputTokens,
    event.inputChars, event.outputChars, event.createdAt,
  ).run();
}

export async function recordLimitEvent(env, event) {
  await db(env).prepare(
    'INSERT INTO limit_events (id, installation_id, network_hash, kind, created_at) VALUES (?, ?, ?, ?, ?)',
  ).bind(event.id, event.installationId, event.networkHash, event.kind, event.createdAt).run();
}

export async function countRecentLimits(env, installationId, since) {
  const row = await db(env).prepare(
    'SELECT COUNT(*) AS count FROM limit_events WHERE installation_id = ? AND created_at >= ?',
  ).bind(installationId, since).first();
  return Number(row && row.count) || 0;
}

export async function recordProviderHealth(env, routeId, success, code, now) {
  if (success) {
    await db(env).prepare(
      'INSERT INTO provider_health (route_id, consecutive_failures, last_error_code, last_success_at) VALUES (?, 0, ?, ?) '
        + 'ON CONFLICT(route_id) DO UPDATE SET consecutive_failures = 0, last_error_code = ?, last_success_at = ?',
    ).bind(routeId, '', now, '', now).run();
    return;
  }
  await db(env).prepare(
    'INSERT INTO provider_health (route_id, consecutive_failures, last_error_code, last_failure_at) VALUES (?, 1, ?, ?) '
      + 'ON CONFLICT(route_id) DO UPDATE SET consecutive_failures = consecutive_failures + 1, last_error_code = ?, last_failure_at = ?',
  ).bind(routeId, code, now, code, now).run();
}

export async function claimAlertWindow(env, alertKey, now, cooldownSeconds) {
  const existing = await db(env).prepare(
    'SELECT last_sent_at FROM alert_state WHERE alert_key = ?',
  ).bind(alertKey).first();
  if (existing && Number(existing.last_sent_at) > now - cooldownSeconds * 1000) return false;
  await db(env).prepare(
    'INSERT INTO alert_state (alert_key, last_sent_at) VALUES (?, ?) '
      + 'ON CONFLICT(alert_key) DO UPDATE SET last_sent_at = excluded.last_sent_at',
  ).bind(alertKey, now).run();
  return true;
}

export async function cleanupTelemetry(env, before) {
  await db(env).batch([
    db(env).prepare('DELETE FROM usage_events WHERE created_at < ?').bind(before),
    db(env).prepare('DELETE FROM limit_events WHERE created_at < ?').bind(before),
  ]);
}

export const storage = {
  upsertInstallation,
  getInstallation,
  touchInstallation,
  countRecentUsage,
  recordUsage,
  recordLimitEvent,
  countRecentLimits,
  recordProviderHealth,
  claimAlertWindow,
  cleanupTelemetry,
};
