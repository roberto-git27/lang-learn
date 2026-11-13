// Languages of the seeded tracks; unknown codes fall back to the raw code.
const LANG_LABELS = {
  it: { label: "Italiano", flag: "🇮🇹" },
  ja: { label: "日本語", flag: "🇯🇵" },
};

export function LangBadge({ code }) {
  const info = LANG_LABELS[code?.toLowerCase()] || { label: code, flag: "🌐" };
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      padding: "4px 10px",
      background: "rgba(255,255,255,0.05)",
      border: "1px solid var(--border)",
      borderRadius: "999px",
      fontSize: "12px",
      fontWeight: 500,
      color: "var(--text-secondary)",
      letterSpacing: "0.02em",
    }}>
      <span>{info.flag}</span>
      <span>{info.label}</span>
    </span>
  );
}
