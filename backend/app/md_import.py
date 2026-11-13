"""
Deterministic parser for the Studio's `.md` exercise format (Phase 9, D-08):
no LLM, 0 tokens, a line number on every problem. The format is documented
with examples in `sample/README.md`; in short:

    ---                                  optional front matter: defaults
    difficulty: 1                        for every block below
    topics: [school, particle_wa]
    ---

    ## kanji_reading                     one block per exercise, `## <type>`
    sentence: わたしは 学生です。
    translation: Sono uno studente.
    focus: 学生
    - [x] がくせい                        options: exactly one checked
    - [ ] がっせい
    ...

Other headings (`#`, `###`…) close the current block and, like any text
outside a block, are ignored — free notes can live next to the exercises.
Inside a block every line must be a known `key: value` (English keys, Italian
aliases accepted) or an option; anything else is an error, so typos never
slip through silently.

The same front matter and conventions describe a *generation request*
(`mode: generate`, see `parse_generation_request`): parameters for the AI,
free-text instructions and an optional `## terms` list. `exercises_to_markdown`
turns exercises back into the import format, so a generated draft can be
edited by hand and imported.

Pure functions only: duplicates against the DB and the actual insert live in
`studio_service.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from .exercise_payloads import BLANK, MAX_DIFFICULTY
from .tracks import TrackSpec

# Canonical keys (D-16: English) and the Italian aliases accepted in files.
KEY_ALIASES = {
    "sentence": "sentence", "frase": "sentence",
    "translation": "translation", "traduzione": "translation",
    "question": "question", "domanda": "question",
    "focus": "focus",
    "explanation": "explanation", "spiegazione": "explanation",
    "alternative": "alternative", "alternativa": "alternative",
    "answer": "answer", "risposta": "answer",
    "difficulty": "difficulty", "difficoltà": "difficulty", "difficolta": "difficulty",
    "topics": "topics", "argomenti": "topics",
    "track": "track",
    "mode": "mode",
    # generation requests only
    "per_term": "per_term", "count": "count", "types": "types", "examples": "examples",
}
FRONT_MATTER_KEYS = {"track", "mode", "difficulty", "topics"}
TERMS_KEYS = {"track", "mode"}
REQUEST_KEYS = FRONT_MATTER_KEYS | {"per_term", "count", "types", "examples"}
REPEATABLE_KEYS = {"alternative"}
COMMON_KEYS = {"sentence", "translation", "difficulty", "topics"}

# Keys each exercise type uses on top of COMMON_KEYS, and whether it takes options.
TYPE_KEYS: dict[str, set[str]] = {
    "multiple_choice": {"question", "explanation"},
    "fill_blank": {"explanation"},
    "translate_rev": {"alternative"},
    "kanji_reading": {"focus", "explanation"},
    "kanji_writing": {"focus", "explanation"},
    "romaji_input": {"focus", "explanation", "answer"},
}
OPTION_TYPES = {"multiple_choice", "fill_blank", "kanji_reading", "kanji_writing"}

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_OPTION = re.compile(r"^[-*+]\s+\[([ xX])\](?:\s+(.*?))?\s*$")
_FIELD = re.compile(r"^([^\s:：]+)\s*[:：]\s*(.*?)\s*$")
_COMMENT = re.compile(r"^<!--.*-->$")
_TRAILING_COMMENT = re.compile(r"\s+#.*$")   # front matter only: "difficulty: 1   # a note"
_TOPIC_SEPARATORS = re.compile(r"[,、]")
_TEXTBOOK_BLANK = re.compile(r"【[\s\u3000]*】")   # 【　　】, the blank printed in textbooks


class ParsedExercise(BaseModel):
    """One `## <type>` block, parsed and validated (payload normalized when valid)."""
    line: int
    exercise_type: str
    difficulty: int | None = None
    topics: list[str] = Field(default_factory=list)
    phrase_target: str | None = None   # the sentence, in the track's target language
    phrase_base: str | None = None     # its translation, in the track's base language
    payload: dict | None = None
    annotations: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    term: str | None = None            # generated items: the requested term it is about

    @property
    def is_valid(self) -> bool:
        return not self.errors


class ParsedFile(BaseModel):
    items: list[ParsedExercise] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)   # file-level: nothing can be imported


@dataclass
class _Block:
    line: int
    exercise_type: str
    fields: dict[str, list[str]] = field(default_factory=dict)
    options: list[tuple[bool, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def normalize_topic(raw: str) -> str:
    """'Particella は' → 'particella_は': lower case, runs of non-word characters → '_'."""
    return re.sub(r"\W+", "_", raw.strip().lower()).strip("_")


def _parse_topics(value: str) -> list[str]:
    value = value.strip().removeprefix("[").removesuffix("]")
    return list(dict.fromkeys(t for t in (normalize_topic(p) for p in _TOPIC_SEPARATORS.split(value)) if t))


def _parse_difficulty(value: str) -> int:
    try:
        difficulty = int(value.strip())
    except ValueError:
        raise ValueError(f"difficulty must be a number from 1 to {MAX_DIFFICULTY}, got '{value}'") from None
    if not 1 <= difficulty <= MAX_DIFFICULTY:
        raise ValueError(f"difficulty must be from 1 to {MAX_DIFFICULTY}, got {difficulty}")
    return difficulty


def _field(line: str) -> tuple[str, str] | None:
    """(canonical key, value) for a `key: value` line with a known key, else None."""
    match = _FIELD.match(line)
    if not match:
        return None
    key = KEY_ALIASES.get(match.group(1).lower())
    return (key, match.group(2)) if key else None


def _parse_front_matter(
    lines: list[str], track_code: str, mode: str, allowed: set[str],
) -> tuple[dict[str, tuple[int, str]], int, list[str]]:
    """({key: (line, raw value)}, index of the first body line, file-level errors)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0, []
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, len(lines), ["line 1: the front matter is not closed by a '---' line"]

    values, errors = {}, []
    for i in range(1, end):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            continue
        parsed = _field(line)
        if parsed is None or parsed[0] not in allowed:
            errors.append(f"line {i + 1}: unknown front matter line '{line}' (allowed: {', '.join(sorted(allowed))})")
            continue
        key, value = parsed
        value = _TRAILING_COMMENT.sub("", value).strip()
        if key == "track" and value != track_code:
            errors.append(f"line {i + 1}: this file is for track '{value}', not '{track_code}'")
        elif key == "mode" and value.lower() != mode:
            errors.append(f"line {i + 1}: this file is for the Studio's '{value}' mode, not '{mode}'")
        else:
            values[key] = (i + 1, value)
    return values, end + 1, errors


def _common_defaults(values: dict[str, tuple[int, str]], errors: list[str]) -> dict:
    """difficulty/topics from the front matter, with line-numbered errors."""
    defaults = {}
    if "difficulty" in values:
        line, value = values["difficulty"]
        try:
            defaults["difficulty"] = _parse_difficulty(value)
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
    if "topics" in values:
        defaults["topics"] = _parse_topics(values["topics"][1])
    return defaults


def _parse_blocks(lines: list[str], start: int) -> list[_Block]:
    blocks: list[_Block] = []
    current: _Block | None = None
    for i in range(start, len(lines)):
        number, line = i + 1, lines[i].strip()
        heading = _HEADING.match(line)
        if heading:
            current = None
            if len(heading.group(1)) == 2:
                current = _Block(line=number, exercise_type=(heading.group(2).split() or [""])[0].lower())
                blocks.append(current)
            continue
        if current is None or not line or _COMMENT.match(line):
            continue

        option = _OPTION.match(line)
        if option:
            text = option.group(2) or ""
            if not text:
                current.errors.append(f"line {number}: option without text")
            current.options.append((option.group(1) != " ", text))
            continue
        parsed = _field(line)
        if parsed is None:
            current.errors.append(f"line {number}: not a known 'key: value' line or '- [ ]' option: '{line}'")
            continue
        key, value = parsed
        if key in current.fields and key not in REPEATABLE_KEYS:
            current.errors.append(f"line {number}: '{key}' given twice")
            continue
        current.fields.setdefault(key, []).append(value)
    return blocks


def validation_message(exc: ValueError) -> str:
    """One readable line for a payload validation error."""
    if isinstance(exc, ValidationError):
        error = exc.errors()[0]
        location = ".".join(str(part) for part in error["loc"])
        message = error["msg"].removeprefix("Value error, ")
        return f"{location}: {message}" if location else message
    return str(exc)


def phrase_from_payload(exercise_type: str, payload: dict) -> str | None:
    """
    The complete sentence an exercise is about — its phrase in the target
    language (a fill_blank one gets its blank filled in). None for
    multiple_choice, whose question is in the base language.
    """
    if exercise_type == "fill_blank":
        return BLANK.sub(payload["correct"], payload["sentence_with_blank"], count=1)
    if exercise_type == "translate_rev":
        return payload["prompt"]
    return payload.get("sentence") if exercise_type != "multiple_choice" else None


def _build(block: _Block, defaults: dict, spec: TrackSpec) -> ParsedExercise:
    item = ParsedExercise(line=block.line, exercise_type=block.exercise_type, errors=list(block.errors))
    errors = item.errors
    exercise_type = block.exercise_type
    if exercise_type not in spec.payload_models or exercise_type not in TYPE_KEYS:
        importable = ", ".join(t for t in spec.payload_models if t in TYPE_KEYS)
        errors.append(f"unknown exercise type '{exercise_type}' (this track has: {importable})")
        return item

    fields = {key: values[0] for key, values in block.fields.items()}
    for key in block.fields.keys() - COMMON_KEYS - TYPE_KEYS[exercise_type]:
        errors.append(f"'{key}' is not used by {exercise_type}")

    try:
        item.difficulty = _parse_difficulty(fields["difficulty"]) if "difficulty" in fields else defaults.get("difficulty")
        if item.difficulty is None:
            errors.append("difficulty missing (set it in the block or in the front matter)")
    except ValueError as exc:
        errors.append(str(exc))
    item.topics = _parse_topics(fields["topics"]) if "topics" in fields else list(defaults.get("topics", []))

    sentence = fields.get("sentence", "")
    item.phrase_base = fields.get("translation") or None
    if not sentence:
        errors.append("'sentence' missing")
    if not item.phrase_base:
        errors.append("'translation' missing")

    payload: dict = {"explanation": fields.get("explanation") or None}
    if exercise_type in OPTION_TYPES:
        checked = [i for i, (correct, _) in enumerate(block.options) if correct]
        if len(checked) != 1:
            errors.append(f"exactly one option must be marked '- [x]', found {len(checked)}")
        payload["options"] = [text for _, text in block.options]
        payload["correct_index"] = checked[0] if len(checked) == 1 else None
    elif block.options:
        errors.append(f"{exercise_type} takes no options")

    if exercise_type == "fill_blank":
        sentence = _TEXTBOOK_BLANK.sub("___", sentence)
        payload["sentence_with_blank"] = sentence
        if payload["correct_index"] is not None:
            payload["correct"] = payload["options"][payload["correct_index"]]
    elif exercise_type == "translate_rev":
        payload.update(prompt=sentence, expected=item.phrase_base, alternatives=block.fields.get("alternative", []))
    else:
        payload.update(sentence=sentence, question=fields.get("question"), focus=fields.get("focus"))
    if errors:
        return item

    try:
        item.payload = spec.validate_payload(exercise_type, payload)
    except ValueError as exc:
        errors.append(validation_message(exc))
        return item

    item.phrase_target = phrase_from_payload(exercise_type, item.payload) or sentence
    answer = fields.get("answer")
    if answer and answer.strip().lower() not in item.payload.get("accepted", []):
        errors.append(
            f"answer '{answer}' differs from the romaji computed from the reading "
            f"('{item.payload.get('expected')}'): check the sentence or remove 'answer'"
        )
    item.warnings.extend(spec.level_problems(item.difficulty, item.payload))
    item.annotations = spec.annotations_for(exercise_type, item.payload)
    return item


def parse_exercises_md(text: str, spec: TrackSpec) -> ParsedFile:
    """Every `## <type>` block of `text`, validated for the track; never raises on bad input."""
    lines = text.splitlines()
    values, start, errors = _parse_front_matter(lines, spec.code, "import", FRONT_MATTER_KEYS)
    defaults = _common_defaults(values, errors)
    if errors:
        return ParsedFile(errors=errors)
    items = [_build(block, defaults, spec) for block in _parse_blocks(lines, start)]
    if not items:
        return ParsedFile(errors=["no exercises found: every exercise starts with a '## <exercise_type>' heading"])
    return ParsedFile(items=items)


# ---------------------------------------------------------------------------
# Generation requests (`mode: generate`)
# ---------------------------------------------------------------------------
MAX_PER_TERM = 6
MAX_COUNT = 20
MAX_SPECS = 30          # exercises per request: a cost cap
MAX_EXAMPLES = 5        # human-checked examples shown to the model per exercise type
_TERMS_HEADING = re.compile(r"^##\s+(terms|termini)\s*$", re.IGNORECASE)
_TERM_ITEM = re.compile(r"^[-*+]\s+(\S+)\s*(.*)$")


class Term(BaseModel):
    text: str
    note: str | None = None    # anything after the term on its line, e.g. a meaning


class GenerationRequest(BaseModel):
    """A parsed generation request: what to generate, for which terms, with which extra instructions."""
    difficulty: int | None = None
    topics: list[str] = Field(default_factory=list)
    types: list[str] | None = None      # None: the track's option-based types
    per_term: int = 3
    count: int = 5                      # used when there are no terms
    examples: int = 3
    terms: list[Term] = Field(default_factory=list)
    instructions: str = ""
    errors: list[str] = Field(default_factory=list)


def _bounded_int(values: dict, key: str, default: int, low: int, high: int, errors: list[str]) -> int:
    if key not in values:
        return default
    line, raw = values[key]
    try:
        number = int(raw)
    except ValueError:
        number = None
    if number is None or not low <= number <= high:
        errors.append(f"line {line}: {key} must be a number from {low} to {high}, got '{raw}'")
        return default
    return number


def parse_generation_request(text: str, spec: TrackSpec) -> GenerationRequest:
    """
    Front matter (difficulty — required —, topics, types, per_term, count,
    examples), free-text instructions for the model (everything else in the
    body), and an optional `## terms` section: one `- term [note]` per line
    (until the next heading); each term gets `per_term` exercises. Never
    raises on bad input.
    """
    lines = text.splitlines()
    values, start, errors = _parse_front_matter(lines, spec.code, "generate", REQUEST_KEYS)
    request = GenerationRequest(**_common_defaults(values, errors))
    request.per_term = _bounded_int(values, "per_term", 3, 1, MAX_PER_TERM, errors)
    request.count = _bounded_int(values, "count", 5, 1, MAX_COUNT, errors)
    request.examples = _bounded_int(values, "examples", 3, 0, MAX_EXAMPLES, errors)
    if "types" in values:
        line, raw = values["types"]
        request.types = list(dict.fromkeys(t.strip().lower() for t in _TOPIC_SEPARATORS.split(raw) if t.strip()))
        unknown = [t for t in request.types if t not in spec.payload_models]
        if unknown or not request.types:
            errors.append(f"line {line}: unknown exercise types {unknown} (this track has: {', '.join(spec.payload_models)})")

    instructions, in_terms = [], False
    for i in range(start, len(lines)):
        line = lines[i].strip()
        if _TERMS_HEADING.match(line):
            in_terms = True
        elif line.startswith("#") and _HEADING.match(line):
            in_terms = False
            instructions.append(lines[i])
        elif in_terms:
            if not line or _COMMENT.match(line):
                continue
            item = _TERM_ITEM.match(line)
            if item is None:
                errors.append(f"line {i + 1}: a term is written '- term [note]', got '{line}'")
                continue
            term = item.group(1).rstrip(":：")
            if any(t.text == term for t in request.terms):
                errors.append(f"line {i + 1}: term '{term}' listed twice")
                continue
            request.terms.append(Term(text=term, note=item.group(2).lstrip(":：—–- ").strip() or None))
        else:
            instructions.append(lines[i])
    request.instructions = "\n".join(instructions).strip()

    if request.difficulty is None and "difficulty" not in values:
        errors.append("difficulty missing: set it in the front matter (1–10)")
    if not request.terms and not request.instructions:
        errors.append("empty request: write what to generate, or list terms under '## terms'")
    total = len(request.terms) * request.per_term if request.terms else request.count
    if total > MAX_SPECS:
        errors.append(f"{total} exercises requested: at most {MAX_SPECS} per request (fewer terms or a lower per_term)")
    request.errors = errors
    return request


# ---------------------------------------------------------------------------
# Exercises → .md (the import format), to edit a generated draft by hand
# ---------------------------------------------------------------------------
def _one_line(text: str | None) -> str:
    """Line breaks → one space; every other character (full-width spaces included) is kept."""
    return re.sub(r"\s*\n\s*", " ", text or "").strip()


def exercises_to_markdown(items: list[ParsedExercise], track_code: str) -> str:
    """The import-format .md of valid exercises; `parse_exercises_md` reads it back unchanged."""
    lines = ["---", f"track: {track_code}", "mode: import", "---", ""]
    for item in items:
        if not item.payload:
            continue
        payload, exercise_type = item.payload, item.exercise_type
        lines += [f"## {exercise_type}", f"difficulty: {item.difficulty}"]
        if item.topics:
            lines.append(f"topics: {', '.join(item.topics)}")
        sentence = {
            "fill_blank": payload.get("sentence_with_blank"),
            "translate_rev": payload.get("prompt"),
        }.get(exercise_type, payload.get("sentence") or item.phrase_target)
        lines += [f"sentence: {_one_line(sentence)}", f"translation: {_one_line(item.phrase_base)}"]
        if exercise_type == "multiple_choice":
            lines.append(f"question: {_one_line(payload['question'])}")
        if "focus" in payload:
            lines.append(f"focus: {payload['focus']}")
        if "options" in payload:
            correct = payload.get("correct_index")
            if correct is None:
                correct = payload["options"].index(payload["correct"])
            lines += [f"- [{'x' if i == correct else ' '}] {option}" for i, option in enumerate(payload["options"])]
        lines += [f"alternative: {_one_line(alternative)}" for alternative in payload.get("alternatives", [])]
        if payload.get("explanation"):
            lines.append(f"explanation: {_one_line(payload['explanation'])}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Texts for the vocabulary (`mode: terms`)
# ---------------------------------------------------------------------------
def parse_terms_text(text: str, spec: TrackSpec) -> tuple[str, list[str]]:
    """
    (body, file-level errors) of a text whose vocabulary is extracted: the
    optional front matter (`track`, `mode: terms`), headings and HTML
    comments are left out — only the prose and dialogue lines remain.
    """
    lines = text.splitlines()
    _, start, errors = _parse_front_matter(lines, spec.code, "terms", TERMS_KEYS)
    body = re.sub(r"<!--.*?-->", "", "\n".join(lines[start:]), flags=re.DOTALL)   # comments may span lines
    return "\n".join(line for line in body.splitlines() if not _HEADING.match(line.strip())).strip(), errors

