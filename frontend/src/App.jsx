import { useCallback, useEffect, useState } from "react";
import { useSession } from "./hooks/useSession";
import { FilterBar } from "./components/FilterBar";
import { SessionView } from "./components/SessionView";
import { SessionSummary } from "./components/SessionSummary";
import { ChatWindow } from "./components/ChatWindow";
import { ProfileGate } from "./components/ProfileGate";
import { AdminPage } from "./pages/AdminPage";
import { StudioPage } from "./pages/StudioPage";
import {
  getStoredProfileId, setStoredProfileId, getStoredTrack, setStoredTrack, identityHeaders,
} from "./utils/identity";
import { ui } from "./i18n";

const NAV_ITEMS = [
  { id: "chat",     label: ui.app.nav.chat },
  { id: "practice", label: ui.app.nav.practice },
  { id: "studio",   label: ui.app.nav.studio },
  { id: "admin",    label: ui.app.nav.admin },
];

// Most recently used track of the profile, unless the stored one is still valid.
function pickTrack(profile) {
  const stored = getStoredTrack();
  return profile.tracks.includes(stored) ? stored : profile.tracks[0] ?? null;
}

export default function App() {
  const [tracks, setTracks] = useState(null);      // every enabled track
  const [profile, setProfile] = useState(null);    // selected profile
  const [trackCode, setTrackCode] = useState(null);
  const [bootError, setBootError] = useState(null);

  const [page, setPage] = useState("chat");
  const [phase, setPhase] = useState("filters"); // "filters" | "session" | "summary"
  const [sessionExercises, setSessionExercises] = useState([]);
  const [sessionResults, setSessionResults] = useState([]);
  const { loading, error, startSession, clearError } = useSession(trackCode);

  // Boot: load tracks and restore the stored profile (no PIN on reload — the
  // PIN only guards switching profiles, see ProfileGate).
  useEffect(() => {
    Promise.all([fetch("/api/tracks"), fetch("/api/users")])
      .then(async ([tracksRes, usersRes]) => {
        if (!tracksRes.ok || !usersRes.ok) throw new Error(ui.app.backendDown);
        const [allTracks, profiles] = await Promise.all([tracksRes.json(), usersRes.json()]);
        setTracks(allTracks);
        const stored = profiles.find((p) => p.id === getStoredProfileId());
        if (stored) {
          setProfile(stored);
          setTrackCode(pickTrack(stored));
        } else {
          setStoredProfileId(null);
        }
      })
      .catch((err) => setBootError(err.message));
  }, []);

  const resetPractice = useCallback(() => {
    setSessionExercises([]);
    setSessionResults([]);
    setPhase("filters");
    clearError();
  }, [clearError]);

  const handleProfileSelected = (selected) => {
    setStoredProfileId(selected.id);
    setProfile(selected);
    const code = pickTrack(selected);
    setTrackCode(code);
    setStoredTrack(code);
    resetPractice();
  };

  const handleSwitchProfile = () => {
    setStoredProfileId(null);
    setProfile(null);
    resetPractice();
  };

  // Enrolls the profile in the track if needed and marks it as the last used one.
  const handleTrackChange = async (code) => {
    try {
      const res = await fetch(`/api/users/${profile.id}/tracks/${encodeURIComponent(code)}`, { method: "PUT" });
      const updated = await res.json();
      if (!res.ok) throw new Error(updated.detail || ui.app.trackSwitchFailed);
      setProfile(updated);
      setTrackCode(code);
      setStoredTrack(code);
      resetPractice();
    } catch (err) {
      setBootError(err.message);
    }
  };

  const handleStart = async (filters) => {
    const exercises = await startSession(filters);
    if (exercises && exercises.length > 0) {
      setSessionExercises(exercises);
      setSessionResults([]);
      setPhase("session");
    }
  };

  const handleSessionComplete = (results) => {
    setSessionResults(results);
    setPhase("summary");

    fetch("/api/exercises/attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...identityHeaders() },
      body: JSON.stringify({ results }),
    }).catch(() => {
      // best-effort: never block the UI if saving history fails
    });
  };

  const handleNavClick = (id) => {
    setPage(id);
    if (id === "practice") resetPractice();
  };

  const track = tracks?.find((t) => t.code === trackCode) ?? null;
  const otherTracks = tracks?.filter((t) => !profile?.tracks.includes(t.code)) ?? [];

  if (bootError) {
    return (
      <div style={{ ...layoutStyle, alignItems: "center", justifyContent: "center" }}>
        <div style={errorBoxStyle}>
          <span style={{ fontSize: "28px" }}>⚠</span>
          <p style={{ color: "var(--error)", fontWeight: 600, fontSize: "15px" }}>{bootError}</p>
          <button onClick={() => window.location.reload()} style={retryButtonStyle}>{ui.app.reload}</button>
        </div>
      </div>
    );
  }

  if (!tracks) {
    return <div style={{ ...layoutStyle, alignItems: "center", justifyContent: "center" }}><div style={spinnerStyle} /><style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style></div>;
  }

  if (!profile || !track) {
    return (
      <div style={layoutStyle}>
        <main style={mainStyle}>
          <ProfileGate tracks={tracks} onSelect={handleProfileSelected} />
        </main>
        <style>{globalAnimations}</style>
      </div>
    );
  }

  return (
    <div style={layoutStyle}>
      {/* Header */}
      <header style={headerStyle}>
        <button onClick={resetPractice} style={logoStyle}>
          <span style={{ color: "var(--accent)" }}>lang</span>learn
        </button>

        <nav style={navStyle}>
          {NAV_ITEMS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => handleNavClick(id)}
              style={navItemStyle(page === id)}
            >
              {label}
            </button>
          ))}
        </nav>

        {page === "practice" && phase === "session" && (
          <div style={sessionBadge}>
            <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)" }}>
              {ui.app.exerciseCount(sessionExercises.length)}
            </span>
          </div>
        )}

        <select
          value={track.code}
          onChange={(e) => handleTrackChange(e.target.value)}
          title={ui.app.trackTitle}
          style={trackSelectStyle}
        >
          {profile.tracks.map((code) => (
            <option key={code} value={code}>{tracks.find((t) => t.code === code)?.name ?? code}</option>
          ))}
          {otherTracks.length > 0 && (
            <optgroup label={ui.app.addTrack}>
              {otherTracks.map((t) => <option key={t.code} value={t.code}>+ {t.name}</option>)}
            </optgroup>
          )}
        </select>

        <button onClick={handleSwitchProfile} title={ui.app.switchProfile} style={profileChipStyle}>
          {profile.display_name}
        </button>
      </header>

      {/* Main */}
      <main style={mainStyle}>
        {page === "practice" && (
          <>
            {/* Filters phase */}
            {phase === "filters" && !loading && !error && (
              <div style={stageStyle}>
                <div style={{ textAlign: "center", marginBottom: "40px" }}>
                  <h1 style={titleStyle}>
                    {ui.practice.title(track.name)}<br />
                    <span style={{ color: "var(--accent)" }}>{ui.practice.titleAccent}</span>
                  </h1>
                  <p style={subtitleStyle}>
                    {ui.practice.subtitle}
                  </p>
                </div>
                <FilterBar key={track.code} track={track} onStart={handleStart} />
              </div>
            )}

            {/* Loading */}
            {loading && (
              <div style={stageStyle}>
                <div style={loadingStyle}>
                  <div style={spinnerStyle} />
                  <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
                    {ui.practice.preparing}
                  </p>
                </div>
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              </div>
            )}

            {/* Error */}
            {error && !loading && (
              <div style={stageStyle}>
                <div style={errorBoxStyle}>
                  <span style={{ fontSize: "28px" }}>⚠</span>
                  <p style={{ color: "var(--error)", fontWeight: 600, fontSize: "15px" }}>{error}</p>
                  <button onClick={resetPractice} style={retryButtonStyle}>
                    {ui.common.tryAgain}
                  </button>
                </div>
              </div>
            )}

            {/* Session phase */}
            {phase === "session" && !loading && (
              <div style={stageStyle}>
                <SessionView
                  exercises={sessionExercises}
                  onComplete={handleSessionComplete}
                />
              </div>
            )}

            {/* Summary phase */}
            {phase === "summary" && (
              <div style={stageStyle}>
                <SessionSummary
                  results={sessionResults}
                  onRestart={resetPractice}
                />
              </div>
            )}
          </>
        )}

        {page === "chat" && (
          <div style={{ display: "flex", justifyContent: "center", width: "100%", padding: "0 20px" }}>
            <ChatWindow key={`${profile.id}-${track.code}`} track={track} />
          </div>
        )}

        {page === "studio" && <StudioPage key={track.code} track={track} />}

        {page === "admin" && <AdminPage key={track.code} track={track} />}
      </main>

      {/* Footer */}
      <footer style={footerStyle}>
        <span>{ui.app.footer}</span>
      </footer>

      <style>{globalAnimations}</style>
    </div>
  );
}

/* ── Styles ── */

const layoutStyle = {
  minHeight: "100vh",
  display: "flex",
  flexDirection: "column",
};

const headerStyle = {
  position: "sticky",
  top: 0,
  zIndex: 100,
  display: "flex",
  alignItems: "center",
  gap: "24px",
  padding: "14px 32px",
  borderBottom: "1px solid var(--border)",
  backdropFilter: "blur(12px)",
  background: "rgba(15,15,19,0.85)",
};

const logoStyle = {
  background: "none",
  border: "none",
  color: "var(--text-primary)",
  fontSize: "18px",
  fontWeight: 700,
  letterSpacing: "-0.03em",
  cursor: "pointer",
  padding: 0,
  flexShrink: 0,
};

const navStyle = {
  display: "flex",
  gap: "4px",
  flex: 1,
};

const navItemStyle = (active) => ({
  padding: "7px 16px",
  borderRadius: "var(--radius-sm)",
  fontSize: "13px",
  fontWeight: active ? 600 : 400,
  background: active ? "rgba(99,102,241,0.15)" : "transparent",
  border: active ? "1px solid rgba(99,102,241,0.3)" : "1px solid transparent",
  color: active ? "var(--accent-light)" : "var(--text-secondary)",
  cursor: "pointer",
  transition: "all var(--transition)",
});

const trackSelectStyle = {
  padding: "6px 12px",
  background: "rgba(255,255,255,0.03)",
  border: "1px solid var(--border)",
  borderRadius: "999px",
  color: "var(--text-primary)",
  fontSize: "12px",
  outline: "none",
  cursor: "pointer",
};

const profileChipStyle = {
  padding: "6px 12px",
  background: "rgba(99,102,241,0.1)",
  border: "1px solid rgba(99,102,241,0.25)",
  borderRadius: "999px",
  color: "var(--accent-light)",
  fontSize: "12px",
  fontWeight: 600,
  cursor: "pointer",
};

const sessionBadge = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  padding: "6px 14px",
  background: "rgba(99,102,241,0.1)",
  border: "1px solid rgba(99,102,241,0.2)",
  borderRadius: "999px",
  marginLeft: "auto",
};

const mainStyle = {
  flex: 1,
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "center",
  padding: "40px 20px",
};

const stageStyle = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  width: "100%",
  animation: "fadeSlideIn 0.4s ease forwards",
};

const titleStyle = {
  fontSize: "clamp(28px, 5vw, 42px)",
  fontWeight: 700,
  letterSpacing: "-0.03em",
  lineHeight: 1.2,
  color: "var(--text-primary)",
  marginBottom: "12px",
};

const subtitleStyle = {
  fontSize: "16px",
  color: "var(--text-secondary)",
  fontWeight: 400,
  lineHeight: 1.6,
};

const loadingStyle = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "20px",
};

const spinnerStyle = {
  width: "36px",
  height: "36px",
  border: "3px solid var(--border)",
  borderTopColor: "var(--accent)",
  borderRadius: "50%",
  animation: "spin 0.8s linear infinite",
};

const errorBoxStyle = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "16px",
  padding: "40px",
  background: "var(--error-bg)",
  border: "1px solid var(--error-border)",
  borderRadius: "var(--radius-lg)",
  textAlign: "center",
  maxWidth: "400px",
};

const retryButtonStyle = {
  padding: "10px 28px",
  background: "var(--error)",
  color: "#fff",
  borderRadius: "var(--radius-sm)",
  fontSize: "14px",
  fontWeight: 600,
  cursor: "pointer",
};

const footerStyle = {
  padding: "16px 32px",
  textAlign: "center",
  fontSize: "11px",
  color: "var(--text-muted)",
  borderTop: "1px solid var(--border)",
  letterSpacing: "0.05em",
};

const globalAnimations = `
  @keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(12px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  nav button:hover {
    background: rgba(99,102,241,0.08) !important;
    color: var(--text-primary) !important;
  }
`;
