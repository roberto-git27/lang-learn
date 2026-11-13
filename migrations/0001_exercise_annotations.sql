-- =============================================================================
-- Migration 0001 — exercises.annotations (Phase 7: furigana)
-- =============================================================================
-- Derived reading aids (e.g. furigana per display field) computed by the
-- track when an exercise is created. Idempotent: safe to re-run.
-- Usage: psql -d <db> -U <user> -f migrations/0001_exercise_annotations.sql
--
-- Not needed for a fresh DB: postgresql/schema.sql already includes it.
-- Exercises created before this migration get '{}' (no furigana).
-- =============================================================================

ALTER TABLE exercises
    ADD COLUMN IF NOT EXISTS annotations JSONB NOT NULL DEFAULT '{}'::jsonb;
