"""
Unit tests for profile PIN hashing (`app.user_service`), the track helpers
(`app.track_service`, on in-memory ORM objects) and the track spec registry
(`app.tracks`). No DB/network.
"""
import pytest
from fastapi import HTTPException

from app.models import ExerciseType, Language, Track, TrackExerciseType
from app.track_service import (
    to_track_response,
    track_exercise_type_id,
    track_light_type_codes,
    track_type_codes,
)
from app.tracks import TRACK_SPECS, get_track_spec
from app.user_service import hash_pin, verify_pin


# ---------------------------------------------------------------------------
# PIN hashing
# ---------------------------------------------------------------------------
def test_pin_roundtrip():
    stored = hash_pin("0420")
    assert verify_pin("0420", stored)
    assert not verify_pin("0421", stored)


def test_pin_hash_is_salted():
    assert hash_pin("1234") != hash_pin("1234")


def test_pin_hash_does_not_contain_the_pin():
    assert "1234" not in hash_pin("1234").split("$")[-1]


@pytest.mark.parametrize("stored", ["", "garbage", "md5$1$00$00", "pbkdf2_sha256$1$zz$00"])
def test_verify_pin_rejects_malformed_hashes(stored):
    try:
        assert verify_pin("1234", stored) is False
    except ValueError:
        pytest.fail("verify_pin must not raise on malformed input")


# ---------------------------------------------------------------------------
# Track helpers
# ---------------------------------------------------------------------------
def _japanese_track() -> Track:
    types = {
        "multiple_choice": (1, False),
        "fill_blank": (2, False),
        "translate_rev": (3, True),
    }
    track = Track(
        id=1, code="ja", name="日本語 · Japanese",
        target_language=Language(id=2, code="ja", name="Japanese"),
        base_language=Language(id=1, code="it", name="Italian"),
    )
    track.exercise_types = [
        TrackExerciseType(
            track_id=1, exercise_type_id=type_id, is_typed_input=typed,
            exercise_type=ExerciseType(id=type_id, code=code, name=code.replace("_", " ").title()),
        )
        for code, (type_id, typed) in types.items()
    ]
    return track


def test_track_type_codes_are_sorted_and_complete():
    assert track_type_codes(_japanese_track()) == ["fill_blank", "multiple_choice", "translate_rev"]


def test_track_light_types_exclude_typed_input():
    assert track_light_type_codes(_japanese_track()) == ["fill_blank", "multiple_choice"]


def test_track_exercise_type_id_resolves_enabled_type():
    assert track_exercise_type_id(_japanese_track(), "translate_rev") == 3


def test_track_exercise_type_id_rejects_type_outside_track():
    with pytest.raises(HTTPException) as exc:
        track_exercise_type_id(_japanese_track(), "translate_fwd")
    assert exc.value.status_code == 400


def test_to_track_response_exposes_languages_and_types():
    response = to_track_response(_japanese_track())
    assert (response.code, response.target_language, response.base_language) == ("ja", "ja", "it")
    assert [t.code for t in response.exercise_types if t.is_typed_input] == ["translate_rev"]


# ---------------------------------------------------------------------------
# Track spec registry
# ---------------------------------------------------------------------------
def test_every_registered_spec_has_a_readable_chat_prompt():
    for spec in TRACK_SPECS.values():
        assert spec.chat_system_prompt().strip()
        assert spec.generation_guidelines.strip()


def test_get_track_spec_unknown_code_fails_loudly():
    with pytest.raises(LookupError):
        get_track_spec("xx")
