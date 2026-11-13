"""
Typed exercise payloads (D-12): one Pydantic model per exercise type, used
wherever a payload enters the system — Claude's `submit_new_exercises` items,
manual creation, demo data. Extra keys are ignored and dropped, so what is
stored is always the normalized model dump.

Track-specific types (e.g. Japanese kanji/romaji) live next to their track
(`tracks/japanese_payloads.py`); each `TrackSpec` maps the exercise types it
enables to their payload model.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BLANK = re.compile(r"_{2,}|＿+")  # the gap in a fill_blank sentence (ASCII or full-width)

# Difficulty scale shared by every track: 1 (first lessons) … 10 (advanced).
# Each track maps it to its own reference levels (Japanese: two per JLPT level).
MAX_DIFFICULTY = 10


class PayloadModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _unique(options: list[str]) -> list[str]:
    if len(set(options)) != len(options):
        raise ValueError("options must be unique")
    if any(not o for o in options):
        raise ValueError("options must not be empty")
    return options


class MultipleChoicePayload(PayloadModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str | None = None

    _unique_options = field_validator("options")(_unique)


class FillBlankPayload(PayloadModel):
    sentence_with_blank: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=6)
    correct: str
    explanation: str | None = None

    _unique_options = field_validator("options")(_unique)

    @model_validator(mode="after")
    def _check(self):
        if not BLANK.search(self.sentence_with_blank):
            raise ValueError("sentence_with_blank must contain a blank (___)")
        if self.correct not in self.options:
            raise ValueError("`correct` must match one of the `options`")
        return self


class TranslateRevPayload(PayloadModel):
    """A target-language sentence to translate; the answer is typed in the base language."""
    prompt: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    alternatives: list[str] = Field(default_factory=list)


def validate_payload(models: dict[str, type[PayloadModel]], exercise_type: str, payload: dict) -> dict:
    """Normalized payload for `exercise_type`; raises ValueError if the type is unknown or the payload invalid."""
    model = models.get(exercise_type)
    if model is None:
        raise ValueError(f"No payload model for exercise type '{exercise_type}'")
    return model.model_validate(payload).model_dump(exclude_none=True)
