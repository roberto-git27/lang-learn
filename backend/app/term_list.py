"""
Term lists written by a human (Phase 9): a `.csv` with a header row, one
term per line, opened in the Studio's *Vocabulary* mode instead of a text.

    term,reading,meaning
    学生,,studente
    日,にち,giorno (nei composti)
    こんにちは,,buongiorno

- `term` (Italian alias `termine`) is required; `reading` (`lettura`, kana)
  and `meaning` (`significato`) are optional. Other columns (a level, tags)
  are ignored with a warning: a term's level comes from its kanji.
- The delimiter is a comma, a semicolon or a tab (spreadsheet exports).
- Each term goes through `TrackSpec.dictionary_term`, so a word already
  found in a text is the same term; a meaning given here is a human one.

Pure functions only: the DB side lives in `term_service.py`.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass

from .tracks import TermCandidate, TrackSpec

COLUMNS = {
    "term": "term", "termine": "term",
    "reading": "reading", "lettura": "reading",
    "meaning": "meaning", "significato": "meaning",
}
DELIMITERS = (",", ";", "\t")
MAX_ROWS = 2000


@dataclass
class TermRow:
    line: int
    candidate: TermCandidate
    meaning: str | None


@dataclass
class TermList:
    rows: list[TermRow]
    errors: list[str]     # the list cannot be read at all
    warnings: list[str]   # rows or columns left out


def _header(text: str) -> tuple[int, str] | None:
    """(index, line) of the first line that is not empty or a `#` comment."""
    for index, line in enumerate(text.splitlines()):
        if line.strip() and not line.lstrip().startswith("#"):
            return index, line
    return None


def _delimiter(header: str) -> str | None:
    for delimiter in DELIMITERS:
        first = header.split(delimiter)[0].strip().strip('"').strip().lower()
        if delimiter in header and COLUMNS.get(first) is not None:
            return delimiter
    return None


def is_term_list(text: str) -> bool:
    """A term list starts with a header row whose first column is a known one (`term`, `reading`…)."""
    found = _header(text)
    return found is not None and _delimiter(found[1]) is not None


def parse_term_list(text: str, spec: TrackSpec) -> TermList:
    found = _header(text)
    delimiter = _delimiter(found[1]) if found else None
    if found is None or delimiter is None:
        return TermList(rows=[], errors=["Not a term list: the first line must be a header such as 'term,reading,meaning'"], warnings=[])
    start, _ = found
    lines = text.splitlines()
    reader = csv.reader(lines[start:], delimiter=delimiter)
    header = [cell.strip().lower() for cell in next(reader)]
    columns = {COLUMNS[name]: i for i, name in reversed(list(enumerate(header))) if name in COLUMNS}
    if "term" not in columns:
        return TermList(rows=[], errors=["The header has no 'term' column"], warnings=[])
    warnings = [
        f"Column '{name}' ignored" + (": a term's level comes from its kanji" if name in ("level", "livello") else "")
        for name in header if name and name not in COLUMNS
    ]

    def cell(row: list[str], key: str) -> str:
        index = columns.get(key)
        return row[index].strip() if index is not None and index < len(row) else ""

    rows: list[TermRow] = []
    seen: dict[tuple[str, str], int] = {}
    for offset, row in enumerate(reader, start=1):
        line = start + offset + 1   # 1-based, the header is line start + 1
        if not any(c.strip() for c in row) or row[0].lstrip().startswith("#"):
            continue
        if len(rows) >= MAX_ROWS:
            warnings.append(f"Only the first {MAX_ROWS} terms are read")
            break
        word = cell(row, "term")
        if not word:
            warnings.append(f"Line {line}: no term, skipped")
            continue
        candidate = spec.dictionary_term(word, cell(row, "reading") or None)
        if candidate is None:
            warnings.append(f"Line {line}: no term, skipped")
            continue
        key = (candidate.lemma, candidate.reading)
        if key in seen:
            warnings.append(f"Line {line}: {word} is the same term as line {seen[key]}, skipped")
            continue
        seen[key] = line
        rows.append(TermRow(line=line, candidate=candidate, meaning=cell(row, "meaning")[:255] or None))
    if not rows:
        return TermList(rows=[], errors=["The list has no terms"], warnings=warnings)
    return TermList(rows=rows, errors=[], warnings=warnings)
