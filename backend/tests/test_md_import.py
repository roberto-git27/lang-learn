"""
The Studio's `.md` parser (`app/md_import.py`): the public sample files, the
maintainer's local course files (git-ignored `data/`, skipped when absent)
and every error the parser must report with its line. No DB needed.
"""
import re
from pathlib import Path

import pytest

from app.md_import import (
    exercises_to_markdown, normalize_topic, parse_exercises_md, parse_generation_request, parse_terms_text,
)
from app.tracks import get_track_spec

REPO = Path(__file__).resolve().parents[2]
SPEC = get_track_spec("ja")
SAMPLE = parse_exercises_md((REPO / "sample" / "ja_starter.md").read_text(encoding="utf-8"), SPEC)
COURSE_FILES = sorted((REPO / "data").glob("**/*.md"))
SAMPLE_FILES = sorted(p for p in (REPO / "sample").glob("*.md") if p.name != "README.md")


def parse(text: str):
    return parse_exercises_md(text, SPEC)


def only_item(text: str):
    result = parse(text)
    assert not result.errors
    (item,) = result.items
    return item


# ---------------------------------------------------------------------------
# sample/ja_starter.md — the starter set anyone can import
# ---------------------------------------------------------------------------
def test_sample_is_clean():
    assert not SAMPLE.errors
    assert [(i.line, i.errors, i.warnings) for i in SAMPLE.items if i.errors or i.warnings] == []


def test_sample_covers_every_japanese_type_mostly_at_level_one():
    assert {i.exercise_type for i in SAMPLE.items} == set(SPEC.payload_models)
    levels = [i.difficulty for i in SAMPLE.items]
    assert levels.count(1) > len(levels) / 2


def test_sample_is_mostly_option_based():
    typed = [i for i in SAMPLE.items if i.exercise_type in {"translate_rev", "romaji_input"}]
    translations = [i for i in SAMPLE.items if i.exercise_type == "translate_rev"]
    assert len(typed) <= len(SAMPLE.items) / 3
    assert len(translations) <= 2


def test_sample_phrases_are_unique():
    targets = [i.phrase_target for i in SAMPLE.items]
    assert len(targets) == len(set(targets))


def test_sample_furigana_never_reveal_the_answer():
    for item in SAMPLE.items:
        if item.exercise_type == "kanji_reading":
            assert not any(s.get("reading") for s in item.annotations["sentence"] if s.get("focus"))
        if item.exercise_type in {"kanji_reading", "kanji_writing"}:
            assert "options" not in item.annotations


def file_errors(text: str) -> list:
    """Every problem of a Studio file, parsed according to its `mode:`."""
    if re.search(r"^mode:\s*generate\b", text, re.MULTILINE):
        return parse_generation_request(text, SPEC).errors
    if re.search(r"^mode:\s*terms\b", text, re.MULTILINE):
        return parse_terms_text(text, SPEC)[1]
    result = parse(text)
    return result.errors + [(i.line, i.errors) for i in result.items if i.errors]


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.name)
def test_sample_files_parse_without_errors(path):
    assert file_errors(path.read_text(encoding="utf-8")) == []


@pytest.mark.skipif(not COURSE_FILES, reason="no local course files in data/")
@pytest.mark.parametrize("path", COURSE_FILES, ids=lambda p: p.name)
def test_course_files_parse_without_errors(path):
    """The maintainer's course .md files (git-ignored) double as import tests."""
    assert file_errors(path.read_text(encoding="utf-8")) == []


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------
KANJI_READING = """\
## kanji_reading
sentence: わたしは 学生です。
translation: Sono uno studente.
focus: 学生
- [ ] がっせい
- [x] がくせい
- [ ] がくせ
- [ ] かくせい
"""


def test_front_matter_sets_defaults_and_blocks_override_them():
    result = parse("---\ntrack: ja\ndifficulty: 2\ntopics: [school, Particella は]\n---\n"
                   + KANJI_READING + "\n" + KANJI_READING.replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\ntopics: family\n"))
    first, second = result.items
    assert (first.difficulty, first.topics) == (2, ["school", "particella_は"])
    assert (second.difficulty, second.topics) == (1, ["family"])


def test_front_matter_accepts_trailing_comments():
    item = only_item("---\ndifficulty: 2   # a note\ntopics: school  # another\n---\n" + KANJI_READING)
    assert (item.difficulty, item.topics) == (2, ["school"])


def test_format_examples_in_the_studio_page_parse():
    """The examples shown in the Studio's format guide must be valid files."""
    page = (REPO / "frontend" / "src" / "pages" / "StudioPage.jsx").read_text(encoding="utf-8")
    example = lambda name: page.split(f"const {name} = `", 1)[1].split("`;", 1)[0]
    assert only_item(example("IMPORT_EXAMPLE")).errors == []
    assert parse_generation_request(example("GENERATE_EXAMPLE"), SPEC).errors == []
    assert parse_terms_text(example("TERMS_EXAMPLE"), SPEC)[1] == []


def test_options_and_correct_index():
    item = only_item("---\ndifficulty: 1\n---\n" + KANJI_READING)
    assert item.errors == []
    assert item.payload["options"][item.payload["correct_index"]] == "がくせい"
    assert item.phrase_target == "わたしは 学生です。"
    assert item.phrase_base == "Sono uno studente."
    assert item.line == 4   # the `## <type>` heading


def test_italian_aliases():
    item = only_item(
        "## romaji_input\ndifficoltà: 1\nfrase: わたしは 山田です。\ntraduzione: Sono Yamada.\n"
        "focus: 山田\nrisposta: Yamada\nspiegazione: Un cognome.\n"
    )
    assert item.errors == []
    assert item.payload["expected"] == "yamada"
    assert item.payload["explanation"] == "Un cognome."


def test_romaji_answer_must_match_the_computed_reading():
    item = only_item("## romaji_input\ndifficulty: 1\nsentence: わたしは 山田です。\ntranslation: Sono Yamada.\nfocus: 山田\nanswer: yamda\n")
    assert "differs from the romaji computed" in item.errors[0]


def test_fill_blank_phrase_is_the_complete_sentence():
    item = only_item(
        "## fill_blank\ndifficulty: 1\nsentence: わたし___ がくせいです。\ntranslation: Sono uno studente.\n"
        "- [x] は\n- [ ] を\n- [ ] に\n"
    )
    assert item.payload["correct"] == "は"
    assert item.phrase_target == "わたしは がくせいです。"


def test_fill_blank_accepts_the_textbook_blank():
    item = only_item(
        "## fill_blank\ndifficulty: 1\nsentence: わたしは　インド　【　　】　来ました。\ntranslation: Vengo dall'India.\n"
        "- [x] から\n- [ ] を\n- [ ] で\n"
    )
    assert item.payload["sentence_with_blank"] == "わたしは　インド　___　来ました。"
    assert item.phrase_target == "わたしは　インド　から　来ました。"


def test_translate_rev_uses_the_translation_and_repeatable_alternatives():
    item = only_item(
        "## translate_rev\ndifficulty: 1\nsentence: わたしは イタリア人です。\ntranslation: Sono italiano.\n"
        "alternative: Sono italiana.\nalternative: Io sono italiano.\n"
    )
    assert item.payload == {
        "prompt": "わたしは イタリア人です。", "expected": "Sono italiano.",
        "alternatives": ["Sono italiana.", "Io sono italiano."],
    }


def test_text_outside_blocks_and_other_headings_are_ignored():
    result = parse("# Lesson 1\nSome notes.\n\n---\n" + KANJI_READING.replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\n")
                   + "\n### Notes\nA：はじめまして。\n<!-- a comment -->\n")
    (item,) = result.items
    assert item.errors == []


def test_level_problems_are_warnings_not_errors():
    item = only_item(
        "## kanji_reading\ndifficulty: 1\nsentence: 医者です。\ntranslation: È un medico.\nfocus: 医者\n"
        "- [x] いしゃ\n- [ ] いしや\n- [ ] いじゃ\n- [ ] いさ\n"
    )
    assert item.errors == []
    assert item.warnings == ["kanji above level 1: 医者"]


def test_normalize_topic():
    assert normalize_topic("  Particella は ") == "particella_は"
    assert normalize_topic("self-introduction") == "self_introduction"


# ---------------------------------------------------------------------------
# Errors: always reported, never raised
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("block, message", [
    ("## kanji_readin\n", "unknown exercise type 'kanji_readin'"),
    (KANJI_READING, "difficulty missing"),
    (KANJI_READING.replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 11\n"), "difficulty must be from 1 to 10"),
    (KANJI_READING.replace("- [ ] がっせい", "- [x] がっせい").replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\n"),
     "exactly one option must be marked '- [x]', found 2"),
    (KANJI_READING.replace("translation: Sono uno studente.\n", "").replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\n"),
     "'translation' missing"),
    (KANJI_READING.replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\nnote: hi\n"), "line 3: not a known 'key: value' line"),
    (KANJI_READING.replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\nquestion: ?\n"), "'question' is not used by kanji_reading"),
    (KANJI_READING.replace("focus: 学生", "focus: 先生").replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\n"),
     "`focus` must appear in `sentence`"),
    (KANJI_READING.replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\nsentence: again\n"), "'sentence' given twice"),
    (KANJI_READING.replace("- [ ] がくせ\n", "- [ ]\n").replace("## kanji_reading\n", "## kanji_reading\ndifficulty: 1\n"),
     "line 8: option without text"),
])
def test_block_errors(block, message):
    (item,) = parse(block).items
    assert any(message in error for error in item.errors), item.errors
    assert item.payload is None


@pytest.mark.parametrize("text, message", [
    ("---\ntrack: no\n---\n" + KANJI_READING, "this file is for track 'no'"),
    ("---\ndifficulty: 1\n" + KANJI_READING, "front matter is not closed"),
    ("---\nlevel: 1\n---\n" + KANJI_READING, "unknown front matter line"),
    ("Just some text.\n", "no exercises found"),
    ("---\nmode: generate\n---\n" + KANJI_READING, "this file is for the Studio's 'generate' mode"),
])
def test_file_errors(text, message):
    result = parse(text)
    assert result.items == []
    assert any(message in error for error in result.errors), result.errors


# ---------------------------------------------------------------------------
# Exercises → .md: a generated draft can be edited by hand and imported
# ---------------------------------------------------------------------------
def test_markdown_keeps_full_width_spaces_and_flattens_line_breaks():
    item = only_item("## fill_blank\ndifficulty: 1\nsentence: わたしは　インド　【　　】　来ました。\ntranslation: Vengo dall'India.\n"
                     "- [x] から\n- [ ] を\n")
    item.payload["explanation"] = "から = da.\nPunto di partenza."
    text = exercises_to_markdown([item], "ja")
    assert "sentence: わたしは　インド　___　来ました。" in text
    assert "explanation: から = da. Punto di partenza." in text
    assert only_item(text).phrase_target == item.phrase_target


def test_markdown_round_trip_keeps_every_exercise():
    text = exercises_to_markdown(SAMPLE.items, "ja")
    again = parse(text)
    assert not again.errors
    assert [(i.exercise_type, i.difficulty, i.topics, i.phrase_target, i.phrase_base, i.payload) for i in again.items] == [
        (i.exercise_type, i.difficulty, i.topics, i.phrase_target, i.phrase_base, i.payload) for i in SAMPLE.items
    ]


# ---------------------------------------------------------------------------
# Generation requests
# ---------------------------------------------------------------------------
REQUEST = """\
---
mode: generate
difficulty: 1
per_term: 2
types: kanji_reading, fill_blank
examples: 0
---

# Richiesta
Frasi brevissime.

## terms
- 一 uno
- 火: fuoco

# Note
Altro testo per il modello.
"""


def test_generation_request():
    request = parse_generation_request(REQUEST, SPEC)
    assert request.errors == []
    assert (request.difficulty, request.per_term, request.types, request.examples) == (1, 2, ["kanji_reading", "fill_blank"], 0)
    assert [(t.text, t.note) for t in request.terms] == [("一", "uno"), ("火", "fuoco")]
    assert request.instructions == "# Richiesta\nFrasi brevissime.\n\n# Note\nAltro testo per il modello."


@pytest.mark.parametrize("text, message", [
    (REQUEST.replace("difficulty: 1\n", ""), "difficulty missing"),
    (REQUEST.replace("per_term: 2", "per_term: 9"), "per_term must be a number from 1 to 6"),
    (REQUEST.replace("fill_blank", "fill_blanks"), "unknown exercise types ['fill_blanks']"),
    (REQUEST.replace("- 火: fuoco", "- 一 again"), "term '一' listed twice"),
    (REQUEST.replace("- 火: fuoco", "火 fuoco"), "a term is written '- term [note]'"),
    (REQUEST.replace("mode: generate", "mode: import"), "this file is for the Studio's 'import' mode"),
    ("---\nmode: generate\ndifficulty: 1\n---\n", "empty request"),
    (REQUEST.replace("per_term: 2", "per_term: 6").replace("- 火: fuoco", "".join(f"- {k}\n" for k in "二三四五六火")),
     "at most 30 per request"),
])
def test_generation_request_errors(text, message):
    errors = parse_generation_request(text, SPEC).errors
    assert any(message in error for error in errors), errors
