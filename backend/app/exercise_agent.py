"""
Exercise selection/generation agent.

Replaces the naive fallback that used to live in
`routers/chat.py::_fetch_exercises` (random DB lookup, and on a miss,
generate exactly one phrase's worth of exercises regardless of how many were
requested). See CLAUDE.md ("Exercise selection/generation agent — design
and status") for the full design.

Everything happens inside one *track* (e.g. Japanese from Italian): the
track decides which exercise types exist and which of them are "light"
(answered by picking an option rather than typing).

Pipeline for one call to `select_or_generate_exercises`:
1. Resolve the track's exercise types, and auto-create any requested topic
   code that doesn't exist yet in the track *before* anything else. This
   fixes a real bug in the old code: a topic filter is an OR/ANY match, so
   mixing one known topic with one unknown one used to silently succeed
   using only the known topic — the unknown one was never created.
2. Compute a deterministic 60% topic / 20% review / 20% harder-difficulty
   mix (harder = one step up on the 1–MAX_DIFFICULTY scale), and the type of every new slot: option-based ("light") types by
   default, at most MAX_TYPED_PER_SESSION typed answers per session — pure
   Python, no LLM involved, and no randomness beyond the DB's `random()`.
3. Fill every bucket from the DB first. The review bucket pulls the user's
   own past wrong attempts (never backfilled by generation — any shortfall
   just becomes extra topic-bucket slots). The topic/harder buckets exclude
   exercises the user has already seen recently ("exhausted"); one shared
   exclusion set is threaded sequentially through every subsequent query so
   the same exercise can never be picked twice in one run.
4. Whatever is still missing after the DB lookup is the "gap": handed to
   Claude via `claude_service.generate_exercises_for_gap`, a single forced
   tool-use call, matched back by a stable `spec_id`. At most one further
   stateless top-up call targets anything still missing; whatever's left
   after that is accepted as a partial result (logged, not retried further).
5. The final list (DB candidates + newly generated ones) is reordered so
   consecutive exercises differ in type where possible, then committed once,
   unconditionally — a partially-filled session (and any newly created
   topic) is valid state worth keeping even if generation didn't close the
   whole gap.

The result carries a `trace` dict shaped to match the `agent_runs` table's
columns, so `agent_run_service` can persist it verbatim without this module
knowing anything about that table.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import claude_service, term_service
from .exercise_payloads import MAX_DIFFICULTY
from .exercise_service import (
    EXERCISE_LOAD_OPTIONS,
    exercise_to_response,
    get_or_create_topics,
    link_phrase_topics,
    load_exercises,
    topic_phrase_ids,
)
from .models import Attempt, Exercise, Phrase, PhraseTranslation, Track, User
from .schemas import ExerciseResponse, GeneratedExerciseItem, NewExerciseSpec, TranslationResponse
from .track_service import (
    MAX_TYPED_PER_SESSION,
    track_exercise_type_id,
    track_light_type_codes,
    track_type_codes,
)
from .tracks import get_track_spec
from .tracks.base import TrackSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure functions — no DB/network, safe to unit test without any fixtures.
# ---------------------------------------------------------------------------
@dataclass
class BucketSizes:
    topic: int
    review: int
    harder: int


def compute_bucket_sizes(n_exercises: int) -> BucketSizes:
    """
    Deterministic 60/20/20 split: review and harder each get round(20%),
    topic gets whatever is left (absorbing the rounding remainder). At very
    small `n_exercises` (e.g. 3) the topic share can end up well below 60% —
    that's an accepted side-effect of small session sizes, not a bug.
    """
    n_exercises = max(1, n_exercises)
    n_review = round(n_exercises * 0.2)
    n_harder = round(n_exercises * 0.2)
    n_topic = n_exercises - n_review - n_harder
    return BucketSizes(topic=n_topic, review=n_review, harder=n_harder)


def reallocate_review_shortfall(sizes: BucketSizes, actual_review_count: int) -> BucketSizes:
    """
    The review bucket is never backfilled by generation — it only pulls from
    the user's real history. Whatever it falls short of its target becomes
    extra topic-bucket slots instead.
    """
    actual_review_count = max(0, min(actual_review_count, sizes.review))
    shortfall = sizes.review - actual_review_count
    return BucketSizes(topic=sizes.topic + shortfall, review=actual_review_count, harder=sizes.harder)


def plan_slot_types(
    n_slots: int,
    forced_type: str | None,
    light_types: list[str],
    typed_types: list[str],
    typed_budget: int,
) -> list[str]:
    """
    A concrete exercise_type for each of `n_slots` new slots (topic + harder
    buckets together). Option-based ("light") types cycle; typed types get at
    most `typed_budget` slots, spread out (never first, never adjacent). Every
    slot gets `forced_type` when the learner asked for one type explicitly.
    """
    if forced_type:
        return [forced_type] * n_slots
    if not light_types:
        return [typed_types[i % len(typed_types)] for i in range(n_slots)] if typed_types else []

    # at most one typed slot every three, so they can never be adjacent
    n_typed = min(max(0, typed_budget), n_slots // 3) if typed_types else 0
    typed_positions = {round((k + 1) * n_slots / (n_typed + 1)) for k in range(n_typed)}
    types: list[str] = []
    light_i = typed_i = 0
    for position in range(n_slots):
        if position in typed_positions and position > 0:
            types.append(typed_types[typed_i % len(typed_types)])
            typed_i += 1
        else:
            types.append(light_types[light_i % len(light_types)])
            light_i += 1
    return types


def build_gap_specs(
    bucket_name: str,
    type_code: str,
    requested: int,
    found: int,
    difficulty: int,
    topic_codes: list[str],
    start_counter: int,
) -> tuple[list[NewExerciseSpec], int]:
    """
    Builds the `NewExerciseSpec` list for whatever a (bucket, exercise_type)
    slot group is still missing after the DB lookup — `max(0, requested -
    found)` items. `spec_id`s are numbered from `start_counter + 1` so ids
    stay unique and stable across every bucket/type group filled in the same
    run. Returns the specs plus the counter value to pass as `start_counter`
    for the next group.
    """
    missing = max(0, requested - found)
    specs = [
        NewExerciseSpec(
            spec_id=f"{bucket_name}-{start_counter + i}",
            exercise_type=type_code,
            difficulty=difficulty,
            topics=topic_codes,
        )
        for i in range(1, missing + 1)
    ]
    return specs, start_counter + missing


def order_anti_adjacency(exercises: list[ExerciseResponse]) -> list[ExerciseResponse]:
    """
    Reorders the final list so consecutive exercises differ in exercise_type
    where possible (round-robin merge across type groups), then does one
    local-swap pass to also separate any adjacent pair that happens to share
    the same phrase_id (can only happen if the same phrase surfaced from two
    different bucket/type queries — rare, but jarring if left adjacent).
    """
    if len(exercises) <= 1:
        return list(exercises)

    groups: dict[str, list[ExerciseResponse]] = {}
    for ex in exercises:
        groups.setdefault(ex.exercise_type, []).append(ex)

    ordered: list[ExerciseResponse] = []
    queues = list(groups.values())
    while queues:
        next_queues = []
        for queue in queues:
            ordered.append(queue.pop(0))
            if queue:
                next_queues.append(queue)
        queues = next_queues

    for i in range(1, len(ordered)):
        if ordered[i].phrase_id == ordered[i - 1].phrase_id:
            for j in range(i + 1, len(ordered)):
                if ordered[j].phrase_id != ordered[i - 1].phrase_id:
                    ordered[i], ordered[j] = ordered[j], ordered[i]
                    break
    return ordered


def check_generated_item(
    track_spec: TrackSpec, spec: NewExerciseSpec, item: GeneratedExerciseItem, language_codes: set[str],
) -> tuple[dict | None, str | None]:
    """
    (normalized payload, None) if the generated item can be stored, else
    (None, reason): the payload must be valid for its type, respect the
    level gate, and the phrase must come in both track languages.
    """
    try:
        payload = track_spec.validate_payload(spec.exercise_type, item.payload)
    except ValidationError as exc:
        error = exc.errors()[0]
        field_path = ".".join(str(part) for part in error["loc"]) or "payload"
        return None, f"invalid payload ({field_path}): {error['msg']}"
    except ValueError as exc:
        return None, f"invalid payload: {exc}"
    problems = track_spec.level_problems(spec.difficulty, payload)
    if problems:
        return None, "; ".join(problems)
    missing = language_codes - {tr.language for tr in item.phrase_translations}
    if missing:
        return None, f"phrase missing languages: {sorted(missing)}"
    return payload, None


# ---------------------------------------------------------------------------
# DB-touching helpers — all take the caller's single AsyncSession, no
# session creation here (see `select_or_generate_exercises`'s docstring for
# why a single shared session matters).
# ---------------------------------------------------------------------------
async def _get_recently_seen_exercise_ids(db: AsyncSession, user_id: int, limit: int = 300) -> set[int]:
    """
    Exercises the user has attempted recently — excluded from the
    topic/harder buckets as "exhausted" (the review bucket wants these on
    purpose). Postgres rejects `SELECT DISTINCT` combined with `ORDER BY` on
    a column outside the select list, so we fetch plain rows ordered by
    recency and dedupe in Python instead.
    """
    result = await db.execute(
        select(Attempt.exercise_id)
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.answered_at.desc())
        .limit(limit)
    )
    return set(result.scalars().all())


async def _get_review_candidates(
    db: AsyncSession,
    user_id: int,
    track_id: int,
    forced_type_id: int | None,
    limit: int,
) -> list[Exercise]:
    """
    Exercises of this track the user got wrong before (and of the forced
    exercise_type, if the user asked for one specifically). Not filtered by
    topic or difficulty — review pulls whatever the user actually struggled
    with, regardless of what's being negotiated now.
    """
    if limit <= 0:
        return []

    conditions = [
        Attempt.user_id == user_id,
        Attempt.is_correct.is_(False),
        Exercise.track_id == track_id,
    ]
    if forced_type_id is not None:
        conditions.append(Exercise.exercise_type_id == forced_type_id)

    id_rows = await db.execute(
        select(Attempt.exercise_id)
        .join(Exercise, Exercise.id == Attempt.exercise_id)
        .where(*conditions)
        .order_by(Attempt.answered_at.desc())
    )
    # Dedupe in Python (most-recent-wrong-attempt-per-exercise wins), then cap.
    ordered_ids = list(dict.fromkeys(id_rows.scalars().all()))[:limit]
    return await load_exercises(db, ordered_ids)


async def _query_candidates(
    db: AsyncSession,
    track_id: int,
    difficulty: int,
    topic_ids: list[int] | None,
    exercise_type_id: int,
    exclude_ids: set[int],
    limit: int,
) -> list[Exercise]:
    """
    Random candidate lookup for one (bucket, exercise_type) slot group.
    Deliberately single-type per call (never a pooled multi-type query) so
    the caller's deterministic type assignment is honored exactly, not just
    probabilistically — this is what guarantees the light-type floor.
    """
    if limit <= 0:
        return []

    conditions = [
        Exercise.track_id == track_id,
        Exercise.exercise_type_id == exercise_type_id,
        Exercise.phrase_id.in_(select(Phrase.id).where(Phrase.track_id == track_id, Phrase.difficulty == difficulty)),
    ]
    if exclude_ids:
        conditions.append(Exercise.id.notin_(exclude_ids))
    if topic_ids:
        conditions.append(Exercise.phrase_id.in_(topic_phrase_ids(topic_ids)))

    id_query = select(Exercise.id).where(*conditions).order_by(sqlfunc.random()).limit(limit)
    exercise_ids = list((await db.execute(id_query)).scalars().all())
    return await load_exercises(db, exercise_ids)


async def _get_reference_exercises(
    db: AsyncSession,
    track_id: int,
    exercise_type_id: int,
    topic_ids: list[int] | None,
    limit: int = 3,
) -> list[Exercise]:
    """
    Up to `limit` existing exercises of the same track/type/topic, preferring
    `human_checked=true`, used as a style reference in the gap-filling prompt
    (shown to the LLM as tone/structure guidance, never as content to copy).
    """
    conditions = [
        Exercise.track_id == track_id,
        Exercise.exercise_type_id == exercise_type_id,
    ]
    if topic_ids:
        conditions.append(Exercise.phrase_id.in_(topic_phrase_ids(topic_ids)))

    result = await db.execute(
        select(Exercise)
        .where(*conditions)
        .options(*EXERCISE_LOAD_OPTIONS)
        .order_by(Exercise.human_checked.desc(), sqlfunc.random())
        .limit(limit)
    )
    return list(result.scalars().all())


def _reference_to_prompt_dict(exercise: Exercise) -> dict:
    """Trims an Exercise down to the bits worth showing the LLM as a style example."""
    return {"exercise_type": exercise.exercise_type.code, "payload": exercise.payload}


async def _persist_generated_item(
    db: AsyncSession,
    track: Track,
    spec: NewExerciseSpec,
    item: GeneratedExerciseItem,
    payload: dict,
) -> ExerciseResponse:
    """
    Creates the new Phrase + PhraseTranslation rows + PhraseTopic links +
    Exercise row for one generated item. One brand-new phrase per exercise —
    never "every type for one phrase", since gap-filling should only produce
    exactly what's missing. Translations in languages outside the track are
    dropped. Flushes only; the caller commits once for the whole agent run.
    """
    phrase = Phrase(track_id=track.id, difficulty=spec.difficulty)
    db.add(phrase)
    await db.flush()

    track_languages = {
        track.target_language.code: track.target_language_id,
        track.base_language.code: track.base_language_id,
    }
    translations_out: list[TranslationResponse] = []
    for tr in item.phrase_translations:
        language_id = track_languages.get(tr.language)
        if language_id is None or any(t.language == tr.language for t in translations_out):
            logger.warning("Generated translation for language '%s' outside track '%s' (or duplicate) — skipped", tr.language, track.code)
            continue
        db.add(PhraseTranslation(phrase_id=phrase.id, language_id=language_id, content=tr.content, ipa=tr.ipa))
        translations_out.append(TranslationResponse(language=tr.language, content=tr.content, ipa=tr.ipa, audio_url=None))

    topics = await get_or_create_topics(db, track, [*spec.topics, *(item.detected_topics or [])])
    link_phrase_topics(db, phrase, topics)

    annotations = get_track_spec(track.code).annotations_for(spec.exercise_type, payload)
    exercise = Exercise(
        track_id=track.id,
        phrase_id=phrase.id,
        exercise_type_id=track_exercise_type_id(track, spec.exercise_type),
        payload=payload,
        annotations=annotations,
        origin="ai_generated",
    )
    db.add(exercise)
    await db.flush()
    target_text = next((t.content for t in translations_out if t.language == track.target_language.code), None)
    if target_text:
        await term_service.link_exercise_terms(db, track, exercise.id, spec.exercise_type, target_text, payload)

    return ExerciseResponse(
        id=exercise.id,
        track=track.code,
        exercise_type=spec.exercise_type,
        source_language=track.base_language.code,
        target_language=track.target_language.code,
        difficulty=spec.difficulty,
        payload=payload,
        phrase_id=phrase.id,
        phrase_translations=translations_out,
        topics=[t.code for t in topics],
        is_new_phrase=True,
        annotations=annotations,
    )


# ---------------------------------------------------------------------------
# Orchestration — the entry point `routers/chat.py` calls.
# ---------------------------------------------------------------------------
class AgentGenerationError(Exception):
    """
    Raised when the agent ends up with zero exercises after DB lookup +
    generation. Carries the `trace` dict built up to the point of failure so
    the caller can still persist an observable (failed) agent run instead of
    losing all visibility into what was attempted.
    """

    def __init__(self, message: str, trace: dict | None = None):
        super().__init__(message)
        self.trace = trace or {}


@dataclass
class AgentSelectionResult:
    exercises: list[ExerciseResponse]
    trace: dict = field(default_factory=dict)


async def select_or_generate_exercises(
    db: AsyncSession,
    user: User,
    track: Track,
    filters: dict,
) -> AgentSelectionResult:
    """
    Picks (and, for the gap, generates) a session's exercises within `track`.
    `filters` is the `request_exercises` tool input negotiated in the chat:
    `difficulty`, optional `topics`, `exercise_type`, `n_exercises`.
    See this module's docstring for the full pipeline description.

    `db` must be a single session used for the whole call — topic
    auto-creation and any generated exercises are only flushed, not
    committed, until the very end, so a caller that splits this across two
    sessions would make the topic invisible to its own later queries.
    """
    difficulty = max(1, min(int(filters.get("difficulty") or 2), MAX_DIFFICULTY))
    n_exercises = max(1, min(int(filters.get("n_exercises") or 10), 15))
    forced_type = filters.get("exercise_type") or None
    forced_type_id = track_exercise_type_id(track, forced_type) if forced_type else None

    light_types = track_light_type_codes(track)
    typed_types = [t for t in track_type_codes(track) if t not in light_types]

    # Resolve/auto-create requested topics FIRST — this is what fixes the
    # "mixed known + unknown topic silently drops the unknown one" bug.
    topics = await get_or_create_topics(db, track, filters.get("topics") or [])
    topic_ids = [t.id for t in topics] or None
    topic_codes = [t.code for t in topics]

    sizes = compute_bucket_sizes(n_exercises)

    review_candidates = await _get_review_candidates(db, user.id, track.id, forced_type_id, sizes.review)
    sizes = reallocate_review_shortfall(sizes, len(review_candidates))

    # Shared across every subsequent query so the same exercise is never
    # picked twice in one run (a real risk once difficulty=5 makes the
    # topic and harder buckets share identical filters).
    used_ids: set[int] = {ex.id for ex in review_candidates}
    used_ids |= await _get_recently_seen_exercise_ids(db, user.id)

    typed_in_review = sum(1 for ex in review_candidates if ex.exercise_type.code in typed_types)
    slot_types = plan_slot_types(
        sizes.topic + sizes.harder, forced_type, light_types, typed_types,
        MAX_TYPED_PER_SESSION - typed_in_review,
    )
    topic_types, harder_types = slot_types[:sizes.topic], slot_types[sizes.topic:]

    db_found: list[Exercise] = list(review_candidates)
    gap_specs: list[NewExerciseSpec] = []
    spec_counter = 0

    async def _fill_bucket(bucket_name: str, types: list[str], bucket_difficulty: int) -> None:
        nonlocal spec_counter
        type_counts: dict[str, int] = {}
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1

        # Sequential on purpose: each query must see the previous one's
        # picks via `used_ids` before it runs.
        for type_code, count in type_counts.items():
            found = await _query_candidates(
                db, track.id, bucket_difficulty, topic_ids,
                track_exercise_type_id(track, type_code), used_ids, count,
            )
            db_found.extend(found)
            used_ids.update(ex.id for ex in found)

            new_specs, spec_counter = build_gap_specs(
                bucket_name, type_code, count, len(found), bucket_difficulty,
                topic_codes, spec_counter,
            )
            gap_specs.extend(new_specs)

    await _fill_bucket("topic", topic_types, difficulty)
    await _fill_bucket("harder", harder_types, min(MAX_DIFFICULTY, difficulty + 1))

    cycles = 0
    llm_calls = 0
    input_tokens = 0
    output_tokens = 0
    generated: list[ExerciseResponse] = []
    unfilled_spec_ids: list[str] = []
    rejected: list[dict] = []

    if gap_specs:
        reference_examples: dict[str, list[dict]] = {}
        for type_code in sorted({s.exercise_type for s in gap_specs}):
            refs = await _get_reference_exercises(db, track.id, track_exercise_type_id(track, type_code), topic_ids)
            if refs:
                reference_examples[type_code] = [_reference_to_prompt_dict(r) for r in refs]

        pending = {s.spec_id: s for s in gap_specs}
        already_generated_hints: list[str] = []
        track_spec = get_track_spec(track.code)
        language_codes = {track.target_language.code, track.base_language.code}

        for _ in range(2):  # first call, plus at most one stateless top-up
            if not pending:
                break
            cycles += 1
            llm_calls += 1
            items, usage = claude_service.generate_exercises_for_gap(
                list(pending.values()), track.base_language.code, track.target_language.code,
                track_spec.generation_guidelines, dict(track_spec.type_instructions),
                reference_examples, already_generated_hints or None,
            )
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)

            seen_this_round: set[str] = set()
            for item in items:
                spec = pending.get(item.spec_id)
                if spec is None or item.spec_id in seen_this_round:
                    logger.warning("Dropping unmatched/duplicate spec_id '%s' from LLM response", item.spec_id)
                    continue
                seen_this_round.add(item.spec_id)
                payload, reason = check_generated_item(track_spec, spec, item, language_codes)
                if reason:
                    # stays pending: the top-up call gets another chance at it
                    logger.warning("Rejected generated item %s: %s", item.spec_id, reason)
                    rejected.append({"spec_id": item.spec_id, "reason": reason})
                    continue
                del pending[item.spec_id]
                generated.append(await _persist_generated_item(db, track, spec, item, payload))
                if item.phrase_translations:
                    already_generated_hints.append(item.phrase_translations[0].content)

        unfilled_spec_ids = list(pending.keys())
        if unfilled_spec_ids:
            logger.warning(
                "Exercise agent: %d spec(s) still unfilled after top-up: %s",
                len(unfilled_spec_ids), unfilled_spec_ids,
            )

    all_exercises = [exercise_to_response(ex) for ex in db_found] + generated
    ordered = order_anti_adjacency(all_exercises)

    # Commit unconditionally — a partially-filled session (and any newly
    # created topic) is valid state worth keeping even if the gap wasn't
    # fully closed.
    await db.commit()

    trace = {
        "request_params": {**filters, "track": track.code},
        "target_composition": {
            "topic": sizes.topic,
            "review": sizes.review,
            "harder": sizes.harder,
            "max_typed": 0 if forced_type else MAX_TYPED_PER_SESSION,
        },
        "db_found_count": len(db_found),
        "gap_count": len(gap_specs),
        "cycles": cycles,
        "llm_calls": llm_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "unfilled_spec_ids": unfilled_spec_ids,
        "rejected": rejected,
        "final_exercise_ids": [ex.id for ex in ordered],
    }

    if not ordered:
        raise AgentGenerationError(
            "No exercises found in the DB and generation could not fill the gap", trace=trace,
        )

    return AgentSelectionResult(exercises=ordered, trace=trace)
