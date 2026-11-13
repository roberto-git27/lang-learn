import { useEffect, useState } from "react";
import { ErrorBox, Spinner } from "./_shared";
import { exerciseTypeLabel } from "../../utils/exerciseTypes";

// Short column headers (the full label is the tooltip).
const SHORT_LABELS = {
  multiple_choice: "MC",
  fill_blank: "Blank",
  kanji_reading: "Read",
  kanji_writing: "Write",
  romaji_input: "Romaji",
  translate_rev: "Transl.",
};

// Below this many exercises a level is shown as thin: a chat session (10
// exercises, part of them one level up) would mostly be generated.
const THIN_LEVEL = 20;

/**
 * How many exercises the track has per difficulty and type, and how many of
 * them a human verified. Sessions take exercises from the DB first and ask
 * the generation model only for what is missing, so empty levels cost tokens.
 */
export function CoveragePanel({ track }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`/api/exercises/stats?track=${encodeURIComponent(track.code)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load the exercise counts");
      setStats(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div style={cardStyle}>
      <div style={headerRow}>
        <div>
          <h3 style={titleStyle}>Coverage</h3>
          <p style={subtitleStyle}>
            Exercises per difficulty and type. Sessions use these first and generate only what is missing.
          </p>
        </div>
        <button onClick={load} disabled={loading} style={refreshBtn}>
          {loading ? <Spinner /> : "↻ Refresh"}
        </button>
      </div>

      {error && <ErrorBox message={error} />}

      {stats && (
        <>
          <div style={totalsRow}>
            <span><strong>{stats.total}</strong> exercises</span>
            <span style={{ color: "var(--text-muted)" }}>·</span>
            <span><strong>{stats.human_checked}</strong> verified</span>
            <span style={{ color: "var(--text-muted)" }}>·</span>
            <span><strong>{stats.total - stats.human_checked}</strong> to review</span>
          </div>

          <div style={tableWrap}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={th("left")}>Level</th>
                  <th style={th()}>Total</th>
                  <th style={th()} title="Verified by a human">Verified</th>
                  {stats.exercise_types.map((code) => (
                    <th key={code} style={th()} title={exerciseTypeLabel(code)}>
                      {SHORT_LABELS[code] ?? code}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stats.levels.map((level) => (
                  <tr key={level.difficulty} style={{ opacity: level.total === 0 ? 0.45 : 1 }}>
                    <td style={td("left")}>{level.difficulty}</td>
                    <td style={{ ...td(), fontWeight: 700, color: totalColor(level.total) }}>{level.total}</td>
                    <td style={td()}>{level.human_checked}</td>
                    {stats.exercise_types.map((code) => (
                      <td key={code} style={{ ...td(), color: level.by_type[code] ? "var(--text-primary)" : "var(--text-muted)" }}>
                        {level.by_type[code] || "·"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p style={noteStyle}>
            Levels with fewer than {THIN_LEVEL} exercises are highlighted: a session there will mostly be generated.
            Add exercises from the Studio (import or generate).
          </p>
        </>
      )}
    </div>
  );
}

function totalColor(total) {
  if (total === 0) return "var(--text-muted)";
  return total < THIN_LEVEL ? "#f59e0b" : "var(--success)";
}

const cardStyle = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", padding: "32px", boxShadow: "0 8px 32px rgba(0,0,0,0.3)" };
const headerRow = { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "16px" };
const titleStyle = { fontSize: "18px", fontWeight: 700, letterSpacing: "-0.02em", color: "var(--text-primary)", marginBottom: "6px" };
const subtitleStyle = { fontSize: "13px", color: "var(--text-secondary)" };
const refreshBtn = { padding: "8px 14px", background: "rgba(255,255,255,0.04)", border: "1.5px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-primary)", fontSize: "13px", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" };
const totalsRow = { display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "18px", fontSize: "13px", color: "var(--text-secondary)" };
const tableWrap = { marginTop: "14px", overflowX: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)" };
const tableStyle = { width: "100%", borderCollapse: "collapse", fontSize: "13px", fontVariantNumeric: "tabular-nums" };
const th = (align = "right") => ({ textAlign: align, padding: "8px 10px", fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.02)", whiteSpace: "nowrap" });
const td = (align = "right") => ({ textAlign: align, padding: "7px 10px", borderBottom: "1px solid var(--border)", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" });
const noteStyle = { marginTop: "12px", fontSize: "12px", color: "var(--text-muted)", lineHeight: 1.5 };
