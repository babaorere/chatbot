-- ============================================================================
-- Migration 004: Create system_settings table (admin global config)
-- ============================================================================
-- Key-value store for system-wide configuration.
-- No RLS needed — admin-only table.
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_settings (
    key             VARCHAR(100) PRIMARY KEY,
    value           JSONB NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default settings
INSERT INTO system_settings (key, value, description)
VALUES
    ('cors_allow_origins', '["*"]', 'CORS allowed origins'),
    ('cors_allow_methods', '["*"]', 'CORS allowed HTTP methods'),
    ('cors_allow_headers', '["*"]', 'CORS allowed request headers'),
    ('log_level', '"INFO"', 'Application log level (DEBUG, INFO, WARNING, ERROR)'),
    ('db_echo', 'false', 'SQLAlchemy query logging'),
    ('app_env', '"development"', 'Application environment (development, production)'),
    ('default_model', '"openrouter/nvidia/nemotron-3-super-120b-a12b:free"', 'Default LLM model for new tenants'),
    ('default_model_display', '"nemotron-3-super-120b:free"', 'Human-readable default model name'),
    ('pagination_limit', '50', 'Default pagination limit for list endpoints'),
    ('request_id_length', '8', 'Length of truncated UUID for request IDs'),
    ('rls_tables', '["users", "conversations", "messages", "knowledge_base", "products"]', 'Tables with RLS policies'),
    ('exclude_paths', '["/health", "/docs", "/openapi.json", "/redoc"]', 'Paths excluded from tenant resolution')
ON CONFLICT (key) DO NOTHING;
