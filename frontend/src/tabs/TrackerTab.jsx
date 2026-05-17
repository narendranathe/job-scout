/**
 * TrackerTab — application tracker + resume version manager + compare.
 *
 * Largest tab so far in LOC. The state surface is wide because it owns
 * three distinct sub-UIs: the resume-version manager (with PDF upload +
 * compare), the status filter bar, and the per-application card list.
 * All state lives in App() — this is pure presentation.
 */
import { LogoImg } from "../components/LogoImg.jsx";
import { ST_COLOR, ST_LABEL } from "../lib/jobConstants.js";
import { fmtSal, timeAgo } from "../lib/format.js";
import { RENDER_API } from "../lib/api.js";

const RESUME_VERSIONS = ["_DE","_data","_SWE","_SE","_AE","_AI","_ML","standard","custom"];

export function TrackerTab({ state }) {
  const {
    t, apps, enriched,
    trackerFilter, setTrackerFilter,
    resumeVersions, showResumeManager, setShowResumeManager, fetchResumeVersions, deleteResumeVersion,
    compareA, setCompareA, compareB, setCompareB, compareVersions, compareResult, setCompareResult,
    addingVersion, setAddingVersion, rvForm, setRvForm, rvFile, setRvFile, rvResult, setRvResult, rvUploading, submitResumeVersion,
    editingNotes, setEditingNotes, editingResume, setEditingResume,
    removeApp, saveApp, updateField,
  } = state;

  const allApps = Object.values(apps).sort((a,b)=>new Date(b.updated_at)-new Date(a.updated_at));
  const filtered = trackerFilter==="All" ? allApps : allApps.filter(a=>a.status===trackerFilter);
  const counts = {All:allApps.length};
  Object.keys(ST_LABEL).forEach(s=>{ counts[s]=allApps.filter(a=>a.status===s).length; });
  const exportApps = () => {
    const blob = new Blob([JSON.stringify(allApps,null,2)],{type:"application/json"});
    const a = document.createElement("a"); a.href=URL.createObjectURL(blob);
    a.download=`jobscout-tracker-${new Date().toISOString().slice(0,10)}.json`; a.click();
  };

  return (
    <div>
      {/* ── Resume Version Manager ── */}
      <div style={{marginBottom:18,background:t.cd,borderRadius:12,border:`1px solid ${t.bd}`,overflow:"hidden",boxShadow:t.shS}}>
        <button onClick={()=>{setShowResumeManager(m=>!m);if(!showResumeManager)fetchResumeVersions();}}
          style={{width:"100%",padding:"14px 20px",display:"flex",justifyContent:"space-between",alignItems:"center",background:"transparent",border:"none",cursor:"pointer",fontFamily:"inherit",color:t.tx}}>
          <span style={{fontSize:15,fontWeight:700}}>📄 Resume Version Manager</span>
          <span style={{fontSize:14,color:t.txM,transform:showResumeManager?"rotate(180deg)":"",transition:"transform .2s"}}>▾</span>
        </button>
        {showResumeManager && (
          <div style={{padding:"0 20px 18px",borderTop:`1px solid ${t.bd}`}}>
            {/* Saved versions list */}
            {resumeVersions.length > 0 && (
              <div style={{marginTop:14,display:"flex",flexDirection:"column",gap:8}}>
                {resumeVersions.map(rv => (
                  <div key={rv.version_key} style={{display:"flex",alignItems:"center",gap:12,padding:"10px 14px",borderRadius:9,background:t.bgS,border:`1px solid ${t.bd}`,flexWrap:"wrap"}}>
                    <div style={{flex:1,minWidth:140}}>
                      <span style={{fontWeight:700,color:t.ac,fontSize:14}}>{rv.version_key}</span>
                      <span style={{color:t.txM,fontSize:13,marginLeft:8}}>{rv.display_name}</span>
                    </div>
                    <span style={{fontSize:12,color:t.txM}}>{rv.extracted_skills?.length||0} skills</span>
                    {rv.target_companies?.length > 0 && (
                      <span style={{fontSize:12,color:t.txS}}>{rv.target_companies.slice(0,3).join(", ")}</span>
                    )}
                    <button onClick={()=>deleteResumeVersion(rv.version_key)}
                      style={{padding:"4px 10px",borderRadius:6,border:`1px solid ${t.er}30`,background:"transparent",color:t.er,fontSize:12,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
            {resumeVersions.length === 0 && !addingVersion && (
              <p style={{fontSize:14,color:t.txM,marginTop:14}}>No resume versions saved yet. Upload a PDF or paste text below.</p>
            )}

            {/* Compare section — only when 2+ versions exist */}
            {resumeVersions.length >= 2 && (
              <div style={{marginTop:14,padding:"14px",borderRadius:10,background:`${t.bl}08`,border:`1px solid ${t.bl}20`}}>
                <div style={{fontSize:12,fontWeight:700,color:t.bl,textTransform:"uppercase",letterSpacing:".06em",marginBottom:10}}>⚖ Compare Versions</div>
                <div style={{display:"flex",gap:8,flexWrap:"wrap",alignItems:"center"}}>
                  <select value={compareA} onChange={e=>{setCompareA(e.target.value);setCompareResult(null);}}
                    style={{padding:"7px 10px",borderRadius:7,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:13,fontFamily:"inherit",outline:"none",flex:"1 1 120px"}}>
                    <option value="">— Version A —</option>
                    {resumeVersions.map(v=><option key={v.version_key} value={v.version_key}>{v.version_key} · {v.display_name}</option>)}
                  </select>
                  <span style={{color:t.txM,fontWeight:600}}>vs</span>
                  <select value={compareB} onChange={e=>{setCompareB(e.target.value);setCompareResult(null);}}
                    style={{padding:"7px 10px",borderRadius:7,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:13,fontFamily:"inherit",outline:"none",flex:"1 1 120px"}}>
                    <option value="">— Version B —</option>
                    {resumeVersions.map(v=><option key={v.version_key} value={v.version_key}>{v.version_key} · {v.display_name}</option>)}
                  </select>
                  <button onClick={compareVersions} disabled={!compareA||!compareB||compareA===compareB||!RENDER_API}
                    style={{padding:"7px 16px",borderRadius:7,border:"none",background:compareA&&compareB&&compareA!==compareB?t.gP:`${t.txM}20`,color:compareA&&compareB&&compareA!==compareB?"#fff":t.txM,fontSize:13,fontWeight:700,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
                    Compare →
                  </button>
                </div>
                {compareResult && (
                  <div style={{marginTop:12}}>
                    {/* Similarity score */}
                    <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:12}}>
                      <div style={{fontSize:32,fontWeight:800,color:compareResult.similarity_pct>=70?t.ok:compareResult.similarity_pct>=40?t.wm:t.er,fontFamily:"'Playfair Display',serif"}}>
                        {compareResult.similarity_pct}%
                      </div>
                      <div style={{fontSize:13,color:t.txM}}>
                        overlap · {compareResult.shared.length} shared skills<br/>
                        <span style={{color:t.bl}}>{compareResult.a.display_name}: {compareResult.a.skill_count} skills</span>
                        {" · "}
                        <span style={{color:t.vi}}>{compareResult.b.display_name}: {compareResult.b.skill_count} skills</span>
                      </div>
                    </div>
                    {/* Diff columns */}
                    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
                      {[
                        {label:`Only in ${compareResult.a.version_key}`,skills:compareResult.only_a,c:t.bl},
                        {label:"Shared",skills:compareResult.shared,c:t.ok},
                        {label:`Only in ${compareResult.b.version_key}`,skills:compareResult.only_b,c:t.vi},
                      ].map(col=>(
                        <div key={col.label}>
                          <div style={{fontSize:11,fontWeight:700,color:col.c,textTransform:"uppercase",letterSpacing:".05em",marginBottom:6}}>{col.label} ({col.skills.length})</div>
                          <div style={{display:"flex",flexDirection:"column",gap:3}}>
                            {col.skills.map(s=>(
                              <span key={s} style={{fontSize:12,padding:"2px 7px",borderRadius:5,background:`${col.c}14`,color:col.c}}>{s}</span>
                            ))}
                            {col.skills.length===0 && <span style={{fontSize:12,color:t.txM,fontStyle:"italic"}}>none</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Add version form */}
            {addingVersion ? (
              <div style={{marginTop:14,display:"flex",flexDirection:"column",gap:10,padding:"14px",borderRadius:10,background:`${t.ac}06`,border:`1px solid ${t.ac}20`}}>
                {/* PDF upload */}
                <div style={{padding:"10px 12px",borderRadius:7,border:`1.5px dashed ${t.ac}50`,background:t.bgS}}>
                  <div style={{fontSize:12,fontWeight:700,color:t.txM,marginBottom:6}}>📎 UPLOAD PDF (recommended)</div>
                  <input type="file" accept=".pdf" onChange={e=>{setRvFile(e.target.files[0]||null);setRvResult(null);}}
                    style={{fontSize:13,color:t.txS,fontFamily:"inherit"}}/>
                  {rvFile && <div style={{fontSize:12,color:t.ok,marginTop:4,fontWeight:600}}>✓ {rvFile.name}</div>}
                  <div style={{fontSize:11,color:t.txM,marginTop:4}}>or paste text below instead</div>
                </div>
                <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
                  <input placeholder="Version key (e.g. _DE, _GS)" value={rvForm.version_key}
                    onChange={e=>setRvForm(f=>({...f,version_key:e.target.value}))}
                    style={{flex:"1 1 140px",padding:"8px 12px",borderRadius:7,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:14,fontFamily:"inherit",outline:"none"}}/>
                  <input placeholder="Display name (e.g. Goldman Sachs)" value={rvForm.display_name}
                    onChange={e=>setRvForm(f=>({...f,display_name:e.target.value}))}
                    style={{flex:"2 1 200px",padding:"8px 12px",borderRadius:7,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:14,fontFamily:"inherit",outline:"none"}}/>
                </div>
                {!rvFile && (
                  <textarea placeholder="Paste resume text here (used if no PDF selected)..." value={rvForm.resume_text}
                    onChange={e=>setRvForm(f=>({...f,resume_text:e.target.value}))}
                    rows={5} style={{padding:"8px 12px",borderRadius:7,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:13,fontFamily:"inherit",outline:"none",resize:"vertical"}}/>
                )}
                <input placeholder="Notes (optional — e.g. 'sent to quant firms')..." value={rvForm.notes}
                  onChange={e=>setRvForm(f=>({...f,notes:e.target.value}))}
                  style={{padding:"8px 12px",borderRadius:7,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:14,fontFamily:"inherit",outline:"none"}}/>
                <div style={{display:"flex",gap:8}}>
                  <button onClick={submitResumeVersion} disabled={!RENDER_API||!rvForm.version_key.trim()||rvUploading}
                    style={{padding:"9px 20px",borderRadius:8,border:"none",background:RENDER_API&&!rvUploading?t.gP:`${t.txM}20`,color:RENDER_API&&!rvUploading?"#fff":t.txM,fontSize:14,fontWeight:700,cursor:RENDER_API&&!rvUploading?"pointer":"not-allowed",fontFamily:"inherit"}}>
                    {rvUploading?"⏳ Processing...":"Save Version"}
                  </button>
                  <button onClick={()=>{setAddingVersion(false);setRvResult(null);setRvFile(null);}}
                    style={{padding:"9px 16px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txM,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>
                    Cancel
                  </button>
                </div>
                {rvResult && (
                  <div style={{fontSize:13,fontWeight:600,color:rvResult.ok?t.ok:t.er,marginTop:4}}>{rvResult.msg}</div>
                )}
                {!RENDER_API && <div style={{fontSize:13,color:t.er}}>⚠️ Set VITE_RENDER_URL to enable saving versions.</div>}
              </div>
            ) : (
              <button onClick={()=>{setAddingVersion(true);setRvResult(null);}}
                style={{marginTop:12,padding:"9px 18px",borderRadius:8,border:`1.5px dashed ${t.ac}60`,background:"transparent",color:t.ac,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>
                ＋ Add Version
              </button>
            )}
          </div>
        )}
      </div>

      {/* Summary cards */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(120px,1fr))",gap:12,marginBottom:20}}>
        {[["All","📋",t.ac],["saved","🔖",ST_COLOR.saved],["applied","✅",ST_COLOR.applied],
          ["interview","📞",ST_COLOR.interview],["offer","🎉",ST_COLOR.offer],["rejected","✗",ST_COLOR.rejected]
        ].map(([st,ico,c])=>(
          <button key={st} onClick={()=>setTrackerFilter(st)}
            style={{padding:"14px 10px",borderRadius:12,border:`2px solid ${trackerFilter===st?c:t.bd}`,
              background:trackerFilter===st?`${c}12`:t.cd,cursor:"pointer",fontFamily:"inherit",
              display:"flex",flexDirection:"column",alignItems:"center",gap:4,transition:"all .15s"}}>
            <span style={{fontSize:22}}>{ico}</span>
            <span style={{fontSize:26,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{counts[st]||0}</span>
            <span style={{fontSize:11,color:t.txM,fontWeight:700,textTransform:"capitalize"}}>{st}</span>
          </button>
        ))}
      </div>

      {/* Export + header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}>
        <span style={{fontSize:14,color:t.txM,fontWeight:600}}>{filtered.length} job{filtered.length!==1?"s":""} tracked</span>
        {allApps.length>0 && (
          <button onClick={exportApps}
            style={{padding:"8px 16px",borderRadius:8,border:`1px solid ${t.bd}`,background:t.cd,
              color:t.txS,fontSize:13,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>
            ⬇ Export JSON
          </button>
        )}
      </div>

      {/* Application list */}
      {filtered.length===0 ? (
        <div style={{textAlign:"center",padding:56,color:t.txM,fontSize:16}}>
          {allApps.length===0
            ? <span>No saved jobs yet. Open any job card and click <strong>🔖 Save</strong> or <strong>✅ Applied</strong>.</span>
            : `No "${trackerFilter}" jobs. Try a different filter.`
          }
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {filtered.map(app => {
            const c = ST_COLOR[app.status] || t.ac;
            const editing = editingNotes===app.external_id;
            // Try to find full job details from loaded data
            const fullJob = enriched.find(j=>j.external_id===app.external_id);
            return (
              <div key={app.external_id} style={{background:t.cd,borderRadius:12,border:`1px solid ${t.bd}`,overflow:"hidden",boxShadow:t.shS}}>
                <div style={{padding:"16px 20px",display:"flex",alignItems:"center",gap:14,flexWrap:"wrap"}}>
                  <LogoImg name={app.company} size={36} t={t}/>
                  <div style={{flex:1,minWidth:200}}>
                    <div style={{fontSize:16,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif",marginBottom:4}}>{app.title}</div>
                    <div style={{fontSize:14,color:t.txS,display:"flex",gap:10,flexWrap:"wrap"}}>
                      <span style={{fontWeight:700}}>{app.company}</span>
                      {app.location && <span>{app.location}</span>}
                      {app.salary_max>0 && <span style={{color:t.wm,fontWeight:700}}>{fmtSal(app.salary_min)}–{fmtSal(app.salary_max)}</span>}
                      <span style={{color:t.txM}}>Saved {timeAgo(app.saved_at)}</span>
                      {app.applied_at && <span style={{color:ST_COLOR.applied}}>Applied {timeAgo(app.applied_at)}</span>}
                    </div>
                  </div>
                  {/* Score */}
                  {app.relevance_score>0 && (
                    <div style={{width:44,height:44,borderRadius:10,display:"flex",alignItems:"center",justifyContent:"center",background:t.sBg(app.relevance_score)}}>
                      <span style={{fontSize:17,fontWeight:800,color:t.sTx(app.relevance_score),fontFamily:"'Playfair Display',serif"}}>{(app.relevance_score*100).toFixed(0)}</span>
                    </div>
                  )}
                  {/* Status buttons */}
                  <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
                    {Object.keys(ST_LABEL).map(st=>{
                      const isCur=app.status===st;
                      const sc=ST_COLOR[st];
                      const jobForSave = fullJob || app;
                      return (
                        <button key={st} onClick={()=>isCur?removeApp(app.external_id):saveApp(jobForSave,st)}
                          style={{padding:"6px 11px",borderRadius:7,border:`1.5px solid ${isCur?sc:t.bd}`,
                            background:isCur?`${sc}18`:"transparent",color:isCur?sc:t.txM,
                            fontSize:12,fontWeight:isCur?700:500,cursor:"pointer",fontFamily:"inherit",
                            transition:"all .15s",whiteSpace:"nowrap"}}>
                          {ST_LABEL[st]}
                        </button>
                      );
                    })}
                  </div>
                </div>
                {/* Resume version + Notes + actions */}
                <div style={{padding:"10px 20px 14px",borderTop:`1px solid ${t.bd}`,display:"flex",flexDirection:"column",gap:8}}>
                  {/* Resume version row */}
                  <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
                    <span style={{fontSize:12,fontWeight:700,color:t.txM,whiteSpace:"nowrap",minWidth:90}}>📄 Resume used:</span>
                    {editingResume===app.external_id ? (
                      <div style={{display:"flex",gap:6,flexWrap:"wrap",alignItems:"center"}}>
                        {RESUME_VERSIONS.map(v=>(
                          <button key={v} onClick={()=>{updateField(app.external_id,"resume_version",v);setEditingResume(null);}}
                            style={{padding:"4px 10px",borderRadius:6,border:`1.5px solid ${app.resume_version===v?t.ac:t.bd}`,
                              background:app.resume_version===v?t.acL:"transparent",
                              color:app.resume_version===v?t.ac:t.txS,fontSize:13,fontWeight:600,
                              cursor:"pointer",fontFamily:"inherit"}}>
                            {v}
                          </button>
                        ))}
                        <input defaultValue={app.resume_version||""} placeholder="or type custom…"
                          onBlur={e=>{if(e.target.value)updateField(app.external_id,"resume_version",e.target.value);setEditingResume(null);}}
                          onKeyDown={e=>{if(e.key==="Enter"){if(e.target.value)updateField(app.external_id,"resume_version",e.target.value);setEditingResume(null);}if(e.key==="Escape")setEditingResume(null);}}
                          style={{padding:"4px 10px",borderRadius:6,border:`1px solid ${t.ac}`,background:t.inp,color:t.tx,fontSize:13,fontFamily:"inherit",outline:"none",width:140}}
                        />
                      </div>
                    ) : (
                      <button onClick={()=>setEditingResume(app.external_id)}
                        style={{padding:"4px 10px",borderRadius:6,
                          border:`1.5px solid ${app.resume_version?t.ac:t.bd}`,
                          background:app.resume_version?t.acL:"transparent",
                          color:app.resume_version?t.ac:t.txM,fontSize:13,fontWeight:app.resume_version?700:400,
                          cursor:"pointer",fontFamily:"inherit"}}>
                        {app.resume_version || "＋ Set resume version"}
                      </button>
                    )}
                  </div>
                  {/* Notes + action buttons row */}
                  <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
                    {editing ? (
                      <input autoFocus defaultValue={app.notes}
                        onBlur={e=>{updateField(app.external_id,"notes",e.target.value);setEditingNotes(null);}}
                        onKeyDown={e=>{if(e.key==="Enter"){updateField(app.external_id,"notes",e.target.value);setEditingNotes(null);}if(e.key==="Escape")setEditingNotes(null);}}
                        placeholder="Add notes (press Enter to save)..."
                        style={{flex:1,padding:"8px 12px",borderRadius:8,border:`1px solid ${t.ac}`,
                          background:t.inp,color:t.tx,fontSize:14,fontFamily:"inherit",outline:"none"}}
                      />
                    ) : (
                      <button onClick={()=>setEditingNotes(app.external_id)}
                        style={{flex:1,textAlign:"left",padding:"8px 12px",borderRadius:8,
                          border:`1px solid ${app.notes?t.bd:"transparent"}`,background:app.notes?t.bgS:"transparent",
                          color:app.notes?t.txS:t.txM,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>
                        {app.notes || "✏️ Add notes..."}
                      </button>
                    )}
                    <a href={app.url} target="_blank" rel="noopener noreferrer"
                      style={{padding:"8px 14px",borderRadius:8,background:t.gP,color:"#fff",
                        fontSize:13,fontWeight:700,textDecoration:"none",whiteSpace:"nowrap"}}>
                      Apply →
                    </a>
                    <button onClick={()=>removeApp(app.external_id)}
                      style={{padding:"8px 12px",borderRadius:8,border:`1px solid ${t.er}30`,
                        background:"transparent",color:t.er,fontSize:13,fontWeight:600,
                        cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
