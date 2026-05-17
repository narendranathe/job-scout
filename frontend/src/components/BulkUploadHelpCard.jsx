/**
 * BulkUploadHelpCard — "I have many resumes" panel (Path B of Step 5).
 *
 * PRD #89 Slice 3. Static informational card that shows the user how to
 * point ``backend/tools/bulk_upload_to_render.py`` at THIS dashboard's
 * Render URL + their API token. We inline the values dynamically so
 * the user doesn't have to translate placeholders.
 *
 * Includes a "Refresh vault" button so the user can confirm uploads
 * land while the script runs.
 */
import { useState } from "react";

export function BulkUploadHelpCard({ t, apiBase, apiToken, onRefresh }) {
  const [count, setCount] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await fetch(`${apiBase}/api/vault/stats`, {
        headers: apiToken ? { Authorization: `Bearer ${apiToken}` } : {},
        credentials: "include",
      });
      if (r.ok) {
        const d = await r.json();
        const n = d.stats?.pdf_count || d.pdf_count || 0;
        setCount(n);
        onRefresh?.(n);
      }
    } catch (_) {
      // Silently no-op — count stays as it was.
    } finally {
      setBusy(false);
    }
  };

  const tokenPlaceholder = apiToken
    ? '"$YOUR_TOKEN"' // The user already has one; we don't echo it.
    : '"<set if API_SECRET configured, else leave blank>"';

  const script = [
    "cd backend",
    `$env:JOBSCOUT_API_URL    = "${apiBase || "<dashboard URL>"}"`,
    `$env:JOBSCOUT_API_SECRET = ${tokenPlaceholder}`,
    `python -m tools.bulk_upload_to_render --source-dir "<your folder>" \\`,
    `    --exclude '(?i)^(?:jayanth|lankipalli|naru_kiran|sai_maruthi|siva\\s+chandan)'`,
  ].join("\n");

  return (
    <div
      style={{
        padding: 18,
        borderRadius: 10,
        border: `1px solid ${t.bd}`,
        background: t.bgS,
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 14, color: t.tx, marginBottom: 8 }}>
        Have many resumes?
      </div>
      <p style={{ color: t.txM, fontSize: 13, margin: "0 0 10px" }}>
        Bulk-upload a whole folder via the CLI:
      </p>
      <pre
        style={{
          background: t.cd,
          border: `1px solid ${t.bd}`,
          borderRadius: 8,
          padding: 12,
          color: t.tx,
          fontSize: 12,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          overflowX: "auto",
          margin: 0,
        }}
      >
        {script}
      </pre>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginTop: 12,
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          onClick={refresh}
          disabled={busy}
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: `1px solid ${t.bd}`,
            background: t.cd,
            color: t.tx,
            fontSize: 12,
            fontWeight: 600,
            cursor: busy ? "wait" : "pointer",
            fontFamily: "inherit",
          }}
        >
          {busy ? "Checking…" : "🔄 Refresh vault"}
        </button>
        {count !== null && (
          <span style={{ color: t.txM, fontSize: 12 }}>
            {count} {count === 1 ? "PDF" : "PDFs"} in vault
          </span>
        )}
      </div>
    </div>
  );
}
