-- =============================================================================
-- LANGLEARN — PostgreSQL schema (v2: tracks + profiles)
-- =============================================================================
-- Run top to bottom: the file is already ordered by FK dependencies.
-- Tested on PostgreSQL 16+.
--
-- docker-compose applies this file automatically on the first start (empty
-- data directory). Manual use: psql -d <db> -U <user> -f schema.sql
--
-- To reset everything (WARNING: deletes all data):
--   DROP SCHEMA public CASCADE; CREATE SCHEMA public;
-- then run this file again.
--
-- A *track* is one language being studied from one base language (e.g.
-- Japanese from Italian). Every phrase, topic and exercise belongs to exactly
-- one track; composite foreign keys on (id, track_id) make it impossible to
-- link rows across tracks (e.g. a Japanese exercise on a Norwegian phrase).
-- =============================================================================


-- =============================================================================
-- 1. LANGUAGES
-- =============================================================================
CREATE TABLE languages (
    id      SERIAL PRIMARY KEY,
    code    VARCHAR(8)  NOT NULL UNIQUE,   -- 'it', 'ja', ...
    name    VARCHAR(64) NOT NULL
);


-- =============================================================================
-- 2. TRACKS (target language studied from a base language)
-- =============================================================================
CREATE TABLE tracks (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(16) NOT NULL UNIQUE,   -- 'ja'
    name                VARCHAR(64) NOT NULL,
    target_language_id  INTEGER     NOT NULL REFERENCES languages(id),
    base_language_id    INTEGER     NOT NULL REFERENCES languages(id),  -- language of explanations/translations
    enabled             BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_track_languages_differ CHECK (target_language_id <> base_language_id)
);


-- =============================================================================
-- 3. EXERCISE TYPES (global lookup) and the types each track enables
-- =============================================================================
CREATE TABLE exercise_types (
    id    SERIAL PRIMARY KEY,
    code  VARCHAR(32)  NOT NULL UNIQUE,
    name  VARCHAR(128) NOT NULL
);

CREATE TABLE track_exercise_types (
    track_id          INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    exercise_type_id  INTEGER NOT NULL REFERENCES exercise_types(id),
    is_typed_input    BOOLEAN NOT NULL DEFAULT FALSE,  -- answered by typing (vs picking an option)
    PRIMARY KEY (track_id, exercise_type_id)
);


-- =============================================================================
-- 4. PHRASES (sentence concept) and their translations
-- =============================================================================
CREATE TABLE phrases (
    id          SERIAL PRIMARY KEY,
    track_id    INTEGER     NOT NULL REFERENCES tracks(id),
    difficulty  INTEGER     NOT NULL DEFAULT 2,   -- 1 (first lessons) … 10 (advanced)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_phrases_difficulty CHECK (difficulty BETWEEN 1 AND 10),
    CONSTRAINT uq_phrases_id_track UNIQUE (id, track_id)   -- target of composite FKs
);

CREATE INDEX ix_phrases_track_difficulty ON phrases (track_id, difficulty);


CREATE TABLE phrase_translations (
    id           SERIAL PRIMARY KEY,
    phrase_id    INTEGER     NOT NULL REFERENCES phrases(id) ON DELETE CASCADE,
    language_id  INTEGER     NOT NULL REFERENCES languages(id),
    content      TEXT        NOT NULL,
    ipa          VARCHAR(255),                                  -- optional phonetic transcription
    audio_url    VARCHAR(512),                                  -- URL on S3/R2/GCS, NOT the binary file
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_phrase_language UNIQUE (phrase_id, language_id)
);

CREATE INDEX ix_translation_lang_text ON phrase_translations (language_id, content);
CREATE INDEX ix_translation_phrase    ON phrase_translations (phrase_id);


-- =============================================================================
-- 5. TOPICS (per track) and their N:N relation with phrases
-- =============================================================================
CREATE TABLE topics (
    id        SERIAL PRIMARY KEY,
    track_id  INTEGER      NOT NULL REFERENCES tracks(id),
    code      VARCHAR(64)  NOT NULL,          -- 'particle_mo', 'self_introduction'
    category  VARCHAR(32)  NOT NULL,          -- 'grammar', 'vocab', 'auto'
    name      VARCHAR(128) NOT NULL,
    CONSTRAINT uq_topics_track_code UNIQUE (track_id, code),
    CONSTRAINT uq_topics_id_track   UNIQUE (id, track_id)
);


CREATE TABLE phrase_topics (
    phrase_id  INTEGER NOT NULL,
    topic_id   INTEGER NOT NULL,
    track_id   INTEGER NOT NULL,
    PRIMARY KEY (phrase_id, topic_id),
    FOREIGN KEY (phrase_id, track_id) REFERENCES phrases(id, track_id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id, track_id)  REFERENCES topics(id, track_id)  ON DELETE CASCADE
);

CREATE INDEX ix_phrase_topics_topic ON phrase_topics (topic_id);


-- =============================================================================
-- 6. EXERCISES (type-dependent JSONB payload)
-- =============================================================================
CREATE TABLE exercises (
    id                  SERIAL PRIMARY KEY,
    track_id            INTEGER     NOT NULL,
    phrase_id           INTEGER     NOT NULL,
    exercise_type_id    INTEGER     NOT NULL,
    payload             JSONB       NOT NULL,
    annotations         JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- derived reading aids (e.g. furigana), computed by the track
    origin              VARCHAR(16) NOT NULL,                  -- who wrote it: the agent, or a human via a Studio import
    human_checked       BOOLEAN     NOT NULL DEFAULT FALSE,   -- verified by a human (reference quality)
    human_checked_at    TIMESTAMPTZ,
    human_checked_by    VARCHAR(64),                           -- display name of the reviewer profile (no auth)
    ingest_job_id       INTEGER,                               -- the Studio import it came from (FK added in section 7)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_exercises_origin CHECK (origin IN ('ai_generated', 'human_import')),
    CONSTRAINT uq_exercises_id_track UNIQUE (id, track_id),   -- target of composite FKs
    -- same track as its phrase, and a type the track enables
    FOREIGN KEY (phrase_id, track_id)        REFERENCES phrases(id, track_id) ON DELETE CASCADE,
    FOREIGN KEY (track_id, exercise_type_id) REFERENCES track_exercise_types(track_id, exercise_type_id)
);

CREATE INDEX ix_exercises_track_type    ON exercises (track_id, exercise_type_id);
CREATE INDEX ix_exercises_phrase        ON exercises (phrase_id);
CREATE INDEX ix_exercises_human_checked ON exercises (track_id, human_checked, created_at);


-- =============================================================================
-- 7. USERS (profiles — NOT authentication), the tracks they study, their imports
-- =============================================================================
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    display_name  VARCHAR(64)  NOT NULL,
    pin_hash      VARCHAR(255),              -- optional 4-digit PIN, PBKDF2-SHA256 (see user_service.py)
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_users_display_name ON users (LOWER(display_name));


CREATE TABLE user_tracks (
    user_id       INTEGER     NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    track_id      INTEGER     NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, track_id)
);


-- Studio jobs: imports (saved at once) and AI generations (a draft saved or
-- discarded later). The source .md is kept verbatim, so every exercise can be
-- traced back to the file or request it came from.
CREATE TABLE ingest_jobs (
    id               SERIAL PRIMARY KEY,
    track_id         INTEGER      NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    user_id          INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    source_name      VARCHAR(255) NOT NULL,     -- file name, or 'pasted text'
    source_text      TEXT         NOT NULL,     -- the imported .md or the generation request, verbatim
    kind             VARCHAR(16)  NOT NULL DEFAULT 'import' CHECK (kind IN ('import', 'generate', 'terms')),
    status           VARCHAR(16)  NOT NULL DEFAULT 'saved' CHECK (status IN ('draft', 'saved', 'discarded')),
    items            JSONB        NOT NULL DEFAULT '[]'::jsonb,   -- generation draft: the proposed exercises
    model            VARCHAR(64),
    llm_calls        INTEGER      NOT NULL DEFAULT 0,
    input_tokens     INTEGER      NOT NULL DEFAULT 0,
    output_tokens    INTEGER      NOT NULL DEFAULT 0,
    duration_ms      INTEGER      NOT NULL DEFAULT 0,
    created_count    INTEGER      NOT NULL DEFAULT 0,
    duplicate_count  INTEGER      NOT NULL DEFAULT 0,
    error_count      INTEGER      NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_ingest_jobs_track ON ingest_jobs (track_id, created_at DESC);

ALTER TABLE exercises ADD CONSTRAINT fk_exercises_ingest_job
    FOREIGN KEY (ingest_job_id) REFERENCES ingest_jobs(id) ON DELETE SET NULL;


-- Vocabulary: content words in dictionary form, one row per (lemma, reading)
-- per track, so the same word is never stored twice (言いました/言う, かみ/髪).
-- `level` is the lowest difficulty whose kanji gate accepts `written`.
CREATE TABLE terms (
    id              SERIAL PRIMARY KEY,
    track_id        INTEGER      NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    lemma           VARCHAR(64)  NOT NULL,     -- dictionary entry: identity, with `reading`
    reading         VARCHAR(128) NOT NULL,     -- hiragana for Japanese
    written         VARCHAR(64)  NOT NULL,     -- dictionary form as first seen in a text
    pos             VARCHAR(16)  NOT NULL,     -- noun | proper_noun | pronoun | verb | i_adjective | ...
    level           SMALLINT     NOT NULL CHECK (level BETWEEN 1 AND 10),
    meaning         VARCHAR(255),              -- in the track's base language; NULL until known
    meaning_source  VARCHAR(8)   CHECK (meaning_source IN ('ai', 'human')),
    example         TEXT,                      -- a sentence it appears in (context for its meaning)
    ingest_job_id   INTEGER      REFERENCES ingest_jobs(id) ON DELETE SET NULL,   -- the Studio job that added it
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_terms_lemma UNIQUE (track_id, lemma, reading),
    CONSTRAINT uq_terms_id_track UNIQUE (id, track_id)
);

-- Which terms an exercise is about (focus) or merely contains.
CREATE TABLE exercise_terms (
    exercise_id  INTEGER     NOT NULL,
    term_id      INTEGER     NOT NULL,
    track_id     INTEGER     NOT NULL,
    role         VARCHAR(8)  NOT NULL CHECK (role IN ('focus', 'contains')),
    PRIMARY KEY (exercise_id, term_id),
    FOREIGN KEY (exercise_id, track_id) REFERENCES exercises(id, track_id) ON DELETE CASCADE,
    FOREIGN KEY (term_id, track_id)     REFERENCES terms(id, track_id)     ON DELETE CASCADE
);

CREATE INDEX ix_exercise_terms_term ON exercise_terms (term_id);


-- =============================================================================
-- 8. ATTEMPTS (immutable log, source of truth for progress)
-- =============================================================================
CREATE TABLE attempts (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id       INTEGER     NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    is_correct        BOOLEAN     NOT NULL,
    score             INTEGER     NOT NULL DEFAULT 0,
    response_time_ms  INTEGER,
    answered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_attempts_user_time   ON attempts (user_id, answered_at DESC);
CREATE INDEX ix_attempts_exercise    ON attempts (exercise_id);


-- =============================================================================
-- 9. PER-TOPIC PROGRESS (denormalized aggregate; topics are per track)
-- =============================================================================
CREATE TABLE user_topic_progress (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id            INTEGER          NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    correct_count       INTEGER          NOT NULL DEFAULT 0,
    incorrect_count     INTEGER          NOT NULL DEFAULT 0,
    mastery_score       DOUBLE PRECISION NOT NULL DEFAULT 0.0
                                         CHECK (mastery_score BETWEEN 0.0 AND 1.0),
    last_attempted_at   TIMESTAMPTZ,
    CONSTRAINT uq_user_topic UNIQUE (user_id, topic_id)
);

CREATE INDEX ix_progress_user ON user_topic_progress (user_id);


-- =============================================================================
-- 10. AGENT_RUNS (observability of the exercise selection/generation agent)
-- =============================================================================
-- One row per agent run (called by chat.py after the negotiation). Lets you
-- monitor cycles/tokens/time per request and inspect the step-by-step trace
-- of a single run (see GET /exercises/agent-runs/{id}).
CREATE TABLE agent_runs (
    id                   SERIAL PRIMARY KEY,
    session_id           VARCHAR(64),                 -- chat session id, when available
    user_id              INTEGER     REFERENCES users(id)  ON DELETE SET NULL,
    track_id             INTEGER     REFERENCES tracks(id) ON DELETE SET NULL,
    request_params       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    target_composition   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    db_found_count       INTEGER     NOT NULL DEFAULT 0,
    gap_count            INTEGER     NOT NULL DEFAULT 0,
    cycles               INTEGER     NOT NULL DEFAULT 0,
    llm_calls            INTEGER     NOT NULL DEFAULT 0,
    input_tokens         INTEGER     NOT NULL DEFAULT 0,
    output_tokens        INTEGER     NOT NULL DEFAULT 0,
    duration_ms          INTEGER     NOT NULL DEFAULT 0,
    final_exercise_ids   JSONB       NOT NULL DEFAULT '[]'::jsonb,
    trace                JSONB       NOT NULL DEFAULT '{}'::jsonb,
    status               VARCHAR(16) NOT NULL DEFAULT 'ok',   -- 'ok' | 'partial' | 'error'
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_agent_runs_created ON agent_runs (created_at DESC);
CREATE INDEX ix_agent_runs_track   ON agent_runs (track_id, created_at DESC);


-- =============================================================================
-- =============================================================================
-- SEED DATA — REQUIRED for the API to work
-- =============================================================================
-- The backend resolves tracks, languages and exercise types by `code`.
-- =============================================================================
-- =============================================================================

INSERT INTO languages (code, name) VALUES
    ('it', 'Italian'),
    ('ja', 'Japanese')
ON CONFLICT (code) DO NOTHING;


INSERT INTO exercise_types (code, name) VALUES
    ('multiple_choice', 'Multiple Choice'),
    ('fill_blank',      'Fill in the Blank'),
    ('translate_rev',   'Translate into the base language'),
    ('kanji_reading',   'Kanji reading'),
    ('kanji_writing',   'Kanji writing'),
    ('romaji_input',    'Romaji input')
ON CONFLICT (code) DO NOTHING;


-- Japanese, studied from Italian
INSERT INTO tracks (code, name, target_language_id, base_language_id)
SELECT 'ja', '日本語 · Japanese', t.id, b.id
FROM languages t, languages b
WHERE t.code = 'ja' AND b.code = 'it'
ON CONFLICT (code) DO NOTHING;

-- No typing in Japanese (no IME needed): option-based types, plus typed
-- answers only in Latin script — translate_rev (Italian) and romaji_input.
INSERT INTO track_exercise_types (track_id, exercise_type_id, is_typed_input)
SELECT tr.id, et.id, et.code IN ('translate_rev', 'romaji_input')
FROM tracks tr, exercise_types et
WHERE tr.code = 'ja'
  AND et.code IN ('multiple_choice', 'fill_blank', 'translate_rev', 'kanji_reading', 'kanji_writing', 'romaji_input')
ON CONFLICT DO NOTHING;


-- Initial Japanese topics (optional — the agent creates others on the fly with category='auto')
INSERT INTO topics (track_id, code, category, name)
SELECT tr.id, v.code, v.category, v.name
FROM tracks tr, (VALUES
    ('particle_wa_ga',    'grammar', 'Particles は / が'),
    ('particle_mo',       'grammar', 'Particle も'),
    ('particle_no',       'grammar', 'Particle の'),
    ('particle_ni_de',    'grammar', 'Particles に / で'),
    ('particle_wo',       'grammar', 'Particle を'),
    ('copula_desu',       'grammar', 'Copula です'),
    ('i_adjectives',      'grammar', 'い-adjectives'),
    ('na_adjectives',     'grammar', 'な-adjectives'),
    ('verbs_masu',        'grammar', 'Verbs, polite ます form'),
    ('greetings',         'vocab',   'Greetings'),
    ('self_introduction', 'vocab',   'Self-introduction'),
    ('family',            'vocab',   'Family'),
    ('school',            'vocab',   'School'),
    ('numbers_counters',  'vocab',   'Numbers and counters'),
    ('time_dates',        'vocab',   'Time and dates'),
    ('food',              'vocab',   'Food and drinks')
) AS v(code, category, name)
WHERE tr.code = 'ja'
ON CONFLICT DO NOTHING;


-- =============================================================================
-- CHECK
-- =============================================================================
-- After running it you should see 14 tables:
--   \dt  (in psql)
-- And the seeds:
--   SELECT count(*) FROM tracks;                -- 1
--   SELECT count(*) FROM track_exercise_types;  -- 6
--   SELECT count(*) FROM topics;                -- 16
-- =============================================================================
