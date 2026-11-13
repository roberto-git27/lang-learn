/* Shared micro-components and styles used by the admin panels and the Studio page */
import { exerciseTypeLabel } from "../../utils/exerciseTypes";
import { RubyText } from "../../components/RubyText";

export function ErrorBox({ message }) {
  return (
    <div style={{ padding: "12px 14px", background: "var(--error-bg)", border: "1px solid var(--error-border)", borderRadius: "var(--radius-sm)", marginBottom: "14px" }}>
      <span style={{ color: "var(--error)", fontSize: "13px" }}>⚠ {message}</span>
    </div>
  );
}

export function Spinner() {
  return (
    <span style={{ display: "inline-block", width: "13px", height: "13px", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
  );
}

export const labelStyle = {
  fontSize: "10px",
  fontWeight: 600,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

export const selectStyle = {
  background: "rgba(255,255,255,0.04)",
  border: "1.5px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "10px 12px",
  color: "var(--text-primary)",
  fontSize: "14px",
  outline: "none",
  cursor: "pointer",
  maxWidth: "220px",
};

export const inputStyle = {
  width: "100%",
  background: "rgba(255,255,255,0.04)",
  border: "1.5px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "11px 13px",
  color: "var(--text-primary)",
  fontSize: "14px",
  lineHeight: 1.6,
  outline: "none",
  transition: "border-color var(--transition)",
};

export const diffBadgeStyle = {
  padding: "3px 10px",
  background: "rgba(99,102,241,0.12)",
  border: "1px solid rgba(99,102,241,0.25)",
  borderRadius: "999px",
  fontSize: "12px",
  fontWeight: 600,
  color: "var(--accent-light)",
  whiteSpace: "nowrap",
};

export const tagStyle = {
  padding: "3px 9px",
  background: "rgba(99,102,241,0.1)",
  border: "1px solid rgba(99,102,241,0.2)",
  borderRadius: "999px",
  fontSize: "11px",
  color: "var(--accent-light)",
  fontWeight: 500,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

export const submitButtonStyle = (disabled) => ({
  width: "100%",
  padding: "13px",
  background: disabled ? "rgba(99,102,241,0.3)" : "var(--accent)",
  color: disabled ? "rgba(255,255,255,0.4)" : "#fff",
  borderRadius: "var(--radius-sm)",
  fontSize: "14px",
  fontWeight: 600,
  letterSpacing: "0.02em",
  cursor: disabled ? "not-allowed" : "pointer",
  transition: "all var(--transition)",
  boxShadow: disabled ? "none" : "0 4px 18px rgba(99,102,241,0.3)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "8px",
});

export const btnHover = `
  button:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); }
  input:focus, textarea:focus, select:focus { border-color: var(--border-focus) !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes fadeSlideIn { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
`;

/* Exercise payload preview — used by the review queue and the Studio import
   preview, which render every exercise type the same way. Furigana are always
   shown here, so reviewers can check the readings too. */
export function ExTypeBadge({ code }) {
  return (
    <span style={{ padding: "4px 10px", background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.35)", borderRadius: "999px", fontSize: "12px", fontWeight: 600, color: "var(--accent-light)" }}>
      {exerciseTypeLabel(code)}
    </span>
  );
}

export function PayloadDisplay({ type, payload, annotations = {} }) {
  if (!payload) return null;

  if (type === "translate_rev") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {payload.prompt && <PayloadRow label="Prompt" value={payload.prompt} segments={annotations.prompt} />}
        <PayloadRow label="Expected answer" value={payload.expected} highlight />
        {payload.alternatives?.length > 0 && (
          <div>
            <p style={fieldLabel}>Accepted alternatives</p>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "4px" }}>
              {payload.alternatives.map((a, i) => <span key={i} style={altChip}>{a}</span>)}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (type === "romaji_input") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <PayloadRow label="Sentence (underlined: word to write in romaji)" value={payload.sentence} segments={annotations.sentence} />
        <PayloadRow label="Expected answer (computed)" value={payload.expected} highlight />
        <PayloadRow label="Also accepted" value={(payload.accepted || []).join(" · ")} />
        {payload.explanation && <PayloadRow label="Explanation" value={payload.explanation} segments={annotations.explanation} />}
      </div>
    );
  }

  if (type === "multiple_choice" || type === "kanji_reading" || type === "kanji_writing") {
    const field = type === "multiple_choice" ? "question" : "sentence";
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {payload[field] && <PayloadRow label={type === "multiple_choice" ? "Question" : "Sentence (underlined: the word asked about)"} value={payload[field]} segments={annotations[field]} />}
        {payload.options?.length > 0 && (
          <div>
            <p style={fieldLabel}>Options</p>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "6px" }}>
              {payload.options.map((opt, i) => (
                <div key={i} style={optionRow(i === payload.correct_index)}>
                  <span style={optionIndex(i === payload.correct_index)}>{i}</span>
                  <span style={{ fontSize: "14px", color: i === payload.correct_index ? "var(--success)" : "var(--text-primary)", lineHeight: 1.8 }}><RubyText text={opt} segments={annotations.options?.[i]} /></span>
                  {i === payload.correct_index && <span style={correctMark}>✓ correct</span>}
                </div>
              ))}
            </div>
          </div>
        )}
        {payload.explanation && <PayloadRow label="Explanation" value={payload.explanation} segments={annotations.explanation} />}
      </div>
    );
  }

  if (type === "fill_blank") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {payload.sentence_with_blank && <PayloadRow label="Sentence with blank" value={payload.sentence_with_blank} segments={annotations.sentence_with_blank} />}
        {payload.options?.length > 0 && (
          <div>
            <p style={fieldLabel}>Options</p>
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "6px" }}>
              {payload.options.map((opt, i) => (
                <span key={i} style={{ padding: "5px 12px", borderRadius: "999px", fontSize: "13px", fontWeight: 500, background: opt === payload.correct ? "var(--success-bg)" : "rgba(255,255,255,0.04)", border: `1px solid ${opt === payload.correct ? "var(--success-border)" : "var(--border)"}`, color: opt === payload.correct ? "var(--success)" : "var(--text-primary)" }}>
                  {opt === payload.correct && "✓ "}<RubyText text={opt} segments={annotations.options?.[i]} />
                </span>
              ))}
            </div>
          </div>
        )}
        {payload.explanation && <PayloadRow label="Explanation" value={payload.explanation} segments={annotations.explanation} />}
      </div>
    );
  }

  return null;
}

function PayloadRow({ label, value, highlight, segments }) {
  return (
    <div>
      <p style={fieldLabel}>{label}</p>
      <p style={{ fontSize: "14px", color: highlight ? "var(--text-primary)" : "var(--text-secondary)", fontWeight: highlight ? 500 : 400, marginTop: "4px", lineHeight: 1.9, padding: highlight ? "8px 12px" : 0, background: highlight ? "rgba(255,255,255,0.03)" : "transparent", borderRadius: highlight ? "var(--radius-sm)" : 0, border: highlight ? "1px solid var(--border)" : "none" }}>
        <RubyText text={value} segments={segments} />
      </p>
    </div>
  );
}

const fieldLabel = { fontSize: "10px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" };
const altChip = { fontSize: "13px", color: "var(--text-secondary)", padding: "4px 10px", background: "rgba(255,255,255,0.03)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", display: "block", width: "fit-content" };
const optionRow = (correct) => ({ display: "flex", alignItems: "center", gap: "10px", padding: "8px 12px", borderRadius: "var(--radius-sm)", background: correct ? "var(--success-bg)" : "rgba(255,255,255,0.02)", border: `1px solid ${correct ? "var(--success-border)" : "var(--border)"}` });
const optionIndex = (correct) => ({ width: "22px", height: "22px", borderRadius: "50%", background: correct ? "var(--success)" : "rgba(255,255,255,0.08)", color: correct ? "#fff" : "var(--text-muted)", fontSize: "11px", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontFamily: "var(--font-mono)" });
const correctMark = { marginLeft: "auto", fontSize: "11px", fontWeight: 600, color: "var(--success)" };
