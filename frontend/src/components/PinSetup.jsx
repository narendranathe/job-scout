/**
 * PinSetup — scaffolding for Slice 3 of issue #89.
 *
 * Tracking:  https://github.com/narendranathe/job-scout/issues/92
 * Parent PRD: https://github.com/narendranathe/job-scout/issues/89
 *
 * Step 6 of OnboardingWizard. Two paths:
 *   A. Create a PIN — 4–8 digit numeric input + confirm field.
 *      On success calls POST /api/set-pin, then POST /api/login so the
 *      cookie session is active before the wizard exits.
 *   B. Skip — explicit consent checkbox required ("Anyone with this
 *      URL can edit my preferences"). Writes
 *      user_profile.skip_pin_acknowledged = 1 via POST /api/profile.
 *
 * Backend dependency: Slice 1 (#90) adds POST /api/login (cookie auth).
 * Until that lands, the post-PIN auto-login no-ops and the wizard
 * falls back to the Bearer header from localStorage.
 *
 * Props:
 *   onComplete()  — PIN saved (either created or skipped); advance to step 7
 */

import React, { useState } from 'react';

const API = (import.meta.env.VITE_RENDER_URL || '').replace(/\/+$/, '');

export default function PinSetup({ onComplete }) {
  const [pin, setPin] = useState('');
  const [confirm, setConfirm] = useState('');
  const [skip, setSkip] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');

  function validatePin(p) {
    if (!/^\d{4,8}$/.test(p)) return 'PIN must be 4–8 digits.';
    return '';
  }

  async function handleCreate() {
    const err = validatePin(pin);
    if (err) return setError(err);
    if (pin !== confirm) return setError('PINs do not match.');
    // TODO(slice-3): POST /api/set-pin {pin}, then POST /api/login {pin}
    // to obtain the session cookie immediately.
    onComplete();
  }

  async function handleSkip() {
    if (!consent) return setError('Please acknowledge the consent box.');
    // TODO(slice-3): POST /api/profile {skip_pin_acknowledged: true}
    onComplete();
  }

  if (skip) {
    return (
      <div>
        <h3>Skip PIN setup</h3>
        <p>
          Without a PIN, anyone who has this dashboard URL can edit your
          preferences and trigger uploads/scrapes. The site is otherwise
          open by design — set a PIN later from the Monitor tab.
        </p>
        <label>
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />{' '}
          I understand and want to skip for now.
        </label>
        {error && <p style={{ color: '#c33' }}>{error}</p>}
        <button onClick={() => setSkip(false)}>Go back and create a PIN</button>
        <button onClick={handleSkip} disabled={!consent}>
          Skip
        </button>
      </div>
    );
  }

  return (
    <div>
      <h3>Lock your dashboard with a PIN</h3>
      <p>4–8 digits. You'll enter it next time you visit.</p>
      <label>
        PIN{' '}
        <input
          type="password"
          inputMode="numeric"
          maxLength={8}
          value={pin}
          onChange={(e) => setPin(e.target.value)}
        />
      </label>
      <label>
        Confirm{' '}
        <input
          type="password"
          inputMode="numeric"
          maxLength={8}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </label>
      {error && <p style={{ color: '#c33' }}>{error}</p>}
      <button onClick={handleCreate}>Create PIN</button>
      <button onClick={() => setSkip(true)}>Skip for now</button>
    </div>
  );
}
