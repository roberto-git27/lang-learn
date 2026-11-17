"""
Hand-made reading overrides applied by the Japanese text module (furigana,
romaji, exercise annotations), on the real dictionary. No DB.
"""
import pytest

from app.tracks import get_track_spec
from app.tracks.japanese_text import annotate, reading_override_problems, romaji, set_reading_overrides

SPEC = get_track_spec("ja")
TEXT = "ペンが 五本 あります。日本の本です。"


@pytest.fixture(autouse=True)
def no_overrides_left():
    yield
    set_reading_overrides({})


def _readings(text):
    return [(s["text"], s.get("reading")) for s in annotate(text) if s.get("reading")]


def test_without_overrides_the_dictionary_reading_is_used():
    assert ("本", "ぽん") in _readings(TEXT)
    assert romaji("五本")[0] == "gopon"


def test_a_multi_token_word_gets_one_reading_in_furigana_and_romaji():
    set_reading_overrides({"五本": "ごほん"})
    assert _readings(TEXT) == [("五本", "ごほん"), ("日本", "にほん"), ("本", "ほん")]
    assert romaji("五本")[0] == "gohon"
    assert "".join(s["text"] for s in annotate(TEXT)) == TEXT


def test_an_override_never_cuts_a_longer_word():
    set_reading_overrides({"本": "もと"})
    assert ("日本", "にほん") in _readings(TEXT)    # one token: untouched
    assert ("本", "もと") in _readings(TEXT)


def test_katakana_readings_are_stored_in_hiragana_and_okurigana_stay_outside():
    set_reading_overrides({"火曜日": "カヨウビ", "行きます": "いきます"})
    assert _readings("火曜日に 行きます") == [("火曜日", "かようび"), ("行", "い")]


def test_the_longest_word_wins():
    set_reading_overrides({"本": "もと", "五本": "ごほん"})
    assert _readings("五本")[0] == ("五本", "ごほん")


def test_annotations_and_romaji_payloads_follow_the_override():
    payload = SPEC.validate_payload("romaji_input", {"sentence": "ペンが 五本 あります。", "focus": "五本"})
    assert payload["expected"] == "gopon"
    set_reading_overrides({"五本": "ごほん"})
    payload = SPEC.validate_payload("romaji_input", payload)
    assert payload["expected"] == "gohon"
    sentence = SPEC.annotations_for("romaji_input", payload)["sentence"]
    assert {"text": "五本", "reading": "ごほん", "focus": True} in sentence


@pytest.mark.parametrize("surface, reading, ok", [
    ("五本", "ごほん", True),
    ("五本", "ゴホン", True),
    ("ほん", "ほん", False),         # no kanji: no furigana to fix
    ("五 本", "ごほん", False),
    ("五本", "gohon", False),
    ("五本", "", False),
])
def test_override_validation(surface, reading, ok):
    assert (reading_override_problems(surface, reading) == []) is ok
