"""
End-to-end tests of `exercise_agent.select_or_generate_exercises` with the DB
queries, the Claude call and the persistence step replaced by fakes: they
check that the exercises generated to fill a gap end up in the session
returned to the chat, next to the ones found in the DB (e.g. 5 requested,
3 found, 2 generated → 5 delivered).
"""
import asyncio
from types import SimpleNamespace

from app import exercise_agent
from app.schemas import ExerciseResponse, GeneratedExerciseItem

LIGHT = ["fill_blank", "kanji_reading", "kanji_writing", "multiple_choice"]
TYPED = ["romaji_input", "translate_rev"]
TRACK = SimpleNamespace(
    id=1, code="ja",
    target_language=SimpleNamespace(code="ja"), base_language=SimpleNamespace(code="it"),
)


def _response(id: int, exercise_type: str, is_new: bool) -> ExerciseResponse:
    return ExerciseResponse(
        id=id, track="ja", exercise_type=exercise_type, source_language="it", target_language="ja",
        difficulty=2, payload={}, phrase_id=id, phrase_translations=[], topics=[], is_new_phrase=is_new,
    )


class FakeDb:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _install_fakes(monkeypatch, db_pool: int, reject_first_round: set[str] = frozenset(),
                   always_reject: set[str] = frozenset()):
    """
    `db_pool` exercises exist in the DB (handed out across bucket queries,
    any type); Claude answers every spec it is asked for, except the
    rejected ones. Returns a dict recording the calls.
    """
    calls = {"claude": [], "persisted": []}
    pool = list(range(1, db_pool + 1))
    type_ids = {code: i for i, code in enumerate(LIGHT + TYPED, start=1)}
    type_codes = {i: code for code, i in type_ids.items()}

    async def no_topics(db, track, codes):
        return []

    async def no_review(db, user_id, track_id, type_id, limit):
        return []

    async def nothing_seen(db, user_id, limit=300):
        return set()

    async def query_candidates(db, track_id, difficulty, topic_ids, type_id, used_ids, count):
        found = []
        while pool and len(found) < count:
            found.append(SimpleNamespace(id=pool.pop(0), exercise_type=SimpleNamespace(code=type_codes[type_id])))
        return found

    async def no_references(db, track_id, type_id, topic_ids):
        return []

    def generate(specs, *args, **kwargs):
        round_no = len(calls["claude"])
        calls["claude"].append([s.spec_id for s in specs])
        items = []
        for s in specs:
            bad = s.spec_id in always_reject or (round_no == 0 and s.spec_id in reject_first_round)
            items.append(GeneratedExerciseItem(
                spec_id=s.spec_id, phrase_translations=[], payload={"bad": bad},
            ))
        return items, {"input_tokens": 10, "output_tokens": 20}

    def check(track_spec, spec, item, language_codes):
        return (None, "rejected by test") if item.payload["bad"] else (item.payload, None)

    async def persist(db, track, spec, item, payload):
        new_id = 1000 + len(calls["persisted"])
        calls["persisted"].append(new_id)
        return _response(new_id, spec.exercise_type, is_new=True)

    def to_response(ex):
        return _response(ex.id, ex.exercise_type.code, is_new=False)

    monkeypatch.setattr(exercise_agent, "get_or_create_topics", no_topics)
    monkeypatch.setattr(exercise_agent, "_get_review_candidates", no_review)
    monkeypatch.setattr(exercise_agent, "_get_recently_seen_exercise_ids", nothing_seen)
    monkeypatch.setattr(exercise_agent, "_query_candidates", query_candidates)
    monkeypatch.setattr(exercise_agent, "_get_reference_exercises", no_references)
    monkeypatch.setattr(exercise_agent, "_persist_generated_item", persist)
    monkeypatch.setattr(exercise_agent, "check_generated_item", check)
    monkeypatch.setattr(exercise_agent, "exercise_to_response", to_response)
    monkeypatch.setattr(exercise_agent, "track_light_type_codes", lambda track: LIGHT)
    monkeypatch.setattr(exercise_agent, "track_type_codes", lambda track: LIGHT + TYPED)
    monkeypatch.setattr(exercise_agent, "track_exercise_type_id", lambda track, code: type_ids[code])
    monkeypatch.setattr(exercise_agent, "get_track_spec", lambda code: SimpleNamespace(
        generation_guidelines="", type_instructions={},
    ))
    monkeypatch.setattr(exercise_agent.claude_service, "generate_exercises_for_gap", generate)
    return calls


def _run(filters: dict, db: FakeDb):
    user = SimpleNamespace(id=1)
    return asyncio.run(exercise_agent.select_or_generate_exercises(db, user, TRACK, filters))


def test_generated_exercises_are_delivered_with_db_ones(monkeypatch):
    calls = _install_fakes(monkeypatch, db_pool=3)
    db = FakeDb()
    result = _run({"difficulty": 2, "n_exercises": 5}, db)

    ids = [ex.id for ex in result.exercises]
    assert len(ids) == 5
    assert sorted(ids) == [1, 2, 3, 1000, 1001]
    assert sum(ex.is_new_phrase for ex in result.exercises) == 2
    assert len(calls["claude"]) == 1 and len(calls["claude"][0]) == 2
    assert result.trace["db_found_count"] == 3
    assert result.trace["gap_count"] == 2
    assert result.trace["unfilled_spec_ids"] == []
    assert sorted(result.trace["final_exercise_ids"]) == sorted(ids)
    assert db.commits == 1


def test_empty_db_delivers_only_generated(monkeypatch):
    _install_fakes(monkeypatch, db_pool=0)
    result = _run({"difficulty": 2, "n_exercises": 5}, FakeDb())
    assert len(result.exercises) == 5
    assert all(ex.is_new_phrase for ex in result.exercises)


def test_item_rejected_once_is_retried_and_delivered(monkeypatch):
    calls = _install_fakes(monkeypatch, db_pool=3)
    _run({"difficulty": 2, "n_exercises": 5}, FakeDb())
    victim = calls["claude"][0][0]

    calls = _install_fakes(monkeypatch, db_pool=3, reject_first_round={victim})
    result = _run({"difficulty": 2, "n_exercises": 5}, FakeDb())
    assert calls["claude"][1] == [victim]  # the top-up asks only for the rejected spec
    assert result.trace["unfilled_spec_ids"] == []
    assert len(result.exercises) == 5


def test_item_rejected_twice_gives_a_partial_session(monkeypatch):
    calls = _install_fakes(monkeypatch, db_pool=3)
    # learn the spec ids the plan produces, then reject one of them for good
    _run({"difficulty": 2, "n_exercises": 5}, FakeDb())
    victim = calls["claude"][0][0]

    calls = _install_fakes(monkeypatch, db_pool=3, always_reject={victim})
    result = _run({"difficulty": 2, "n_exercises": 5}, FakeDb())
    assert len(calls["claude"]) == 2  # first call + one top-up
    assert result.trace["unfilled_spec_ids"] == [victim]
    assert len(result.exercises) == 4  # 3 from the DB + the other generated one


def test_forced_type_generated_exercises_are_delivered(monkeypatch):
    _install_fakes(monkeypatch, db_pool=2)
    result = _run({"difficulty": 2, "n_exercises": 3, "exercise_type": "fill_blank"}, FakeDb())
    assert len(result.exercises) == 3
    assert all(ex.exercise_type == "fill_blank" for ex in result.exercises if ex.is_new_phrase)
    assert sum(ex.is_new_phrase for ex in result.exercises) == 1
