"""
Pydantic schemas for API I/O validation.

Conventions:
- *Request: endpoint input (with sensible defaults).
- *Response: output sent to the client.
- LLM*: shape expected from Claude's response (for structured parsing).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .md_import import ParsedExercise


# ---------------------------------------------------------------------------
# Output schema requested from Claude (structured JSON)
# ---------------------------------------------------------------------------
class LLMTranslation(BaseModel):
    """One LLM-generated translation of the phrase."""
    language: str
    content: str
    ipa: str | None = None


# ---------------------------------------------------------------------------
# Endpoint responses
# ---------------------------------------------------------------------------
class TranslationResponse(BaseModel):
    language: str
    content: str
    ipa: str | None = None
    audio_url: str | None = None


class ExerciseResponse(BaseModel):
    id: int
    track: str
    exercise_type: str
    source_language: str   # the track's base language (questions, explanations)
    target_language: str   # the track's target language (the one being studied)
    difficulty: int
    payload: dict[str, Any]
    phrase_id: int
    phrase_translations: list[TranslationResponse]
    topics: list[str]
    is_new_phrase: bool
    # Reading aids keyed like the payload (e.g. {"question": [segments], "options": [[segments], ...]}).
    annotations: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tracks and profiles
# ---------------------------------------------------------------------------
class TrackExerciseTypeResponse(BaseModel):
    code: str
    name: str
    is_typed_input: bool


class TrackResponse(BaseModel):
    code: str
    name: str
    target_language: str
    base_language: str
    exercise_types: list[TrackExerciseTypeResponse]


class ProfileResponse(BaseModel):
    id: int
    display_name: str
    has_pin: bool
    tracks: list[str]   # track codes, most recently used first


class ProfileCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    pin: str | None = Field(default=None, pattern=r"^\d{4}$", description="Optional 4-digit PIN")
    tracks: list[str] = Field(min_length=1, description="Track codes to enroll in, e.g. ['ja']")

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("display_name must not be blank")
        return value


class PinVerifyRequest(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")


# ---------------------------------------------------------------------------
# Exercise history (attempts) — shared by the Practice tab and the chat
# ---------------------------------------------------------------------------
class ExerciseResultItem(BaseModel):
    exercise: dict
    result: dict


class ExerciseResultsRequest(BaseModel):
    results: list[ExerciseResultItem]


class RecordAttemptsResponse(BaseModel):
    recorded: int


# ---------------------------------------------------------------------------
# Exercise agent (Phase 1) — gap-filling tool-use call
#
# When the deterministic bucketing in `exercise_agent.py` finds the DB short
# of exercises for some (bucket, exercise_type) slots, it asks Claude to
# generate exactly those via a tool call to `submit_new_exercises`
# (see `claude_service.generate_exercises_for_gap`). These schemas describe
# that request/response shape.
# ---------------------------------------------------------------------------
class NewExerciseSpec(BaseModel):
    """One exercise Claude must generate (agent gap or Studio request).

    `spec_id` is a stable identifier chosen by the caller (not Claude) so a
    capped top-up call can target exactly the still-missing items by id.
    `term` (Studio only): the word or kanji the exercise must be about.
    """
    spec_id: str
    exercise_type: str
    difficulty: int
    topics: list[str] = Field(default_factory=list)
    term: str | None = None
    term_note: str | None = None


class GeneratedExerciseItem(BaseModel):
    """One exercise produced by Claude inside the submit_new_exercises tool call.

    Each item gets its own brand-new phrase (one exercise per phrase — the
    agent never generates "all types for one phrase" when gap-filling, to
    avoid producing exercise types nobody asked for).
    """
    spec_id: str
    phrase_translations: list[LLMTranslation]
    detected_topics: list[str] = Field(default_factory=list)
    # Validated per exercise type by the track's payload models (exercise_payloads.py).
    payload: dict[str, Any]


class SubmitNewExercisesInput(BaseModel):
    """Tool-use input schema for the `submit_new_exercises` tool."""
    exercises: list[GeneratedExerciseItem]


# ---------------------------------------------------------------------------
# Exercise agent (Phase 2) — observability (`agent_runs` table)
#
# One row per call to `exercise_agent.select_or_generate_exercises`. The list
# endpoint returns `AgentRunSummary` (cheap columns only); the detail
# endpoint returns `AgentRunDetail`, which adds the heavier JSONB payloads
# (full trace, request params, final exercise ids).
# ---------------------------------------------------------------------------
class AgentRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str | None
    user_display_name: str | None
    track_code: str | None
    status: str
    db_found_count: int
    gap_count: int
    generated_count: int
    cycles: int
    llm_calls: int
    input_tokens: int
    output_tokens: int
    duration_ms: int
    created_at: datetime


class AgentRunDetail(AgentRunSummary):
    request_params: dict
    target_composition: dict
    final_exercise_ids: list
    trace: dict


# ---------------------------------------------------------------------------
# Exercise review (Phase 3) — human-checked queue
#
# `human_checked`/`human_checked_at`/`human_checked_by` on `Exercise` exist
# since Phase 0 but had no UI until now. `exercise_agent._get_reference_exercises`
# already prefers `human_checked = true` rows as style examples for Claude,
# so marking good exercises here directly improves future generations.
# ---------------------------------------------------------------------------
class ExerciseReviewResponse(ExerciseResponse):
    """`ExerciseResponse` plus the review metadata — used by the review
    queue and the human-checked toggle (both care about who/when an exercise
    was verified)."""
    origin: str
    human_checked: bool
    human_checked_at: datetime | None
    human_checked_by: str | None
    created_at: datetime


class ReviewQueueResponse(BaseModel):
    items: list[ExerciseReviewResponse]
    total: int


class HumanCheckedUpdateRequest(BaseModel):
    human_checked: bool = True


class DifficultyStats(BaseModel):
    difficulty: int
    total: int
    human_checked: int        # verified by a human (imports, approved generations)
    by_type: dict[str, int]   # exercise type code → count


class ExerciseStatsResponse(BaseModel):
    """How many exercises a track has per difficulty (Admin › Coverage): every
    level of the scale is listed, empty ones included."""
    exercise_types: list[str]
    levels: list[DifficultyStats]
    total: int
    human_checked: int


# ---------------------------------------------------------------------------
# Studio (Phase 9) — .md import (9a) and AI generation drafts (9b)
#
# Preview and import parse the same text with the same deterministic parser
# (`md_import.py`), so the preview is exactly what gets stored. A generation
# is not repeatable, so its result is kept as a draft (`ingest_jobs.items`)
# until the user saves or discards it.
# ---------------------------------------------------------------------------
class StudioTextRequest(BaseModel):
    track: str = Field(description="Track code, e.g. 'ja'")
    text: str = Field(min_length=1, max_length=500_000, description="The .md: exercises to import, or a generation request")
    source_name: str = Field(default="pasted text", min_length=1, max_length=255, description="File name, kept with the job")


class ImportPreviewItem(ParsedExercise):
    # ready: will be stored · duplicate: already in the DB or earlier in the file · error: cannot be stored
    status: Literal["ready", "duplicate", "error"]


class ImportPreviewResponse(BaseModel):
    items: list[ImportPreviewItem]
    errors: list[str]   # file-level problems: nothing can be imported until they are fixed
    ready_count: int
    duplicate_count: int
    error_count: int


class NormalizeSkipped(BaseModel):
    line: int       # first line of the segment, in the text that was sent
    reason: str


class NormalizeResponse(BaseModel):
    """The .md with the unreadable parts rewritten by the parse model: to preview and check before importing."""
    text: str
    sent_segments: int        # segments sent to the model (invalid blocks + text outside blocks)
    rewritten_segments: int   # segments replaced by the model's exercises
    exercise_count: int
    skipped: list[NormalizeSkipped]
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class GenerationSaveRequest(BaseModel):
    track: str = Field(description="Track code, e.g. 'ja'")
    keep: list[int] = Field(description="Positions (0-based) of the draft items to save; the others are dropped")


class RegenerateItemRequest(BaseModel):
    track: str = Field(description="Track code, e.g. 'ja'")
    note: str = Field(default="", max_length=500, description="Optional: what to change, for the AI")


class StudioJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: Literal["import", "generate", "terms"]
    status: Literal["draft", "saved", "discarded"]
    source_name: str
    user_display_name: str | None
    created_count: int
    duplicate_count: int
    error_count: int
    model: str | None
    llm_calls: int
    input_tokens: int
    output_tokens: int
    duration_ms: int
    created_at: datetime


class StudioJobDetail(StudioJobSummary):
    source_text: str
    items: list[ImportPreviewItem]   # generation draft (empty for imports)
    markdown: str | None = None      # the draft's valid items in the import format, to edit by hand


# ---------------------------------------------------------------------------
# Vocabulary (D-24) — terms of a track and their meanings
# ---------------------------------------------------------------------------
class TermPreviewItem(BaseModel):
    lemma: str
    reading: str
    written: str
    pos: str
    level: int
    example: str | None = None
    status: Literal["new", "existing"]
    meaning: str | None = None       # stored meaning, or the one a term list gives a new term
    new_meaning: str | None = None   # term list: the meaning it gives a known term without a human one
    line: int | None = None          # term list: its line


class TermsPreviewResponse(BaseModel):
    items: list[TermPreviewItem]
    errors: list[str]   # file-level problems (front matter, unreadable term list)
    warnings: list[str] = []   # term list: rows or columns left out
    new_count: int
    existing_count: int
    meaning_updates: int = 0   # term list: known terms that get a meaning


class TermsSaveResponse(StudioJobSummary):
    meaning_updates: int = 0   # term list: known terms that got its meaning


class TermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lemma: str
    reading: str
    written: str
    pos: str
    level: int
    meaning: str | None
    meaning_source: Literal["ai", "human"] | None
    example: str | None
    exercise_count: int = 0
    created_at: datetime


class TermListResponse(BaseModel):
    items: list[TermResponse]
    total: int
    missing_meanings: int   # terms of the track without a meaning, whatever the filters


class TermMeaningUpdate(BaseModel):
    track: str = Field(description="Track code, e.g. 'ja'")
    meaning: str | None = Field(default=None, max_length=255, description="Empty or null clears it")


class TranslateMeaningsRequest(BaseModel):
    track: str = Field(description="Track code, e.g. 'ja'")
    limit: int = Field(default=60, ge=1, le=60, description="Terms per call (oldest without a meaning first)")


class TranslateMeaningsResponse(BaseModel):
    translated: int
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class TermSyncResponse(BaseModel):
    exercises_linked: int
    terms_created: int

