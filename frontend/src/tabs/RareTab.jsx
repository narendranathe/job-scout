/**
 * RareTab — jobs whose title or JD mentions niche AI/LLM tooling.
 * Surfaced separately so the main relevance score stays interpretable
 * on a small corpus.
 */
import { useState, useEffect } from "react";
import { LogoImg } from "../components/LogoImg.jsx";
import { ATS_META } from "../lib/jobConstants.js";
import { fmtSal, timeAgo } from "../lib/format.js";

export function RareTab({ state }) {
  const { t, data, enriched } = state;
  const rareJobs = enriched
    .filter(j => (j.rare_skill_hits||[]).length > 0)
    .sort((a,b) => (b.rare_skill_hits.length - a.rare_skill_hits.length) || ((b.relevance_score||0) - (a.relevance_score||0)));

  const RARE_PAGE_SIZE = 80;
  const [visibleRareCount, setVisibleRareCount] = useState(RARE_PAGE_SIZE);
  useEffect(() => { setVisibleRareCount(RARE_PAGE_SIZE); }, [enriched]);

  return (
    <div>
      <div style={{marginBottom:18,padding:"14px 18px",borderRadius:12,background:`${t.vi}10`,border:`1px solid ${t.vi}30`}}>
        <div style={{fontSize:14,color:t.txS,lineHeight:1.6}}>
          Jobs whose title or JD mentions niche AI/LLM tooling — surfaced as a separate lane to keep the main relevance score interpretable on a small corpus.
        </div>
        <div style={{fontSize:12,color:t.txM,marginTop:8}}>
          Watchlist: {(data?.jobs?.length ? Array.from(new Set(rareJobs.flatMap(j=>j.rare_skill_hits))) : []).join(" · ") || "—"}
        </div>
      </div>
      {rareJobs.length === 0 ? (
        <div style={{textAlign:"center",padding:44,color:t.txM,fontSize:16}}>
          No rare-skill jobs in the current corpus.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {rareJobs.slice(0, visibleRareCount).map(j => {
            const sc = j.relevance_score || 0;
            const ats = ATS_META[j.ats] || ATS_META.unknown;
            return (
              <div key={j.external_id} style={{background:t.cd,borderRadius:12,border:`1px solid ${t.bd}`,padding:"16px 18px",boxShadow:t.shS}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:14}}>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6,flexWrap:"wrap"}}>
                      <LogoImg name={j.company} size={28} t={t}/>
                      <span style={{fontSize:16,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>{j.title}</span>
                      <span style={{fontSize:13,color:t.txM}}>· {j.company}</span>
                      <span style={{fontSize:11,color:ats.c,fontWeight:700}}>{ats.i} {ats.l}</span>
                      {j.sponsorship && <span title="JD mentions visa sponsorship" style={{color:t.vi,fontWeight:700,fontSize:13}}>🛂</span>}
                    </div>
                    <div style={{display:"flex",gap:6,flexWrap:"wrap",marginTop:8}}>
                      {j.rare_skill_hits.map(s => (
                        <span key={s} style={{padding:"4px 10px",borderRadius:8,background:`${t.vi}15`,color:t.vi,fontSize:12,fontWeight:700,border:`1px solid ${t.vi}40`}}>
                          🎯 {s}
                        </span>
                      ))}
                    </div>
                    <div style={{display:"flex",gap:14,flexWrap:"wrap",fontSize:12,color:t.txM,marginTop:10}}>
                      {j._loc.isRemote ? <span style={{color:t.ok,fontWeight:600}}>🏠 Remote</span> : <span>{j._loc.display||"—"}</span>}
                      {j.salary_max>0 && <span style={{color:t.wm,fontWeight:600}}>{fmtSal(j.salary_min)}–{fmtSal(j.salary_max)}</span>}
                      {j.posted_at && <span>{timeAgo(j.posted_at)}</span>}
                    </div>
                  </div>
                  <div style={{display:"flex",alignItems:"center",gap:10,flexShrink:0}}>
                    <div style={{width:44,height:44,borderRadius:10,display:"flex",alignItems:"center",justifyContent:"center",background:t.sBg(sc)}}>
                      <span style={{fontSize:16,fontWeight:800,color:t.sTx(sc),fontFamily:"'Playfair Display',serif"}}>{(sc*100).toFixed(0)}%</span>
                    </div>
                    <a href={j.url} target="_blank" rel="noopener noreferrer"
                      style={{padding:"9px 16px",borderRadius:8,background:t.gP,color:"#fff",fontSize:13,fontWeight:700,textDecoration:"none",whiteSpace:"nowrap"}}>
                      Apply →
                    </a>
                  </div>
                </div>
              </div>
            );
          })}
          {rareJobs.length > 0 && (
            <div style={{textAlign:"center",padding:"18px 0",display:"flex",flexDirection:"column",alignItems:"center",gap:10}}>
              <span style={{color:t.txM,fontSize:14}}>
                {visibleRareCount >= rareJobs.length
                  ? `Showing all ${rareJobs.length} rare-skill job${rareJobs.length !== 1 ? "s" : ""} ✓`
                  : `Showing ${visibleRareCount} of ${rareJobs.length} rare-skill jobs`}
              </span>
              {visibleRareCount < rareJobs.length && (
                <button
                  onClick={() => setVisibleRareCount(v => Math.min(v + RARE_PAGE_SIZE, rareJobs.length))}
                  style={{padding:"10px 32px",borderRadius:9,border:`1.5px solid ${t.vi}`,background:"none",color:t.vi,fontWeight:700,fontSize:15,cursor:"pointer",fontFamily:"inherit",width:"100%",maxWidth:320}}
                >
                  Load More ({Math.min(RARE_PAGE_SIZE, rareJobs.length - visibleRareCount)} more)
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
