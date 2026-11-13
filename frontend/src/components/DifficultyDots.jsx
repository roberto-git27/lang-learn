import { MAX_DIFFICULTY } from "../utils/levels";

export function DifficultyDots({ value }) {
  const max = MAX_DIFFICULTY;
  const filled = Math.min(Math.max(value || 0, 0), max);

  const color =
    filled <= 3 ? "#10b981" :
    filled <= 6 ? "#f59e0b" :
    "#f43f5e";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
      {Array.from({ length: max }).map((_, i) => (
        <span
          key={i}
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: i < filled ? color : "var(--text-muted)",
            opacity: i < filled ? 1 : 0.3,
            transition: `background var(--transition)`,
          }}
        />
      ))}
      <span style={{
        marginLeft: "6px",
        fontSize: "11px",
        color: "var(--text-muted)",
        fontFamily: "var(--font-mono)",
      }}>
        {filled}/{max}
      </span>
    </div>
  );
}
