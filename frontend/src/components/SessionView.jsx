import { useState } from "react";
import { ExerciseCard } from "./ExerciseCard";

// Furigana are shown by default up to this difficulty (1–4 = up to JLPT N4,
// beginner levels, D-04); the learner's toggle then applies to the rest of the session.
const FURIGANA_DEFAULT_MAX_DIFFICULTY = 4;

export function SessionView({ exercises, onComplete }) {
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState([]);
  const [furiganaChoice, setFuriganaChoice] = useState(null); // null = default by difficulty

  const exercise = exercises[index];
  const showFurigana = furiganaChoice ?? exercise.difficulty <= FURIGANA_DEFAULT_MAX_DIFFICULTY;
  const isLast = index === exercises.length - 1;
  const progressPct = (index / exercises.length) * 100;

  const handleResult = (result) => {
    setResults((prev) => [...prev, { exercise, result }]);
  };

  const handleNext = () => {
    if (isLast) {
      onComplete(results);
    } else {
      setIndex((i) => i + 1);
    }
  };

  return (
    <div style={wrapStyle}>
      {/* Progress bar */}
      <div style={progressWrap}>
        <div style={progressHeader}>
          <span style={progressLabel}>Exercise {index + 1} of {exercises.length}</span>
          <span style={progressLabel}>{Math.round(progressPct)}% complete</span>
        </div>
        <div style={progressTrack}>
          <div style={{ ...progressFill, width: `${progressPct}%` }} />
        </div>
      </div>

      <ExerciseCard
        key={exercise.id}
        exercise={exercise}
        onResult={handleResult}
        onNext={handleNext}
        isLast={isLast}
        showFurigana={showFurigana}
        onToggleFurigana={() => setFuriganaChoice(!showFurigana)}
      />
    </div>
  );
}

const wrapStyle = {
  width: "100%",
  maxWidth: "680px",
  display: "flex",
  flexDirection: "column",
  gap: "20px",
};

const progressWrap = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: "14px 20px",
};

const progressHeader = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "10px",
};

const progressLabel = {
  fontSize: "11px",
  fontWeight: 600,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

const progressTrack = {
  height: "5px",
  background: "rgba(255,255,255,0.06)",
  borderRadius: "3px",
  overflow: "hidden",
};

const progressFill = {
  height: "100%",
  background: "var(--accent)",
  borderRadius: "3px",
  transition: "width 0.5s ease",
};
