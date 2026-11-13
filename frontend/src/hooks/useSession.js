import { useState, useCallback } from "react";

const API_BASE = "/api/exercises";

// Starts a Practice session: random exercises of the track, no LLM involved.
export function useSession(track) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const startSession = useCallback(async (filters) => {
    setLoading(true);
    setError(null);

    const count = Math.floor(Math.random() * 11) + 5; // 5–15
    const params = new URLSearchParams({ track, limit: String(count) });
    if (filters.difficulty) params.append("difficulty", filters.difficulty);
    if (filters.exercise_type) params.append("exercise_type", filters.exercise_type);

    try {
      const res = await fetch(`${API_BASE}/random?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load exercises");
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [track]);

  const clearError = useCallback(() => setError(null), []);

  return { loading, error, startSession, clearError };
}
