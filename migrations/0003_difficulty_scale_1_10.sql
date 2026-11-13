-- =============================================================================
-- Migration 0003 — difficulty scale 1–10 (was 1–5)
-- =============================================================================
-- Two steps per JLPT level for the Japanese track (1 = first lessons,
-- 2 = N5, 3–4 = N4, 5–6 = N3, 7–8 = N2, 9–10 = N1). Existing rows are not
-- rescaled: the demo exercises were removed and content is re-imported on
-- the new scale. Idempotent: safe to re-run.
-- Usage: psql -d <db> -U <user> -f migrations/0003_difficulty_scale_1_10.sql
--
-- Not needed for a fresh DB: postgresql/schema.sql already includes it.
-- =============================================================================

ALTER TABLE phrases DROP CONSTRAINT IF EXISTS phrases_difficulty_check;   -- 1–5, auto-named
ALTER TABLE phrases DROP CONSTRAINT IF EXISTS chk_phrases_difficulty;
ALTER TABLE phrases ADD CONSTRAINT chk_phrases_difficulty CHECK (difficulty BETWEEN 1 AND 10);
