"""
FastAPI router for the vocabulary of a track (D-24): browse terms, fix a
meaning by hand, delete a wrong term, ask the AI for the missing meanings,
link existing exercises.
See `term_service.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..exercise_payloads import MAX_DIFFICULTY
from ..schemas import (
    TermListResponse, TermMeaningUpdate, TermResponse, TermSyncResponse, TranslateMeaningsRequest,
    TranslateMeaningsResponse,
)
from .. import term_service, track_service, user_service

router = APIRouter(prefix="/terms", tags=["terms"])


@router.get("", response_model=TermListResponse, summary="Terms of a track, most recent first")
async def list_terms_endpoint(
    track: str = Query(description="Track code, e.g. 'ja'"),
    q: str | None = Query(default=None, description="Search in the written form, reading, lemma and meaning"),
    level: int | None = Query(default=None, ge=1, le=MAX_DIFFICULTY),
    missing_meaning: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> TermListResponse:
    track_obj = await track_service.get_track(db, track)
    items, total, missing = await term_service.list_terms(
        db, track_obj, query=q, level=level, missing_meaning=missing_meaning, limit=limit, offset=offset,
    )
    return TermListResponse(items=items, total=total, missing_meanings=missing)


@router.patch("/{term_id}", response_model=TermResponse, summary="Set (or clear) a term's meaning by hand")
async def set_meaning_endpoint(
    term_id: int,
    request: TermMeaningUpdate,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TermResponse:
    await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    return TermResponse.model_validate(await term_service.set_meaning(db, track, term_id, request.meaning))


@router.delete(
    "/{term_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
    summary="Delete a wrong term and its links to exercises",
)
async def delete_term_endpoint(
    term_id: int,
    track: str = Query(description="Track code, e.g. 'ja'"),
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await user_service.get_user(db, user_id)
    await term_service.delete_term(db, await track_service.get_track(db, track), term_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/meanings",
    response_model=TranslateMeaningsResponse,
    summary="Ask the AI the meaning of the terms that have none (one batched call), and store it",
)
async def translate_meanings_endpoint(
    request: TranslateMeaningsRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TranslateMeaningsResponse:
    await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    return TranslateMeaningsResponse(**await term_service.translate_missing_meanings(db, track, request.limit))


@router.post("/sync", response_model=TermSyncResponse, summary="Link the exercises that have no terms yet (no LLM)")
async def sync_terms_endpoint(
    track: str = Query(description="Track code, e.g. 'ja'"),
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TermSyncResponse:
    await user_service.get_user(db, user_id)
    track_obj = await track_service.get_track(db, track)
    linked, created = await term_service.sync_exercise_terms(db, track_obj)
    return TermSyncResponse(exercises_linked=linked, terms_created=created)
