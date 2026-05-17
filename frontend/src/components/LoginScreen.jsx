/**
 * LoginScreen — full-page PIN entry for returning users.
 *
 * PRD #89 Slice 4 §4.1. Rendered by App.jsx when:
 *   - /api/profile reports has_pin == true
 *   - AND no valid jobscout_session cookie is detected client-side
 *
 * On submit: POST /api/login. On success: persist the returned CSRF
 * token to localStorage["jobscout_csrf"] and call onLoggedIn so the
 * dashboard re-fetches.
 *
 * Rate limit: 3 wrong attempts triggers a 10s client-side cooldown.
 * This nudges casual brute-forcers without burning Render compute —
 * the server-side PIN check is already pbkdf2 with 200k iterations so
 * a hard rate-limit at the network layer isn't required.
 *
 * Props:
 *   t:           theme tokens
 *   apiBase:     RENDER_API
 *   onLoggedIn(csrf): called after a successful POST /api/login
 */
import { useEffect, useState } from "react";

const MAX_ATTEMPTS = 3;
const COOLDOWN_MS = 10_000;

export function LoginScreen({ t, apiBase, onLoggedIn }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showForgot, setShowForgot] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [cooldownUntil, setCooldownUntil] = useState(0);

  // Tick a timer while in cooldown so the disabled button + countdown
  // update without manual nudging.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (cooldownUntil <= Date.now()) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [cooldownUntil]);
  const cooldownLeft = Math.max(0, cooldownUntil - now);

  const submit = async (e) => {
    e?.preventDefault?.();
    setError(null);
    if (cooldownLeft > 0) return;
    if (!pin.trim()) {
      setError("Enter your PIN");
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(`${apiBase}/api/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ pin: pin.trim() }),
      });
      if (r.ok) {
        const d = await r.json();
        if (d?.csrf_token && typeof window !== "undefined") {
          try {
            window.localStorage.setItem("jobscout_csrf", d.csrf_token);
          } catch (_) {}
        }
        setAttempts(0);
        onLoggedIn?.(d?.csrf_token || "");
        return;
      }
      if (r.status === 401) {
        const next = attempts + 1;
        setAttempts(next);
        if (next >= MAX_ATTEMPTS) {
          setCooldownUntil(Date.now() + COOLDOWN_MS);
          setError(
            `Too many wrong attempts. Try again in ${Math.ceil(COOLDOWN_MS / 1000)}s.`
          );
        } else {
          setError(`Invalid PIN (${MAX_ATTEMPTS - next} attempts left)`);
        }
      } else {
        setError(`Server error (${r.status})`);
      }
    } catch (e) {
      setError(`Network: ${e?.message || e}`);
    } finally {
      setBusy(false);
      setPin("");
    }
  };

  const overlay = {
    position: "fixed",
    inset: 0,
    background: t.bg || "#111",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
    zIndex: 1500,
  };
  const card = {
    background: t.cd,
    color: t.tx,
    border: `1px solid ${t.bd}`,
    borderRadius: 14,
    padding: "32px",
    maxWidth: 380,
    width: "100%",
    boxShadow: t.shL || "0 12px 40px rgba(0,0,0,0.45)",
    fontFamily: "inherit",
  };
  const field = {
    width: "100%",
    padding: "12px 16px",
    borderRadius: 8,
    border: `1px solid ${t.bd}`,
    background: t.bgS,
    color: t.tx,
    fontSize: 18,
    fontFamily: "inherit",
    letterSpacing: "0.3em",
    textAlign: "center",
    boxSizing: "border-box",
  };
  const btn = (disabled) => ({
    width: "100%",
    padding: "12px 18px",
    borderRadius: 8,
    border: `1px solid ${disabled ? t.bd : t.ac}`,
    background: disabled ? t.bgS : t.ac,
    color: disabled ? t.txM : "#fff",
    fontSize: 14,
    fontWeight: 700,
    cursor: disabled ? "not-allowed" : "pointer",
    fontFamily: "inherit",
    marginTop: 16,
  });

  return (
    <div style={overlay}>
      <form style={card} onSubmit={submit}>
        <div style={{ textAlign: "center", marginBottom: 18 }}>
          <div
            style={{
              fontSize: 30,
              fontFamily: "'Playfair Display', serif",
              color: t.ac,
              margin: 0,
            }}
          >
            JobScout
          </div>
          <div
            style={{ color: t.txM, fontSize: 13, marginTop: 4 }}
          >
            Enter your PIN to continue
          </div>
        </div>
        <input
          type="password"
          inputMode="numeric"
          maxLength={8}
          autoFocus
          autoComplete="current-password"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          placeholder="••••"
          style={field}
          disabled={cooldownLeft > 0 || busy}
        />
        {error && (
          <div
            role="alert"
            style={{
              marginTop: 12,
              padding: "8px 12px",
              borderRadius: 6,
              background: "#fee",
              color: "#900",
              fontSize: 13,
              border: "1px solid #f99",
              textAlign: "center",
            }}
          >
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={busy || cooldownLeft > 0}
          style={btn(busy || cooldownLeft > 0)}
        >
          {cooldownLeft > 0
            ? `Wait ${Math.ceil(cooldownLeft / 1000)}s…`
            : busy
            ? "Signing in…"
            : "Sign in"}
        </button>
        <div style={{ textAlign: "center", marginTop: 16 }}>
          <button
            type="button"
            onClick={() => setShowForgot((v) => !v)}
            style={{
              background: "transparent",
              border: 0,
              color: t.txS,
              fontSize: 12,
              cursor: "pointer",
              textDecoration: "underline",
              fontFamily: "inherit",
            }}
          >
            Forgot PIN?
          </button>
        </div>
        {showForgot && (
          <div
            style={{
              marginTop: 12,
              padding: "10px 14px",
              borderRadius: 8,
              background: t.bgS,
              color: t.txM,
              fontSize: 12,
              lineHeight: 1.6,
              border: `1px solid ${t.bd}`,
            }}
          >
            The PIN is stored as a pbkdf2 hash and cannot be recovered.
            To reset it, you need shell access to the Render container or
            to call <code>POST /api/admin/reset-pin</code> with the
            <code>API_SECRET</code> Bearer token. See the admin docs.
          </div>
        )}
      </form>
    </div>
  );
}
