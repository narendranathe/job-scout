/**
 * MonitorTab — system health + manual triggers + pipeline status + recent runs.
 *
 * Extracted from App.jsx as part of the split. Takes the entire tab state
 * as a single `state` prop object so the call site stays one line; each
 * field is destructured at the top of the component for clarity. State
 * lives in App() (where the data hooks run); this component is purely
 * presentational over that state plus a handful of action callbacks.
 */
import { ScrapeProgressBar } from "../components/ScrapeProgressBar.jsx";
import { MRow, Chk } from "../components/MRow.jsx";
import { timeAgo } from "../lib/format.js";
import { RENDER_API } from "../lib/api.js";

export function MonitorTab({ state }) {
  const {
    t,
    source, lastUpdated, health, data, allJobs,
    barVisible, scrapeProgress, scrapeMsg, triggerScrape,
    doctorLoading, doctorErr, doctorResult, runDoctor,
    purgeDays, setPurgeDays, purgeLoading, purgeMsg, purgeIsErr, runPurgeStale,
    reextractLoading, reextractMsg, runReextract,
    vacuumLoading, vacuumMsg, vacuumIsErr, runClearCache,
    reindexLoading, reindexMsg, runReindex,
    // PRD #89 Slice 4 — admin button to re-show the onboarding wizard.
    resetOnboardingLoading, resetOnboardingMsg, runResetOnboarding,
  } = state;

  return (
    <div className="two-col">
      {/* System Health */}
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 20px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>System Health</h3>
        <MRow l="Data Source"    v={source==="render"?"🟢 Render (Live)":source==="static"?"🟡 Static":"Static Only"} c={source==="render"?t.ok:t.wm} t={t}/>
        <MRow l="Last Refresh"   v={lastUpdated?timeAgo(lastUpdated):"—"} c={t.ac} t={t}/>
        {health && <>
          <MRow l="Server Status"  v={health.status==="idle"?"✅ Idle":"⏳ Scraping..."} c={health.status==="scraping"?t.wm:t.ok} t={t}/>
          <MRow l="Uptime"         v={`${health.uptime_hours||0}h`}            c={t.ac} t={t}/>
          <MRow l="Total Cycles"   v={health.total_cycles||0}                  c={t.ac} t={t}/>
          <MRow l="New Jobs Found" v={health.total_new_jobs||0}                c={t.ok} t={t}/>
          <MRow l="Scrape Duration" v={`${health.last_duration_sec||0}s`}     c={t.ac} t={t}/>
          <MRow l="Scan Interval"  v={`${(health.fast_interval_sec||300)/60}min`} c={t.ac} t={t}/>
          <MRow l="Companies"      v={health.companies_tracked||0}             c={t.ac} t={t}/>
          {health.last_error && <MRow l="Last Error" v={health.last_error} c={t.er} t={t}/>}
        </>}
        {!health && RENDER_API && (
          <div style={{fontSize:14,color:t.txM,padding:"12px 0"}}>
            Render not responding — may be cold-starting (~30s). Check back shortly.
          </div>
        )}
      </div>

      {/* Manual Triggers */}
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 20px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Manual Triggers</h3>
        <div style={{display:"flex",flexDirection:"column",gap:14}}>

          {/* Render scrape button */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>🚀 Trigger Render Scrape</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Kick off an immediate full scrape on the Render server. Takes ~2–3 minutes.
              {!RENDER_API && <span style={{color:t.er}}> (Set VITE_RENDER_URL to enable)</span>}
            </div>
            {barVisible ? (
              <ScrapeProgressBar snap={scrapeProgress} t={t} />
            ) : (
              <button onClick={triggerScrape} disabled={!RENDER_API}
                style={{padding:"11px 22px",borderRadius:9,border:"none",
                  background:RENDER_API?t.gP:`${t.txM}20`,
                  color:RENDER_API?"#fff":t.txM,
                  fontSize:14,fontWeight:700,cursor:RENDER_API?"pointer":"not-allowed",
                  fontFamily:"inherit",transition:"all .15s"}}>
                ▶ Run Scrape Now
              </button>
            )}
            {scrapeMsg && (
              <div style={{marginTop:10,fontSize:14,color:scrapeMsg.startsWith("✅")?t.ok:scrapeMsg.startsWith("⏳")||scrapeMsg.startsWith("🚀")?t.wm:t.er,fontWeight:600}}>
                {scrapeMsg}
              </div>
            )}
          </div>

          {/* Doctor health-check */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>🩺 Doctor</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Run server health probes: DB connectivity, scraper imports, recent scrape success, env vars, vault dirs, disk space.
              {!RENDER_API && <span style={{color:t.er}}> (Set VITE_RENDER_URL to enable)</span>}
            </div>
            <button onClick={runDoctor} disabled={doctorLoading||!RENDER_API}
              style={{padding:"11px 22px",borderRadius:9,border:"none",
                background:doctorLoading?t.bgS:(RENDER_API?t.gP:`${t.txM}20`),
                color:doctorLoading||!RENDER_API?t.txM:"#fff",
                fontSize:14,fontWeight:700,cursor:doctorLoading||!RENDER_API?"not-allowed":"pointer",
                fontFamily:"inherit",transition:"all .15s"}}>
              {doctorLoading?"⏳ Running checks…":"▶ Run Doctor"}
            </button>
            {doctorErr && (
              <div style={{marginTop:10,fontSize:14,color:t.er,fontWeight:600}}>❌ {doctorErr}</div>
            )}
            {doctorResult && (() => {
              const overall = doctorResult.overall;
              const overallColor = overall==="pass"?"#4ADE80":overall==="warn"?"#F59E0B":"#EF4444";
              return (
                <div style={{marginTop:14}}>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:12,padding:"10px 14px",
                    background:`${overallColor}15`,border:`1px solid ${overallColor}40`,borderRadius:8}}>
                    <span style={{fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".06em"}}>Overall</span>
                    <span style={{fontSize:15,fontWeight:800,color:overallColor,textTransform:"uppercase",letterSpacing:".05em"}}>{overall}</span>
                  </div>
                  <div style={{display:"flex",flexDirection:"column",gap:8}}>
                    {(doctorResult.checks||[]).map((c,i) => {
                      const color = c.status==="pass"?"#4ADE80":c.status==="warn"?"#F59E0B":"#EF4444";
                      return (
                        <div key={i} style={{padding:"10px 12px",borderRadius:8,
                          background:t.cd,border:`1px solid ${t.bd}`}}>
                          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
                            <span style={{fontSize:11,fontWeight:800,color:"#fff",
                              background:color,padding:"2px 8px",borderRadius:4,
                              textTransform:"uppercase",letterSpacing:".05em"}}>{c.status}</span>
                            <span style={{fontSize:14,fontWeight:700,color:t.tx,fontFamily:"monospace"}}>{c.name}</span>
                          </div>
                          <div style={{fontSize:13,color:t.txM,marginLeft:2}}>{c.detail}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
          </div>

          {/* Purge Stale Jobs (#23) */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>🗑️ Purge Stale Jobs</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Permanently delete inactive jobs (is_active=0) older than the threshold below. Refuses to run during an active scrape.
              {!RENDER_API && <span style={{color:t.er}}> (Set VITE_RENDER_URL to enable)</span>}
            </div>
            <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:12,flexWrap:"wrap"}}>
              <label htmlFor="purge-days" style={{fontSize:13,color:t.txS,fontWeight:600}}>Days inactive:</label>
              <input id="purge-days" type="number" min="1" step="1" value={purgeDays}
                onChange={e=>setPurgeDays(e.target.value)}
                disabled={purgeLoading||!RENDER_API}
                style={{width:80,padding:"7px 10px",borderRadius:7,border:`1px solid ${t.bd}`,
                  background:t.cd,color:t.tx,fontSize:14,fontFamily:"inherit"}}/>
              <span style={{fontSize:12,color:t.txM}}>
                = {Number(purgeDays)>0 ? Number(purgeDays)*24 : 0}h threshold
              </span>
            </div>
            <button onClick={runPurgeStale} disabled={purgeLoading||!RENDER_API}
              style={{padding:"11px 22px",borderRadius:9,border:"none",
                background:purgeLoading?t.bgS:(RENDER_API?"#DC2626":`${t.txM}20`),
                color:purgeLoading||!RENDER_API?t.txM:"#fff",
                fontSize:14,fontWeight:700,cursor:purgeLoading||!RENDER_API?"not-allowed":"pointer",
                fontFamily:"inherit",transition:"all .15s"}}>
              {purgeLoading?"⏳ Purging…":"🗑 Purge Now"}
            </button>
            {purgeMsg && (
              <div style={{marginTop:10,padding:"8px 12px",borderRadius:8,
                background:purgeIsErr?`${t.er}15`:`${t.ok}15`,
                border:`1px solid ${purgeIsErr?t.er:t.ok}40`,
                fontSize:14,color:purgeIsErr?t.er:t.ok,fontWeight:600}}>
                {purgeIsErr?"❌ ":"✅ "}{purgeMsg}
              </div>
            )}
          </div>


          {/* Re-extract skills (#24) */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>🧠 Re-extract Skills</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Re-run skill extraction over every resume version after updating regex patterns.
              Non-destructive — only the extracted_skills column is rewritten.
              {!RENDER_API && <span style={{color:t.er}}> (Set VITE_RENDER_URL to enable)</span>}
            </div>
            <button onClick={runReextract} disabled={reextractLoading||!RENDER_API}
              style={{padding:"11px 22px",borderRadius:9,border:"none",
                background:reextractLoading?t.bgS:(RENDER_API?t.gP:`${t.txM}20`),
                color:reextractLoading||!RENDER_API?t.txM:"#fff",
                fontSize:14,fontWeight:700,cursor:reextractLoading||!RENDER_API?"not-allowed":"pointer",
                fontFamily:"inherit",transition:"all .15s"}}>
              {reextractLoading?"⏳ Re-extracting…":"▶ Re-extract Skills"}
            </button>
            {reextractMsg && (
              <div style={{marginTop:10,fontSize:14,fontWeight:600,
                color:reextractMsg.type==="ok"?t.ok:t.er}}>
                {reextractMsg.text}
              </div>
            )}
          </div>

          {/* Clear DB Cache / VACUUM (#23) */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>♻️ Clear DB Cache</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Run <code style={{fontFamily:"monospace",fontSize:12,background:t.cd,padding:"1px 5px",borderRadius:4}}>VACUUM</code> on the SQLite database to reclaim freelist space. Holds an exclusive lock — refuses during active scrapes.
              {!RENDER_API && <span style={{color:t.er}}> (Set VITE_RENDER_URL to enable)</span>}
            </div>
            <button onClick={runClearCache} disabled={vacuumLoading||!RENDER_API}
              style={{padding:"11px 22px",borderRadius:9,border:"none",
                background:vacuumLoading?t.bgS:(RENDER_API?"#DC2626":`${t.txM}20`),
                color:vacuumLoading||!RENDER_API?t.txM:"#fff",
                fontSize:14,fontWeight:700,cursor:vacuumLoading||!RENDER_API?"not-allowed":"pointer",
                fontFamily:"inherit",transition:"all .15s"}}>
              {vacuumLoading?"⏳ Vacuuming…":"♻ Run VACUUM"}
            </button>
            {vacuumMsg && (
              <div style={{marginTop:10,padding:"8px 12px",borderRadius:8,
                background:vacuumIsErr?`${t.er}15`:`${t.ok}15`,
                border:`1px solid ${vacuumIsErr?t.er:t.ok}40`,
                fontSize:14,color:vacuumIsErr?t.er:t.ok,fontWeight:600}}>
                {vacuumIsErr?"❌ ":"✅ "}{vacuumMsg}
              </div>
            )}
          </div>

          {/* Vault re-index (#24) */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>📚 Vault Re-index</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Rebuild the TF-IDF index from every .txt file in resume_vault/text/.
              Use after bulk-importing new PDFs.
              {!RENDER_API && <span style={{color:t.er}}> (Set VITE_RENDER_URL to enable)</span>}
            </div>
            <button onClick={runReindex} disabled={reindexLoading||!RENDER_API}
              style={{padding:"11px 22px",borderRadius:9,border:"none",
                background:reindexLoading?t.bgS:(RENDER_API?t.gP:`${t.txM}20`),
                color:reindexLoading||!RENDER_API?t.txM:"#fff",
                fontSize:14,fontWeight:700,cursor:reindexLoading||!RENDER_API?"not-allowed":"pointer",
                fontFamily:"inherit",transition:"all .15s"}}>
              {reindexLoading?"⏳ Rebuilding index…":"▶ Rebuild Index"}
            </button>
            {reindexMsg && (
              <div style={{marginTop:10,fontSize:14,fontWeight:600,
                color:reindexMsg.type==="ok"?t.ok:t.er}}>
                {reindexMsg.text}
              </div>
            )}
          </div>

          {/* Reset onboarding (PRD #89 Slice 4) */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>🔄 Reset Onboarding</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Clear the onboarded_at flag and re-show the wizard on next page load.
              Does not delete your roles, companies, or vault.
              {!RENDER_API && <span style={{color:t.er}}> (Set VITE_RENDER_URL to enable)</span>}
            </div>
            <button onClick={runResetOnboarding} disabled={resetOnboardingLoading||!RENDER_API}
              style={{padding:"11px 22px",borderRadius:9,border:"none",
                background:resetOnboardingLoading?t.bgS:(RENDER_API?t.gP:`${t.txM}20`),
                color:resetOnboardingLoading||!RENDER_API?t.txM:"#fff",
                fontSize:14,fontWeight:700,cursor:resetOnboardingLoading||!RENDER_API?"not-allowed":"pointer",
                fontFamily:"inherit",transition:"all .15s"}}>
              {resetOnboardingLoading?"⏳ Resetting…":"▶ Reset onboarding"}
            </button>
            {resetOnboardingMsg && (
              <div style={{marginTop:10,fontSize:14,fontWeight:600,
                color:resetOnboardingMsg.type==="ok"?t.ok:t.er}}>
                {resetOnboardingMsg.text}
              </div>
            )}
          </div>

          {/* GitHub Actions button */}
          <div style={{padding:18,borderRadius:12,background:t.bgS,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:15,fontWeight:700,color:t.tx,marginBottom:6}}>⚡ Trigger GitHub Actions</div>
            <div style={{fontSize:13,color:t.txM,marginBottom:14}}>
              Run a full scrape via GitHub Actions (all 120+ companies). Deploy to GitHub Pages after.
            </div>
            <a href="https://github.com/narendranathe/job-scout/actions/workflows/scrape-and-deploy.yml"
              target="_blank" rel="noopener noreferrer"
              style={{display:"inline-block",padding:"11px 22px",borderRadius:9,
                background:"#24292f",color:"#fff",fontSize:14,fontWeight:700,
                textDecoration:"none",transition:"opacity .15s"}}>
              Open GitHub Actions →
            </a>
          </div>

          {/* Auto-refresh */}
          <div style={{padding:14,borderRadius:10,background:`${t.ok}08`,border:`1px solid ${t.ok}20`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <span style={{fontSize:14,color:t.txS}}>Dashboard auto-refresh</span>
            <span style={{fontSize:14,fontWeight:700,color:t.ok}}>Every 2 min</span>
          </div>
        </div>
      </div>

      {/* Pipeline status */}
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 20px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Pipeline Status</h3>
        <div style={{display:"flex",flexDirection:"column",gap:14}}>
          <Chk done={!!RENDER_API}         label="Render URL configured"    detail={RENDER_API||"Set VITE_RENDER_URL in .env"} t={t}/>
          <Chk done={source==="render"}    label="Render API responding"    detail={source==="render"?"Live data flowing":"Using static fallback"} t={t}/>
          <Chk done={!!health}             label="Health endpoint reachable" detail={health?`${health.total_cycles} cycles completed`:"Waiting..."} t={t}/>
          <Chk done={health?.total_cycles>0} label="First scrape completed" detail={health?.last_scrape_at?`Last: ${timeAgo(health.last_scrape_at)}`:"Pending"} t={t}/>
          <Chk done={allJobs.length>0}     label="Jobs flowing to dashboard" detail={`${allJobs.length} jobs loaded`} t={t}/>
        </div>
        <div style={{marginTop:20,padding:14,background:t.bgS,borderRadius:10,border:`1px solid ${t.bd}`}}>
          <div style={{fontSize:12,fontWeight:700,color:t.txM,marginBottom:8,textTransform:"uppercase",letterSpacing:".06em"}}>Data Flow</div>
          <div style={{fontSize:13,color:t.txS,lineHeight:2.2}}>
            <span style={{color:t.ok}}>●</span> Render: Tier 1 (24 cos) → every 5 min (active hours)<br/>
            <span style={{color:t.wm}}>●</span> Actions: 120+ companies → 9×/day (skip 12am–5:30am CST)<br/>
            <span style={{color:t.bl}}>●</span> Dashboard auto-refresh → every 2 min
          </div>
        </div>
      </div>

      {/* Scrape history */}
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 20px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Recent Scrape Runs</h3>
        {(data?.runs||[]).length===0
          ? <div style={{padding:22,textAlign:"center",color:t.txM,fontSize:15}}>No history yet</div>
          : <div style={{display:"flex",flexDirection:"column",gap:6}}>
            {(data?.runs||[]).slice(0,10).map((r,i)=>(
              <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"9px 0",borderBottom:`1px solid ${t.bd}`,fontSize:14}}>
                <div style={{display:"flex",gap:12,alignItems:"center"}}>
                  <span style={{color:r.status==="complete"?t.ok:t.er,fontWeight:600}}>{r.status==="complete"?"✅":"❌"}</span>
                  <span style={{color:t.txS}}>{r.started_at?timeAgo(r.started_at):"—"}</span>
                </div>
                <div style={{display:"flex",gap:14,color:t.txM}}>
                  {r.companies_scraped&&<span>{r.companies_scraped} cos</span>}
                  {r.new_jobs!=null&&<span style={{color:t.ok,fontWeight:600}}>+{r.new_jobs}</span>}
                  {(r.errors||0)>0&&<span style={{color:t.er}}>{r.errors} err</span>}
                </div>
              </div>
            ))}
          </div>
        }
      </div>
    </div>
  );
}
