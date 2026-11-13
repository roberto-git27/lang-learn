// Port of Python's difflib.SequenceMatcher.ratio() — Ratcliff/Obershelp algorithm.

function findLongestMatch(a, b, alo, ahi, blo, bhi) {
  let bestI = alo, bestJ = blo, bestSize = 0;
  let j2len = {};

  for (let i = alo; i < ahi; i++) {
    const next = {};
    for (let j = blo; j < bhi; j++) {
      if (a[i] === b[j]) {
        const k = (j2len[j - 1] ?? 0) + 1;
        next[j] = k;
        if (k > bestSize) {
          bestI = i - k + 1;
          bestJ = j - k + 1;
          bestSize = k;
        }
      }
    }
    j2len = next;
  }
  return [bestI, bestJ, bestSize];
}

function getMatchingBlocks(a, b) {
  const queue = [[0, a.length, 0, b.length]];
  const blocks = [];

  while (queue.length > 0) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = findLongestMatch(a, b, alo, ahi, blo, bhi);
    if (k > 0) {
      blocks.push([i, j, k]);
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }

  return blocks;
}

export function normalize(text) {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

export function similarityRatio(a, b) {
  if (a.length === 0 && b.length === 0) return 1.0;
  if (a.length === 0 || b.length === 0) return 0.0;

  const matches = getMatchingBlocks(a, b).reduce((sum, [, , k]) => sum + k, 0);
  return (2.0 * matches) / (a.length + b.length);
}
