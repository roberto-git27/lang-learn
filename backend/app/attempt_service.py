"""
Exercise history persistence: `Attempt` (immutable log) + `UserTopicProgress`
(per-topic aggregate, used by the selection agent's "review" heuristics — see
`exercise_agent.py`). Topics are per track, so progress is per track too.

Single entry point for both flows that complete an exercise session (Practice
tab and chat) — see `routers/exercises.py::record_attempts_endpoint` and
`routers/chat.py::_stream_exercise_feedback`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Attempt, Exercise, PhraseTopic, User, UserTopicProgress

logger = logging.getLogger(__name__)


async def _update_topic_progress(db: AsyncSession, user: User, topic_id: int, is_correct: bool) -> None:
    progress = await db.scalar(
        select(UserTopicProgress).where(
            UserTopicProgress.user_id == user.id,
            UserTopicProgress.topic_id == topic_id,
        )
    )
    if progress is None:
        progress = UserTopicProgress(user_id=user.id, topic_id=topic_id, correct_count=0, incorrect_count=0)
        db.add(progress)

    if is_correct:
        progress.correct_count += 1
    else:
        progress.incorrect_count += 1

    total = progress.correct_count + progress.incorrect_count
    progress.mastery_score = progress.correct_count / total if total else 0.0
    progress.last_attempted_at = datetime.now(timezone.utc)
    await db.flush()


async def record_attempts(db: AsyncSession, user: User, results: list[dict]) -> int:
    """
    `results` is a list of `{"exercise": {...serialized ExerciseResponse...},
    "result": {...client-side outcome, at least "correct"...}}`, as produced
    by the frontend (SessionView / ChatWindow). Only the exercise id is taken
    from the client; its topics are read from the DB.

    Returns how many attempts were stored (0 on failure). Never raises to the
    caller: a failure while persisting history must never block the main
    flow (end of exercise session / chat feedback).
    """
    recorded = 0
    try:
        outcomes = [
            (item["exercise"]["id"], bool((item.get("result") or {}).get("correct")), (item.get("result") or {}).get("response_time_ms"))
            for item in results
            if (item.get("exercise") or {}).get("id") is not None
        ]
        exercise_ids = {exercise_id for exercise_id, _, _ in outcomes}
        known = set((await db.execute(select(Exercise.id).where(Exercise.id.in_(exercise_ids)))).scalars().all())

        topic_rows = await db.execute(
            select(Exercise.id, PhraseTopic.topic_id)
            .join(PhraseTopic, PhraseTopic.phrase_id == Exercise.phrase_id)
            .where(Exercise.id.in_(known))
        )
        topics_by_exercise: dict[int, list[int]] = {}
        for exercise_id, topic_id in topic_rows.all():
            topics_by_exercise.setdefault(exercise_id, []).append(topic_id)

        for exercise_id, is_correct, response_time_ms in outcomes:
            if exercise_id not in known:
                logger.warning("Attempt for unknown exercise %s — skipped", exercise_id)
                continue
            db.add(Attempt(
                user_id=user.id,
                exercise_id=exercise_id,
                is_correct=is_correct,
                score=1 if is_correct else 0,
                response_time_ms=response_time_ms,
            ))
            recorded += 1
            for topic_id in topics_by_exercise.get(exercise_id, []):
                await _update_topic_progress(db, user, topic_id, is_correct)

        await db.commit()
        return recorded
    except Exception:
        logger.exception("Error while persisting attempts — history not updated for this session")
        await db.rollback()
        return 0
