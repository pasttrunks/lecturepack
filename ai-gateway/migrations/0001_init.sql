-- Lecture content, prompts, completions, slide images, and transcript text are
-- deliberately absent from this schema. The gateway stores operational usage
-- metadata only.
CREATE TABLE IF NOT EXISTS installations (
    installation_id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    app_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    task TEXT NOT NULL,
    route_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    success INTEGER NOT NULL,
    result TEXT NOT NULL,
    failure_code TEXT NOT NULL,
    retryable INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    status_code INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    input_chars INTEGER NOT NULL,
    output_chars INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS usage_install_time
    ON usage_events (installation_id, created_at);
CREATE INDEX IF NOT EXISTS usage_task_time
    ON usage_events (task, created_at);

CREATE TABLE IF NOT EXISTS limit_events (
    id TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL,
    network_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS limits_install_time
    ON limit_events (installation_id, created_at);

CREATE TABLE IF NOT EXISTS provider_health (
    route_id TEXT PRIMARY KEY,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT NOT NULL DEFAULT '',
    last_failure_at INTEGER,
    last_success_at INTEGER
);

CREATE TABLE IF NOT EXISTS alert_state (
    alert_key TEXT PRIMARY KEY,
    last_sent_at INTEGER NOT NULL
);
