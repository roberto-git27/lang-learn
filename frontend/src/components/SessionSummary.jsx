import { exerciseTypeLabel, PROMPT_FIELD } from "../utils/exerciseTypes";
import { RubyText } from "./RubyText";

/**
 * End-of-session summary: score, per-type breakdown and the numbered list of
 * mistakes (numbers are positions in the session, the same ones the chat
 * model uses). Without `onRestart` (chat flow) there is no restart button.
 */
export function SessionSummary({ results, onRestart }) {
  const total = results.length;
  const correctCount = results.filter((r) => r.result.correct).length;
  const score = total > 0 ? Math.round((correctCount / total) * 100) : 0;

  const scoreLabel =
    score >= 90 ? "Excellent!" :
    score >= 70 ? "Great!" :
    score >= 50 ? "Good" : "Keep practicing";

  const scoreColor =
    score >= 70 ? "var(--success)" :
    score >= 50 ? "#f59e0b" : "var(--error)";

  const scoreBg =
    score >= 70 ? "var(--success-bg)" :
    score >= 50 ? "rgba(245,158,11,0.1)" : "var(--error-bg)";

  const scoreBorder =
    score >= 70 ? "var(--success-border)" :
    score >= 50 ? "rgba(245,158,11,0.3)" : "var(--error-border)";

  // Per-type breakdown
  const byType = {};
  for (const { exercise, result } of results) {
    const t = exercise.exercise_type;
    if (!byType[t]) byType[t] = { correct: 0, total: 0 };
    byType[t].total++;
    if (result.correct) byType[t].correct++;
  }

  // Average similarity for translation exercises
  const withSim = results.filter((r) => r.result.similarity_score !== undefined);
  const avgSim = withSim.length > 0
    ? withSim.reduce((s, r) => s + r.result.similarity_score, 0) / withSim.length
    : null;

  const wrong = results
    .map((r, i) => ({ ...r, number: i + 1 }))
    .filter((r) => !r.result.correct);

  return (
    <div style={wrapStyle}>
      {/* Score hero */}
      <div style={card}>
        <div style={scoreRow}>
          <div style={{ ...scoreDial, borderColor: scoreColor, background: scoreBg }}>
            <span style={{ fontSize: "26px", fontWeight: 800, color: scoreColor, lineHeight: 1 }}>{score}%</span>
          </div>
          <div>
            <p style={{ fontSize: "22px", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em", marginBottom: "6px" }}>
              {scoreLabel}
            </p>
            <p style={{ fontSize: "15px", color: "var(--text-secondary)" }}>
              {correctCount} of {total} {total === 1 ? "exercise correct" : "exercises correct"}
            </p>
            {avgSim !== null && (
              <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "6px", fontFamily: "var(--font-mono)" }}>
                average similarity (translations): {Math.round(avgSim * 100)}%
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Per-type breakdown — only shown when more than one type */}
      {Object.keys(byType).length > 1 && (
        <div style={card}>
          <p style={sectionLabel}>By exercise type</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {Object.entries(byType).map(([type, { correct: c, total: t }]) => {
              const pct = Math.round((c / t) * 100);
              const barColor = pct === 100 ? "var(--success)" : pct >= 50 ? "#f59e0b" : "var(--error)";
              return (
                <div key={type} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <span style={{ fontSize: "13px", color: "var(--text-secondary)", minWidth: "160px" }}>
                    {exerciseTypeLabel(type)}
                  </span>
                  <div style={{ flex: 1, height: "6px", background: "rgba(255,255,255,0.06)", borderRadius: "3px", overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${pct}%`, background: barColor, borderRadius: "3px", transition: "width 0.7s ease" }} />
                  </div>
                  <span style={{ fontSize: "12px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", minWidth: "32px", textAlign: "right" }}>
                    {c}/{t}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Wrong answers review */}
      {wrong.length > 0 && (
        <div style={card}>
          <p style={sectionLabel}>Mistakes to review — {wrong.length}</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {wrong.map(({ exercise, result, number }) => {
              const promptField = PROMPT_FIELD[exercise.exercise_type];
              const annotations = exercise.annotations || {};
              return (
                <div key={number} style={wrongItem}>
                  <p style={wrongType}>#{number} · {exerciseTypeLabel(exercise.exercise_type)}</p>
                  {promptField && (
                    <p style={wrongPrompt}>
                      <RubyText text={exercise.payload[promptField]} segments={annotations[promptField]} />
                    </p>
                  )}
                  {result.user_answer && (
                    <p style={wrongAnswer(false)}>
                      <span style={answerLabel}>Your answer</span> {result.user_answer}
                    </p>
                  )}
                  <p style={wrongAnswer(true)}>
                    <span style={answerLabel}>Correct answer</span> {result.correct_answer}
                  </p>
                  {result.explanation && (
                    <p style={explanationStyle}>
                      <RubyText text={result.explanation} segments={annotations.explanation} />
                    </p>
                  )}
                  {result.similarity_score !== undefined && (
                    <p style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: "4px" }}>
                      similarity: {Math.round(result.similarity_score * 100)}%
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Action */}
      {onRestart && (
        <button onClick={onRestart} style={restartBtn}>
          New session →
        </button>
      )}

      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

/* ── Styles ── */

const wrapStyle = {
  width: "100%",
  maxWidth: "680px",
  display: "flex",
  flexDirection: "column",
  gap: "16px",
  animation: "fadeSlideIn 0.4s ease forwards",
};

const card = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  padding: "28px 32px",
  boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
};

const scoreRow = {
  display: "flex",
  alignItems: "center",
  gap: "28px",
  flexWrap: "wrap",
};

const scoreDial = {
  width: "92px",
  height: "92px",
  borderRadius: "50%",
  border: "3px solid",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
};

const sectionLabel = {
  fontSize: "10px",
  fontWeight: 600,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
  marginBottom: "16px",
};

const wrongItem = {
  borderLeft: "2px solid var(--error-border)",
  paddingLeft: "16px",
};

const wrongType = {
  fontSize: "11px",
  fontFamily: "var(--font-mono)",
  color: "var(--text-muted)",
  marginBottom: "6px",
};

const wrongPrompt = {
  fontSize: "14px",
  color: "var(--text-secondary)",
  marginBottom: "8px",
  lineHeight: 1.9,
};

const wrongAnswer = (correct) => ({
  fontSize: "13px",
  color: correct ? "var(--success)" : "var(--error)",
  marginBottom: "4px",
  lineHeight: 1.5,
});

const answerLabel = {
  color: "var(--text-muted)",
  marginRight: "6px",
};

const explanationStyle = {
  fontSize: "12px",
  color: "var(--text-muted)",
  fontStyle: "italic",
  marginTop: "6px",
  lineHeight: 1.9,
};

const restartBtn = {
  padding: "14px 32px",
  background: "var(--accent)",
  color: "#fff",
  borderRadius: "var(--radius-sm)",
  fontSize: "15px",
  fontWeight: 600,
  letterSpacing: "0.02em",
  cursor: "pointer",
  boxShadow: "0 4px 20px rgba(99,102,241,0.35)",
  transition: "all var(--transition)",
  alignSelf: "flex-start",
};
