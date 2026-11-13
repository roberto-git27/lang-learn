"""
FastAPI router for tracks (a target language studied from a base language).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import TrackResponse
from .. import track_service

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("", response_model=list[TrackResponse], summary="List enabled tracks and their exercise types")
async def list_tracks_endpoint(db: AsyncSession = Depends(get_db)) -> list[TrackResponse]:
    return [track_service.to_track_response(t) for t in await track_service.list_tracks(db)]
