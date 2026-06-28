-- ============================================================================
-- Migration 002: Create knowledge_base table (RAG per tenant)
-- ============================================================================
-- PostgreSQL Full-Text Search (FTS) with Spanish language support.
-- pgvector column reserved for future semantic search.
-- RLS enabled for tenant isolation.
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;

-- Immutable unaccent function for index compatibility
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$
    SELECT public.unaccent('public.unaccent', $1)
$$;

-- Knowledge base table
CREATE TABLE IF NOT EXISTS knowledge_base (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category        VARCHAR(100) NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    embedding       double precision[],
    search_vector   tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('spanish', coalesce(immutable_unaccent(title), '')), 'A') ||
        setweight(to_tsvector('spanish', coalesce(immutable_unaccent(content), '')), 'B') ||
        setweight(to_tsvector('spanish', coalesce(immutable_unaccent(category), '')), 'C')
    ) STORED,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_kb_tenant ON knowledge_base(tenant_id);
CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_base(tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_kb_active ON knowledge_base(tenant_id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_kb_search_vector ON knowledge_base USING GIN(search_vector);

-- pgvector index (reserved for future use)
-- Requires pgvector extension installed in production
-- CREATE INDEX IF NOT EXISTS idx_kb_embedding ON knowledge_base USING ivfflat(embedding vector_cosine_ops) WITH(lists = 100);

-- RLS for tenant isolation
ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_kb ON knowledge_base;
CREATE POLICY tenant_isolation_kb ON knowledge_base
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Drop policy for superuser access (admin operations)
DROP POLICY IF EXISTS admin_access_kb ON knowledge_base;
CREATE POLICY admin_access_kb ON knowledge_base
    USING (true);
