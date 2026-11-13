"""
Exercise persistence and lookup services, always scoped to one track.

- Shared helpers used by the exercise agent (`exercise_agent.py`): topic
  get-or-create, eager-load options, ORM → response serialization.
- `get_random_exercise`: random DB lookup with optional filters (Practice tab).
- Human-checked review queue (Phase 3).
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import func as sqlfunc, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
    Exercise,
    Phrase,
    PhraseTopic,
    PhraseTranslation,
    Topic,
    Track,
    User,
)
from .schemas import (
    DifficultyStats,
    ExerciseResponse,
    ExerciseReviewResponse,
    ExerciseStatsResponse,
    TranslationResponse,
)
from .exercise_payloads import MAX_DIFFICULTY
from .track_service import MAX_TYPED_PER_SESSION, track_exercise_type_id, track_type_codes, track_typed_type_ids

logger = logging.getLogger(__name__)

# Shared eager-load shape for any Exercise ORM object serialized to an
# ExerciseResponse/ExerciseReviewResponse — avoids N+1 lazy loads on the
# track, exercise type and the phrase's translations/topics.
EXERCISE_LOAD_OPTIONS = (
    selectinload(Exercise.track),
    selectinload(Exercise.exercise_type),
    selectinload(Exercise.phrase).selectinload(Phrase.translations).selectinload(PhraseTranslation.language),
    selectinload(Exercise.phrase).selectinload(Phrase.topics),
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
async def get_or_create_topics(db: AsyncSession, track: Track, codes: Iterable[str]) -> list[Topic]:
    """Get-or-create topics within the track. Unknown ones are created with category='auto'."""
    codes = list(dict.fromkeys(c for c in codes if c))
    if not codes:
        return []

    result = await db.execute(select(Topic).where(Topic.track_id == track.id, Topic.code.in_(codes)))
    existing = result.scalars().all()
    existing_codes = {t.code for t in existing}
    new_topics = [
        Topic(track_id=track.id, code=c, category="auto", name=c.replace("_", " ").title())
        for c in codes
        if c not in existing_codes
    ]
    db.add_all(new_topics)
    await db.flush()
    return list(existing) + new_topics


def link_phrase_topics(db: AsyncSession, phrase: Phrase, topics: Iterable[Topic]) -> None:
    for topic in topics:
        db.add(PhraseTopic(phrase_id=phrase.id, topic_id=topic.id, track_id=phrase.track_id))


async def create_phrase(
    db: AsyncSession, track: Track, difficulty: int, target_text: str, base_text: str, topic_codes: Iterable[str],
) -> Phrase:
    """New phrase of the track with its text in the target and base language, linked to its topics. Flushes only."""
    phrase = Phrase(track_id=track.id, difficulty=difficulty)
    db.add(phrase)
    await db.flush()
    db.add(PhraseTranslation(phrase_id=phrase.id, language_id=track.target_language_id, content=target_text.strip()))
    db.add(PhraseTranslation(phrase_id=phrase.id, language_id=track.base_language_id, content=base_text.strip()))
    link_phrase_topics(db, phrase, await get_or_create_topics(db, track, topic_codes))
    return phrase


def exercise_to_response(exercise: Exercise, is_new_phrase: bool = False) -> ExerciseResponse:
    """Serializes a fully eager-loaded Exercise (see `EXERCISE_LOAD_OPTIONS`)."""
    return ExerciseResponse(
        id=exercise.id,
        track=exercise.track.code,
        exercise_type=exercise.exercise_type.code,
        source_language=exercise.track.base_language.code,
        target_language=exercise.track.target_language.code,
        difficulty=exercise.phrase.difficulty,
        payload=exercise.payload,
        phrase_id=exercise.phrase_id,
        phrase_translations=[
            TranslationResponse(language=tr.language.code, content=tr.content, ipa=tr.ipa, audio_url=tr.audio_url)
            for tr in exercise.phrase.translations
        ],
        topics=[t.code for t in exercise.phrase.topics],
        is_new_phrase=is_new_phrase,
        annotations=exercise.annotations or {},
    )


async def load_exercises(db: AsyncSession, exercise_ids: list[int]) -> list[Exercise]:
    """Eager-loaded exercises, in the same order as `exercise_ids`."""
    if not exercise_ids:
        return []
    result = await db.execute(select(Exercise).where(Exercise.id.in_(exercise_ids)).options(*EXERCISE_LOAD_OPTIONS))
    by_id = {ex.id: ex for ex in result.scalars().all()}
    return [by_id[i] for i in exercise_ids if i in by_id]


def topic_phrase_ids(topic_ids: list[int]):
    """Subquery: phrases linked to at least one of the given topics."""
    return select(PhraseTopic.phrase_id).where(PhraseTopic.topic_id.in_(topic_ids)).distinct()


# ---------------------------------------------------------------------------
# Random exercise lookup (Practice tab)
# ---------------------------------------------------------------------------
async def get_random_exercise(
    db: AsyncSession,
    track: Track,
    exercise_type: str | None = None,
    difficulty: int | None = None,
    topics: list[str] | None = None,
    limit: int = 1,
) -> list[ExerciseResponse]:
    conditions = [Exercise.track_id == track.id]

    if exercise_type:
        conditions.append(Exercise.exercise_type_id == track_exercise_type_id(track, exercise_type))

    if difficulty is not None:
        conditions.append(
            Exercise.phrase_id.in_(select(Phrase.id).where(Phrase.track_id == track.id, Phrase.difficulty == difficulty))
        )

    if topics:
        topic_ids = select(Topic.id).where(Topic.track_id == track.id, Topic.code.in_(topics))
        conditions.append(Exercise.phrase_id.in_(select(PhraseTopic.phrase_id).where(PhraseTopic.topic_id.in_(topic_ids))))

    async def pick(extra_condition, n: int) -> list[int]:
        query = select(Exercise.id).where(*conditions, extra_condition).order_by(sqlfunc.random()).limit(n)
        return list((await db.execute(query)).scalars().all()) if n > 0 else []

    if exercise_type:
        exercise_ids = await pick(true(), limit)
    else:
        # Mixed session: at most MAX_TYPED_PER_SESSION typed answers, the rest option-based.
        typed_ids = track_typed_type_ids(track)
        exercise_ids = await pick(Exercise.exercise_type_id.in_(typed_ids), min(MAX_TYPED_PER_SESSION, limit))
        exercise_ids += await pick(Exercise.exercise_type_id.notin_(typed_ids), limit - len(exercise_ids))
        random.shuffle(exercise_ids)

    if not exercise_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No exercises found for the given filters",
        )

    return [exercise_to_response(ex) for ex in await load_exercises(db, list(exercise_ids))]


# ---------------------------------------------------------------------------
# Exercise review (Phase 3) — human-checked queue
# ---------------------------------------------------------------------------
def _exercise_to_review_response(exercise: Exercise, is_new_phrase: bool = False) -> ExerciseReviewResponse:
    base = exercise_to_response(exercise, is_new_phrase=is_new_phrase)
    return ExerciseReviewResponse(
        **base.model_dump(),
        origin=exercise.origin,
        human_checked=exercise.human_checked,
        human_checked_at=exercise.human_checked_at,
        human_checked_by=exercise.human_checked_by,
        created_at=exercise.created_at,
    )


async def list_review_queue(
    db: AsyncSession,
    track: Track,
    *,
    exercise_type: str | None = None,
    difficulty: int | None = None,
    human_checked: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[ExerciseReviewResponse], int]:
    """Oldest first (FIFO): whatever has been sitting unreviewed the longest surfaces first."""
    conditions = [Exercise.track_id == track.id, Exercise.human_checked.is_(human_checked)]

    if exercise_type:
        conditions.append(Exercise.exercise_type_id == track_exercise_type_id(track, exercise_type))
    if difficulty is not None:
        conditions.append(Exercise.phrase_id.in_(select(Phrase.id).where(Phrase.difficulty == difficulty)))

    total = await db.scalar(select(sqlfunc.count()).select_from(Exercise).where(*conditions))

    id_query = (
        select(Exercise.id).where(*conditions).order_by(Exercise.created_at.asc()).limit(limit).offset(offset)
    )
    exercise_ids = list((await db.execute(id_query)).scalars().all())
    exercises = await load_exercises(db, exercise_ids)
    return [_exercise_to_review_response(ex) for ex in exercises], total or 0


def build_exercise_stats(
    rows: Iterable[tuple[int, str, bool, int]], type_codes: list[str],
) -> ExerciseStatsResponse:
    """Counts per difficulty from (difficulty, type code, human_checked, count)
    rows; every level of the scale appears, with every type of the track."""
    levels = {
        d: DifficultyStats(difficulty=d, total=0, human_checked=0, by_type={code: 0 for code in type_codes})
        for d in range(1, MAX_DIFFICULTY + 1)
    }
    for difficulty, type_code, checked, count in rows:
        level = levels.get(difficulty)
        if level is None:
            continue
        level.total += count
        level.by_type[type_code] = level.by_type.get(type_code, 0) + count
        if checked:
            level.human_checked += count
    return ExerciseStatsResponse(
        exercise_types=type_codes,
        levels=list(levels.values()),
        total=sum(level.total for level in levels.values()),
        human_checked=sum(level.human_checked for level in levels.values()),
    )


async def exercise_stats(db: AsyncSession, track: Track) -> ExerciseStatsResponse:
    """How many exercises the track has, per difficulty and type."""
    count = sqlfunc.count(Exercise.id)
    query = (
        select(Phrase.difficulty, Exercise.exercise_type_id, Exercise.human_checked, count)
        .join(Phrase, Phrase.id == Exercise.phrase_id)
        .where(Exercise.track_id == track.id)
        .group_by(Phrase.difficulty, Exercise.exercise_type_id, Exercise.human_checked)
    )
    type_code_by_id = {tet.exercise_type_id: tet.exercise_type.code for tet in track.exercise_types}
    rows = [
        (difficulty, type_code_by_id.get(type_id, str(type_id)), checked, n)
        for difficulty, type_id, checked, n in (await db.execute(query)).all()
    ]
    return build_exercise_stats(rows, track_type_codes(track))


async def update_human_checked(
    db: AsyncSession,
    exercise_id: int,
    human_checked: bool,
    reviewer: User,
) -> ExerciseReviewResponse:
    exercise = await db.scalar(
        select(Exercise).where(Exercise.id == exercise_id).options(*EXERCISE_LOAD_OPTIONS)
    )
    if exercise is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exercise {exercise_id} not found",
        )

    exercise.human_checked = human_checked
    exercise.human_checked_at = datetime.now(timezone.utc) if human_checked else None
    exercise.human_checked_by = reviewer.display_name if human_checked else None
    await db.commit()
    # `AsyncSessionLocal` is configured with `expire_on_commit=False`
    # (database.py), so the eager-loaded relationships above are still
    # attached — no need to re-fetch.
    return _exercise_to_review_response(exercise)
