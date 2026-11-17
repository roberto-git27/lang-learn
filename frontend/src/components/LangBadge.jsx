import { ui } from "../i18n";

// Languages of the seeded tracks (names in their own language); unknown codes fall back to the raw code.
const LANG_FLAGS = { it: "🇮🇹", ja: "🇯🇵" };

export function LangBadge({ code }) {
  const key = code?.toLowerCase();
  const info = { label: ui.languages[key] ?? code, flag: LANG_FLAGS[key] ?? "🌐" };
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
