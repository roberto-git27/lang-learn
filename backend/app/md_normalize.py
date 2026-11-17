"""
LLM fallback of the Studio import (Phase 9, D-08): the parts of a `.md` that
the deterministic parser cannot read are rewritten in the import format by
the cheap model, which may only *map* the content, never invent or fix it.

The model never writes Markdown: it returns structured exercises (a strict
tool call) and this module renders them as `## <type>` blocks, so the result
always goes back through `parse_exercises_md` and the human preview before
anything is imported. Only two kinds of segment are sent:

- a `## <type>` block with errors (a typo in a key, no `- [x]`, an unknown
  type…), with the parser's errors;
- text outside any block (e.g. exercises pasted from a workbook) — notes that
  contain no exercise come back as "skipped" and stay as they are.

Valid blocks and the front matter are never sent and never changed.
Pure functions only: the Claude call lives in `claude_service.normalize_exercises`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .md_import import (
    _COMMENT, _HEADING, FRONT_MATTER_KEYS, TYPE_KEYS, _common_defaults, _one_line, _parse_front_matter,
    parse_exercises_md,
)
from .tracks import TrackSpec

MAX_NORMALIZE_CHARS = 20_000   # text sent to the model per request: a cost cap


@dataclass
class Segment:
    """A run of body lines: one `## <type>` block, or text outside any block."""
    id: str
    kind: str                     # "block" | "text"
    start: int                    # 1-based line number of its first line
    lines: list[str]
    errors: list[str] = field(default_factory=list)   # parser errors of an invalid block
    needs_model: bool = False


@dataclass
class SplitFile:
    head: list[str]               # front matter lines, kept verbatim
    segments: list[Segment]
    errors: list[str]             # file-level: the model cannot help, fix them by hand


class OptionOut(BaseModel):
    text: str
    correct: bool


class NormalizedExercise(BaseModel):
    """One exercise as returned by the model (`submit_parsed_exercises`)."""
    segment_id: str
    exercise_type: str
    difficulty: int | None = None
    topics: list[str] = Field(default_factory=list)
    sentence: str = ""
    translation: str | None = None
    question: str | None = None
    focus: str | None = None
    options: list[OptionOut] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    explanation: str | None = None
    answer: str | None = None
    source_excerpt: str = ""


class SkippedSegment(BaseModel):
    segment_id: str
    reason: str


def importable_types(spec: TrackSpec) -> list[str]:
    """Exercise types of the track that the `.md` format can describe."""
    return [t for t in spec.payload_models if t in TYPE_KEYS]


def _is_content(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not _HEADING.match(stripped) and not _COMMENT.match(stripped)


def split_for_normalization(text: str, spec: TrackSpec) -> SplitFile:
    """
    The file cut into segments, each marked when it needs the model. The
    front matter must already be valid (the model never touches it).
    """
    lines = text.splitlines()
    values, start, errors = _parse_front_matter(lines, spec.code, "import", FRONT_MATTER_KEYS)
    _common_defaults(values, errors)
    if errors:
        return SplitFile(head=lines[:start], segments=[], errors=errors)

    segments: list[Segment] = []
    current: Segment | None = None
    for i in range(start, len(lines)):
        heading = _HEADING.match(lines[i].strip())
        if heading or current is None:
            kind = "block" if heading and len(heading.group(1)) == 2 else "text"
            # Consecutive non-block headings and text stay one text segment.
            if not (current is not None and current.kind == "text" and kind == "text"):
                current = Segment(id=f"s{len(segments) + 1}", kind=kind, start=i + 1, lines=[])
                segments.append(current)
        current.lines.append(lines[i])

    by_line = {item.line: item for item in parse_exercises_md(text, spec).items}
    for segment in segments:
        if segment.kind == "block":
            item = by_line.get(segment.start)
            segment.errors = list(item.errors) if item else ["not parsed"]
            segment.needs_model = bool(segment.errors)
        else:
            segment.needs_model = any(_is_content(line) for line in segment.lines)
    return SplitFile(head=lines[:start], segments=segments, errors=[])


def segments_prompt(segments: list[Segment]) -> str:
    """The segments to normalize, delimited and with their parser errors."""
    parts = []
    for segment in segments:
        attrs = f'id="{segment.id}" kind="{"invalid_block" if segment.kind == "block" else "free_text"}" line="{segment.start}"'
        body = "\n".join(segment.lines).strip("\n")
        errors = "".join(f"\nparser error: {e}" for e in segment.errors)
        parts.append(f"<segment {attrs}>{errors}\n{body}\n</segment>")
    return "\n\n".join(parts)


def _comment_text(text: str) -> str:
    """One line that cannot close an HTML comment."""
    return _one_line(text).replace("--", "—")


def render_block(item: NormalizedExercise) -> list[str]:
    """An exercise as an import-format block; invalid content is kept so the preview reports it."""
    lines = [f"## {item.exercise_type}"]
    if item.source_excerpt.strip():
        lines.append(f"<!-- source: {_comment_text(item.source_excerpt)} -->")
    if item.difficulty is not None:
        lines.append(f"difficulty: {item.difficulty}")
    topics = [t for t in (_one_line(t) for t in item.topics) if t]
    if topics:
        lines.append(f"topics: {', '.join(topics)}")
    lines.append(f"sentence: {_one_line(item.sentence)}")
    if item.translation and item.translation.strip():
        lines.append(f"translation: {_one_line(item.translation)}")
    used = TYPE_KEYS.get(item.exercise_type, set())
    for key in ("question", "focus", "answer"):
        value = getattr(item, key)
        if key in used and value and value.strip():
            lines.append(f"{key}: {_one_line(value)}")
    if "alternative" in used:
        lines += [f"alternative: {_one_line(a)}" for a in item.alternatives if a.strip()]
    lines += [f"- [{'x' if option.correct else ' '}] {_one_line(option.text)}" for option in item.options]
    if "explanation" in used and item.explanation and item.explanation.strip():
        lines.append(f"explanation: {_one_line(item.explanation)}")
    return lines


def rebuild(split: SplitFile, results: dict[str, list[NormalizedExercise]]) -> str:
    """
    The file with every segment that got exercises replaced by their blocks.
    A text segment keeps its leading headings (e.g. '# Lesson 2') and the
    rest of its text inside an HTML comment (notes, answer keys: nothing is
    lost, and text outside blocks is ignored by the parser anyway); a segment
    the model returned nothing for is kept as it was.
    """
    out = list(split.head)
    for segment in split.segments:
        items = results.get(segment.id)
        if not items:
            out += segment.lines
            continue
        if segment.kind == "text":
            first = next(i for i, line in enumerate(segment.lines) if _is_content(line))
            out += segment.lines[:first]
            original = "\n".join(segment.lines[first:]).strip("\n").replace("-->", "—>")
            out += ["<!-- original text, rewritten as the blocks below:", *original.splitlines(), "-->"]
        for item in items:
            if out and out[-1].strip():
                out.append("")
            out += render_block(item)
        out.append("")
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
