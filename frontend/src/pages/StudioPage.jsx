import { useEffect, useRef, useState } from "react";
import { identityHeaders } from "../utils/identity";
import { exerciseTypeLabel } from "../utils/exerciseTypes";
import {
  ErrorBox, Spinner, btnHover, labelStyle, inputStyle, diffBadgeStyle, tagStyle, submitButtonStyle,
  ExTypeBadge, PayloadDisplay,
} from "./admin/_shared";
import { Rich, ui } from "../i18n";

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
  import: { label: ui.studio.modes.import, example: IMPORT_EXAMPLE },
  generate: { label: ui.studio.modes.generate, example: GENERATE_EXAMPLE },
  terms: { label: ui.studio.modes.terms, example: TERMS_EXAMPLE },
};


const FRONT_MATTER_MODE = /^---\s*\n(?:.*\n)*?mode:\s*(import|generate|terms)\b.*\n(?:.*\n)*?---/;

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.[0]?.msg || ui.common.requestFailed);
  return data;
}

const postJson = (url, body) => requestJson(url, {
  method: "POST",
  headers: { "Content-Type": "application/json", ...identityHeaders() },
  body: JSON.stringify(body),
});

export function StudioPage({ track }) {
  const [mode, setMode] = useState("import");
  const [sources, setSources] = useState(() => Object.fromEntries(Object.keys(MODES).map((m) => [m, { text: "", name: ui.studio.pastedText }])));
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

  const body = () => ({ track: track.code, text: source.text, source_name: source.name.trim() || ui.studio.pastedText });

  const handlePreview = () => run("preview", async () => setPreview(await postJson("/api/studio/imports/preview", body())));

  const handleFix = () => run("fix", async () => {
    const original = source.text;
    const res = await postJson("/api/studio/imports/normalize", body());
    setSource("import", { text: res.text });
    setBeforeFix(original);
    setNotice(ui.studio.fixed(res));
  });

  const restoreBeforeFix = () => {
    setSource("import", { text: beforeFix });
    setBeforeFix(null);
  };

  const handleImport = () => run("import", async () => {
    const job = await postJson("/api/studio/imports", body());
    setPreview(null);
    setBeforeFix(null);
    setNotice(ui.studio.imported(job.created_count, job.source_name));
    setHistoryVersion((v) => v + 1);
  });

  const handleExtractTerms = () => run("extract", async () => setTermsPreview(await postJson("/api/studio/terms/preview", body())));

  const handleSaveTerms = () => run("saveTerms", async () => {
    const job = await postJson("/api/studio/terms", body());
    setTermsPreview(null);
    setNotice(ui.studio.termsSaved(job));
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
    setNotice(ui.studio.draftSaved(job.created_count));
    setHistoryVersion((v) => v + 1);
  });

  // Resolves to the updated draft (null on error, shown above the editor).
  const handleRegenerate = async (position, note) => {
    let updated = null;
    await run(`regenerate-${position}`, async () => {
      updated = await postJson(`/api/studio/generations/${draft.id}/items/${position}/regenerate`, { track: track.code, note });
      setDraft(updated);
      setHistoryVersion((v) => v + 1);
    });
    return updated;
  };

  const handleDiscard = () => run("discard", async () => {
    await postJson(`/api/studio/generations/${draft.id}/discard?track=${encodeURIComponent(track.code)}`, {});
    setDraft(null);
    setHistoryVersion((v) => v + 1);
  });

  const editAsMarkdown = () => {
    loadText(draft.markdown, ui.studio.editedName(draft.source_name), "import");
    setNotice(ui.studio.draftInEditor);
  };

  const openDraft = (job) => { setDraft(job); switchMode("generate"); };

  const canRun = source.text.trim() && !busy;

  return (
    <div style={wrapStyle}>
      <div style={{ marginBottom: "28px" }}>
        <h1 style={pageTitle}>{ui.studio.title}</h1>
        <p style={pageSubtitle}>
          <Rich text={ui.studio.subtitle} />
        </p>
      </div>

      <div style={modeBar}>
        {Object.entries(MODES).map(([id, { label }]) => (
          <button key={id} onClick={() => switchMode(id)} style={modeTab(mode === id)}>{label}</button>
        ))}
      </div>

      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", marginBottom: "14px" }}>
          <button onClick={() => fileInput.current?.click()} style={secondaryBtn}>{mode === "terms" ? ui.studio.openFileTerms : ui.studio.openFile}</button>
          <input ref={fileInput} type="file" accept=".md,.markdown,.txt,.csv,.tsv,text/markdown,text/plain,text/csv" onChange={openFile} style={{ display: "none" }} />
          <input
            value={source.name} onChange={(e) => setSource(mode, { name: e.target.value })} maxLength={255}
            title={ui.studio.nameTitle} style={{ ...inputStyle, flex: 1, minWidth: "160px", padding: "7px 11px", fontSize: "13px" }}
          />
          <button onClick={() => setShowFormat((v) => !v)} style={linkBtn}>{showFormat ? ui.studio.hideFormat : ui.studio.formatGuide}</button>
        </div>

        {showFormat && <FormatGuide mode={mode} track={track} />}

        <textarea
          value={source.text} onChange={(e) => setSource(mode, { text: e.target.value })} spellCheck={false}
          placeholder={ui.studio.placeholders[mode] + "\n\n" + MODES[mode].example}
          style={textareaStyle}
        />

        {error && <div style={{ marginTop: "14px" }}><ErrorBox message={error} /></div>}

        {mode === "import" && (
          <button onClick={handlePreview} disabled={!canRun} style={{ ...submitButtonStyle(!canRun), marginTop: "14px" }}>
            {busy === "preview" ? <Spinner /> : ui.studio.preview}
          </button>
        )}
        {mode === "terms" && (
          <button onClick={handleExtractTerms} disabled={!canRun} style={{ ...submitButtonStyle(!canRun), marginTop: "14px" }}>
            {busy === "extract" ? <Spinner /> : ui.studio.extractTerms}
          </button>
        )}
        {mode === "generate" && (
          <button onClick={handleGenerate} disabled={!canRun || !!draft} style={{ ...submitButtonStyle(!canRun || !!draft), marginTop: "14px" }}>
            {busy === "generate" ? <><Spinner /> {ui.studio.generating}</> : draft ? ui.studio.draftPending : ui.studio.generate}
          </button>
        )}

        {notice && <p style={successBox}>✓ {notice}</p>}
        {mode === "import" && beforeFix !== null && (
          <button onClick={restoreBeforeFix} disabled={!!busy} style={{ ...linkBtn, marginTop: "10px" }}>
            {ui.studio.restoreBeforeFix}
          </button>
        )}
      </div>

      {mode === "import" && preview && <ImportPreview preview={preview} busy={busy} onImport={handleImport} onFix={handleFix} />}
      {mode === "terms" && termsPreview && <TermsPreview preview={termsPreview} busy={busy} onSave={handleSaveTerms} />}
      {mode === "terms" && <Vocabulary track={track} version={vocabularyVersion} />}
      {mode === "generate" && draft && (
        <GenerationDraft
          key={draft.id} draft={draft} busy={busy} error={error}
          onSave={handleSave} onDiscard={handleDiscard} onEdit={editAsMarkdown} onRegenerate={handleRegenerate}
        />
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
          <p style={{ ...labelStyle, margin: "14px 0 6px" }}>{ui.studio.guide.types}</p>
          <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "4px" }}>
            {track.exercise_types.map(({ code }) => (
              <li key={code} style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                <code style={codeStyle}>## {code}</code> {ui.studio.typeNotes[code] ?? ""}
              </li>
            ))}
          </ul>
          <p style={guideNote}>
            <Rich text={ui.studio.guide.import} codeStyle={codeStyle} />
          </p>
        </>
      ) : mode === "terms" ? (
        <>
          <p style={guideNote}>
            {ui.studio.guide.terms}
          </p>
          <p style={{ ...labelStyle, margin: "14px 0 6px" }}>{ui.studio.guide.termListTitle}</p>
          <pre style={preStyle}>{TERM_LIST_EXAMPLE}</pre>
          <p style={guideNote}>
            <Rich text={ui.studio.guide.termList} codeStyle={codeStyle} />
          </p>
        </>
      ) : (
        <p style={guideNote}>
          {ui.studio.guide.generate(track.exercise_types.map(({ code }) => code).join(", "))}
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
      <h3 style={sectionTitle}>{ui.studio.previewTitle}</h3>
      {preview.errors.map((e) => <ErrorBox key={e} message={e} />)}
      {preview.items.length > 0 && <Counts items={preview.items} />}

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {preview.items.map((item) => <PreviewItem key={item.line} item={item} label={ui.studio.line(item.line)} />)}
      </div>

      <button onClick={onImport} disabled={blocked} style={{ ...submitButtonStyle(blocked), marginTop: "18px" }}>
        {busy === "import" ? <Spinner /> : ui.studio.importCount(preview.ready_count)}
      </button>
      {preview.error_count > 0 && preview.ready_count > 0 && (
        <p style={hintText}>
          {ui.studio.errorsSkipped}
        </p>
      )}
      {fixable && (
        <div style={{ marginTop: "14px" }}>
          <button onClick={onFix} disabled={!!busy} style={secondaryBtn}>
            {busy === "fix" ? <><Spinner /> {ui.studio.fixing}</> : ui.studio.fix}
          </button>
          <p style={hintText}>
            {ui.studio.fixHint}
          </p>
        </div>
      )}
    </div>
  );
}

/* ── Generation draft ───────────────────────────────────────── */

function GenerationDraft({ draft, busy, error, onSave, onDiscard, onEdit, onRegenerate }) {
  const [kept, setKept] = useState(() => new Set(draft.items.flatMap((item, i) => (item.status === "ready" ? [i] : []))));
  const [rewriting, setRewriting] = useState(null);   // position whose note box is open
  const [note, setNote] = useState("");

  const regenerate = async (i) => {
    const updated = await onRegenerate(i, note);
    if (!updated) return;
    setRewriting(null);
    setNote("");
    setKept((prev) => {
      const next = new Set(prev);
      if (updated.items[i]?.status === "ready") next.add(i); else next.delete(i);
      return next;
    });
  };
  const toggle = (i) => setKept((prev) => {
    const next = new Set(prev);
    if (next.has(i)) next.delete(i); else next.add(i);
    return next;
  });
  const blocked = kept.size === 0 || !!busy;

  return (
    <div style={{ ...cardStyle, marginTop: "16px", animation: "fadeSlideIn 0.3s ease forwards" }}>
      <h3 style={sectionTitle}>{ui.studio.draftTitle(draft.source_name)}</h3>
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
          >
            {rewriting === i ? (
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center", marginTop: "10px" }}>
                <input
                  value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} autoFocus
                  onKeyDown={(e) => { if (e.key === "Enter" && !busy) regenerate(i); }}
                  placeholder={ui.studio.regenerateNote}
                  style={{ ...inputStyle, flex: 1, minWidth: "200px", padding: "7px 11px", fontSize: "13px" }}
                />
                <button onClick={() => regenerate(i)} disabled={!!busy} style={secondaryBtn}>
                  {busy === `regenerate-${i}` ? <Spinner /> : ui.studio.regenerate}
                </button>
                <button onClick={() => { setRewriting(null); setNote(""); }} disabled={!!busy} style={linkBtn}>{ui.common.cancel}</button>
                {error && busy === null && <span style={{ fontSize: "12px", color: "var(--error)" }}>{error}</span>}
              </div>
            ) : (
              <button onClick={() => { setRewriting(i); setNote(""); }} disabled={!!busy} style={{ ...linkBtn, marginTop: "8px" }}>
                {ui.studio.regenerateOpen}
              </button>
            )}
          </PreviewItem>
        ))}
      </div>

      <button onClick={() => onSave([...kept])} disabled={blocked} style={{ ...submitButtonStyle(blocked), marginTop: "18px" }}>
        {busy === "save" ? <Spinner /> : ui.studio.saveDraft(kept.size)}
      </button>
      <div style={{ display: "flex", justifyContent: "center", gap: "18px", marginTop: "12px" }}>
        {draft.markdown && <button onClick={onEdit} disabled={!!busy} style={linkBtn}>{ui.studio.editAsMarkdown}</button>}
        <button onClick={onDiscard} disabled={!!busy} style={{ ...linkBtn, color: "var(--error)" }}>{ui.studio.discard}</button>
      </div>
    </div>
  );
}

/* ── Shared item rendering ──────────────────────────────────── */

function Counts({ items }) {
  const count = (status) => items.filter((it) => it.status === status).length;
  return (
    <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "10px 0 16px" }}>
      <span style={countChip("ready")}>{ui.studio.counts.ready(count("ready"))}</span>
      <span style={countChip("duplicate")}>{ui.studio.counts.duplicate(count("duplicate"))}</span>
      <span style={countChip("error")}>{ui.studio.counts.error(count("error"))}</span>
    </div>
  );
}

function PreviewItem({ item, label, selectable = false, selected = false, onToggle, children }) {
  const dimmed = item.status === "duplicate" || (selectable && !selected);
  return (
    <div style={itemCard(item.status, dimmed)}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: item.payload ? "10px" : "6px" }}>
        {selectable && <input type="checkbox" checked={selected} onChange={onToggle} title={ui.studio.keepTitle} style={{ accentColor: "var(--accent)" }} />}
        <span style={countChip(item.status)}>{ui.studio.status[item.status] ?? item.status}</span>
        <span style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{label}</span>
        {item.payload ? <ExTypeBadge code={item.exercise_type} /> : <span style={tagStyle}>{exerciseTypeLabel(item.exercise_type)}</span>}
        {item.term && <span style={termChip}>{item.term}</span>}
        {item.difficulty && <span style={diffBadgeStyle}>{ui.common.difficulty(item.difficulty)}</span>}
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
      {children}
    </div>
  );
}

/* ── Vocabulary ─────────────────────────────────────────────── */


function TermsPreview({ preview, busy, onSave }) {
  const updates = preview.meaning_updates ?? 0;
  const blocked = preview.errors.length > 0 || (preview.new_count === 0 && updates === 0) || !!busy;
  const label = [
    preview.new_count ? ui.vocabulary.newTerms(preview.new_count) : "",
    updates ? ui.vocabulary.meanings(updates) : "",
  ].filter(Boolean).join(" + ") || ui.vocabulary.newTerms(0);
  return (
    <div style={{ ...cardStyle, marginTop: "16px", animation: "fadeSlideIn 0.3s ease forwards" }}>
      <h3 style={sectionTitle}>{preview.items.some((term) => term.line) ? ui.vocabulary.inList : ui.vocabulary.inText}</h3>
      {preview.errors.map((e) => <ErrorBox key={e} message={e} />)}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "10px 0 16px" }}>
        <span style={countChip("ready")}>{ui.vocabulary.counts.new(preview.new_count)}</span>
        <span style={countChip("duplicate")}>{ui.vocabulary.counts.known(preview.existing_count)}</span>
        {updates > 0 && <span style={countChip("ready")}>{ui.vocabulary.counts.meanings(updates)}</span>}
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
        {busy === "saveTerms" ? <Spinner /> : ui.vocabulary.save(label)}
      </button>
    </div>
  );
}

function TermHead({ term }) {
  return (
    <>
      <span style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary)", minWidth: "84px" }}>{term.written}</span>
      <span style={{ fontSize: "12px", color: "var(--text-secondary)", minWidth: "90px" }}>{term.reading !== term.written ? term.reading : ""}</span>
      <span style={tagStyle}>{ui.vocabulary.pos[term.pos] ?? term.pos}</span>
      <span style={diffBadgeStyle}>{ui.vocabulary.level(term.level)}</span>
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
    return ui.vocabulary.translated(r);
  });

  const sync = () => act("sync", async () => {
    const r = await postJson(`/api/terms/sync?track=${encodeURIComponent(track.code)}`, {});
    return ui.vocabulary.synced(r.exercises_linked, r.terms_created);
  });

  const saveMeaning = (term, meaning) => act(null, async () => {
    await requestJson(`/api/terms/${term.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json", ...identityHeaders() },
      body: JSON.stringify({ track: track.code, meaning }),
    });
    return null;
  });

  const remove = (term) => {
    if (!window.confirm(ui.vocabulary.confirmDelete(term.written))) return;
    act(null, async () => {
      const res = await fetch(`/api/terms/${term.id}?track=${encodeURIComponent(track.code)}`, { method: "DELETE", headers: identityHeaders() });
      if (!res.ok) throw new Error((await res.json()).detail || ui.vocabulary.deleteFailed);
      return ui.vocabulary.deleted(term.written);
    });
  };

  return (
    <div style={{ ...cardStyle, marginTop: "16px" }}>
      <h3 style={sectionTitle}>{ui.vocabulary.title}</h3>
      <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "14px" }}>
        {data ? ui.vocabulary.totals(data.total, missingOnly || !!query, data.missing_meanings) : ui.common.loading}{" "}
        {ui.vocabulary.autoLink}
      </p>

      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "12px" }}>
        <button onClick={translate} disabled={!!busy || !data?.missing_meanings} style={secondaryBtn}>
          {busy === "translate" ? <Spinner /> : ui.vocabulary.translate(Math.min(60, data?.missing_meanings ?? 0))}
        </button>
        <button onClick={sync} disabled={!!busy} style={secondaryBtn}>{busy === "sync" ? <Spinner /> : ui.vocabulary.sync}</button>
      </div>
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center", marginBottom: "14px" }}>
        <input value={query} onChange={(e) => { setQuery(e.target.value); setLimit(VOCABULARY_LIMIT); }} placeholder={ui.vocabulary.search}
          style={{ ...inputStyle, flex: 1, minWidth: "180px", padding: "7px 11px", fontSize: "13px" }} />
        <label style={{ fontSize: "12px", color: "var(--text-secondary)", display: "flex", gap: "6px", alignItems: "center" }}>
          <input type="checkbox" checked={missingOnly} onChange={(e) => { setMissingOnly(e.target.checked); setLimit(VOCABULARY_LIMIT); }} style={{ accentColor: "var(--accent)" }} />
          {ui.vocabulary.missingOnly}
        </label>
      </div>

      {error && <ErrorBox message={error} />}
      {notice && <p style={{ ...successBox, marginTop: 0, marginBottom: "12px" }}>✓ {notice}</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {data?.items.map((term) => (
          <div key={term.id} style={termRow}>
            <TermHead term={term} />
            <MeaningInput term={term} onSave={saveMeaning} />
            <span title={ui.vocabulary.exercisesTitle} style={{ fontSize: "11px", color: "var(--text-muted)" }}>{ui.vocabulary.exerciseCount(term.exercise_count)}</span>
            <button onClick={() => remove(term)} title={ui.vocabulary.deleteTitle} style={{ ...linkBtn, color: "var(--error)" }}>✕</button>
          </div>
        ))}
      </div>
      {data && data.items.length < data.total && (
        <button onClick={() => setLimit((n) => n + VOCABULARY_LIMIT)} style={{ ...secondaryBtn, width: "100%", marginTop: "12px" }}>
          {ui.common.loadMore(data.total - data.items.length)}
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
        placeholder={ui.vocabulary.meaningPlaceholder} title={term.example ?? ""}
        style={{ ...inputStyle, padding: "5px 9px", fontSize: "13px" }}
      />
      {term.meaning_source && <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>{ui.vocabulary.source[term.meaning_source]}</span>}
    </span>
  );
}

/* ── Job history ────────────────────────────────────────────── */

const JOB_STATUS = { saved: "ready", draft: "history", discarded: "duplicate" };

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
      <h3 style={sectionTitle}>{ui.jobs.title}</h3>
      <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "14px" }}>
        {ui.jobs.subtitle}
      </p>
      {error && <ErrorBox message={error} />}
      {jobs?.length === 0 && <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>{ui.jobs.empty}</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {jobs?.map((job) => (
          <div key={job.id} style={itemCard("history")}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span style={tagStyle}>{ui.jobs.kinds[job.kind] ?? job.kind}</span>
              <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)" }}>{job.source_name}</span>
              <span style={countChip(JOB_STATUS[job.status])}>{job.status === "saved" ? `+${job.created_count}` : ui.jobs.status[job.status] ?? job.status}</span>
              {job.kind === "generate" && <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>{ui.runs.tokens(job.input_tokens + job.output_tokens)}</span>}
              <span style={{ marginLeft: "auto", fontSize: "11px", color: "var(--text-muted)" }}>
                {new Date(job.created_at).toLocaleString()}{job.user_display_name ? ` · ${job.user_display_name}` : ""}
              </span>
            </div>
            <div style={{ display: "flex", gap: "14px", marginTop: "8px" }}>
              <button onClick={() => toggleSource(job)} style={linkBtn}>{openJob?.id === job.id ? ui.jobs.hideSource : ui.jobs.showSource}</button>
              {openJob?.id === job.id && (
                <button onClick={() => onLoadSource(openJob.source_text, openJob.source_name, openJob.kind)} style={linkBtn}>{ui.jobs.load}</button>
              )}
              {job.status === "draft" && <button onClick={() => openDraft(job)} style={linkBtn}>{ui.jobs.openDraft}</button>}
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
