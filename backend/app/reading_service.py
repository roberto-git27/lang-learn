"""
Hand-made reading overrides (Phase 9): a word whose computed reading is
wrong (五本 read ごぽん) gets the right one (ごほん) everywhere in its track —
furigana and the romaji of `romaji_input` exercises.

The overrides live in `reading_overrides` and are handed to the track's text
module (`TrackSpec.set_reading_overrides`), which applies them to every
reading it computes. That registry is process-wide: it is loaded at startup
(`load_all`) and replaced after every change, which is enough for the single
backend process this POC runs (several workers would each need a reload).

Adding or removing an override recomputes the stored payload (romaji) and
annotations of the track's exercises that contain the word, so nothing shown
keeps the old reading. Term readings (the vocabulary's identity) are left
as they are.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Exercise, ExerciseType, ReadingOverride, Track, User
from .tracks import TRACK_SPECS, get_track_spec

log = logging.getLogger(__name__)


async def _publish(db: AsyncSession, track: Track) -> None:
    rows = (await db.execute(select(ReadingOverride).where(ReadingOverride.track_id == track.id))).scalars()
    get_track_spec(track.code).set_reading_overrides({row.surface: row.reading for row in rows})


async def load_all(db: AsyncSession) -> None:
    """Hands every track's overrides to its text module (startup)."""
    rows = (await db.execute(select(ReadingOverride, Track.code).join(Track, Track.id == ReadingOverride.track_id))).all()
    by_track: dict[str, dict[str, str]] = {code: {} for code in TRACK_SPECS}
    for row, code in rows:
        by_track.setdefault(code, {})[row.surface] = row.reading
    for code, overrides in by_track.items():
        if code in TRACK_SPECS:
            TRACK_SPECS[code].set_reading_overrides(overrides)


async def list_overrides(db: AsyncSession, track: Track) -> list[ReadingOverride]:
    result = await db.execute(
        select(ReadingOverride).where(ReadingOverride.track_id == track.id).order_by(ReadingOverride.surface)
    )
    return list(result.scalars().all())


async def _refresh_exercises(db: AsyncSession, track: Track, surface: str) -> int:
    """Recomputes payload and annotations of the track's exercises containing `surface`; returns how many changed."""
    spec = get_track_spec(track.code)
    rows = (await db.execute(
        select(Exercise, ExerciseType.code)
        .join(ExerciseType, ExerciseType.id == Exercise.exercise_type_id)
        .where(Exercise.track_id == track.id, cast(Exercise.payload, String).contains(surface))
    )).all()
    changed = 0
    for exercise, type_code in rows:
        payload = exercise.payload
        try:
            payload = spec.validate_payload(type_code, payload)   # recomputes derived fields (romaji)
        except Exception as exc:   # an old payload the current model rejects: keep it, refresh the furigana only
            log.warning("Exercise %s keeps its payload: %s", exercise.id, exc)
        annotations = spec.annotations_for(type_code, payload)
        if payload != exercise.payload or annotations != exercise.annotations:
            exercise.payload, exercise.annotations = payload, annotations
            changed += 1
    return changed


async def set_override(db: AsyncSession, track: Track, user: User, surface: str, reading: str) -> tuple[ReadingOverride, int]:
    """Adds or replaces the override of `surface`; returns it and how many exercises were updated."""
    spec = get_track_spec(track.code)
    surface, reading = surface.strip(), reading.strip()
    problems = spec.reading_override_problems(surface, reading)
    if problems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(problems))
    reading = spec.normalize_reading(reading)
    override = await db.scalar(
        select(ReadingOverride).where(ReadingOverride.track_id == track.id, ReadingOverride.surface == surface)
    )
    if override is None:
        override = ReadingOverride(track_id=track.id, surface=surface, reading=reading, user_id=user.id)
        db.add(override)
    else:
        override.reading, override.user_id = reading, user.id
    await db.flush()
    await _publish(db, track)
    try:
        changed = await _refresh_exercises(db, track, surface)
        await db.commit()
    except Exception:
        await db.rollback()
        await _publish(db, track)
        raise
    await db.refresh(override, attribute_names=["user"])
    return override, changed


async def delete_override(db: AsyncSession, track: Track, override_id: int) -> int:
    """Removes an override (the computed reading comes back); returns how many exercises were updated."""
    override = await db.scalar(
        select(ReadingOverride).where(ReadingOverride.id == override_id, ReadingOverride.track_id == track.id)
    )
    if override is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reading override {override_id} not found")
    surface = override.surface
    await db.delete(override)
    await db.flush()
    await _publish(db, track)
    try:
        changed = await _refresh_exercises(db, track, surface)
        await db.commit()
    except Exception:
        await db.rollback()
        await _publish(db, track)
        raise
    return changed
