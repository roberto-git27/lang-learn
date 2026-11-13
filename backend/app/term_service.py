"""
Vocabulary of a track (D-24, stage 1): `terms` in dictionary form, one row
per (lemma, reading), and `exercise_terms` linking every exercise to the
terms it is about (`focus`) or contains.

Everything here is deterministic (the track's `extract_terms`, MeCab for
Japanese) except `translate_missing_meanings`, the only LLM call: meanings
are asked once, in batches, only for terms that have none, and stored.

- A term is created the first time it is seen — in a text saved from the
  Studio, or in any new exercise (import, generation draft, session agent) —
  and reused afterwards: never two rows for the same word.
- `sync_exercise_terms` links the exercises created before terms existed.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException, status
from sqlalchemy import func as sqlfunc, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from . import claude_service
from .config import settings
from .md_import import parse_terms_text
from .models import Exercise, ExerciseTerm, ExerciseType, IngestJob, PhraseTranslation, Term, Track, User
from .schemas import TermPreviewItem, TermResponse, TermsPreviewResponse
from .tracks import TermCandidate, TrackSpec, get_track_spec

Key = tuple[str, str]   # (lemma, reading)

MAX_MEANINGS_PER_CALL = 60


def _key(candidate: TermCandidate | Term) -> Key:
    return candidate.lemma, candidate.reading


def collect_terms(spec: TrackSpec, text: str) -> list[tuple[TermCandidate, str]]:
    """Each term of `text` once, with the first sentence it appears in."""
    found: dict[Key, tuple[TermCandidate, str]] = {}
    for sentence in spec.split_sentences(text):
        for candidate in spec.extract_terms(sentence):
            found.setdefault(_key(candidate), (candidate, sentence))
    return list(found.values())


async def _existing(db: AsyncSession, track: Track, keys: set[Key]) -> dict[Key, Term]:
    if not keys:
        return {}
    result = await db.execute(
        select(Term).where(Term.track_id == track.id, tuple_(Term.lemma, Term.reading).in_(list(keys)))
    )
    return {_key(term): term for term in result.scalars().all()}


async def _get_or_create(
    db: AsyncSession, track: Track, spec: TrackSpec, found: list[tuple[TermCandidate, str]], job_id: int | None = None,
) -> tuple[dict[Key, Term], int]:
    """The terms of `found`, created when missing (flushes); returns (terms by key, how many were created)."""
    terms = await _existing(db, track, {_key(c) for c, _ in found})
    created = 0
    for candidate, example in found:
        known = terms.get(_key(candidate))
        if known is not None:
            # Seen first in kana (なまえ), now in its dictionary spelling (名前): keep the latter.
            if candidate.written == candidate.lemma and known.written != candidate.lemma:
                known.written, known.level = candidate.written, spec.text_level(candidate.written)
            continue
        term = Term(
            track_id=track.id, lemma=candidate.lemma, reading=candidate.reading, written=candidate.written,
            pos=candidate.pos, level=spec.text_level(candidate.written), example=example, ingest_job_id=job_id,
        )
        db.add(term)
        terms[_key(candidate)] = term
        created += 1
    await db.flush()
    return terms, created


# ---------------------------------------------------------------------------
# Terms from a text (Studio)
# ---------------------------------------------------------------------------
async def preview_terms(db: AsyncSession, track: Track, text: str) -> TermsPreviewResponse:
    """The terms of `text`, marked new or already known; writes nothing, 0 tokens."""
    spec = get_track_spec(track.code)
    body, errors = parse_terms_text(text, spec)
    if errors:
        return TermsPreviewResponse(items=[], errors=errors, new_count=0, existing_count=0)
    found = collect_terms(spec, body)
    existing = await _existing(db, track, {_key(c) for c, _ in found})
    items = []
    for candidate, example in found:
        known = existing.get(_key(candidate))
        items.append(TermPreviewItem(
            lemma=candidate.lemma, reading=candidate.reading, written=known.written if known else candidate.written,
            pos=candidate.pos, level=known.level if known else spec.text_level(candidate.written),
            example=example, status="existing" if known else "new", meaning=known.meaning if known else None,
        ))
    return TermsPreviewResponse(
        items=items,
        errors=[],
        new_count=sum(item.status == "new" for item in items),
        existing_count=sum(item.status == "existing" for item in items),
    )


async def save_terms(db: AsyncSession, track: Track, user: User, text: str, source_name: str) -> IngestJob:
    """Stores the new terms of `text` (the source is kept in a 'terms' job); 400 when every term is known."""
    spec = get_track_spec(track.code)
    body, errors = parse_terms_text(text, spec)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(errors))
    found = collect_terms(spec, body)
    if not found:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No terms found in the text")
    job = IngestJob(
        track_id=track.id, user_id=user.id, source_name=source_name.strip(), source_text=text,
        kind="terms", status="saved",
    )
    db.add(job)
    await db.flush()
    _, created = await _get_or_create(db, track, spec, found, job_id=job.id)
    if not created:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Every term of the text is already known")
    job.created_count, job.duplicate_count = created, len(found) - created
    await db.commit()
    await db.refresh(job, attribute_names=["user"])
    return job


# ---------------------------------------------------------------------------
# Exercises ↔ terms
# ---------------------------------------------------------------------------
def _analysis_texts(exercise_type: str, sentence: str, payload: dict) -> tuple[str, str]:
    """
    (sentence, focus) to extract terms from. For kanji_writing both use the
    correct spelling (がっこう → 学校): the sentence written as it really is,
    which the analyzer also segments far better than kana-only text.
    """
    focus = payload.get("focus") or ""
    if exercise_type == "kanji_writing" and focus:
        spelling = payload["options"][payload["correct_index"]]
        return sentence.replace(focus, spelling, 1), spelling
    return sentence, focus


async def link_exercise_terms(
    db: AsyncSession, track: Track, exercise_id: int, exercise_type: str, sentence: str, payload: dict,
) -> int:
    """Links an exercise to the terms of its sentence (creating unknown ones); returns how many terms were created."""
    spec = get_track_spec(track.code)
    sentence, focus = _analysis_texts(exercise_type, sentence, payload)
    focus_terms = spec.extract_terms(focus) if focus else []
    focus_keys = {_key(c) for c in focus_terms}
    found = collect_terms(spec, sentence)
    seen = {_key(c) for c, _ in found}
    found += [(c, sentence) for c in focus_terms if _key(c) not in seen]
    terms, created = await _get_or_create(db, track, spec, found)
    linked = set((await db.execute(
        select(ExerciseTerm.term_id).where(ExerciseTerm.exercise_id == exercise_id)
    )).scalars())
    for key, term in terms.items():
        if term.id not in linked:
            db.add(ExerciseTerm(
                exercise_id=exercise_id, term_id=term.id, track_id=track.id,
                role="focus" if key in focus_keys else "contains",
            ))
    return created


async def sync_exercise_terms(db: AsyncSession, track: Track) -> tuple[int, int]:
    """Links the track's exercises that have no terms yet; returns (exercises linked, terms created)."""
    rows = (await db.execute(
        select(Exercise.id, ExerciseType.code, Exercise.payload, PhraseTranslation.content)
        .join(ExerciseType, ExerciseType.id == Exercise.exercise_type_id)
        .join(PhraseTranslation, (PhraseTranslation.phrase_id == Exercise.phrase_id)
              & (PhraseTranslation.language_id == track.target_language_id))
        .where(Exercise.track_id == track.id, ~Exercise.id.in_(select(ExerciseTerm.exercise_id)))
    )).all()
    created = 0
    for exercise_id, code, payload, sentence in rows:
        created += await link_exercise_terms(db, track, exercise_id, code, sentence, payload)
    await db.commit()
    return len(rows), created


# ---------------------------------------------------------------------------
# Browsing and meanings
# ---------------------------------------------------------------------------
async def list_terms(
    db: AsyncSession, track: Track, *, query: str | None = None, level: int | None = None,
    missing_meaning: bool = False, limit: int = 50, offset: int = 0,
) -> tuple[list[TermResponse], int, int]:
    """(terms, total matching, terms of the track without a meaning), most recent first."""
    conditions = [Term.track_id == track.id]
    if query:
        like = f"%{query.strip()}%"
        conditions.append(Term.written.ilike(like) | Term.reading.ilike(like) | Term.lemma.ilike(like) | Term.meaning.ilike(like))
    if level is not None:
        conditions.append(Term.level == level)
    if missing_meaning:
        conditions.append(Term.meaning.is_(None))
    total = await db.scalar(select(sqlfunc.count()).select_from(Term).where(*conditions))
    missing = await db.scalar(select(sqlfunc.count()).select_from(Term).where(Term.track_id == track.id, Term.meaning.is_(None)))
    usage = select(ExerciseTerm.term_id, sqlfunc.count().label("n")).group_by(ExerciseTerm.term_id).subquery()
    rows = (await db.execute(
        select(Term, sqlfunc.coalesce(usage.c.n, 0))
        .outerjoin(usage, usage.c.term_id == Term.id)
        .where(*conditions)
        .order_by(Term.created_at.desc(), Term.id.desc())
        .limit(limit).offset(offset)
    )).all()
    items = [TermResponse.model_validate(term).model_copy(update={"exercise_count": n}) for term, n in rows]
    return items, total or 0, missing or 0


async def _get_term(db: AsyncSession, track: Track, term_id: int) -> Term:
    term = await db.scalar(select(Term).where(Term.id == term_id, Term.track_id == track.id))
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Term {term_id} not found on track '{track.code}'")
    return term


async def delete_term(db: AsyncSession, track: Track, term_id: int) -> None:
    """Removes a wrong term (e.g. a bad segmentation of kana-only text) and its links."""
    await db.delete(await _get_term(db, track, term_id))
    await db.commit()


async def set_meaning(db: AsyncSession, track: Track, term_id: int, meaning: str | None) -> Term:
    """A meaning written (or cleared) by hand: it wins over the AI's."""
    term = await _get_term(db, track, term_id)
    term.meaning = (meaning or "").strip() or None
    term.meaning_source = "human" if term.meaning else None
    await db.commit()
    return term


async def translate_missing_meanings(db: AsyncSession, track: Track, limit: int) -> dict:
    """Asks Claude the meaning of up to `limit` terms without one (oldest first) and stores it."""
    terms = list((await db.execute(
        select(Term).where(Term.track_id == track.id, Term.meaning.is_(None))
        .order_by(Term.created_at, Term.id).limit(min(limit, MAX_MEANINGS_PER_CALL))
    )).scalars())
    if not terms:
        return {"translated": 0, "model": settings.claude_generation_model, "input_tokens": 0, "output_tokens": 0, "duration_ms": 0}
    started = time.monotonic()
    try:
        meanings, usage = await asyncio.to_thread(
            claude_service.translate_terms,
            [{"term_id": t.id, "written": t.written, "reading": t.reading, "pos": t.pos, "example": t.example} for t in terms],
            track.target_language.code,
            track.base_language.code,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Translation failed: {exc}") from exc
    translated = 0
    for term in terms:
        meaning = (meanings.get(term.id) or "").strip()
        if meaning:
            term.meaning, term.meaning_source = meaning[:255], "ai"
            translated += 1
    await db.commit()
    return {
        "translated": translated, "model": settings.claude_generation_model, **usage,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }

