from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from ..exercise_payloads import PayloadModel, validate_payload

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


@dataclass(frozen=True)
class TermCandidate:
    """A vocabulary item found in a text (see `TrackSpec.extract_terms`)."""
    lemma: str      # dictionary entry: the identity of the term, with `reading`
    reading: str    # of the lemma, in the track's phonetic script (Japanese: hiragana)
    written: str    # dictionary form as written in the text (Japanese: かみ even when the lemma is 髪)
    pos: str        # noun | proper_noun | pronoun | verb | i_adjective | na_adjective | adverb | prenominal | numeral


@dataclass(frozen=True)
class TrackSpec:
    """Code-side behavior of a track (the DB row holds its data)."""

    code: str
    chat_prompt_file: str
    # Appended to the gap-filling prompt: style/level rules for generated content.
    generation_guidelines: str
    # Payload model of every exercise type the track enables (D-12).
    payload_models: Mapping[str, type[PayloadModel]]
    # Per-type payload instructions for the gap-filling prompt.
    type_instructions: Mapping[str, str]
    # Reading aids for an exercise payload (e.g. furigana), stored in
    # `exercises.annotations`. None for tracks that need none.
    annotate_payload: Callable[[str, dict], dict] | None = None
    # Deterministic level gate for generated content: problems found (empty = OK).
    level_problems: Callable[[int, dict], list[str]] = field(default=lambda difficulty, payload: [])
    # Vocabulary (terms): the sentences of a text, its content words (dictionary
    # forms, deduplicated by lemma + reading), and the lowest difficulty whose
    # level gate accepts a text.
    split_sentences: Callable[[str], list[str]] = field(
        default=lambda text: [line.strip() for line in text.splitlines() if line.strip()]
    )
    extract_terms: Callable[[str], list[TermCandidate]] = field(default=lambda text: [])
    text_level: Callable[[str], int] = field(default=lambda text: 1)
    # Hand-made reading overrides (surface → reading), applied by every reading the track computes.
    set_reading_overrides: Callable[[dict[str, str]], None] = field(default=lambda overrides: None)
    # Problems of a reading override (empty = OK); a track without readings accepts none.
    reading_override_problems: Callable[[str, str], list[str]] = field(
        default=lambda surface, reading: ["This track has no computed readings"]
    )
    # A reading as stored (Japanese: katakana → hiragana).
    normalize_reading: Callable[[str], str] = field(default=lambda reading: reading)
    # A word typed by a human (a term list, with an optional reading) as one term; None when empty.
    dictionary_term: Callable[[str, str | None], TermCandidate | None] = field(
        default=lambda word, reading=None: (
            TermCandidate(lemma=word.strip(), reading=(reading or word).strip(), written=word.strip(), pos="expression")
            if word.strip() else None
        )
    )

    def chat_system_prompt(self) -> str:
        return (PROMPTS_DIR / self.chat_prompt_file).read_text(encoding="utf-8")

    def annotations_for(self, exercise_type: str, payload: dict) -> dict:
        return self.annotate_payload(exercise_type, payload) if self.annotate_payload else {}

    def validate_payload(self, exercise_type: str, payload: dict) -> dict:
        """Normalized payload; raises ValueError if invalid for the type."""
        return validate_payload(dict(self.payload_models), exercise_type, payload)
