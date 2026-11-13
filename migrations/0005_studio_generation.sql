-- =============================================================================
-- Migration 0005 — Studio generation drafts (Phase 9b)
-- =============================================================================
-- `ingest_jobs` now holds AI generations too: `kind` (import | generate),
-- `status` (draft | saved | discarded), the draft `items`, and the cost of
-- the job (model, LLM calls, tokens, duration). Existing rows are imports,
-- already saved. Idempotent: safe to re-run.
-- Usage: psql -d <db> -U <user> -f migrations/0005_studio_generation.sql
--
-- Not needed for a fresh DB: postgresql/schema.sql already includes it.
-- =============================================================================

ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS kind          VARCHAR(16) NOT NULL DEFAULT 'import';
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS status        VARCHAR(16) NOT NULL DEFAULT 'saved';
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS items         JSONB       NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS model         VARCHAR(64);
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS llm_calls     INTEGER     NOT NULL DEFAULT 0;
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS input_tokens  INTEGER     NOT NULL DEFAULT 0;
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS output_tokens INTEGER     NOT NULL DEFAULT 0;
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS duration_ms   INTEGER     NOT NULL DEFAULT 0;

ALTER TABLE ingest_jobs DROP CONSTRAINT IF EXISTS ingest_jobs_kind_check;
ALTER TABLE ingest_jobs ADD CONSTRAINT ingest_jobs_kind_check CHECK (kind IN ('import', 'generate'));
ALTER TABLE ingest_jobs DROP CONSTRAINT IF EXISTS ingest_jobs_status_check;
ALTER TABLE ingest_jobs ADD CONSTRAINT ingest_jobs_status_check CHECK (status IN ('draft', 'saved', 'discarded'));
