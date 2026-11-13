"""
FastAPI router for the exercise endpoints. Every lookup is scoped to a track.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..exercise_payloads import MAX_DIFFICULTY
from ..schemas import (
    AgentRunDetail,
    AgentRunSummary,
    ExerciseResponse,
    ExerciseResultsRequest,
    ExerciseReviewResponse,
    ExerciseStatsResponse,
    HumanCheckedUpdateRequest,
    RecordAttemptsResponse,
    ReviewQueueResponse,
)
from .. import agent_run_service, track_service, user_service
from ..attempt_service import record_attempts
from ..exercise_service import (
    exercise_stats,
    get_random_exercise,
    list_review_queue,
    update_human_checked,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get(
    "/random",
    response_model=list[ExerciseResponse],
    summary="Fetch random exercises of a track with optional filters (Practice tab)",
)
async def random_exercise_endpoint(
    track: str = Query(description="Track code, e.g. 'ja'"),
    exercise_type: str | None = Query(default=None),
    difficulty: int | None = Query(default=None, ge=1, le=MAX_DIFFICULTY),
    topics: list[str] = Query(default_factory=list, description="Topic codes, e.g. particle_mo. Repeat the param for multiple values."),
    limit: int = Query(default=1, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[ExerciseResponse]:
    try:
        track_obj = await track_service.get_track(db, track)
        return await get_random_exercise(
            db, track_obj, exercise_type, difficulty, topics=topics or None, limit=limit,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching random exercises")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching exercises",
        )


@router.get(
    "/stats",
    response_model=ExerciseStatsResponse,
    summary="How many exercises a track has per difficulty and type (Admin › Coverage)",
)
async def exercise_stats_endpoint(
    track: str = Query(description="Track code, e.g. 'ja'"),
    db: AsyncSession = Depends(get_db),
) -> ExerciseStatsResponse:
    try:
        track_obj = await track_service.get_track(db, track)
        return await exercise_stats(db, track_obj)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while counting exercises")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while counting exercises",
        )


@router.get(
    "/review-queue",
    response_model=ReviewQueueResponse,
    summary="Review queue of a track: exercises not yet (or already) verified by a human (Phase 3)",
)
async def review_queue_endpoint(
    track: str = Query(description="Track code, e.g. 'ja'"),
    exercise_type: str | None = Query(default=None),
    difficulty: int | None = Query(default=None, ge=1, le=MAX_DIFFICULTY),
    human_checked: bool = Query(default=False, description="False = to review, True = already verified"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueResponse:
    try:
        track_obj = await track_service.get_track(db, track)
        items, total = await list_review_queue(
            db, track_obj, exercise_type=exercise_type, difficulty=difficulty,
            human_checked=human_checked, limit=limit, offset=offset,
        )
        return ReviewQueueResponse(items=items, total=total)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching the review queue")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching the review queue",
        )


@router.patch(
    "/{exercise_id}/human-checked",
    response_model=ExerciseReviewResponse,
    summary="Set/clear the human verification flag of an existing exercise",
)
async def update_human_checked_endpoint(
    exercise_id: int,
    request: HumanCheckedUpdateRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ExerciseReviewResponse:
    try:
        reviewer = await user_service.get_user(db, user_id)
        return await update_human_checked(db, exercise_id, request.human_checked, reviewer)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while updating the verification status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while updating the verification status",
        )


@router.get(
    "/agent-runs",
    response_model=list[AgentRunSummary],
    summary="List runs of the exercise selection/generation agent (Phase 2 — observability)",
)
async def agent_runs_endpoint(
    track: str | None = Query(default=None, description="Track code; omit for every track"),
    session_id: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status", description="ok | partial | error"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunSummary]:
    try:
        track_id = (await track_service.get_track(db, track)).id if track else None
        runs = await agent_run_service.list_agent_runs(
            db, track_id=track_id, session_id=session_id, user_id=user_id, run_status=status_filter, limit=limit,
        )
        return [AgentRunSummary.model_validate(run) for run in runs]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching agent runs")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching agent runs",
        )


@router.get(
    "/agent-runs/{run_id}",
    response_model=AgentRunDetail,
    summary="Detail of a single agent run, including the full trace",
)
async def agent_run_detail_endpoint(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> AgentRunDetail:
    try:
        run = await agent_run_service.get_agent_run(db, run_id)
        return AgentRunDetail.model_validate(run)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while fetching the agent run")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while fetching the agent run",
        )


@router.post(
    "/attempts",
    response_model=RecordAttemptsResponse,
    summary="Record the results of an exercise session (history + mastery)",
)
async def record_attempts_endpoint(
    request: ExerciseResultsRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> RecordAttemptsResponse:
    """
    Called at the end of a session by the Practice tab (the chat flow
    persists internally in `routers/chat.py::_stream_exercise_feedback`,
    since it already has the results). The profile comes from `X-User-Id`
    (not authentication — see user_service.py).
    """
    user = await user_service.get_user(db, user_id)
    recorded = await record_attempts(db, user, [r.model_dump() for r in request.results])
    return RecordAttemptsResponse(recorded=recorded)
