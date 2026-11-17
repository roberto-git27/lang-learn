-- =============================================================================
-- Migration 0007 — hand-made reading overrides (Phase 9)
-- =============================================================================
-- `reading_overrides`: a word whose computed reading is wrong (五本 → ごほん)
-- and the reading to use instead, everywhere in the track: furigana, romaji
-- of romaji_input exercises. Adding or removing one recomputes the stored
-- annotations of the exercises that contain the word. Idempotent.
-- Usage: psql -d <db> -U <user> -f migrations/0007_reading_overrides.sql
--
-- Not needed for a fresh DB: postgresql/schema.sql already includes it.
-- =============================================================================

CREATE TABLE IF NOT EXISTS reading_overrides (
    id          SERIAL PRIMARY KEY,
    track_id    INTEGER      NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    surface     VARCHAR(32)  NOT NULL,     -- the word as written, with kanji
    reading     VARCHAR(64)  NOT NULL,     -- its reading (hiragana for Japanese)
    user_id     INTEGER      REFERENCES users(id) ON DELETE SET NULL,   -- who added it
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_reading_overrides UNIQUE (track_id, surface)
);
