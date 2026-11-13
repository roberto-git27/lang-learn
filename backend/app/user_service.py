"""
Profiles: lightweight identities, NOT authentication.

A profile has a display name and an optional 4-digit PIN. The PIN only guards
switching profiles in the UI (`POST /users/{id}/verify-pin`); afterwards the
frontend sends the profile id in the `X-User-Id` header, which the backend
trusts. Anyone able to send that header by hand bypasses the PIN — acceptable
for a private, single-tenant instance, never a security boundary.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Track, User, UserTrack
from .schemas import ProfileResponse

_PIN_ITERATIONS = 200_000


# ---------------------------------------------------------------------------
# PIN hashing — pure functions (standard library only)
# ---------------------------------------------------------------------------
def hash_pin(pin: str) -> str:
    """PBKDF2-SHA256 with a random salt, stored as 'pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>'."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _PIN_ITERATIONS)
    return f"pbkdf2_sha256${_PIN_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """False for a wrong PIN or a malformed stored hash — never raises."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
def to_profile_response(user: User) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        display_name=user.display_name,
        has_pin=user.pin_hash is not None,
        tracks=[ut.track.code for ut in user.tracks],
    )


async def list_profiles(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(func.lower(User.display_name)))
    return list(result.scalars().all())


async def get_user(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Profile {user_id} not found")
    return user


async def create_profile(db: AsyncSession, display_name: str, pin: str | None, tracks: list[Track]) -> User:
    existing = await db.scalar(select(User).where(func.lower(User.display_name) == display_name.lower()))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Profile '{display_name}' already exists")

    user = User(display_name=display_name, pin_hash=hash_pin(pin) if pin else None)
    db.add(user)
    await db.flush()
    for track in tracks:
        db.add(UserTrack(user_id=user.id, track_id=track.id))
    await db.commit()
    await db.refresh(user, attribute_names=["tracks"])
    return user


async def use_track(db: AsyncSession, user: User, track: Track) -> None:
    """Enrolls the profile in the track if needed and marks it as the most recently used one."""
    user_track = await db.get(UserTrack, (user.id, track.id))
    if user_track is None:
        db.add(UserTrack(user_id=user.id, track_id=track.id))
    else:
        user_track.last_used_at = datetime.now(timezone.utc)
    await db.commit()


async def current_user_id(x_user_id: int | None = Header(default=None)) -> int:
    """FastAPI dependency: the selected profile id from the `X-User-Id` header (not verified — see module docstring)."""
    if x_user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Select a profile first (X-User-Id header)")
    return x_user_id
