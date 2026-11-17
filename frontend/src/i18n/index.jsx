import { en } from "./en";

// The UI language: English only for now (D-16). A second language would pick
// its table here.
export const ui = en;

/**
 * A UI string with light markup: **bold** and `code`. Keeps the strings in
 * `en.js` plain text while the UI can still emphasize a word.
 */
export function Rich({ text, codeStyle }) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <b key={i}>{part.slice(2, -2)}</b>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} style={codeStyle}>{part.slice(1, -1)}</code>;
    return part;
  });
}
