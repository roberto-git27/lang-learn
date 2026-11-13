"""
FastAPI router for profiles (NOT authentication — see user_service.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import PinVerifyRequest, ProfileCreateRequest, ProfileResponse
from .. import track_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[ProfileResponse], summary="List profiles")
async def list_profiles_endpoint(db: AsyncSession = Depends(get_db)) -> list[ProfileResponse]:
    return [user_service.to_profile_response(u) for u in await user_service.list_profiles(db)]


@router.post(
    "", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED,
    summary="Create a profile (optional 4-digit PIN) enrolled in the given tracks",
)
async def create_profile_endpoint(
    request: ProfileCreateRequest, db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    tracks = [await track_service.get_track(db, code) for code in dict.fromkeys(request.tracks)]
    user = await user_service.create_profile(db, request.display_name, request.pin, tracks)
    return user_service.to_profile_response(user)


@router.post(
    "/{user_id}/verify-pin", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
    summary="Check a profile's PIN before switching to it (UI guard, not authentication)",
)
async def verify_pin_endpoint(
    user_id: int, request: PinVerifyRequest, db: AsyncSession = Depends(get_db),
) -> Response:
    user = await user_service.get_user(db, user_id)
    if user.pin_hash is not None and not user_service.verify_pin(request.pin, user.pin_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong PIN")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{user_id}/tracks/{track_code}", response_model=ProfileResponse,
    summary="Enroll a profile in a track, or mark it as the most recently used one",
)
async def use_track_endpoint(
    user_id: int, track_code: str, db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    user = await user_service.get_user(db, user_id)
    track = await track_service.get_track(db, track_code)
    await user_service.use_track(db, user, track)
    await db.refresh(user, attribute_names=["tracks"])
    return user_service.to_profile_response(user)
