/**
 * Every UI string of the app, in English (D-16). Components import `ui` from
 * "../i18n" and never hard-code text: a second UI language means a second
 * file with the same shape. Values are strings, or functions when the text
 * embeds numbers or names (plurals included). Strings rendered with `<Rich>`
 * may use **bold** and `code`.
 *
 * Not here: learning content (exercise text, explanations, meanings — data in
 * the track's base language), the Studio's .md format examples (file syntax),
 * and messages coming from the API (English, written by the backend).
 */

const count = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const seconds = (ms) => `${(ms / 1000).toFixed(1)} s`;

export const en = {
  common: {
    loading: "Loading…",
    back: "Back",
    cancel: "Cancel",
    tryAgain: "Try again",
    refresh: "↻ Refresh",
    requestFailed: "Request failed",
    difficulty: (n) => `difficulty ${n}`,
    loadMore: (remaining) => `Show more (${remaining} remaining)`,
  },
  app: {
    nav: { chat: "Chat", practice: "Practice", studio: "Studio", admin: "Admin" },
    backendDown: "Backend not reachable",
    trackSwitchFailed: "Could not switch track",
    reload: "Reload",
    exerciseCount: (n) => count(n, "exercise"),
    trackTitle: "Track you are studying",
    addTrack: "Add a track",
    switchProfile: "Switch profile",
    footer: "LangLearn — Powered by AI",
  },
  practice: {
    title: (track) => `Practice ${track}`,
    titleAccent: "every day.",
    subtitle: "Pick your settings and start a practice session.",
    preparing: "Preparing session…",
    loadFailed: "Failed to load exercises",
  },
  exerciseTypes: {
    multiple_choice: "Multiple choice",
    fill_blank: "Fill in the blank",
    translate_rev: "Translate",
    kanji_reading: "Kanji reading",
    kanji_writing: "Kanji writing",
    romaji_input: "Romaji",
  },
  // Each language in its own language.
  languages: { it: "Italiano", ja: "日本語" },
  session: {
    progress: (current, total) => `Exercise ${current} of ${total}`,
    complete: (pct) => `${pct}% complete`,
  },
  filters: {
    type: "Exercise type",
    allTypes: "All types",
    difficulty: "Difficulty",
    anyDifficulty: "Any",
    start: "Start session →",
    sessionSize: "Each session includes 5–15 random exercises",
  },
  profiles: {
    loadFailed: "Failed to load profiles",
    title: "Who is studying?",
    subtitle: "Profiles keep separate history and tracks. They are not accounts: anyone using this instance can pick one.",
    noTracks: "no tracks",
    newProfile: "+ New profile",
    wrongPin: "Wrong PIN",
    pinCheckFailed: "PIN check failed",
    pinFor: "PIN for",
    enter: "Enter",
    createFailed: "Could not create the profile",
    name: "Name",
    pin: "PIN (optional, 4 digits)",
    tracks: "Tracks",
    create: "Create profile",
  },
  exercise: {
    // Language names in the UI language (the prompt says "Translate into Italian").
    languageNames: { it: "Italian", ja: "Japanese" },
    instructions: {
      multiple_choice: "Choose the correct answer",
      fill_blank: "Fill in the blank",
      kanji_reading: "How is the underlined word read?",
      kanji_writing: "Choose the kanji for the underlined word",
      romaji_input: "Write the underlined word in romaji",
    },
    translateInto: (language) => `Translate into ${language}`,
    furiganaToggle: "Show/hide the readings above kanji",
    showTranslation: "Show translation",
    yourAnswer: "Your answer",
    typeRomaji: "Type in romaji…",
    typeTranslation: "Type the translation…",
    correct: "Correct!",
    wrong: "Not quite",
    correctAnswer: "Correct answer:",
    similarity: (pct) => `similarity: ${pct}%`,
    check: "Check",
    finish: "Finish session →",
    next: "Next exercise →",
    enterToContinue: "Press Enter to continue",
    enterToConfirm: "Press Enter to confirm",
  },
  summary: {
    excellent: "Excellent!",
    great: "Great!",
    good: "Good",
    keepPracticing: "Keep practicing",
    correctOf: (correct, total) => `${correct} of ${total} ${total === 1 ? "exercise correct" : "exercises correct"}`,
    averageSimilarity: (pct) => `average similarity (translations): ${pct}%`,
    byType: "By exercise type",
    mistakes: (n) => `Mistakes to review — ${n}`,
    yourAnswer: "Your answer",
    correctAnswer: "Correct answer",
    newSession: "New session →",
  },
  chat: {
    greeting: "Hi! I'm your language assistant.",
    intro: (track) =>
      `You are practicing ${track}. Tell me your level and maybe a specific topic, ` +
      "and I will prepare a tailored exercise session for you.",
    // "Found <strong>N</strong> exercises for you!"
    found: { before: "Found ", after: (n) => ` ${n === 1 ? "exercise" : "exercises"} for you!` },
    startExercises: "Start exercises →",
    newChat: "+ New chat",
    newChatTitle: "Start over: the current conversation is cleared",
    placeholders: {
      searching: "Looking for exercises…",
      reviewing: "Analyzing your results…",
      ready: "Start the exercises or keep chatting",
      afterSession: 'Ask about a mistake (e.g. "why is #3 wrong?") or ask for more exercises',
      default: "Type a message…",
    },
    hint: "Enter to send · Shift+Enter for a new line",
    networkError: "Network error",
    httpError: (code) => `HTTP error ${code}`,
  },
  admin: {
    title: "Admin",
    subtitle:
      "Review generated exercises, see how many exercises each level has, fix wrong furigana readings and inspect " +
      "every run of the exercise agent. New exercises are written in the Studio.",
    tabs: { review: "Review", coverage: "Coverage", readings: "Readings", agentRuns: "Agent Runs" },
  },
  review: {
    loadFailed: "Failed to load the review queue",
    updateFailed: "Update failed",
    title: "Review queue",
    subtitle: "Exercises already in the DB: mark the good ones as verified — the agent prefers them as style examples for new generations.",
    toReview: "To review",
    verified: "Verified",
    anyType: "Any type",
    anyDifficulty: "Any difficulty",
    empty: "No exercises match these filters.",
    imported: "imported",
    aiGenerated: "AI-generated",
    verifiedBy: (name, date) => `Verified by ${name} on ${date}`,
    notVerified: "Not verified yet",
    unverify: "Remove verification",
    approve: "✓ Approve",
  },
  // Payload fields as shown to reviewers (Admin and Studio previews).
  payload: {
    prompt: "Prompt",
    expected: "Expected answer",
    alternatives: "Accepted alternatives",
    romajiSentence: "Sentence (underlined: word to write in romaji)",
    expectedComputed: "Expected answer (computed)",
    alsoAccepted: "Also accepted",
    question: "Question",
    focusSentence: "Sentence (underlined: the word asked about)",
    options: "Options",
    correct: "✓ correct",
    blankSentence: "Sentence with blank",
  },
  coverage: {
    // Short column headers (the full type label is the tooltip).
    shortTypes: {
      multiple_choice: "MC", fill_blank: "Blank", kanji_reading: "Read", kanji_writing: "Write",
      romaji_input: "Romaji", translate_rev: "Transl.",
    },
    loadFailed: "Failed to load the exercise counts",
    title: "Coverage",
    subtitle: "Exercises per difficulty and type. Sessions use these first and generate only what is missing.",
    exercises: "exercises",
    verified: "verified",
    toReview: "to review",
    level: "Level",
    total: "Total",
    verifiedColumn: "Verified",
    verifiedTitle: "Verified by a human",
    note: (thin) =>
      `Levels with fewer than ${thin} exercises are highlighted: a session there will mostly be generated. ` +
      "Add exercises from the Studio (import or generate).",
  },
  runs: {
    loadFailed: "Failed to load agent runs",
    detailFailed: "Failed to load run details",
    title: "Agent Runs",
    subtitle: "Every run of the exercise selection/generation agent: computed mix, gap, LLM cycles/tokens and outcome.",
    empty: "No runs recorded yet.",
    db: (n) => `db ${n}`,
    gap: (n) => `gap ${n}`,
    created: (n) => `created ${n}`,
    cycles: (n) => `${n} cycles`,
    calls: (n) => `${n} calls`,
    tokens: (n) => `${n} tok`,
    ms: (n) => `${n} ms`,
    requestParams: "Request params",
    composition: "Target composition",
    finalIds: "Final exercise ids",
    trace: "Full trace",
  },
  readings: {
    intro:
      "Furigana and romaji are computed by a dictionary, which sometimes picks the wrong reading (五本 → ごぽん). " +
      "Fix a word here once: the reading is used everywhere in the track, and the exercises that contain the word are " +
      "updated. A word that is part of a longer one is not touched (本 does not change 日本).",
    word: "Word (with kanji)",
    reading: "Reading (kana)",
    save: "Save reading",
    empty: "No reading fixed by hand yet.",
    remove: "Remove",
    removeTitle: "Back to the computed reading",
    saved: (surface, reading, n) => `${surface} is now read ${reading} everywhere. ${count(n, "exercise")} updated.`,
    removed: (surface, n) => `${surface}: back to the computed reading. ${count(n, "exercise")} updated.`,
  },
  studio: {
    title: "Studio",
    subtitle:
      "**Import** exercises you wrote or checked yourself from a `.md` file (no AI, already verified), or " +
      "**generate** new ones with the AI from a request — they are drafted, you keep what you like, and they go to " +
      "the review queue. Verified exercises become the examples the AI imitates. **Vocabulary** extracts the words " +
      "of any text (dictionary forms, never stored twice) and keeps their meanings.",
    modes: { import: "Import .md", generate: "Generate with AI", terms: "Vocabulary" },
    placeholders: {
      import: "Paste a .md of exercises, or open a file.",
      generate: "Write a generation request, or open one (e.g. sample/ja_generate1.md).",
      terms: "Paste any text, or open one (e.g. sample/ja_story1.md): its words are extracted in dictionary form. A .csv term list works too.",
    },
    // What each type needs besides `sentence` and `translation` (full reference: sample/README.md).
    typeNotes: {
      multiple_choice: "question + 4 options",
      fill_blank: "sentence with ___ or 【　】 + 2–6 options",
      translate_rev: "alternative: (repeatable) — other accepted translations",
      kanji_reading: "focus (a kanji word of the sentence) + 4 kana options",
      kanji_writing: "focus (a kana word of the sentence) + 4 kanji options",
      romaji_input: "focus; answer: (optional) is checked against the computed romaji",
    },
    pastedText: "pasted text",
    editedName: (name) => `${name} (edited)`,
    openFile: "Open .md file…",
    openFileTerms: "Open .md / .csv file…",
    nameTitle: "Name kept with the job",
    formatGuide: "Format guide",
    hideFormat: "Hide format",
    preview: "Preview →",
    extractTerms: "Extract terms (no AI) →",
    generate: "Generate with AI →",
    generating: "Generating… this can take a minute",
    draftPending: "Save or discard the current draft first",
    restoreBeforeFix: "↺ Restore the text before the AI fix",
    guide: {
      types: "Exercise types on this track",
      import:
        "One exercise per `## type` block; options are task-list items, exactly one `[x]`; explanation is optional. " +
        "Keys may also be written in Italian (frase, traduzione, domanda, spiegazione, alternativa, risposta, " +
        "difficoltà, argomenti). Text outside a block is ignored; `# comments` only in the front matter. " +
        "Readings (furigana, romaji) are computed, never written.",
      terms:
        "Any text: its content words are extracted in dictionary form (言いました → 言う), without particles or " +
        "auxiliaries, and compared with the vocabulary already stored — the same word is never stored twice (かみ and " +
        "髪 are one term). Headings, comments and the front matter are ignored. No AI: meanings are added below, on request.",
      termListTitle: "Or a term list (.csv)",
      termList:
        "A header row, then one term per line (comma, semicolon or tab). `reading` (kana) and `meaning` are optional; " +
        "Italian headers work too (termine, lettura, significato). A word the dictionary knows becomes the same term " +
        "as in texts (食べます → 食べる); anything else is kept whole (お茶, こんにちは) — give the reading when the " +
        "computed one is wrong. Meanings here are yours: they also fill known terms without one, or with the AI's, " +
        "never one written by hand. Write words in kanji when they have them.",
      generate: (types) =>
        "Everything that is not front matter or a term is sent to the AI as your request. Each exercise is checked " +
        "before it reaches the draft (valid structure, kanji of the level, the term really used); what fails is " +
        `retried once. Types on this track: ${types}. At most 30 exercises per request.`,
    },
    previewTitle: "Preview",
    line: (n) => `line ${n}`,
    importCount: (n) => `Import ${count(n, "exercise")}`,
    errorsSkipped:
      "Blocks with errors are skipped: fix them and import the file again — what is already imported is recognized as a duplicate.",
    fix: "Fix with AI",
    fixing: "Fixing…",
    fixHint:
      "A cheap model rewrites the blocks with errors and any text outside the blocks (e.g. exercises pasted from a " +
      "workbook) in this format, copying the content without inventing it. Valid blocks and the front matter are not " +
      "sent. The result goes back to the editor: check it, then Preview again.",
    fixed: (res) => {
      const skipped = res.skipped.map((s) => `line ${s.line}: ${s.reason}`).join("; ");
      return (
        `The AI rewrote ${res.rewritten_segments} of ${count(res.sent_segments, "part")} as ` +
        `${count(res.exercise_count, "exercise")} (${res.model}, ${res.input_tokens + res.output_tokens} tokens, ` +
        `${seconds(res.duration_ms)}). Content is copied, not invented: compare each block with its <!-- source --> ` +
        "line, fill in what is missing, then Preview." +
        (skipped ? ` Left as they were — ${skipped}.` : "")
      );
    },
    imported: (n, source) => `Imported ${count(n, "exercise")} from ${source}: verified and available in Practice and Chat.`,
    termsSaved: (job) =>
      `Saved ${count(job.created_count, "new term")} from ${job.source_name}` +
      (job.duplicate_count ? ` (${job.duplicate_count} already known)` : "") + "." +
      (job.meaning_updates ? ` ${count(job.meaning_updates, "known term")} got the list's meaning.` : "") +
      ' Missing meanings: "Translate missing meanings" below, or write them by hand.',
    draftSaved: (n) => `Saved ${count(n, "generated exercise")}: they are in Admin → Review, waiting for approval.`,
    draftInEditor:
      "The draft is now in the import editor: fix what you want, then Preview and Import (as verified exercises). " +
      "Discard the draft if you no longer need it.",
    draftTitle: (name) => `Draft — ${name}`,
    regenerateOpen: "↻ Write this one again with AI",
    regenerateNote: "What to change (optional), e.g. a more natural sentence",
    regenerate: "Write it again",
    saveDraft: (n) => `Save ${count(n, "exercise")} to the review queue`,
    editAsMarkdown: "Edit as .md and import by hand",
    discard: "Discard the draft",
    keepTitle: "Keep this exercise",
    counts: {
      ready: (n) => `${n} ready`,
      duplicate: (n) => `${n} duplicate`,
      error: (n) => `${n} with errors`,
    },
    status: { ready: "ready", duplicate: "duplicate", error: "error" },
  },
  vocabulary: {
    pos: {
      noun: "noun", proper_noun: "name", pronoun: "pronoun", verb: "verb", i_adjective: "い-adj",
      na_adjective: "な-adj", adverb: "adverb", prenominal: "prenominal", numeral: "numeral", expression: "expression",
    },
    level: (n) => (n >= 3 ? "level 3+" : `level ${n}`),
    inText: "Terms in the text",
    inList: "Terms in the list",
    counts: {
      new: (n) => `${n} new`,
      known: (n) => `${n} already known`,
      meanings: (n) => `${count(n, "meaning")} to add`,
    },
    newTerms: (n) => count(n, "new term"),
    meanings: (n) => count(n, "meaning"),
    save: (what) => `Save ${what}`,
    title: "Vocabulary of the track",
    totals: (total, filtered, missing) =>
      `${count(total, "term")}${filtered ? " matching" : ""} · ${missing} without a meaning.`,
    autoLink: "Every new exercise is linked to its terms automatically.",
    translate: (n) => `Translate missing meanings with AI (${n})`,
    translated: (r) =>
      `${count(r.translated, "meaning")} added by ${r.model} · ${r.input_tokens + r.output_tokens} tokens · ${seconds(r.duration_ms)}`,
    sync: "Link existing exercises",
    synced: (linked, created) => `${count(linked, "exercise")} linked to their terms · ${count(created, "new term")}.`,
    search: "Search (word, reading, meaning)",
    missingOnly: "without a meaning",
    exercisesTitle: "Exercises using this term",
    exerciseCount: (n) => `${n} ex.`,
    deleteTitle: "Delete this term",
    confirmDelete: (word) => `Delete the term ${word} and its links to exercises?`,
    deleteFailed: "Delete failed",
    deleted: (word) => `${word} deleted.`,
    meaningPlaceholder: "meaning",
    source: { ai: "AI", human: "you" },
  },
  jobs: {
    title: "Past imports and generations",
    subtitle: "Every job keeps its source file, so each exercise can be traced back to it.",
    empty: "Nothing yet on this track.",
    kinds: { import: "import", generate: "AI", terms: "vocabulary" },
    status: { saved: "saved", draft: "draft", discarded: "discarded" },
    showSource: "Show source",
    hideSource: "Hide source",
    load: "Load into the editor",
    openDraft: "Open draft",
  },
};
