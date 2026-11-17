"""
`.csv` term lists for the Studio's Vocabulary mode (`app/term_list.py`) and
`TrackSpec.dictionary_term` on the real dictionary. No DB.
"""
import pytest

from app.term_list import is_term_list, parse_term_list
from app.tracks import get_track_spec
from app.tracks.japanese_text import dictionary_term

SPEC = get_track_spec("ja")


@pytest.mark.parametrize("word, reading, expected", [
    ("学生", None, ("学生", "がくせい", "学生", "noun")),
    ("食べます", None, ("食べる", "たべる", "食べる", "verb")),        # inflected: the dictionary form, as in texts
    ("のむ", None, ("飲む", "のむ", "のむ", "verb")),
    ("お茶", None, ("お茶", "おちゃ", "お茶", "noun")),               # MeCab would keep only 茶
    ("こんにちは", None, ("こんにちは", "こんにちは", "こんにちは", "expression")),
    ("がくせい", None, ("がくせい", "がくせい", "がくせい", "expression")),   # kana MeCab splits: kept whole
    ("日", None, ("日", "ひ", "日", "noun")),
    ("日", "にち", ("日", "にち", "日", "noun")),                   # the given reading wins: another term
    ("ガクセイ", "ガクセイ", ("ガクセイ", "がくせい", "ガクセイ", "expression")),   # reading in hiragana
])
def test_dictionary_term(word, reading, expected):
    term = dictionary_term(word, reading)
    assert (term.lemma, term.reading, term.written, term.pos) == expected


def test_dictionary_term_of_an_empty_word():
    assert dictionary_term("  ") is None


def test_detection_needs_a_known_first_column():
    assert is_term_list("term,meaning\n学生,studente")
    assert is_term_list("# my list\n\nTermine;Significato\n学生;studente")
    assert is_term_list("term\treading\n日\tにち")
    assert not is_term_list("---\nmode: terms\n---\n今日は 土曜日です。")
    assert not is_term_list("学生,studente")


def test_rows_meanings_and_line_numbers():
    parsed = parse_term_list("term,reading,meaning\n学生,,studente\n\n日,にち,giorno\n", SPEC)
    assert not parsed.errors and not parsed.warnings
    assert [(r.line, r.candidate.lemma, r.candidate.reading, r.meaning) for r in parsed.rows] == [
        (2, "学生", "がくせい", "studente"), (4, "日", "にち", "giorno"),
    ]


def test_italian_headers_quotes_and_semicolons():
    parsed = parse_term_list('Termine;Lettura;Significato\n先生;;"insegnante; maestro"\n', SPEC)
    (row,) = parsed.rows
    assert (row.candidate.lemma, row.meaning) == ("先生", "insegnante; maestro")


def test_unknown_columns_are_ignored_with_a_warning():
    parsed = parse_term_list("term,meaning,level,tags\n学生,studente,1,school\n", SPEC)
    assert len(parsed.rows) == 1
    assert any("'level' ignored" in w and "kanji" in w for w in parsed.warnings)
    assert any("'tags' ignored" in w for w in parsed.warnings)


def test_duplicates_and_empty_terms_are_skipped():
    parsed = parse_term_list("term,meaning\n食べる,mangiare\n食べます,mangiare\n,vuoto\n", SPEC)
    assert [r.candidate.lemma for r in parsed.rows] == ["食べる"]
    assert any("line 2" in w for w in parsed.warnings) and any("Line 4: no term" in w for w in parsed.warnings)


def test_a_header_without_term_or_without_rows_is_an_error():
    assert parse_term_list("meaning,term\n", SPEC).errors == ["The list has no terms"]
    assert parse_term_list("reading,meaning\nがくせい,studente\n", SPEC).errors == ["The header has no 'term' column"]
