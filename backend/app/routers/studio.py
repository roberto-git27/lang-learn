"""
FastAPI router for the Studio (Phase 9): import of human-written exercises
from `.md` (a preview that writes nothing, then the import), AI generation
from a request (a draft, then save or discard), and the vocabulary of a text
(see `studio_service.py`, `term_service.py`).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import (
    GenerationSaveRequest, ImportPreviewResponse, RegenerateItemRequest, NormalizeResponse, StudioJobDetail, StudioJobSummary, StudioTextRequest,
    TermsPreviewResponse, TermsSaveResponse,
)
from .. import studio_service, term_service, track_service, user_service

router = APIRouter(prefix="/studio", tags=["studio"])


@router.post(
    "/imports/preview",
    response_model=ImportPreviewResponse,
    summary="Parse a .md of exercises and show what importing it would do (writes nothing, no LLM)",
)
async def preview_import_endpoint(request: StudioTextRequest, db: AsyncSession = Depends(get_db)) -> ImportPreviewResponse:
    track = await track_service.get_track(db, request.track)
    return await studio_service.preview_import(db, track, request.text)


@router.post(
    "/imports/normalize",
    response_model=NormalizeResponse,
    summary="Rewrite the invalid blocks and the text outside blocks of a .md in the import format with the cheap model "
            "(content copied, never invented); writes nothing — preview the result before importing",
)
async def normalize_import_endpoint(
    request: StudioTextRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> NormalizeResponse:
    await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    return await studio_service.normalize_import(track, request.text)


@router.post(
    "/imports",
    response_model=StudioJobSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Import the ready exercises of a .md (human-checked); the source is kept with the job",
)
async def import_endpoint(
    request: StudioTextRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StudioJobSummary:
    user = await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    job = await studio_service.import_exercises(db, track, user, request.text, request.source_name)
    return StudioJobSummary.model_validate(job)


@router.post(
    "/generations",
    response_model=StudioJobDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Generate exercises from a request .md with Claude; the result is a draft to save or discard",
)
async def generate_endpoint(
    request: StudioTextRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StudioJobDetail:
    user = await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    job = await studio_service.generate_draft(db, track, user, request.text, request.source_name)
    return studio_service.job_detail(job, track)


@router.post(
    "/generations/{job_id}/save",
    response_model=StudioJobSummary,
    summary="Store the kept items of a generation draft (AI-generated, to review)",
)
async def save_generation_endpoint(
    job_id: int,
    request: GenerationSaveRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StudioJobSummary:
    await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    return StudioJobSummary.model_validate(await studio_service.save_draft(db, track, job_id, request.keep))


@router.post(
    "/generations/{job_id}/items/{position}/regenerate",
    response_model=StudioJobDetail,
    summary="Write one draft item again with Claude (same spec, a different sentence, optional note); "
            "the cost is added to the job",
)
async def regenerate_item_endpoint(
    job_id: int,
    position: int,
    request: RegenerateItemRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StudioJobDetail:
    await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    job = await studio_service.regenerate_item(db, track, job_id, position, request.note)
    return studio_service.job_detail(job, track)


@router.post(
    "/generations/{job_id}/discard",
    response_model=StudioJobSummary,
    summary="Discard a generation draft",
)
async def discard_generation_endpoint(
    job_id: int,
    track: str = Query(description="Track code, e.g. 'ja'"),
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StudioJobSummary:
    await user_service.get_user(db, user_id)
    track_obj = await track_service.get_track(db, track)
    return StudioJobSummary.model_validate(await studio_service.discard_draft(db, track_obj, job_id))


@router.post(
    "/terms/preview",
    response_model=TermsPreviewResponse,
    summary="Vocabulary of a text, or of a .csv term list, in dictionary form, marked new or already known "
            "(writes nothing, no LLM)",
)
async def preview_terms_endpoint(request: StudioTextRequest, db: AsyncSession = Depends(get_db)) -> TermsPreviewResponse:
    track = await track_service.get_track(db, request.track)
    return await term_service.preview_terms(db, track, request.text)


@router.post(
    "/terms",
    response_model=TermsSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store the new terms of a text (no meanings yet) or of a .csv term list (with its meanings, also given to "
            "known terms without a human one); the source is kept with the job",
)
async def save_terms_endpoint(
    request: StudioTextRequest,
    user_id: int = Depends(user_service.current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TermsSaveResponse:
    user = await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, request.track)
    job, meaning_updates = await term_service.save_terms(db, track, user, request.text, request.source_name)
    return TermsSaveResponse.model_validate(job).model_copy(update={"meaning_updates": meaning_updates})


@router.get("/jobs", response_model=list[StudioJobSummary], summary="Past imports and generations of a track, most recent first")
async def list_jobs_endpoint(
    track: str = Query(description="Track code, e.g. 'ja'"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[StudioJobSummary]:
    track_obj = await track_service.get_track(db, track)
    return [StudioJobSummary.model_validate(job) for job in await studio_service.list_jobs(db, track_obj, limit)]


@router.get("/jobs/{job_id}", response_model=StudioJobDetail, summary="One job, with its source text (and its draft, for a generation)")
async def get_job_endpoint(
    job_id: int,
    track: str = Query(description="Track code, e.g. 'ja'"),
    db: AsyncSession = Depends(get_db),
) -> StudioJobDetail:
    track_obj = await track_service.get_track(db, track)
    return studio_service.job_detail(await studio_service.get_job(db, track_obj, job_id), track_obj)
