/**
 * LoginScreen — scaffolding for Slice 4 of issue #89.
 *
 * Tracking:  https://github.com/narendranathe/job-scout/issues/93
 * Parent PRD: https://github.com/narendranathe/job-scout/issues/89
 * Spec:      docs/superpowers/specs/2026-05-17-first-run-onboarding-wizard.md
 *
 * Shown when user_profile.pin_hash != "" AND no valid jobscout_session
 * cookie. App.jsx mounts this in place of the dashboard or wizard
 * until the user signs in.
 *
 * Backend dependency: Slice 1 (#90) ships POST /api/login (PIN →
 * signed cookie). Until then this scaffold no-ops on submit.
 *
 * UX requirements (see issue #93 acceptance criteria):
 *   - Full-page card layout, no chrome
 *   - PIN input is type=password inputMode=numeric maxLength=8
 *   - Wrong-PIN inline error; 3 attempts → 10s cooldown (client-side)
 *   - "Forgot PIN?" expandable hint (no recovery flow; admin reset only)
 *   - On 200: redirect to whatever path was originally requested
 *     (default /); pass `redirectTo` via props
 *
 * Props:
 *   redirectTo  — path to navigate to after successful login (default "/")
 *   onLogin()   — optional callback (e.g., to refresh top-level state)
 */

import React, { useState } from 'react';

const API = (import.meta.env.VITE_RENDER_URL || '').replace(/\/+$/, '');
const COOLDOWN_AFTER = 3;
const COOLDOWN_MS = 10_000;

export default function LoginScreen({ redirectTo = '/', onLogin }) {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [attempts, setAttempts] = useState(0);
  const [cooldownUntil, setCooldownUntil] = useState(0);
  const [forgot, setForgot] = useState(false);

  const inCooldown = Date.now() < cooldownUntil;

  async function handleSubmit(e) {
    e.preventDefault();
    if (inCooldown) return;
    if (!/^\d{4,8}$/.test(pin)) {
      setError('PIN must be 4–8 digits.');
      return;
    }

    // TODO(slice-4): POST /api/login {pin}
    // const resp = await fetch(`${API}/api/login`, { … });
    // if (resp.ok) { onLogin?.(); window.location.href = redirectTo; return; }
    // setError('Invalid PIN');
    // setAttempts(a => a + 1);
    // if (attempts + 1 >= COOLDOWN_AFTER) setCooldownUntil(Date.now() + COOLDOWN_MS);
    setError('Login endpoint not implemented yet (scaffold).');
  }

  return (
    <div style={{ maxWidth: 360, margin: '120px auto', padding: 24, textAlign: 'center' }}>
      <h1>JobScout</h1>
      <p style={{ opacity: 0.7 }}>Enter your PIN to continue.</p>
      <form onSubmit={handleSubmit}>
        <input
          type="password"
          inputMode="numeric"
          maxLength={8}
          autoFocus
          autoComplete="one-time-code"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          disabled={inCooldown}
          style={{ fontSize: 24, letterSpacing: '0.4em', padding: 12, width: '100%' }}
        />
        {error && <p style={{ color: '#c33', marginTop: 8 }}>{error}</p>}
        {inCooldown && (
          <p style={{ color: '#c33', marginTop: 8 }}>
            Too many attempts. Try again in {Math.ceil((cooldownUntil - Date.now()) / 1000)}s.
          </p>
        )}
        <button type="submit" disabled={inCooldown} style={{ marginTop: 16, width: '100%' }}>
          Sign in
        </button>
      </form>
      <button
        onClick={() => setForgot((f) => !f)}
        style={{ marginTop: 24, background: 'none', border: 'none', textDecoration: 'underline' }}
      >
        Forgot PIN?
      </button>
      {forgot && (
        <p style={{ fontSize: 12, opacity: 0.7, marginTop: 8 }}>
          The PIN is stored as a pbkdf2 hash and can't be recovered. To
          reset, call <code>POST /api/admin/reset-pin</code> with your
          API_SECRET Bearer token, or use the Monitor tab on a session
          that already has admin access.
        </p>
      )}
    </div>
  );
}
