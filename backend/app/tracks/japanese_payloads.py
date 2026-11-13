"""
Japanese-only exercise types and the level check for generated content.

Every type here has an explicit `focus`: the word the exercise is about,
which must appear in `sentence` — the learner always sees the word inside a
real sentence, underlined, never in isolation.
"""
from __future__ import annotations

import re

from pydantic import Field, field_validator, model_validator

from ..exercise_payloads import PayloadModel
from .japanese_text import KANJI, has_kanji, romaji

_KANA_ONLY = re.compile(r"^[\u3040-\u309f\u30a0-\u30ffー]+$")
_NOT_ROMAJI = re.compile(r"[^a-zāīūēō' ]")

# Difficulty scale (1–10) → JLPT, two steps per JLPT level:
#   1 first lessons (LEVEL_1_KANJI)   2 JLPT N5 (N5_KANJI)
#   3–4 N4   5–6 N3   7–8 N2   9–10 N1
# Levels 1–2 are gated deterministically by kanji; above that there is no list.

# Kanji of the first chapters of any course: numbers, days, and the basic
# words of a self-introduction (人, 学生, 先生, 大/小, 山/川, 田 for 山田/田中).
LEVEL_1_KANJI = frozenset("一二三四五六七八九十百千円日月火水木金土人本学生先大小山川田中上下子女男私")

# Level 2: the JLPT N5 set (the first ~100 kanji of any course), plus 田,
# which textbooks use from lesson one in common names even though JLPT lists
# place it later.
N5_KANJI = LEVEL_1_KANJI | frozenset(
    "一二三四五六七八九十百千万円年月日火水木金土曜時分半今何毎週午前後上下中外右左"
    "東西南北名人男女子父母友学校生先大小高安長新古多少行来見聞読書話食飲買休言入出"
    "立山川天気雨花電車道駅国語白本店社会目耳口手足力私"
)


class _FocusPayload(PayloadModel):
    sentence: str = Field(min_length=1)
    focus: str = Field(min_length=1)
    explanation: str | None = None

    @model_validator(mode="after")
    def _focus_in_sentence(self):
        if self.focus not in self.sentence:
            raise ValueError("`focus` must appear in `sentence`")
        return self


class _FourOptions(_FocusPayload):
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)

    @field_validator("options")
    @classmethod
    def _unique(cls, options: list[str]) -> list[str]:
        if len(set(options)) != len(options) or any(not o for o in options):
            raise ValueError("options must be unique and non-empty")
        return options


class KanjiReadingPayload(_FourOptions):
    """The focus is written with kanji; options are readings in kana."""

    @model_validator(mode="after")
    def _check(self):
        if not has_kanji(self.focus):
            raise ValueError("kanji_reading: `focus` must contain kanji")
        if not all(_KANA_ONLY.match(o) for o in self.options):
            raise ValueError("kanji_reading: options must be kana only")
        return self


class KanjiWritingPayload(_FourOptions):
    """The focus is written in kana; options are spellings with kanji."""

    @model_validator(mode="after")
    def _check(self):
        if not _KANA_ONLY.match(self.focus):
            raise ValueError("kanji_writing: `focus` must be kana only")
        if not all(has_kanji(o) for o in self.options):
            raise ValueError("kanji_writing: every option must contain kanji")
        return self


class RomajiInputPayload(_FocusPayload):
    """
    Type the focus in romaji. `expected`/`accepted` are always computed here
    from the reading (never taken from the LLM or the author).
    """
    expected: str | None = None
    accepted: list[str] | None = None

    @model_validator(mode="after")
    def _compute_answer(self):
        self.expected, self.accepted = romaji(self.focus)
        if not self.expected or _NOT_ROMAJI.search(self.expected):
            raise ValueError("romaji_input: `focus` must be kana/kanji text that can be romanized")
        return self


# ---------------------------------------------------------------------------
# Level check
# ---------------------------------------------------------------------------
_DISPLAY_FIELDS = ("question", "sentence", "sentence_with_blank", "prompt", "focus")


_ALLOWED_KANJI = {1: LEVEL_1_KANJI, 2: N5_KANJI}


def level_problems(difficulty: int, payload: dict) -> list[str]:
    """
    Deterministic level gate for generated content: at difficulty 1–2 every
    kanji shown to the learner must be in that level's set. Explanations are
    excluded (shown after answering). Empty list = OK.
    """
    allowed = _ALLOWED_KANJI.get(difficulty)
    if allowed is None:
        return []
    texts = [payload.get(f) for f in _DISPLAY_FIELDS] + list(payload.get("options") or [])
    above = sorted({ch for t in texts if isinstance(t, str) for ch in KANJI.findall(t)} - allowed)
    return [f"kanji above level {difficulty}: {''.join(above)}"] if above else []


def text_level(text: str) -> int:
    """
    Lowest difficulty whose level gate accepts every kanji of `text`: 1 (first
    lessons), 2 (N5), or 3 meaning "above N5" — there is no list beyond N5,
    so 3 is a lower bound (grammar and vocabulary are not measured).
    """
    kanji = set(KANJI.findall(text))
    if kanji <= LEVEL_1_KANJI:
        return 1
    return 2 if kanji <= N5_KANJI else 3

