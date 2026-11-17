# LangLearn

An AI-powered language-learning platform, currently focused on **Japanese**. Pick your profile and track, ask a chatbot (Claude, tool use, SSE streaming) for an exercise session; an agent picks — and generates only what is missing — a mix of exercises tuned to your history; at the end the chatbot comments on your results.

> [!WARNING]
> **Beta, for local or trusted use only.** LangLearn is a proof of concept, not a hosted service. Read this before running it anywhere other than your own machine:
> - **Profiles are not authentication.** The selected profile is sent as a plain `X-User-Id` header and the backend trusts it; the optional PIN only guards the profile switch in the UI. Anyone who can reach the API can act as any profile.
> - **Your Anthropic key pays for every visitor.** The chat, the Studio generation, the import's *Fix with AI* and the AI meanings call Claude with the key in your `.env`. If the app is reachable from the internet, anyone can spend your credit.
> - For these reasons `docker-compose.yaml` binds every port to `127.0.0.1`. Keep it that way unless you add real authentication and rate limiting in front of it.
> - The database schema can still change between versions, sometimes with a reset (see [Database and migrations](#database-and-migrations)).

---

## Features

- **Tracks** — a track is a target language studied from a base language (e.g. Japanese from Italian). Phrases, topics and exercises belong to one track, enforced by composite foreign keys in PostgreSQL; each track enables its own exercise types
- **Profiles** — several people can share one instance: each profile (optional 4-digit PIN) has its own tracks, history and review data. Profiles are not accounts: this is a private, single-tenant tool
- **Negotiation chat** — SSE-streamed chatbot, with a per-track prompt and tool, that collects difficulty and topics through Anthropic tool use, starts the exercise search and gives feedback at the end of the session
- **Exercise sessions** — a sequence of exercises with a final summary, graded client-side. Japanese track types, mostly pick-one-of-four and never requiring a Japanese keyboard: `kanji_reading` (学生 → がくせい), `kanji_writing` (がっこう → 学校), `multiple_choice`, `fill_blank`, plus at most two typed answers per session — `romaji_input` (山田 → yamada, long-vowel spellings all accepted) and `translate_rev` (Japanese → base language). The word being asked about is always underlined inside a real sentence, whose translation is available on request
- **Difficulty 1–10** — two steps per JLPT level (1 first lessons, 2 N5, 3–4 N4 … 9–10 N1), so the beginner levels are fine-grained
- **Level gate** — generated exercises at levels 1–2 may only use that level's kanji (first-lesson set, then JLPT N5); anything else is rejected before it reaches the database
- **Practice mode** — start a session straight from filters (type, difficulty), with no LLM cost
- **Furigana** — readings above kanji computed deterministically in Python (MeCab via `fugashi` + `unidic-lite`, zero tokens), stored with each exercise, on by default at beginner levels with a toggle — and never on the word the exercise is asking about
- **Exercise selection/generation agent** — after the negotiation, an orchestrator deterministically computes a 60% topic / 20% review-of-mistakes / 20% harder-difficulty mix (with at least 60% light `multiple_choice`/`fill_blank` types) and hands Claude (tool-use loop, max 2 cycles) only the targeted generation of the remaining gap — types always come from the track; the pipeline is documented in `backend/app/exercise_agent.py`
- **Observability** — every agent run is recorded in `agent_runs` (cycles, tokens, duration, full trace) and browsable from the *Agent Runs* admin panel
- **Vocabulary** — the words of any text (a chapter, a dialogue) are extracted in dictionary form with MeCab, zero tokens, and stored once per word (言いました → 言う; かみ and 髪 are one term); every exercise is linked to the terms it is about or contains; meanings are asked to the AI once, in batches, and can be fixed by hand; a `.csv` term list (term, reading, meaning) adds curated words with their meanings
- **Studio generation** — describe what you want in a `.md` request (parameters, free text, a list of terms such as kanji): the exercises are planned in Python, written by Claude with randomly picked verified exercises as examples, checked (structure, kanji level, the term really used) and shown as a draft with its cost; write single items again (with an optional note), keep what you like for the review queue, or turn the draft into `.md`, fix it and import it
- **Studio import** — write exercises in a plain `.md` format ([`sample/README.md`](sample/README.md)), preview them with their furigana and line-numbered errors, then import them: a deterministic parser, zero tokens, duplicates recognized on re-import, and the source file kept with every import; blocks with errors or exercises pasted from a workbook can be rewritten in the format by a cheap model (*Fix with AI*: content copied, never invented, back in the editor for a human check)
- **Human review** — a review queue for generated exercises (`human_checked`); imported and verified exercises become style examples for later generations
- **Exercise history** — every completed session (Practice tab and chat) writes `attempts`/`user_topic_progress` per profile and track, which feed the agent's review heuristics
- **Tests** — pytest suite over the agent's deterministic logic and the validation layer (no network or DB required)

---

## Architecture

```
Browser
  └── React + Nginx (port 80)
        └── /api/*  →  FastAPI (port 8000)
                          ├── PostgreSQL via asyncpg + async SQLAlchemy
                          └── Anthropic API (Claude) — generation + chat
```

**Stack:**
- Frontend: React (Vite), CSS variables, no external state library — four areas: Chat, Practice, Studio (`.md` import, AI generation, vocabulary), Admin (Review, Coverage, Agent Runs)
- Backend: FastAPI, Pydantic v2, async SQLAlchemy, asyncpg
- DB: PostgreSQL 18 — relational schema with track isolation via composite foreign keys (`tracks`, `track_exercise_types`, `phrases`, `phrase_translations`, `topics`, `phrase_topics`, `exercises`, `users`, `user_tracks`, `attempts`, `user_topic_progress`, `agent_runs`, …)
- LLM: Anthropic SDK — `claude-haiku-5-5` for the chat (SSE streaming via `AsyncAnthropic`), `claude-sonnet-5-5` for exercise generation and term meanings; both configurable in `.env`

**Design choices worth noting:**
- The LLM is used only where it adds value: bucketing, gap computation and ordering are plain, unit-tested Python; Claude is called only to fill the gap the database can't cover, with a hard cap on cycles.
- Structured output through a tool call validated by Pydantic, rather than parsing free-form JSON: the prompt names the tool, `tool_choice` stays `auto` (the 5.5 models reject a forced choice), the call is checked and asked again once if missing; the term-meanings tool is `strict`.
- Every agent run is persisted with its full trace, so cost and behavior can be inspected after the fact.
- Language-specific behavior (prompts, generation guidelines, text annotation) lives in small per-track modules; language-specific *data* (enabled exercise types, topics) lives in the database.
- Deterministic work before any LLM call: furigana come from a morphological analyzer, not from the model — cheaper, reproducible and unit-tested.

---

## Quick start

**Prerequisites:** Docker and Docker Compose.

```bash
cp .env.example .env      # then set ANTHROPIC_API_KEY and the POSTGRES_* values
docker-compose up -d      # PostgreSQL + FastAPI + React/Nginx
```

On the first start, `postgresql/schema.sql` (tables + seed data) is applied automatically, and the app asks you to create a profile.

To try the app without spending tokens, open the **Studio** tab, load [`sample/ja_starter.md`](sample/ja_starter.md) (18 hand-written Japanese exercises, levels 1–3, every exercise type) with *Open .md file…*, then *Preview* and *Import*; the exercises are then available in **Practice** and **Chat**.

```bash
# Rebuild after code changes
docker-compose build backend && docker-compose up -d
```

| Service    | URL                         |
|------------|-----------------------------|
| Frontend   | http://localhost:80         |
| Backend    | http://localhost:8000       |
| API docs   | http://localhost:8000/docs  |
| PostgreSQL | localhost:5432              |

### Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest
```

---

## API endpoints

Profile-attributed requests carry the selected profile id in the `X-User-Id` header (not authentication).

### Tracks and profiles
| Method | Path                               | Description |
|--------|------------------------------------|-------------|
| GET    | `/tracks`                          | Enabled tracks with their languages and exercise types |
| GET    | `/users`                           | Profiles (name, whether a PIN is set, tracks) |
| POST   | `/users`                           | Creates a profile: `display_name`, optional 4-digit `pin`, `tracks` |
| POST   | `/users/{id}/verify-pin`           | Checks a profile's PIN before switching to it (204 / 403) |
| PUT    | `/users/{id}/tracks/{code}`        | Enrolls the profile in a track or marks it as the most recently used |

### Exercises `/exercises`
| Method | Path                            | Description |
|--------|---------------------------------|-------------|
| GET    | `/exercises/random`             | Random exercises of a track (`track`, optional `exercise_type`, `difficulty`, `topics[]`, `limit`) — Practice tab |
| POST   | `/exercises/attempts`           | Records a session's results for the profile; writes `attempts` + updates `user_topic_progress` |
| GET    | `/exercises/stats`              | Exercise counts of a track per difficulty and type, verified ones apart (`track`) |
| GET    | `/exercises/review-queue`       | Review queue of a track: exercises to verify / already verified (`track`, `exercise_type`, `difficulty`, `human_checked`, `limit`, `offset`) |
| PATCH  | `/exercises/{id}/human-checked` | Sets/clears the human verification of an exercise (reviewer = current profile) |
| GET    | `/exercises/agent-runs`         | Runs of the selection/generation agent (filters `track`, `session_id`, `user_id`, `status`, `limit`) |
| GET    | `/exercises/agent-runs/{id}`    | Detail of a single run, including the full trace |

### Studio `/studio`
| Method | Path                            | Description |
|--------|---------------------------------|-------------|
| POST   | `/studio/imports/preview`       | Parses a `.md` of exercises (`track`, `text`) and returns each block's status (ready / duplicate / error), errors and warnings with line numbers, payload and furigana — writes nothing |
| POST   | `/studio/imports/normalize`     | *Fix with AI*: rewrites the invalid blocks and the text outside blocks in the format with the cheap model (`CLAUDE_PARSE_MODEL`); returns the new `.md`, the skipped parts and the cost — writes nothing |
| POST   | `/studio/imports`               | Imports the ready blocks as verified exercises, keeping the source text (`track`, `text`, `source_name`) |
| POST   | `/studio/generations`           | Generates exercises from a request `.md` with Claude; returns a draft (items, errors, cost, the draft as `.md`) |
| POST   | `/studio/generations/{id}/save` | Stores the kept draft items (`keep` positions) as AI-generated exercises, to review |
| POST   | `/studio/generations/{id}/items/{position}/regenerate` | Writes one draft item again (same spec, a different sentence, optional `note`); cost added to the draft |
| POST   | `/studio/generations/{id}/discard` | Discards a draft |
| POST   | `/studio/terms/preview`         | Terms of a text or `.csv` term list in dictionary form, new vs already known (no LLM) |
| POST   | `/studio/terms`                 | Stores the new terms of a text or term list (source kept; a list's meanings are human ones) |
| GET    | `/studio/jobs`                  | Past imports, generations and vocabulary extractions of a track |
| GET    | `/studio/jobs/{id}`             | One job, with its source text (and its draft) |

### Vocabulary `/terms`
| Method | Path                     | Description |
|--------|--------------------------|-------------|
| GET    | `/terms`                 | Terms of a track (`q`, `level`, `missing_meaning`, `limit`, `offset`), with how many exercises use each |
| PATCH  | `/terms/{id}`            | Sets or clears a meaning by hand |
| DELETE | `/terms/{id}`            | Deletes a wrong term and its links |
| POST   | `/terms/meanings`        | Asks the AI the meaning of up to 60 terms without one, and stores it |
| POST   | `/terms/sync`            | Links the exercises that have no terms yet |

### Chat `/chat`
| Method | Path                                       | Description |
|--------|--------------------------------------------|-------------|
| POST   | `/chat/message`                            | Sends a message (SSE streaming); the first message creates a session bound to the profile and to `track` |
| POST   | `/chat/sessions/{id}/exercise-results`     | Sends exercise results, streams back the feedback |
| GET    | `/chat/sessions/{id}`                      | Current session state (track, phase, filters, message count) |
| DELETE | `/chat/sessions/{id}`                      | Forgets a session (*New chat* in the UI) |

`GET /health` returns `{"status": "ok"}`.

---

## Database and migrations

There is no migration tool (no Alembic): `postgresql/schema.sql` is the source of truth for a fresh setup. Incremental changes live in `migrations/` as numbered, idempotent SQL files, applied by hand to an existing database:

```bash
docker exec -i postgres psql -U <user> -d <db> < migrations/0001_exercise_annotations.sql
```

| File | Content |
|------|---------|
| `migrations/0001_exercise_annotations.sql` | `exercises.annotations` (furigana) |
| `migrations/0002_japanese_exercise_types.sql` | `kanji_reading`, `kanji_writing`, `romaji_input` on the Japanese track |
| `migrations/0003_difficulty_scale_1_10.sql` | difficulty scale 1–10 (was 1–5) |
| `migrations/0004_studio_imports.sql` | `ingest_jobs` (imported sources), `exercises.ingest_job_id`, origin `human_import` |
| `migrations/0005_studio_generation.sql` | generation drafts in `ingest_jobs`: kind, status, items, cost |
| `migrations/0006_terms.sql` | vocabulary: `terms`, `exercise_terms` |

To recreate the database from `schema.sql` (**deletes all data**):

```bash
docker-compose down && rm -rf volumes/postgresql && docker-compose up -d
```

---

## Contributing

This is a personal study and portfolio project, and **contributions (pull requests) are not accepted for now**. Issues reporting bugs are welcome. You are free to fork it under the terms of the license below.

## License

LangLearn is licensed under the **GNU Affero General Public License v3.0** ([`LICENSE`](LICENSE)). You can use, study, modify and share it. If you distribute a modified version, or run one as a network service that other people use, you must make its full source code available under the same license.

The sample files in [`sample/`](sample/) are original content written for this project and are covered by the same license. Never add text from commercial textbooks or graded readers to the repository: keep such material in the git-ignored `data/` folder.
