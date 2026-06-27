/**
 * JobsTab — the main jobs view. Filter bar (search + toggles + chips),
 * default-resume hint banner, then a scrollable list of JobCard.
 *
 * State lives in App() — this is presentation only. Each JobCard
 * receives its own slice of state via props from App, so per-card
 * memoization survives App re-renders.
 */
import { Chips } from "../components/Chips.jsx";
import { JobCard } from "../components/JobCard.jsx";
import { EMPTY_ARR, EMPTY_OBJ } from "../lib/jobConstants.js";
import CompanyAutocomplete from '../components/CompanyAutocomplete'
import CompanyPriorityPanel from '../components/CompanyPriorityPanel'

const PREFERRED_STATES = ["TX","CA","NY","WA","CO","IL","GA","MA"];
const PREFERRED_CITIES = ["Remote","Dallas","Austin","Plano","Houston","San Francisco","New York","Seattle"];

export function JobsTab({ state }) {
  const {
    t, iS, selS,
    q, sQ,
    remoteOnly, setRemoteOnly, h1bOnly, setH1bOnly,
    platinumOnly, setPlatinumOnly, highCompOnly, setHighCompOnly,
    selPosted, setSelPosted, selSalary, setSelSalary, so, sSo,
    showFilters, setShowFilters, activeN, clearAll,
    opts, selRoles, setSelRoles, selExp, setSelExp,
    selStates, setSelStates, selCities, setSelCities, selATS, setSelATS,
    defaultResumeVersion, defaultHintDismissed, dismissDefaultHint, setTab,
    fj, allJobs, xJ, visibleCount, setVisibleCount, PAGE_SIZE,
    apps, coHistoryByCompany, bestMatchByJob, jobFitByJob,
    vdMapByJob, expandedByJob, pdfStateByJob,
    toggleCardOpen, saveApp, removeApp, markApplied,
    fetchBestMatch, toggleVersionRow, downloadResumePdf,
    roster, priorityCompanies, onCompaniesChange,
    priorityMode, onModeChange, scoreWeights, onWeightsChange,
    onOpenProfile,
  } = state;

  return (
    <div>
      {/* Filter bar */}
      <div className="filter-bar">
        <CompanyAutocomplete
          value={q}
          onChange={sQ}
          roster={roster || []}
          style={{ flex: '1 1 200px', maxWidth: 340 }}
          inputStyle={iS}
          t={t}
          onAddToPriority={(name) => {
            if (priorityCompanies && !priorityCompanies.find(c => c.name === name)) {
              const inRoster = (roster || []).some(r => r.name.toLowerCase() === name.toLowerCase())
              onCompaniesChange([...priorityCompanies, { name, status: inRoster ? 'active' : 'pending' }])
            }
          }}
        />
        <button onClick={()=>setRemoteOnly(r=>!r)}
          style={{padding:"12px 14px",borderRadius:9,border:`1.5px solid ${remoteOnly?t.ac:t.bd}`,background:remoteOnly?t.acL:"transparent",color:remoteOnly?t.ac:t.txM,fontSize:15,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
          🏠 Remote
        </button>
        <button onClick={()=>setH1bOnly(r=>!r)}
          style={{padding:"12px 14px",borderRadius:9,border:`1.5px solid ${h1bOnly?t.vi:t.bd}`,background:h1bOnly?`${t.vi}12`:"transparent",color:h1bOnly?t.vi:t.txM,fontSize:15,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
          🛂 H1B
        </button>
        <button onClick={()=>setPlatinumOnly(r=>!r)}
          style={{padding:"12px 14px",borderRadius:9,border:`1.5px solid ${platinumOnly?"#b8860b":t.bd}`,background:platinumOnly?"#b8860b18":"transparent",color:platinumOnly?"#b8860b":t.txM,fontSize:15,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
          ✦ Platinum
        </button>
        <button onClick={()=>setHighCompOnly(r=>!r)}
          style={{padding:"12px 14px",borderRadius:9,border:`1.5px solid ${highCompOnly?t.ok:t.bd}`,background:highCompOnly?`${t.ok}12`:"transparent",color:highCompOnly?t.ok:t.txM,fontSize:15,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
          💰 $220K+
        </button>
        <select value={selPosted} onChange={e=>setSelPosted(e.target.value)} style={selS}>
          <option value="All">📅 Any Time</option><option value="24h">Last 24h</option>
          <option value="3d">Last 3 days</option><option value="7d">Last 7 days</option>
          <option value="14d">Last 14 days</option><option value="30d">Last 30 days</option>
        </select>
        <select value={selSalary} onChange={e=>setSelSalary(e.target.value)} style={selS}>
          <option value="All">💰 Any Salary</option><option value="$100K+">$100K+</option>
          <option value="$130K+">$130K+</option><option value="$160K+">$160K+</option>
          <option value="$200K+">$200K+</option><option value="$250K+">$250K+</option>
        </select>
        <select value={so} onChange={e=>sSo(e.target.value)} style={selS}>
          <option value="relevance">↓ Relevance</option>
          <option value="salary">↓ Salary</option>
          <option value="date">↓ Newest</option>
        </select>
        <button onClick={()=>setShowFilters(f=>!f)}
          style={{padding:"12px 14px",borderRadius:9,border:`1.5px solid ${activeN?t.ac:t.bd}`,background:activeN?t.acL:"transparent",color:activeN?t.ac:t.txM,fontSize:15,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
          🎛 Filters{activeN?` (${activeN})`:""}
        </button>
        {activeN>0 && (
          <button onClick={clearAll}
            style={{padding:"12px 12px",borderRadius:9,border:`1.5px solid ${t.er}30`,background:"transparent",color:t.er,fontSize:15,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>
            ✕ Clear
          </button>
        )}
        <span style={{fontSize:14,color:t.txM,fontWeight:600,marginLeft:"auto",whiteSpace:"nowrap"}}>
          {q.trim() ? `${fj.length} match${fj.length!==1?"es":""}` : `${fj.length} of ${allJobs.length}`}
        </span>
      </div>

      {/* Expanded filters */}
      {showFilters && (
        <div style={{background:t.cd,borderRadius:14,padding:22,border:`1px solid ${t.bd}`,marginBottom:18,display:"flex",flexDirection:"column",gap:18,boxShadow:t.shS}}>
          <CompanyPriorityPanel
            companies={priorityCompanies || []}
            onCompaniesChange={onCompaniesChange}
            mode={priorityMode || 'score_boost'}
            onModeChange={onModeChange}
            weights={scoreWeights || { skills: 53, role_fit: 25, logistics: 22, company_tier: 8 }}
            onWeightsChange={onWeightsChange}
            roster={roster || []}
            onOpenAddSearch={onOpenProfile}
          />
          <Chips label="Role Category"   options={opts.roles}  selected={selRoles}  onChange={setSelRoles}  t={t}/>
          <Chips label="Experience Level" options={opts.exp}    selected={selExp}    onChange={setSelExp}    t={t}/>
          <Chips label="State"           options={opts.states} selected={selStates} onChange={setSelStates} t={t} pinned={PREFERRED_STATES}/>
          <Chips label="City / Hub"      options={opts.cities} selected={selCities} onChange={setSelCities} t={t} pinned={PREFERRED_CITIES}/>
          <Chips label="ATS Platform"    options={opts.ats}    selected={selATS}    onChange={setSelATS}    t={t}/>
        </div>
      )}

      {/* R2 #2: empty-state hint when no default resume is configured.
          Tells users why the "Resume Match" chip is missing and gives
          them a one-click path to the Vault tab to fix it. Dismissible
          so it doesn't nag forever once the user knows. */}
      {!defaultResumeVersion && !defaultHintDismissed && (
        <div role="note"
          style={{display:"flex",alignItems:"center",gap:12,padding:"12px 16px",marginBottom:14,
            background:`${t.ac}10`,border:`1px solid ${t.ac}30`,borderRadius:10,color:t.tx,fontSize:14}}>
          <span style={{fontSize:18,lineHeight:1}}>💡</span>
          <span style={{flex:1,lineHeight:1.5}}>
            Set a default resume in the{" "}
            <button onClick={() => setTab("vault")}
              style={{background:"none",border:"none",padding:0,color:t.ac,fontWeight:700,
                fontSize:14,fontFamily:"inherit",cursor:"pointer",textDecoration:"underline"}}>
              Vault
            </button>{" "}
            tab to see auto-match scores on every job card.
          </span>
          <button onClick={dismissDefaultHint}
            aria-label="Dismiss default-resume hint"
            title="Dismiss"
            style={{background:"none",border:`1px solid ${t.bd}`,color:t.txM,
              fontSize:14,padding:"3px 10px",borderRadius:6,cursor:"pointer",fontFamily:"inherit"}}>
            ✕
          </button>
        </div>
      )}

      {/* Job cards */}
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        {fj.slice(0, visibleCount).map(j => {
          const coKey = (j.company || "").toLowerCase();
          return (
            <JobCard
              key={j.external_id}
              j={j}
              t={t}
              open={xJ === j.external_id}
              app={apps[j.external_id]}
              coHistory={coHistoryByCompany[coKey] || EMPTY_ARR}
              bm={bestMatchByJob[j.external_id]}
              jobFit={jobFitByJob[j.external_id]}
              vdMap={vdMapByJob[j.external_id] || EMPTY_OBJ}
              expandedRows={expandedByJob[j.external_id] || EMPTY_OBJ}
              pdfState={pdfStateByJob[j.external_id] || EMPTY_OBJ}
              onToggleOpen={toggleCardOpen}
              onSave={saveApp}
              onRemove={removeApp}
              onMarkApplied={markApplied}
              onFetchBestMatch={fetchBestMatch}
              onToggleVersionRow={toggleVersionRow}
              onDownloadResumePdf={downloadResumePdf}
            />
          );
        })}
        {fj.length > 0 && (
          <div style={{textAlign:"center",padding:"18px 0",display:"flex",flexDirection:"column",alignItems:"center",gap:10}}>
            <span style={{color:t.txM,fontSize:14}}>
              {visibleCount >= fj.length
                ? `Showing all ${fj.length} job${fj.length !== 1 ? "s" : ""} ✓`
                : `Showing ${visibleCount} of ${fj.length} jobs`}
            </span>
            {visibleCount < fj.length && (
              <button
                onClick={() => setVisibleCount(v => Math.min(v + PAGE_SIZE, fj.length))}
                style={{padding:"10px 32px",borderRadius:9,border:`1.5px solid ${t.ac}`,background:"none",color:t.ac,fontWeight:700,fontSize:15,cursor:"pointer",fontFamily:"inherit",width:"100%",maxWidth:320}}
              >
                Load More ({Math.min(PAGE_SIZE, fj.length - visibleCount)} more)
              </button>
            )}
          </div>
        )}
        {fj.length===0 && (
          <div style={{textAlign:"center",padding:44,color:t.txM,fontSize:16}}>
            No jobs match.{" "}
            <button onClick={clearAll} style={{background:"none",border:"none",color:t.ac,cursor:"pointer",fontWeight:700,fontSize:16,fontFamily:"inherit",textDecoration:"underline"}}>
              Clear all filters
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
