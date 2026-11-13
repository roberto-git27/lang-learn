"""
Vocabulary (D-24, stage 1), the deterministic part: sentences of a text,
terms in dictionary form (one per lemma + reading), their level, and what an
exercise is "about". Real MeCab dictionary, no DB, no network.
"""
import pytest

from app.md_import import parse_terms_text
from app.term_service import _analysis_texts, collect_terms
from app.tracks import get_track_spec
from app.tracks.japanese_payloads import text_level
from app.tracks.japanese_text import extract_terms, split_sentences

SPEC = get_track_spec("ja")


def terms(text):
    return [(t.written, t.reading, t.pos) for t in extract_terms(text)]


def test_sentences_keep_quotes_with_their_speech_verb_and_split_dialogue_lines():
    text = ("「ダニエル！ここよ！」と、ジュリアは大きな声で言いました。ジュリアは家の入口の前に\nいます。 "
            "「今日、私達は日本に行くのよ。覚えてる？」 「もちろん！」 僕の名前はダニエルです。")
    assert split_sentences(text) == [
        "「ダニエル！ここよ！」と、ジュリアは大きな声で言いました。",
        "ジュリアは家の入口の前にいます。",       # line break inside the sentence joined
        "今日、私達は日本に行くのよ。覚えてる？",   # a sentence that is only a quote loses its brackets
        "もちろん！",
        "僕の名前はダニエルです。",
    ]


def test_terms_are_dictionary_forms_without_particles_or_auxiliaries():
    assert terms("僕達はロンドンの家で一緒に住んでいます。") == [
        ("僕達", "ぼくたち", "pronoun"), ("ロンドン", "ろんどん", "proper_noun"),
        ("家", "いえ", "noun"), ("一緒", "いっしょ", "noun"), ("住む", "すむ", "verb"),
    ]


def test_one_term_per_lemma_and_reading():
    # 言いました/言った → 言う; かみ and 髪 are the same UniDic lemma
    assert terms("言いました。言った。かみが長い。髪が長い。") == [
        ("言う", "いう", "verb"), ("かみ", "かみ", "noun"), ("長い", "ながい", "i_adjective"),
    ]


@pytest.mark.parametrize("text, expected", [
    ("アメリカ人です。", ("アメリカ人", "あめりかじん", "noun")),     # suffix merged, nationality じん
    ("大学生です。", ("大学生", "だいがくせい", "noun")),
    ("私は二十四歳です。", ("二十四歳", "にじゅうよんさい", "numeral")),
    ("私です。", ("私", "わたし", "pronoun")),                       # learner reading override
])
def test_compounds_and_readings(text, expected):
    assert expected in terms(text)


@pytest.mark.parametrize("text, expected", [
    ("学校に行きます。", [("学校", "noun"), ("行く", "verb")]),                  # 行く can be an auxiliary, not here
    ("手伝ってくれます。住んでいます。", [("手伝う", "verb"), ("住む", "verb")]),   # ～てくれる, ～ている are not terms
    ("日本語を勉強します。", [("日本語", "noun"), ("勉強", "noun")]),              # 語 as suffix; する after a verbal noun
    ("本があります。", [("本", "noun"), ("ある", "verb")]),
])
def test_auxiliaries_only_after_te_form(text, expected):
    assert [(w, p) for w, _, p in terms(text)] == expected


def test_parse_terms_text_drops_front_matter_headings_and_comments():
    body, errors = parse_terms_text("---\nmode: terms  # vocabulary\n---\n# Chapter 1\n<!-- note -->\n学校に行きます。\n", SPEC)
    assert (body, errors) == ("学校に行きます。", [])
    body, _ = parse_terms_text("<!-- a note\n   on two lines -->\n本です。<!-- inline -->", SPEC)
    assert body == "本です。"
    assert parse_terms_text("---\nmode: generate\n---\n本", SPEC)[1] == ["line 2: this file is for the Studio's 'generate' mode, not 'terms'"]


def test_words_without_japanese_script_are_not_terms():
    assert terms("Chapter 1 は学校です。") == [("学校", "がっこう", "noun")]


@pytest.mark.parametrize("text, has_nai", [
    ("中国人ではなくて、韓国人です。", False),
    ("学生じゃない。", False),
    ("高くない。", False),
    ("お金がない。", True),
])
def test_nai_is_a_term_only_when_it_is_a_word(text, has_nai):
    assert any(w == "ない" for w, _, _ in terms(text)) is has_nai


def test_honorifics_are_not_part_of_the_name():
    assert terms("マルコさんと山田さん。マルコは学生です。") == [
        ("マルコ", "まるこ", "proper_noun"), ("山田", "やまだ", "proper_noun"), ("学生", "がくせい", "noun"),
    ]


def test_digits_are_not_terms():
    assert terms("24歳です。") == []


@pytest.mark.parametrize("text, level", [("学生", 1), ("学校", 2), ("家", 3), ("わたし", 1)])
def test_text_level_is_the_lowest_level_accepting_its_kanji(text, level):
    assert text_level(text) == level


def test_collect_terms_keeps_the_first_sentence_of_each_term():
    found = collect_terms(SPEC, "学校に行きます。学校は大きいです。")
    assert [(c.written, example) for c, example in found] == [
        ("学校", "学校に行きます。"), ("行く", "学校に行きます。"), ("大きい", "学校は大きいです。"),
    ]


def test_kanji_writing_is_analyzed_with_its_correct_spelling():
    payload = {"sentence": "わたしは　がくせい　ではありません。", "focus": "がくせい", "options": ["学校", "学生"], "correct_index": 1}
    sentence, focus = _analysis_texts("kanji_writing", payload["sentence"], payload)
    assert (sentence, focus) == ("わたしは　学生　ではありません。", "学生")
    assert terms(sentence) == [("わたし", "わたし", "pronoun"), ("学生", "がくせい", "noun"), ("ある", "ある", "verb")]
    assert terms("わたしは　がくせい　ではありません。")[1:3] != [("学生", "がくせい", "noun")]   # why: kana alone splits badly


def test_other_types_are_analyzed_as_they_are():
    payload = {"sentence": "これは 本です。", "focus": "本"}
    assert _analysis_texts("kanji_reading", "これは 本です。", payload) == ("これは 本です。", "本")
    assert _analysis_texts("fill_blank", "わたしは がくせいです。", {"sentence_with_blank": "わたし___"}) == ("わたしは がくせいです。", "")
