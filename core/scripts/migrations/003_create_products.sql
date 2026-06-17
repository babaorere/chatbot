-- ============================================================================
-- Migration 003: Create products table (tenant catalog)
-- ============================================================================
-- Each tenant manages their own product catalog.
-- RLS enabled for tenant isolation.
-- ============================================================================

CREATE TABLE IF NOT EXISTS products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    price           NUMERIC(10, 2),
    stock           INTEGER DEFAULT 0,
    category        VARCHAR(100),
    is_available    BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_products_available ON products(tenant_id) WHERE is_available = true;
CREATE INDEX IF NOT EXISTS idx_products_name ON products(tenant_id, name);

-- RLS for tenant isolation
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_products ON products;
CREATE POLICY tenant_isolation_products ON products
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

DROP POLICY IF EXISTS admin_access_products ON products;
CREATE POLICY admin_access_products ON products
    USING (true);
