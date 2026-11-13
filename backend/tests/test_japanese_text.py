"""
Unit tests for deterministic furigana (`app.tracks.japanese_text`). Uses the
real MeCab dictionary (`unidic-lite`), no network. Readings asserted here are
the ones a beginner expects — if a dictionary upgrade changes them, these
tests are the place to notice.
"""
import pytest

from app.tracks import get_track_spec
from app.tracks.japanese_text import annotate, annotate_payload, has_kanji, romaji, spoken_reading, to_hiragana


def _render(segments):
    """Compact form for assertions: 学校(がっこう)の."""
    return "".join(f"{s['text']}({s['reading']})" if s.get("reading") else s["text"] for s in segments)


# ---------------------------------------------------------------------------
# annotate
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "学校の　せんせい",
    "あの方は だいがくの せんせいです",
    "Come si legge 学校?",
    "わたし ___ がくせいです。",
    "24歳です。",
    "  spazi  finali  ",
    "",
])
def test_segments_concatenate_to_the_input(text):
    assert "".join(s["text"] for s in annotate(text)) == text


def test_readings_only_on_kanji():
    segments = annotate("ジュリアは家の前にいます。")
    assert all(has_kanji(s["text"]) for s in segments if s.get("reading"))
    assert _render(segments) == "ジュリアは家(いえ)の前(まえ)にいます。"


def test_readings_are_hiragana():
    assert _render(annotate("学校")) == "学校(がっこう)"


def test_okurigana_stays_outside_the_ruby():
    assert _render(annotate("お茶を飲みます")) == "お茶(ちゃ)を飲(の)みます"


@pytest.mark.parametrize("text, expected", [
    ("私は学生です", "私(わたし)は学生(がくせい)です"),
    ("日本に行く", "日本(にほん)に行(い)く"),
    ("わたしは日本人です", "わたしは日本(にほん)人(じん)です"),
    ("あの方は先生です", "あの方(かた)は先生(せんせい)です"),
    ("キムさんは韓国人です", "キムさんは韓国(かんこく)人(じん)です"),
    ("中国人", "中国(ちゅうごく)人(じん)"),
    ("アメリカ人", "アメリカ人(じん)"),
    ("外国人", "外国(がいこく)人(じん)"),
    ("三人", "三(さん)人(にん)"),   # counter: stays にん
])
def test_beginner_reading_overrides(text, expected):
    assert _render(annotate(text)) == expected


@pytest.mark.parametrize("text", ["il suffisso 「人」（にん）", "il suffisso 人(にん)", "五（ご） persone"])
def test_no_furigana_when_the_text_already_gives_the_reading(text):
    segments = annotate(text)
    assert not any(s.get("reading") for s in segments if s["text"] in {"人", "五"})
    assert "".join(s["text"] for s in segments) == text


@pytest.mark.parametrize("text, kanji", [("qui 日 si legge にち", "日"), ("大 (grande) + 学 (studio)", "学"), ("太 e 犬 somigliano a 大", "太")])
def test_no_furigana_on_a_kanji_quoted_alone(text, kanji):
    assert not any(s.get("reading") for s in annotate(text) if kanji in s["text"])


def test_single_kanji_inside_japanese_keeps_furigana():
    assert _render(annotate("お茶を飲みます")) == "お茶(ちゃ)を飲(の)みます"
    assert _render(annotate("家族は五人です")).startswith("家族(かぞく)は五(ご)")


def test_kana_only_text_has_no_readings():
    assert annotate("せんせいです") == [{"text": "せんせいです"}]


def test_to_hiragana():
    assert to_hiragana("ガッコウ") == "がっこう"


# ---------------------------------------------------------------------------
# annotate_payload — furigana must never give the answer away
# ---------------------------------------------------------------------------
def test_reading_question_hides_the_asked_word():
    ann = annotate_payload("multiple_choice", {
        "question": "Come si legge 学校?",
        "options": ["がっこう", "がこう", "かっこう", "がっこ"],
    })
    assert "reading" not in str(ann.get("question", []))


def test_writing_question_hides_furigana_on_every_option():
    ann = annotate_payload("multiple_choice", {
        "question": "Scegli la grafia corretta: あの方は だいがくの せんせいです",
        "options": ["大学", "大字", "太学", "大校"],
    })
    assert "options" not in ann
    # the rest of the sentence keeps its furigana
    assert _render(ann["question"]).startswith("Scegli la grafia corretta: あの方(かた)")


def test_meaning_question_keeps_option_furigana():
    ann = annotate_payload("multiple_choice", {"question": "Cosa significa 'scuola'?", "options": ["学校", "会社", "病院", "駅"]})
    assert [_render(o) for o in ann["options"]] == ["学校(がっこう)", "会社(かいしゃ)", "病院(びょういん)", "駅(えき)"]


def test_fill_blank_context_keeps_furigana():
    ann = annotate_payload("fill_blank", {"sentence_with_blank": "学校 ___ 行きます。", "options": ["に", "で", "を"]})
    assert _render(ann["sentence_with_blank"]) == "学校(がっこう) ___ 行(い)きます。"
    assert "options" not in ann  # kana-only options need no furigana


@pytest.mark.parametrize("blank", ["___", "____", "＿＿"])
def test_fill_blank_options_are_read_in_context(blank):
    ann = annotate_payload("fill_blank", {"sentence_with_blank": f"わたしの家族は五{blank}です。", "options": ["人", "つ", "本"]})
    assert _render(ann["options"][0]) == "人(にん)"


def test_bracketed_reading_covers_the_whole_compound():
    segments = annotate("五人（ごにん）")
    assert not any(s.get("reading") for s in segments)


def test_explanation_is_always_annotated():
    ann = annotate_payload("multiple_choice", {
        "question": "Come si legge 学校?",
        "options": ["がっこう", "がこう", "かっこう", "がっこ"],
        "explanation": "学校 si legge がっこう.",
    })
    assert _render(ann["explanation"]) == "学校(がっこう) si legge がっこう."


def test_answer_fields_are_not_annotated():
    ann = annotate_payload("translate_rev", {"prompt": "私は学生です。", "expected": "Sono uno studente.", "alternatives": ["Io sono studente."]})
    assert set(ann) == {"prompt"}


def test_payload_without_kanji_has_no_annotations():
    assert annotate_payload("multiple_choice", {"question": "Quale particella?", "options": ["も", "の"]}) == {}


def test_japanese_track_spec_uses_the_annotator():
    assert get_track_spec("ja").annotations_for("translate_rev", {"prompt": "学校"}) == {"prompt": [{"text": "学校", "reading": "がっこう"}]}


# ---------------------------------------------------------------------------
# Focus types (explicit focus word inside the sentence)
# ---------------------------------------------------------------------------
def _focus_text(segments):
    return "".join(s["text"] for s in segments if s.get("focus"))


def test_kanji_reading_hides_the_focus_reading_only():
    ann = annotate_payload("kanji_reading", {"sentence": "山田さんは 先生です。", "focus": "先生", "options": ["せんせい", "せんせ", "せいせん", "さきせい"]})
    assert _focus_text(ann["sentence"]) == "先生"
    assert not any(s.get("reading") for s in ann["sentence"] if s.get("focus"))
    assert _render(ann["sentence"]).startswith("山田(やまだ)")
    assert "options" not in ann


def test_kanji_writing_marks_a_kana_focus_and_never_annotates_options():
    ann = annotate_payload("kanji_writing", {"sentence": "がっこうに 行きます。", "focus": "がっこう", "options": ["学校", "学生", "校学", "大学"]})
    assert _focus_text(ann["sentence"]) == "がっこう"
    assert "options" not in ann


def test_romaji_input_keeps_furigana_on_the_focus():
    ann = annotate_payload("romaji_input", {"sentence": "わたしは 山田です。", "focus": "山田"})
    focus = [s for s in ann["sentence"] if s.get("focus")]
    assert focus == [{"text": "山田", "reading": "やまだ", "focus": True}]


def test_focus_segments_still_concatenate_to_the_sentence():
    sentence = "毎日 日本語を 勉強します。"
    ann = annotate_payload("kanji_reading", {"sentence": sentence, "focus": "毎日"})
    assert "".join(s["text"] for s in ann["sentence"]) == sentence


# ---------------------------------------------------------------------------
# Romaji
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text, display, also_accepted", [
    ("山田", "yamada", []),
    ("学校", "gakkō", ["gakkou", "gakkoo", "gakko"]),
    ("とうきょう", "tōkyō", ["toukyou", "tokyo"]),
    ("せんせい", "sensei", []),
    ("おかあさん", "okāsan", ["okaasan"]),
    ("きって", "kitte", []),
    ("まっちゃ", "matcha", []),
    ("てんいん", "ten'in", []),
    ("こんにちは", "konnichiwa", []),
    ("コーヒー", "kōhī", ["koohii", "kohi"]),
    ("日本", "nihon", []),
    ("すし", "sushi", []),
])
def test_romaji(text, display, also_accepted):
    shown, accepted = romaji(text)
    assert shown == display
    assert display in accepted and all(a in accepted for a in also_accepted)


def test_particles_are_read_as_pronounced():
    assert spoken_reading("わたしは がっこうへ ほんを") == "わたしわ がっこうえ ほんお"
