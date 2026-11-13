"""
Claude API calls used by the exercise agent and the Studio generation.

Both calls (`generate_exercises_for_gap`, `translate_terms`) get their
structured output as a tool call: the prompt names the tool, `tool_choice` is
`auto` (the 5.5 models reject a forced choice) and `_call_tool` checks that the
call was made, asking again once if it was not. The tool input arrives already
parsed and is validated with Pydantic by the caller. No temperature (rejected
by the 5.5 models): `output_config.effort` sets how much the model thinks.
"""
from __future__ import annotations

import json
import logging

from anthropic import Anthropic
from pydantic import ValidationError

from .config import settings
from .exercise_payloads import MAX_DIFFICULTY
from .schemas import NewExerciseSpec, SubmitNewExercisesInput

logger = logging.getLogger(__name__)

# Singleton client — the SDK is thread-safe and manages its own connection pool
_client = Anthropic(api_key=settings.anthropic_api_key)

# Models that accept the server-side refusal fallback: when a safety classifier
# declines a request, the API retries it on a suitable model by itself.
# Claude Haiku 5.5 has no server-side fallback.
_FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _call_tool(*, tool: dict, prompt: str, max_tokens: int, system: str | None = None) -> tuple[dict, dict]:
    """
    One generation-model call that must end in a call to `tool`. Returns
    `(tool_input, usage)`. With `tool_choice` `auto` a call is not
    guaranteed: a reply without it is asked once more, then it is an error.
    Streams (thinking counts toward `max_tokens`, which can get large) and
    keeps only the final message.
    """
    model = settings.claude_generation_model
    request = {
        "model": model,
        "max_tokens": max_tokens,
        "tools": [tool],
        "tool_choice": {"type": "auto"},
        "output_config": {"effort": settings.claude_generation_effort},
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        request["system"] = system
    usage = {"input_tokens": 0, "output_tokens": 0}

    for _attempt in range(2):
        if model in _FALLBACK_MODELS:
            stream_ctx = _client.beta.messages.stream(
                **request, betas=[_FALLBACK_BETA], extra_body={"fallbacks": "default"},
            )
        else:
            stream_ctx = _client.messages.stream(**request)
        with stream_ctx as stream:
            response = stream.get_final_message()

        usage["input_tokens"] += getattr(response.usage, "input_tokens", 0) or 0
        usage["output_tokens"] += getattr(response.usage, "output_tokens", 0) or 0

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) or "unspecified"
            raise ValueError(f"Claude declined the request (refusal, category: {category})")
        if response.stop_reason == "max_tokens":
            raise ValueError(f"Claude's reply was cut off at max_tokens={max_tokens} before {tool['name']} was complete")

        block = next(
            (b for b in response.content if getattr(b, "type", None) == "tool_use" and b.name == tool["name"]),
            None,
        )
        if block is not None:
            return block.input, usage
        logger.warning("No %s call in Claude's reply (stop_reason=%s), asking again", tool["name"], response.stop_reason)

    raise ValueError(f"Claude did not return a {tool['name']} tool call")


# ---------------------------------------------------------------------------
# Exercise agent (Phase 1) — gap-filling via tool use
#
# Used by `exercise_agent.py` to fill exactly the gap left after the
# deterministic DB lookup — never to generate a full session.
# ---------------------------------------------------------------------------
def _build_gap_prompt(
    specs: list[NewExerciseSpec],
    source_language: str,
    target_language: str,
    track_guidelines: str,
    type_instructions: dict[str, str],
    reference_examples: dict[str, list[dict]],
    already_generated_hints: list[str] | None,
    instructions: str | None = None,
) -> str:
    """Builds the user prompt describing exactly which exercises to generate."""
    lines = [
        f"Generate {len(specs)} NEW exercise(s) for a language-learning app. The learner "
        f"studies '{target_language}' (target language); their base language is "
        f"'{source_language}' (source language).",
        "",
        track_guidelines.strip(),
        "",
        "Each exercise below needs its own brand-new, independent phrase — do NOT "
        "reuse the same phrase/sentence across items, and do not produce any "
        "exercise beyond exactly what is listed.",
        "",
        "Exercises to generate (one brand-new phrase EACH):",
    ]
    for spec in specs:
        topics_str = ", ".join(spec.topics) if spec.topics else "free choice"
        term = f", term={spec.term!r}" + (f" ({spec.term_note})" if spec.term_note else "") if spec.term else ""
        lines.append(
            f"- spec_id={spec.spec_id!r}: type={spec.exercise_type}, "
            f"difficulty={spec.difficulty}/{MAX_DIFFICULTY}, topics={topics_str}{term}"
        )
    if any(spec.term for spec in specs):
        lines += [
            "",
            "An exercise with a `term` must be about that term: the term (or a word written with it) "
            "must appear in the exercise, and where the type has a `focus` the focus must contain it. "
            "Vary the sentences and the words across the exercises of the same term.",
        ]

    lines.append("")
    lines.append("Payload fields required per exercise type:")
    for type_code in sorted({s.exercise_type for s in specs}):
        instr = type_instructions.get(type_code)
        if instr:
            lines.append(f"- {instr}")

    if reference_examples:
        lines.append("")
        lines.append(
            "Style reference — existing exercises of the same type, verified by a human "
            "where possible (match tone and structure, do NOT copy their content):"
        )
        for type_code, examples in reference_examples.items():
            for ex in examples:
                lines.append(f"  [{type_code}] {json.dumps(ex, ensure_ascii=False)}")

    if already_generated_hints:
        lines.append("")
        lines.append(
            "Phrases already generated in a previous round for this same session — "
            "do NOT repeat these or anything too similar:"
        )
        for hint in already_generated_hints:
            lines.append(f"  - {hint}")

    if instructions:
        lines += [
            "",
            "Request from the teacher (follow it unless it conflicts with the rules above):",
            instructions.strip(),
        ]

    lines.append("")
    lines.append(
        "Call the submit_new_exercises tool with exactly one entry per spec_id "
        "listed above (echo the exact spec_id back for each). Each entry's "
        "`phrase_translations` must include BOTH the source and target language."
    )
    return "\n".join(lines)


_SUBMIT_NEW_EXERCISES_TOOL = {
    "name": "submit_new_exercises",
    "description": (
        "Submit the newly generated exercises that fill the requested gap. "
        "Call this exactly once, with one entry per requested spec_id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "exercises": {
                "type": "array",
                "description": "One entry per requested spec_id.",
                "items": {
                    "type": "object",
                    "properties": {
                        "spec_id": {
                            "type": "string",
                            "description": "Must exactly match one of the requested spec_ids.",
                        },
                        "phrase_translations": {
                            "type": "array",
                            "description": (
                                "Translations for this exercise's brand-new phrase — "
                                "must include an entry for BOTH the source and target language."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "language": {"type": "string"},
                                    "content": {"type": "string"},
                                    "ipa": {"type": ["string", "null"]},
                                },
                                "required": ["language", "content"],
                            },
                        },
                        "detected_topics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Extra topic codes (snake_case) this phrase covers, beyond the ones requested.",
                        },
                        "payload": {
                            "type": "object",
                            "description": "Exercise payload — fields depend on this item's exercise_type (see the instructions in the prompt).",
                        },
                    },
                    "required": ["spec_id", "phrase_translations", "payload"],
                },
            },
        },
        "required": ["exercises"],
    },
}


def generate_exercises_for_gap(
    specs: list[NewExerciseSpec],
    source_language: str,
    target_language: str,
    track_guidelines: str,
    type_instructions: dict[str, str],
    reference_examples: dict[str, list[dict]] | None = None,
    already_generated_hints: list[str] | None = None,
    instructions: str | None = None,
) -> tuple[list, dict]:
    """
    Ask Claude (a `submit_new_exercises` tool call) to generate exactly the
    exercises described by `specs`.

    Returns `(items, usage)`:
    - `items`: `list[GeneratedExerciseItem]` — only what Claude actually
      returned. The caller matches `spec_id`s against what was requested and
      decides whether a top-up call is needed for anything missing.
    - `usage`: `{"input_tokens": int, "output_tokens": int}`.

    `source_language`/`target_language` are the track's base and target
    languages; `track_guidelines` and `type_instructions` come from the
    track's `TrackSpec`; `instructions` is the Studio's free-text request.
    Items are returned unvalidated: the caller checks each payload against
    the track's payload models.
    """
    prompt = _build_gap_prompt(
        specs, source_language, target_language, track_guidelines, type_instructions,
        reference_examples or {}, already_generated_hints, instructions,
    )
    # Room for the thinking as well as the exercises themselves.
    max_tokens = min(8000 + len(specs) * 800, 64000)

    tool_input, usage = _call_tool(
        tool=_SUBMIT_NEW_EXERCISES_TOOL,
        prompt=prompt,
        max_tokens=max_tokens,
        system=(
            "You are a high-quality language-exercise generator for a language-learning "
            "platform. Answer by calling the submit_new_exercises tool exactly once, with "
            "natural, idiomatic phrases appropriate to each exercise's difficulty level."
        ),
    )

    # Not a strict tool: each payload's fields depend on its exercise type, so
    # the schema leaves `payload` open and the validation happens here.
    try:
        parsed = SubmitNewExercisesInput.model_validate(tool_input)
    except ValidationError as e:
        logger.error("submit_new_exercises input failed validation: %s\nRaw: %s", e, tool_input)
        raise ValueError(f"submit_new_exercises input does not match the expected schema: {e}") from e

    return parsed.exercises, usage


# ---------------------------------------------------------------------------
# Vocabulary (D-24) — meanings of new terms, asked once and stored
# ---------------------------------------------------------------------------
_SUBMIT_TERM_MEANINGS_TOOL = {
    "name": "submit_term_meanings",
    "description": "Submit the meaning of every term, one entry per term_id. Call this exactly once.",
    # Strict: the arguments always match the schema.
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "meanings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term_id": {"type": "integer"},
                        "meaning": {"type": "string", "description": "Short dictionary-style gloss."},
                    },
                    "required": ["term_id", "meaning"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["meanings"],
        "additionalProperties": False,
    },
}


def translate_terms(terms: list[dict], target_language: str, base_language: str) -> tuple[dict[int, str], dict]:
    """
    Meanings of vocabulary terms (dicts with term_id, written, reading, pos,
    example) in the base language, via a submit_term_meanings tool call. Returns
    ({term_id: meaning}, usage); ids not in the request are ignored.
    """
    lines = [
        f"Give the meaning in '{base_language}' of each '{target_language}' vocabulary term below, "
        "for a learner's glossary.",
        "",
        "Rules:",
        "- A short dictionary-style gloss (1–4 words; two senses separated by '; ' only if both are common).",
        "- The sense used in the example sentence comes first.",
        "- Verbs in the infinitive, adjectives in the base form; proper nouns as the name itself "
        "(or its usual form in the base language, e.g. ロンドン → Londra).",
        "- No readings, romanization or explanations.",
        "",
        "",
        "Answer by calling the submit_term_meanings tool once, with one entry for every term.",
        "",
        "Terms (JSON, one per line):",
        *(json.dumps(t, ensure_ascii=False, sort_keys=True) for t in terms),
    ]
    tool_input, usage = _call_tool(
        tool=_SUBMIT_TERM_MEANINGS_TOOL,
        prompt="\n".join(lines),
        max_tokens=min(4000 + len(terms) * 60, 16000),
    )
    requested = {t["term_id"] for t in terms}
    meanings = {
        entry["term_id"]: str(entry["meaning"])
        for entry in tool_input.get("meanings", [])
        if isinstance(entry, dict) and entry.get("term_id") in requested and entry.get("meaning")
    }
    return meanings, usage
