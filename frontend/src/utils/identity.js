// Lightweight per-browser identity: this is NOT authentication.
// The selected profile id (see ProfileGate) and the last track are kept in
// localStorage; the profile id travels as the X-User-Id header.
const PROFILE_KEY = "langlearn_profile_id";
const TRACK_KEY = "langlearn_track";

function read(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value === null || value === undefined) localStorage.removeItem(key);
    else localStorage.setItem(key, String(value));
  } catch {
    // storage unavailable (private mode, blocked site data) — keep going in memory
  }
}

export function getStoredProfileId() {
  const value = Number(read(PROFILE_KEY));
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function setStoredProfileId(id) {
  write(PROFILE_KEY, id);
}

export function getStoredTrack() {
  return read(TRACK_KEY);
}

export function setStoredTrack(code) {
  write(TRACK_KEY, code);
}

// Pass as headers on every request that must be attributed to the profile.
export function identityHeaders() {
  const id = getStoredProfileId();
  return id ? { "X-User-Id": String(id) } : {};
}
