/**
 * Single row in the Vault tab — collapsed/expanded view of one resume
 * version. Memoized via React.memo so a list of 95 rows doesn't
 * re-render every time the parent re-renders.
 *
 * Why styles are computed inside the row: previously the App() body
 * declared these as inline literals inside an IIFE on every render —
 * fresh object identities defeated React.memo. Computing them here
 * ties the recompute to the row's own (memo-gated) re-renders, which
 * only fire when t/isOpen/etc. actually change for this row.
 */
import { memo } from "react";

import { timeAgo } from "../lib/format.js";

function _VaultRow({ f, t, isOpen, isDefault, det, onToggle, onDelete, onSetDefault }) {
  const labelStyle = {fontSize:12,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".06em",marginBottom:6,display:"block"};
  const btnSecondary = {padding:"7px 14px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:13,fontWeight:500,cursor:"pointer",fontFamily:"inherit"};
  const btnDanger = {padding:"7px 14px",borderRadius:8,border:`1px solid ${t.er}40`,background:`${t.er}10`,color:t.er,fontSize:13,fontWeight:500,cursor:"pointer",fontFamily:"inherit"};
  // Set-as-default: outlined → click → ★ Default pill once selected. The
  // active variant is intentionally disabled — clicking it again would be
  // a no-op POST.
  const btnDefault = {padding:"7px 12px",borderRadius:8,border:`1px solid ${t.ac}50`,background:`${t.ac}10`,color:t.ac,fontSize:13,fontWeight:600,cursor:"pointer",fontFamily:"inherit"};
  const btnDefaultActive = {padding:"7px 12px",borderRadius:8,border:`1px solid ${t.ac}`,background:t.ac,color:"#fff",fontSize:13,fontWeight:700,cursor:"default",fontFamily:"inherit"};

  const sizeLabel = typeof f.size_kb === "number"
    ? (f.size_kb >= 1024 ? `${(f.size_kb/1024).toFixed(1)} MB` : `${f.size_kb} KB`)
    : null;
  return (
    <div style={{background:isDefault?`${t.ac}08`:t.bgS,borderRadius:10,border:`1px solid ${isDefault?t.ac:t.bd}`,overflow:"hidden"}}>
      <div style={{padding:"12px 14px",display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,flexWrap:"wrap"}} className="vault-row">
        <div style={{flex:1,minWidth:200}}>
          <div style={{fontSize:14,fontWeight:700,color:t.tx,display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
            {f.company || "—"}{f.role ? ` · ${f.role}` : ""}
            {isDefault && (
              <span title="This resume drives the Resume Match % chip on job cards"
                style={{fontSize:10,padding:"2px 7px",borderRadius:5,background:t.ac,color:"#fff",fontWeight:800,letterSpacing:".05em",textTransform:"uppercase"}}>
                ★ Default
              </span>
            )}
          </div>
          <div style={{fontSize:12,color:t.txM,marginTop:3,wordBreak:"break-word"}}>
            <span style={{fontFamily:"monospace",color:t.ac}}>{f.version_key}</span>
            {f.filename && <span> · {f.filename}</span>}
            {sizeLabel && <span> · {sizeLabel}</span>}
          </div>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          {isDefault ? (
            <button type="button" style={btnDefaultActive}
              aria-label={`${f.version_key} is the current default resume`}
              disabled>
              ★ Default
            </button>
          ) : (
            <button type="button" style={btnDefault}
              aria-label={`Set ${f.version_key} as the default resume`}
              onClick={() => onSetDefault && onSetDefault(f.version_key)}>
              ☆ Set as default
            </button>
          )}
          <button type="button" style={btnSecondary}
            aria-expanded={isOpen}
            aria-label={`${isOpen?"Hide":"View"} details for ${f.version_key}`}
            onClick={() => onToggle(f.version_key, isOpen)}>
            {isOpen ? "Hide" : "View Details"}
          </button>
          <button type="button" style={btnDanger}
            aria-label={`Delete vault version ${f.version_key}`}
            onClick={() => onDelete(f.version_key)}>
            Delete
          </button>
        </div>
      </div>
      {isOpen && (
        <div style={{padding:"14px 16px",borderTop:`1px solid ${t.bd}`,background:t.cd}}>
          {!det || det.__loading ? (
            <div style={{color:t.txM,fontStyle:"italic",fontSize:13}}>Loading details...</div>
          ) : det.error ? (
            <div style={{color:t.er,fontSize:13}}>❌ {det.error}</div>
          ) : (
            <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:12}}>
              <div>
                <div style={labelStyle}>Display Name</div>
                <div style={{fontSize:14,color:t.tx}}>{det.display_name || "—"}</div>
              </div>
              <div>
                <div style={labelStyle}>Target Companies</div>
                <div style={{fontSize:14,color:t.tx}}>
                  {(det.target_companies || []).join(", ") || "—"}
                </div>
              </div>
              <div>
                <div style={labelStyle}>Target Roles</div>
                <div style={{fontSize:14,color:t.tx}}>
                  {(det.target_roles || []).join(", ") || "—"}
                </div>
              </div>
              <div style={{gridColumn:"1 / -1"}}>
                <div style={labelStyle}>Extracted Skills ({(det.extracted_skills || []).length})</div>
                <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                  {(det.extracted_skills || []).slice(0,40).map(s => (
                    <span key={s} style={{fontSize:12,padding:"3px 9px",borderRadius:6,background:t.acL,color:t.ac,border:`1px solid ${t.ac}30`}}>{s}</span>
                  ))}
                  {(det.extracted_skills || []).length === 0 && <span style={{color:t.txM,fontSize:13,fontStyle:"italic"}}>none</span>}
                </div>
              </div>
              {det.notes && (
                <div style={{gridColumn:"1 / -1"}}>
                  <div style={labelStyle}>Notes</div>
                  <div style={{fontSize:13,color:t.txS}}>{det.notes}</div>
                </div>
              )}
              <div>
                <div style={labelStyle}>Resume Length</div>
                <div style={{fontSize:14,color:t.tx}}>{(det.resume_text || "").length.toLocaleString()} chars</div>
              </div>
              {det.updated_at && (
                <div>
                  <div style={labelStyle}>Updated</div>
                  <div style={{fontSize:14,color:t.tx}}>{timeAgo(det.updated_at)}</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export const VaultRow = memo(_VaultRow);
