"""
FastAPI router for hand-made reading overrides (Phase 9): a word whose
computed reading is wrong gets the right one everywhere in its track.
See `reading_service.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import ReadingOverrideChange, ReadingOverrideRequest, ReadingOverrideResponse
from .. import reading_service, track_service, user_service

router = APIRouter(prefix="/readings", tags=["readings"])


@router.get("", response_model=list[ReadingOverrideResponse], summary="Reading overrides of a track, by word")
async def list_overrides_endpoint(
    track: str = Query(description="Track code, e.g. 'ja'"),
    db: AsyncSession = Depends(get_db),
) -> list[ReadingOverrideResponse]:
    track_obj = await track_service.get_track(db, track)
    return [ReadingOverrideResponse.model_validate(o) for o in await reading_service.list_overrides(db, track_obj)]


@router.put(
    "",
    response_model=ReadingOverrideChange,
    summary="Set the reading of a word everywhere in the track (furigana, romaji); "
            "the exercises containing it are updated",
)
async def set_override_endpoint(
    request: ReadingOverrideRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ReadingOverrideChange:
    user = await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    override, changed = await reading_service.set_override(db, track, user, request.surface, request.reading)
    return ReadingOverrideChange(override=ReadingOverrideResponse.model_validate(override), exercises_updated=changed)


@router.delete(
    "/{override_id}",
    response_model=ReadingOverrideChange,
    summary="Remove a reading override (the computed reading comes back); the exercises containing the word are updated",
)
async def delete_override_endpoint(
    override_id: int,
    track: str = Query(description="Track code, e.g. 'ja'"),
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ReadingOverrideChange:
    await user_service.get_user(db, user_id)
    track_obj = await track_service.get_track(db, track)
    changed = await reading_service.delete_override(db, track_obj, override_id)
    return ReadingOverrideChange(override=None, exercises_updated=changed)
