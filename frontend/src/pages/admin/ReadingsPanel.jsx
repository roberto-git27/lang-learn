import { useEffect, useState } from "react";
import { identityHeaders } from "../../utils/identity";
import { ErrorBox, Spinner, inputStyle, labelStyle, submitButtonStyle } from "./_shared";

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.[0]?.msg || "Request failed");
  return data;
}

/**
 * Words whose computed reading is wrong (e.g. 五本 read ごぽん) and the reading
 * to use instead, everywhere in the track: furigana and the romaji of
 * romaji_input exercises. Saving or removing one updates the stored exercises
 * that contain the word.
 */
export function ReadingsPanel({ track, initialSurface = "" }) {
  const [items, setItems] = useState(null);
  const [surface, setSurface] = useState(initialSurface);
  const [reading, setReading] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const query = `track=${encodeURIComponent(track.code)}`;

  const load = () => requestJson(`/api/readings?${query}`).then(setItems).catch((err) => setError(err.message));
  useEffect(() => { load(); }, [track.code]);   // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (label, action) => {
    setBusy(label); setError(null); setNotice(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const updated = (n) => `${n} exercise${n === 1 ? "" : "s"} updated.`;

  const save = () => run("save", async () => {
    const res = await requestJson("/api/readings", {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...identityHeaders() },
      body: JSON.stringify({ track: track.code, surface: surface.trim(), reading: reading.trim() }),
    });
    setNotice(`${res.override.surface} is now read ${res.override.reading} everywhere. ${updated(res.exercises_updated)}`);
    setSurface(""); setReading("");
  });

  const remove = (item) => run(`delete-${item.id}`, async () => {
    const res = await requestJson(`/api/readings/${item.id}?${query}`, { method: "DELETE", headers: identityHeaders() });
    setNotice(`${item.surface}: back to the computed reading. ${updated(res.exercises_updated)}`);
  });

  const canSave = surface.trim() && reading.trim() && !busy;

  return (
    <div style={cardStyle}>
      <p style={introText}>
        Furigana and romaji are computed by a dictionary, which sometimes picks the wrong reading (五本 → ごぽん).
        Fix a word here once: the reading is used everywhere in the track, and the exercises that contain the word are
        updated. A word that is part of a longer one is not touched (本 does not change 日本).
      </p>

      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ flex: "1 1 140px" }}>
          <span style={labelStyle}>Word (with kanji)</span>
          <input value={surface} onChange={(e) => setSurface(e.target.value)} maxLength={32} placeholder="五本" style={inputStyle} />
        </label>
        <label style={{ flex: "1 1 140px" }}>
          <span style={labelStyle}>Reading (kana)</span>
          <input
            value={reading} onChange={(e) => setReading(e.target.value)} maxLength={64} placeholder="ごほん" style={inputStyle}
            onKeyDown={(e) => { if (e.key === "Enter" && canSave) save(); }}
          />
        </label>
        <button onClick={save} disabled={!canSave} style={{ ...submitButtonStyle(!canSave), width: "auto", padding: "10px 18px" }}>
          {busy === "save" ? <Spinner /> : "Save reading"}
        </button>
      </div>

      {error && <div style={{ marginTop: "12px" }}><ErrorBox message={error} /></div>}
      {notice && <p style={noticeStyle}>✓ {notice}</p>}

      <div style={{ marginTop: "18px", display: "flex", flexDirection: "column", gap: "6px" }}>
        {items === null && !error && <Spinner />}
        {items?.length === 0 && <p style={introText}>No reading fixed by hand yet.</p>}
        {items?.map((item) => (
          <div key={item.id} style={rowStyle}>
            <ruby style={{ fontSize: "18px", color: "var(--text-primary)" }}>{item.surface}<rt style={{ fontSize: "10px" }}>{item.reading}</rt></ruby>
            <span style={{ fontSize: "12px", color: "var(--text-secondary)", flex: 1 }}>{item.reading}</span>
            <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>{item.user_display_name ?? ""}</span>
            <button onClick={() => remove(item)} disabled={!!busy} style={deleteBtn} title="Back to the computed reading">
              {busy === `delete-${item.id}` ? <Spinner /> : "Remove"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

const cardStyle = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "20px" };
const introText = { fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: "16px" };
const noticeStyle = { marginTop: "12px", fontSize: "13px", color: "var(--success)" };
const rowStyle = { display: "flex", alignItems: "center", gap: "12px", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)" };
const deleteBtn = { background: "none", border: "none", padding: 0, color: "var(--error)", fontSize: "12px", fontWeight: 600, cursor: "pointer" };
