// Difficulty scale shared with the backend (exercise_payloads.MAX_DIFFICULTY):
// 1 = first lessons … 10 = advanced (Japanese: two steps per JLPT level).
export const MAX_DIFFICULTY = 10;
export const DIFFICULTY_LEVELS = Array.from({ length: MAX_DIFFICULTY }, (_, i) => i + 1);
