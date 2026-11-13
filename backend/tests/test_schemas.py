"""
Unit tests for the generic exercise payload models (`exercise_payloads.py`)
and the profile creation/PIN requests. Pure Pydantic validation, no
DB/network — same spirit as the rest of `backend/tests/`.
"""
import pytest
from pydantic import ValidationError

from app.exercise_payloads import FillBlankPayload, MultipleChoicePayload
from app.schemas import PinVerifyRequest, ProfileCreateRequest


# ---------------------------------------------------------------------------
# MultipleChoicePayload
# ---------------------------------------------------------------------------
def test_multiple_choice_valid():
    payload = MultipleChoicePayload(
        question="Come si dice 'scuola'?", options=["がっこう", "がこう", "かっこう", "がっこ"], correct_index=0,
    )
    assert payload.correct_index == 0


def test_multiple_choice_rejects_wrong_option_count():
    with pytest.raises(ValidationError):
        MultipleChoicePayload(question="Q", options=["a", "b", "c"], correct_index=0)


def test_multiple_choice_rejects_out_of_range_correct_index():
    with pytest.raises(ValidationError):
        MultipleChoicePayload(question="Q", options=["a", "b", "c", "d"], correct_index=4)


def test_multiple_choice_rejects_duplicate_options():
    with pytest.raises(ValidationError):
        MultipleChoicePayload(question="Q", options=["a", "a", "c", "d"], correct_index=0)


# ---------------------------------------------------------------------------
# FillBlankPayload
# ---------------------------------------------------------------------------
def test_fill_blank_valid():
    payload = FillBlankPayload(sentence_with_blank="わたし___がくせいです", options=["も", "の", "を"], correct="も")
    assert payload.correct == "も"


def test_fill_blank_rejects_correct_not_in_options():
    with pytest.raises(ValidationError):
        FillBlankPayload(sentence_with_blank="わたし___がくせいです", options=["も", "の", "を"], correct="は")


def test_fill_blank_rejects_too_few_options():
    with pytest.raises(ValidationError):
        FillBlankPayload(sentence_with_blank="わたし___がくせいです", options=["も"], correct="も")


def test_fill_blank_requires_a_blank():
    with pytest.raises(ValidationError):
        FillBlankPayload(sentence_with_blank="わたしもがくせいです", options=["も", "の"], correct="も")


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
def test_profile_create_strips_name_and_accepts_no_pin():
    req = ProfileCreateRequest(display_name="  Roberto ", tracks=["ja"])
    assert req.display_name == "Roberto"
    assert req.pin is None


def test_profile_create_rejects_blank_name():
    with pytest.raises(ValidationError):
        ProfileCreateRequest(display_name="   ", tracks=["ja"])


def test_profile_create_requires_at_least_one_track():
    with pytest.raises(ValidationError):
        ProfileCreateRequest(display_name="Roberto", tracks=[])


@pytest.mark.parametrize("pin", ["123", "12345", "12a4", ""])
def test_profile_create_rejects_malformed_pin(pin):
    with pytest.raises(ValidationError):
        ProfileCreateRequest(display_name="Roberto", pin=pin, tracks=["ja"])


def test_pin_verify_request_accepts_four_digits():
    assert PinVerifyRequest(pin="0420").pin == "0420"
