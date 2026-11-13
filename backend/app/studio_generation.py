"""
Studio generation (Phase 9b), the pure part: which exercises to ask Claude
for, and whether what came back can be kept. No DB, no network — the
orchestration (reference examples, the Claude calls, the draft) lives in
`studio_service.py`.

Same split as the session agent: the plan is deterministic (one spec per
exercise: type, difficulty, topics, term), Claude only writes the content,
and every item is checked before it can reach the draft.
"""
from __future__ import annotations

import json

from .exercise_agent import check_generated_item
from .md_import import GenerationRequest, ParsedExercise, normalize_topic, phrase_from_payload
from .schemas import GeneratedExerciseItem, NewExerciseSpec
from .tracks import TrackSpec


def plan_specs(request: GenerationRequest, default_types: list[str]) -> list[NewExerciseSpec]:
    """
    One spec per exercise. With terms, each term gets `per_term` exercises
    and the types rotate so consecutive terms start from a different type;
    without terms, `count` exercises cycling through the types.
    """
    types = request.types or default_types
    base = {"difficulty": request.difficulty, "topics": request.topics}
    if not request.terms:
        return [
            NewExerciseSpec(spec_id=f"s{i + 1}", exercise_type=types[i % len(types)], **base)
            for i in range(request.count)
        ]
    specs = []
    for t, term in enumerate(request.terms):
        for k in range(request.per_term):
            specs.append(NewExerciseSpec(
                spec_id=f"s{len(specs) + 1}",
                exercise_type=types[(t + k) % len(types)],
                term=term.text,
                term_note=term.note,
                **base,
            ))
    return specs


def check_studio_item(
    track_spec: TrackSpec, spec: NewExerciseSpec, item: GeneratedExerciseItem, language_codes: set[str],
) -> tuple[dict | None, str | None]:
    """The session agent's checks (payload, level gate, both languages) plus: the term is really used."""
    payload, reason = check_generated_item(track_spec, spec, item, language_codes)
    if payload is not None and spec.term and spec.term not in json.dumps(payload, ensure_ascii=False):
        return None, f"the exercise does not use the term '{spec.term}'"
    return payload, reason


def to_parsed_exercise(
    position: int,
    spec: NewExerciseSpec,
    item: GeneratedExerciseItem | None,
    payload: dict | None,
    reason: str | None,
    track_spec: TrackSpec,
    target_language: str,
    base_language: str,
) -> ParsedExercise:
    """A generated item in the same shape as an imported block, so both share preview, duplicates and storage."""
    translations = {tr.language: tr.content.strip() for tr in (item.phrase_translations if item else [])}
    parsed = ParsedExercise(
        line=position,
        exercise_type=spec.exercise_type,
        difficulty=spec.difficulty,
        # The request's topics when it sets any; otherwise the ones the model detected.
        topics=spec.topics or list(dict.fromkeys(
            t for t in (normalize_topic(d) for d in (item.detected_topics if item else [])) if t
        )),
        phrase_target=translations.get(target_language),
        phrase_base=translations.get(base_language),
        term=spec.term,
    )
    if payload is None:
        parsed.errors.append(reason or "not generated")
        return parsed
    parsed.payload = payload
    parsed.phrase_target = phrase_from_payload(spec.exercise_type, payload) or parsed.phrase_target
    parsed.annotations = track_spec.annotations_for(spec.exercise_type, payload)
    return parsed
