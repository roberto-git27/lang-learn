# Samples — the Studio `.md` formats

Three modes, chosen by `mode:` in the front matter (or by the Studio tab):
`import` (default), `generate` and `terms`.

Files in this folder can be imported from the **Studio** tab (open the file →
*Preview* → *Import*). The import is deterministic: no LLM call, 0 tokens.
Imported exercises are stored as already verified (`human_checked`) and become
style examples for the exercises the agent generates.

- [`ja_starter.md`](ja_starter.md) — 18 beginner Japanese exercises (levels
  1–3, every exercise type). Import it to try the app without spending tokens.
- [`ja_terms.csv`](ja_terms.csv) — a term list with readings and meanings:
  open it in the Studio's *Vocabulary* mode.
- [`ja_story1.md`](ja_story1.md) — a short original story with a dialogue
  (`mode: terms`, JLPT N5 kanji): open it in the Studio's *Vocabulary* mode to
  extract its words.
- [`ja_generate1.md`](ja_generate1.md), [`ja_generate2.md`](ja_generate2.md) —
  generation requests (level 1, three exercises for each of 一二三四五火 and
  水木金土人本): open them in the Studio, *Generate with AI*, then keep what
  you like. Edit the request text to experiment with the prompt.

All samples here are written from scratch for this project. Exercises taken
from textbooks or courses may be copyrighted: keep those files in the
git-ignored `data/` folder (`backend/tests/test_md_import.py` parses every
`data/**/*.md` too, so your own files double as import tests).

## Format

```markdown
---
track: ja                  # optional: the import fails if it is not the selected track
difficulty: 1              # default for every block (1–10)
topics: school, family     # optional default topics
---

# Lesson 1

Any heading other than "##", and any text outside a block, is ignored.

## kanji_reading
sentence: わたしは 学生です。
translation: Sono uno studente.
focus: 学生
- [x] がくせい
- [ ] がっせい
- [ ] がくせ
- [ ] かくせい
explanation: Niente っ piccola.
```

One exercise per `## <exercise_type>` block; options are task-list items,
exactly one checked. Inside a block every non-empty line must be a
`key: value` line or an option (`<!-- comments -->` are allowed): an unknown
line is an error, so a typo never slips through silently. `# comments` at the
end of a line are allowed only in the front matter.

### Keys

| Key | Italian alias | Used by | |
|---|---|---|---|
| `sentence` | `frase` | every type | the sentence in the target language (required) |
| `translation` | `traduzione` | every type | its translation in the base language (required) |
| `difficulty` | `difficoltà` | every type | 1–10, overrides the front matter |
| `topics` | `argomenti` | every type | comma-separated, overrides the front matter; normalized to `snake_case` |
| `question` | `domanda` | `multiple_choice` | the question |
| `focus` | — | `kanji_reading`, `kanji_writing`, `romaji_input` | the word asked about, copied exactly from the sentence |
| `explanation` | `spiegazione` | all but `translate_rev` | optional |
| `alternative` | `alternativa` | `translate_rev` | another accepted translation (repeatable) |
| `answer` | `risposta` | `romaji_input` | optional check: must match the romaji computed from the reading |

### Exercise types (Japanese track)

| Type | Needs | Notes |
|---|---|---|
| `multiple_choice` | `question`, 4 options | |
| `fill_blank` | `sentence` with `___` (or the textbook blank `【　】`), 2–6 options | the stored phrase is the sentence with the blank filled in |
| `translate_rev` | — | the learner types `translation` (or an `alternative`) in Italian |
| `kanji_reading` | `focus` with kanji, 4 kana options | |
| `kanji_writing` | `focus` in kana, 4 kanji options | |
| `romaji_input` | `focus` | the romaji is computed, never written; `answer` only checks it |

Readings (furigana, romaji) are always computed, never written in the file.

### What the preview reports

- **error** — the block is invalid (line number included); it is skipped, the rest can still be imported.
- **warning** — imported anyway: kanji above the level (at difficulty 1–2), or a sentence already stored with another translation or difficulty (the stored one is kept: a sentence is one phrase).
- **duplicate** — the same exercise is already in the database or earlier in the file. Re-importing a corrected file therefore only adds what is new.

Every import keeps the source text, so each exercise can be traced back to the file it came from.

### Fix with AI

When the preview has blocks with errors, or no block at all (e.g. exercises
pasted from a workbook), *Fix with AI* sends **only** those blocks and the
text outside blocks to a cheap model (Claude Haiku), which maps them to this
format: content copied as written, never invented — a missing translation or
an answer the source does not give stays missing, and the preview says so.
Valid blocks and the front matter are never sent. Each rewritten block gets a
`<!-- source: … -->` line with the text it came from, and pasted text is kept
in a comment above its blocks. The result goes back to the editor: compare,
fill in, *Preview*, *Import* (as verified exercises: you checked them).
*Restore the text before the AI fix* undoes it.

## Generation requests

A request is a `.md` with `mode: generate` in the front matter. The Studio
turns it into a plan (one exercise per spec: type, difficulty, topics, term),
asks the AI to write them, checks every result and shows a draft: keep what
you like and save it to the review queue, or *Edit as .md* to fix it by hand
and import it as verified exercises.

```markdown
---
track: ja
mode: generate
difficulty: 1                          # required (1–10)
per_term: 3                            # exercises per term (1–6, default 3)
types: kanji_reading, kanji_writing    # optional: default = the track's option-based types
topics: numbers_counters               # optional; without it the AI proposes topics
examples: 3                            # verified exercises shown to the AI per type (0–5, default 3)
---

Free text for the AI: what you want, in your own words (any language).

## terms
- 一 uno
- 火 fuoco; 火よう日 = martedì
```

- Everything outside the front matter and the `## terms` list is sent to the AI as your request.
- Each term gets `per_term` exercises and the types rotate across terms. Without terms, `count: N` (1–20, default 5) asks for N exercises.
- Anything after the term on its line is a note for the AI (a meaning, the readings to practise…).
- At most 30 exercises per request.
- **Examples:** up to `examples` human-checked exercises per type are picked at random — same difficulty first, then the closest levels — and shown to the AI as models of structure and tone.
- **Checks:** every exercise must be valid for its type, use only the kanji of its level (levels 1–2) and really use its term. What fails is sent back once with the reason; what still fails appears in the draft as an error.

## Vocabulary texts (`mode: terms`)

Any text — a chapter, a dialogue, a list of sentences. The Studio extracts its
content words in dictionary form (言いました → 言う; particles, the copula and
auxiliaries such as ～ている are left out), shows which are new and which are
already known, and stores the new ones. Headings, `<!-- comments -->` and the
front matter are ignored. No AI is involved; meanings are added afterwards
(*Translate missing meanings with AI*, or by hand).

```markdown
---
track: ja
mode: terms
---

# Chapter title (ignored)

今日は 土曜日です。あさから 雨が ふっています。
A：雨は いつ やみますか。
B：午後三時ごろ やみます。
```

### Term lists (`.csv`)

Curated words with their meanings, one per line after a header row
(comma, semicolon or tab; Italian headers `termine`, `lettura`,
`significato` work too):

```csv
term,reading,meaning
学生,,studente
日,にち,giorno (nei composti)
こんにちは,,buongiorno
```

- `term` is required, `reading` (kana) and `meaning` are optional; other
  columns (a level, tags) are ignored with a warning — a term's level comes
  from its kanji.
- A word the dictionary reads as one word becomes the same term as in texts
  (食べます → 食べる); anything else is kept whole (お茶, こんにちは, a kana-only
  word). Write words in kanji when they have them, and give the reading
  when the computed one is wrong (火曜日 → かようび).
- The meanings are human ones: they go to new terms and to known terms
  without a meaning or with the AI's, never over one written by hand.

