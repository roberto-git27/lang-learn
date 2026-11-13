"""
Language-specific behavior, one module per track.

The database says *what* a track is (languages, enabled exercise types,
topics — see `tracks` / `track_exercise_types`); these modules say *how* the
code behaves for it (chat prompt, generation guidelines). A track row without
a spec here is a configuration error and fails loudly.
"""
from __future__ import annotations

from .base import TermCandidate, TrackSpec

__all__ = ["JAPANESE", "TRACK_SPECS", "TermCandidate", "TrackSpec", "get_track_spec"]
from .japanese import JAPANESE

TRACK_SPECS: dict[str, TrackSpec] = {spec.code: spec for spec in (JAPANESE,)}


def get_track_spec(code: str) -> TrackSpec:
    try:
        return TRACK_SPECS[code]
    except KeyError:
        raise LookupError(f"No TrackSpec registered for track '{code}'") from None
