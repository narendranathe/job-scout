/**
 * PreviewModeBanner — scaffolding for Slice 4 of issue #89.
 *
 * Tracking:  https://github.com/narendranathe/job-scout/issues/93
 * Parent PRD: https://github.com/narendranathe/job-scout/issues/89
 *
 * Persistent top-of-page banner shown when the user chose
 * "Skip — I'm just looking" on wizard step 1
 * (user_profile.onboarded_at == "preview").
 *
 * Behavior:
 *   - Visible on every dashboard page in preview mode
 *   - Single CTA "Start setup" → /setup?force=1
 *   - Dismiss link writes user_profile.preview_banner_dismissed = 1
 *     for the current session (Slice 4 may store this in
 *     localStorage instead — TBD during implementation)
 *
 * Companion piece: a click-interceptor in App.jsx that intercepts any
 * write surface (Tracker pills, Vault upload, Save buttons, scrape
 * trigger) and opens a modal pointing back at the wizard. This banner
 * is the always-visible nudge; the modal is the write-time block.
 *
 * Props:
 *   onDismiss()  — user clicked the dismiss link
 */

import React from 'react';

export default function PreviewModeBanner({ onDismiss }) {
  return (
    <div
      role="status"
      style={{
        background: '#fff8e1',
        borderBottom: '1px solid #f0c040',
        padding: '8px 16px',
        fontSize: 13,
        textAlign: 'center',
      }}
    >
      <strong>Preview mode.</strong>{' '}
      You're browsing JobScout without setting up. Any changes you try
      to make will prompt you to finish setup first.
      <a
        href="/setup?force=1"
        style={{ marginLeft: 12, textDecoration: 'underline' }}
      >
        Start setup
      </a>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss banner"
          style={{
            marginLeft: 12,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            opacity: 0.6,
          }}
        >
          ✕
        </button>
      )}
    </div>
  );
}
