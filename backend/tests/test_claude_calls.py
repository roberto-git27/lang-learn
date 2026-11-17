"""
Request shapes of the Claude calls, with a fake client (no network): the 5.5
models reject a forced `tool_choice` and sampling parameters, so the tool call
is requested with `auto`, checked, and asked again once when missing.
"""
from types import SimpleNamespace

import pytest

from app import claude_service
from app.config import settings
from app.routers import chat


def _response(content, stop_reason="end_turn"):
    return SimpleNamespace(
        content=content, stop_reason=stop_reason, stop_details=None,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def _tool_use(name, tool_input):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input)


class _FakeStream:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._response


class _FakeClient:
    """Records every request; `messages` and `beta.messages` share the queue."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(stream=self._stream(beta=False))
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream(beta=True)))

    def _stream(self, beta):
        def stream(**kwargs):
            self.calls.append({"beta": beta, **kwargs})
            return _FakeStream(self.responses.pop(0))
        return stream


TERMS = [{"term_id": 1, "written": "雨", "reading": "あめ", "pos": "noun", "example": "雨が ふっています。"}]
MEANINGS = {"meanings": [{"term_id": 1, "meaning": "pioggia"}]}


@pytest.fixture
def fake(monkeypatch):
    def install(responses, model="claude-sonnet-5-5"):
        client = _FakeClient(responses)
        monkeypatch.setattr(claude_service, "_client", client)
        monkeypatch.setattr(settings, "claude_generation_model", model)
        return client
    return install


def test_request_uses_auto_tool_choice_effort_and_no_temperature(fake):
    client = fake([_response([_tool_use("submit_term_meanings", MEANINGS)], "tool_use")])
    meanings, usage = claude_service.translate_terms(TERMS, "ja", "it")

    assert meanings == {1: "pioggia"}
    assert usage == {"input_tokens": 10, "output_tokens": 5}
    request = client.calls[0]
    assert request["tool_choice"] == {"type": "auto"}
    assert request["output_config"] == {"effort": settings.claude_generation_effort}
    assert "temperature" not in request
    assert request["tools"][0]["strict"] is True
    assert "submit_term_meanings" in request["messages"][0]["content"]


def test_strict_schema_closes_every_object():
    schema = claude_service._SUBMIT_TERM_MEANINGS_TOOL["input_schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["meanings"]["items"]["additionalProperties"] is False


def test_sonnet_gets_the_server_side_fallback(fake):
    client = fake([_response([_tool_use("submit_term_meanings", MEANINGS)], "tool_use")])
    claude_service.translate_terms(TERMS, "ja", "it")
    request = client.calls[0]
    assert request["beta"] is True
    assert request["betas"] == [claude_service._FALLBACK_BETA]
    assert request["extra_body"] == {"fallbacks": "default"}


def test_haiku_has_no_server_side_fallback(fake):
    client = fake([_response([_tool_use("submit_term_meanings", MEANINGS)], "tool_use")], model="claude-haiku-5-5")
    claude_service.translate_terms(TERMS, "ja", "it")
    request = client.calls[0]
    assert request["beta"] is False
    assert "betas" not in request and "extra_body" not in request


def test_missing_tool_call_is_asked_again_once(fake):
    text_only = _response([SimpleNamespace(type="text", text="Ecco i significati.")])
    client = fake([text_only, _response([_tool_use("submit_term_meanings", MEANINGS)], "tool_use")])
    meanings, usage = claude_service.translate_terms(TERMS, "ja", "it")
    assert meanings == {1: "pioggia"}
    assert len(client.calls) == 2
    assert usage == {"input_tokens": 20, "output_tokens": 10}


def test_two_replies_without_the_tool_call_are_an_error(fake):
    text_only = _response([SimpleNamespace(type="text", text="...")])
    fake([text_only, text_only])
    with pytest.raises(ValueError, match="did not return a submit_term_meanings"):
        claude_service.translate_terms(TERMS, "ja", "it")


def test_refusal_is_an_error_without_retry(fake):
    client = fake([_response([], "refusal")])
    with pytest.raises(ValueError, match="declined"):
        claude_service.translate_terms(TERMS, "ja", "it")
    assert len(client.calls) == 1


def test_truncated_reply_is_an_error(fake):
    fake([_response([_tool_use("submit_term_meanings", {"meanings": []})], "max_tokens")])
    with pytest.raises(ValueError, match="max_tokens"):
        claude_service.translate_terms(TERMS, "ja", "it")


def test_generation_request(fake):
    exercise = {
        "spec_id": "s1",
        "phrase_translations": [
            {"language": "ja", "content": "雨が ふっています。"},
            {"language": "it", "content": "Sta piovendo."},
        ],
        "payload": {"question": "?", "options": ["a", "b", "c", "d"], "correct_index": 0},
    }
    client = fake([_response([_tool_use("submit_new_exercises", {"exercises": [exercise]})], "tool_use")])
    items, _usage = claude_service.generate_exercises_for_gap(
        specs=[], source_language="it", target_language="ja",
        track_guidelines="", type_instructions={},
    )
    assert [item.spec_id for item in items] == ["s1"]
    request = client.calls[0]
    assert request["tool_choice"] == {"type": "auto"}
    assert "temperature" not in request
    assert "submit_new_exercises" in request["system"]


def test_chat_history_keeps_thinking_blocks():
    from anthropic.types import Message

    message = Message.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "Ok!"},
            {"type": "tool_use", "id": "tu_1", "name": "request_exercises", "input": {"difficulty": 1}},
        ],
    })
    turn = chat._assistant_turn(message)
    assert turn["role"] == "assistant"
    assert [b["type"] for b in turn["content"]] == ["thinking", "text", "tool_use"]
    assert turn["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert turn["content"][1] == {"type": "text", "text": "Ok!"}


def test_chat_request_shape():
    session = {"system_prompt": "S", "tool": {"name": "request_exercises"}, "messages": []}
    request = chat._chat_request(session)
    assert request["model"] == settings.claude_chat_model
    assert request["output_config"] == {"effort": settings.claude_chat_effort}
    assert "temperature" not in request
    assert request["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}


def _tool_call_turn(*ids):
    return {"role": "assistant", "content": [
        {"type": "text", "text": "Ok!"},
        *({"type": "tool_use", "id": i, "name": "request_exercises", "input": {}} for i in ids),
    ]}


def test_every_tool_use_gets_a_tool_result():
    # A reply with two calls: the one being run gets its result, the other one
    # a "not run" result (the API rejects a tool_use left without one).
    results = chat._tool_results([_tool_call_turn("tu_1", "tu_2")], {"tu_1": {"content": "{}"}})
    assert [(r["tool_use_id"], r["content"]) for r in results] == [("tu_1", "{}"), ("tu_2", chat._NOT_RUN)]


def test_no_tool_results_after_a_user_turn_or_plain_text():
    assert chat._tool_results([{"role": "user", "content": "ciao"}], {}) == []
    assert chat._tool_results([{"role": "assistant", "content": [{"type": "text", "text": "Ciao"}]}], {}) == []


def test_message_after_a_reply_with_a_tool_call_closes_it(monkeypatch):
    # e.g. the feedback reply called request_exercises: nothing ran it, so the
    # next user message must start with its tool_result.
    import asyncio

    class _Stop(Exception):
        pass

    def stream(**kwargs):
        raise _Stop

    monkeypatch.setattr(chat, "_async_client", SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    session = {"system_prompt": "S", "tool": {"name": "request_exercises"}, "phase": "negotiating",
               "pending_tool_use_id": None, "messages": [{"role": "user", "content": "x"}, _tool_call_turn("tu_7")]}

    async def run():
        return [event async for event in chat._stream_chat_message(session, "Grazie!")]

    asyncio.run(run())
    last = session["messages"][-1]
    assert last["role"] == "user"
    assert last["content"][0] == {"type": "tool_result", "tool_use_id": "tu_7", "content": chat._NOT_RUN}
    assert last["content"][1] == {"type": "text", "text": "Grazie!"}


def _exercise(exercise_type, payload):
    return {
        "exercise_type": exercise_type, "difficulty": 1, "topics": ["weather"], "payload": payload,
        "source_language": "it", "target_language": "ja",
        "phrase_translations": [
            {"language": "ja", "content": "雨が ふっています。"},
            {"language": "it", "content": "Sta piovendo."},
        ],
    }


def test_results_summary_gives_the_model_the_question():
    fill = _exercise("fill_blank", {
        "sentence_with_blank": "___が ふっています。", "options": ["雨", "本", "店", "駅"],
        "correct": "雨", "explanation": "雨 (あめ) = pioggia.",
    })
    romaji = _exercise("romaji_input", {"sentence": "雨が ふっています。", "focus": "雨", "expected": "ame"})
    summary = chat.build_results_summary([
        {"exercise": fill, "result": {"correct": False, "user_answer": "本", "correct_answer": "雨",
                                      "explanation": "雨 (あめ) = pioggia."}},
        {"exercise": romaji, "result": {"correct": True, "user_answer": "ame", "correct_answer": "ame"}},
    ])
    assert (summary["exercises_completed"], summary["correct_count"], summary["score_pct"]) == (2, 1, 50)
    first, second = summary["details"]
    assert first["number"] == 1 and first["correct"] is False
    assert first["prompt"] == "___が ふっています。"
    assert first["options"] == ["雨", "本", "店", "駅"]
    assert first["sentence"] == "雨が ふっています。"
    assert first["sentence_translation"] == "Sta piovendo."
    assert (first["user_answer"], first["correct_answer"]) == ("本", "雨")
    # Typed answer: no options, the focus word instead.
    assert second["number"] == 2 and second["correct"] is True
    assert second["focus"] == "雨" and "options" not in second


def _summary(correct_flags):
    details = [
        {"number": i, "exercise_type": "fill_blank", "prompt": f"frase {i}", "correct": ok,
         "user_answer": "に", "correct_answer": "で"}
        for i, ok in enumerate(correct_flags, 1)
    ]
    return {"exercises_completed": len(details), "correct_count": sum(correct_flags), "details": details}


def test_session_note_lists_parameters_score_and_mistakes():
    note = chat.session_note({"difficulty": 2, "topics": ["weather"]}, _summary([True, False]))
    assert note.startswith("difficulty 2; topics weather: 1/2 correct")
    assert 'fill_blank "frase 2" answered "に" instead of "で"' in note
    assert "frase 1" not in note


def test_session_note_caps_the_mistakes():
    note = chat.session_note({"difficulty": 1}, _summary([False] * 8))
    assert note.count("answered") == chat.MAX_NOTE_MISTAKES
    assert note.endswith("and 3 more")


def test_compact_history_keeps_the_tool_call_and_drops_thinking():
    assistant_turn = {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "Ok!"},
        {"type": "tool_use", "id": "tu_9", "name": "request_exercises", "input": {"difficulty": 2}},
    ]}
    notes = [f"note {i}" for i in range(1, 6)]
    history = chat.compact_history(notes, "Sì, vai", assistant_turn)

    assert [m["role"] for m in history] == ["user", "assistant"]
    first = history[0]["content"]
    assert first.endswith("[Learner's message]\nSì, vai")
    # Only the most recent notes are kept.
    assert "note 1" not in first and "note 2" not in first
    assert all(f"- note {i}" in first for i in (3, 4, 5))
    assert [b["type"] for b in history[1]["content"]] == ["text", "tool_use"]
    assert history[1]["content"][1]["id"] == "tu_9"
    # The original turn is not modified.
    assert assistant_turn["content"][0]["type"] == "thinking"


def test_delete_session_forgets_it():
    from app.session_store import create_session, delete_session, get_session

    session_id, session = create_session(1, "ja", "S", {"name": "request_exercises"})
    assert session["history_notes"] == []
    delete_session(session_id)
    assert get_session(session_id) is None
    delete_session(session_id)  # unknown ids are ignored


def _text(text):
    return SimpleNamespace(type="text", text=text)


def test_written_tool_call_is_detected():
    assert chat.is_written_tool_call(_response([_text("[Tool call: request_exercises with difficulty 2, n_exercises 5]")]))
    assert chat.is_written_tool_call(_response([_text("[Tool call: requestexercises with difficulty 2]")]))
    assert not chat.is_written_tool_call(_response([_text("Livello 2, 10 esercizi misti. Parto?")]))
    assert not chat.is_written_tool_call(_response([_text("Ok"), _tool_use("request_exercises", {})]))


class _AsyncStream:
    def __init__(self, response):
        self._response = response
        self.text_stream = self._texts()

    async def _texts(self):
        for block in self._response.content:
            if block.type == "text":
                yield block.text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self._response


def test_written_tool_call_is_asked_again(monkeypatch):
    import asyncio
    import json as _json

    written = _response([_text("[Tool call: request_exercises with difficulty 2]")])
    real = _response([SimpleNamespace(type="tool_use", id="tu_1", name="request_exercises",
                                      input={"difficulty": 2}, model_dump=lambda **kw: {
                                          "type": "tool_use", "id": "tu_1", "name": "request_exercises",
                                          "input": {"difficulty": 2}})], "tool_use")
    written.content[0].model_dump = lambda **kw: {"type": "text", "text": written.content[0].text}
    replies = [written, real]
    requests = []

    def stream(**kwargs):
        requests.append([dict(m) for m in kwargs["messages"]])
        return _AsyncStream(replies.pop(0))

    async def fake_fetch(*args):
        return [{"id": 1}], None

    monkeypatch.setattr(chat, "_async_client", SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    monkeypatch.setattr(chat, "_fetch_exercises", fake_fetch)
    session = {"system_prompt": "S", "tool": {"name": "request_exercises"}, "phase": "negotiating",
               "pending_tool_use_id": None, "history_notes": [], "session_id": "s", "user_id": 1,
               "track": None, "messages": []}

    async def run():
        return [_json.loads(e[len("data: "):]) async for e in chat._stream_chat_message(session, "Sì")]

    events = asyncio.run(run())
    types = [e["type"] for e in events]
    assert types.index("text_reset") < types.index("phase_change")
    assert session["pending_tool_use_id"] == "tu_1" and session["phase"] == "ready"
    # The second request sees the written call and the app's note, append-only.
    assert [m["role"] for m in requests[1]] == ["user", "assistant", "user"]
    assert requests[1][2]["content"] == chat._WRITTEN_TOOL_CALL_NOTE



def test_import_fallback_runs_on_the_parse_model_with_a_strict_tool(fake, monkeypatch):
    monkeypatch.setattr(settings, "claude_parse_model", "claude-haiku-5-5")
    exercise = {
        "segment_id": "s1", "exercise_type": "romaji_input", "difficulty": None, "topics": [],
        "sentence": "山田です。", "translation": "Sono Yamada.", "question": None, "focus": "山田",
        "options": [], "alternatives": [], "explanation": None, "answer": None, "source_excerpt": "山田です。",
    }
    reply = {"exercises": [exercise, {**exercise, "segment_id": "s9"}], "skipped": [{"segment_id": "s2", "reason": "notes"}]}
    client = fake([_response([_tool_use("submit_parsed_exercises", reply)], "tool_use")])

    exercises, skipped, _ = claude_service.normalize_exercises(
        '<segment id="s1">山田です。</segment>', {"s1", "s2"}, ["romaji_input"], "ja", "it", "difficulty: 1",
    )
    assert [e.segment_id for e in exercises] == ["s1"]          # unknown segment ids are dropped
    assert [s.reason for s in skipped] == ["notes"]
    request = client.calls[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["beta"] is False                             # no server-side fallback on Haiku
    assert request["output_config"] == {"effort": settings.claude_parse_effort}
    assert request["tool_choice"] == {"type": "auto"}
    tool = request["tools"][0]
    assert tool["strict"] is True
    item_schema = tool["input_schema"]["properties"]["exercises"]["items"]
    assert set(item_schema["required"]) == set(item_schema["properties"])   # strict: every key required
    assert item_schema["properties"]["exercise_type"]["enum"] == ["romaji_input"]
    assert "never" in request["system"].lower()
