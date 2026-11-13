"""
FastAPI router for the exercise-negotiation chatbot.

Phase flow:
  negotiating → (tool_use emitted) → searching → ready → in_exercise → reviewing → negotiating

A chat session belongs to one profile and one track, fixed when it is
created: the system prompt and the `request_exercises` tool are built for
that track (its exercise types and existing topics).

Every endpoint uses SSE (Server-Sent Events) to stream generated text.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import AsyncIterator

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from .. import agent_run_service, track_service, user_service
from ..attempt_service import record_attempts
from ..config import settings
from ..database import AsyncSessionLocal
from ..exercise_agent import AgentGenerationError, select_or_generate_exercises
from ..exercise_payloads import MAX_DIFFICULTY
from ..models import Topic, Track
from ..schemas import ExerciseResultsRequest
from ..session_store import create_session, delete_session, get_session
from ..tracks import get_track_spec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_async_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

# Thinking counts toward max_tokens even though it is never shown, so leave
# room for it on top of the short replies the chat prompt asks for.
_CHAT_MAX_TOKENS = 4096


def _chat_request(session: dict) -> dict:
    """Arguments of every chat call. `system` and `tools` stay fixed for the
    whole session and the history is append-only, so thinking blocks replayed
    from earlier turns stay valid."""
    return {
        "model": settings.claude_chat_model,
        "max_tokens": _CHAT_MAX_TOKENS,
        "output_config": {"effort": settings.claude_chat_effort},
        "system": session["system_prompt"],
        "tools": [session["tool"]],
        # One exercise session at a time: at most one request_exercises call
        # per reply (the 5.5 models accept this with `auto`, not a forced choice).
        "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
        "messages": session["messages"],
    }


_NOT_RUN = "Not run: one exercise session at a time. Ask the learner before calling request_exercises again."


def _tool_results(messages: list[dict], answers: dict[str, dict]) -> list[dict]:
    """
    tool_result blocks for every tool_use of the last assistant turn, which the
    API requires in the very next message. `answers` maps a tool_use id to its
    result fields (content, is_error); any other call gets a "not run" result.
    """
    if not messages or messages[-1]["role"] != "assistant":
        return []
    return [
        {"type": "tool_result", "tool_use_id": block["id"],
         **answers.get(block["id"], {"content": _NOT_RUN})}
        for block in messages[-1]["content"]
        if block.get("type") == "tool_use"
    ]


_WRITTEN_TOOL_CALL = re.compile(r"request_?exercises|tool[ _]?call", re.IGNORECASE)
_WRITTEN_TOOL_CALL_NOTE = (
    "[Note from the app, not from the learner: your last reply wrote the tool call as text, "
    "which starts nothing and was not shown. Call the request_exercises tool now with those "
    "parameters, without any text.]"
)


def is_written_tool_call(message) -> bool:
    """A reply with no tool_use whose text describes one (e.g. "[Tool call:
    request_exercises with difficulty 2]") instead of making it."""
    if any(block.type == "tool_use" for block in message.content):
        return False
    text = "".join(block.text for block in message.content if block.type == "text")
    return bool(_WRITTEN_TOOL_CALL.search(text))


def _assistant_turn(message) -> dict:
    """The assistant turn to append to the history: every content block as
    returned (thinking blocks included, which must be passed back unchanged)."""
    return {
        "role": "assistant",
        "content": [block.model_dump(mode="json", exclude_none=True) for block in message.content],
    }


def _refusal_error(message) -> str | None:
    """User-facing error when a safety classifier declined the turn."""
    if message.stop_reason != "refusal":
        return None
    return "The model declined to answer this message. Try rephrasing it."


def _request_exercises_tool(track: Track, topic_codes: list[str]) -> dict:
    """The `request_exercises` tool for one track: its exercise types and known topics."""
    type_codes = track_service.track_type_codes(track)
    return {
        "name": "request_exercises",
        "description": (
            "Call it ONLY once the learner has confirmed the session summary (difficulty is required). "
            "Do not call it if essential information is missing or the learner is still vague."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "difficulty": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_DIFFICULTY,
                    "description": f"Difficulty from 1 (first lessons) to {MAX_DIFFICULTY} (advanced); see the level table in the system prompt",
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        f"Optional topic codes. Existing ones: {', '.join(topic_codes) or 'none yet'}. "
                        "You may also name a new snake_case topic: it is created automatically."
                    ),
                },
                "exercise_type": {
                    "type": "string",
                    "enum": type_codes,
                    "description": "Optional exercise type. Omit for a mix.",
                },
                "n_exercises": {
                    "type": "integer",
                    "minimum": 3,
                    "maximum": 15,
                    "description": "Number of exercises requested. Default: 10.",
                },
            },
            "required": ["difficulty"],
        },
    }


# ---------------------------------------------------------------------------
# Input/output models
# ---------------------------------------------------------------------------
class ChatMessageRequest(BaseModel):
    session_id: str | None = None
    track: str | None = None   # required when session_id is None (new session)
    message: str


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------
def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Exercise fetching — never raises, always returns (exercises | None, error | None)
# ---------------------------------------------------------------------------
async def _fetch_exercises(
    filters: dict, user_id: int, track_code: str, session_id: str | None,
) -> tuple[list[dict] | None, str | None]:
    """
    Delegates to the exercise agent (`exercise_agent.select_or_generate_exercises`):
    a deterministic 60/20/20 (topic/review/harder) bucketing fills as much as
    possible from the DB, auto-creates any requested topic that doesn't exist
    yet, and hands only the residual gap to Claude via a capped tool-use loop.

    Runs in a single DB session for the whole call — topic auto-creation and
    any generated exercises are only visible within that same session until
    committed, so splitting this across two sessions would silently drop a
    just-created topic.

    Every outcome (ok, partial gap, or failure) is logged as one row in
    `agent_runs` via `agent_run_service.record_agent_run` — best-effort, this
    never affects what's returned here.

    Never raises — always returns (result, error).
    """
    start = time.perf_counter()
    track_id: int | None = None
    try:
        async with AsyncSessionLocal() as db:
            user = await user_service.get_user(db, user_id)
            track = await track_service.get_track(db, track_code)
            track_id = track.id
            result = await select_or_generate_exercises(db, user, track, filters)
            duration_ms = int((time.perf_counter() - start) * 1000)
            run_status = "partial" if result.trace.get("unfilled_spec_ids") else "ok"
            await agent_run_service.record_agent_run(
                db, session_id=session_id, user_id=user_id, track_id=track_id, trace=result.trace,
                duration_ms=duration_ms, run_status=run_status,
            )
            return [ex.model_dump() for ex in result.exercises], None
    except AgentGenerationError as e:
        logger.warning("Exercise agent produced no exercises: %s", e)
        await _record_failed_run(session_id, user_id, track_id, e.trace, start)
        return None, (
            "No exercises were found and new ones could not be generated. "
            "Try changing the difficulty or the topic."
        )
    except HTTPException as e:
        logger.exception("HTTP error while fetching chat exercises")
        await _record_failed_run(session_id, user_id, track_id, {"request_params": filters}, start)
        return None, f"Error while fetching exercises: {e.detail}"
    except Exception:
        logger.exception("Unexpected error while fetching chat exercises")
        await _record_failed_run(session_id, user_id, track_id, {"request_params": filters}, start)
        return None, "Internal error while fetching exercises."


async def _record_failed_run(
    session_id: str | None, user_id: int, track_id: int | None, trace: dict, start: float,
) -> None:
    """Opens its own session since the one used by the failed attempt is already closed by now."""
    duration_ms = int((time.perf_counter() - start) * 1000)
    async with AsyncSessionLocal() as db:
        await agent_run_service.record_agent_run(
            db, session_id=session_id, user_id=user_id, track_id=track_id, trace=trace,
            duration_ms=duration_ms, run_status="error",
        )


# ---------------------------------------------------------------------------
# Stream generator — POST /chat/message
# ---------------------------------------------------------------------------
async def _stream_chat_message(
    session: dict,
    user_message: str,
) -> AsyncIterator[str]:
    """
    SSE generator for POST /chat/message.
    Guarantees that 'done' is ALWAYS emitted, even on exceptions.
    """
    # Every tool_use needs its tool_result before the next user turn: exercises
    # found but not started are dropped, any other call (e.g. one made in a
    # feedback reply) is answered as not run.
    pending = session.get("pending_tool_use_id")
    answers = {}
    if pending and session.get("phase") == "ready":
        answers[pending] = {"content": "The learner kept chatting instead of starting these exercises; they were discarded."}
    open_results = _tool_results(session["messages"], answers)
    if open_results:
        session["messages"].append({"role": "user", "content": [
            *open_results, {"type": "text", "text": user_message},
        ]})
    else:
        session["messages"].append({"role": "user", "content": user_message})
    if pending and session.get("phase") == "ready":
        session["pending_tool_use_id"] = None
        session["exercises"] = None
        session["phase"] = "negotiating"
        yield _sse({"type": "phase_change", "phase": "negotiating"})

    # ── Step 1: streaming Anthropic call ─────────────────────────────────
    # A reply that writes the tool call as text starts nothing: it is kept in
    # the history (append-only), followed by a note, and asked again once; the
    # frontend drops the text already shown (text_reset).
    final_message = None
    try:
        for attempt in range(2):
            async with _async_client.messages.stream(**_chat_request(session)) as stream:
                async for text in stream.text_stream:
                    yield _sse({"type": "text_delta", "text": text})
                final_message = await stream.get_final_message()
            if attempt == 1 or not is_written_tool_call(final_message):
                break
            logger.warning("Chat reply wrote the tool call as text; asking again")
            session["messages"].append(_assistant_turn(final_message))
            session["messages"].append({"role": "user", "content": _WRITTEN_TOOL_CALL_NOTE})
            yield _sse({"type": "text_reset"})
    except Exception as e:
        logger.exception("Anthropic stream error (chat message)")
        yield _sse({"type": "error", "message": f"API error: {str(e)}"})
        yield _sse({"type": "done"})
        return

    # ── Step 2: extract content and tool_use from the final message ──────
    tool_use_block = None
    try:
        refusal = _refusal_error(final_message)
        if refusal:
            # Not added to the history: the user can rephrase and try again
            # (a tool_result closing a discarded tool_use stays).
            last = session["messages"].pop()
            if isinstance(last["content"], list):
                session["messages"].append({
                    "role": "user",
                    "content": [b for b in last["content"] if b.get("type") == "tool_result"],
                })
            yield _sse({"type": "error", "message": refusal})
            yield _sse({"type": "done"})
            return
        tool_use_block = next((b for b in final_message.content if b.type == "tool_use"), None)
        assistant_turn = _assistant_turn(final_message)
        if tool_use_block and tool_use_block.name == "request_exercises" and session["history_notes"]:
            session["messages"] = compact_history(session["history_notes"], user_message, assistant_turn)
        else:
            session["messages"].append(assistant_turn)
    except Exception:
        logger.exception("Error while processing final_message")
        yield _sse({"type": "error", "message": "Internal error while processing the response"})
        yield _sse({"type": "done"})
        return

    # ── Step 3a: tool_use → fetch exercises ─────────────────────────────
    if tool_use_block and tool_use_block.name == "request_exercises":
        filters = tool_use_block.input
        session["phase"] = "searching"
        session["filters"] = filters
        session["pending_tool_use_id"] = tool_use_block.id

        yield _sse({"type": "phase_change", "phase": "searching", "filters": filters})

        exercises, error = await _fetch_exercises(
            filters, session["user_id"], session["track"], session["session_id"],
        )

        if exercises:
            session["exercises"] = exercises
            session["phase"] = "ready"
            yield _sse({"type": "phase_change", "phase": "ready", "exercises": exercises})
        else:
            # Empty DB + failed generation → back to negotiating, the model explains why
            session["messages"].append({
                "role": "user",
                "content": _tool_results(session["messages"], {tool_use_block.id: {
                    "content": json.dumps({"error": error or "No exercises found"}),
                    "is_error": True,
                }}),
            })
            session["pending_tool_use_id"] = None
            session["phase"] = "negotiating"

            # Notify the frontend BEFORE streaming text, so the input gets re-enabled
            yield _sse({"type": "phase_change", "phase": "negotiating"})

            try:
                async with _async_client.messages.stream(**_chat_request(session)) as recovery_stream:
                    async for text in recovery_stream.text_stream:
                        yield _sse({"type": "text_delta", "text": text})
                    recovery_msg = await recovery_stream.get_final_message()
                if _refusal_error(recovery_msg):
                    yield _sse({"type": "error", "message": _refusal_error(recovery_msg)})
                else:
                    session["messages"].append(_assistant_turn(recovery_msg))
            except Exception as e:
                logger.exception("Error during recovery after a failed search")
                yield _sse({"type": "error", "message": str(e)})

    # ── Step 3b: plain text reply ───────────────────────────────────────
    else:
        session["phase"] = "negotiating"

    yield _sse({"type": "done"})


# ---------------------------------------------------------------------------
# End-of-session results, as the model reads them
# ---------------------------------------------------------------------------
# Payload field holding the text shown before answering, per exercise type
# (mirror of PROMPT_FIELD in frontend/src/utils/exerciseTypes.js).
PROMPT_FIELD = {
    "multiple_choice": "question",
    "fill_blank": "sentence_with_blank",
    "translate_rev": "prompt",
    "kanji_reading": "sentence",
    "kanji_writing": "sentence",
    "romaji_input": "sentence",
}


def _result_detail(number: int, exercise: dict, result: dict) -> dict:
    """
    One exercise as the model sees it in the feedback: what was asked (the
    prompt text, the underlined word, the options), the sentence and its
    translation, the learner's answer and the correct one. Without the
    question the model could only explain the rule in general, not the
    learner's actual mistake.
    """
    payload = exercise.get("payload") or {}
    translations = {t.get("language"): t.get("content") for t in exercise.get("phrase_translations") or []}
    detail = {
        "number": number,
        "exercise_type": exercise.get("exercise_type"),
        "topics": exercise.get("topics", []),
        "difficulty": exercise.get("difficulty"),
        "prompt": payload.get(PROMPT_FIELD.get(exercise.get("exercise_type"), ""), None),
        "focus": payload.get("focus"),
        "options": payload.get("options"),
        "sentence": translations.get(exercise.get("target_language")),
        "sentence_translation": translations.get(exercise.get("source_language")),
        "correct": bool(result.get("correct")),
        "user_answer": result.get("user_answer", ""),
        "correct_answer": result.get("correct_answer", ""),
        "similarity_score": result.get("similarity_score"),
        "explanation": result.get("explanation") or payload.get("explanation"),
    }
    # Fields a type doesn't have (no options in a typed answer…) are left out.
    return {key: value for key, value in detail.items() if value not in (None, "", [])}


def build_results_summary(results: list[dict]) -> dict:
    """The tool_result sent back to the model at the end of a session.
    `number` is the exercise's position in the session, as the learner saw
    it in the summary ("la numero 3")."""
    correct_count = sum(1 for r in results if r["result"].get("correct"))
    return {
        "exercises_completed": len(results),
        "correct_count": correct_count,
        "score_pct": round(correct_count / len(results) * 100) if results else 0,
        "details": [_result_detail(i, r["exercise"], r["result"]) for i, r in enumerate(results, 1)],
    }


# ---------------------------------------------------------------------------
# History compaction — keeps a long chat cheap
#
# Every request resends the whole history, results of every session
# included. When a new exercise session starts and earlier ones are complete,
# the history restarts from a short note per earlier session, built in Python
# (no LLM call). The whole old history is dropped, never single turns from the
# middle: with the 5.5 models, removing turns from the middle would invalidate
# every later thinking block. `system` and `tools` are separate request fields
# and are never touched.
# ---------------------------------------------------------------------------
MAX_HISTORY_NOTES = 3     # earlier sessions remembered after a compaction
MAX_NOTE_MISTAKES = 5     # mistakes listed per session


def session_note(filters: dict | None, summary: dict) -> str:
    """One line about a completed session, for the compacted history."""
    filters = filters or {}
    parts = [f"difficulty {filters.get('difficulty', '?')}"]
    if filters.get("topics"):
        parts.append("topics " + ", ".join(filters["topics"]))
    if filters.get("exercise_type"):
        parts.append(f"type {filters['exercise_type']}")
    line = f"{'; '.join(parts)}: {summary['correct_count']}/{summary['exercises_completed']} correct"
    mistakes = [d for d in summary["details"] if not d.get("correct")]
    if mistakes:
        described = [
            f"{d.get('exercise_type')} \"{d.get('prompt') or d.get('sentence') or ''}\" "
            f"answered \"{d.get('user_answer', '')}\" instead of \"{d.get('correct_answer', '')}\""
            for d in mistakes[:MAX_NOTE_MISTAKES]
        ]
        more = len(mistakes) - MAX_NOTE_MISTAKES
        line += ". Mistakes: " + "; ".join(described) + (f"; and {more} more" if more > 0 else "")
    return line


def compact_history(notes: list[str], user_message: str, assistant_turn: dict) -> list[dict]:
    """
    The new history when a session starts after earlier ones: the learner's
    latest message prefixed with the notes on the earlier sessions, then the
    assistant turn that calls request_exercises. Its thinking blocks are
    dropped (text and tool_use stay): they were produced on the old history
    and would no longer be valid on the new one.
    """
    context = "\n".join(f"- {note}" for note in notes[-MAX_HISTORY_NOTES:])
    first_turn = (
        "[Context: earlier sessions in this chat; older messages were removed to keep the "
        f"conversation short]\n{context}\n\n[Learner's message]\n{user_message}"
    )
    content = [b for b in assistant_turn["content"] if b.get("type") not in ("thinking", "redacted_thinking")]
    return [
        {"role": "user", "content": first_turn},
        {"role": "assistant", "content": content},
    ]


# ---------------------------------------------------------------------------
# Stream generator — POST /chat/sessions/{id}/exercise-results
# ---------------------------------------------------------------------------
async def _stream_exercise_feedback(
    session: dict,
    results: list[dict],
) -> AsyncIterator[str]:
    """
    SSE generator for the end-of-session feedback.
    Guarantees that 'done' is ALWAYS emitted.
    """
    tool_use_id = session["pending_tool_use_id"]

    # Build a results summary the model can read
    try:
        results_summary = build_results_summary(results)
        session["history_notes"].append(session_note(session.get("filters"), results_summary))
    except Exception:
        logger.exception("Error while building the results summary")
        yield _sse({"type": "error", "message": "Error while processing the results"})
        yield _sse({"type": "done"})
        return

    # Persist history (attempts + per-topic mastery) — best-effort, must never
    # block the conversational feedback on error.
    try:
        async with AsyncSessionLocal() as db:
            user = await user_service.get_user(db, session["user_id"])
            await record_attempts(db, user, results)
    except Exception:
        logger.exception("Error while persisting attempts (chat flow) — ignored")

    session["messages"].append({
        "role": "user",
        "content": _tool_results(session["messages"], {tool_use_id: {
            "content": json.dumps(results_summary, ensure_ascii=False),
        }}),
    })

    # Ask the model for feedback
    try:
        async with _async_client.messages.stream(**_chat_request(session)) as stream:
            async for text in stream.text_stream:
                yield _sse({"type": "text_delta", "text": text})
            feedback_message = await stream.get_final_message()
    except Exception as e:
        logger.exception("Anthropic stream error (exercise feedback)")
        yield _sse({"type": "error", "message": f"API error: {str(e)}"})
        yield _sse({"type": "done"})
        return

    # Update history and reset state
    try:
        if _refusal_error(feedback_message):
            yield _sse({"type": "error", "message": _refusal_error(feedback_message)})
        else:
            session["messages"].append(_assistant_turn(feedback_message))
    except Exception:
        logger.exception("Error while saving feedback to the session")

    session["pending_tool_use_id"] = None
    session["exercises"] = None
    session["phase"] = "negotiating"

    yield _sse({"type": "phase_change", "phase": "negotiating"})
    yield _sse({"type": "done"})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
async def _new_session(user_id: int, track_code: str | None) -> dict:
    """
    Creates a chat session fixed to one profile and one track, marking the
    track as the profile's most recently used one (enrolling it if needed).
    The system prompt and tool are built once here: the topic list reflects
    the track's topics at session start.
    """
    async with AsyncSessionLocal() as db:
        user = await user_service.get_user(db, user_id)
        track = await track_service.get_track(db, track_code)
        await user_service.use_track(db, user, track)
        topic_codes = list((await db.execute(
            select(Topic.code).where(Topic.track_id == track.id).order_by(Topic.code)
        )).scalars().all())
        system_prompt = get_track_spec(track.code).chat_system_prompt()
        tool = _request_exercises_tool(track, topic_codes)
    _, session = create_session(user_id=user_id, track=track.code, system_prompt=system_prompt, tool=tool)
    return session
@router.post("/message", summary="Send a chat message")
async def chat_message(
    request: ChatMessageRequest,
    user_id: int = Depends(user_service.current_user_id),
) -> StreamingResponse:
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message must not be empty",
        )

    if request.session_id:
        session = get_session(request.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {request.session_id} not found",
            )
        if session["user_id"] != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session belongs to another profile")
    else:
        session = await _new_session(user_id, request.track)

    session_id = session["session_id"]
    is_new = request.session_id is None

    async def generator():
        if is_new:
            yield _sse({"type": "session_created", "session_id": session_id})
        async for chunk in _stream_chat_message(session, request.message):
            yield chunk

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/sessions/{session_id}/exercise-results",
    summary="Submit exercise results for feedback",
)
async def exercise_results(
    session_id: str,
    request: ExerciseResultsRequest,
    user_id: int = Depends(user_service.current_user_id),
) -> StreamingResponse:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    if session["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session belongs to another profile")
    if session.get("pending_tool_use_id") is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending tool_use for this session",
        )
    if not request.results:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Results list must not be empty",
        )

    session["phase"] = "reviewing"
    results = [r.model_dump() for r in request.results]

    return StreamingResponse(
        _stream_exercise_feedback(session, results),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/sessions/{session_id}", summary="Current session state")
async def session_state(session_id: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return {
        "session_id": session_id,
        "track": session["track"],
        "phase": session["phase"],
        "message_count": len(session["messages"]),
        "has_exercises": session["exercises"] is not None,
        "filters": session["filters"],
    }


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Forget a chat session (New chat)",
)
async def end_session(
    session_id: str,
    user_id: int = Depends(user_service.current_user_id),
) -> Response:
    session = get_session(session_id)
    if session is not None:
        if session["user_id"] != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session belongs to another profile")
        delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
