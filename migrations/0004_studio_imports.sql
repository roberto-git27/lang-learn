-- =============================================================================
-- Migration 0004 — Studio imports (Phase 9)
-- =============================================================================
-- `ingest_jobs` keeps every imported .md verbatim; `exercises.ingest_job_id`
-- links each imported exercise to it. Exercise origins are now 'ai_generated'
-- or 'human_import' (the quick manual form was replaced by the Studio import:
-- old 'manual' rows become 'human_import'). Idempotent: safe to re-run.
-- Usage: psql -d <db> -U <user> -f migrations/0004_studio_imports.sql
--
-- Not needed for a fresh DB: postgresql/schema.sql already includes it.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id               SERIAL PRIMARY KEY,
    track_id         INTEGER      NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    user_id          INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    source_name      VARCHAR(255) NOT NULL,
    source_text      TEXT         NOT NULL,
    created_count    INTEGER      NOT NULL DEFAULT 0,
    duplicate_count  INTEGER      NOT NULL DEFAULT 0,
    error_count      INTEGER      NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ingest_jobs_track ON ingest_jobs (track_id, created_at DESC);

ALTER TABLE exercises ADD COLUMN IF NOT EXISTS ingest_job_id INTEGER;
ALTER TABLE exercises DROP CONSTRAINT IF EXISTS fk_exercises_ingest_job;
ALTER TABLE exercises ADD CONSTRAINT fk_exercises_ingest_job
    FOREIGN KEY (ingest_job_id) REFERENCES ingest_jobs(id) ON DELETE SET NULL;

ALTER TABLE exercises DROP CONSTRAINT IF EXISTS exercises_origin_check;   -- auto-named, v2 schema
ALTER TABLE exercises DROP CONSTRAINT IF EXISTS chk_exercises_origin;
UPDATE exercises SET origin = 'human_import' WHERE origin = 'manual';
ALTER TABLE exercises ADD CONSTRAINT chk_exercises_origin CHECK (origin IN ('ai_generated', 'human_import'));
