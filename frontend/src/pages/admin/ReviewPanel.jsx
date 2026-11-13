import { useEffect, useState } from "react";
import { identityHeaders } from "../../utils/identity";
import { exerciseTypeLabel } from "../../utils/exerciseTypes";
import { DIFFICULTY_LEVELS } from "../../utils/levels";
import {
  ErrorBox, Spinner, btnHover, selectStyle, diffBadgeStyle, tagStyle, ExTypeBadge, PayloadDisplay,
} from "./_shared";

const LIMIT = 20;

export function ReviewPanel({ track }) {
  const [exerciseType, setExerciseType] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [humanChecked, setHumanChecked] = useState(false);

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);

  const buildQuery = (currentOffset) => {
    const params = new URLSearchParams({ track: track.code, human_checked: String(humanChecked), limit: String(LIMIT), offset: String(currentOffset) });
    if (exerciseType) params.set("exercise_type", exerciseType);
    if (difficulty) params.set("difficulty", difficulty);
    return params.toString();
  };

  const load = async (currentOffset, append) => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`/api/exercises/review-queue?${buildQuery(currentOffset)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load the review queue");
      setItems((prev) => (append ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      setOffset(currentOffset);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(0, false); }, [exerciseType, difficulty, humanChecked]); // eslint-disable-line react-hooks/exhaustive-deps

  const setReviewStatus = async (exerciseId, nextHumanChecked) => {
    setActionError(null);
    try {
      const res = await fetch(`/api/exercises/${exerciseId}/human-checked`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...identityHeaders() },
        body: JSON.stringify({ human_checked: nextHumanChecked }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Update failed");
      // The item no longer matches the current human_checked filter — drop it.
      setItems((prev) => prev.filter((it) => it.id !== exerciseId));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (err) {
      setActionError(err.message);
    }
  };

  return (
    <div style={cardStyle}>
      <SectionTitle>Review queue</SectionTitle>
      <p style={subtitleStyle}>
        Exercises already in the DB: mark the good ones as verified — the agent prefers them as style examples for new generations.
      </p>

      <div style={filterRow}>
        <div style={{ display: "flex", gap: "6px" }}>
          <button onClick={() => setHumanChecked(false)} style={modeBtn(!humanChecked)}>To review</button>
          <button onClick={() => setHumanChecked(true)} style={modeBtn(humanChecked)}>Verified</button>
        </div>

        <select value={exerciseType} onChange={(e) => setExerciseType(e.target.value)} style={selectStyle}>
          <option value="">Any type</option>
          {track.exercise_types.map(({ code }) => <option key={code} value={code}>{exerciseTypeLabel(code)}</option>)}
        </select>
        <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} style={selectStyle}>
          <option value="">Any difficulty</option>
          {DIFFICULTY_LEVELS.map((d) => <option key={d} value={d}>Difficulty {d}</option>)}
        </select>
      </div>

      {error && <ErrorBox message={error} />}
      {actionError && <ErrorBox message={actionError} />}

      {!loading && items.length === 0 && (
        <p style={{ fontSize: "13px", color: "var(--text-muted)", marginTop: "16px" }}>No exercises match these filters.</p>
      )}

      <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        {items.map((ex) => (
          <QueueItemCard key={ex.id} exercise={ex} onSetStatus={setReviewStatus} />
        ))}
      </div>

      {loading && <div style={{ marginTop: "16px", textAlign: "center" }}><Spinner /></div>}

      {!loading && offset + items.length < total && (
        <button onClick={() => load(offset + LIMIT, true)} style={loadMoreBtn}>
          Load more ({total - offset - items.length} remaining)
        </button>
      )}
      <style>{btnHover}</style>
    </div>
  );
}

function QueueItemCard({ exercise, onSetStatus }) {
  const srcTr = exercise.phrase_translations.find((t) => t.language === exercise.source_language);
  const tgtTr = exercise.phrase_translations.find((t) => t.language === exercise.target_language);

  return (
    <div style={itemCardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
        <ExTypeBadge code={exercise.exercise_type} />
        <span style={tagStyle}>{exercise.origin === "human_import" ? "imported" : "AI-generated"}</span>
        <span style={diffBadgeStyle}>difficulty {exercise.difficulty}</span>
        {exercise.topics.map((t) => <span key={t} style={tagStyle}>{t}</span>)}
        <span style={{ marginLeft: "auto", fontSize: "11px", color: "var(--text-muted)" }}>
          {new Date(exercise.created_at).toLocaleDateString()}
        </span>
      </div>

      {(srcTr || tgtTr) && (
        <div style={phraseBox}>
          {srcTr && <div style={{ fontSize: "13px", color: "var(--text-secondary)" }}>{srcTr.content}</div>}
          {tgtTr && <div style={{ fontSize: "14px", color: "var(--text-primary)", fontWeight: 500, marginTop: srcTr ? "4px" : 0 }}>{tgtTr.content}</div>}
        </div>
      )}

      <PayloadDisplay type={exercise.exercise_type} payload={exercise.payload} annotations={exercise.annotations} />

      <div style={{ marginTop: "12px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px" }}>
        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          {exercise.human_checked
            ? `Verified by ${exercise.human_checked_by || "—"} on ${new Date(exercise.human_checked_at).toLocaleString()}`
            : "Not verified yet"}
        </span>
        {exercise.human_checked ? (
          <button onClick={() => onSetStatus(exercise.id, false)} style={secondaryBtn}>Remove verification</button>
        ) : (
          <button onClick={() => onSetStatus(exercise.id, true)} style={approveBtn}>✓ Approve</button>
        )}
      </div>
    </div>
  );
}

/* ── Styles ─────────────────────────────────── */

function SectionTitle({ children }) {
  return <h3 style={{ fontSize: "18px", fontWeight: 700, letterSpacing: "-0.02em", color: "var(--text-primary)", marginBottom: "6px" }}>{children}</h3>;
}

const cardStyle = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", padding: "32px", boxShadow: "0 8px 32px rgba(0,0,0,0.3)" };
const subtitleStyle = { fontSize: "13px", color: "var(--text-secondary)" };
const filterRow = { display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center", marginTop: "8px" };
const itemCardStyle = { background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "16px" };
const phraseBox = { background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 12px", marginBottom: "12px" };
const modeBtn = (active) => ({ padding: "7px 14px", borderRadius: "var(--radius-sm)", fontSize: "13px", fontWeight: active ? 600 : 400, background: active ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.03)", border: `1.5px solid ${active ? "rgba(99,102,241,0.4)" : "var(--border)"}`, color: active ? "var(--accent-light)" : "var(--text-secondary)", cursor: "pointer", transition: "all var(--transition)" });
const approveBtn = { padding: "6px 14px", background: "var(--success-bg)", border: "1px solid var(--success-border)", borderRadius: "var(--radius-sm)", color: "var(--success)", fontSize: "12px", fontWeight: 600, cursor: "pointer" };
const secondaryBtn = { padding: "6px 14px", background: "rgba(255,255,255,0.04)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-secondary)", fontSize: "12px", fontWeight: 600, cursor: "pointer" };
const loadMoreBtn = { width: "100%", marginTop: "16px", padding: "10px", background: "rgba(255,255,255,0.03)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-secondary)", fontSize: "13px", fontWeight: 600, cursor: "pointer" };
