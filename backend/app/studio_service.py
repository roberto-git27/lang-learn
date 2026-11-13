"""
Studio (Phase 9): exercises imported from `.md` (9a, D-08/D-22) or generated
by Claude from a request (9b, D-23). Both end up as the same items
(`md_import.ParsedExercise`), classified against the database the same way:

- `ready`: a new exercise. Its phrase is reused when the same sentence
  already exists in the track (the stored translation and difficulty win —
  a warning says so when the item disagrees), otherwise it is created.
- `duplicate`: the same exercise (type + normalized payload, same sentence)
  is already in the DB or earlier in the file/draft — skipped, so
  re-importing a corrected file only adds what is new.
- `error`: the item is invalid and cannot be stored.

Import: preview and import re-parse the same text (deterministic, 0 tokens);
the import stores `origin='human_import'`, already `human_checked` by the
importing profile. Generation: one request → a plan of specs → Claude (one
call + at most one top-up for what was missing or rejected) → a draft kept in
`ingest_jobs.items`; saving it stores the kept items as `origin='ai_generated'`,
not verified — they go to the review queue. Every job keeps its source .md
verbatim, linked from every exercise it produced.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import claude_service, term_service
from .config import settings
from .exercise_service import create_phrase, get_or_create_topics
from .md_import import (
    ParsedExercise, exercises_to_markdown, parse_exercises_md, parse_generation_request,
)
from .models import Exercise, ExerciseType, IngestJob, Phrase, PhraseTopic, PhraseTranslation, Track, User
from .schemas import ImportPreviewItem, ImportPreviewResponse, NewExerciseSpec, StudioJobDetail
from .studio_generation import check_studio_item, plan_specs, to_parsed_exercise
from .track_service import track_exercise_type_id, track_light_type_codes
from .tracks import get_track_spec


@dataclass
class _ExistingPhrase:
    id: int
    base_text: str | None
    difficulty: int


def _exercise_key(item: ParsedExercise) -> str:
    """Identity of an exercise: its sentence, type and normalized payload."""
    return json.dumps([item.phrase_target, item.exercise_type, item.payload], sort_keys=True, ensure_ascii=False)


async def _existing_phrases(db: AsyncSession, track: Track, targets: set[str]) -> dict[str, _ExistingPhrase]:
    """Phrases of the track whose target-language text is one of `targets`, by that text."""
    if not targets:
        return {}
    rows = (await db.execute(
        select(PhraseTranslation.content, Phrase.id, Phrase.difficulty)
        .join(Phrase, Phrase.id == PhraseTranslation.phrase_id)
        .where(
            Phrase.track_id == track.id,
            PhraseTranslation.language_id == track.target_language_id,
            PhraseTranslation.content.in_(targets),
        )
    )).all()
    phrases = {content: _ExistingPhrase(phrase_id, None, difficulty) for content, phrase_id, difficulty in rows}
    by_id = {p.id: p for p in phrases.values()}
    if by_id:
        base_rows = await db.execute(
            select(PhraseTranslation.phrase_id, PhraseTranslation.content).where(
                PhraseTranslation.phrase_id.in_(list(by_id)), PhraseTranslation.language_id == track.base_language_id,
            )
        )
        for phrase_id, content in base_rows.all():
            by_id[phrase_id].base_text = content
    return phrases


async def _existing_exercise_keys(db: AsyncSession, phrases: dict[str, _ExistingPhrase]) -> set[str]:
    """`_exercise_key` of every exercise already stored on those phrases."""
    target_by_id = {p.id: target for target, p in phrases.items()}
    if not target_by_id:
        return set()
    rows = await db.execute(
        select(Exercise.phrase_id, ExerciseType.code, Exercise.payload)
        .join(ExerciseType, ExerciseType.id == Exercise.exercise_type_id)
        .where(Exercise.phrase_id.in_(list(target_by_id)))
    )
    return {
        json.dumps([target_by_id[phrase_id], code, payload], sort_keys=True, ensure_ascii=False)
        for phrase_id, code, payload in rows.all()
    }


async def _classify(
    db: AsyncSession, track: Track, parsed_items: list[ParsedExercise], file_errors: list[str], source: str = "line",
) -> tuple[ImportPreviewResponse, dict[str, _ExistingPhrase]]:
    phrases = await _existing_phrases(db, track, {it.phrase_target for it in parsed_items if it.is_valid})
    stored_keys = await _existing_exercise_keys(db, phrases)

    seen: dict[str, int] = {}                     # exercise key → position of its first occurrence
    first_use: dict[str, ParsedExercise] = {}     # sentence → first ready item using it
    items = []
    for item in parsed_items:
        if not item.is_valid:
            items.append(ImportPreviewItem(**item.model_dump(), status="error"))
            continue
        key = _exercise_key(item)
        if key in stored_keys:
            item.warnings.append("already in the database")
            items.append(ImportPreviewItem(**item.model_dump(), status="duplicate"))
            continue
        if key in seen:
            item.warnings.append(f"same exercise as {source} {seen[key]}")
            items.append(ImportPreviewItem(**item.model_dump(), status="duplicate"))
            continue
        seen[key] = item.line

        # One phrase per sentence: its translation and difficulty come from
        # the DB, or from the first item using it.
        existing = phrases.get(item.phrase_target)
        first = first_use.setdefault(item.phrase_target, item)
        if existing:
            origin, base_text, difficulty = "the database", existing.base_text, existing.difficulty
        else:
            origin, base_text, difficulty = f"{source} {first.line}", first.phrase_base, first.difficulty
        if base_text != item.phrase_base:
            item.warnings.append(f"this sentence already has the translation '{base_text}' ({origin}): that one is kept")
        if difficulty != item.difficulty:
            item.warnings.append(f"this sentence already has difficulty {difficulty} ({origin}): that one is used")
        items.append(ImportPreviewItem(**item.model_dump(), status="ready"))

    preview = ImportPreviewResponse(
        items=items,
        errors=file_errors,
        ready_count=sum(it.status == "ready" for it in items),
        duplicate_count=sum(it.status == "duplicate" for it in items),
        error_count=sum(it.status == "error" for it in items),
    )
    return preview, phrases


async def _link_missing_topics(db: AsyncSession, track: Track, phrase_id: int, topic_codes: list[str]) -> None:
    topics = await get_or_create_topics(db, track, topic_codes)
    linked = set((await db.execute(select(PhraseTopic.topic_id).where(PhraseTopic.phrase_id == phrase_id))).scalars())
    for topic in topics:
        if topic.id not in linked:
            db.add(PhraseTopic(phrase_id=phrase_id, topic_id=topic.id, track_id=track.id))


async def _store(
    db: AsyncSession, track: Track, job: IngestJob, items: list[ImportPreviewItem],
    phrases: dict[str, _ExistingPhrase], origin: str, reviewer: User | None,
) -> None:
    """Adds the exercises of `items` (all `ready`) and their term links to the session; the caller commits."""
    now = datetime.now(timezone.utc)
    phrase_ids = {target: p.id for target, p in phrases.items()}
    for item in items:
        phrase_id = phrase_ids.get(item.phrase_target)
        if phrase_id is None:
            phrase = await create_phrase(db, track, item.difficulty, item.phrase_target, item.phrase_base, item.topics)
            phrase_id = phrase_ids[item.phrase_target] = phrase.id
        else:
            await _link_missing_topics(db, track, phrase_id, item.topics)
        exercise = Exercise(
            track_id=track.id,
            phrase_id=phrase_id,
            exercise_type_id=track_exercise_type_id(track, item.exercise_type),
            payload=item.payload,
            annotations=item.annotations,
            origin=origin,
            human_checked=reviewer is not None,
            human_checked_at=now if reviewer else None,
            human_checked_by=reviewer.display_name if reviewer else None,
            ingest_job_id=job.id,
        )
        db.add(exercise)
        await db.flush()
        await term_service.link_exercise_terms(
            db, track, exercise.id, item.exercise_type, item.phrase_target, item.payload,
        )


# ---------------------------------------------------------------------------
# Import (9a)
# ---------------------------------------------------------------------------
async def preview_import(db: AsyncSession, track: Track, text: str) -> ImportPreviewResponse:
    """What importing `text` would do; writes nothing."""
    parsed = parse_exercises_md(text, get_track_spec(track.code))
    preview, _ = await _classify(db, track, parsed.items, parsed.errors)
    return preview


async def import_exercises(db: AsyncSession, track: Track, user: User, text: str, source_name: str) -> IngestJob:
    """Stores every `ready` block of `text` in one transaction; 400 when there is nothing to import."""
    parsed = parse_exercises_md(text, get_track_spec(track.code))
    preview, phrases = await _classify(db, track, parsed.items, parsed.errors)
    if preview.errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(preview.errors))
    ready = [item for item in preview.items if item.status == "ready"]
    if not ready:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to import: every exercise is a duplicate or has errors",
        )

    job = IngestJob(
        track_id=track.id, user_id=user.id, source_name=source_name.strip(), source_text=text,
        kind="import", status="saved",
        created_count=len(ready), duplicate_count=preview.duplicate_count, error_count=preview.error_count,
    )
    db.add(job)
    await db.flush()
    await _store(db, track, job, ready, phrases, origin="human_import", reviewer=user)
    await db.commit()
    await db.refresh(job, attribute_names=["user"])
    return job


# ---------------------------------------------------------------------------
# Generation (9b)
# ---------------------------------------------------------------------------
async def _reference_examples(
    db: AsyncSession, track: Track, type_codes: set[str], difficulty: int, per_type: int,
) -> dict[str, list[dict]]:
    """
    Up to `per_type` human-checked exercises per type, picked at random —
    same difficulty first, then the closest levels — as style examples for
    the model (structure and tone, never content to copy).
    """
    examples: dict[str, list[dict]] = {}
    if per_type <= 0:
        return examples
    for code in sorted(type_codes):
        rows = await db.execute(
            select(Exercise.payload, Phrase.difficulty)
            .join(Phrase, Phrase.id == Exercise.phrase_id)
            .where(
                Exercise.track_id == track.id,
                Exercise.exercise_type_id == track_exercise_type_id(track, code),
                Exercise.human_checked.is_(True),
            )
            .order_by(sqlfunc.abs(Phrase.difficulty - difficulty), sqlfunc.random())
            .limit(per_type)
        )
        found = [{"exercise_type": code, "difficulty": level, "payload": payload} for payload, level in rows.all()]
        if found:
            examples[code] = found
    return examples


def _call_claude(track: Track, specs: list[NewExerciseSpec], references, hints, instructions):
    spec = get_track_spec(track.code)
    return claude_service.generate_exercises_for_gap(
        specs,
        source_language=track.base_language.code,
        target_language=track.target_language.code,
        track_guidelines=spec.generation_guidelines,
        type_instructions={t: spec.type_instructions[t] for t in {s.exercise_type for s in specs}},
        reference_examples=references,
        already_generated_hints=hints,
        instructions=instructions,
    )


async def generate_draft(db: AsyncSession, track: Track, user: User, text: str, source_name: str) -> IngestJob:
    """
    Parses the request, plans one spec per exercise, asks Claude (1 call +
    at most 1 top-up for missing or rejected items) and stores the result as
    a draft. 400 for an invalid request, 502 when the model call fails.
    """
    spec = get_track_spec(track.code)
    request = parse_generation_request(text, spec)
    if request.errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(request.errors))
    specs = plan_specs(request, track_light_type_codes(track))
    references = await _reference_examples(
        db, track, {s.exercise_type for s in specs}, request.difficulty, request.examples,
    )
    languages = {track.target_language.code, track.base_language.code}

    accepted: dict[str, tuple] = {}     # spec_id → (item, payload)
    rejected: dict[str, tuple] = {}     # spec_id → (item, reason)
    calls = input_tokens = output_tokens = 0
    started = time.monotonic()
    instructions = request.instructions
    try:
        for _ in range(2):   # first call + one top-up
            pending = [s for s in specs if s.spec_id not in accepted]
            if not pending:
                break
            hints = [
                tr.content for item, _ in accepted.values() for tr in item.phrase_translations
                if tr.language == track.target_language.code
            ]
            items, usage = await asyncio.to_thread(_call_claude, track, pending, references, hints, instructions)
            calls += 1
            input_tokens += usage["input_tokens"]
            output_tokens += usage["output_tokens"]
            by_id = {s.spec_id: s for s in pending}
            for item in items:
                pending_spec = by_id.get(item.spec_id)
                if pending_spec is None or item.spec_id in accepted:
                    continue
                payload, reason = check_studio_item(spec, pending_spec, item, languages)
                if payload is None:
                    rejected[item.spec_id] = (item, reason)
                else:
                    accepted[item.spec_id] = (item, payload)
                    rejected.pop(item.spec_id, None)
            problems = [f"- {sid}: {reason}" for sid, (_, reason) in rejected.items()]
            if problems:
                instructions = (request.instructions + "\n\n" if request.instructions else "") + (
                    "Your previous answer for these spec_ids was rejected; generate them again, fixing the problem:\n"
                    + "\n".join(problems)
                )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Generation failed: {exc}") from exc

    parsed = []
    for position, s in enumerate(specs, start=1):
        item, payload = accepted.get(s.spec_id, (None, None))
        reason = None
        if payload is None:
            item, reason = rejected.get(s.spec_id, (None, "not returned by the model"))
        parsed.append(to_parsed_exercise(
            position, s, item, payload, reason, spec, track.target_language.code, track.base_language.code,
        ))
    preview, _ = await _classify(db, track, parsed, [], source="item")

    job = IngestJob(
        track_id=track.id, user_id=user.id, source_name=source_name.strip(), source_text=text,
        kind="generate", status="draft", items=[item.model_dump() for item in preview.items],
        model=settings.claude_generation_model, llm_calls=calls, input_tokens=input_tokens, output_tokens=output_tokens,
        duration_ms=int((time.monotonic() - started) * 1000),
        duplicate_count=preview.duplicate_count, error_count=preview.error_count,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job, attribute_names=["user"])
    return job


async def _draft(db: AsyncSession, track: Track, job_id: int) -> IngestJob:
    job = await get_job(db, track, job_id)
    if job.kind != "generate" or job.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job {job_id} is not a generation draft")
    return job


async def save_draft(db: AsyncSession, track: Track, job_id: int, keep: list[int]) -> IngestJob:
    """
    Stores the kept draft items (re-checked against the DB: something may
    have been imported meanwhile) as unverified AI-generated exercises.
    """
    job = await _draft(db, track, job_id)
    drafted = [ImportPreviewItem.model_validate(item) for item in job.items]
    keep_positions = set(keep)
    kept = [
        ParsedExercise(**item.model_dump(exclude={"status", "warnings"}))
        for position, item in enumerate(drafted) if position in keep_positions and item.status == "ready"
    ]
    if not kept:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to save: keep at least one ready exercise")
    preview, phrases = await _classify(db, track, kept, [], source="item")
    ready = [item for item in preview.items if item.status == "ready"]
    if not ready:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to save: the kept exercises are already in the database")

    await _store(db, track, job, ready, phrases, origin="ai_generated", reviewer=None)
    job.status = "saved"
    job.created_count = len(ready)
    await db.commit()
    return job


async def discard_draft(db: AsyncSession, track: Track, job_id: int) -> IngestJob:
    job = await _draft(db, track, job_id)
    job.status = "discarded"
    await db.commit()
    return job


# ---------------------------------------------------------------------------
# Job history (both kinds)
# ---------------------------------------------------------------------------
async def list_jobs(db: AsyncSession, track: Track, limit: int = 50) -> list[IngestJob]:
    """Most recent first."""
    result = await db.execute(
        select(IngestJob).where(IngestJob.track_id == track.id).order_by(IngestJob.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_job(db: AsyncSession, track: Track, job_id: int) -> IngestJob:
    job = await db.scalar(select(IngestJob).where(IngestJob.id == job_id, IngestJob.track_id == track.id))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Studio job {job_id} not found on track '{track.code}'")
    return job


def job_detail(job: IngestJob, track: Track) -> StudioJobDetail:
    """The job with its source, its draft items and, for a generation, those items as an editable .md."""
    detail = StudioJobDetail.model_validate(job)
    if job.kind == "generate":
        detail.markdown = exercises_to_markdown([item for item in detail.items if item.payload], track.code)
    return detail
