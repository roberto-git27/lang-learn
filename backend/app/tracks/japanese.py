from ..exercise_payloads import FillBlankPayload, MultipleChoicePayload, TranslateRevPayload
from .base import TrackSpec
from .japanese_payloads import (
    LEVEL_1_KANJI,
    N5_KANJI,
    KanjiReadingPayload,
    KanjiWritingPayload,
    RomajiInputPayload,
    level_problems,
    text_level,
)
from .japanese_text import (
    annotate_payload, dictionary_term, to_hiragana, extract_terms, reading_override_problems, set_reading_overrides, split_sentences,
)

_GUIDELINES = f"""\
Track: Japanese studied by an Italian speaker.

Levels (the requested difficulty of each exercise, 1–10, two steps per JLPT level):
- 1 = first lessons. Very short sentences (max ~6 words), polite です/ます form, everyday vocabulary
  (greetings, self-introduction, family, school, numbers, days). Write mostly in hiragana/katakana.
  You may ONLY use these kanji: {"".join(sorted(LEVEL_1_KANJI))}.
- 2 = rest of JLPT N5: simple connected sentences. You may ONLY use these kanji:
  {"".join(sorted(N5_KANJI))}.
- 3–4 = JLPT N4 (3 = early N4, 4 = consolidated N4). 5–6 = JLPT N3. 7–8 = JLPT N2. 9–10 = JLPT N1.
At levels 1–2 an exercise using any other kanji (distractors included) is rejected automatically.

Rules:
- Every exercise is built around one natural sentence, which is also the phrase you return in
  `phrase_translations` (Japanese + its Italian translation). The learner sees the Italian
  translation on request, so it must match the sentence exactly.
- Questions, explanations and translations are written in Italian.
- Never require typing Japanese: typed answers are in Italian or in romaji.
- Distractors must be plausible for a learner but clearly wrong in context (typical mistakes:
  wrong particle, wrong conjugation, missing long vowel or small っ, similar-looking kanji);
  exactly one correct answer.
- Do not add readings (furigana/romaji) to the Japanese text: they are computed automatically.
"""

_TYPE_INSTRUCTIONS = {
    "multiple_choice": (
        '"multiple_choice" payload: "question" (Italian, may quote Japanese), "options" (exactly 4, '
        '1 correct + 3 plausible distractors), "correct_index" (0-3), "explanation" (Italian).'
    ),
    "fill_blank": (
        '"fill_blank" payload: "sentence_with_blank" (the Japanese sentence with ___ where the word is '
        'missing), "options" (3-4 kana/kanji options), "correct" (must match one of "options"), '
        '"explanation" (Italian, brief grammar note).'
    ),
    "translate_rev": (
        '"translate_rev" payload: "prompt" (the Japanese sentence), "expected" (its Italian translation), '
        '"alternatives" (other acceptable Italian translations).'
    ),
    "kanji_reading": (
        '"kanji_reading" payload: "sentence" (Japanese), "focus" (a whole word of the sentence written with kanji, '
        'with its okurigana — e.g. 三つ, not 三 — copied exactly as it appears), "options" (exactly 4 readings in hiragana: the correct one + 3 typical '
        'mistakes, e.g. がっこう/がこう/がっこ/かっこう), "correct_index" (0-3), "explanation" (Italian).'
    ),
    "kanji_writing": (
        '"kanji_writing" payload: "sentence" (Japanese, with the focus word written in hiragana), "focus" '
        '(that hiragana word, copied exactly), "options" (exactly 4 spellings with kanji: the correct one + 3 '
        'look-alike or same-sound distractors), "correct_index" (0-3), "explanation" (Italian). At difficulty 1–2 '
        'the distractors too may only use the allowed kanji (e.g. 日/目, 木/本, 大学 vs 大字).'
    ),
    "romaji_input": (
        '"romaji_input" payload: "sentence" (Japanese), "focus" (a word of the sentence, copied exactly, '
        'that the learner will type in romaji — names and simple words work best), "explanation" (Italian, '
        'optional). Do not provide the romaji: it is computed automatically.'
    ),
}

JAPANESE = TrackSpec(
    code="ja",
    chat_prompt_file="ja/chat_negotiation.md",
    generation_guidelines=_GUIDELINES,
    payload_models={
        "multiple_choice": MultipleChoicePayload,
        "fill_blank": FillBlankPayload,
        "translate_rev": TranslateRevPayload,
        "kanji_reading": KanjiReadingPayload,
        "kanji_writing": KanjiWritingPayload,
        "romaji_input": RomajiInputPayload,
    },
    type_instructions=_TYPE_INSTRUCTIONS,
    annotate_payload=annotate_payload,
    level_problems=level_problems,
    split_sentences=split_sentences,
    text_level=text_level,
    extract_terms=extract_terms,
    dictionary_term=dictionary_term,
    set_reading_overrides=set_reading_overrides,
    normalize_reading=to_hiragana,
    reading_override_problems=reading_override_problems,
)
