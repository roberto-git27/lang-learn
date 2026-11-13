import { useEffect, useState } from "react";
import { ErrorBox, Spinner, btnHover, labelStyle, tagStyle } from "./_shared";

const STATUS_COLORS = {
  ok: { bg: "rgba(16,185,129,0.1)", border: "rgba(16,185,129,0.3)", color: "var(--success)" },
  partial: { bg: "rgba(245,158,11,0.1)", border: "rgba(245,158,11,0.3)", color: "#f59e0b" },
  error: { bg: "var(--error-bg)", border: "var(--error-border)", color: "var(--error)" },
};

export function AgentRunsPanel({ track }) {
  const [runs, setRuns] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadRuns = async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`/api/exercises/agent-runs?limit=50&track=${encodeURIComponent(track.code)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load agent runs");
      setRuns(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadRuns(); }, []);

  const toggleRow = async (run) => {
    if (expandedId === run.id) { setExpandedId(null); setDetail(null); return; }
    setExpandedId(run.id); setDetail(null); setDetailLoading(true);
    try {
      const res = await fetch(`/api/exercises/agent-runs/${run.id}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load run details");
      setDetail(data);
    } catch (err) {
      setDetail({ error: err.message });
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <>
      <div style={cardStyle}>
        <div style={headerRow}>
          <div>
            <SectionTitle>Agent Runs</SectionTitle>
            <p style={subtitleStyle}>
              Every run of the exercise selection/generation agent: computed mix, gap, LLM cycles/tokens and outcome.
            </p>
          </div>
          <button onClick={loadRuns} disabled={loading} style={refreshBtn}>
            {loading ? <Spinner /> : "↻ Refresh"}
          </button>
        </div>

        {error && <ErrorBox message={error} />}

        {runs && runs.length === 0 && !loading && (
          <p style={{ fontSize: "13px", color: "var(--text-muted)", marginTop: "12px" }}>
            No runs recorded yet.
          </p>
        )}

        {runs && runs.length > 0 && (
          <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
            {runs.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                expanded={expandedId === run.id}
                onToggle={() => toggleRow(run)}
                detail={expandedId === run.id ? detail : null}
                detailLoading={expandedId === run.id && detailLoading}
              />
            ))}
          </div>
        )}
      </div>
      <style>{btnHover}</style>
    </>
  );
}

function RunRow({ run, expanded, onToggle, detail, detailLoading }) {
  const statusStyle = STATUS_COLORS[run.status] || STATUS_COLORS.error;

  return (
    <div style={rowWrap}>
      <button onClick={onToggle} style={rowHeader}>
        <span style={{ ...statusBadge, background: statusStyle.bg, border: `1px solid ${statusStyle.border}`, color: statusStyle.color }}>
          {run.status}
        </span>
        <span style={{ fontSize: "12px", color: "var(--text-secondary)", minWidth: "150px" }}>
          {new Date(run.created_at).toLocaleString()}
        </span>
        <span style={{ ...monoChip, flex: 1 }} title={run.session_id || ""}>
          {run.session_id ? run.session_id.slice(0, 8) : "—"}
        </span>
        <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{run.user_display_name || "—"}</span>
        <span style={tagStyle}>db {run.db_found_count}</span>
        <span style={tagStyle}>gap {run.gap_count}</span>
        <span style={run.generated_count > 0 ? createdBadge : tagStyle}>created {run.generated_count}</span>
        <span style={tagStyle}>{run.cycles} cycles</span>
        <span style={tagStyle}>{run.llm_calls} calls</span>
        <span style={tagStyle}>{run.input_tokens + run.output_tokens} tok</span>
        <span style={tagStyle}>{run.duration_ms} ms</span>
        <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div style={detailBox}>
          {detailLoading && <Spinner />}
          {detail?.error && <ErrorBox message={detail.error} />}
          {detail && !detail.error && (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <DetailField label="Request params" value={detail.request_params} />
              <DetailField label="Target composition" value={detail.target_composition} />
              <DetailField label="Final exercise ids" value={detail.final_exercise_ids} />
              <DetailField label="Full trace" value={detail.trace} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DetailField({ label, value }) {
  return (
    <div>
      <p style={labelStyle}>{label}</p>
      <pre style={preStyle}>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function SectionTitle({ children }) {
  return <h3 style={{ fontSize: "18px", fontWeight: 700, letterSpacing: "-0.02em", color: "var(--text-primary)", marginBottom: "6px" }}>{children}</h3>;
}

const cardStyle = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", padding: "32px", boxShadow: "0 8px 32px rgba(0,0,0,0.3)" };
const subtitleStyle = { fontSize: "13px", color: "var(--text-secondary)" };
const headerRow = { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "16px" };
const refreshBtn = { padding: "8px 14px", background: "rgba(255,255,255,0.04)", border: "1.5px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-primary)", fontSize: "13px", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" };
const rowWrap = { border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", overflow: "hidden" };
const rowHeader = { width: "100%", display: "flex", alignItems: "center", gap: "10px", padding: "10px 14px", background: "rgba(255,255,255,0.02)", border: "none", cursor: "pointer", textAlign: "left", flexWrap: "wrap" };
const statusBadge = { padding: "3px 9px", borderRadius: "999px", fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" };
const createdBadge = { padding: "3px 9px", background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", borderRadius: "999px", fontSize: "11px", color: "var(--success)", fontWeight: 600 };
const monoChip = { fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" };
const detailBox = { padding: "16px", borderTop: "1px solid var(--border)", background: "rgba(0,0,0,0.15)" };
const preStyle = { fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-secondary)", whiteSpace: "pre-wrap", wordBreak: "break-word", marginTop: "6px", padding: "10px 12px", background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)" };
