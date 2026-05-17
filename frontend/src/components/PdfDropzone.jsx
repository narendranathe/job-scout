/**
 * PdfDropzone — scaffolding for Slice 3 of issue #89.
 *
 * Tracking:  https://github.com/narendranathe/job-scout/issues/92
 * Parent PRD: https://github.com/narendranathe/job-scout/issues/89
 * Spec:      docs/superpowers/specs/2026-05-17-first-run-onboarding-wizard.md
 *
 * Drag-and-drop PDF upload with an editable preview card. Used by
 * Step 5 of OnboardingWizard, and (optionally) reusable elsewhere
 * once a "single-upload" UX is needed off the wizard path.
 *
 * Flow:
 *   1. User drops a PDF
 *   2. POST /api/vault/parse-filename {filename}
 *      → server echoes parse_resume_filename() result
 *      → {company, role, version_key, display_name, job_id}
 *   3. Render preview card with editable Company / Role / Submitted-at
 *      (Submitted-at defaults to file.lastModified)
 *   4. User confirms → POST /api/vault/upload (multipart) with bytes +
 *      edited metadata + submitted_at
 *   5. Caller (wizard) gets {versionKey, ...} back via onUploaded
 *
 * Props:
 *   onUploaded(result)  — called once on successful upload
 *   onSkip()            — user dismissed without uploading
 *
 * Backend dependency: Slice 3 also adds POST /api/vault/parse-filename
 * (small echo route in vault_routes.py). Slice 1 adds cookie auth +
 * CSRF; this component must thread the CSRF header through both POSTs
 * when a cookie session is active.
 */

import React, { useState } from 'react';

const API = (import.meta.env.VITE_RENDER_URL || '').replace(/\/+$/, '');

export default function PdfDropzone({ onUploaded, onSkip }) {
  const [file, setFile] = useState(null);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState('');

  async function handleFile(f) {
    if (!f) return;
    if (f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) {
      setError('That doesn\'t look like a PDF — only .pdf files are supported.');
      return;
    }
    setFile(f);
    setError('');
    // TODO(slice-3): POST /api/vault/parse-filename and set meta from response
    // Stub: derive a minimal meta from the filename until the endpoint lands
    setMeta({
      company: '',
      role: '',
      submittedAt: new Date(f.lastModified).toISOString(),
    });
  }

  async function handleConfirm() {
    // TODO(slice-3): multipart POST to /api/vault/upload
    // const form = new FormData();
    // form.append('pdf', file);
    // form.append('company', meta.company);
    // form.append('role', meta.role);
    // form.append('submitted_at', meta.submittedAt);
    // const resp = await fetch(`${API}/api/vault/upload`, { method: 'POST', body: form, headers: authHeaders() });
    // if (resp.ok) onUploaded(await resp.json());
    onUploaded({ versionKey: '(scaffold)' });
  }

  return (
    <div style={{ border: '2px dashed #888', padding: 24, borderRadius: 8 }}>
      <h3>Upload your first resume</h3>
      <input
        type="file"
        accept="application/pdf,.pdf"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      {error && <p style={{ color: '#c33' }}>{error}</p>}
      {meta && (
        <div style={{ marginTop: 16 }}>
          <label>
            Company{' '}
            <input
              value={meta.company}
              onChange={(e) => setMeta({ ...meta, company: e.target.value })}
            />
          </label>
          <label>
            Role{' '}
            <input
              value={meta.role}
              onChange={(e) => setMeta({ ...meta, role: e.target.value })}
            />
          </label>
          <label>
            Submitted{' '}
            <input
              type="datetime-local"
              value={meta.submittedAt.slice(0, 16)}
              onChange={(e) =>
                setMeta({ ...meta, submittedAt: new Date(e.target.value).toISOString() })
              }
            />
          </label>
          <button onClick={handleConfirm}>Save to vault</button>
        </div>
      )}
      {onSkip && (
        <button onClick={onSkip} style={{ marginTop: 16 }}>
          Skip for now
        </button>
      )}
    </div>
  );
}
