import { ui } from "../i18n";

// Human-readable labels for exercise type codes (see the exercise_types seed).
export function exerciseTypeLabel(code) {
  return ui.exerciseTypes[code] ?? code;
}

// Field holding the text shown before answering, per exercise type.
export const PROMPT_FIELD = {
  multiple_choice: "question",
  fill_blank: "sentence_with_blank",
  translate_rev: "prompt",
  kanji_reading: "sentence",
  kanji_writing: "sentence",
  romaji_input: "sentence",
};

// Types whose sentence translation can be shown before answering without
// giving the answer away (it would for meaning questions and translations).
export const TRANSLATION_BEFORE_ANSWER = new Set(["fill_blank", "kanji_reading", "kanji_writing", "romaji_input"]);
