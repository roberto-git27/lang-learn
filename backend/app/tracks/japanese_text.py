"""
Deterministic furigana for Japanese text — no LLM involved (D-04).

`annotate(text)` splits a string into segments whose concatenation is exactly
the input; segments containing kanji carry their reading in hiragana:

    annotate("お茶を飲みます")
    → [{"text": "お"}, {"text": "茶", "reading": "ちゃ"}, {"text": "を"},
       {"text": "飲", "reading": "の"}, {"text": "みます"}]

Readings come from MeCab (via `fugashi`) with the `unidic-lite` dictionary,
so they depend on context. UniDic picks formal or rare readings for a few
very common words (私 → わたくし, 日本 → にっぽん, あの方 → ほう); the override
rules below fix those for a learner, and a single kanji quoted on its own
inside non-Japanese text (a character being discussed) gets no furigana. Readings are shown per token, so words
MeCab splits in the middle keep their inner kana under the ruby
(取り扱い → 取り扱(とりあつか)い) — correct, just less granular. Anything else that is wrong shows up in
the review queue, where furigana are always visible.

`annotate_payload(exercise_type, payload)` applies this to an exercise's
display fields and never puts furigana on the word being asked about (see
`_revealing_readings`).
"""
from __future__ import annotations

import re
from functools import lru_cache

from fugashi import Tagger

from ..exercise_payloads import BLANK
from .base import TermCandidate

Segment = dict  # {"text": str, "reading": str (only when the text contains kanji)}

KANJI = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3005]")  # CJK ideographs + 々
_KATAKANA_TO_HIRAGANA = {code: code - 0x60 for code in range(ord("ァ"), ord("ヶ") + 1)}

# Word overrides: UniDic's default reading → the one a learner expects.
_READING_OVERRIDES = {
    "私": "わたし",
    "日本": "にほん",
}
# Context overrides: (previous token, token) → reading.
_PAIR_OVERRIDES = {
    ("外国", "人"): "じん",
    ("この", "方"): "かた",   # 方 is "person" (polite) after a demonstrative, not ほう ("direction")
    ("その", "方"): "かた",
    ("あの", "方"): "かた",
    ("どの", "方"): "かた",
}


@lru_cache(maxsize=1)
def _tagger() -> Tagger:
    return Tagger()


def to_hiragana(text: str) -> str:
    return text.translate(_KATAKANA_TO_HIRAGANA)


def has_kanji(text: str) -> bool:
    return bool(KANJI.search(text))


def _split_okurigana(surface: str, reading: str) -> list[Segment]:
    """
    Puts the reading only over the kanji part of a token: kana shared at the
    start/end of surface and reading stay outside the ruby
    (飲み/のみ → 飲(の) + み, お茶 → お + 茶(ちゃ)).
    """
    start = 0
    while start < len(surface) and start < len(reading) and not has_kanji(surface[start]) and surface[start] == reading[start]:
        start += 1
    end = 0
    while (
        end < len(surface) - start and end < len(reading) - start
        and not has_kanji(surface[-1 - end]) and surface[-1 - end] == reading[-1 - end]
    ):
        end += 1

    core = surface[start:len(surface) - end]
    core_reading = reading[start:len(reading) - end]
    segments: list[Segment] = []
    if start:
        segments.append({"text": surface[:start]})
    segments.append({"text": core, "reading": core_reading} if core_reading else {"text": core})
    if end:
        segments.append({"text": surface[len(surface) - end:]})
    return segments


# The text already spells the reading right after the word: 「人」（にん）, 人(にん).
_EXPLICIT_READING = re.compile(r"^[」』]?\s*[（(][\u3040-\u309f\u30a0-\u30ffー・、\s]+[）)]")


def _drop_explicit_readings(segments: list[Segment]) -> list[Segment]:
    """
    No furigana on a word whose reading the text itself gives in brackets
    (typical of explanations): out of context MeCab may pick another
    reading, and the ruby would contradict the text. The bracketed reading
    covers the whole kanji compound before it (五人（ごにん）).
    """
    out = list(segments)
    for i, seg in enumerate(segments):
        following = "".join(s["text"] for s in segments[i + 1:])
        if seg.get("reading") and _EXPLICIT_READING.match(following):
            j = i
            while j >= 0 and out[j].get("reading"):
                out[j] = {"text": out[j]["text"]}
                j -= 1
    return out


_JAPANESE_CHAR = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\u3005ー]")


def _drop_isolated_characters(segments: list[Segment]) -> list[Segment]:
    """
    No furigana on a single kanji standing alone among non-Japanese text
    ("日 si legge にち", "大 + 学"): it is discussed as a character, whose
    reading depends on the word it appears in, so any ruby would mislead.
    A kanji that is the whole text (e.g. an option 駅) is a word: kept.
    """
    out = list(segments)
    for i, seg in enumerate(segments):
        if not seg.get("reading") or len(seg["text"]) != 1:
            continue
        before = segments[i - 1]["text"][-1:] if i > 0 else ""
        after = segments[i + 1]["text"][:1] if i + 1 < len(segments) else ""
        if (before or after) and not _JAPANESE_CHAR.match(before) and not _JAPANESE_CHAR.match(after):
            out[i] = {"text": seg["text"]}
    return out


def _merge_plain(segments: list[Segment]) -> list[Segment]:
    """Joins consecutive segments without a reading (and same focus flag), to keep the output compact."""
    merged: list[Segment] = []
    for seg in segments:
        if (
            "reading" not in seg and merged and "reading" not in merged[-1]
            and seg.get("focus") == merged[-1].get("focus")
        ):
            merged[-1] = {**merged[-1], "text": merged[-1]["text"] + seg["text"]}
        else:
            merged.append(seg)
    return merged


def _kanji_reading(word, previous) -> str:
    """Hiragana reading of a token containing kanji, with the learner overrides applied."""
    surface = word.surface
    if (
        surface == "人" and word.feature.pos1 == "接尾辞"
        and previous is not None and previous.feature.pos3 == "地名"
    ):
        return "じん"   # nationality/origin: 中国人, アメリカ人 (UniDic says にん)
    return (
        _PAIR_OVERRIDES.get((previous.surface if previous is not None else "", surface))
        or _READING_OVERRIDES.get(surface)
        or to_hiragana(word.feature.kana)
    )


def annotate(text: str) -> list[Segment]:
    """Segments of `text` (concatenating to exactly `text`), with hiragana readings over kanji."""
    segments: list[Segment] = []
    previous = None
    for word in _tagger()(text):
        if word.white_space:
            segments.append({"text": word.white_space})
        surface = word.surface
        kana = word.feature.kana
        if not has_kanji(surface) or not kana or kana == "*":
            segments.append({"text": surface})
        else:
            segments.extend(_split_okurigana(surface, _kanji_reading(word, previous)))
        previous = word

    # MeCab drops trailing whitespace; keep the invariant "segments == text".
    rebuilt = "".join(seg["text"] for seg in segments)
    if rebuilt != text and text.startswith(rebuilt):
        segments.append({"text": text[len(rebuilt):]})
    return _merge_plain(_drop_isolated_characters(_drop_explicit_readings(segments)))


# ---------------------------------------------------------------------------
# Romaji (Hepburn), from the same readings used for furigana
# ---------------------------------------------------------------------------
# Particles are written with one kana but pronounced differently.
_PARTICLE_SOUND = {"は": "わ", "へ": "え", "を": "お"}
# Greetings that end with the particle は inside a single token.
_WORD_SOUND = {"こんにちは": "こんにちわ", "こんばんは": "こんばんわ"}

_DIGRAPHS = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo", "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho", "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo", "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo", "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo", "ぢゃ": "ja", "ぢゅ": "ju", "ぢょ": "jo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo", "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
    # katakana-only combinations (loanwords), written here in hiragana
    "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo", "てぃ": "ti", "でぃ": "di",
    "うぃ": "wi", "うぇ": "we", "うぉ": "wo", "しぇ": "she", "じぇ": "je", "ちぇ": "che",
    "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo", "でゅ": "dyu", "とぅ": "tu",
}
_MONOGRAPHS = dict(zip(
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
    "がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽゔぁぃぅぇぉゎ",
    "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no ha hi fu he ho "
    "ma mi mu me mo ya yu yo ra ri ru re ro wa o n ga gi gu ge go za ji zu ze zo da ji zu de do "
    "ba bi bu be bo pa pi pu pe po vu a i u e o wa".split(),
))
_MACRON = {"a": "ā", "i": "ī", "u": "ū", "e": "ē", "o": "ō"}
# Second vowel that lengthens the first one in Hepburn (えい and いい stay as written).
_LENGTHENERS = {"a": "a", "u": "u", "e": "e", "o": "ou"}


def spoken_reading(text: str) -> str:
    """
    Hiragana of how `text` is pronounced: kanji read as for furigana (same
    overrides), particles は/へ/を as わ/え/お, other characters unchanged.
    """
    parts: list[str] = []
    previous = None
    for word in _tagger()(text):
        parts.append(word.white_space)
        surface = word.surface
        kana = word.feature.kana
        if surface in _WORD_SOUND:
            reading = _WORD_SOUND[surface]
        elif word.feature.pos1 == "助詞" and surface in _PARTICLE_SOUND:
            reading = _PARTICLE_SOUND[surface]
        elif has_kanji(surface) and kana and kana != "*":
            reading = _kanji_reading(word, previous)
        else:
            reading = to_hiragana(surface)
        parts.append(reading)
        previous = word
    return "".join(parts)


def _syllables(kana: str) -> list[tuple[str, str]]:
    """(kana, romaji) units; 'っ' and 'ー' are kept as markers for the next step."""
    units: list[tuple[str, str]] = []
    i = 0
    while i < len(kana):
        pair = kana[i:i + 2]
        if pair in _DIGRAPHS:
            units.append((pair, _DIGRAPHS[pair]))
            i += 2
            continue
        char = kana[i]
        if char in ("っ", "ー"):
            units.append((char, char))
        elif char in _MONOGRAPHS:
            units.append((char, _MONOGRAPHS[char]))
        else:
            units.append((char, char))  # not kana (punctuation, Latin): kept as is
        i += 1
    return units


def _romanize(kana: str, long_vowels: str) -> str:
    """
    `long_vowels`: 'macron' (gakkō), 'written' (gakkou — every kana spelled
    out, ー as a repeated vowel), 'short' (gakko — length dropped).
    """
    units = _syllables(kana)
    out: list[str] = []
    geminate = False
    for idx, (char, roma) in enumerate(units):
        if char == "っ":
            geminate = True
            continue
        if char == "ー":
            vowel = out[-1][-1] if out and out[-1][-1:] in _MACRON else ""
            if vowel and long_vowels == "macron":
                out[-1] = out[-1][:-1] + _MACRON[vowel]
            elif vowel and long_vowels == "written":
                out.append(vowel)
            continue
        if geminate:
            roma = ("t" + roma) if roma.startswith("ch") else (roma[0] + roma if roma[0].isalpha() else roma)
            geminate = False
        if char == "ん" and idx + 1 < len(units) and units[idx + 1][1][:1] in "aiueoy":
            roma = "n'"
        previous = out[-1] if out else ""
        vowel = previous[-1:] if previous else ""
        if roma in ("u", "o", "a", "e") and vowel in _LENGTHENERS and roma in _LENGTHENERS[vowel] and long_vowels != "written":
            if long_vowels == "macron":
                out[-1] = previous[:-1] + _MACRON[vowel]
            continue  # 'short': drop the lengthening vowel
        out.append(roma)
    return "".join(out)


def romaji(text: str) -> tuple[str, list[str]]:
    """
    Hepburn romaji of `text`: (display form with macrons, accepted answers).
    Accepted forms cover the usual ways learners type long vowels
    (gakkō / gakkou / gakkoo / gakko); comparison should ignore case, spaces,
    hyphens and apostrophes.
    """
    kana = spoken_reading(text)
    display = _romanize(kana, "macron")
    written = _romanize(kana, "written")
    accepted = [display, written, _romanize(kana, "short"), written.replace("ou", "oo")]
    return display, list(dict.fromkeys(accepted))


# ---------------------------------------------------------------------------
# Exercise payloads
# ---------------------------------------------------------------------------
# Fields shown before answering, in which furigana must not give the answer away.
_CONTEXT_FIELDS = ("question", "sentence_with_blank", "prompt")
_OPTIONS_FIELD = "options"
# Shown only after answering: furigana always allowed.
_AFTER_ANSWER_FIELDS = ("explanation",)


def _revealing_readings(payload: dict) -> set[str]:
    """
    Readings that would reveal the answer if shown as furigana. A kanji word
    is "being asked about" when its reading is visible in kana elsewhere in
    the exercise — e.g. question "Come si legge 学校?" with option がっこう, or
    question "…だいがくの…" with option 大学. Hiding a few harmless furigana
    by mistake is acceptable; showing the answer is not.
    """
    visible = [payload.get(f) for f in _CONTEXT_FIELDS] + list(payload.get(_OPTIONS_FIELD) or [])
    visible_texts = [to_hiragana(t) for t in visible if isinstance(t, str)]
    option_texts = {to_hiragana(o).strip() for o in payload.get(_OPTIONS_FIELD) or [] if isinstance(o, str)}

    hidden: set[str] = set()
    for text in visible_texts:
        for seg in annotate(text):
            reading = seg.get("reading")
            if not reading:
                continue
            if reading in option_texts or (len(reading) >= 2 and any(reading in t for t in visible_texts)):
                hidden.add(reading)
    return hidden


def _slice(segments: list[Segment], start: int, end: int) -> list[Segment]:
    """Segments covering text[start:end]; a reading is kept only if its segment lies fully inside."""
    out: list[Segment] = []
    pos = 0
    for seg in segments:
        seg_start, seg_end = pos, pos + len(seg["text"])
        pos = seg_end
        lo, hi = max(seg_start, start), min(seg_end, end)
        if lo >= hi:
            continue
        piece = seg["text"][lo - seg_start:hi - seg_start]
        inside = seg_start >= start and seg_end <= end
        out.append({"text": piece, "reading": seg["reading"]} if inside and seg.get("reading") else {"text": piece})
    return _merge_plain(out)


def _option_segments(option: str, sentence_with_blank: str | None) -> list[Segment]:
    """
    Furigana for one option. For fill_blank, the option is read inside the
    sentence (blank filled in), so counters and particles get their
    in-context reading (五___ + 人 → にん, not ひと).
    """
    blank = BLANK.search(sentence_with_blank or "")
    if blank:
        start = blank.start()
        filled = sentence_with_blank[:start] + option + sentence_with_blank[blank.end():]
        return _slice(annotate(filled), start, start + len(option))
    return annotate(option)


# Types with an explicit `focus` inside `sentence` (tracks/japanese_payloads.py).
_FOCUS_TYPES = {"kanji_reading", "kanji_writing", "romaji_input"}


def _focus_sentence(sentence: str, focus: str, hide_focus_reading: bool) -> list[Segment]:
    """Sentence segments with the focus word flagged (`"focus": true`), optionally without its furigana."""
    segments = annotate(sentence)
    start = sentence.index(focus)
    end = start + len(focus)
    focus_part = [
        {"text": s["text"], "focus": True} if hide_focus_reading else {**s, "focus": True}
        for s in _slice(segments, start, end)
    ]
    return _merge_plain(_slice(segments, 0, start) + focus_part + _slice(segments, end, len(sentence)))


def _annotate_focus_payload(exercise_type: str, payload: dict) -> dict:
    """
    Types with an explicit focus need no guessing: the sentence is always
    annotated (the focus must be underlined even without kanji), the focus
    has no furigana when its reading is the question (kanji_reading), and
    options never get furigana (kana readings, or kanji spellings that are
    themselves the question).
    """
    annotations = {
        "sentence": _focus_sentence(payload["sentence"], payload["focus"], exercise_type == "kanji_reading"),
    }
    explanation = payload.get("explanation")
    if isinstance(explanation, str) and has_kanji(explanation):
        annotations["explanation"] = annotate(explanation)
    return annotations


def _hide(segments: list[Segment], hidden: set[str]) -> list[Segment]:
    return _merge_plain([{"text": s["text"]} if s.get("reading") in hidden else s for s in segments])


def annotate_payload(exercise_type: str, payload: dict) -> dict:
    """
    Furigana for an exercise's display fields, keyed like the payload:
    {"question": [segments], "options": [[segments], ...], "explanation": [...]}.
    Only fields that contain kanji are included (plus `sentence` for focus
    types, always). Answer fields (`correct`, `expected`, `alternatives`,
    `accepted`) are not annotated: they are either options (already covered)
    or in the base language / romaji.

    Types without an explicit focus (multiple_choice, fill_blank,
    translate_rev) rely on the `_revealing_readings` heuristic.
    """
    if exercise_type in _FOCUS_TYPES:
        return _annotate_focus_payload(exercise_type, payload)

    hidden = _revealing_readings(payload)
    annotations: dict = {}

    for field in _CONTEXT_FIELDS:
        text = payload.get(field)
        if isinstance(text, str) and has_kanji(text):
            annotations[field] = _hide(annotate(text), hidden)

    # If any option contains the word being asked about, the options ARE the
    # question (e.g. "which kanji is だいがく?"): no furigana on any of them —
    # distractors are often non-words, and a lone unannotated option would
    # stand out as the answer.
    options = payload.get(_OPTIONS_FIELD)
    if isinstance(options, list) and any(isinstance(o, str) and has_kanji(o) for o in options):
        sentence = payload.get("sentence_with_blank")
        option_segments = [
            _option_segments(o, sentence) if isinstance(o, str) else [{"text": str(o)}] for o in options
        ]
        options_reveal = any(seg.get("reading") in hidden for segs in option_segments for seg in segs)
        if not options_reveal:
            annotations[_OPTIONS_FIELD] = option_segments

    for field in _AFTER_ANSWER_FIELDS:
        text = payload.get(field)
        if isinstance(text, str) and has_kanji(text):
            annotations[field] = annotate(text)

    return annotations


# ---------------------------------------------------------------------------
# Sentences of a text (Studio text requests)
# ---------------------------------------------------------------------------
_SENTENCE_END = "。！？!?"
_OPEN_QUOTES, _CLOSE_QUOTES = "「『", "」』"
_QUOTE_CONTINUES = "とっ、,"   # 「…」と言いました: the quote is part of a longer sentence


def split_sentences(text: str) -> list[str]:
    """
    Sentences of a Japanese text, verbatim: line breaks inside a sentence are
    joined (printed books wrap anywhere), a sentence ends at 。！？ outside
    quotes or at a closing quote not followed by a quotative (と, って, 、), so
    「…」と、…言いました。 stays whole while consecutive lines of dialogue are
    split. A sentence that is only a quote loses its brackets.
    """
    flat = re.sub(r"\s*\n\s*", "", text)
    sentences, current, depth = [], "", 0
    for i, ch in enumerate(flat):
        current += ch
        if ch in _OPEN_QUOTES:
            depth += 1
        elif ch in _CLOSE_QUOTES:
            depth = max(0, depth - 1)
        following = flat[i + 1:].lstrip()
        ends = depth == 0 and (
            (ch in _SENTENCE_END and not following[:1] in _CLOSE_QUOTES + _SENTENCE_END)
            or (ch in _CLOSE_QUOTES and following[:1] not in _QUOTE_CONTINUES + _SENTENCE_END)
        )
        if ends:
            sentences.append(current)
            current = ""
    sentences.append(current)

    result = []
    for sentence in (s.strip().strip("　").strip() for s in sentences):
        if len(sentence) > 1 and sentence[0] in _OPEN_QUOTES and sentence[-1] in _CLOSE_QUOTES \
                and not any(q in sentence[1:-1] for q in _OPEN_QUOTES + _CLOSE_QUOTES):
            sentence = sentence[1:-1].strip()
        if sentence:
            result.append(sentence)
    return result


# ---------------------------------------------------------------------------
# Vocabulary: content words of a text, in dictionary form
# ---------------------------------------------------------------------------
# UniDic part of speech → term category. Particles, copula and symbols are
# not terms; verbs that can be auxiliaries (非自立可能: 行く, いる, くれる…) are
# terms unless they follow a て-form (～ていく, ～ている, ～てくれる), and
# する is not one after a verbal noun (勉強する: the term is 勉強).
_TERM_POS = {
    ("名詞", "普通名詞"): "noun",
    ("名詞", "固有名詞"): "proper_noun",
    ("名詞", "数詞"): "numeral",
    ("代名詞", "*"): "pronoun",
    ("動詞", "一般"): "verb",
    ("形容詞", "一般"): "i_adjective",
    ("形状詞", "一般"): "na_adjective",
    ("副詞", "*"): "adverb",
    ("連体詞", "*"): "prenominal",
}
_MERGEABLE = {"noun", "proper_noun", "pronoun", "numeral"}   # take a nominal suffix: アメリカ人, 大学生, 僕達
_SUFFIX_NOUNS = {"語"}   # tagged as nouns but used as suffixes: 日本語, 英語
_HONORIFICS = {"さん", "くん", "君", "ちゃん", "さま", "様"}   # not part of the name: マルコさん → マルコ
_JAPANESE_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")   # kana or kanji: "Chapter" is not a term


def _grammatical_nai(previous, before_previous) -> bool:
    """ない that is grammar, not a word: ではない / じゃない / でもない, and ～くない after an adjective."""
    if previous is None:
        return False
    if previous.feature.pos1 == "形容詞" or previous.feature.lemma == "だ":   # 高くない, 学生じゃない
        return True
    return previous.surface in ("は", "も") and before_previous is not None and before_previous.surface in ("で", "じゃ")


def _term_pos(word, previous, before_previous=None) -> str | None:
    feature = word.feature
    if feature.pos1 == "形容詞" and feature.lemma == "無い" and _grammatical_nai(previous, before_previous):
        return None
    if feature.pos2 == "非自立可能" and feature.pos1 in ("動詞", "形容詞"):
        after_te = previous is not None and previous.feature.pos1 == "助詞" and previous.feature.pos2 == "接続助詞"
        after_verbal_noun = previous is not None and previous.feature.pos3 == "サ変可能" and feature.lemma == "為る"
        if after_te or after_verbal_noun:
            return None
        return "verb" if feature.pos1 == "動詞" else "i_adjective"
    return _TERM_POS.get((feature.pos1, feature.pos2)) or _TERM_POS.get((feature.pos1, "*"))


def _lemma(word) -> str:
    """UniDic lemma without the gloss of loanwords (バスケットボール-basketball → バスケットボール)."""
    return (word.feature.lemma or word.surface).split("-")[0]


def _dictionary_reading(word, previous) -> str:
    """Hiragana reading of the dictionary form, with the learner overrides (私 → わたし)."""
    kana = word.feature.kanaBase or word.feature.kana or word.surface
    if has_kanji(word.feature.orthBase or word.surface):
        override = _READING_OVERRIDES.get(word.feature.orthBase)
        if override:
            return override
        if word.surface == word.feature.orthBase:   # not inflected: same reading as the furigana
            return _kanji_reading(word, previous)
    return to_hiragana(kana)


def extract_terms(text: str) -> list[TermCandidate]:
    """
    Content words of `text` in dictionary form (言いました → 言う), each once:
    identity = lemma + reading, so かみ and 髪 (same UniDic lemma) are one
    term. A noun followed by a nominal suffix is one term (アメリカ人 — read
    じん —, 大学生), and so are consecutive numerals with their counter
    (二十四歳). Numerals only when written with kanji (二, not 24).
    """
    terms: dict[tuple[str, str], TermCandidate] = {}
    previous, before_previous, last = None, None, None
    for word in _tagger()(text):
        feature = word.feature
        if feature.pos1 == "接尾辞" and word.surface in _HONORIFICS:
            before_previous, previous = previous, word
            continue
        is_suffix = (feature.pos1 == "接尾辞" and feature.pos2 == "名詞的") or word.surface in _SUFFIX_NOUNS
        if is_suffix and last is not None and last.pos in _MERGEABLE:
            suffix_reading = _kanji_reading(word, previous) if has_kanji(word.surface) else to_hiragana(feature.kana or "")
            merged = TermCandidate(
                lemma=last.lemma + (feature.orthBase or word.surface),
                reading=last.reading + suffix_reading,
                written=last.written + word.surface,
                pos=last.pos if last.pos != "proper_noun" else "noun",
            )
            terms.pop((last.lemma, last.reading), None)
            terms.setdefault((merged.lemma, merged.reading), merged)
            last, before_previous, previous = merged, previous, word
            continue
        pos = _term_pos(word, previous, before_previous)
        if pos is not None and not _JAPANESE_SCRIPT.search(word.surface):
            pos = None
        if pos == "numeral" and not has_kanji(word.surface):
            pos = None
        if pos == "numeral" and last is not None and last.pos == "numeral":   # 二十 + 四 → 二十四
            merged = TermCandidate(
                lemma=last.lemma + (feature.orthBase or word.surface), reading=last.reading + _kanji_reading(word, previous),
                written=last.written + word.surface, pos="numeral",
            )
            terms.pop((last.lemma, last.reading), None)
            terms.setdefault((merged.lemma, merged.reading), merged)
            last, before_previous, previous = merged, previous, word
            continue
        if pos is None:
            last, before_previous, previous = None, previous, word
            continue
        candidate = TermCandidate(
            lemma=_lemma(word),
            reading=_dictionary_reading(word, previous),
            written=feature.orthBase or word.surface,
            pos=pos,
        )
        terms.setdefault((candidate.lemma, candidate.reading), candidate)
        last, before_previous, previous = candidate, previous, word
    return list(terms.values())
