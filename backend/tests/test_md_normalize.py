"""
The Studio import's LLM fallback, pure part (`app/md_normalize.py`): which
segments go to the model, how its exercises are rendered back as `.md` and
how the file is rebuilt. No model call, no DB.
"""
from app.md_import import parse_exercises_md
from app.md_normalize import (
    NormalizedExercise, OptionOut, importable_types, rebuild, render_block, segments_prompt,
    split_for_normalization,
)
from app.tracks import get_track_spec

SPEC = get_track_spec("ja")

VALID_BLOCK = """## kanji_reading
sentence: わたしは 学生です。
translation: Sono uno studente.
focus: 学生
- [x] がくせい
- [ ] がっせい
- [ ] がくせ
- [ ] かくせい"""

FILE = f"""---
difficulty: 1
---

# Lesson 1

1. 山田さんは 先生です。 Il signor Yamada è un insegnante. Lettura di 先生: せんせい

{VALID_BLOCK}

## kanji_reading
frase: 日本人です。
traduzione: È giapponese.
focus: 日本人
- [ ] にほんじん
- [ ] にっぽんじん
- [ ] にほんにん
- [ ] にほじん
"""


def _reading_item(segment_id: str, **changes) -> NormalizedExercise:
    data = dict(
        segment_id=segment_id, exercise_type="kanji_reading", sentence="山田さんは 先生です。",
        translation="Il signor Yamada è un insegnante.", focus="先生",
        options=[OptionOut(text=t, correct=t == "せんせい") for t in ("せんせい", "せんせ", "せいせい", "ぜんせい")],
        source_excerpt="1. 山田さんは 先生です。 Il signor Yamada è un insegnante.",
    )
    data.update(changes)
    return NormalizedExercise(**data)


def test_segments_marked_for_the_model():
    split = split_for_normalization(FILE, SPEC)
    assert not split.errors
    assert split.head == ["---", "difficulty: 1", "---"]
    kinds = [(s.kind, s.needs_model) for s in split.segments]
    # text with an exercise, the valid block (kept), the block with no '- [x]'
    assert kinds == [("text", True), ("block", False), ("block", True)]
    invalid = split.segments[2]
    assert any("exactly one option" in e for e in invalid.errors)


def test_notes_only_text_is_still_sent_but_headings_and_comments_alone_are_not():
    split = split_for_normalization("---\ndifficulty: 1\n---\n# Title\n<!-- a comment -->\n\n" + VALID_BLOCK + "\n", SPEC)
    assert [s.needs_model for s in split.segments] == [False, False]


def test_front_matter_errors_are_not_for_the_model():
    split = split_for_normalization("---\ntrack: no\n---\n" + VALID_BLOCK, SPEC)
    assert split.errors and not split.segments


def test_prompt_carries_ids_kinds_and_parser_errors():
    split = split_for_normalization(FILE, SPEC)
    prompt = segments_prompt([s for s in split.segments if s.needs_model])
    assert '<segment id="s1" kind="free_text" line="4">' in prompt
    assert 'kind="invalid_block"' in prompt
    assert "parser error: exactly one option" in prompt
    assert "学生" not in prompt   # the valid block is never sent


def test_rendered_block_parses_cleanly():
    text = "---\ndifficulty: 1\n---\n\n" + "\n".join(render_block(_reading_item("s1"))) + "\n"
    result = parse_exercises_md(text, SPEC)
    assert not result.errors
    (item,) = result.items
    assert item.errors == []
    assert item.payload["focus"] == "先生"
    assert item.payload["options"][item.payload["correct_index"]] == "せんせい"


def test_missing_values_stay_missing_and_the_preview_reports_them():
    block = render_block(_reading_item("s1", translation=None, options=[]))
    assert not any(line.startswith("translation:") for line in block)
    (item,) = parse_exercises_md("---\ndifficulty: 1\n---\n" + "\n".join(block), SPEC).items
    assert "'translation' missing" in item.errors


def test_source_excerpt_cannot_break_the_comment():
    block = render_block(_reading_item("s1", source_excerpt="a --> b\nc"))
    assert block[1] == "<!-- source: a —> b c -->"


def test_keys_of_other_types_are_dropped():
    block = render_block(_reading_item("s1", question="?", answer="sensei", alternatives=["x"]))
    assert not any(line.split(":")[0] in {"question", "answer", "alternative"} for line in block)


def test_rebuild_replaces_only_what_the_model_returned():
    split = split_for_normalization(FILE, SPEC)
    fixed_block = _reading_item(
        "s3", sentence="日本人です。", translation="È giapponese.", focus="日本人",
        options=[OptionOut(text=t, correct=False) for t in ("にほんじん", "にっぽんじん", "にほんにん", "にほじん")],
    )
    text = rebuild(split, {"s1": [_reading_item("s1")], "s3": [fixed_block]})

    assert text.startswith("---\ndifficulty: 1\n---\n\n# Lesson 1\n")   # head and leading heading kept
    # the pasted text is kept, commented out, above its blocks
    assert "<!-- original text, rewritten as the blocks below:\n1. 山田さんは 先生です。" in text
    assert VALID_BLOCK in text                           # valid block verbatim
    result = parse_exercises_md(text, SPEC)
    assert not result.errors
    assert [bool(i.errors) for i in result.items] == [False, False, True]   # no answer in the source: still an error


def test_rebuild_keeps_segments_without_exercises():
    split = split_for_normalization(FILE, SPEC)
    assert rebuild(split, {}) == FILE


def test_importable_types_cover_the_track():
    assert set(importable_types(SPEC)) == {
        "multiple_choice", "fill_blank", "translate_rev", "kanji_reading", "kanji_writing", "romaji_input",
    }
