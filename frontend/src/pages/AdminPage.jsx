import { useState } from "react";
import { AgentRunsPanel } from "./admin/AgentRunsPanel";
import { CoveragePanel } from "./admin/CoveragePanel";
import { ReadingsPanel } from "./admin/ReadingsPanel";
import { ReviewPanel } from "./admin/ReviewPanel";
import { ui } from "../i18n";

const TABS = [
  { id: "review",      label: ui.admin.tabs.review,    icon: "🔍" },
  { id: "coverage",    label: ui.admin.tabs.coverage,  icon: "🧮" },
  { id: "readings",    label: ui.admin.tabs.readings,  icon: "ふ" },
  { id: "agent-runs",  label: ui.admin.tabs.agentRuns, icon: "📊" },
];

export function AdminPage({ track }) {
  const [tab, setTab] = useState("review");

  return (
    <div style={wrapStyle}>
      {/* Page header */}
      <div style={headerBlock}>
        <h1 style={pageTitle}>{ui.admin.title}</h1>
        <p style={pageSubtitle}>{ui.admin.subtitle}</p>
      </div>

      {/* Tab bar */}
      <div style={tabBar}>
        {TABS.map(({ id, label, icon }) => (
          <button key={id} onClick={() => setTab(id)} style={tabBtn(tab === id)}>
            <span style={{ fontSize: "14px" }}>{icon}</span>
            {label}
          </button>
        ))}
      </div>

      {/* Panel */}
      <div style={panelWrap}>
        {tab === "review"      && <ReviewPanel track={track} />}
        {tab === "coverage"    && <CoveragePanel track={track} />}
        {tab === "readings"    && <ReadingsPanel track={track} />}
        {tab === "agent-runs"  && <AgentRunsPanel track={track} />}
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
}

const wrapStyle = {
  width: "100%",
  maxWidth: "680px",
  display: "flex",
  flexDirection: "column",
  gap: "0",
};

const headerBlock = {
  marginBottom: "28px",
};

const pageTitle = {
  fontSize: "28px",
  fontWeight: 700,
  letterSpacing: "-0.03em",
  color: "var(--text-primary)",
  marginBottom: "6px",
};

const pageSubtitle = {
  fontSize: "14px",
  color: "var(--text-secondary)",
  lineHeight: 1.6,
};

const tabBar = {
  display: "flex",
  gap: "4px",
  padding: "5px",
  background: "rgba(255,255,255,0.03)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  marginBottom: "24px",
};

const tabBtn = (active) => ({
  flex: 1,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "7px",
  padding: "9px 12px",
  borderRadius: "calc(var(--radius) - 4px)",
  fontSize: "13px",
  fontWeight: active ? 600 : 400,
  background: active ? "var(--bg-card)" : "transparent",
  border: active ? "1px solid var(--border)" : "1px solid transparent",
  color: active ? "var(--text-primary)" : "var(--text-secondary)",
  cursor: "pointer",
  transition: "all var(--transition)",
  boxShadow: active ? "0 2px 8px rgba(0,0,0,0.3)" : "none",
  whiteSpace: "nowrap",
});

const panelWrap = {
  animation: "fadeIn 0.25s ease forwards",
};
