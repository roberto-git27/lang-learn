// Romaji answers are compared loosely: case, spaces, hyphens, apostrophes and
// periods are ignored, and circumflex long vowels (ô) count as macrons (ō).
// The backend lists the accepted spellings (gakkō / gakkou / gakkoo / gakko).
const CIRCUMFLEX_TO_MACRON = { â: "ā", î: "ī", û: "ū", ê: "ē", ô: "ō" };

function normalizeRomaji(text) {
  return (text || "")
    .normalize("NFC")
    .toLowerCase()
    .replace(/[âîûêô]/g, (c) => CIRCUMFLEX_TO_MACRON[c])
    .replace(/[\s\-'’.]/g, "");
}

export function isAcceptedRomaji(answer, accepted) {
  const normalized = normalizeRomaji(answer);
  return normalized.length > 0 && accepted.some((a) => normalizeRomaji(a) === normalized);
}
