/**
 * PinSetup — 4-to-8-digit PIN entry + confirm, OR skip with consent.
 *
 * PRD #89 Slice 3, Step 6.
 *
 * Two flows:
 *
 *   1. **Create a PIN** — primary path. POST /api/set-pin, then POST
 *      /api/login (so step 7 has a valid cookie + CSRF before the final
 *      profile commit).
 *
 *   2. **Skip for now** — requires explicit consent checkbox. POSTs
 *      ``{skip_pin_acknowledged: true}`` to /api/profile. The dashboard
 *      then surfaces <MissingPinBanner> until a PIN is set.
 *
 * Props:
 *   t:           theme tokens
 *   apiBase:     RENDER_API
 *   authHeaders: () => {Authorization?: string}
 *   csrfToken:   string (used for /api/set-pin which is auth-gated)
 *   onPinSet():  fired after PIN + login both succeed
 *   onSkip():    fired after the skip-consent path succeeds
 *   onCsrfRefresh(csrf): fired after a fresh /api/login mints a new
 *                        CSRF; the caller persists it to localStorage
 *                        so subsequent step-7 commits work.
 */
import { useState } from "react";

const MIN_LEN = 4;
const MAX_LEN = 8;
const NUMERIC = /^\d*$/;

export function PinSetup({
  t,
  apiBase,
  authHeaders,
  csrfToken,
  onPinSet,
  onSkip,
  onCsrfRefresh,
}) {
  const [mode, setMode] = useState("create"); // create | skip
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const valid =
    pin.length >= MIN_LEN &&
    pin.length <= MAX_LEN &&
    NUMERIC.test(pin) &&
    pin === confirm;

  const save = async () => {
    setError(null);
    if (!valid) {
      if (pin.length < MIN_LEN) setError(`PIN must be at least ${MIN_LEN} digits`);
      else if (pin.length > MAX_LEN) setError(`PIN can't exceed ${MAX_LEN} digits`);
      else if (!NUMERIC.test(pin)) setError("PIN must be numeric");
      else if (pin !== confirm) setError("PINs don't match");
      return;
    }
    setBusy(true);
    try {
      // Set the PIN — this endpoint is Bearer/cookie gated. In wizard
      // first-run mode the API_SECRET is unset (dev) and this passes;
      // in production setups it requires the existing session.
      const setResp = await fetch(`${apiBase}/api/set-pin`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
          ...(authHeaders ? authHeaders() : {}),
        },
        credentials: "include",
        body: JSON.stringify({ pin }),
      });
      if (!setResp.ok) {
        let msg = `HTTP ${setResp.status}`;
        try {
          const e = await setResp.json();
          if (e.error) msg = e.error;
        } catch (_) {}
        throw new Error(msg);
      }

      // Immediately log in with the new PIN so step 7's profile commit
      // has a fresh cookie + CSRF token. Without this, the next request
      // would be unauthenticated and the wizard would dead-end.
      const loginResp = await fetch(`${apiBase}/api/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ pin }),
      });
      if (loginResp.ok) {
        try {
          const d = await loginResp.json();
          if (d.csrf_token) onCsrfRefresh?.(d.csrf_token);
        } catch (_) {}
      }

      onPinSet?.();
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const skipWithConsent = async () => {
    if (!consent) {
      setError(
        "Please confirm you understand anyone with this URL can edit preferences."
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/profile`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
          ...(authHeaders ? authHeaders() : {}),
        },
        credentials: "include",
        body: JSON.stringify({ skip_pin_acknowledged: true }),
      });
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try {
          const e = await resp.json();
          if (e.error) msg = e.error;
        } catch (_) {}
        throw new Error(msg);
      }
      onSkip?.();
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const tabBtn = (active, label, onClick) => (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: "8px 16px",
        borderRadius: 8,
        border: `1px solid ${active ? t.ac : t.bd}`,
        background: active ? t.ac : "transparent",
        color: active ? "#fff" : t.tx,
        fontSize: 13,
        fontWeight: 600,
        cursor: "pointer",
        fontFamily: "inherit",
      }}
    >
      {label}
    </button>
  );

  const field = {
    width: "100%",
    padding: "11px 14px",
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

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
        {tabBtn(mode === "create", "Create a PIN", () => setMode("create"))}
        {tabBtn(mode === "skip", "Skip for now", () => setMode("skip"))}
      </div>

      {mode === "create" && (
        <div>
          <p style={{ color: t.txM, fontSize: 13, marginTop: 0 }}>
            4 to 8 digits. The PIN gates write access to your preferences
            and resume vault. It's stored as a pbkdf2 hash — recoverable
            only by admin shell access.
          </p>
          <div style={{ display: "grid", gap: 12 }}>
            <input
              type="password"
              inputMode="numeric"
              maxLength={MAX_LEN}
              autoComplete="new-password"
              value={pin}
              onChange={(e) => {
                if (NUMERIC.test(e.target.value)) setPin(e.target.value);
              }}
              placeholder="PIN"
              style={field}
            />
            <input
              type="password"
              inputMode="numeric"
              maxLength={MAX_LEN}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => {
                if (NUMERIC.test(e.target.value)) setConfirm(e.target.value);
              }}
              placeholder="Confirm PIN"
              style={field}
            />
          </div>
          {error && (
            <div
              style={{
                marginTop: 12,
                padding: "8px 12px",
                borderRadius: 6,
                background: "#fee",
                color: "#900",
                fontSize: 13,
                border: "1px solid #f99",
              }}
            >
              {error}
            </div>
          )}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              marginTop: 16,
            }}
          >
            <button
              type="button"
              onClick={save}
              disabled={!valid || busy}
              style={{
                padding: "11px 22px",
                borderRadius: 8,
                border: `1px solid ${valid ? t.ac : t.bd}`,
                background: valid ? t.ac : t.bgS,
                color: valid ? "#fff" : t.txM,
                fontSize: 14,
                fontWeight: 600,
                cursor: valid && !busy ? "pointer" : "not-allowed",
                fontFamily: "inherit",
              }}
            >
              {busy ? "Saving…" : "Save PIN →"}
            </button>
          </div>
        </div>
      )}

      {mode === "skip" && (
        <div>
          <div
            style={{
              padding: "12px 14px",
              borderRadius: 8,
              background: `${t.wm}11`,
              border: `1px solid ${t.wm}`,
              color: t.tx,
              fontSize: 13,
              marginBottom: 14,
            }}
          >
            ⚠️ Without a PIN, anyone who knows the dashboard URL can
            change your roles, dream companies, and resume vault.
          </div>
          <label
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              color: t.tx,
              fontSize: 14,
              cursor: "pointer",
              padding: "8px 0",
            }}
          >
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              I understand anyone with this URL can edit my preferences.
            </span>
          </label>
          {error && (
            <div
              style={{
                marginTop: 12,
                padding: "8px 12px",
                borderRadius: 6,
                background: "#fee",
                color: "#900",
                fontSize: 13,
                border: "1px solid #f99",
              }}
            >
              {error}
            </div>
          )}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              marginTop: 16,
            }}
          >
            <button
              type="button"
              onClick={skipWithConsent}
              disabled={!consent || busy}
              style={{
                padding: "11px 22px",
                borderRadius: 8,
                border: `1px solid ${consent ? t.wm : t.bd}`,
                background: consent ? t.wm : t.bgS,
                color: consent ? "#fff" : t.txM,
                fontSize: 14,
                fontWeight: 600,
                cursor: consent && !busy ? "pointer" : "not-allowed",
                fontFamily: "inherit",
              }}
            >
              {busy ? "Saving…" : "Skip without PIN →"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
