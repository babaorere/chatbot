-- ============================================================================
-- Migration 001: Extend tenants with business profile fields
-- ============================================================================
-- Adds email, phone, address, city, website, logo_url, business_hours
-- to the tenants table for tenant self-management.
-- ============================================================================

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone VARCHAR(50);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS business_hours JSONB DEFAULT '{}';

-- Index for email lookups
CREATE INDEX IF NOT EXISTS idx_tenants_email ON tenants(email) WHERE email IS NOT NULL;
