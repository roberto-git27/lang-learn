"""
SQLAlchemy ORM models (mirror of postgresql/schema.sql).

Key ideas:
- A `Track` is one language studied from a base language (e.g. Japanese from
  Italian). Phrases, topics and exercises all belong to exactly one track;
  composite foreign keys on (id, track_id) keep rows from crossing tracks.
- `Phrase` is language-agnostic: it represents the "sentence concept";
  `PhraseTranslation` holds the text, one row per language.
- `Exercise.payload` is JSONB because each exercise type has different fields.
- `User` is a profile, not an account (see user_service.py);
  `UserTrack` lists the tracks a profile studies.
- `Attempt` is an immutable (append-only) log; `UserTopicProgress` is the aggregate.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Languages and tracks
# ---------------------------------------------------------------------------
class Language(Base):
    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)  # 'it', 'ja'
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Track(Base):
    """A target language studied from a base language (explanations/translations)."""
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # 'ja'
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    target_language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    base_language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    target_language = relationship("Language", foreign_keys=[target_language_id], lazy="joined")
    base_language = relationship("Language", foreign_keys=[base_language_id], lazy="joined")
    exercise_types = relationship("TrackExerciseType", lazy="selectin")


class ExerciseType(Base):
    __tablename__ = "exercise_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # 'multiple_choice' | 'fill_blank' | 'translate_rev'
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class TrackExerciseType(Base):
    """Which exercise types a track enables, and whether they need typing."""
    __tablename__ = "track_exercise_types"

    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    exercise_type_id: Mapped[int] = mapped_column(ForeignKey("exercise_types.id"), primary_key=True)
    is_typed_input: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    exercise_type = relationship("ExerciseType", lazy="joined")


# ---------------------------------------------------------------------------
# Phrases and translations
# ---------------------------------------------------------------------------
class Phrase(Base):
    """
    Abstract sentence concept: holds metadata but no text.
    The text lives in the translations, one per language.
    """
    __tablename__ = "phrases"
    __table_args__ = (
        UniqueConstraint("id", "track_id", name="uq_phrases_id_track"),
        Index("ix_phrases_track_difficulty", "track_id", "difficulty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=2, nullable=False)  # 1..5
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    translations = relationship(
        "PhraseTranslation",
        back_populates="phrase",
        cascade="all, delete-orphan",
    )
    topics = relationship("Topic", secondary="phrase_topics", viewonly=True)


class PhraseTranslation(Base):
    __tablename__ = "phrase_translations"
    __table_args__ = (
        UniqueConstraint("phrase_id", "language_id", name="uq_phrase_language"),
        Index("ix_translation_lang_text", "language_id", "content"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phrase_id: Mapped[int] = mapped_column(ForeignKey("phrases.id", ondelete="CASCADE"), nullable=False)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ipa: Mapped[str | None] = mapped_column(String(255))           # optional phonetic transcription
    audio_url: Mapped[str | None] = mapped_column(String(512))     # URL on S3/R2/GCS, NOT the file itself
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    phrase = relationship("Phrase", back_populates="translations")
    language = relationship("Language")


# ---------------------------------------------------------------------------
# Topics (per track) and their N:N relation with phrases
# ---------------------------------------------------------------------------
class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("track_id", "code", name="uq_topics_track_code"),
        UniqueConstraint("id", "track_id", name="uq_topics_id_track"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)      # 'particle_mo'
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # 'grammar', 'vocab', 'auto'
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class PhraseTopic(Base):
    __tablename__ = "phrase_topics"
    __table_args__ = (
        ForeignKeyConstraint(["phrase_id", "track_id"], ["phrases.id", "phrases.track_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["topic_id", "track_id"], ["topics.id", "topics.track_id"], ondelete="CASCADE"),
    )

    phrase_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------
class Exercise(Base):
    """
    Concrete exercise tied to a phrase and a type, within one track.
    `payload` is JSONB because its shape depends on the type:
      - multiple_choice: {"question": "...", "options": [...], "correct_index": 0, "explanation": "..."}
      - fill_blank:      {"sentence_with_blank": "...___...", "options": [...], "correct": "...", "explanation": "..."}
      - translate_rev:   {"prompt": "<target-language sentence>", "expected": "...", "alternatives": [...]}
    `annotations` holds derived reading aids computed by the track when the
    exercise is created (Japanese: furigana per display field, see
    tracks/japanese_text.py), never written by the LLM.
    `origin` says who wrote it: 'ai_generated' (the agent) or 'human_import'
    (a human, imported from .md in the Studio — `ingest_job_id` points to the import).
    """
    __tablename__ = "exercises"
    __table_args__ = (
        ForeignKeyConstraint(["phrase_id", "track_id"], ["phrases.id", "phrases.track_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["track_id", "exercise_type_id"],
            ["track_exercise_types.track_id", "track_exercise_types.exercise_type_id"],
        ),
        Index("ix_exercises_track_type", "track_id", "exercise_type_id"),
        UniqueConstraint("id", "track_id", name="uq_exercises_id_track"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    phrase_id: Mapped[int] = mapped_column(Integer, nullable=False)
    exercise_type_id: Mapped[int] = mapped_column(ForeignKey("exercise_types.id"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    annotations: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # reading aids, e.g. furigana
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    human_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    human_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    human_checked_by: Mapped[str | None] = mapped_column(String(64))
    ingest_job_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    track = relationship("Track", primaryjoin="Exercise.track_id == Track.id", foreign_keys=[track_id], viewonly=True)
    phrase = relationship("Phrase", primaryjoin="Exercise.phrase_id == Phrase.id", foreign_keys=[phrase_id], viewonly=True)
    exercise_type = relationship("ExerciseType")


# ---------------------------------------------------------------------------
# Users (profiles), tracks they study, attempts, progress
# ---------------------------------------------------------------------------
class User(Base):
    """A profile — NOT an authenticated account (see user_service.py)."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)  # unique case-insensitively (DB index)
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tracks = relationship("UserTrack", lazy="selectin", order_by="UserTrack.last_used_at.desc()")


class UserTrack(Base):
    __tablename__ = "user_tracks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    track = relationship("Track", lazy="joined")


class IngestJob(Base):
    """
    One Studio job, with its source .md kept verbatim: an import (saved at
    once) or a generation (a draft whose `items` wait for the user to save
    or discard them; cost in `llm_calls`/tokens/`duration_ms`).
    """
    __tablename__ = "ingest_jobs"
    __table_args__ = (
        Index("ix_ingest_jobs_track", "track_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="import", nullable=False)     # import | generate | terms
    status: Mapped[str] = mapped_column(String(16), default="saved", nullable=False)    # draft | saved | discarded
    items: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)            # generation draft
    model: Mapped[str | None] = mapped_column(String(64))
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", lazy="joined")

    @property
    def user_display_name(self) -> str | None:
        return self.user.display_name if self.user else None


class Term(Base):
    """
    A vocabulary item of a track, in dictionary form: one row per (lemma,
    reading), so the same word is never stored twice (see
    `TrackSpec.extract_terms`). `meaning` stays NULL until translated (by the
    AI on request, or by hand).
    """
    __tablename__ = "terms"
    __table_args__ = (
        UniqueConstraint("track_id", "lemma", "reading", name="uq_terms_lemma"),
        UniqueConstraint("id", "track_id", name="uq_terms_id_track"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    lemma: Mapped[str] = mapped_column(String(64), nullable=False)
    reading: Mapped[str] = mapped_column(String(128), nullable=False)
    written: Mapped[str] = mapped_column(String(64), nullable=False)
    pos: Mapped[str] = mapped_column(String(16), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    meaning: Mapped[str | None] = mapped_column(String(255))
    meaning_source: Mapped[str | None] = mapped_column(String(8))   # ai | human
    example: Mapped[str | None] = mapped_column(Text)
    ingest_job_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExerciseTerm(Base):
    """An exercise is about a term (`focus`) or merely contains it."""
    __tablename__ = "exercise_terms"
    __table_args__ = (
        ForeignKeyConstraint(["exercise_id", "track_id"], ["exercises.id", "exercises.track_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["term_id", "track_id"], ["terms.id", "terms.track_id"], ondelete="CASCADE"),
        Index("ix_exercise_terms_term", "term_id"),
    )

    exercise_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)   # focus | contains


class ReadingOverride(Base):
    """
    A word whose computed reading is wrong (五本 → ごほん) and the reading to
    use instead, everywhere in the track (see `reading_service.py`).
    """
    __tablename__ = "reading_overrides"
    __table_args__ = (UniqueConstraint("track_id", "surface", name="uq_reading_overrides"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    reading: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", lazy="joined")

    @property
    def user_display_name(self) -> str | None:
        return self.user.display_name if self.user else None


class Attempt(Base):
    """Immutable log of every attempt. Source of truth for progress."""
    __tablename__ = "attempts"
    __table_args__ = (
        Index("ix_attempts_user_time", "user_id", "answered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserTopicProgress(Base):
    """
    Denormalized progress aggregate per (user, topic) — topics are per track,
    so this is implicitly per track too. Updated on every attempt (see
    attempt_service.record_attempts).
    """
    __tablename__ = "user_topic_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_user_topic"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0..1
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Observability of the exercise selection/generation agent
# ---------------------------------------------------------------------------
class AgentRun(Base):
    """One row per agent run (cycles, tokens, duration, trace)."""
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"))
    request_params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    target_composition: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    db_found_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gap_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cycles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_exercise_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    trace: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", lazy="joined")
    track = relationship("Track", lazy="joined")

    @property
    def generated_count(self) -> int:
        """
        How many brand-new exercises this run actually generated and
        persisted to the DB — `gap_count` minus whatever spec_ids were still
        unfilled after the capped top-up loop (`trace["unfilled_spec_ids"]`).
        Derived, not a column: everything it needs is already stored.
        """
        trace = self.trace if isinstance(self.trace, dict) else {}
        unfilled = len(trace.get("unfilled_spec_ids") or [])
        return max(0, self.gap_count - unfilled)

    @property
    def user_display_name(self) -> str | None:
        return self.user.display_name if self.user else None

    @property
    def track_code(self) -> str | None:
        return self.track.code if self.track else None
