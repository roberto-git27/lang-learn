"""
In-memory session store for the chatbot.

No persistence — state is lost when the process restarts.
Each session is identified by a UUID generated on the first interaction.
"""
from __future__ import annotations

import uuid
from typing import Any

SessionId = str

# Global dict: session_id -> state dict
_store: dict[SessionId, dict[str, Any]] = {}


def create_session(
    user_id: int, track: str, system_prompt: str, tool: dict,
) -> tuple[SessionId, dict[str, Any]]:
    session_id = str(uuid.uuid4())
    session: dict[str, Any] = {
        "session_id": session_id,
        "messages": [],              # message list in Anthropic API format
        "phase": "negotiating",      # negotiating | searching | ready | in_exercise | reviewing
        "filters": None,             # parameters collected by the model (tool input)
        "exercises": None,           # list[dict] — serialized ExerciseResponse
        "pending_tool_use_id": None, # id of the tool_use block awaiting a tool_result
        "user_id": user_id,          # profile (no auth), fixed at creation
        "track": track,              # track code, fixed at creation
        "system_prompt": system_prompt,  # track-specific negotiation prompt
        "tool": tool,                # track-specific request_exercises tool definition
        "history_notes": [],         # short notes on the completed sessions (history compaction)
    }
    _store[session_id] = session
    return session_id, session


def get_session(session_id: SessionId) -> dict[str, Any] | None:
    return _store.get(session_id)



def delete_session(session_id: SessionId) -> None:
    """Forgets a session ("New chat" in the UI). Unknown ids are ignored."""
    _store.pop(session_id, None)
