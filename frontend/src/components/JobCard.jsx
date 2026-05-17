/**
 * JobCard — the memoized job listing card. Largest single component in
 * the dashboard. Extracted from App.jsx as part of the split.
 *
 * React.memo is preserved at the bottom (default export wraps the
 * underscore-prefixed component). All shared identities (style objects,
 * empty refs, helper fns) live in ../lib/jobConstants.js so a re-render
 * of App.jsx doesn't blow up memoization here.
 *
 * Props (all read-only — parent owns state, JobCard fires callbacks):
 *   j                — job row
 *   t                — theme tokens
 *   open             — is the expanded body visible
 *   app              — application row (status, notes, resume_version)
 *   coHistory        — array of prior applications at this company
 *   bm               — best-match drawer state for this card
 *   jobFit           — per-card default-resume fit score chip state
 *   vdMap            — version-details cache for the best-match drawer
 *   expandedRows     — { [version_key]: true } map for the drawer rows
 *   pdfState         — per-version PDF-download state
 *   onToggleOpen     — toggle the card's expanded body
 *   onSave           — save under a status pill
 *   onRemove         — remove from tracker
 *   onMarkApplied    — mark applied (uses content_hash on POST)
 *   onFetchBestMatch — POST /api/vault/best-match for this job
 *   onToggleVersionRow — expand a row in the best-match drawer
 *   onDownloadResumePdf — GET /api/vault/version/<key>/pdf
 */
import { memo } from "react";

import { fmtSal, timeAgo } from "../lib/format.js";
import {
  ATS_META,
  ROLE_CATS,
  ST_COLOR,
  ST_LABEL,
  JC_STYLES,
  isPlatinum,
  likelySponsor,
  jobFitTone,
  stopProp,
} from "../lib/jobConstants.js";
import { LogoImg } from "./LogoImg.jsx";
import { Pill } from "./Pill.jsx";

function _JobCard({
  j,
  t,
  open,
  app,
  coHistory,
  bm,
  jobFit,
  vdMap,
  expandedRows,
  pdfState,
  onToggleOpen,
  onSave,
  onRemove,
  onMarkApplied,
  onFetchBestMatch,
  onToggleVersionRow,
  onDownloadResumePdf,
}) {
  const sc = j.relevance_score || 0;
  const ats = ATS_META[j.ats] || ATS_META.unknown;
  const catLbl = ROLE_CATS.find(r => r.id === j._cat)?.label || "Other";
  const isApplied = j.application_status === 'applied';

  const cardStyle = {
    background:t.cd,borderRadius:12,border:`1px solid ${t.bd}`,
    overflow:"hidden",cursor:"pointer",transition:"all .2s",
    boxShadow:open?t.sh:t.shS,opacity:isApplied?0.45:1,
  };
  const handleCardClick = () => onToggleOpen(j.external_id);

  // Job-fit chip: only rendered when a default resume is configured AND a
  // score has been (or is being) fetched for THIS card. Three visual
  // states, each visually distinct:
  //  - loading:  "📄 …" on muted background
  //  - error:    "⚠️ —" on warning-tinted background (separate from loading
  //              so a stuck request doesn't look like an in-flight one)
  //  - scored:   color + emoji + percent + (tone) label
  //
  // WCAG 1.4.1: the chip is NEVER color-only. The score variant carries a
  // green/yellow/red emoji icon (visible to users who can't perceive the
  // background color) AND an aria-label spelling out the tone ("Strong",
  // "Moderate", "Weak") for screen readers.
  const fitChip = (() => {
    if (!jobFit) return null;
    if (jobFit.loading) {
      return (
        <span title="Loading resume match…"
          aria-label="Resume match: loading"
          role="status"
          style={{padding:"3px 7px",borderRadius:6,background:`${t.txM}15`,border:`1px solid ${t.txM}30`,
            fontSize:11,fontWeight:700,color:t.txM,whiteSpace:"nowrap"}}>
          📄 …
        </span>
      );
    }
    if (jobFit.error || jobFit.pct == null) {
      return (
        <span title={jobFit.error || "No match score"}
          aria-label={`Resume match: error${jobFit.error ? ` — ${jobFit.error}` : ""}`}
          style={{padding:"3px 7px",borderRadius:6,background:`${t.wm}15`,border:`1px solid ${t.wm}40`,
            fontSize:11,fontWeight:700,color:t.wm,whiteSpace:"nowrap"}}>
          ⚠️ —
        </span>
      );
    }
    const pct = jobFit.pct;
    const tone = jobFitTone(pct, t);
    return (
      <span
        title={`Resume match against default version${jobFit.versionKey ? ` (${jobFit.versionKey})` : ""}: ${pct}% (${tone.label})`}
        aria-label={`Resume match: ${pct} percent — ${tone.label}`}
        style={{padding:"3px 8px",borderRadius:6,background:tone.bg,border:`1px solid ${tone.bd}`,
          fontSize:11,fontWeight:800,color:tone.fg,whiteSpace:"nowrap",letterSpacing:".02em"}}>
        {tone.icon} {pct}%
      </span>
    );
  })();

  return (
    <div onClick={handleCardClick} style={cardStyle}>
      <div className="job-card-top" style={JC_STYLES.topRow}>
        <div style={JC_STYLES.titleRow}>
          <LogoImg name={j.company} size={40} t={t}/>
          <div style={JC_STYLES.titleInner}>
            <div style={JC_STYLES.titleLine}>
              <span style={{fontSize:17,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>{j.title}</span>
              {isApplied && <Pill ch={ST_LABEL.applied} c={ST_COLOR.applied} t={t}/>}
              <Pill ch={catLbl} c={t.bl} t={t}/>
              <Pill ch={`${ats.i} ${ats.l}`} c={ats.c} t={t}/>
            </div>
            <div className="job-meta" style={{...JC_STYLES.metaRow, color:t.txS}}>
              <span style={{fontWeight:700}}>{j.company}</span>
              {isPlatinum(j) && <span style={JC_STYLES.platinum}>PLATINUM</span>}
              <span>{j._loc.display||"—"}</span>
              {j._loc.state && <span style={{color:t.bl,fontWeight:600}}>📍 {j._loc.state}</span>}
              {j._loc.isRemote && <span style={{color:t.ok,fontWeight:700}}>🏠 Remote</span>}
              {j.salary_max>0 && <span style={{color:t.wm,fontWeight:700}}>{fmtSal(j.salary_min)}–{fmtSal(j.salary_max)}</span>}
              {j.posted_at && <span style={{color:t.txM}}>{timeAgo(j.posted_at)}</span>}
              {j.sponsorship && <span title="JD mentions visa sponsorship" style={{color:t.vi,fontWeight:700}}>🛂</span>}
              {(j.rare_skill_hits||[]).length>0 && <span title={`Rare skills: ${j.rare_skill_hits.join(", ")}`} style={{color:t.vi,fontWeight:700}}>🎯 {j.rare_skill_hits.length}</span>}
            </div>
          </div>
        </div>
        <div style={JC_STYLES.scoreCluster}>
          {fitChip}
          <div style={{width:52,height:52,borderRadius:12,display:"flex",alignItems:"center",justifyContent:"center",background:t.sBg(sc)}}>
            <span style={{fontSize:20,fontWeight:800,color:t.sTx(sc),fontFamily:"'Playfair Display',serif"}}>{(sc*100).toFixed(0)}</span>
          </div>
          <span style={{fontSize:18,color:t.txM,transform:open?"rotate(180deg)":"",transition:"transform .2s"}}>▾</span>
        </div>
      </div>
      {open && (
        <div style={{padding:"0 20px 18px",borderTop:`1px solid ${t.bd}`}}>
          <div style={JC_STYLES.skillsRow}>
            {(j.matched_skills||[]).map(s => <Pill key={s} ch={s} t={t} big/>)}
            {(j.sponsorship||likelySponsor(j)) && <Pill ch="🛂 Likely H1B" c={t.vi} t={t} big/>}
          </div>
          {j.description && (
            <p style={{fontSize:15,color:t.txS,lineHeight:1.85,maxHeight:160,overflow:"hidden",margin:"10px 0"}}>
              {j.description.slice(0,700)}...
            </p>
          )}
          {coHistory && coHistory.length > 0 && (
            <div style={{margin:"12px 0",padding:"12px 16px",borderRadius:10,background:`${t.wm}10`,border:`1px solid ${t.wm}30`}}>
              <div style={{fontSize:12,fontWeight:700,color:t.wm,textTransform:"uppercase",letterSpacing:".06em",marginBottom:8}}>
                📋 Your history at {j.company}
              </div>
              {coHistory.map((a, i) => (
                <div key={i} style={{display:"flex",gap:10,alignItems:"center",padding:"5px 0",borderBottom:i<coHistory.length-1?`1px solid ${t.bd}`:"none",flexWrap:"wrap",fontSize:13}}>
                  <span style={{color:t.txS,flex:1,minWidth:120}}>{a.title}</span>
                  {a.applied_at && <span style={{color:t.txM}}>{timeAgo(a.applied_at)}</span>}
                  {a.resume_version && <span style={{color:t.ac,fontWeight:600}}>📄 {a.resume_version}</span>}
                  <span style={{fontWeight:700,color:ST_COLOR[a.status]||t.txM,padding:"2px 8px",borderRadius:5,background:`${ST_COLOR[a.status]||t.txM}18`,fontSize:12}}>
                    {a.status.charAt(0).toUpperCase()+a.status.slice(1)}
                  </span>
                </div>
              ))}
            </div>
          )}
          <div style={JC_STYLES.actionsRow}>
            <a href={j.url} target="_blank" rel="noopener noreferrer" onClick={stopProp}
              style={{display:"inline-block",padding:"11px 24px",borderRadius:9,background:t.gP,color:"#fff",fontSize:15,fontWeight:700,textDecoration:"none",boxShadow:`0 3px 12px ${t.ac}30`}}>
              Apply →
            </a>
            <button
              onClick={e => { e.stopPropagation(); onMarkApplied(j); }}
              style={JC_STYLES.appliedBtn}
            >
              ✓ Applied
            </button>
            {(() => {
              const loading = bm?.loading;
              return (
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); if (!loading) onFetchBestMatch(j); }}
                  disabled={loading || !j.external_id}
                  style={{padding:"9px 14px",borderRadius:8,border:`1.5px solid ${t.vi}`,
                    background:loading?`${t.vi}10`:`${t.vi}18`,color:t.vi,
                    fontSize:13,fontWeight:700,cursor:loading?"wait":"pointer",fontFamily:"inherit",
                    transition:"all .15s",whiteSpace:"nowrap",opacity:loading?0.7:1,minHeight:36}}>
                  {loading?"Matching…":(bm?.data?"↻ Refresh Match":"📄 Find Best Resume")}
                </button>
              );
            })()}
            <div style={JC_STYLES.statusBtnsRow}>
              {Object.keys(ST_LABEL).map(st => {
                const isCur = app?.status === st;
                const c = ST_COLOR[st];
                return (
                  <button key={st} onClick={e => { e.stopPropagation(); if (isCur) onRemove(j.external_id); else onSave(j, st); }}
                    style={{padding:"9px 13px",borderRadius:8,border:`1.5px solid ${isCur?c:t.bd}`,
                      background:isCur?`${c}18`:"transparent",color:isCur?c:t.txM,
                      fontSize:13,fontWeight:isCur?700:500,cursor:"pointer",fontFamily:"inherit",
                      transition:"all .15s",whiteSpace:"nowrap"}}>
                    {ST_LABEL[st]}
                  </button>
                );
              })}
            </div>
          </div>
          {bm && !bm.loading && (() => {
            if (bm.error) {
              return (
                <div onClick={stopProp} style={{marginTop:12,padding:"10px 14px",borderRadius:8,background:`${t.wm}10`,border:`1px solid ${t.wm}30`,color:t.wm,fontSize:13}}>
                  Resume match failed: {bm.error}
                </div>
              );
            }
            if (!bm.data || !bm.data.rankings || bm.data.rankings.length === 0) {
              return (
                <div onClick={stopProp} style={{marginTop:12,padding:"10px 14px",borderRadius:8,background:`${t.bd}30`,border:`1px solid ${t.bd}`,color:t.txM,fontSize:13}}>
                  No resume versions found in vault.
                </div>
              );
            }
            return (
              <div onClick={stopProp}
                style={{marginTop:14,padding:"14px 16px",borderRadius:10,background:`${t.vi}08`,border:`1px solid ${t.vi}40`}}>
                <div style={{fontSize:12,fontWeight:700,color:t.vi,textTransform:"uppercase",letterSpacing:".06em",marginBottom:10}}>
                  📄 Top {bm.data.rankings.length} resume matches · {bm.data.count} in vault
                </div>
                <div style={{display:"flex",flexDirection:"column",gap:8}}>
                  {bm.data.rankings.map((rk, idx) => {
                    const isRowOpen = !!expandedRows[rk.version_key];
                    const vd = vdMap[rk.version_key];
                    const pct = Math.round((rk.combined_score||0)*100);
                    const skillPct = rk.skill_match_pct||0;
                    const matchedCount = Array.isArray(rk.matched_skills)?rk.matched_skills.length:0;
                    return (
                      <div key={rk.version_key}
                        style={{padding:"10px 12px",borderRadius:8,background:t.cd,border:`1px solid ${t.bd}`}}>
                        <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}}>
                          <span style={{fontSize:12,fontWeight:800,color:t.txM,minWidth:24}}>#{idx+1}</span>
                          <span style={{fontSize:14,fontWeight:700,color:t.tx,flex:1,minWidth:140,wordBreak:"break-word"}}>
                            {rk.display_name || rk.version_key}
                          </span>
                          <div style={{display:"flex",alignItems:"center",gap:8,minWidth:160,flex:"0 1 220px"}}>
                            <div style={{...JC_STYLES.rkBar, background:`${t.bd}80`}}>
                              <div style={{width:`${Math.max(0,Math.min(100,pct))}%`,height:"100%",background:t.vi,transition:"width .25s"}}/>
                            </div>
                            <span style={{fontSize:13,fontWeight:800,color:t.vi,minWidth:38,textAlign:"right"}}>{pct}%</span>
                          </div>
                          <span title={`${matchedCount} matched skills · ${skillPct}% skill overlap`} style={{fontSize:12,color:t.txM,fontWeight:600}}>
                            🎯 {matchedCount} · {skillPct}%
                          </span>
                          <button
                            type="button"
                            aria-expanded={isRowOpen}
                            aria-label={`${isRowOpen?"Hide":"View"} details for ${rk.display_name || rk.version_key}`}
                            onClick={() => onToggleVersionRow(j.external_id, rk.version_key)}
                            style={{padding:"8px 12px",borderRadius:6,border:`1px solid ${t.vi}50`,background:isRowOpen?`${t.vi}20`:"transparent",color:t.vi,fontSize:12,fontWeight:700,cursor:"pointer",fontFamily:"inherit",minHeight:32}}>
                            {isRowOpen?"Hide ▴":"View ▾"}
                          </button>
                          {(() => {
                            const pd = pdfState[rk.version_key];
                            const dlLoading = !!pd?.loading;
                            const dlError = pd?.error || null;
                            const fallbackName = rk.filename || `${rk.version_key}.pdf`;
                            return (
                              <button
                                type="button"
                                aria-label={`Download PDF for ${rk.display_name || rk.version_key}`}
                                aria-busy={dlLoading}
                                title={dlError || `Download ${fallbackName}`}
                                disabled={dlLoading}
                                onClick={() => { if (!dlLoading) onDownloadResumePdf(rk.version_key, fallbackName); }}
                                style={{padding:"8px 12px",borderRadius:6,border:`1px solid ${dlError?t.wm:t.ok}60`,background:dlError?`${t.wm}15`:`${t.ok}15`,color:dlError?t.wm:t.ok,fontSize:12,fontWeight:700,cursor:dlLoading?"wait":"pointer",fontFamily:"inherit",minHeight:32,opacity:dlLoading?0.7:1,whiteSpace:"nowrap"}}>
                                {dlLoading?"Downloading…":(dlError?"⚠ Retry":"📥 PDF")}
                              </button>
                            );
                          })()}
                        </div>
                        {pdfState[rk.version_key]?.error && (
                          <div
                            role="alert"
                            aria-live="polite"
                            style={{marginTop:6,fontSize:11,color:t.wm,fontWeight:600,lineHeight:1.4,wordBreak:"break-word"}}>
                            ⚠ {pdfState[rk.version_key].error}
                          </div>
                        )}
                        {isRowOpen && (
                          <div style={{marginTop:10,padding:"10px 12px",borderRadius:6,background:`${t.bd}30`,fontSize:12,color:t.txS,lineHeight:1.7}}>
                            {vd?.loading && <span style={{color:t.txM}}>Loading version details…</span>}
                            {vd?.error && <span style={{color:t.wm}}>Failed: {vd.error}</span>}
                            {vd?.data && (
                              <div style={JC_STYLES.vdGrid}>
                                <div><span style={{color:t.txM,fontWeight:700}}>Key:</span> {vd.data.version_key}</div>
                                {vd.data.display_name && <div><span style={{color:t.txM,fontWeight:700}}>Name:</span> {vd.data.display_name}</div>}
                                {Array.isArray(vd.data.target_companies) && vd.data.target_companies.length>0 && (
                                  <div><span style={{color:t.txM,fontWeight:700}}>Companies:</span> {vd.data.target_companies.join(", ")}</div>
                                )}
                                {Array.isArray(vd.data.target_roles) && vd.data.target_roles.length>0 && (
                                  <div><span style={{color:t.txM,fontWeight:700}}>Roles:</span> {vd.data.target_roles.join(", ")}</div>
                                )}
                                {vd.data.created_at && <div><span style={{color:t.txM,fontWeight:700}}>Created:</span> {vd.data.created_at}</div>}
                                {vd.data.updated_at && <div><span style={{color:t.txM,fontWeight:700}}>Updated:</span> {vd.data.updated_at}</div>}
                                {vd.data.notes && <div><span style={{color:t.txM,fontWeight:700}}>Notes:</span> {vd.data.notes}</div>}
                                {Array.isArray(vd.data.extracted_skills) && vd.data.extracted_skills.length>0 && (
                                  <div style={{marginTop:4}}>
                                    <span style={{color:t.txM,fontWeight:700}}>Skills ({vd.data.extracted_skills.length}):</span>{" "}
                                    {vd.data.extracted_skills.slice(0,18).join(", ")}
                                    {vd.data.extracted_skills.length>18?"…":""}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

export const JobCard = memo(_JobCard);
