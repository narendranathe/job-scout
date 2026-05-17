/**
 * PdfDropzone — drag-and-drop PDF upload with editable parsed metadata.
 *
 * PRD #89 Slice 3, Step 5 (Path A: "I have one resume to start").
 *
 * Flow:
 *   1. User drops/picks a PDF
 *   2. We read it as ArrayBuffer + base64 (vault upload accepts both
 *      base64 JSON and multipart; we use base64 because it survives
 *      the existing CSRF/JSON path with no extra encoder gymnastics)
 *   3. POST /api/vault/parse-filename → preview {company, role, …}
 *   4. User edits the auto-parsed fields if they want
 *   5. POST /api/vault/upload with the bytes + edited metadata
 *   6. onUploaded(versionKey) fires so the wizard can set it as default
 *
 * Props:
 *   t:           theme tokens
 *   apiBase:     RENDER_API
 *   authHeaders: () => {Authorization?: string} (from lib/api.js)
 *   csrfToken:   string from localStorage
 *   onUploaded(result): called on success with the upload API response
 *                       (result.version_key is what the wizard tracks)
 */
import { useRef, useState } from "react";

const MAX_PDF_BYTES = 10_000_000; // matches backend limit

export function PdfDropzone({ t, apiBase, authHeaders, csrfToken, onUploaded }) {
  const inputRef = useRef(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [stage, setStage] = useState("idle"); // idle | preview | uploading | done
  const [file, setFile] = useState(null);
  const [pdfBase64, setPdfBase64] = useState("");
  const [preview, setPreview] = useState(null); // {company, role, …}
  const [editCompany, setEditCompany] = useState("");
  const [editRole, setEditRole] = useState("");
  const [submittedAt, setSubmittedAt] = useState("");

  const reset = () => {
    setStage("idle");
    setFile(null);
    setPdfBase64("");
    setPreview(null);
    setEditCompany("");
    setEditRole("");
    setError(null);
  };

  const onFile = async (f) => {
    setError(null);
    if (!f) return;
    if (!/\.pdf$/i.test(f.name)) {
      setError("File must be a PDF (.pdf)");
      return;
    }
    if (f.size > MAX_PDF_BYTES) {
      setError(`PDF too large: ${(f.size / 1e6).toFixed(1)} MB (max 10 MB)`);
      return;
    }

    setBusy(true);
    try {
      // ArrayBuffer → base64 (no Buffer in browser; use FileReader's
      // readAsDataURL and strip the prefix).
      const dataUrl = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onerror = () => reject(r.error || new Error("read failed"));
        r.onload = () => resolve(r.result);
        r.readAsDataURL(f);
      });
      const b64 = String(dataUrl).split(",")[1] || "";

      // Ask backend to parse the filename
      const parseResp = await fetch(`${apiBase}/api/vault/parse-filename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: f.name }),
      });
      let parsed = {};
      if (parseResp.ok) parsed = await parseResp.json();

      setFile(f);
      setPdfBase64(b64);
      setPreview(parsed);
      setEditCompany(parsed.company || "");
      setEditRole(parsed.role || "");
      // File.lastModified is the mtime when the user picked the file,
      // which matches the PRD's "default to file's lastModified" rule.
      const mod = new Date(f.lastModified || Date.now());
      setSubmittedAt(mod.toISOString().slice(0, 10));
      setStage("preview");
    } catch (e) {
      setError(`Could not read file: ${e?.message || e}`);
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    onFile(e.dataTransfer.files?.[0]);
  };

  const onPick = (e) => {
    onFile(e.target.files?.[0]);
  };

  const save = async () => {
    if (!file || !pdfBase64) return;
    if (!editCompany.trim()) {
      setError("Company is required");
      return;
    }
    setBusy(true);
    setError(null);
    setStage("uploading");
    try {
      const body = {
        pdf_base64: pdfBase64,
        company: editCompany.trim(),
        role: editRole.trim() || null,
        filename: file.name,
        submitted_at: submittedAt
          ? new Date(submittedAt).toISOString()
          : null,
      };
      const resp = await fetch(`${apiBase}/api/vault/upload`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
          ...(authHeaders ? authHeaders() : {}),
        },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try {
          const e = await resp.json();
          if (e.error) msg = e.error;
        } catch (_) {}
        throw new Error(msg);
      }
      const result = await resp.json();
      setStage("done");
      onUploaded?.(result);
    } catch (e) {
      setError(String(e?.message || e));
      setStage("preview");
    } finally {
      setBusy(false);
    }
  };

  // ── Styles ────────────────────────────────────────────────────
  const dropArea = {
    border: `2px dashed ${drag ? t.ac : t.bd}`,
    borderRadius: 12,
    padding: "32px 20px",
    textAlign: "center",
    color: t.txM,
    background: drag ? `${t.ac}11` : t.bgS,
    cursor: "pointer",
    transition: "all .12s",
  };
  const field = {
    width: "100%",
    padding: "9px 12px",
    borderRadius: 8,
    border: `1px solid ${t.bd}`,
    background: t.bgS,
    color: t.tx,
    fontSize: 14,
    fontFamily: "inherit",
    boxSizing: "border-box",
  };
  const labelStyle = {
    display: "block",
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: ".06em",
    color: t.txM,
    marginBottom: 4,
  };

  if (stage === "done") {
    return (
      <div
        style={{
          padding: 18,
          borderRadius: 10,
          border: `1px solid ${t.ok}`,
          background: `${t.ok}11`,
          color: t.tx,
        }}
      >
        ✅ Saved <strong>{editCompany}</strong>
        {editRole ? ` — ${editRole}` : ""} to your vault.
        <div style={{ marginTop: 8, fontSize: 12, color: t.txM }}>
          This is now your default resume for job-match scoring.
        </div>
        <button
          type="button"
          onClick={reset}
          style={{
            marginTop: 10,
            padding: "6px 12px",
            borderRadius: 6,
            border: `1px solid ${t.bd}`,
            background: "transparent",
            color: t.tx,
            cursor: "pointer",
            fontSize: 12,
            fontFamily: "inherit",
          }}
        >
          Add another resume
        </button>
      </div>
    );
  }

  if (stage === "preview" || stage === "uploading") {
    return (
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "10px 14px",
            background: t.bgS,
            border: `1px solid ${t.bd}`,
            borderRadius: 8,
            marginBottom: 14,
          }}
        >
          <span style={{ fontSize: 22 }}>📄</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontWeight: 600,
                color: t.tx,
                fontSize: 13,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={file?.name}
            >
              {file?.name}
            </div>
            <div style={{ fontSize: 11, color: t.txM }}>
              {file?.size != null
                ? `${(file.size / 1024).toFixed(0)} KB`
                : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={reset}
            style={{
              padding: "4px 10px",
              borderRadius: 6,
              border: `1px solid ${t.bd}`,
              background: "transparent",
              color: t.txS,
              cursor: "pointer",
              fontSize: 12,
              fontFamily: "inherit",
            }}
          >
            Change file
          </button>
        </div>

        <div style={{ display: "grid", gap: 12 }}>
          <div>
            <label style={labelStyle}>Company</label>
            <input
              type="text"
              value={editCompany}
              onChange={(e) => setEditCompany(e.target.value)}
              style={field}
              placeholder="e.g. Anthropic"
            />
          </div>
          <div>
            <label style={labelStyle}>Role (optional)</label>
            <input
              type="text"
              value={editRole}
              onChange={(e) => setEditRole(e.target.value)}
              style={field}
              placeholder="e.g. Data Engineer"
            />
          </div>
          <div>
            <label style={labelStyle}>Submitted</label>
            <input
              type="date"
              value={submittedAt}
              onChange={(e) => setSubmittedAt(e.target.value)}
              style={field}
            />
            <div style={{ fontSize: 11, color: t.txM, marginTop: 4 }}>
              Defaults to the file's last-modified date.
            </div>
          </div>
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

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
          <button
            type="button"
            onClick={save}
            disabled={busy}
            style={{
              padding: "10px 18px",
              borderRadius: 8,
              border: `1px solid ${t.ac}`,
              background: t.ac,
              color: "#fff",
              fontWeight: 600,
              cursor: busy ? "wait" : "pointer",
              fontFamily: "inherit",
              fontSize: 14,
            }}
          >
            {busy ? "Saving…" : "Save to vault"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        style={dropArea}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
      >
        <div style={{ fontSize: 38, marginBottom: 8 }}>📤</div>
        <div style={{ fontWeight: 600, color: t.tx, marginBottom: 4 }}>
          Drop a PDF here, or click to pick one
        </div>
        <div style={{ fontSize: 12, color: t.txM }}>
          Up to 10 MB · We'll auto-parse company + role from the filename
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          onChange={onPick}
          style={{ display: "none" }}
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
    </div>
  );
}
