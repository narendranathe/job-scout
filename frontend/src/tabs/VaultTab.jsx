/**
 * VaultTab — full vault UI: stats, default-resume banner, upload form,
 * compare two versions, browse/search/sort all PDFs.
 *
 * State + handlers live in App(); this is purely presentational. Owns
 * three small inline style helpers since they're only used here.
 */
import { VaultRow } from "../components/VaultRow.jsx";
import { RENDER_API } from "../lib/api.js";

export function VaultTab({ state }) {
  const {
    t, iS,
    vaultLoading, vaultError, fetchVault,
    vaultStats, vaultFiles, filteredVaultFiles,
    vaultSearch, setVaultSearch, vaultSort, setVaultSort,
    vaultExpanded, vaultDetails, toggleVaultRow, deleteVaultVersion,
    defaultResumeVersion, setAsDefaultResume, defaultUpdating, defaultMsg,
    // Upload form
    vaultFileInputRef, vaultUpFile, setVaultUpFile,
    vaultUpCompany, setVaultUpCompany, vaultUpRole, setVaultUpRole,
    uploadVaultPdf, vaultUpLoading, vaultUpStatus,
    // Compare
    vaultCmpA, setVaultCmpA, vaultCmpB, setVaultCmpB,
    compareVaultVersions, vaultCmpLoading, vaultCmpResult,
  } = state;
  const filteredFiles = filteredVaultFiles;

  const labelStyle = {fontSize:12,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".06em",marginBottom:6,display:"block"};
  const cardStyle = {background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS,marginBottom:18};
  const btnPrimary = {padding:"9px 18px",borderRadius:9,border:"none",background:t.gP,color:"#fff",fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit"};
  const btnSecondary = {padding:"7px 14px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:13,fontWeight:500,cursor:"pointer",fontFamily:"inherit"};

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:18,flexWrap:"wrap",gap:12}}>
        <h2 style={{margin:0,fontSize:24,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>Resume Vault</h2>
        <div style={{display:"flex",gap:10,alignItems:"center"}}>
          {vaultLoading && <span style={{fontSize:13,color:t.txM,fontStyle:"italic"}}>Loading...</span>}
          <button onClick={fetchVault} disabled={vaultLoading} style={btnSecondary}>↻ Refresh</button>
        </div>
      </div>

      {!RENDER_API && (
        <div style={{...cardStyle,borderColor:`${t.er}40`,background:`${t.er}08`,color:t.er}}>
          ⚠️ No Render API configured. Set VITE_RENDER_URL in your .env file.
        </div>
      )}

      {vaultError && (
        <div style={{...cardStyle,borderColor:`${t.er}40`,background:`${t.er}08`,color:t.er}}>
          ❌ {vaultError}
        </div>
      )}

      {/* Default-resume status banner (Issue #39 part A) — surfaces
          which version is currently driving the Resume Match chip on
          job cards. Lets the user discover the feature even when
          scrolling vault entries first. */}
      <div style={{...cardStyle,
        borderColor:defaultResumeVersion?`${t.ac}40`:`${t.txM}30`,
        background:defaultResumeVersion?`${t.ac}08`:`${t.txM}05`,
        marginBottom:18}}>
        <div style={{display:"flex",alignItems:"center",gap:12,flexWrap:"wrap"}}>
          <span style={{fontSize:13,fontWeight:700,color:t.txM,textTransform:"uppercase",letterSpacing:".06em"}}>
            Default Resume
          </span>
          {defaultResumeVersion ? (
            <>
              <span style={{fontSize:14,fontFamily:"monospace",color:t.ac,fontWeight:700}}>
                ★ {defaultResumeVersion}
              </span>
              <span style={{fontSize:12,color:t.txM}}>
                — drives the "Resume Match %" chip on each job card
              </span>
              <button
                type="button"
                onClick={() => setAsDefaultResume("")}
                disabled={defaultUpdating}
                style={{...btnSecondary,marginLeft:"auto",opacity:defaultUpdating?0.5:1}}
                aria-label="Clear default resume">
                Clear default
              </button>
            </>
          ) : (
            <span style={{fontSize:13,color:t.txM}}>
              None set — click <em>Set as default</em> on any vault entry below to enable the per-card resume-match chip.
            </span>
          )}
        </div>
        {defaultMsg && (
          <div style={{marginTop:10,fontSize:13,color:defaultMsg.ok?t.ok:t.er,fontWeight:600}}>
            {defaultMsg.text}
          </div>
        )}
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:12,marginBottom:18}}>
        {[
          [vaultStats?.pdf_count ?? "—","PDFs in Vault",t.ac],
          [vaultStats?.text_count ?? "—","Extracted Texts",t.bl],
          [(vaultStats?.total_size_mb ?? 0) + " MB","Total Size",t.wm],
          [vaultStats?.unique_companies ?? "—","Companies",t.vi],
          [vaultStats?.db_versions ?? "—","DB Versions",t.ok],
        ].map(([v,l,c]) => (
          <div key={l} style={{padding:18,borderRadius:12,background:`${c}10`,border:`1px solid ${c}30`,textAlign:"center"}}>
            <div style={{fontSize:28,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{v}</div>
            <div style={{fontSize:12,color:t.txM,marginTop:4,textTransform:"uppercase",letterSpacing:".05em",fontWeight:600}}>{l}</div>
          </div>
        ))}
      </div>

      <div style={cardStyle}>
        <h3 style={{margin:"0 0 16px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Upload New Resume</h3>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:12}}>
          <div>
            <label htmlFor="vault-up-file" style={labelStyle}>PDF File <span style={{color:t.txS,fontWeight:400}}>(max 10 MB)</span></label>
            <input id="vault-up-file" ref={vaultFileInputRef} type="file" accept="application/pdf,.pdf"
              onChange={e => setVaultUpFile(e.target.files?.[0] || null)}
              style={{...iS,padding:"9px 12px"}}/>
          </div>
          <div>
            <label htmlFor="vault-up-company" style={labelStyle}>Company <span style={{color:t.er}}>*</span></label>
            <input id="vault-up-company" type="text" placeholder="e.g. Goldman Sachs"
              value={vaultUpCompany} maxLength={80} required aria-required="true"
              onChange={e => setVaultUpCompany(e.target.value)}
              style={iS}/>
          </div>
          <div>
            <label htmlFor="vault-up-role" style={labelStyle}>Role (optional)</label>
            <input id="vault-up-role" type="text" placeholder="e.g. Data Engineer"
              value={vaultUpRole} maxLength={80}
              onChange={e => setVaultUpRole(e.target.value)}
              style={iS}/>
          </div>
        </div>
        <div style={{display:"flex",gap:12,alignItems:"center",marginTop:14,flexWrap:"wrap"}}>
          <button onClick={uploadVaultPdf}
            disabled={vaultUpLoading || !vaultUpFile || !vaultUpCompany.trim()}
            style={{...btnPrimary,opacity:(vaultUpLoading || !vaultUpFile || !vaultUpCompany.trim())?0.5:1}}>
            {vaultUpLoading ? "Uploading..." : "Upload to Vault"}
          </button>
          {vaultUpStatus && (
            <span style={{fontSize:13,color:vaultUpStatus.ok?t.ok:t.er,fontWeight:600}}>
              {vaultUpStatus.msg}
            </span>
          )}
        </div>
      </div>

      <div style={cardStyle}>
        <h3 style={{margin:"0 0 16px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Compare Two Versions (TF-IDF)</h3>
        {(() => {
          const seen = new Set();
          const uniqueOptions = vaultFiles.filter(f => {
            if (!f.version_key || seen.has(f.version_key)) return false;
            seen.add(f.version_key);
            return true;
          });
          const opts = (
            <>
              <option value="">— select —</option>
              {uniqueOptions.map(f => (
                <option key={f.version_key} value={f.version_key}>
                  {f.version_key}{f.display_name ? ` (${f.display_name})` : ""}
                </option>
              ))}
            </>
          );
          return (
            <>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr auto",gap:12,alignItems:"end"}} className="vault-cmp-grid">
                <div>
                  <label htmlFor="vault-cmp-a" style={labelStyle}>Version A</label>
                  <select id="vault-cmp-a" value={vaultCmpA} onChange={e => setVaultCmpA(e.target.value)} style={iS}>{opts}</select>
                </div>
                <div>
                  <label htmlFor="vault-cmp-b" style={labelStyle}>Version B</label>
                  <select id="vault-cmp-b" value={vaultCmpB} onChange={e => setVaultCmpB(e.target.value)} style={iS}>{opts}</select>
                </div>
                <button type="button" onClick={compareVaultVersions}
                  disabled={vaultCmpLoading || !vaultCmpA || !vaultCmpB || vaultCmpA === vaultCmpB}
                  style={{...btnPrimary,opacity:(vaultCmpLoading || !vaultCmpA || !vaultCmpB || vaultCmpA === vaultCmpB)?0.5:1}}>
                  {vaultCmpLoading ? "Comparing..." : "Compare"}
                </button>
              </div>
              {uniqueOptions.length < 2 && (
                <div style={{marginTop:10,fontSize:12,color:t.txM}}>Need at least 2 distinct versions in the vault to compare.</div>
              )}
            </>
          );
        })()}
        {vaultCmpResult && (
          <div style={{marginTop:18,padding:16,background:t.bgS,borderRadius:10,border:`1px solid ${t.bd}`}}>
            {vaultCmpResult.error ? (
              <div style={{color:t.er,fontWeight:600}}>❌ {vaultCmpResult.error}</div>
            ) : (
              <>
                <div style={{display:"flex",alignItems:"center",gap:14,marginBottom:14,flexWrap:"wrap"}}>
                  <div style={{fontSize:36,fontWeight:700,color:t.ac,fontFamily:"'Playfair Display',serif"}}>
                    {Math.round(typeof vaultCmpResult.similarity_pct === "number" ? vaultCmpResult.similarity_pct : (vaultCmpResult.similarity||0)*100)}%
                  </div>
                  <div style={{fontSize:14,color:t.txS,flex:1,minWidth:200}}>
                    {vaultCmpResult.interpretation || "Similarity score"}
                  </div>
                </div>
                <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:12}}>
                  {vaultCmpResult.shared_skills?.length > 0 && (
                    <div>
                      <div style={labelStyle}>Shared Skills ({vaultCmpResult.shared_skills.length})</div>
                      <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                        {vaultCmpResult.shared_skills.slice(0,30).map(s => (
                          <span key={s} style={{fontSize:12,padding:"3px 9px",borderRadius:6,background:`${t.ok}15`,color:t.ok,border:`1px solid ${t.ok}30`}}>{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {vaultCmpResult.only_a?.length > 0 && (
                    <div>
                      <div style={labelStyle}>Only in A ({vaultCmpResult.only_a.length})</div>
                      <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                        {vaultCmpResult.only_a.slice(0,30).map(s => (
                          <span key={s} style={{fontSize:12,padding:"3px 9px",borderRadius:6,background:`${t.bl}15`,color:t.bl,border:`1px solid ${t.bl}30`}}>{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {vaultCmpResult.only_b?.length > 0 && (
                    <div>
                      <div style={labelStyle}>Only in B ({vaultCmpResult.only_b.length})</div>
                      <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                        {vaultCmpResult.only_b.slice(0,30).map(s => (
                          <span key={s} style={{fontSize:12,padding:"3px 9px",borderRadius:6,background:`${t.vi}15`,color:t.vi,border:`1px solid ${t.vi}30`}}>{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div style={cardStyle}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16,flexWrap:"wrap",gap:12}}>
          <h3 style={{margin:0,fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>
            Browse Vault ({filteredFiles.length}{vaultFiles.length !== filteredFiles.length ? ` of ${vaultFiles.length}` : ""})
          </h3>
          <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
            <input type="text" placeholder="Search vault..."
              value={vaultSearch}
              onChange={e => setVaultSearch(e.target.value)}
              style={{...iS,maxWidth:240,padding:"8px 12px",fontSize:14}}/>
            <select value={vaultSort} onChange={e => setVaultSort(e.target.value)}
              style={{...iS,width:"auto",padding:"8px 12px",fontSize:14,cursor:"pointer"}}>
              <option value="company">Sort: Company</option>
              <option value="role">Sort: Role</option>
              <option value="version_key">Sort: Key</option>
              <option value="filename">Sort: Filename</option>
              <option value="size_bytes">Sort: Size</option>
            </select>
          </div>
        </div>

        {filteredFiles.length === 0 ? (
          <div style={{padding:32,textAlign:"center",color:t.txM,fontStyle:"italic"}}>
            {vaultLoading ? "Loading vault files..." : "No vault files found."}
          </div>
        ) : (
          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            {filteredFiles.map(f => (
              <VaultRow
                key={f.filename || f.version_key}
                f={f}
                t={t}
                isOpen={vaultExpanded === f.version_key}
                isDefault={defaultResumeVersion === f.version_key}
                det={vaultDetails[f.version_key]}
                onToggle={toggleVaultRow}
                onDelete={deleteVaultVersion}
                onSetDefault={setAsDefaultResume}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
