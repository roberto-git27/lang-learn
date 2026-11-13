"""
Studio generation, the pure part (`app/studio_generation.py`): the plan of
specs, the checks on what the model returns, and the conversion to the
items shared with the import. No DB, no network, no Anthropic.
"""
from app.md_import import GenerationRequest, Term
from app.schemas import GeneratedExerciseItem, LLMTranslation, NewExerciseSpec
from app.studio_generation import check_studio_item, plan_specs, to_parsed_exercise
from app.tracks import get_track_spec

SPEC = get_track_spec("ja")
LANGUAGES = {"ja", "it"}


def test_plan_gives_each_term_per_term_exercises_rotating_the_types():
    request = GenerationRequest(difficulty=1, per_term=2, types=["kanji_reading", "kanji_writing", "fill_blank"],
                                terms=[Term(text="一"), Term(text="二", note="due")], topics=["numbers_counters"])
    specs = plan_specs(request, ["multiple_choice"])
    assert [(s.term, s.exercise_type) for s in specs] == [
        ("一", "kanji_reading"), ("一", "kanji_writing"), ("二", "kanji_writing"), ("二", "fill_blank"),
    ]
    assert [s.spec_id for s in specs] == ["s1", "s2", "s3", "s4"]
    assert specs[2].term_note == "due" and all(s.difficulty == 1 and s.topics == ["numbers_counters"] for s in specs)


def test_plan_without_terms_uses_count_and_the_default_types():
    specs = plan_specs(GenerationRequest(difficulty=2, count=3), ["fill_blank", "multiple_choice"])
    assert [s.exercise_type for s in specs] == ["fill_blank", "multiple_choice", "fill_blank"]
    assert all(s.term is None for s in specs)


def _item(spec_id, sentence, focus, options, correct=0, translation="Sono uno studente."):
    return GeneratedExerciseItem(
        spec_id=spec_id,
        phrase_translations=[LLMTranslation(language="ja", content=sentence), LLMTranslation(language="it", content=translation)],
        detected_topics=["Self introduction"],
        payload={"sentence": sentence, "focus": focus, "options": options, "correct_index": correct},
    )


def test_check_accepts_an_item_that_uses_its_term():
    spec = NewExerciseSpec(spec_id="s1", exercise_type="kanji_reading", difficulty=1, term="学")
    payload, reason = check_studio_item(SPEC, spec, _item("s1", "わたしは 学生です。", "学生", ["がくせい", "がっせい", "がくせ", "かくせい"]), LANGUAGES)
    assert reason is None and payload["focus"] == "学生"


def test_check_rejects_an_item_that_ignores_its_term():
    spec = NewExerciseSpec(spec_id="s1", exercise_type="kanji_reading", difficulty=1, term="火")
    payload, reason = check_studio_item(SPEC, spec, _item("s1", "わたしは 学生です。", "学生", ["がくせい", "がっせい", "がくせ", "かくせい"]), LANGUAGES)
    assert payload is None and "does not use the term '火'" in reason


def test_check_keeps_the_level_gate():
    spec = NewExerciseSpec(spec_id="s1", exercise_type="kanji_reading", difficulty=1, term="医")
    payload, reason = check_studio_item(SPEC, spec, _item("s1", "医者です。", "医者", ["いしゃ", "いしや", "いじゃ", "いさ"], translation="È un medico."), LANGUAGES)
    assert payload is None and "kanji above level 1" in reason


def test_to_parsed_exercise_shapes_a_generated_item_like_an_imported_one():
    spec = NewExerciseSpec(spec_id="s1", exercise_type="kanji_reading", difficulty=1, topics=["school"], term="学")
    item = _item("s1", "わたしは 学生です。", "学生", ["がくせい", "がっせい", "がくせ", "かくせい"])
    payload, _ = check_studio_item(SPEC, spec, item, LANGUAGES)
    parsed = to_parsed_exercise(4, spec, item, payload, None, SPEC, "ja", "it")
    assert parsed.is_valid and parsed.line == 4 and parsed.term == "学"
    assert parsed.topics == ["school"]   # the request's topics win over the detected ones
    spec.topics = []
    assert to_parsed_exercise(4, spec, item, payload, None, SPEC, "ja", "it").topics == ["self_introduction"]
    assert (parsed.phrase_target, parsed.phrase_base) == ("わたしは 学生です。", "Sono uno studente.")
    assert parsed.annotations["sentence"][1] == {"text": "学生", "focus": True}


def test_to_parsed_exercise_keeps_the_reason_of_a_rejected_item():
    spec = NewExerciseSpec(spec_id="s2", exercise_type="fill_blank", difficulty=1, term="一")
    parsed = to_parsed_exercise(2, spec, None, None, "not returned by the model", SPEC, "ja", "it")
    assert not parsed.is_valid and parsed.errors == ["not returned by the model"] and parsed.payload is None
