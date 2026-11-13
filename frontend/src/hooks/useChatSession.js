import { useState, useCallback, useRef } from "react";
import { identityHeaders } from "../utils/identity";

const API_BASE = "/api/chat";

/**
 * Hook holding the whole chatbot logic:
 * - session (session_id)
 * - messages (role: 'user' | 'assistant')
 * - phase (negotiating | searching | ready | in_exercise | reviewing)
 * - ready exercises
 * - SSE stream consumption
 *
 * A session is bound to one track (sent when the session is created); the
 * parent remounts the chat when the profile or track changes.
 */
export function useChatSession(track) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [phase, setPhase] = useState("negotiating");
  const [exercises, setExercises] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);

  // ref to update the assistant text incrementally without a stale closure
  const assistantTextRef = useRef("");

  /**
   * Consumes an SSE stream from a fetch Response and calls onEvent for each event.
   * Handles partial buffer chunks and closes the reader cleanly.
   */
  const _parseSSEStream = useCallback(async (response, onEvent) => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        let chunk;
        try {
          chunk = await reader.read();
        } catch {
          // connection dropped — exit silently
          break;
        }

        const { done, value } = chunk;
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Split SSE events: each event ends with \n\n
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? ""; // keep the last incomplete chunk

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            onEvent(event);
          } catch {
            // malformed event, ignore it
          }
        }
      }
    } finally {
      try {
        reader.cancel();
      } catch {
        // ignored — the reader may already be closed
      }
    }
  }, []);

  /**
   * Sends a chat message.
   * Creates the session automatically when session_id is null.
   */
  const sendMessage = useCallback(async (text) => {
    if (streaming) return;
    if (!text.trim()) return;

    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setStreaming(true);
    assistantTextRef.current = "";

    // Keep session_id in a local variable to avoid a stale closure on the
    // session_created event
    let resolvedSessionId = sessionId;

    try {
      const response = await fetch(`${API_BASE}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...identityHeaders() },
        body: JSON.stringify({ session_id: resolvedSessionId, track, message: text }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP error ${response.status}`);
      }

      await _parseSSEStream(response, (event) => {
        switch (event.type) {
          case "session_created":
            resolvedSessionId = event.session_id;
            setSessionId(event.session_id);
            break;

          case "text_delta":
            assistantTextRef.current += event.text;
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "assistant") {
                return [
                  ...prev.slice(0, -1),
                  { role: "assistant", content: assistantTextRef.current },
                ];
              }
              return [...prev, { role: "assistant", content: assistantTextRef.current }];
            });
            break;

          case "text_reset":
            // The reply just shown was dropped by the server (a tool call
            // written as text): remove it, the retry streams a new one.
            assistantTextRef.current = "";
            setMessages((prev) => (prev[prev.length - 1]?.role === "assistant" ? prev.slice(0, -1) : prev));
            break;

          case "phase_change":
            setPhase(event.phase);
            if (event.phase === "ready" && event.exercises) {
              setExercises(event.exercises);
            }
            break;

          case "error":
            setError(event.message);
            break;

          case "done":
            // the server closed the stream cleanly
            break;

          default:
            break;
        }
      });
    } catch (err) {
      setError(err.message || "Network error");
    } finally {
      setStreaming(false);
    }
  }, [sessionId, streaming, track, _parseSSEStream]);

  /**
   * Switches the phase to in_exercise (called by the "Start exercises" button).
   */
  const startExercises = useCallback(() => {
    setPhase("in_exercise");
  }, []);

  /**
   * Sends the exercise results to the backend and streams back the feedback.
   */
  const submitResults = useCallback(async (results) => {
    if (!sessionId) return;
    setError(null);
    setPhase("reviewing");
    setStreaming(true);
    assistantTextRef.current = "";

    try {
      const response = await fetch(`${API_BASE}/sessions/${sessionId}/exercise-results`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...identityHeaders() },
        body: JSON.stringify({ results }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP error ${response.status}`);
      }

      await _parseSSEStream(response, (event) => {
        switch (event.type) {
          case "text_delta":
            assistantTextRef.current += event.text;
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "assistant") {
                return [
                  ...prev.slice(0, -1),
                  { role: "assistant", content: assistantTextRef.current },
                ];
              }
              return [...prev, { role: "assistant", content: assistantTextRef.current }];
            });
            break;

          case "phase_change":
            setPhase(event.phase);
            break;

          case "error":
            setError(event.message);
            break;

          case "done":
            break;

          default:
            break;
        }
      });
    } catch (err) {
      setError(err.message || "Network error");
      setPhase("negotiating");
    } finally {
      setStreaming(false);
    }
  }, [sessionId, _parseSSEStream]);

  /**
   * "New chat": forgets the session on the server (best-effort) and clears
   * the local state; the next message creates a fresh session.
   */
  const resetChat = useCallback(() => {
    if (streaming) return;
    if (sessionId) {
      fetch(`${API_BASE}/sessions/${sessionId}`, {
        method: "DELETE",
        headers: identityHeaders(),
      }).catch(() => {});
    }
    setSessionId(null);
    setMessages([]);
    setPhase("negotiating");
    setExercises([]);
    setError(null);
    assistantTextRef.current = "";
  }, [sessionId, streaming]);

  return {
    sessionId,
    messages,
    phase,
    exercises,
    streaming,
    error,
    sendMessage,
    startExercises,
    submitResults,
    resetChat,
  };
}
