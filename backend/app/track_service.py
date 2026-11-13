"""
Track lookups shared by routers, the exercise agent and the review services.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Track
from .schemas import TrackExerciseTypeResponse, TrackResponse


async def get_track(db: AsyncSession, code: str | None) -> Track:
    """Enabled track by code; 400 when missing, 404 when unknown or disabled."""
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A track is required")
    track = await db.scalar(select(Track).where(Track.code == code, Track.enabled.is_(True)))
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown track: {code}")
    return track


async def list_tracks(db: AsyncSession) -> list[Track]:
    result = await db.execute(select(Track).where(Track.enabled.is_(True)).order_by(Track.code))
    return list(result.scalars().all())


# Typed answers (translate, romaji) are slow at beginner level: at most this
# many per session, in both the chat agent and the Practice tab.
MAX_TYPED_PER_SESSION = 2


def track_type_codes(track: Track) -> list[str]:
    """Exercise types the track enables, in a stable order."""
    return sorted(tet.exercise_type.code for tet in track.exercise_types)


def track_light_type_codes(track: Track) -> list[str]:
    """Enabled types answered by picking an option (no typing) — quick to do."""
    return sorted(tet.exercise_type.code for tet in track.exercise_types if not tet.is_typed_input)


def track_typed_type_ids(track: Track) -> list[int]:
    """ids of the enabled types answered by typing."""
    return [tet.exercise_type_id for tet in track.exercise_types if tet.is_typed_input]


def track_exercise_type_id(track: Track, code: str) -> int:
    """id of an exercise type the track enables; 400 if the track doesn't enable it."""
    for tet in track.exercise_types:
        if tet.exercise_type.code == code:
            return tet.exercise_type_id
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Exercise type '{code}' is not available on track '{track.code}'",
    )


def to_track_response(track: Track) -> TrackResponse:
    return TrackResponse(
        code=track.code,
        name=track.name,
        target_language=track.target_language.code,
        base_language=track.base_language.code,
        exercise_types=[
            TrackExerciseTypeResponse(
                code=tet.exercise_type.code, name=tet.exercise_type.name, is_typed_input=tet.is_typed_input,
            )
            for tet in sorted(track.exercise_types, key=lambda t: t.exercise_type.code)
        ],
    )
