import { useState } from "react";
import { exerciseTypeLabel } from "../utils/exerciseTypes";
import { DIFFICULTY_LEVELS } from "../utils/levels";
import { ui } from "../i18n";

// Practice filters: the track comes from the header, so only type and difficulty remain.
export function FilterBar({ track, onStart }) {
  const [difficulty, setDifficulty] = useState("");
  const [exerciseType, setExerciseType] = useState("");

  const handleStart = () => {
    onStart({
      difficulty: difficulty ? parseInt(difficulty) : undefined,
      exercise_type: exerciseType || undefined,
    });
  };

  return (
    <div style={wrapStyle}>
      <div style={gridStyle}>
        {/* Exercise type */}
        <div style={fieldStyle}>
          <label style={labelStyle}>{ui.filters.type}</label>
          <select
            value={exerciseType}
            onChange={(e) => setExerciseType(e.target.value)}
            style={selectStyle}
          >
            <option value="">{ui.filters.allTypes}</option>
            {track.exercise_types.map(({ code }) => (
              <option key={code} value={code}>{exerciseTypeLabel(code)}</option>
            ))}
          </select>
        </div>

        {/* Difficulty */}
        <div style={fieldStyle}>
          <label style={labelStyle}>{ui.filters.difficulty}</label>
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            style={selectStyle}
          >
            <option value="">{ui.filters.anyDifficulty}</option>
            {DIFFICULTY_LEVELS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>

      <button onClick={handleStart} style={startButtonStyle}>
        {ui.filters.start}
      </button>
      <p style={{ textAlign: "center", fontSize: "11px", color: "var(--text-muted)", marginTop: "10px" }}>
        {ui.filters.sessionSize}
      </p>

      <style>{hoverStyle}</style>
    </div>
  );
}

const wrapStyle = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  padding: "28px 32px",
  width: "100%",
  maxWidth: "620px",
  boxShadow: "0 24px 64px rgba(0,0,0,0.4)",
};

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: "16px",
  marginBottom: "24px",
};

const fieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const labelStyle = {
  fontSize: "10px",
  fontWeight: 600,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

const selectStyle = {
  background: "rgba(255,255,255,0.04)",
  border: "1.5px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "10px 12px",
  color: "var(--text-primary)",
  fontSize: "14px",
  outline: "none",
  cursor: "pointer",
  appearance: "none",
  WebkitAppearance: "none",
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%238b8b9e' d='M6 8L1 3h10z'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  paddingRight: "32px",
};

const startButtonStyle = {
  width: "100%",
  padding: "14px",
  background: "var(--accent)",
  color: "#fff",
  borderRadius: "var(--radius-sm)",
  fontSize: "15px",
  fontWeight: 600,
  letterSpacing: "0.02em",
  transition: "all var(--transition)",
  boxShadow: "0 4px 20px rgba(99,102,241,0.35)",
  cursor: "pointer",
};

const hoverStyle = `
  select:focus { border-color: var(--border-focus) !important; }
  button:hover { filter: brightness(1.1); transform: translateY(-1px); }
`;
