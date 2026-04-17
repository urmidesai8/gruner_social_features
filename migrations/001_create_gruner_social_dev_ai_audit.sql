-- AI feature audit log (PostgreSQL)
-- Requires: pgcrypto for gen_random_uuid()

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS gruner_social_dev_ai_audit (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    http_method TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    model_name TEXT NULL,
    request_payload JSONB NULL,
    response_payload JSONB NULL,
    status_code INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    guardrail_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    guardrail_action TEXT NULL,
    error_message TEXT NULL,
    latency_ms INTEGER NULL,
    client_ip INET NULL,
    user_agent TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT gruner_social_dev_ai_audit_status_code_check
        CHECK (status_code >= 100 AND status_code <= 599)
);

CREATE INDEX IF NOT EXISTS idx_gruner_social_dev_ai_audit_created_at
    ON gruner_social_dev_ai_audit (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_gruner_social_dev_ai_audit_user_created
    ON gruner_social_dev_ai_audit (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_gruner_social_dev_ai_audit_endpoint_created
    ON gruner_social_dev_ai_audit (endpoint, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_gruner_social_dev_ai_audit_user_feature_created
    ON gruner_social_dev_ai_audit (user_id, feature_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_gruner_social_dev_ai_audit_failures
    ON gruner_social_dev_ai_audit (created_at DESC)
    WHERE success = FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_gruner_social_dev_ai_audit_request_id
    ON gruner_social_dev_ai_audit (request_id);
