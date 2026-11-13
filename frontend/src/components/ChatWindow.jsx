import { useState, useRef, useEffect } from "react";
import { useChatSession } from "../hooks/useChatSession";
import { SessionView } from "./SessionView";
import { SessionSummary } from "./SessionSummary";

/** Strips markdown formatting from the assistant's text. */
function stripMarkdown(text) {
  return text
    .replace(/^#{1,6}\s+/gm, "")              // # Headings
    .replace(/\*\*(.+?)\*\*/gs, "$1")          // **bold**
    .replace(/\*(.+?)\*/gs, "$1")              // *italic*
    .replace(/`(.+?)`/g, "$1")                 // `code`
    .replace(/^\s*[-*+]\s+/gm, "• ")           // - bullet lists
    .replace(/^\s*\d+\.\s+/gm, "")            // 1. numbered lists
    .replace(/\[(.+?)\]\(.+?\)/g, "$1")        // [link](url)
    .replace(/_{1,2}(.+?)_{1,2}/gs, "$1")      // __bold__ / _italic_
    .trim();
}

/**
 * ChatWindow — conversational UI for negotiating an exercise session.
 *
 * Phase flow:
 *   negotiating  → chat active, the user describes what they want
 *   searching    → the assistant called the tool, loader shown
 *   ready        → exercises ready, "Start exercises" button visible
 *   in_exercise  → SessionView in the foreground
 *   reviewing    → backend generates the feedback (short loader)
 */
export function ChatWindow({ track }) {
  const {
    messages,
    phase,
    exercises,
    streaming,
    error,
    sendMessage,
    startExercises,
    submitResults,
    resetChat,
  } = useChatSession(track.code);

  const [inputValue, setInputValue] = useState("");
  // Summaries of the sessions completed in this chat, each shown after the
  // message that was last when the session ended: [{ afterIndex, results }]
  const [summaries, setSummaries] = useState([]);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, summaries]);

  // Focus the input when the chat becomes active again
  useEffect(() => {
    if (phase === "negotiating" && !streaming) {
      inputRef.current?.focus();
    }
  }, [phase, streaming]);

  const handleSend = () => {
    const text = inputValue.trim();
    if (!text || streaming || phase === "searching" || phase === "in_exercise") return;
    setInputValue("");
    sendMessage(text);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSessionComplete = (results) => {
    const items = results.map((r) => ({ exercise: r.exercise, result: r.result }));
    setSummaries((prev) => [...prev, { afterIndex: messages.length, results: items }]);
    submitResults(items);
  };

  const summariesAfter = (index) =>
    summaries.filter((s) => s.afterIndex === index).map((s, k) => (
      <div key={`summary-${index}-${k}`} style={summaryWrapStyle}>
        <SessionSummary results={s.results} />
      </div>
    ));

  const inputDisabled = streaming || phase === "searching" || phase === "in_exercise" || phase === "reviewing";

  const handleNewChat = () => {
    if (inputDisabled) return;
    resetChat();
    setSummaries([]);
    setInputValue("");
  };

  // in_exercise phase: show SessionView full-width in the column
  if (phase === "in_exercise" && exercises.length > 0) {
    return (
      <div style={fullColumnStyle}>
        <SessionView exercises={exercises} onComplete={handleSessionComplete} />
      </div>
    );
  }

  return (
    <div style={wrapStyle}>
      {/* Messages area */}
      <div style={messagesAreaStyle}>
        {messages.length === 0 && (
          <div style={emptyStateStyle}>
            <p style={emptyTitleStyle}>Hi! I'm your language assistant.</p>
            <p style={emptySubStyle}>
              You are practicing {track.name}. Tell me your level and maybe a specific topic,
              and I will prepare a tailored exercise session for you.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i}>
            <div style={bubbleWrapStyle(msg.role)}>
              <div style={bubbleStyle(msg.role)}>
                <p style={bubbleTextStyle}>
                  {msg.role === "assistant" ? stripMarkdown(msg.content) : msg.content}
                </p>
              </div>
            </div>
            {summariesAfter(i + 1)}
          </div>
        ))}

        {/* Loader during searching / reviewing */}
        {(phase === "searching" || phase === "reviewing") && (
          <div style={bubbleWrapStyle("assistant")}>
            <div style={{ ...bubbleStyle("assistant"), ...loaderBubbleStyle }}>
              <span style={dotStyle(0)} />
              <span style={dotStyle(1)} />
              <span style={dotStyle(2)} />
            </div>
          </div>
        )}

        {/* "Start exercises" button once ready */}
        {phase === "ready" && exercises.length > 0 && (
          <div style={readyBannerStyle}>
            <p style={readyTextStyle}>
              Found <strong>{exercises.length}</strong>{" "}
              {exercises.length === 1 ? "exercise" : "exercises"} for you!
            </p>
            <button onClick={startExercises} style={startBtnStyle}>
              Start exercises →
            </button>
          </div>
        )}

        {error && (
          <div style={errorBannerStyle}>
            <span style={{ fontSize: "18px" }}>⚠</span>
            <p style={{ color: "var(--error)", fontSize: "13px" }}>{error}</p>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* New chat: drops the whole conversation (history and summaries) */}
      {messages.length > 0 && (
        <div style={newChatRowStyle}>
          <button
            onClick={handleNewChat}
            disabled={inputDisabled}
            style={newChatBtnStyle(!inputDisabled)}
            title="Start over: the current conversation is cleared"
          >
            + New chat
          </button>
        </div>
      )}

      {/* Input area */}
      <div style={inputAreaStyle}>
        <textarea
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={inputDisabled}
          placeholder={
            phase === "searching"
              ? "Looking for exercises…"
              : phase === "reviewing"
              ? "Analyzing your results…"
              : phase === "ready"
              ? "Start the exercises or keep chatting"
              : summaries.length > 0
              ? "Ask about a mistake (e.g. \"why is #3 wrong?\") or ask for more exercises"
              : "Type a message…"
          }
          rows={2}
          style={{
            ...textareaStyle,
            ...(inputDisabled ? textareaDisabledStyle : {}),
          }}
        />
        <button
          onClick={handleSend}
          disabled={inputDisabled || !inputValue.trim()}
          style={sendBtnStyle(!!inputValue.trim() && !inputDisabled)}
        >
          {streaming ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M1 8h14M9 3l6 5-6 5" stroke="currentColor" strokeWidth="1.5"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      </div>

      <p style={hintStyle}>Enter to send · Shift+Enter for a new line</p>

      <style>{animStyles}</style>
    </div>
  );
}

/* ── Styles ── */

const wrapStyle = {
  display: "flex",
  flexDirection: "column",
  height: "calc(100vh - 120px)",
  width: "100%",
  maxWidth: "720px",
};

const newChatRowStyle = {
  display: "flex",
  justifyContent: "flex-end",
  padding: "0 4px 8px",
};

const newChatBtnStyle = (enabled) => ({
  background: "transparent",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm, 6px)",
  color: enabled ? "var(--text-secondary)" : "var(--text-muted)",
  fontSize: "12px",
  padding: "4px 10px",
  cursor: enabled ? "pointer" : "not-allowed",
  opacity: enabled ? 1 : 0.5,
});

const summaryWrapStyle = {
  display: "flex",
  justifyContent: "center",
  margin: "8px 0 16px",
};

const fullColumnStyle = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  width: "100%",
};

const messagesAreaStyle = {
  flex: 1,
  overflowY: "auto",
  display: "flex",
  flexDirection: "column",
  gap: "12px",
  padding: "8px 4px 16px",
  scrollbarWidth: "thin",
  scrollbarColor: "var(--border) transparent",
};

const emptyStateStyle = {
  padding: "40px 24px",
  textAlign: "center",
};

const emptyTitleStyle = {
  fontSize: "18px",
  fontWeight: 600,
  color: "var(--text-primary)",
  marginBottom: "10px",
};

const emptySubStyle = {
  fontSize: "14px",
  color: "var(--text-secondary)",
  lineHeight: 1.7,
  maxWidth: "480px",
  margin: "0 auto",
};

const bubbleWrapStyle = (role) => ({
  display: "flex",
  justifyContent: role === "user" ? "flex-end" : "flex-start",
});

const bubbleStyle = (role) => ({
  maxWidth: "78%",
  padding: "12px 16px",
  borderRadius: role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
  background: role === "user"
    ? "var(--accent)"
    : "var(--bg-card)",
  border: role === "user"
    ? "none"
    : "1px solid var(--border)",
  boxShadow: role === "user"
    ? "0 2px 12px rgba(99,102,241,0.3)"
    : "0 2px 8px rgba(0,0,0,0.2)",
});

const bubbleTextStyle = {
  fontSize: "14px",
  lineHeight: 1.65,
  color: "var(--text-primary)",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const loaderBubbleStyle = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  padding: "14px 18px",
};

const dotStyle = (i) => ({
  display: "inline-block",
  width: "7px",
  height: "7px",
  borderRadius: "50%",
  background: "var(--text-muted)",
  animation: `chatDot 1.2s ease-in-out ${i * 0.2}s infinite`,
});

const readyBannerStyle = {
  display: "flex",
  alignItems: "center",
  gap: "16px",
  padding: "14px 20px",
  background: "rgba(99,102,241,0.1)",
  border: "1px solid rgba(99,102,241,0.25)",
  borderRadius: "var(--radius)",
  flexWrap: "wrap",
};

const readyTextStyle = {
  fontSize: "14px",
  color: "var(--text-secondary)",
  flex: 1,
};

const startBtnStyle = {
  padding: "10px 22px",
  background: "var(--accent)",
  color: "#fff",
  borderRadius: "var(--radius-sm)",
  fontSize: "14px",
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  boxShadow: "0 4px 16px rgba(99,102,241,0.35)",
  transition: "all var(--transition)",
};

const errorBannerStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  padding: "12px 16px",
  background: "var(--error-bg)",
  border: "1px solid var(--error-border)",
  borderRadius: "var(--radius)",
};

const inputAreaStyle = {
  display: "flex",
  gap: "10px",
  alignItems: "flex-end",
  padding: "12px 0 0",
  borderTop: "1px solid var(--border)",
};

const textareaStyle = {
  flex: 1,
  background: "rgba(255,255,255,0.04)",
  border: "1.5px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: "12px 14px",
  color: "var(--text-primary)",
  fontSize: "14px",
  lineHeight: 1.6,
  resize: "none",
  outline: "none",
  transition: "border-color var(--transition)",
  fontFamily: "inherit",
};

const textareaDisabledStyle = {
  opacity: 0.5,
  cursor: "not-allowed",
};

const sendBtnStyle = (active) => ({
  width: "42px",
  height: "42px",
  borderRadius: "var(--radius-sm)",
  background: active ? "var(--accent)" : "rgba(99,102,241,0.2)",
  color: active ? "#fff" : "rgba(255,255,255,0.3)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: active ? "pointer" : "not-allowed",
  transition: "all var(--transition)",
  flexShrink: 0,
  boxShadow: active ? "0 4px 12px rgba(99,102,241,0.3)" : "none",
});

const hintStyle = {
  fontSize: "10px",
  color: "var(--text-muted)",
  textAlign: "right",
  marginTop: "4px",
  letterSpacing: "0.03em",
};

const animStyles = `
  @keyframes chatDot {
    0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
    40% { transform: scale(1); opacity: 1; }
  }
  textarea:focus {
    border-color: var(--border-focus) !important;
    background: rgba(99,102,241,0.04) !important;
  }
  button:hover:not(:disabled) {
    filter: brightness(1.12);
    transform: translateY(-1px);
  }
`;
