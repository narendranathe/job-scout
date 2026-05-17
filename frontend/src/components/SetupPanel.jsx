/**
 * First-run server setup panel.
 *
 * When RENDER_API is "" (fresh browser, no env var, nothing in
 * localStorage) the dashboard would silently show stale GitHub-Pages
 * JSON and disable every admin/vault button. Instead we render this
 * panel as a blocking screen so the user can paste their Render URL +
 * optional API token once, save to localStorage, and the page reloads
 * with everything wired. Also reachable from the header "⚙️" button
 * for editing later.
 *
 * Props:
 *   - mode: "blocking" (no URL yet) | "settings" (re-opened from header)
 *   - onClose: only meaningful in "settings" mode
 *   - t: theme tokens
 */
import { useState } from "react";

import { _readApiUrl, DEFAULT_RENDER_URL, apiToken } from "../lib/api.js";

export function SetupPanel({ mode, onClose, t }) {
  const [url, setUrl] = useState(() => _readApiUrl() || DEFAULT_RENDER_URL);
  const [token, setToken] = useState(() => apiToken());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [probeResult, setProbeResult] = useState(null);

  const save = (e) => {
    e?.preventDefault?.();
    const trimmed = url.trim().replace(/\/+$/, "");
    if (!trimmed) { setError("Render URL is required"); return; }
    if (!/^https?:\/\//.test(trimmed)) { setError("URL must start with http:// or https://"); return; }
    try {
      window.localStorage.setItem("jobscout_api_url", trimmed);
      const tk = token.trim();
      if (tk) window.localStorage.setItem("vault_token", tk);
      else window.localStorage.removeItem("vault_token");
    } catch (ex) {
      setError(`Could not save: ${ex.message || ex}`);
      return;
    }
    window.location.reload();
  };

  const disconnect = () => {
    if (!window.confirm("Disconnect and clear stored URL + token? You'll fall back to the static GitHub Pages snapshot.")) return;
    try {
      window.localStorage.removeItem("jobscout_api_url");
      window.localStorage.removeItem("vault_token");
    } catch {}
    window.location.reload();
  };

  const testConnection = async () => {
    setBusy(true); setError(""); setProbeResult(null);
    const trimmed = url.trim().replace(/\/+$/, "");
    try {
      const r = await fetch(`${trimmed}/ping`, { signal: AbortSignal.timeout(8000) });
      if (r.ok) setProbeResult({ ok: true, msg: `✅ Reachable (HTTP ${r.status})` });
      else setProbeResult({ ok: false, msg: `⚠️ Got HTTP ${r.status} — server is up but /ping didn't return 200` });
    } catch (ex) {
      const m = ex?.name === "TimeoutError" || /timed out/i.test(ex?.message||"")
        ? "Timed out — Render free-tier dynos sleep after 15 min. Wait ~30s and retry."
        : `Network error: ${ex.message || ex}`;
      setProbeResult({ ok: false, msg: `❌ ${m}` });
    } finally { setBusy(false); }
  };

  const overlay = {
    position:"fixed", inset:0, background:"rgba(0,0,0,0.6)", zIndex:9999,
    display:"flex", alignItems:"center", justifyContent:"center", padding:"20px",
  };
  const card = {
    background:t.cd, color:t.tx, border:`1px solid ${t.bd}`, borderRadius:14,
    padding:"28px 28px 22px", maxWidth:520, width:"100%", boxShadow:t.shL || "0 12px 40px rgba(0,0,0,0.35)",
    fontFamily:"inherit",
  };
  const label = { display:"block", fontSize:12, color:t.txM, fontWeight:600, textTransform:"uppercase", letterSpacing:".06em", marginBottom:6 };
  const input = { width:"100%", padding:"10px 12px", borderRadius:8, border:`1px solid ${t.bd}`, background:t.bgS, color:t.tx, fontSize:14, fontFamily:"inherit", boxSizing:"border-box" };
  const btn   = { padding:"10px 18px", borderRadius:8, fontSize:14, fontWeight:600, cursor:"pointer", fontFamily:"inherit", border:"none" };

  return (
    <div style={overlay} role="dialog" aria-modal="true" aria-labelledby="setup-title">
      <form onSubmit={save} style={card}>
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:6}}>
          <h2 id="setup-title" style={{margin:0, fontSize:20, fontWeight:700, fontFamily:"'Playfair Display',serif"}}>
            {mode === "settings" ? "⚙️ Server Settings" : "🔌 Connect to your JobScout server"}
          </h2>
          {mode === "settings" && (
            <button type="button" onClick={onClose} aria-label="Close settings"
              style={{...btn, background:"transparent", color:t.txM, padding:"4px 10px"}}>✕</button>
          )}
        </div>
        <p style={{margin:"0 0 18px", fontSize:13, color:t.txM, lineHeight:1.5}}>
          {mode === "settings"
            ? "Update the Render URL or paste a fresh API token. Saving reloads the page."
            : "Paste your Render backend URL so the dashboard can fetch live data and enable admin actions. Stored locally in your browser — never sent anywhere except to the URL you enter."}
        </p>

        <label htmlFor="setup-url" style={label}>Render URL</label>
        <input id="setup-url" type="url" value={url} onChange={e=>setUrl(e.target.value)}
          placeholder="https://jobscout-api.onrender.com" autoFocus required
          style={input} />
        <div style={{marginTop:8, display:"flex", gap:10, alignItems:"center", flexWrap:"wrap"}}>
          <button type="button" onClick={testConnection} disabled={busy || !url.trim()}
            style={{...btn, background:`${t.ac}18`, color:t.ac, border:`1px solid ${t.ac}40`}}>
            {busy ? "Testing…" : "Test connection"}
          </button>
          {probeResult && (
            <span style={{fontSize:13, color: probeResult.ok ? t.ok : t.wm}}>{probeResult.msg}</span>
          )}
        </div>

        <div style={{marginTop:18}}>
          <label htmlFor="setup-token" style={label}>API token <span style={{color:t.txM, fontWeight:400, textTransform:"none", letterSpacing:0}}>(optional — only if you've set API_SECRET on Render)</span></label>
          <input id="setup-token" type="password" value={token} onChange={e=>setToken(e.target.value)}
            placeholder="leave blank if API_SECRET is not set" autoComplete="off" style={input} />
        </div>

        {error && (
          <div role="alert" style={{marginTop:14, padding:"10px 12px", borderRadius:8, background:`${t.er}15`, color:t.er, fontSize:13}}>
            ⚠️ {error}
          </div>
        )}

        <div style={{marginTop:22, display:"flex", gap:10, alignItems:"center", flexWrap:"wrap", justifyContent:"flex-end"}}>
          {mode === "settings" && _readApiUrl() && (
            <button type="button" onClick={disconnect}
              style={{...btn, background:"transparent", color:t.er, border:`1px solid ${t.er}40`, marginRight:"auto"}}>
              Disconnect
            </button>
          )}
          {mode === "settings" && (
            <button type="button" onClick={onClose}
              style={{...btn, background:"transparent", color:t.txM, border:`1px solid ${t.bd}`}}>Cancel</button>
          )}
          <button type="submit" disabled={busy}
            style={{...btn, background:t.gP || t.ac, color:"#fff"}}>
            Save &amp; reload
          </button>
        </div>
      </form>
    </div>
  );
}
