import { useState, useRef, useEffect } from "react";
import { LangBadge } from "./LangBadge";
import { DifficultyDots } from "./DifficultyDots";
import { RubyText } from "./RubyText";
import { normalize, similarityRatio } from "../utils/similarity";
import { isAcceptedRomaji } from "../utils/romaji";
import { PROMPT_FIELD, TRANSLATION_BEFORE_ANSWER } from "../utils/exerciseTypes";
import { ui } from "../i18n";

// Answered by picking one of payload.options (the rest are typed).
const OPTION_TYPES = new Set(["multiple_choice", "fill_blank", "kanji_reading", "kanji_writing"]);

function shuffledIndices(n) {
  const order = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}

export function ExerciseCard({ exercise, onNext, onResult, isLast, showFurigana, onToggleFurigana }) {
  const [answer, setAnswer] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(null);
  const [result, setResult] = useState(null);
  // Display position -> index in payload.options (options are shuffled by index
  // so each keeps its own furigana from annotations.options).
  const [optionOrder, setOptionOrder] = useState([]);
  const [showTranslation, setShowTranslation] = useState(false);
  const inputRef = useRef(null);

  const payload = exercise.payload || {};
  const annotations = exercise.annotations || {};
  const exType = exercise.exercise_type;
  const hasOptions = OPTION_TYPES.has(exType);
  const promptField = PROMPT_FIELD[exType];

  useEffect(() => {
    setAnswer("");
    setSelectedIndex(null);
    setResult(null);
    setShowTranslation(false);
    setOptionOrder(hasOptions ? shuffledIndices(payload.options?.length ?? 0) : []);
    if (!hasOptions) setTimeout(() => inputRef.current?.focus(), 100);
  }, [exercise.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const isCorrectOption = (optionIndex) =>
    exType === "fill_blank"
      ? normalize(payload.options[optionIndex]) === normalize(payload.correct || "")
      : optionIndex === payload.correct_index;

  const handleSubmit = () => {
    let res;
    if (hasOptions) {
      if (selectedIndex === null) return;
      const chosen = optionOrder[selectedIndex];
      const correctIndex = payload.options.findIndex((_, i) => isCorrectOption(i));
      res = {
        correct: isCorrectOption(chosen),
        user_answer: payload.options[chosen] ?? "",
        correct_answer: payload.options[correctIndex] ?? "",
        explanation: payload.explanation,
      };
    } else if (exType === "romaji_input") {
      if (!answer.trim()) return;
      res = {
        correct: isAcceptedRomaji(answer, payload.accepted || []),
        user_answer: answer.trim(),
        correct_answer: payload.expected,
        explanation: payload.explanation,
      };
    } else {
      // translate_rev: typed answer in the base language, graded by similarity
      if (!answer.trim()) return;
      const expected = payload.expected || "";
      const userNorm = normalize(answer.trim());
      let bestSim = similarityRatio(userNorm, normalize(expected));
      for (const alt of payload.alternatives || []) {
        bestSim = Math.max(bestSim, similarityRatio(userNorm, normalize(alt)));
      }
      res = {
        correct: bestSim >= 0.9,
        user_answer: answer.trim(),
        correct_answer: expected,
        similarity_score: Math.round(bestSim * 10000) / 10000,
      };
    }

    setResult(res);
    onResult?.(res);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      result ? onNext() : handleSubmit();
    }
  };

  const tags = exercise.topics ?? [];
  const hasFurigana = Object.values(annotations).flat(2).some((seg) => seg?.reading);
  const sourceLangName = ui.exercise.languageNames[exercise.source_language] ?? exercise.source_language;
  const sourceLabel = ui.exercise.instructions[exType] ?? ui.exercise.translateInto(sourceLangName);

  // The phrase in the base language: on request before answering (where it
  // doesn't give the answer away), always after.
  const translation = exercise.phrase_translations?.find((t) => t.language === exercise.source_language)?.content;
  const translationAllowed = translation && exType !== "translate_rev" && (result || TRANSLATION_BEFORE_ANSWER.has(exType));

  const canSubmit = hasOptions ? selectedIndex !== null : !!answer.trim();

  const optionStyle = (displayIdx, optionIndex) => {
    const isSelected = selectedIndex === displayIdx;
    let borderColor = "var(--border)";
    let background = "rgba(255,255,255,0.03)";
    let color = "var(--text-primary)";
    if (result && isCorrectOption(optionIndex)) {
      borderColor = "var(--success-border)";
      background = "var(--success-bg)";
      color = "var(--success)";
    } else if (result && isSelected) {
      borderColor = "var(--error-border)";
      background = "var(--error-bg)";
      color = "var(--error)";
    } else if (isSelected) {
      borderColor = "var(--border-focus)";
      background = "rgba(99,102,241,0.08)";
    }
    return { borderColor, background, color };
  };

  return (
    <div className="exercise-card" style={cardStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <LangBadge code={exercise.source_language} />
          <ArrowIcon />
          <LangBadge code={exercise.target_language} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {hasFurigana && (
            <button onClick={onToggleFurigana} title={ui.exercise.furiganaToggle} style={furiganaToggleStyle(showFurigana)}>
              ふりがな
            </button>
          )}
          <DifficultyDots value={exercise.difficulty} />
        </div>
      </div>

      {/* Tags */}
      {tags.length > 0 && (
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "28px" }}>
          {tags.map((tag) => (
            <span key={tag} style={tagStyle}>{tag}</span>
          ))}
        </div>
      )}

      {/* Prompt */}
      <div style={sourceBlockStyle}>
        <span style={labelStyle}>{sourceLabel}</span>
        <p style={sentenceStyle}>
          <RubyText text={payload[promptField] ?? ""} segments={annotations[promptField]} showFurigana={showFurigana} />
        </p>
        {translationAllowed && (
          showTranslation || result
            ? <p style={translationStyle}>{translation}</p>
            : <button onClick={() => setShowTranslation(true)} style={translationButtonStyle}>{ui.exercise.showTranslation}</button>
        )}
      </div>

      {/* Four-option list: multiple choice, kanji reading/writing */}
      {hasOptions && exType !== "fill_blank" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "20px" }}>
          {optionOrder.map((optionIndex, displayIdx) => {
            const { borderColor, background, color } = optionStyle(displayIdx, optionIndex);
            return (
              <button
                key={displayIdx}
                onClick={() => !result && setSelectedIndex(displayIdx)}
                disabled={!!result}
                style={{
                  textAlign: "left",
                  padding: "14px 18px",
                  background,
                  border: `1.5px solid ${borderColor}`,
                  borderRadius: "var(--radius)",
                  color,
                  fontSize: "15px",
                  lineHeight: 1.8,
                  cursor: result ? "default" : "pointer",
                  transition: "all var(--transition)",
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <span style={{
                  width: "22px",
                  height: "22px",
                  borderRadius: "50%",
                  border: `1.5px solid ${borderColor}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "11px",
                  fontWeight: 700,
                  flexShrink: 0,
                  color,
                }}>
                  {String.fromCharCode(65 + displayIdx)}
                </span>
                <span>
                  <RubyText text={payload.options[optionIndex]} segments={annotations.options?.[optionIndex]} showFurigana={showFurigana} />
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Fill-blank word options (always options: no typing in the target language) */}
      {exType === "fill_blank" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "20px" }}>
          {optionOrder.map((optionIndex, displayIdx) => {
            const { borderColor, background, color } = optionStyle(displayIdx, optionIndex);
            return (
              <button
                key={displayIdx}
                onClick={() => !result && setSelectedIndex(displayIdx)}
                disabled={!!result}
                style={{
                  padding: "10px 20px",
                  background,
                  border: `1.5px solid ${borderColor}`,
                  borderRadius: "var(--radius-sm)",
                  color,
                  fontSize: "15px",
                  fontWeight: 500,
                  lineHeight: 1.8,
                  cursor: result ? "default" : "pointer",
                  transition: "all var(--transition)",
                }}
              >
                <RubyText text={payload.options[optionIndex]} segments={annotations.options?.[optionIndex]} showFurigana={showFurigana} />
              </button>
            );
          })}
        </div>
      )}

      {/* Typed answer, always in Latin script: translation (base language) or romaji */}
      {!hasOptions && (
        <div style={{ marginBottom: "20px", position: "relative" }}>
          <span style={labelStyle}>{ui.exercise.yourAnswer}</span>
          <textarea
            ref={inputRef}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!!result}
            placeholder={exType === "romaji_input" ? ui.exercise.typeRomaji : ui.exercise.typeTranslation}
            rows={3}
            style={{
              ...inputStyle,
              ...(result && (result.correct
                ? { borderColor: "var(--success)", background: "var(--success-bg)" }
                : { borderColor: "var(--error)", background: "var(--error-bg)" })),
            }}
          />
        </div>
      )}

      {/* Feedback */}
      {result && (
        <div
          style={{
            ...feedbackBox,
            borderColor: result.correct ? "var(--success-border)" : "var(--error-border)",
            background: result.correct ? "var(--success-bg)" : "var(--error-bg)",
            marginBottom: "20px",
            animation: "fadeSlideIn 0.3s ease forwards",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
            <span style={{ fontSize: "22px", flexShrink: 0, marginTop: "1px" }}>
              {result.correct ? "✓" : "✗"}
            </span>
            <div>
              <p style={{
                fontWeight: 600,
                fontSize: "15px",
                color: result.correct ? "var(--success)" : "var(--error)",
                marginBottom: "6px",
              }}>
                {result.correct ? ui.exercise.correct : ui.exercise.wrong}
              </p>
              {!result.correct && !hasOptions && (
                <>
                  <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>
                    {ui.exercise.correctAnswer}
                  </p>
                  <p style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "14px",
                    color: "var(--text-primary)",
                    background: "rgba(255,255,255,0.04)",
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm)",
                    lineHeight: 1.5,
                  }}>
                    {result.correct_answer}
                  </p>
                </>
              )}
              {result.explanation && (
                <p style={{ marginTop: "8px", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  <RubyText text={result.explanation} segments={annotations.explanation} showFurigana={showFurigana} />
                </p>
              )}
              {result.similarity_score !== undefined && (
                <p style={{
                  marginTop: "8px",
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  fontFamily: "var(--font-mono)",
                }}>
                  {ui.exercise.similarity((result.similarity_score * 100).toFixed(0))}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Buttons */}
      <div style={{ display: "flex", gap: "12px" }}>
        {!result ? (
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={primaryButtonStyle(canSubmit)}
          >
            {ui.exercise.check}
          </button>
        ) : (
          <button onClick={onNext} style={nextButtonStyle}>
            {isLast ? ui.exercise.finish : ui.exercise.next}
          </button>
        )}
      </div>

      <p style={{ marginTop: "16px", fontSize: "11px", color: "var(--text-muted)" }}>
        {result ? ui.exercise.enterToContinue : ui.exercise.enterToConfirm}
      </p>

      <style>{animations}</style>
    </div>
  );
}

/* ── Sub-components ─────────────────────────── */

function ArrowIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ opacity: 0.4 }}>
      <path d="M1 7h12M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ── Styles ─────────────────────────────────── */

const cardStyle = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  padding: "36px",
  width: "100%",
  maxWidth: "620px",
  boxShadow: "0 24px 64px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.05) inset",
};

const headerStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "20px",
  flexWrap: "wrap",
  gap: "12px",
};

const tagStyle = {
  padding: "3px 10px",
  background: "rgba(99,102,241,0.1)",
  border: "1px solid rgba(99,102,241,0.2)",
  borderRadius: "999px",
  fontSize: "11px",
  color: "var(--accent-light)",
  fontWeight: 500,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const sourceBlockStyle = {
  background: "rgba(255,255,255,0.03)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: "20px 24px",
  marginBottom: "24px",
};

const labelStyle = {
  display: "block",
  fontSize: "10px",
  fontWeight: 600,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
  marginBottom: "10px",
};

const sentenceStyle = {
  fontSize: "20px",
  fontWeight: 500,
  lineHeight: 2,
  color: "var(--text-primary)",
  letterSpacing: "-0.01em",
};

const inputStyle = {
  width: "100%",
  background: "rgba(255,255,255,0.04)",
  border: "1.5px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: "14px 16px",
  color: "var(--text-primary)",
  fontSize: "15px",
  lineHeight: 1.6,
  resize: "vertical",
  outline: "none",
  transition: "border-color var(--transition), background var(--transition)",
  marginTop: "8px",
};

const feedbackBox = {
  border: "1px solid",
  borderRadius: "var(--radius)",
  padding: "16px 20px",
};

const primaryButtonStyle = (active) => ({
  padding: "13px 32px",
  background: active ? "var(--accent)" : "rgba(99,102,241,0.3)",
  color: active ? "#fff" : "rgba(255,255,255,0.4)",
  borderRadius: "var(--radius-sm)",
  fontSize: "14px",
  fontWeight: 600,
  letterSpacing: "0.02em",
  transition: "all var(--transition)",
  cursor: active ? "pointer" : "not-allowed",
  display: "flex",
  alignItems: "center",
  gap: "8px",
  boxShadow: active ? "0 4px 20px rgba(99,102,241,0.35)" : "none",
});

const nextButtonStyle = {
  padding: "13px 32px",
  background: "transparent",
  color: "var(--accent-light)",
  border: "1.5px solid rgba(99,102,241,0.4)",
  borderRadius: "var(--radius-sm)",
  fontSize: "14px",
  fontWeight: 600,
  letterSpacing: "0.02em",
  transition: "all var(--transition)",
  cursor: "pointer",
};

const translationStyle = {
  marginTop: "10px",
  fontSize: "14px",
  color: "var(--text-secondary)",
  fontStyle: "italic",
};

const translationButtonStyle = {
  marginTop: "10px",
  padding: "4px 12px",
  borderRadius: "999px",
  fontSize: "12px",
  background: "transparent",
  border: "1px solid var(--border)",
  color: "var(--text-muted)",
  cursor: "pointer",
};

const furiganaToggleStyle = (active) => ({
  padding: "3px 10px",
  borderRadius: "999px",
  fontSize: "11px",
  fontWeight: 600,
  background: active ? "rgba(99,102,241,0.15)" : "transparent",
  border: `1px solid ${active ? "rgba(99,102,241,0.4)" : "var(--border)"}`,
  color: active ? "var(--accent-light)" : "var(--text-muted)",
  cursor: "pointer",
});

const animations = `
@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
textarea:focus {
  border-color: var(--border-focus) !important;
  background: rgba(99,102,241,0.05) !important;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
}
button:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}
`;
