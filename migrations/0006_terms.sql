-- =============================================================================
-- Migration 0006 — vocabulary: terms and the exercises that use them (D-24)
-- =============================================================================
-- `terms`: one row per (lemma, reading) per track; `exercise_terms` links an
-- exercise to the terms it is about (focus) or contains, same track enforced
-- by composite foreign keys. Studio jobs can now also be 'terms' extractions.
-- Existing exercises are linked by the app ("Link existing exercises" in the
-- Studio, POST /terms/sync). Idempotent: safe to re-run.
-- Usage: psql -d <db> -U <user> -f migrations/0006_terms.sql
--
-- Not needed for a fresh DB: postgresql/schema.sql already includes it.
-- =============================================================================

-- Added only when missing: once exercise_terms exists it depends on it.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_exercises_id_track') THEN
        ALTER TABLE exercises ADD CONSTRAINT uq_exercises_id_track UNIQUE (id, track_id);
    END IF;
END $$;

ALTER TABLE ingest_jobs DROP CONSTRAINT IF EXISTS ingest_jobs_kind_check;
ALTER TABLE ingest_jobs ADD CONSTRAINT ingest_jobs_kind_check CHECK (kind IN ('import', 'generate', 'terms'));

CREATE TABLE IF NOT EXISTS terms (
    id              SERIAL PRIMARY KEY,
    track_id        INTEGER      NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    lemma           VARCHAR(64)  NOT NULL,
    reading         VARCHAR(128) NOT NULL,
    written         VARCHAR(64)  NOT NULL,
    pos             VARCHAR(16)  NOT NULL,
    level           SMALLINT     NOT NULL CHECK (level BETWEEN 1 AND 10),
    meaning         VARCHAR(255),
    meaning_source  VARCHAR(8)   CHECK (meaning_source IN ('ai', 'human')),
    example         TEXT,
    ingest_job_id   INTEGER      REFERENCES ingest_jobs(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_terms_lemma UNIQUE (track_id, lemma, reading),
    CONSTRAINT uq_terms_id_track UNIQUE (id, track_id)
);

CREATE TABLE IF NOT EXISTS exercise_terms (
    exercise_id  INTEGER     NOT NULL,
    term_id      INTEGER     NOT NULL,
    track_id     INTEGER     NOT NULL,
    role         VARCHAR(8)  NOT NULL CHECK (role IN ('focus', 'contains')),
    PRIMARY KEY (exercise_id, term_id),
    FOREIGN KEY (exercise_id, track_id) REFERENCES exercises(id, track_id) ON DELETE CASCADE,
    FOREIGN KEY (term_id, track_id)     REFERENCES terms(id, track_id)     ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_exercise_terms_term ON exercise_terms (term_id);
