import { useEffect, useRef, useState } from "react";
import { identityHeaders } from "../utils/identity";
import { exerciseTypeLabel } from "../utils/exerciseTypes";
import {
  ErrorBox, Spinner, btnHover, labelStyle, inputStyle, diffBadgeStyle, tagStyle, submitButtonStyle,
  ExTypeBadge, PayloadDisplay,
} from "./admin/_shared";

// What each type needs besides `sentence` and `translation` (full reference: sample/README.md).
const TYPE_NOTES = {
  multiple_choice: "question + 4 options",
  fill_blank: "sentence with ___ or 【　】 + 2–6 options",
  translate_rev: "alternative: (repeatable) — other accepted translations",
  kanji_reading: "focus (a kanji word of the sentence) + 4 kana options",
  kanji_writing: "focus (a kana word of the sentence) + 4 kanji options",
  romaji_input: "focus; answer: (optional) is checked against the computed romaji",
};

const IMPORT_EXAMPLE = `---
difficulty: 1              # default for every block (1–10)
topics: school, family     # optional
---

## kanji_reading
sentence: わたしは 学生です。
translation: Sono uno studente.
focus: 学生
- [x] がくせい
- [ ] がっせい
- [ ] がくせ
- [ ] かくせい
explanation: Niente っ piccola.`;

const GENERATE_EXAMPLE = `---
mode: generate
difficulty: 1                          # required (1–10)
per_term: 3                            # exercises per term (1–6)
types: kanji_reading, kanji_writing    # optional: default = option-based types
topics: numbers_counters               # optional
examples: 3                            # verified exercises shown to the AI per type (0–5)
---

Free text: what you want, in your own words.
Without terms, set "count: N" for N exercises.

## terms
- 一 uno
- 火 fuoco; 火よう日 = martedì`;

const TERMS_EXAMPLE = `---
mode: terms
---

# Any text: a chapter, a dialogue, a list of sentences

今日は 土曜日です。あさから 雨が ふっています。
A：雨は いつ やみますか。
B：午後三時ごろ やみます。`;

const TERM_LIST_EXAMPLE = `term,reading,meaning
学生,,studente
日,にち,giorno (nei composti)
こんにちは,,buongiorno`;

const MODES = {
  import: { label: "Import .md", example: IMPORT_EXAMPLE },
  generate: { label: "Generate with AI", example: GENERATE_EXAMPLE },
  terms: { label: "Vocabulary", example: TERMS_EXAMPLE },
};

const PLACEHOLDERS = {
  import: "Paste a .md of exercises, or open a file.\n\n",
  generate: "Write a generation request, or open one (e.g. sample/ja_generate1.md).\n\n",
  terms: "Paste any text, or open one (e.g. sample/ja_story1.md): its words are extracted in dictionary form. A .csv term list works too.\n\n",
};

const FRONT_MATTER_MODE = /^---\s*\n(?:.*\n)*?mode:\s*(import|generate|terms)\b.*\n(?:.*\n)*?---/;

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.[0]?.msg || "Request failed");
  return data;
}

const postJson = (url, body) => requestJson(url, {
  method: "POST",
  headers: { "Content-Type": "application/json", ...identityHeaders() },
  body: JSON.stringify(body),
});

export function StudioPage({ track }) {
  const [mode, setMode] = useState("import");
  const [sources, setSources] = useState(() => Object.fromEntries(Object.keys(MODES).map((m) => [m, { text: "", name: "pasted text" }])));
  const [showFormat, setShowFormat] = useState(false);

  const [preview, setPreview] = useState(null);   // import preview
  const [draft, setDraft] = useState(null);       // generation draft (job detail)
  const [termsPreview, setTermsPreview] = useState(null);
  const [vocabularyVersion, setVocabularyVersion] = useState(0);
  const [busy, setBusy] = useState(null);         // "preview" | "import" | "generate" | "save" | "discard"
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [beforeFix, setBeforeFix] = useState(null); // import text before the last AI fix, to restore it
  const fileInput = useRef(null);

  const source = sources[mode];

  // Any edit makes the import preview stale: it must show exactly what will be imported.
  const setSource = (targetMode, changes) => {
    setSources((prev) => ({ ...prev, [targetMode]: { ...prev[targetMode], ...changes } }));
    if (targetMode === "import" && "text" in changes) setPreview(null);
    if (targetMode === "terms" && "text" in changes) setTermsPreview(null);
    setNotice(null);
  };

  const switchMode = (next) => { setMode(next); setError(null); setNotice(null); };

  const loadText = (text, name, detectedMode) => {
    const target = detectedMode ?? text.match(FRONT_MATTER_MODE)?.[1] ?? mode;
    setSource(target, { text, name });
    switchMode(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) loadText(await file.text(), file.name, /\.(csv|tsv)$/i.test(file.name) ? "terms" : undefined);
  };

  const run = async (label, action) => {
    setBusy(label); setError(null); setNotice(null);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const body = () => ({ track: track.code, text: source.text, source_name: source.name.trim() || "pasted text" });

  const handlePreview = () => run("preview", async () => setPreview(await postJson("/api/studio/imports/preview", body())));

  const handleFix = () => run("fix", async () => {
    const original = source.text;
    const res = await postJson("/api/studio/imports/normalize", body());
    setSource("import", { text: res.text });
    setBeforeFix(original);
    const skipped = res.skipped.map((s) => `line ${s.line}: ${s.reason}`).join("; ");
    setNotice(
      `The AI rewrote ${res.rewritten_segments} of ${res.sent_segments} part${res.sent_segments === 1 ? "" : "s"} as ` +
      `${res.exercise_count} exercise${res.exercise_count === 1 ? "" : "s"} (${res.model}, ` +
      `${res.input_tokens + res.output_tokens} tokens, ${(res.duration_ms / 1000).toFixed(1)} s). ` +
      "Content is copied, not invented: compare each block with its <!-- source --> line, fill in what is missing, then Preview." +
      (skipped ? ` Left as they were — ${skipped}.` : ""),
    );
  });

  const restoreBeforeFix = () => {
    setSource("import", { text: beforeFix });
    setBeforeFix(null);
  };

  const handleImport = () => run("import", async () => {
    const job = await postJson("/api/studio/imports", body());
    setPreview(null);
    setBeforeFix(null);
    setNotice(`Imported ${job.created_count} exercise${job.created_count === 1 ? "" : "s"} from ${job.source_name}: verified and available in Practice and Chat.`);
    setHistoryVersion((v) => v + 1);
  });

  const handleExtractTerms = () => run("extract", async () => setTermsPreview(await postJson("/api/studio/terms/preview", body())));

  const handleSaveTerms = () => run("saveTerms", async () => {
    const job = await postJson("/api/studio/terms", body());
    setTermsPreview(null);
    const updates = job.meaning_updates ? ` ${job.meaning_updates} known term${job.meaning_updates === 1 ? "" : "s"} got the list's meaning.` : "";
    setNotice(`Saved ${job.created_count} new term${job.created_count === 1 ? "" : "s"} from ${job.source_name}${job.duplicate_count ? ` (${job.duplicate_count} already known)` : ""}.${updates} Missing meanings: "Translate missing meanings" below, or write them by hand.`);
    setHistoryVersion((v) => v + 1);
    setVocabularyVersion((v) => v + 1);
  });

  const handleGenerate = () => run("generate", async () => {
    setDraft(await postJson("/api/studio/generations", body()));
    setHistoryVersion((v) => v + 1);
  });

  const handleSave = (keep) => run("save", async () => {
    const job = await postJson(`/api/studio/generations/${draft.id}/save`, { track: track.code, keep });
    setDraft(null);
    setNotice(`Saved ${job.created_count} generated exercise${job.created_count === 1 ? "" : "s"}: they are in Admin → Review, waiting for approval.`);
    setHistoryVersion((v) => v + 1);
  });

  const handleDiscard = () => run("discard", async () => {
    await postJson(`/api/studio/generations/${draft.id}/discard?track=${encodeURIComponent(track.code)}`, {});
    setDraft(null);
    setHistoryVersion((v) => v + 1);
  });

  const editAsMarkdown = () => {
    loadText(draft.markdown, `${draft.source_name} (edited)`, "import");
    setNotice("The draft is now in the import editor: fix what you want, then Preview and Import (as verified exercises). Discard the draft if you no longer need it.");
  };

  const openDraft = (job) => { setDraft(job); switchMode("generate"); };

  const canRun = source.text.trim() && !busy;

  return (
    <div style={wrapStyle}>
      <div style={{ marginBottom: "28px" }}>
        <h1 style={pageTitle}>Studio</h1>
        <p style={pageSubtitle}>
          <b>Import</b> exercises you wrote or checked yourself from a <code>.md</code> file (no AI, already verified), or
          <b> generate</b> new ones with the AI from a request — they are drafted, you keep what you like, and they
          go to the review queue. Verified exercises become the examples the AI imitates. <b>Vocabulary</b> extracts the
          words of any text (dictionary forms, never stored twice) and keeps their meanings.
        </p>
      </div>

      <div style={modeBar}>
        {Object.entries(MODES).map(([id, { label }]) => (
          <button key={id} onClick={() => switchMode(id)} style={modeTab(mode === id)}>{label}</button>
        ))}
      </div>

      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", marginBottom: "14px" }}>
          <button onClick={() => fileInput.current?.click()} style={secondaryBtn}>{mode === "terms" ? "Open .md / .csv file…" : "Open .md file…"}</button>
          <input ref={fileInput} type="file" accept=".md,.markdown,.txt,.csv,.tsv,text/markdown,text/plain,text/csv" onChange={openFile} style={{ display: "none" }} />
          <input
            value={source.name} onChange={(e) => setSource(mode, { name: e.target.value })} maxLength={255}
            title="Name kept with the job" style={{ ...inputStyle, flex: 1, minWidth: "160px", padding: "7px 11px", fontSize: "13px" }}
          />
          <button onClick={() => setShowFormat((v) => !v)} style={linkBtn}>{showFormat ? "Hide format" : "Format guide"}</button>
        </div>

        {showFormat && <FormatGuide mode={mode} track={track} />}

        <textarea
          value={source.text} onChange={(e) => setSource(mode, { text: e.target.value })} spellCheck={false}
          placeholder={PLACEHOLDERS[mode] + MODES[mode].example}
          style={textareaStyle}
        />

        {error && <div style={{ marginTop: "14px" }}><ErrorBox message={error} /></div>}

        {mode === "import" && (
          <button onClick={handlePreview} disabled={!canRun} style={{ ...submitButtonStyle(!canRun), marginTop: "14px" }}>
            {busy === "preview" ? <Spinner /> : "Preview →"}
          </button>
        )}
        {mode === "terms" && (
          <button onClick={handleExtractTerms} disabled={!canRun} style={{ ...submitButtonStyle(!canRun), marginTop: "14px" }}>
            {busy === "extract" ? <Spinner /> : "Extract terms (no AI) →"}
          </button>
        )}
        {mode === "generate" && (
          <button onClick={handleGenerate} disabled={!canRun || !!draft} style={{ ...submitButtonStyle(!canRun || !!draft), marginTop: "14px" }}>
            {busy === "generate" ? <><Spinner /> Generating… this can take a minute</> : draft ? "Save or discard the current draft first" : "Generate with AI →"}
          </button>
        )}

        {notice && <p style={successBox}>✓ {notice}</p>}
        {mode === "import" && beforeFix !== null && (
          <button onClick={restoreBeforeFix} disabled={!!busy} style={{ ...linkBtn, marginTop: "10px" }}>
            ↺ Restore the text before the AI fix
          </button>
        )}
      </div>

      {mode === "import" && preview && <ImportPreview preview={preview} busy={busy} onImport={handleImport} onFix={handleFix} />}
      {mode === "terms" && termsPreview && <TermsPreview preview={termsPreview} busy={busy} onSave={handleSaveTerms} />}
      {mode === "terms" && <Vocabulary track={track} version={vocabularyVersion} />}
      {mode === "generate" && draft && (
        <GenerationDraft key={draft.id} draft={draft} busy={busy} onSave={handleSave} onDiscard={handleDiscard} onEdit={editAsMarkdown} />
      )}

      <JobHistory track={track} version={historyVersion} onLoadSource={loadText} onOpenDraft={openDraft} />

      <style>{btnHover}</style>
    </div>
  );
}

/* ── Format guide ───────────────────────────────────────────── */

function FormatGuide({ mode, track }) {
  return (
    <div style={formatBox}>
      <pre style={preStyle}>{MODES[mode].example}</pre>
      {mode === "import" ? (
        <>
          <p style={{ ...labelStyle, margin: "14px 0 6px" }}>Exercise types on this track</p>
          <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "4px" }}>
            {track.exercise_types.map(({ code }) => (
              <li key={code} style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                <code style={codeStyle}>## {code}</code> {TYPE_NOTES[code] ?? ""}
              </li>
            ))}
          </ul>
          <p style={guideNote}>
            One exercise per <code style={codeStyle}>## type</code> block; options are task-list items, exactly one <code style={codeStyle}>[x]</code>;
            explanation is optional. Keys may also be written in Italian (frase, traduzione, domanda, spiegazione, alternativa, risposta,
            difficoltà, argomenti). Text outside a block is ignored; <code style={codeStyle}># comments</code> only in the front matter.
            Readings (furigana, romaji) are computed, never written.
          </p>
        </>
      ) : mode === "terms" ? (
        <>
          <p style={guideNote}>
            Any text: its content words are extracted in dictionary form (言いました → 言う), without particles or auxiliaries,
            and compared with the vocabulary already stored — the same word is never stored twice (かみ and 髪 are one term).
            Headings, comments and the front matter are ignored. No AI: meanings are added below, on request.
          </p>
          <p style={{ ...labelStyle, margin: "14px 0 6px" }}>Or a term list (.csv)</p>
          <pre style={preStyle}>{TERM_LIST_EXAMPLE}</pre>
          <p style={guideNote}>
            A header row, then one term per line (comma, semicolon or tab). <code style={codeStyle}>reading</code> (kana) and{" "}
            <code style={codeStyle}>meaning</code> are optional; Italian headers work too (termine, lettura, significato).
            A word the dictionary knows becomes the same term as in texts (食べます → 食べる); anything else is kept whole
            (お茶, こんにちは) — give the reading when the computed one is wrong. Meanings here are yours: they also fill
            known terms without one, or with the AI's, never one written by hand. Write words in kanji when they have them.
          </p>
        </>
      ) : (
        <p style={guideNote}>
          Everything that is not front matter or a term is sent to the AI as your request. Each exercise is checked before it
          reaches the draft (valid structure, kanji of the level, the term really used); what fails is retried once.
          Types on this track: {track.exercise_types.map(({ code }) => code).join(", ")}. At most 30 exercises per request.
        </p>
      )}
    </div>
  );
}

/* ── Import preview ─────────────────────────────────────────── */

function ImportPreview({ preview, busy, onImport, onFix }) {
  // Invalid blocks, or no block at all (e.g. text pasted from a workbook): the cheap model can map it to the format.
  const fixable = preview.error_count > 0 || preview.items.length === 0;
  const blocked = preview.errors.length > 0 || preview.ready_count === 0 || !!busy;
  return (
    <div style={{ ...cardStyle, marginTop: "16px", animation: "fadeSlideIn 0.3s ease forwards" }}>
      <h3 style={sectionTitle}>Preview</h3>
      {preview.errors.map((e) => <ErrorBox key={e} message={e} />)}
      {preview.items.length > 0 && <Counts items={preview.items} />}

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {preview.items.map((item) => <PreviewItem key={item.line} item={item} label={`line ${item.line}`} />)}
      </div>

      <button onClick={onImport} disabled={blocked} style={{ ...submitButtonStyle(blocked), marginTop: "18px" }}>
        {busy === "import" ? <Spinner /> : `Import ${preview.ready_count} exercise${preview.ready_count === 1 ? "" : "s"}`}
      </button>
      {preview.error_count > 0 && preview.ready_count > 0 && (
        <p style={hintText}>
          Blocks with errors are skipped: fix them and import the file again — what is already imported is recognized as a duplicate.
        </p>
      )}
      {fixable && (
        <div style={{ marginTop: "14px" }}>
          <button onClick={onFix} disabled={!!busy} style={secondaryBtn}>
            {busy === "fix" ? <><Spinner /> Fixing…</> : "Fix with AI"}
          </button>
          <p style={hintText}>
            A cheap model rewrites the blocks with errors and any text outside the blocks (e.g. exercises pasted from a
            workbook) in this format, copying the content without inventing it. Valid blocks and the front matter are
            not sent. The result goes back to the editor: check it, then Preview again.
          </p>
        </div>
      )}
    </div>
  );
}

/* ── Generation draft ───────────────────────────────────────── */

function GenerationDraft({ draft, busy, onSave, onDiscard, onEdit }) {
  const [kept, setKept] = useState(() => new Set(draft.items.flatMap((item, i) => (item.status === "ready" ? [i] : []))));
  const toggle = (i) => setKept((prev) => {
    const next = new Set(prev);
    if (next.has(i)) next.delete(i); else next.add(i);
    return next;
  });
  const blocked = kept.size === 0 || !!busy;

  return (
    <div style={{ ...cardStyle, marginTop: "16px", animation: "fadeSlideIn 0.3s ease forwards" }}>
      <h3 style={sectionTitle}>Draft — {draft.source_name}</h3>
      <p style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>
        {draft.model} · {draft.llm_calls} call{draft.llm_calls === 1 ? "" : "s"} · {draft.input_tokens + draft.output_tokens} tokens
        ({draft.input_tokens} in, {draft.output_tokens} out) · {(draft.duration_ms / 1000).toFixed(1)} s
      </p>
      <Counts items={draft.items} />

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {draft.items.map((item, i) => (
          <PreviewItem
            key={i} item={item} label={`#${item.line}`}
            selectable={item.status === "ready"} selected={kept.has(i)} onToggle={() => toggle(i)}
          />
        ))}
      </div>

      <button onClick={() => onSave([...kept])} disabled={blocked} style={{ ...submitButtonStyle(blocked), marginTop: "18px" }}>
        {busy === "save" ? <Spinner /> : `Save ${kept.size} exercise${kept.size === 1 ? "" : "s"} to the review queue`}
      </button>
      <div style={{ display: "flex", justifyContent: "center", gap: "18px", marginTop: "12px" }}>
        {draft.markdown && <button onClick={onEdit} disabled={!!busy} style={linkBtn}>Edit as .md and import by hand</button>}
        <button onClick={onDiscard} disabled={!!busy} style={{ ...linkBtn, color: "var(--error)" }}>Discard the draft</button>
      </div>
    </div>
  );
}

/* ── Shared item rendering ──────────────────────────────────── */

function Counts({ items }) {
  const count = (status) => items.filter((it) => it.status === status).length;
  return (
    <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "10px 0 16px" }}>
      <span style={countChip("ready")}>{count("ready")} ready</span>
      <span style={countChip("duplicate")}>{count("duplicate")} duplicate</span>
      <span style={countChip("error")}>{count("error")} with errors</span>
    </div>
  );
}

function PreviewItem({ item, label, selectable = false, selected = false, onToggle }) {
  const dimmed = item.status === "duplicate" || (selectable && !selected);
  return (
    <div style={itemCard(item.status, dimmed)}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: item.payload ? "10px" : "6px" }}>
        {selectable && <input type="checkbox" checked={selected} onChange={onToggle} title="Keep this exercise" style={{ accentColor: "var(--accent)" }} />}
        <span style={countChip(item.status)}>{item.status}</span>
        <span style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{label}</span>
        {item.payload ? <ExTypeBadge code={item.exercise_type} /> : <span style={tagStyle}>{exerciseTypeLabel(item.exercise_type)}</span>}
        {item.term && <span style={termChip}>{item.term}</span>}
        {item.difficulty && <span style={diffBadgeStyle}>difficulty {item.difficulty}</span>}
        {item.topics.map((t) => <span key={t} style={tagStyle}>{t}</span>)}
      </div>

      {item.errors.map((e) => <p key={e} style={messageStyle("var(--error)")}>✕ {e}</p>)}
      {item.warnings.map((w) => <p key={w} style={messageStyle("#f59e0b")}>! {w}</p>)}

      {item.payload && (
        <>
          <div style={phraseBox}>
            <div style={{ fontSize: "14px", color: "var(--text-primary)", fontWeight: 500 }}>{item.phrase_target}</div>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>{item.phrase_base}</div>
          </div>
          <PayloadDisplay type={item.exercise_type} payload={item.payload} annotations={item.annotations} />
        </>
      )}
    </div>
  );
}

/* ── Vocabulary ─────────────────────────────────────────────── */

const POS_LABELS = {
  noun: "noun", proper_noun: "name", pronoun: "pronoun", verb: "verb", i_adjective: "い-adj",
  na_adjective: "な-adj", adverb: "adverb", prenominal: "prenominal", numeral: "numeral", expression: "expression",
};

function TermsPreview({ preview, busy, onSave }) {
  const updates = preview.meaning_updates ?? 0;
  const blocked = preview.errors.length > 0 || (preview.new_count === 0 && updates === 0) || !!busy;
  const label = [
    preview.new_count ? `${preview.new_count} new term${preview.new_count === 1 ? "" : "s"}` : "",
    updates ? `${updates} meaning${updates === 1 ? "" : "s"}` : "",
  ].filter(Boolean).join(" + ") || "0 new terms";
  return (
    <div style={{ ...cardStyle, marginTop: "16px", animation: "fadeSlideIn 0.3s ease forwards" }}>
      <h3 style={sectionTitle}>{preview.items.some((t) => t.line) ? "Terms in the list" : "Terms in the text"}</h3>
      {preview.errors.map((e) => <ErrorBox key={e} message={e} />)}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "10px 0 16px" }}>
        <span style={countChip("ready")}>{preview.new_count} new</span>
        <span style={countChip("duplicate")}>{preview.existing_count} already known</span>
        {updates > 0 && <span style={countChip("ready")}>{updates} meaning{updates === 1 ? "" : "s"} to add</span>}
      </div>
      {(preview.warnings ?? []).length > 0 && (
        <ul style={{ margin: "0 0 14px 18px", fontSize: "12px", color: "var(--text-secondary)" }}>
          {preview.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {preview.items.map((term) => (
          <div key={`${term.lemma}|${term.reading}`} style={{ ...termRow, opacity: term.status === "existing" && !term.new_meaning ? 0.55 : 1 }}>
            <TermHead term={term} />
            <span style={{ fontSize: "12px", color: "var(--text-secondary)", flex: 1, minWidth: "120px" }}>
              {term.new_meaning ? <>{term.meaning ? <s>{term.meaning}</s> : null} → {term.new_meaning}</> : term.meaning ?? ""}
            </span>
            {term.example && <span title={term.example} style={exampleText}>{term.example}</span>}
          </div>
        ))}
      </div>
      <button onClick={onSave} disabled={blocked} style={{ ...submitButtonStyle(blocked), marginTop: "18px" }}>
        {busy === "saveTerms" ? <Spinner /> : `Save ${label}`}
      </button>
    </div>
  );
}

function TermHead({ term }) {
  return (
    <>
      <span style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary)", minWidth: "84px" }}>{term.written}</span>
      <span style={{ fontSize: "12px", color: "var(--text-secondary)", minWidth: "90px" }}>{term.reading !== term.written ? term.reading : ""}</span>
      <span style={tagStyle}>{POS_LABELS[term.pos] ?? term.pos}</span>
      <span style={diffBadgeStyle}>{term.level >= 3 ? "level 3+" : `level ${term.level}`}</span>
    </>
  );
}

const VOCABULARY_LIMIT = 50;

function Vocabulary({ track, version }) {
  const [query, setQuery] = useState("");
  const [missingOnly, setMissingOnly] = useState(false);
  const [data, setData] = useState(null);
  const [limit, setLimit] = useState(VOCABULARY_LIMIT);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams({ track: track.code, limit: String(limit), missing_meaning: String(missingOnly) });
    if (query.trim()) params.set("q", query.trim());
    requestJson(`/api/terms?${params}`).then(setData).catch((err) => setError(err.message));
  }, [track.code, query, missingOnly, limit, version, reload]);

  const act = async (label, action) => {
    setBusy(label); setError(null); setNotice(null);
    try {
      setNotice(await action());
      setReload((n) => n + 1);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const translate = () => act("translate", async () => {
    const r = await postJson("/api/terms/meanings", { track: track.code, limit: 60 });
    return `${r.translated} meaning${r.translated === 1 ? "" : "s"} added by ${r.model} · ${r.input_tokens + r.output_tokens} tokens · ${(r.duration_ms / 1000).toFixed(1)} s`;
  });

  const sync = () => act("sync", async () => {
    const r = await postJson(`/api/terms/sync?track=${encodeURIComponent(track.code)}`, {});
    return `${r.exercises_linked} exercise${r.exercises_linked === 1 ? "" : "s"} linked to their terms · ${r.terms_created} new term${r.terms_created === 1 ? "" : "s"}.`;
  });

  const saveMeaning = (term, meaning) => act(null, async () => {
    await requestJson(`/api/terms/${term.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json", ...identityHeaders() },
      body: JSON.stringify({ track: track.code, meaning }),
    });
    return null;
  });

  const remove = (term) => {
    if (!window.confirm(`Delete the term ${term.written} and its links to exercises?`)) return;
    act(null, async () => {
      const res = await fetch(`/api/terms/${term.id}?track=${encodeURIComponent(track.code)}`, { method: "DELETE", headers: identityHeaders() });
      if (!res.ok) throw new Error((await res.json()).detail || "Delete failed");
      return `${term.written} deleted.`;
    });
  };

  return (
    <div style={{ ...cardStyle, marginTop: "16px" }}>
      <h3 style={sectionTitle}>Vocabulary of the track</h3>
      <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "14px" }}>
        {data ? `${data.total} term${data.total === 1 ? "" : "s"}${missingOnly || query ? " matching" : ""} · ${data.missing_meanings} without a meaning` : "Loading…"}.
        Every new exercise is linked to its terms automatically.
      </p>

      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "12px" }}>
        <button onClick={translate} disabled={!!busy || !data?.missing_meanings} style={secondaryBtn}>
          {busy === "translate" ? <Spinner /> : `Translate missing meanings with AI (${Math.min(60, data?.missing_meanings ?? 0)})`}
        </button>
        <button onClick={sync} disabled={!!busy} style={secondaryBtn}>{busy === "sync" ? <Spinner /> : "Link existing exercises"}</button>
      </div>
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center", marginBottom: "14px" }}>
        <input value={query} onChange={(e) => { setQuery(e.target.value); setLimit(VOCABULARY_LIMIT); }} placeholder="Search (word, reading, meaning)"
          style={{ ...inputStyle, flex: 1, minWidth: "180px", padding: "7px 11px", fontSize: "13px" }} />
        <label style={{ fontSize: "12px", color: "var(--text-secondary)", display: "flex", gap: "6px", alignItems: "center" }}>
          <input type="checkbox" checked={missingOnly} onChange={(e) => { setMissingOnly(e.target.checked); setLimit(VOCABULARY_LIMIT); }} style={{ accentColor: "var(--accent)" }} />
          without a meaning
        </label>
      </div>

      {error && <ErrorBox message={error} />}
      {notice && <p style={{ ...successBox, marginTop: 0, marginBottom: "12px" }}>✓ {notice}</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {data?.items.map((term) => (
          <div key={term.id} style={termRow}>
            <TermHead term={term} />
            <MeaningInput term={term} onSave={saveMeaning} />
            <span title="Exercises using this term" style={{ fontSize: "11px", color: "var(--text-muted)" }}>{term.exercise_count} ex.</span>
            <button onClick={() => remove(term)} title="Delete this term" style={{ ...linkBtn, color: "var(--error)" }}>✕</button>
          </div>
        ))}
      </div>
      {data && data.items.length < data.total && (
        <button onClick={() => setLimit((n) => n + VOCABULARY_LIMIT)} style={{ ...secondaryBtn, width: "100%", marginTop: "12px" }}>
          Show more ({data.total - data.items.length} remaining)
        </button>
      )}
    </div>
  );
}

function MeaningInput({ term, onSave }) {
  const [value, setValue] = useState(term.meaning ?? "");
  useEffect(() => setValue(term.meaning ?? ""), [term.meaning]);
  const commit = () => { if (value.trim() !== (term.meaning ?? "")) onSave(term, value.trim()); };
  return (
    <span style={{ display: "flex", alignItems: "center", gap: "6px", flex: 1, minWidth: "160px" }}>
      <input
        value={value} onChange={(e) => setValue(e.target.value)} onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
        placeholder="meaning" title={term.example ?? ""}
        style={{ ...inputStyle, padding: "5px 9px", fontSize: "13px" }}
      />
      {term.meaning_source && <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>{term.meaning_source === "ai" ? "AI" : "you"}</span>}
    </span>
  );
}

/* ── Job history ────────────────────────────────────────────── */

const JOB_STATUS = { saved: "ready", draft: "history", discarded: "duplicate" };
const JOB_KINDS = { import: "import", generate: "AI", terms: "vocabulary" };

function JobHistory({ track, version, onLoadSource, onOpenDraft }) {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const [openJob, setOpenJob] = useState(null); // detail with source_text

  useEffect(() => {
    requestJson(`/api/studio/jobs?track=${encodeURIComponent(track.code)}`)
      .then(setJobs)
      .catch((err) => setError(err.message));
  }, [track.code, version]);

  const loadDetail = (job) => requestJson(`/api/studio/jobs/${job.id}?track=${encodeURIComponent(track.code)}`);

  const toggleSource = async (job) => {
    if (openJob?.id === job.id) { setOpenJob(null); return; }
    try {
      setOpenJob(await loadDetail(job));
    } catch (err) {
      setError(err.message);
    }
  };

  const openDraft = async (job) => {
    try {
      onOpenDraft(await loadDetail(job));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ ...cardStyle, marginTop: "16px" }}>
      <h3 style={sectionTitle}>Past imports and generations</h3>
      <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "14px" }}>
        Every job keeps its source file, so each exercise can be traced back to it.
      </p>
      {error && <ErrorBox message={error} />}
      {jobs?.length === 0 && <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>Nothing yet on this track.</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {jobs?.map((job) => (
          <div key={job.id} style={itemCard("history")}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span style={tagStyle}>{JOB_KINDS[job.kind]}</span>
              <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)" }}>{job.source_name}</span>
              <span style={countChip(JOB_STATUS[job.status])}>{job.status === "saved" ? `+${job.created_count}` : job.status}</span>
              {job.kind === "generate" && <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>{job.input_tokens + job.output_tokens} tok</span>}
              <span style={{ marginLeft: "auto", fontSize: "11px", color: "var(--text-muted)" }}>
                {new Date(job.created_at).toLocaleString()}{job.user_display_name ? ` · ${job.user_display_name}` : ""}
              </span>
            </div>
            <div style={{ display: "flex", gap: "14px", marginTop: "8px" }}>
              <button onClick={() => toggleSource(job)} style={linkBtn}>{openJob?.id === job.id ? "Hide source" : "Show source"}</button>
              {openJob?.id === job.id && (
                <button onClick={() => onLoadSource(openJob.source_text, openJob.source_name, openJob.kind)} style={linkBtn}>Load into the editor</button>
              )}
              {job.status === "draft" && <button onClick={() => openDraft(job)} style={linkBtn}>Open draft</button>}
            </div>
            {openJob?.id === job.id && <pre style={{ ...preStyle, marginTop: "8px", maxHeight: "320px", overflow: "auto" }}>{openJob.source_text}</pre>}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Styles ─────────────────────────────────── */

const STATUS_COLORS = {
  ready: ["var(--success)", "var(--success-bg)", "var(--success-border)"],
  duplicate: ["var(--text-secondary)", "rgba(255,255,255,0.04)", "var(--border)"],
  error: ["var(--error)", "var(--error-bg)", "var(--error-border)"],
  history: ["var(--accent-light)", "rgba(99,102,241,0.1)", "rgba(99,102,241,0.25)"],
};

const countChip = (status) => {
  const [color, background, border] = STATUS_COLORS[status];
  return { padding: "3px 10px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, color, background, border: `1px solid ${border}` };
};

const itemCard = (status, dimmed = false) => ({
  background: "rgba(255,255,255,0.02)",
  border: `1px solid ${status === "error" ? "var(--error-border)" : "var(--border)"}`,
  borderRadius: "var(--radius-sm)",
  padding: "14px 16px",
  opacity: dimmed ? 0.55 : 1,
});

const modeTab = (active) => ({
  flex: 1, padding: "9px 12px", borderRadius: "calc(var(--radius) - 4px)", fontSize: "13px", fontWeight: active ? 600 : 400,
  background: active ? "var(--bg-card)" : "transparent", border: active ? "1px solid var(--border)" : "1px solid transparent",
  color: active ? "var(--text-primary)" : "var(--text-secondary)", cursor: "pointer",
});

const messageStyle = (color) => ({ fontSize: "12px", color, lineHeight: 1.5, marginBottom: "4px" });
const wrapStyle = { width: "100%", maxWidth: "760px", display: "flex", flexDirection: "column" };
const pageTitle = { fontSize: "28px", fontWeight: 700, letterSpacing: "-0.03em", color: "var(--text-primary)", marginBottom: "6px" };
const pageSubtitle = { fontSize: "14px", color: "var(--text-secondary)", lineHeight: 1.6 };
const modeBar = { display: "flex", gap: "4px", padding: "5px", background: "rgba(255,255,255,0.03)", border: "1px solid var(--border)", borderRadius: "var(--radius)", marginBottom: "16px" };
const sectionTitle = { fontSize: "18px", fontWeight: 700, letterSpacing: "-0.02em", color: "var(--text-primary)", marginBottom: "6px" };
const cardStyle = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", padding: "28px", boxShadow: "0 8px 32px rgba(0,0,0,0.3)" };
const textareaStyle = { ...inputStyle, minHeight: "300px", fontFamily: "var(--font-mono)", fontSize: "13px", lineHeight: 1.7, resize: "vertical" };
const formatBox = { background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "14px 16px", marginBottom: "14px" };
const preStyle = { fontFamily: "var(--font-mono)", fontSize: "12px", lineHeight: 1.7, color: "var(--text-secondary)", whiteSpace: "pre-wrap", background: "rgba(0,0,0,0.2)", borderRadius: "var(--radius-sm)", padding: "10px 12px" };
const codeStyle = { fontFamily: "var(--font-mono)", color: "var(--accent-light)" };
const guideNote = { fontSize: "12px", color: "var(--text-muted)", marginTop: "10px", lineHeight: 1.6 };
const hintText = { fontSize: "12px", color: "var(--text-muted)", marginTop: "8px", textAlign: "center" };
const phraseBox = { background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 12px", marginBottom: "12px" };
const termChip = { padding: "3px 10px", borderRadius: "999px", fontSize: "13px", fontWeight: 600, color: "var(--text-primary)", background: "rgba(245,158,11,0.12)", border: "1px solid rgba(245,158,11,0.35)" };
const secondaryBtn = { padding: "7px 14px", background: "rgba(255,255,255,0.04)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-primary)", fontSize: "13px", fontWeight: 600, cursor: "pointer" };
const linkBtn = { background: "none", border: "none", padding: 0, color: "var(--accent-light)", fontSize: "12px", fontWeight: 600, cursor: "pointer" };
const termRow = { display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", padding: "8px 12px", borderRadius: "var(--radius-sm)", background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" };
const exampleText = { fontSize: "11px", color: "var(--text-muted)", maxWidth: "260px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };
const successBox = { marginTop: "14px", padding: "12px 14px", background: "var(--success-bg)", border: "1px solid var(--success-border)", borderRadius: "var(--radius-sm)", color: "var(--success)", fontSize: "13px", lineHeight: 1.6 };
