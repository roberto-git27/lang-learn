"""
Unit tests for the pure (no DB, no network) functions in
`app.exercise_agent` — the deterministic bucketing/gap/ordering logic behind
the exercise selection/generation agent (Phase 1). See that module's
docstring for the full pipeline these functions are pieces of.
"""
from app.exercise_agent import (
    BucketSizes,
    build_gap_specs,
    check_generated_item,
    compute_bucket_sizes,
    order_anti_adjacency,
    plan_slot_types,
    reallocate_review_shortfall,
)
from app.schemas import ExerciseResponse, GeneratedExerciseItem, NewExerciseSpec
from app.tracks import get_track_spec

# Mirrors the Japanese track seed: option-based ("light") and typed types.
LIGHT = ["fill_blank", "kanji_reading", "kanji_writing", "multiple_choice"]
TYPED = ["romaji_input", "translate_rev"]


def _make_exercise(id: int, exercise_type: str, phrase_id: int = 1) -> ExerciseResponse:
    return ExerciseResponse(
        id=id,
        track="ja",
        exercise_type=exercise_type,
        source_language="it",
        target_language="ja",
        difficulty=2,
        payload={},
        phrase_id=phrase_id,
        phrase_translations=[],
        topics=[],
        is_new_phrase=False,
    )


# ---------------------------------------------------------------------------
# compute_bucket_sizes
# ---------------------------------------------------------------------------
def test_compute_bucket_sizes_default_session():
    sizes = compute_bucket_sizes(10)
    assert sizes == BucketSizes(topic=6, review=2, harder=2)


def test_compute_bucket_sizes_absorbs_rounding_remainder_into_topic():
    sizes = compute_bucket_sizes(11)
    assert sizes.review + sizes.harder + sizes.topic == 11
    assert sizes.review == round(11 * 0.2)
    assert sizes.harder == round(11 * 0.2)


def test_compute_bucket_sizes_floors_n_exercises_at_one():
    sizes = compute_bucket_sizes(0)
    assert sizes.topic + sizes.review + sizes.harder == 1


def test_compute_bucket_sizes_small_session_topic_share_can_be_low():
    # Documented accepted side-effect, not a bug: small sessions can end up
    # with a topic share well below 60%.
    sizes = compute_bucket_sizes(3)
    assert sizes.topic + sizes.review + sizes.harder == 3


# ---------------------------------------------------------------------------
# reallocate_review_shortfall
# ---------------------------------------------------------------------------
def test_reallocate_review_shortfall_full_match_no_change():
    sizes = BucketSizes(topic=6, review=2, harder=2)
    result = reallocate_review_shortfall(sizes, actual_review_count=2)
    assert result == BucketSizes(topic=6, review=2, harder=2)


def test_reallocate_review_shortfall_partial_moves_gap_to_topic():
    sizes = BucketSizes(topic=6, review=2, harder=2)
    result = reallocate_review_shortfall(sizes, actual_review_count=1)
    assert result == BucketSizes(topic=7, review=1, harder=2)


def test_reallocate_review_shortfall_zero_found_moves_everything_to_topic():
    sizes = BucketSizes(topic=6, review=2, harder=2)
    result = reallocate_review_shortfall(sizes, actual_review_count=0)
    assert result == BucketSizes(topic=8, review=0, harder=2)


def test_reallocate_review_shortfall_clamps_more_than_requested():
    sizes = BucketSizes(topic=6, review=2, harder=2)
    result = reallocate_review_shortfall(sizes, actual_review_count=99)
    assert result == BucketSizes(topic=6, review=2, harder=2)


# ---------------------------------------------------------------------------
# plan_slot_types
# ---------------------------------------------------------------------------
def test_plan_forced_type_fills_every_slot():
    assert plan_slot_types(4, "fill_blank", LIGHT, TYPED, typed_budget=2) == ["fill_blank"] * 4


def test_plan_caps_typed_answers_per_session():
    types = plan_slot_types(10, None, LIGHT, TYPED, typed_budget=2)
    assert len(types) == 10
    assert sum(t in TYPED for t in types) == 2


def test_plan_never_starts_with_or_chains_typed_answers():
    for n in range(1, 16):
        types = plan_slot_types(n, None, LIGHT, TYPED, typed_budget=2)
        assert not types or types[0] in LIGHT
        assert all(not (a in TYPED and b in TYPED) for a, b in zip(types, types[1:]))


def test_plan_respects_an_exhausted_budget():
    assert all(t in LIGHT for t in plan_slot_types(8, None, LIGHT, TYPED, typed_budget=0))
    assert all(t in LIGHT for t in plan_slot_types(8, None, LIGHT, TYPED, typed_budget=-1))


def test_plan_cycles_through_every_light_type():
    types = plan_slot_types(8, None, LIGHT, TYPED, typed_budget=0)
    assert set(types) == set(LIGHT)


def test_plan_track_without_light_types():
    assert plan_slot_types(3, None, [], ["translate_rev"], typed_budget=2) == ["translate_rev"] * 3


# ---------------------------------------------------------------------------
# check_generated_item
# ---------------------------------------------------------------------------
JA = get_track_spec("ja")
LANGS = {"ja", "it"}


def _item(payload, translations=(("ja", "わたしは 学生です。"), ("it", "Sono uno studente."))):
    return GeneratedExerciseItem(
        spec_id="topic-1",
        phrase_translations=[{"language": lang, "content": text} for lang, text in translations],
        payload=payload,
    )


def _spec(exercise_type, difficulty=1):
    return NewExerciseSpec(spec_id="topic-1", exercise_type=exercise_type, difficulty=difficulty)


READING = {"sentence": "わたしは 学生です。", "focus": "学生", "options": ["がくせい", "がっせい", "がくせ", "かくせい"], "correct_index": 0}


def test_check_accepts_a_valid_item_and_normalizes_it():
    payload, reason = check_generated_item(JA, _spec("kanji_reading"), _item({**READING, "extra": "dropped"}), LANGS)
    assert reason is None
    assert "extra" not in payload


def test_check_rejects_an_invalid_payload():
    payload, reason = check_generated_item(JA, _spec("kanji_reading"), _item({**READING, "focus": "先生"}), LANGS)
    assert payload is None and reason.startswith("invalid payload") and "focus" in reason


def test_check_rejects_kanji_above_level_one():
    above = {**READING, "sentence": "わたしは 医者です。", "focus": "医者", "options": ["いしゃ", "いし", "いっしゃ", "えしゃ"]}
    payload, reason = check_generated_item(JA, _spec("kanji_reading", difficulty=1), _item(above), LANGS)
    assert payload is None and "above level 1" in reason
    payload, reason = check_generated_item(JA, _spec("kanji_reading", difficulty=3), _item(above), LANGS)
    assert reason is None


def test_level_gate_has_two_beginner_steps():
    school = {"sentence": "がっこうに 行きます。", "focus": "がっこう", "options": ["学校", "学生", "校学", "大学"], "correct_index": 0}
    translations = (("ja", "がっこうに 行きます。"), ("it", "Vado a scuola."))
    _, reason = check_generated_item(JA, _spec("kanji_writing", difficulty=1), _item(school, translations), LANGS)
    assert "above level 1" in reason          # 校 and 行 are N5, not first-lesson kanji
    _, reason = check_generated_item(JA, _spec("kanji_writing", difficulty=2), _item(school, translations), LANGS)
    assert reason is None


def test_check_requires_both_track_languages():
    payload, reason = check_generated_item(JA, _spec("kanji_reading"), _item(READING, translations=(("ja", "わたしは 学生です。"),)), LANGS)
    assert payload is None and "missing languages" in reason


# ---------------------------------------------------------------------------
# build_gap_specs
# ---------------------------------------------------------------------------
def test_build_gap_specs_no_gap_when_fully_found():
    specs, counter = build_gap_specs("topic", "multiple_choice", requested=3, found=3, difficulty=2, topic_codes=[], start_counter=0)
    assert specs == []
    assert counter == 0


def test_build_gap_specs_partial_gap():
    specs, counter = build_gap_specs("topic", "fill_blank", requested=3, found=1, difficulty=2, topic_codes=["food"], start_counter=0)
    assert len(specs) == 2
    assert counter == 2
    assert [s.spec_id for s in specs] == ["topic-1", "topic-2"]
    assert all(s.exercise_type == "fill_blank" and s.difficulty == 2 and s.topics == ["food"] for s in specs)


def test_build_gap_specs_total_gap_when_nothing_found():
    specs, counter = build_gap_specs("harder", "translate_rev", requested=2, found=0, difficulty=3, topic_codes=[], start_counter=0)
    assert len(specs) == 2
    assert counter == 2


def test_build_gap_specs_counter_progresses_across_calls():
    first_specs, counter = build_gap_specs("topic", "multiple_choice", requested=2, found=0, difficulty=2, topic_codes=[], start_counter=0)
    second_specs, counter = build_gap_specs("topic", "fill_blank", requested=1, found=0, difficulty=2, topic_codes=[], start_counter=counter)
    assert [s.spec_id for s in first_specs] == ["topic-1", "topic-2"]
    assert [s.spec_id for s in second_specs] == ["topic-3"]
    assert counter == 3


def test_build_gap_specs_never_negative_when_found_exceeds_requested():
    specs, counter = build_gap_specs("topic", "multiple_choice", requested=1, found=5, difficulty=2, topic_codes=[], start_counter=0)
    assert specs == []
    assert counter == 0


# ---------------------------------------------------------------------------
# order_anti_adjacency
# ---------------------------------------------------------------------------
def test_order_anti_adjacency_empty_and_single_are_unchanged():
    assert order_anti_adjacency([]) == []
    single = [_make_exercise(1, "multiple_choice")]
    assert order_anti_adjacency(single) == single


def test_order_anti_adjacency_separates_same_type_when_possible():
    exercises = [
        _make_exercise(1, "multiple_choice"),
        _make_exercise(2, "multiple_choice"),
        _make_exercise(3, "fill_blank"),
    ]
    ordered = order_anti_adjacency(exercises)
    types = [e.exercise_type for e in ordered]
    assert all(types[i] != types[i + 1] for i in range(len(types) - 1))


def test_order_anti_adjacency_separates_adjacent_same_phrase():
    exercises = [
        _make_exercise(1, "multiple_choice", phrase_id=42),
        _make_exercise(2, "fill_blank", phrase_id=42),
        _make_exercise(3, "translate_rev", phrase_id=7),
    ]
    ordered = order_anti_adjacency(exercises)
    phrase_ids = [e.phrase_id for e in ordered]
    assert all(phrase_ids[i] != phrase_ids[i + 1] for i in range(len(phrase_ids) - 1))


def test_order_anti_adjacency_preserves_all_items():
    exercises = [_make_exercise(i, "multiple_choice") for i in range(5)]
    ordered = order_anti_adjacency(exercises)
    assert {e.id for e in ordered} == {e.id for e in exercises}
    assert len(ordered) == len(exercises)
