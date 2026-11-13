"""
Observability for the exercise selection/generation agent (`exercise_agent.py`).

One row in `agent_runs` per call to `select_or_generate_exercises` — see
CLAUDE.md ("Exercise selection/generation agent — design and status",
Phase 2) for the design, and `AgentRun` in `models.py` for the table shape.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentRun

logger = logging.getLogger(__name__)


async def record_agent_run(
    db: AsyncSession,
    *,
    session_id: str | None,
    user_id: int | None,
    track_id: int | None,
    trace: dict,
    duration_ms: int,
    run_status: str,
) -> None:
    """
    Persists one agent run. Best-effort: never raises to the caller — a
    failure to log observability data must never break the exercise
    selection/generation flow itself (same philosophy as
    `attempt_service.record_attempts`).

    `trace` is the dict produced by `exercise_agent.select_or_generate_exercises`
    (or carried by `AgentGenerationError.trace` on failure) and is stored
    verbatim in the `trace` JSONB column — a superset of the individual
    scalar columns below, since it also carries `unfilled_spec_ids`, which
    has no dedicated column. The scalar columns are mirrored out of it for
    cheap listing/filtering without parsing JSON.
    """
    try:
        db.add(AgentRun(
            session_id=session_id,
            user_id=user_id,
            track_id=track_id,
            request_params=trace.get("request_params") or {},
            target_composition=trace.get("target_composition") or {},
            db_found_count=trace.get("db_found_count", 0),
            gap_count=trace.get("gap_count", 0),
            cycles=trace.get("cycles", 0),
            llm_calls=trace.get("llm_calls", 0),
            input_tokens=trace.get("input_tokens", 0),
            output_tokens=trace.get("output_tokens", 0),
            duration_ms=duration_ms,
            final_exercise_ids=trace.get("final_exercise_ids") or [],
            trace=trace,
            status=run_status,
        ))
        await db.commit()
    except Exception:
        logger.exception("Failed to persist agent run — observability data lost for this call")
        await db.rollback()


async def list_agent_runs(
    db: AsyncSession,
    *,
    track_id: int | None = None,
    session_id: str | None = None,
    user_id: int | None = None,
    run_status: str | None = None,
    limit: int = 50,
) -> list[AgentRun]:
    """Most recent runs first, with optional exact-match filters."""
    query = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if track_id is not None:
        query = query.where(AgentRun.track_id == track_id)
    if session_id:
        query = query.where(AgentRun.session_id == session_id)
    if user_id is not None:
        query = query.where(AgentRun.user_id == user_id)
    if run_status:
        query = query.where(AgentRun.status == run_status)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_agent_run(db: AsyncSession, run_id: int) -> AgentRun:
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )
    return run
