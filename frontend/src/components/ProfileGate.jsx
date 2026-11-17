import { useEffect, useState } from "react";
import { ui } from "../i18n";

/**
 * ProfileGate — pick or create a profile before using the app.
 *
 * Profiles are NOT accounts: the optional 4-digit PIN only guards switching
 * to a profile from this screen (checked by POST /users/{id}/verify-pin).
 */
export function ProfileGate({ tracks, onSelect }) {
  const [profiles, setProfiles] = useState(null);
  const [error, setError] = useState(null);
  const [pinFor, setPinFor] = useState(null); // profile awaiting its PIN
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetch("/api/users")
      .then((res) => res.json().then((data) => {
        if (!res.ok) throw new Error(data.detail || ui.profiles.loadFailed);
        setProfiles(data);
        if (data.length === 0) setCreating(true);
      }))
      .catch((err) => setError(err.message));
  }, []);

  const choose = (profile) => {
    setError(null);
    if (profile.has_pin) setPinFor(profile);
    else onSelect(profile);
  };

  return (
    <div style={wrapStyle}>
      <h1 style={titleStyle}>{ui.profiles.title}</h1>
      <p style={subtitleStyle}>{ui.profiles.subtitle}</p>

      {error && <p style={errorStyle}>⚠ {error}</p>}

      {pinFor ? (
        <PinForm profile={pinFor} onCancel={() => setPinFor(null)} onVerified={() => onSelect(pinFor)} />
      ) : creating ? (
        <CreateProfileForm
          tracks={tracks}
          canCancel={profiles?.length > 0}
          onCancel={() => setCreating(false)}
          onCreated={onSelect}
        />
      ) : (
        <>
          <div style={gridStyle}>
            {profiles === null && <p style={subtitleStyle}>{ui.common.loading}</p>}
            {profiles?.map((p) => (
              <button key={p.id} onClick={() => choose(p)} style={profileCard}>
                <span style={avatarStyle}>{p.display_name.slice(0, 1).toUpperCase()}</span>
                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.display_name}</span>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  {p.tracks.join(" · ") || ui.profiles.noTracks}{p.has_pin ? " · 🔒" : ""}
                </span>
              </button>
            ))}
          </div>
          <button onClick={() => setCreating(true)} style={secondaryBtn}>{ui.profiles.newProfile}</button>
        </>
      )}
    </div>
  );
}

function PinForm({ profile, onCancel, onVerified }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      const res = await fetch(`/api/users/${profile.id}/verify-pin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(res.status === 403 ? ui.profiles.wrongPin : data.detail || ui.profiles.pinCheckFailed);
      }
      onVerified();
    } catch (err) {
      setError(err.message);
      setPin("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} style={formStyle}>
      <p style={{ color: "var(--text-secondary)" }}>{ui.profiles.pinFor} <strong>{profile.display_name}</strong></p>
      <input
        autoFocus type="password" inputMode="numeric" maxLength={4} value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
        style={{ ...inputStyle, letterSpacing: "0.5em", textAlign: "center", fontSize: "20px" }}
      />
      {error && <p style={errorStyle}>⚠ {error}</p>}
      <div style={{ display: "flex", gap: "10px" }}>
        <button type="button" onClick={onCancel} style={secondaryBtn}>{ui.common.back}</button>
        <button type="submit" disabled={pin.length !== 4 || loading} style={primaryBtn(pin.length === 4 && !loading)}>{ui.profiles.enter}</button>
      </div>
    </form>
  );
}

function CreateProfileForm({ tracks, canCancel, onCancel, onCreated }) {
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [selectedTracks, setSelectedTracks] = useState(tracks.slice(0, 1).map((t) => t.code));
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const valid = name.trim() && (pin === "" || pin.length === 4) && selectedTracks.length > 0;

  const toggleTrack = (code) => {
    setSelectedTracks((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
  };

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      const res = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: name.trim(), pin: pin || null, tracks: selectedTracks }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail?.[0]?.msg || data.detail || ui.profiles.createFailed);
      onCreated(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} style={formStyle}>
      <label style={labelStyle}>{ui.profiles.name}</label>
      <input autoFocus value={name} maxLength={64} onChange={(e) => setName(e.target.value)} style={inputStyle} />

      <label style={labelStyle}>{ui.profiles.pin}</label>
      <input
        type="password" inputMode="numeric" maxLength={4} value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} style={inputStyle}
      />

      <label style={labelStyle}>{ui.profiles.tracks}</label>
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        {tracks.map((t) => (
          <button key={t.code} type="button" onClick={() => toggleTrack(t.code)} style={chip(selectedTracks.includes(t.code))}>
            {t.name}
          </button>
        ))}
      </div>

      {error && <p style={errorStyle}>⚠ {error}</p>}
      <div style={{ display: "flex", gap: "10px" }}>
        {canCancel && <button type="button" onClick={onCancel} style={secondaryBtn}>{ui.common.back}</button>}
        <button type="submit" disabled={!valid || loading} style={primaryBtn(valid && !loading)}>{ui.profiles.create}</button>
      </div>
    </form>
  );
}

/* ── Styles ── */

const wrapStyle = { width: "100%", maxWidth: "560px", display: "flex", flexDirection: "column", alignItems: "center", gap: "20px", animation: "fadeSlideIn 0.4s ease forwards" };
const titleStyle = { fontSize: "32px", fontWeight: 700, letterSpacing: "-0.03em", color: "var(--text-primary)" };
const subtitleStyle = { fontSize: "13px", color: "var(--text-secondary)", textAlign: "center", lineHeight: 1.6 };
const errorStyle = { color: "var(--error)", fontSize: "13px" };
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "12px", width: "100%" };
const profileCard = { display: "flex", flexDirection: "column", alignItems: "center", gap: "8px", padding: "20px 12px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius)", cursor: "pointer", transition: "all var(--transition)" };
const avatarStyle = { width: "48px", height: "48px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.35)", color: "var(--accent-light)", fontSize: "20px", fontWeight: 700 };
const formStyle = { width: "100%", display: "flex", flexDirection: "column", gap: "10px", padding: "24px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)" };
const labelStyle = { fontSize: "10px", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)", marginTop: "6px" };
const inputStyle = { background: "rgba(255,255,255,0.04)", border: "1.5px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 12px", color: "var(--text-primary)", fontSize: "14px", outline: "none" };
const chip = (active) => ({ padding: "7px 14px", borderRadius: "999px", fontSize: "13px", fontWeight: active ? 600 : 400, background: active ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.03)", border: `1.5px solid ${active ? "rgba(99,102,241,0.4)" : "var(--border)"}`, color: active ? "var(--accent-light)" : "var(--text-secondary)", cursor: "pointer" });
const primaryBtn = (active) => ({ flex: 1, padding: "11px", background: active ? "var(--accent)" : "rgba(99,102,241,0.2)", color: active ? "#fff" : "rgba(255,255,255,0.4)", borderRadius: "var(--radius-sm)", fontSize: "14px", fontWeight: 600, cursor: active ? "pointer" : "not-allowed" });
const secondaryBtn = { padding: "10px 18px", background: "rgba(255,255,255,0.04)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-secondary)", fontSize: "13px", fontWeight: 600, cursor: "pointer" };
