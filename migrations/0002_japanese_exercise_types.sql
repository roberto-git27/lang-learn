-- =============================================================================
-- Migration 0002 — Japanese exercise types (Phase 8)
-- =============================================================================
-- kanji_reading, kanji_writing (option-based) and romaji_input (typed, Latin
-- script), enabled on the 'ja' track. Idempotent: safe to re-run.
-- Usage: psql -d <db> -U <user> -f migrations/0002_japanese_exercise_types.sql
--
-- Not needed for a fresh DB: postgresql/schema.sql already includes it.
-- =============================================================================

INSERT INTO exercise_types (code, name) VALUES
    ('kanji_reading', 'Kanji reading'),
    ('kanji_writing', 'Kanji writing'),
    ('romaji_input',  'Romaji input')
ON CONFLICT (code) DO NOTHING;

INSERT INTO track_exercise_types (track_id, exercise_type_id, is_typed_input)
SELECT tr.id, et.id, et.code = 'romaji_input'
FROM tracks tr, exercise_types et
WHERE tr.code = 'ja' AND et.code IN ('kanji_reading', 'kanji_writing', 'romaji_input')
ON CONFLICT DO NOTHING;
