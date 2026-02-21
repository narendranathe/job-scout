import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area } from "recharts";

/* ═══════════════════════════════════════════════════════════════════
   THEME — Exact match: narendranathe.github.io palette
   ═══════════════════════════════════════════════════════════════════ */
const TH = {
  light: {
    bg:"#FDFCFA",bgS:"#F7F5F2",cd:"#FFFFFF",inp:"#F7F5F2",nav:"#FDFCFAee",
    tx:"#1C1C1C",txS:"#4A4A4A",txM:"#7A7A7A",
    ac:"#2D5A4A",acS:"#4A7C6F",acL:"#E8F0ED",
    wm:"#C4A77D",wmL:"#F5F0E8",bd:"#E8E6E3",
    ok:"#3D8B6E",er:"#B85450",vi:"#6B5B8D",bl:"#4A7C9F",
    shS:"0 2px 8px rgba(0,0,0,0.04)",sh:"0 4px 20px rgba(0,0,0,0.08)",
    gP:"linear-gradient(135deg,#2D5A4A,#4A7C6F)",gW:"linear-gradient(135deg,#C4A77D,#D4BC9A)",
    sBg:s=>s>=.85?"#E8F0ED":s>=.7?"#EBF2F7":s>=.5?"#F5F0E8":"#F5EAEA",
    sTx:s=>s>=.85?"#2D5A4A":s>=.7?"#4A7C9F":s>=.5?"#C4A77D":"#B85450",
  },
  dark: {
    bg:"#0D1A14",bgS:"#132B21",cd:"#18332A",inp:"#132B21",nav:"#0D1A14ee",
    tx:"#EDE8E0",txS:"#B8AFA2",txM:"#706A5E",
    ac:"#6FCF97",acS:"#8FD8AD",acL:"#1E3D30",
    wm:"#D4BC9A",wmL:"#2A2418",bd:"#2A3D33",
    ok:"#6FCF97",er:"#E07A73",vi:"#B8A5D6",bl:"#7CB5D4",
    shS:"0 2px 8px rgba(0,0,0,0.25)",sh:"0 4px 20px rgba(0,0,0,0.35)",
    gP:"linear-gradient(135deg,#3D8B6E,#6FCF97)",gW:"linear-gradient(135deg,#C4A77D,#D4BC9A)",
    sBg:s=>s>=.85?"#1E3D30":s>=.7?"#1A3040":s>=.5?"#2A2418":"#301A18",
    sTx:s=>s>=.85?"#6FCF97":s>=.7?"#7CB5D4":s>=.5?"#D4BC9A":"#E07A73",
  },
};

const ATS_META={greenhouse:{l:"Greenhouse",c:"#3D8B6E",i:"🌿"},lever:{l:"Lever",c:"#6B5B8D",i:"⚡"},workday:{l:"Workday",c:"#C4A77D",i:"📋"},custom:{l:"Direct",c:"#4A7C9F",i:"🔗"},ashby:{l:"Ashby",c:"#C0776E",i:"💎"},smartrecruiters:{l:"SmartRecr.",c:"#5B7B8D",i:"🎯"},bamboohr:{l:"BambooHR",c:"#73B761",i:"🎋"},unknown:{l:"Other",c:"#7A7A7A",i:"📄"}};

/* ═══════════════════════════════════════════════════════════════════
   DUAL-SOURCE DATA HOOK — Option D architecture

   Priority:
     1. Render API (GET /api/data)    → ~5 min freshness
     2. Static api-data.json          → ~60 min freshness (GitHub Actions)

   Auto-refreshes every 2 min from Render, every 10 min from static.
   Shows which source is active.
   ═══════════════════════════════════════════════════════════════════ */

// ⚠️ SET THIS after deploying to Render:
const RENDER_API = import.meta.env.VITE_RENDER_URL || "";
const STATIC_URL = "./api-data.json";

function useJobData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [source, setSource] = useState(null);      // "render" | "static" | null
  const [health, setHealth] = useState(null);       // Render health endpoint
  const [lastUpdated, setLastUpdated] = useState(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    // Try Render API first (5-min fresh data)
    if (RENDER_API) {
      try {
        const res = await fetch(`${RENDER_API}/api/data`, {
          cache: "no-cache",
          signal: AbortSignal.timeout(8000), // 8s timeout (cold start can be slow)
        });
        if (res.ok) {
          const json = await res.json();
          if (mountedRef.current && json.jobs?.length > 0) {
            setData(json);
            setSource("render");
            setLastUpdated(json.exported_at || null);
            setLoading(false);
            setError(null);
            return;
          }
        }
      } catch (e) {
        // Render unavailable — fall through to static
        console.log("Render API unavailable, using static fallback:", e.message);
      }
    }

    // Fallback: static api-data.json (GitHub Actions updates hourly)
    try {
      const res = await fetch(STATIC_URL, { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (mountedRef.current) {
        setData(json);
        setSource(RENDER_API ? "static" : "static-only");
        setLastUpdated(json.exported_at || null);
        setLoading(false);
        setError(null);
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e.message);
        setLoading(false);
      }
    }
  }, []);

  // Fetch health from Render
  const fetchHealth = useCallback(async () => {
    if (!RENDER_API) return;
    try {
      const res = await fetch(`${RENDER_API}/api/health`, {
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok && mountedRef.current) {
        setHealth(await res.json());
      }
    } catch {
      if (mountedRef.current) setHealth(null);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchData();
    fetchHealth();

    // Refresh data every 2 min, health every 30s
    const dataInterval = setInterval(fetchData, 2 * 60 * 1000);
    const healthInterval = setInterval(fetchHealth, 30 * 1000);

    return () => {
      mountedRef.current = false;
      clearInterval(dataInterval);
      clearInterval(healthInterval);
    };
  }, [fetchData, fetchHealth]);

  return { data, loading, error, source, health, lastUpdated };
}

/* ═══ Helpers ═══ */
const P = ({ ch, c, t }) => (
  <span style={{ display:"inline-block",fontSize:10,fontWeight:600,padding:"2px 8px",borderRadius:4,background:`${c||t.ac}14`,color:c||t.ac,letterSpacing:".02em",whiteSpace:"nowrap" }}>{ch}</span>
);
const fmt = n => n >= 1000 ? `${(n/1000).toFixed(0)}K` : `${n}`;
const fmtSal = n => n ? `$${(n/1000).toFixed(0)}K` : "\u2014";
const timeAgo = iso => {
  if (!iso) return "";
  const d = new Date(iso);
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins/60)}h ago`;
  return `${Math.floor(mins/1440)}d ago`;
};

/* ═══════════════════ MAIN DASHBOARD ═══════════════════ */
export default function App() {
  const [mode, setMode] = useState("light");
  const t = TH[mode];
  const { data, loading, error, source, health, lastUpdated } = useJobData();
  const [tab, setTab] = useState("jobs");
  const [xJ, setXJ] = useState(null);
  const [cf, sCf] = useState("All");
  const [rf, sRf] = useState("All");
  const [ef, sEf] = useState("All");
  const [sf, sSf] = useState("All");
  const [ro, sRo] = useState(false);
  const [q, sQ] = useState("");
  const [so, sSo] = useState("relevance");
  const [md, sMd] = useState(false);
  const [nC, sNC] = useState({ n:"",a:"greenhouse",s:"",u:"" });
  const [cq, sCq] = useState("");

  const allJobs = data?.jobs || [];
  const stats = data?.stats || {};
  const dist = data?.distributions || {};

  const cities = useMemo(() => {
    const set = new Set();
    allJobs.forEach(j => { if (j.is_remote) set.add("Remote"); if (j.location) set.add(j.location); });
    return ["All", ...Array.from(set).sort()];
  }, [allJobs]);

  const roles = useMemo(() => {
    const set = new Set(allJobs.map(j => j.title).filter(Boolean));
    return ["All", ...Array.from(set).sort()];
  }, [allJobs]);

  const fj = useMemo(() => {
    let j = [...allJobs];
    if (cf !== "All") j = j.filter(x => (x.location || "").includes(cf) || (cf === "Remote" && x.is_remote));
    if (rf !== "All") j = j.filter(x => x.title === rf);
    if (ef !== "All") j = j.filter(x => detectExp(x) === ef);
    if (sf === "Yes") j = j.filter(x => x.sponsorship || likelySponsors(x));
    if (sf === "No") j = j.filter(x => !x.sponsorship && !likelySponsors(x));
    if (ro) j = j.filter(x => x.is_remote);
    if (q) { const ql = q.toLowerCase(); j = j.filter(x => ((x.title||"")+(x.company||"")+(x.description||"")+(x.matched_skills||[]).join(" ")+(x.location||"")).toLowerCase().includes(ql)); }
    j.sort((a, b) => so === "salary" ? (b.salary_max||0) - (a.salary_max||0) : so === "date" ? new Date(b.posted_at||0) - new Date(a.posted_at||0) : (b.relevance_score||0) - (a.relevance_score||0));
    return j;
  }, [allJobs, cf, rf, ef, sf, ro, q, so]);

  const iS = { width:"100%",padding:"10px 12px",borderRadius:8,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:12,fontFamily:"'Source Sans 3',sans-serif",outline:"none",transition:"all .2s" };
  const sS = { ...iS, cursor: "pointer" };
  const ttS = { background:t.cd,border:`1px solid ${t.bd}`,borderRadius:8,fontSize:11,color:t.tx,boxShadow:t.sh };

  /* ─── Source status badge ─── */
  const SourceBadge = () => {
    const isLive = source === "render";
    const color = isLive ? t.ok : source === "static" ? t.wm : t.txM;
    const label = isLive ? "Live (Render)" : source === "static" ? "Static (Actions)" : source === "static-only" ? "Static" : "...";
    return (
      <div style={{ display:"flex",alignItems:"center",gap:6,fontSize:10,color:t.txM }}>
        <div style={{ width:6,height:6,borderRadius:"50%",background:color,boxShadow:isLive?`0 0 6px ${color}`:"none",animation:isLive?"pulse 2s infinite":"none" }}/>
        <span style={{ fontWeight:500 }}>{label}</span>
        {lastUpdated && <span style={{ opacity:0.7 }}>· {timeAgo(lastUpdated)}</span>}
      </div>
    );
  };

  /* ─── LOADING ─── */
  if (loading) return (
    <div style={{ minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif" }}>
      <div style={{ textAlign:"center" }}>
        <div style={{ fontSize:36,marginBottom:12,animation:"pulse 1.5s infinite" }}>⚡</div>
        <div style={{ fontSize:14,color:t.txS }}>Loading job data...</div>
      </div>
    </div>
  );

  /* ─── ERROR ─── */
  if (error && !data) return (
    <div style={{ minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif" }}>
      <div style={{ textAlign:"center",maxWidth:420,padding:30 }}>
        <div style={{ fontSize:36,marginBottom:12 }}>🔧</div>
        <h2 style={{ fontSize:20,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif",marginBottom:8 }}>Setting Up</h2>
        <p style={{ fontSize:13,color:t.txS,lineHeight:1.6 }}>Run your first scrape to populate the dashboard:</p>
        <code style={{ display:"block",background:t.bgS,padding:14,borderRadius:8,fontSize:12,color:t.ac,marginTop:12,textAlign:"left",lineHeight:1.8 }}>
          cd backend<br/>pip install -r requirements.txt<br/>python main.py --fast
        </code>
      </div>
    </div>
  );

  /* ─── EMPTY STATE ─── */
  if (allJobs.length === 0) return (
    <div style={{ minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif" }}>
      <div style={{ textAlign:"center",maxWidth:420,padding:30 }}>
        <div style={{ fontSize:36,marginBottom:12 }}>📡</div>
        <h2 style={{ fontSize:20,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif",marginBottom:8 }}>No Jobs Yet</h2>
        <p style={{ fontSize:13,color:t.txS,lineHeight:1.6 }}>The scraper hasn't found relevant jobs yet. Run a scrape or wait for the next automated cycle.</p>
        <SourceBadge />
      </div>
    </div>
  );

  const TABS = ["jobs","analytics","companies","trends","monitor"];

  return (<div style={{ minHeight:"100vh",background:t.bg,fontFamily:"'Source Sans 3',sans-serif",color:t.tx }}>
    {/* ═══ NAV ═══ */}
    <nav style={{ position:"sticky",top:0,zIndex:50,background:t.nav,backdropFilter:"blur(20px)",borderBottom:`1px solid ${t.bd}`,padding:"12px 24px",display:"flex",justifyContent:"space-between",alignItems:"center" }}>
      <div style={{ display:"flex",alignItems:"center",gap:14 }}>
        <h1 style={{ fontSize:20,fontWeight:700,color:t.ac,fontFamily:"'Playfair Display',Georgia,serif",margin:0 }}>⚡ JobScout</h1>
        <SourceBadge />
      </div>
      <div style={{ display:"flex",alignItems:"center",gap:10 }}>
        {TABS.map(tb=>(
          <button key={tb} onClick={()=>setTab(tb)} style={{ padding:"6px 14px",borderRadius:6,border:"none",background:tab===tb?t.gP:"transparent",color:tab===tb?"#fff":t.txM,fontSize:11,fontWeight:600,cursor:"pointer",fontFamily:"inherit",textTransform:"capitalize" }}>{tb === "monitor" ? "🖥 Monitor" : tb}</button>
        ))}
        <button onClick={()=>setMode(m=>m==="light"?"dark":"light")} style={{ padding:"6px 12px",borderRadius:6,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:13,cursor:"pointer" }}>{mode==="light"?"🌙":"☀️"}</button>
      </div>
    </nav>

    <div style={{ maxWidth:1200,margin:"0 auto",padding:20 }}>
      {/* ═══ STATS BAR ═══ */}
      <div style={{ display:"grid",gridTemplateColumns:"repeat(6,1fr)",gap:10,marginBottom:20 }}>
        {[
          [stats.total_jobs||0,"Total Jobs",t.ac,t.acL],
          [stats.high_match||0,"High Match",t.ok,"#E8F5E8"],
          [`${stats.remote_pct||0}%`,"Remote",t.bl,"#EBF2F7"],
          [stats.avg_salary?fmtSal(stats.avg_salary):"\u2014","Avg Salary",t.wm,t.wmL],
          [`${stats.h1b_pct||0}%`,"Sponsoring",t.vi,"#F0EBF7"],
          [stats.companies_tracked||0,"Companies",t.acS,t.acL],
        ].map(([v,l,c,bg])=>(
          <div key={l} style={{ background:t.cd,borderRadius:10,padding:"14px 10px",textAlign:"center",border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
            <div style={{ fontSize:22,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif" }}>{v}</div>
            <div style={{ fontSize:9,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".05em",marginTop:2 }}>{l}</div>
          </div>
        ))}
      </div>

      {/* ═══ JOBS TAB ═══ */}
      {tab==="jobs"&&<div>
        <div style={{ display:"flex",gap:8,flexWrap:"wrap",marginBottom:16,alignItems:"center" }}>
          <input placeholder="Search jobs, skills, companies..." value={q} onChange={e=>sQ(e.target.value)} style={{ ...iS,maxWidth:260 }}/>
          <select value={cf} onChange={e=>sCf(e.target.value)} style={{ ...sS,maxWidth:160 }}><option value="All">📍 All Locations</option>{cities.filter(c=>c!=="All").map(c=><option key={c} value={c}>{c}</option>)}</select>
          <select value={ef} onChange={e=>sEf(e.target.value)} style={{ ...sS,maxWidth:130 }}><option value="All">🎯 All Levels</option>{["Entry","Mid","Senior","Staff","Lead","Principal"].map(e=><option key={e} value={e}>{e}</option>)}</select>
          <select value={sf} onChange={e=>sSf(e.target.value)} style={{ ...sS,maxWidth:130 }}><option value="All">🛂 H1B Filter</option><option value="Yes">Likely Sponsors</option><option value="No">No Sponsorship</option></select>
          <button onClick={()=>sRo(r=>!r)} style={{ padding:"10px 14px",borderRadius:8,border:`1px solid ${ro?t.ac:t.bd}`,background:ro?t.acL:"transparent",color:ro?t.ac:t.txM,fontSize:11,fontWeight:600,cursor:"pointer",fontFamily:"inherit" }}>{ro?"🏠 Remote Only":"🏠 Remote"}</button>
          <select value={so} onChange={e=>sSo(e.target.value)} style={{ ...sS,maxWidth:140 }}><option value="relevance">↓ Relevance</option><option value="salary">↓ Salary</option><option value="date">↓ Newest</option></select>
          <span style={{ fontSize:11,color:t.txM,marginLeft:"auto" }}>{fj.length} of {allJobs.length} jobs</span>
        </div>

        <div style={{ display:"flex",flexDirection:"column",gap:8 }}>
          {fj.slice(0,50).map(j=>{
            const sc = j.relevance_score || 0;
            const open = xJ === j.external_id;
            const ats = ATS_META[j.ats] || ATS_META.unknown;
            return (
              <div key={j.external_id} onClick={()=>setXJ(open?null:j.external_id)} style={{ background:t.cd,borderRadius:10,border:`1px solid ${t.bd}`,overflow:"hidden",cursor:"pointer",transition:"all .2s",boxShadow:open?t.sh:t.shS }}>
                <div style={{ padding:"14px 18px",display:"flex",justifyContent:"space-between",alignItems:"center" }}>
                  <div style={{ flex:1,minWidth:0 }}>
                    <div style={{ display:"flex",alignItems:"center",gap:8,marginBottom:4 }}>
                      <span style={{ fontSize:14,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif" }}>{j.title}</span>
                      <P ch={`${ats.i} ${ats.l}`} c={ats.c} t={t}/>
                    </div>
                    <div style={{ display:"flex",gap:10,fontSize:11,color:t.txS }}>
                      <span style={{ fontWeight:600 }}>{j.company}</span>
                      <span>{j.location || "—"}</span>
                      {j.is_remote&&<span style={{ color:t.ok,fontWeight:600 }}>🏠 Remote</span>}
                      {j.salary_max>0&&<span style={{ color:t.wm,fontWeight:600 }}>{fmtSal(j.salary_min)}–{fmtSal(j.salary_max)}</span>}
                      {j.posted_at&&<span style={{ color:t.txM }}>{timeAgo(j.posted_at)}</span>}
                    </div>
                  </div>
                  <div style={{ display:"flex",alignItems:"center",gap:10 }}>
                    <div style={{ width:50,height:50,borderRadius:10,display:"flex",alignItems:"center",justifyContent:"center",background:t.sBg(sc),flexShrink:0 }}>
                      <span style={{ fontSize:16,fontWeight:800,color:t.sTx(sc),fontFamily:"'Playfair Display',serif" }}>{(sc*100).toFixed(0)}</span>
                    </div>
                    <span style={{ fontSize:16,color:t.txM,transform:open?"rotate(180deg)":"",transition:"transform .2s" }}>▾</span>
                  </div>
                </div>
                {open&&<div style={{ padding:"0 18px 14px",borderTop:`1px solid ${t.bd}` }}>
                  <div style={{ display:"flex",gap:4,flexWrap:"wrap",margin:"12px 0 8px" }}>
                    {(j.matched_skills||[]).map(s=><P key={s} ch={s} t={t}/>)}
                    {(j.sponsorship||likelySponsors(j))&&<P ch="🛂 Likely H1B" c={t.vi} t={t}/>}
                  </div>
                  {j.description&&<p style={{ fontSize:12,color:t.txS,lineHeight:1.7,maxHeight:120,overflow:"hidden",margin:"8px 0" }}>{j.description.slice(0,500)}...</p>}
                  <a href={j.url} target="_blank" rel="noopener noreferrer" onClick={e=>e.stopPropagation()} style={{ display:"inline-block",padding:"8px 18px",borderRadius:6,background:t.gP,color:"#fff",fontSize:11,fontWeight:600,textDecoration:"none",marginTop:4,boxShadow:`0 2px 8px ${t.ac}30` }}>Apply →</a>
                </div>}
              </div>
            );
          })}
          {fj.length>50&&<div style={{ textAlign:"center",padding:16,color:t.txM,fontSize:12 }}>Showing 50 of {fj.length} — use filters to narrow down</div>}
        </div>
      </div>}

      {/* ═══ ANALYTICS ═══ */}
      {tab==="analytics"&&<div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
        <div style={{ background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>ATS Distribution</h3>
          <ResponsiveContainer width="100%" height={240}><PieChart>
            <Pie data={dist.ats||[]} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={3} stroke="none">
              {(dist.ats||[]).map((d,i)=><Cell key={i} fill={(ATS_META[d.name]||ATS_META.unknown).c} opacity={0.75}/>)}
            </Pie>
            <Tooltip contentStyle={ttS}/>
          </PieChart></ResponsiveContainer>
          <div style={{ display:"flex",gap:8,flexWrap:"wrap",justifyContent:"center",marginTop:8 }}>
            {(dist.ats||[]).map(d=>{const m=ATS_META[d.name]||ATS_META.unknown;return <span key={d.name} style={{ fontSize:10,color:m.c,fontWeight:600 }}>{m.i} {m.l}: {d.value}</span>;})}
          </div>
        </div>
        <div style={{ background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>Salary Distribution</h3>
          <ResponsiveContainer width="100%" height={240}><BarChart data={dist.salary_buckets||[]}>
            <XAxis dataKey="range" tick={{ fill:t.txM,fontSize:9 }} axisLine={{ stroke:t.bd }} tickLine={false}/>
            <YAxis tick={{ fill:t.txM,fontSize:9 }} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Bar dataKey="count" radius={[6,6,0,0]}>{(dist.salary_buckets||[]).map((d,i)=><Cell key={i} fill={[t.wm,t.wm,t.acS,t.ok,t.ac,t.vi][i]||t.ac} opacity={0.6}/>)}</Bar>
          </BarChart></ResponsiveContainer>
        </div>
        <div style={{ background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>30-Day Trend</h3>
          <ResponsiveContainer width="100%" height={240}><AreaChart data={data?.trend||[]}>
            <XAxis dataKey="date" tick={{ fill:t.txM,fontSize:9 }} axisLine={{ stroke:t.bd }} tickLine={false} tickFormatter={v=>v.slice(5)}/>
            <YAxis tick={{ fill:t.txM,fontSize:9 }} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
          </AreaChart></ResponsiveContainer>
        </div>
        <div style={{ background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>Quick Stats</h3>
          <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:10 }}>
            {[
              [`${stats.h1b_pct||0}%`,"Likely H1B Sponsors",t.vi],
              [`${stats.remote_pct||0}%`,"Remote Positions",t.ok],
              [`${stats.companies_tracked||0}`,"Companies Tracked",t.ac],
              [`${stats.high_match||0}`,"High-Match Jobs",t.wm],
            ].map(([v,l,c])=>(
              <div key={l} style={{ padding:16,borderRadius:10,background:`${c}08`,border:`1px solid ${c}20`,textAlign:"center" }}>
                <div style={{ fontSize:32,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif" }}>{v}</div>
                <div style={{ fontSize:10,color:t.txM,marginTop:2 }}>{l}</div>
              </div>
            ))}
          </div>
        </div>
      </div>}

      {/* ═══ COMPANIES ═══ */}
      {tab==="companies"&&<div>
        <div style={{ marginBottom:16 }}><input placeholder="Search companies..." value={cq} onChange={e=>sCq(e.target.value)} style={{ ...iS,maxWidth:320 }}/></div>
        <div style={{ display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))",gap:14 }}>
          {(data?.top_companies||[]).filter(c=>!cq||c.name.toLowerCase().includes(cq.toLowerCase())).map(co=>(
            <div key={co.name} style={{ background:t.cd,borderRadius:12,padding:18,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
              <div style={{ display:"flex",justifyContent:"space-between",alignItems:"start",marginBottom:12 }}>
                <h4 style={{ margin:0,fontSize:15,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif" }}>{co.name}</h4>
                <div style={{ background:t.acL,padding:"4px 10px",borderRadius:6 }}>
                  <span style={{ fontSize:14,fontWeight:700,color:t.ac }}>{co.count}</span>
                  <span style={{ fontSize:9,color:t.txM,marginLeft:4 }}>jobs</span>
                </div>
              </div>
              <div style={{ display:"flex",gap:4,flexWrap:"wrap" }}>
                {allJobs.filter(j=>j.company===co.name).slice(0,3).map((j,i)=>(
                  <span key={i} style={{ fontSize:10,padding:"2px 8px",borderRadius:4,background:t.bgS,color:t.txS,border:`1px solid ${t.bd}` }}>{j.title}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>}

      {/* ═══ TRENDS ═══ */}
      {tab==="trends"&&<div style={{ display:"grid",gridTemplateColumns:"2fr 1fr",gap:14 }}>
        <div style={{ background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>Jobs by Date</h3>
          <ResponsiveContainer width="100%" height={270}><AreaChart data={data?.trend||[]}>
            <XAxis dataKey="date" tick={{ fill:t.txM,fontSize:9 }} axisLine={{ stroke:t.bd }} tickLine={false} tickFormatter={v=>v.slice(5)}/>
            <YAxis tick={{ fill:t.txM,fontSize:9 }} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
          </AreaChart></ResponsiveContainer>
        </div>
        <div style={{ display:"flex",flexDirection:"column",gap:14 }}>
          <div style={{ background:t.cd,borderRadius:12,padding:18,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1 }}>
            <h3 style={{ margin:"0 0 12px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>Top Companies</h3>
            {(data?.top_companies||[]).slice(0,8).map((co,i)=>(
              <div key={co.name} style={{ display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none" }}>
                <span style={{ fontSize:12,fontWeight:600,color:t.tx }}>{co.name}</span>
                <span style={{ fontSize:12,fontWeight:700,color:t.ac }}>{co.count}</span>
              </div>
            ))}
          </div>
          <div style={{ background:t.cd,borderRadius:12,padding:18,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1 }}>
            <h3 style={{ margin:"0 0 12px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>Top Locations</h3>
            {(dist.cities||[]).slice(0,8).map((c,i)=>(
              <div key={c.name} style={{ display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none" }}>
                <span style={{ fontSize:12,fontWeight:600,color:t.tx }}>{c.name}</span>
                <span style={{ fontSize:12,fontWeight:600,color:t.acS }}>{c.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>}

      {/* ═══ MONITOR — Option D Health Dashboard ═══ */}
      {tab==="monitor"&&<div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:14 }}>
        {/* System Status */}
        <div style={{ background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>System Status</h3>
          <div style={{ display:"flex",flexDirection:"column",gap:12 }}>
            <StatusRow label="Data Source" value={source === "render" ? "Render API (Live)" : source === "static" ? "Static Fallback" : "Static Only"} color={source === "render" ? t.ok : t.wm} t={t}/>
            <StatusRow label="Render API" value={RENDER_API || "Not configured"} color={RENDER_API ? t.ac : t.txM} t={t} mono/>
            <StatusRow label="Last Data Refresh" value={lastUpdated ? timeAgo(lastUpdated) : "—"} color={t.ac} t={t}/>
            {health && <>
              <StatusRow label="Server Status" value={health.status === "idle" ? "Idle" : "Scraping..."} color={health.status === "scraping" ? t.wm : t.ok} t={t}/>
              <StatusRow label="Server Uptime" value={`${health.uptime_hours || 0}h`} color={t.ac} t={t}/>
              <StatusRow label="Total Cycles" value={health.total_cycles || 0} color={t.ac} t={t}/>
              <StatusRow label="New Jobs Found" value={health.total_new_jobs || 0} color={t.ok} t={t}/>
              <StatusRow label="Last Scrape Duration" value={`${health.last_duration_sec || 0}s`} color={t.ac} t={t}/>
              <StatusRow label="Companies Tracked" value={health.companies_tracked || 0} color={t.ac} t={t}/>
              <StatusRow label="Scan Interval" value={`${(health.fast_interval_sec || 300) / 60} min`} color={t.ac} t={t}/>
              {health.last_error && <StatusRow label="Last Error" value={health.last_error} color={t.er} t={t}/>}
            </>}
            {!health && RENDER_API && <div style={{ fontSize:11,color:t.txM,padding:"8px 0" }}>Render server not responding — may be in cold start or unavailable.</div>}
          </div>
        </div>

        {/* Architecture Diagram */}
        <div style={{ background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>Option D Architecture</h3>
          <div style={{ fontSize:11,color:t.txS,lineHeight:2,fontFamily:"'Source Code Pro',monospace" }}>
            <div style={{ padding:12,background:t.bgS,borderRadius:8,border:`1px solid ${t.bd}` }}>
              <div style={{ color:t.ok,fontWeight:700 }}>🟢 Render (every 5 min)</div>
              <div>&nbsp;&nbsp;Tier 1 → 24 top companies</div>
              <div>&nbsp;&nbsp;GET /api/data → Dashboard</div>
              <div style={{ borderTop:`1px dashed ${t.bd}`,margin:"8px 0" }}/>
              <div style={{ color:t.wm,fontWeight:700 }}>🟡 GitHub Actions (hourly)</div>
              <div>&nbsp;&nbsp;All tiers → 109 companies</div>
              <div>&nbsp;&nbsp;api-data.json → Static fallback</div>
              <div style={{ borderTop:`1px dashed ${t.bd}`,margin:"8px 0" }}/>
              <div style={{ color:t.vi,fontWeight:700 }}>💓 Keepalive (every 14 min)</div>
              <div>&nbsp;&nbsp;Actions pings /ping → Prevents sleep</div>
            </div>
          </div>
          <div style={{ marginTop:14,padding:12,background:`${t.ac}08`,borderRadius:8,border:`1px solid ${t.ac}15` }}>
            <div style={{ fontSize:10,fontWeight:700,color:t.ac,marginBottom:6,textTransform:"uppercase" }}>Setup Checklist</div>
            <div style={{ fontSize:11,color:t.txS,lineHeight:1.8 }}>
              <CheckItem done={!!RENDER_API} label="Set VITE_RENDER_URL in .env" t={t}/>
              <CheckItem done={source === "render"} label="Render API responding" t={t}/>
              <CheckItem done={!!health} label="Health endpoint reachable" t={t}/>
              <CheckItem done={health?.total_cycles > 0} label="First scrape completed" t={t}/>
              <CheckItem done={allJobs.length > 0} label="Jobs flowing to dashboard" t={t}/>
            </div>
          </div>
        </div>

        {/* Scrape History */}
        <div style={{ gridColumn:"1/-1",background:t.cd,borderRadius:12,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS }}>
          <h3 style={{ margin:"0 0 16px",fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".08em" }}>Scrape History</h3>
          <div style={{ overflowX:"auto" }}>
            <table style={{ width:"100%",borderCollapse:"collapse",fontSize:11 }}>
              <thead>
                <tr style={{ borderBottom:`2px solid ${t.bd}` }}>
                  {["Time","Status","Duration","Companies","Found","New","Errors"].map(h=>(
                    <th key={h} style={{ padding:"8px 12px",textAlign:"left",color:t.txM,fontWeight:600,fontSize:10,textTransform:"uppercase",letterSpacing:".06em" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.runs || []).map((r, i) => (
                  <tr key={i} style={{ borderBottom:`1px solid ${t.bd}` }}>
                    <td style={{ padding:"8px 12px",color:t.txS }}>{r.started_at ? timeAgo(r.started_at) : "—"}</td>
                    <td style={{ padding:"8px 12px" }}><span style={{ color:r.status==="completed"?t.ok:t.er,fontWeight:600 }}>{r.status||"—"}</span></td>
                    <td style={{ padding:"8px 12px",color:t.txS }}>{r.duration_sec ? `${r.duration_sec}s` : "—"}</td>
                    <td style={{ padding:"8px 12px",color:t.ac,fontWeight:600 }}>{r.companies_scraped||"—"}</td>
                    <td style={{ padding:"8px 12px",color:t.txS }}>{r.jobs_found||"—"}</td>
                    <td style={{ padding:"8px 12px",color:t.ok,fontWeight:600 }}>{r.new_jobs||"—"}</td>
                    <td style={{ padding:"8px 12px",color:(r.errors||0)>0?t.er:t.txM }}>{r.errors||0}</td>
                  </tr>
                ))}
                {(data?.runs||[]).length === 0 && <tr><td colSpan={7} style={{ padding:20,textAlign:"center",color:t.txM }}>No scrape history yet</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>}
    </div>

    {/* ═══ ADD COMPANY MODAL ═══ */}
    {md&&<div style={{ position:"fixed",inset:0,zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",background:mode==="dark"?"rgba(0,0,0,.55)":"rgba(28,28,28,.25)",backdropFilter:"blur(8px)" }} onClick={()=>sMd(false)}>
      <div onClick={e=>e.stopPropagation()} style={{ background:t.cd,borderRadius:14,padding:28,border:`1px solid ${t.bd}`,width:430,boxShadow:"0 16px 50px rgba(0,0,0,.18)" }}>
        <h3 style={{ margin:"0 0 20px",fontSize:18,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif" }}>Add Company</h3>
        <div style={{ display:"flex",flexDirection:"column",gap:12 }}>
          <div><label style={{ fontSize:10,color:t.txM,fontWeight:600,marginBottom:4,display:"block",textTransform:"uppercase",letterSpacing:".06em" }}>Company Name</label><input value={nC.n} onChange={e=>sNC({...nC,n:e.target.value})} placeholder="e.g. Snowflake" style={iS}/></div>
          <div><label style={{ fontSize:10,color:t.txM,fontWeight:600,marginBottom:4,display:"block",textTransform:"uppercase",letterSpacing:".06em" }}>ATS</label><select value={nC.a} onChange={e=>sNC({...nC,a:e.target.value})} style={sS}>{Object.entries(ATS_META).filter(([k])=>!["unknown","custom"].includes(k)).map(([k,v])=><option key={k} value={k}>{v.i} {v.l}</option>)}</select></div>
          <div><label style={{ fontSize:10,color:t.txM,fontWeight:600,marginBottom:4,display:"block",textTransform:"uppercase",letterSpacing:".06em" }}>Slug</label><input value={nC.s} onChange={e=>sNC({...nC,s:e.target.value})} placeholder="from-careers-page-url" style={iS}/></div>
          <div style={{ display:"flex",gap:8,marginTop:6 }}>
            <button onClick={()=>{sMd(false);sNC({n:"",a:"greenhouse",s:"",u:""})}} style={{ flex:1,padding:"10px",borderRadius:8,border:`1px solid ${t.bd}`,background:t.inp,color:t.txS,fontSize:12,fontWeight:500,cursor:"pointer",fontFamily:"inherit" }}>Cancel</button>
            <button onClick={()=>{sMd(false);sNC({n:"",a:"greenhouse",s:"",u:""})}} style={{ flex:1,padding:"10px",borderRadius:8,border:"none",background:t.gP,color:"#fff",fontSize:12,fontWeight:600,cursor:"pointer",fontFamily:"inherit" }}>Add</button>
          </div>
        </div>
      </div>
    </div>}

    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;800&family=Source+Sans+3:wght@300;400;500;600;700&family=Source+Code+Pro:wght@400;500&display=swap');
      *{box-sizing:border-box;margin:0}
      ::-webkit-scrollbar{width:7px}::-webkit-scrollbar-track{background:${t.bgS}}::-webkit-scrollbar-thumb{background:${t.acS};border-radius:4px}
      ::selection{background:${t.acL};color:${t.ac}}
      input:focus,select:focus{border-color:${t.acS}!important;box-shadow:0 0 0 3px ${t.ac}12!important}
      @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    `}</style>
  </div>);
}

/* ═══ Monitor helper components ═══ */
function StatusRow({ label, value, color, t, mono }) {
  return (
    <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center",padding:"6px 0",borderBottom:`1px solid ${t.bd}` }}>
      <span style={{ fontSize:11,color:t.txM,fontWeight:500 }}>{label}</span>
      <span style={{ fontSize:11,fontWeight:600,color,fontFamily:mono?"'Source Code Pro',monospace":"inherit" }}>{value}</span>
    </div>
  );
}

function CheckItem({ done, label, t }) {
  return (
    <div style={{ display:"flex",alignItems:"center",gap:6 }}>
      <span style={{ fontSize:13 }}>{done ? "✅" : "⬜"}</span>
      <span style={{ color: done ? t.ok : t.txM }}>{label}</span>
    </div>
  );
}

/* ═══ Utility functions ═══ */
function detectExp(job) {
  const t = (job.title || "").toLowerCase();
  if (/principal|distinguished|fellow/.test(t)) return "Principal";
  if (/\bstaff\b/.test(t)) return "Staff";
  if (/\blead\b|director|head of/.test(t)) return "Lead";
  if (/senior|sr\b/.test(t)) return "Senior";
  if (/junior|jr\b|associate|entry|intern/.test(t)) return "Entry";
  return "Mid";
}

function likelySponsors(job) {
  const text = ((job.description||"") + " " + (job.company||"")).toLowerCase();
  const pos = /visa sponsor|h1b|h-1b|sponsorship available/.test(text);
  const neg = /no sponsorship|not sponsor|unable to sponsor|citizen only/.test(text);
  if (neg) return false;
  if (pos) return true;
  const big = ["uber","meta","google","amazon","apple","microsoft","netflix","stripe","anthropic","openai","datadog","snowflake","databricks","two sigma","citadel","bloomberg","capital one","palantir","coinbase"];
  return big.includes((job.company||"").toLowerCase());
}
