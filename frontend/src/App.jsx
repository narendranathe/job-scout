import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area } from "recharts";

/* ═══════════════════════════════════════════════════════════════════
   THEME — narendranathe.github.io palette
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

const ATS_META={greenhouse:{l:"Greenhouse",c:"#3D8B6E",i:"🌿"},lever:{l:"Lever",c:"#6B5B8D",i:"⚡"},ashby:{l:"Ashby",c:"#C0776E",i:"💎"},smartrecruiters:{l:"SmartRecr.",c:"#5B7B8D",i:"🎯"},bamboohr:{l:"BambooHR",c:"#73B761",i:"🎋"},unknown:{l:"Other",c:"#7A7A7A",i:"📄"}};

/* ═══ Custom SVG Brand Logo ═══
   Radar/crosshair — "scouting" for jobs
   Uses the portfolio green + gold accent
   ═══════════════════════════════════════ */
function BrandLogo({ size = 32, t }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Outer ring */}
      <circle cx="20" cy="20" r="17" stroke={t.ac} strokeWidth="2" opacity="0.3"/>
      {/* Middle ring */}
      <circle cx="20" cy="20" r="11" stroke={t.ac} strokeWidth="2" opacity="0.6"/>
      {/* Inner filled dot */}
      <circle cx="20" cy="20" r="5" fill={t.ac}/>
      {/* Crosshair lines */}
      <line x1="20" y1="1" x2="20" y2="8" stroke={t.wm} strokeWidth="2" strokeLinecap="round"/>
      <line x1="20" y1="32" x2="20" y2="39" stroke={t.wm} strokeWidth="2" strokeLinecap="round"/>
      <line x1="1" y1="20" x2="8" y2="20" stroke={t.wm} strokeWidth="2" strokeLinecap="round"/>
      <line x1="32" y1="20" x2="39" y2="20" stroke={t.wm} strokeWidth="2" strokeLinecap="round"/>
      {/* Sweep arc — like a radar sweep */}
      <path d="M20 20 L20 5 A15 15 0 0 1 33 13 Z" fill={t.ac} opacity="0.12"/>
    </svg>
  );
}

/* ═══ Company logo — fetched from their actual website ═══
   Chain: Google Favicons (highest quality) → Clearbit → DuckDuckGo → Letter
   Google's S2 service grabs the real favicon from any domain at any size.
*/
const CO_DOMAINS = {
  "Anthropic":"anthropic.com","OpenAI":"openai.com","Stripe":"stripe.com","Datadog":"datadoghq.com",
  "Databricks":"databricks.com","Snowflake":"snowflake.com","Coinbase":"coinbase.com","Palantir":"palantir.com",
  "Scale AI":"scale.com","Discord":"discord.com","Ramp":"ramp.com","Plaid":"plaid.com","Reddit":"reddit.com",
  "Anduril":"anduril.com","Wiz":"wiz.io","Rippling":"rippling.com","dbt Labs":"getdbt.com",
  "Fivetran":"fivetran.com","Confluent":"confluent.io","Netflix":"netflix.com","Spotify":"spotify.com",
  "Vercel":"vercel.com","Linear":"linear.app","Supabase":"supabase.com","Figma":"figma.com",
  "Notion":"notion.so","Brex":"brex.com","Airtable":"airtable.com","MongoDB":"mongodb.com",
  "Elastic":"elastic.co","Cloudflare":"cloudflare.com","GitLab":"gitlab.com","HashiCorp":"hashicorp.com",
  "CrowdStrike":"crowdstrike.com","Block (Square)":"block.xyz","Twilio":"twilio.com","Affirm":"affirm.com",
  "Gusto":"gusto.com","Toast":"toasttab.com","Samsara":"samsara.com","Miro":"miro.com",
  "Navan":"navan.com","Grammarly":"grammarly.com","Canva":"canva.com","Zapier":"zapier.com",
  "Webflow":"webflow.com","Grafana Labs":"grafana.com","Temporal":"temporal.io",
  "Cockroach Labs":"cockroachlabs.com","PlanetScale":"planetscale.com","Vanta":"vanta.com",
  "Weights & Biases":"wandb.ai","Cohere":"cohere.com","Mistral AI":"mistral.ai",
  "Hugging Face":"huggingface.co","Perplexity":"perplexity.ai","Instacart":"instacart.com",
  "DoorDash":"doordash.com","Lyft":"lyft.com","Airbnb":"airbnb.com","Pinterest":"pinterest.com",
  "Snap":"snap.com","Robinhood":"robinhood.com","Chime":"chime.com","Faire":"faire.com",
  "Flexport":"flexport.com","Pagerduty":"pagerduty.com","Okta":"okta.com","SentinelOne":"sentinelone.com",
  "Retool":"retool.com","Neon":"neon.tech","PostHog":"posthog.com","Railway":"railway.app",
  "Tinybird":"tinybird.co","MotherDuck":"motherduck.com","Hex":"hex.tech","Visa":"visa.com",
  "KPMG":"kpmg.com","Bosch":"bosch.com","Prefect":"prefect.io","Dagster":"dagster.io",
  "Great Expectations":"greatexpectations.io","Uber":"uber.com","Atlassian":"atlassian.com",
  "Dropbox":"dropbox.com","Asana":"asana.com","HubSpot":"hubspot.com","Zoom":"zoom.us",
  "Rubrik":"rubrik.com","ClickHouse":"clickhouse.com","Starburst":"starburst.io",
  "Materialize":"materialize.com","Amplitude":"amplitude.com","Calendly":"calendly.com",
  "ClickUp":"clickup.com","Loom":"loom.com","Nutanix":"nutanix.com","Pure Storage":"purestorage.com",
  "Verkada":"verkada.com","Zscaler":"zscaler.com","Galaxy":"galaxy.com",
};

/* Guess domain from company name for logos not in our map */
function guessDomain(name) {
  if (!name) return null;
  const known = CO_DOMAINS[name];
  if (known) return known;
  // Simple heuristic: lowercase, remove spaces/special chars, add .com
  const clean = name.toLowerCase().replace(/[^a-z0-9]/g, "");
  return clean ? `${clean}.com` : null;
}

function LogoImg({ name, size = 32, t }) {
  const [stage, setStage] = useState(0); // 0=google, 1=clearbit, 2=letter
  const domain = guessDomain(name);

  if (!domain || stage >= 2) {
    const letter = (name || "?")[0].toUpperCase();
    const hue = [...(name||"")].reduce((h,c)=>h+c.charCodeAt(0),0) % 360;
    return (
      <div style={{ width:size,height:size,borderRadius:8,background:`hsl(${hue},25%,92%)`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:size*0.44,fontWeight:800,color:`hsl(${hue},35%,40%)`,flexShrink:0,fontFamily:"'Playfair Display',serif" }}>
        {letter}
      </div>
    );
  }

  const srcs = [
    `https://www.google.com/s2/favicons?domain=${domain}&sz=${size*2}`,
    `https://logo.clearbit.com/${domain}?size=${size*2}`,
  ];

  return (
    <img
      src={srcs[stage]}
      alt=""
      width={size}
      height={size}
      style={{ borderRadius:8,flexShrink:0,objectFit:"contain",background:"#fff",border:`1px solid ${t.bd}` }}
      onError={() => setStage(s => s + 1)}
    />
  );
}

/* ═══ Role categories ═══ */
const ROLE_CATS = [
  { id:"de",  label:"Data Engineer",         kw:["data engineer","etl engineer","data pipeline","data infrastructure","big data engineer","analytics platform"] },
  { id:"ml",  label:"ML / AI Engineer",      kw:["ml engineer","machine learning","ai engineer","ai platform","mlops","deep learning","llm","generative ai"] },
  { id:"ae",  label:"Analytics Engineer",    kw:["analytics engineer","business intelligence","bi engineer","bi developer"] },
  { id:"ds",  label:"Data Scientist",        kw:["data scientist","research scientist","applied scientist"] },
  { id:"pe",  label:"Platform / Infra",      kw:["platform engineer","infrastructure engineer","cloud engineer","devops","sre","site reliability","systems engineer"] },
  { id:"swe", label:"Software Engineer",     kw:["software engineer","backend engineer","full stack","fullstack"] },
  { id:"da",  label:"Data Architect",        kw:["data architect","solutions architect"] },
];
function catOf(title) {
  const t = (title||"").toLowerCase();
  for (const c of ROLE_CATS) if (c.kw.some(k => t.includes(k))) return c.id;
  return "other";
}

/* ═══ Location normalization ═══ */
const US_STATES = {"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia"};
const ST_REV = Object.fromEntries(Object.entries(US_STATES).map(([k,v])=>[v.toLowerCase(),k]));
const HUBS = {"San Francisco":"CA","San Jose":"CA","Palo Alto":"CA","Mountain View":"CA","Sunnyvale":"CA","Menlo Park":"CA","Cupertino":"CA","Santa Clara":"CA","Oakland":"CA","Redwood City":"CA","New York":"NY","Manhattan":"NY","Brooklyn":"NY","Seattle":"WA","Bellevue":"WA","Redmond":"WA","Austin":"TX","Dallas":"TX","Houston":"TX","Plano":"TX","Boston":"MA","Cambridge":"MA","Los Angeles":"CA","Santa Monica":"CA","Chicago":"IL","Denver":"CO","Boulder":"CO","Atlanta":"GA","Raleigh":"NC","Durham":"NC","Pittsburgh":"PA","Philadelphia":"PA","Portland":"OR","Salt Lake City":"UT","Miami":"FL","Washington":"DC","Arlington":"VA","McLean":"VA","San Diego":"CA","Irvine":"CA","Minneapolis":"MN","Detroit":"MI","Nashville":"TN"};
const REMOTE_WORDS = ["remote","work from home","wfh","distributed","anywhere"];
const US_WORDS = ["united states","usa","u.s.a.","u.s.","america"];

/* YOUR preferred locations — these float to the top of filter chips */
const PREFERRED_STATES = ["TX","CA","NY","WA","CO","IL","GA","MA"];
const PREFERRED_CITIES = ["Remote","Dallas","Austin","Plano","Houston","San Francisco","New York","Seattle"];

function normLoc(loc, isRemote) {
  if (isRemote || (!loc && isRemote)) return { display:"Remote",city:"Remote",state:null,isRemote:true,isUS:true };
  if (!loc) return { display:"Unknown",city:null,state:null,isRemote:false,isUS:false };
  const raw = loc.trim(), low = raw.toLowerCase();
  if (REMOTE_WORDS.some(w => low.includes(w))) return { display:"Remote",city:"Remote",state:null,isRemote:true,isUS:true };
  const isUS = US_WORDS.some(w => low.includes(w)) || /\b[A-Z]{2}\b/.test(raw);
  let state = null;
  const abbrMatch = raw.match(/\b([A-Z]{2})\b/);
  if (abbrMatch && US_STATES[abbrMatch[1]]) state = abbrMatch[1];
  if (!state) for (const [fn,ab] of Object.entries(ST_REV)) if (low.includes(fn)) { state = ab; break; }
  const parts = raw.split(",").map(s=>s.trim());
  let city = parts[0];
  if (HUBS[city] && !state) state = HUBS[city];
  return { display:raw, city, state, isRemote:false, isUS: isUS||!!state };
}

/* ═══ Experience & Sponsorship ═══ */
function expOf(title) {
  const t = (title||"").toLowerCase();
  if (/principal|distinguished|fellow/.test(t)) return "Principal";
  if (/\bstaff\b/.test(t)) return "Staff";
  if (/\blead\b|director|head of/.test(t)) return "Lead";
  if (/senior|sr\b/.test(t)) return "Senior";
  if (/junior|jr\b|associate|entry|intern/.test(t)) return "Entry";
  return "Mid";
}
function likelySponsor(job) {
  const text = ((job.description||"")+" "+(job.company||"")).toLowerCase();
  if (/no sponsorship|not sponsor|unable to sponsor|citizen only/.test(text)) return false;
  if (/visa sponsor|h1b|h-1b|sponsorship available/.test(text)) return true;
  return ["uber","meta","google","amazon","apple","microsoft","netflix","stripe","anthropic","openai","datadog","snowflake","databricks","two sigma","citadel","bloomberg","capital one","palantir","coinbase"].includes((job.company||"").toLowerCase());
}

/* ═══ Data hook — dual source ═══ */
const RENDER_API = import.meta.env.VITE_RENDER_URL || "";
const STATIC_URL = "./api-data.json";

function useJobData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [source, setSource] = useState(null);
  const [health, setHealth] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const m = useRef(true);
  const fetchData = useCallback(async () => {
    if (RENDER_API) { try {
      const r = await fetch(`${RENDER_API}/api/data`,{cache:"no-cache",signal:AbortSignal.timeout(8000)});
      if (r.ok) { const j = await r.json(); if (m.current && j.jobs?.length>0) { setData(j);setSource("render");setLastUpdated(j.exported_at||null);setLoading(false);setError(null);return; } }
    } catch(e) { console.log("Render unavailable:",e.message); } }
    try { const r = await fetch(STATIC_URL,{cache:"no-cache"}); if (!r.ok) throw new Error(`HTTP ${r.status}`); const j = await r.json();
      if (m.current) { setData(j);setSource(RENDER_API?"static":"static-only");setLastUpdated(j.exported_at||null);setLoading(false);setError(null); }
    } catch(e) { if (m.current) { setError(e.message);setLoading(false); } }
  }, []);
  const fetchHealth = useCallback(async () => {
    if (!RENDER_API) return;
    try { const r = await fetch(`${RENDER_API}/api/health`,{signal:AbortSignal.timeout(5000)}); if (r.ok && m.current) setHealth(await r.json()); } catch { if (m.current) setHealth(null); }
  }, []);
  useEffect(() => { m.current=true; fetchData(); fetchHealth();
    const d=setInterval(fetchData,2*60*1000), h=setInterval(fetchHealth,30*1000);
    return () => { m.current=false;clearInterval(d);clearInterval(h); };
  }, [fetchData, fetchHealth]);
  return { data,loading,error,source,health,lastUpdated };
}

/* ═══ Helpers ═══ */
const fmtSal = n => n ? `$${(n/1000).toFixed(0)}K` : "\u2014";
const timeAgo = iso => { if (!iso) return ""; const mins=Math.floor((Date.now()-new Date(iso).getTime())/60000);
  if (mins<1) return "just now"; if (mins<60) return `${mins}m ago`; if (mins<1440) return `${Math.floor(mins/60)}h ago`; return `${Math.floor(mins/1440)}d ago`; };
const Pill = ({ch,c,t,big}) => <span style={{display:"inline-block",fontSize:big?14:13,fontWeight:600,padding:big?"5px 12px":"4px 10px",borderRadius:6,background:`${c||t.ac}14`,color:c||t.ac,whiteSpace:"nowrap"}}>{ch}</span>;

/* ═══ Sorted chips — preferred items float to top with a star ═══ */
function Chips({options,selected,onChange,t,label,pinned}) {
  const sorted = useMemo(() => {
    if (!pinned?.length) return options;
    const pinSet = new Set(pinned);
    const top = options.filter(o => pinSet.has(o.id));
    const rest = options.filter(o => !pinSet.has(o.id));
    return [...top, ...rest];
  }, [options, pinned]);

  return <div style={{display:"flex",flexDirection:"column",gap:7}}>
    {label && <span style={{fontSize:12,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".06em"}}>{label}</span>}
    <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
      {sorted.map(o => { const on=selected.includes(o.id); const isPinned = pinned?.includes(o.id); return (
        <button key={o.id} onClick={()=>onChange(on?selected.filter(s=>s!==o.id):[...selected,o.id])}
          style={{padding:"7px 14px",borderRadius:8,border:`1.5px solid ${on?t.ac:isPinned?t.wm+"60":t.bd}`,
            background:on?t.acL:isPinned?t.wmL+"40":"transparent",
            color:on?t.ac:t.txS,fontSize:13,fontWeight:on?700:isPinned?600:400,cursor:"pointer",fontFamily:"inherit",transition:"all .15s"}}>
          {isPinned && !on ? "★ " : ""}{o.label}{o.count!=null?` (${o.count})`:""}
        </button>);
      })}
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════
   MAIN DASHBOARD
   ═══════════════════════════════════════════════════════════════════ */
export default function App() {
  const [mode,setMode] = useState("light");
  const t = TH[mode];
  const {data,loading,error,source,health,lastUpdated} = useJobData();
  const [tab,setTab] = useState("jobs");
  const [xJ,setXJ] = useState(null);

  // Filters
  const [q,sQ] = useState("");
  const [selRoles,setSelRoles] = useState([]);
  const [selExp,setSelExp] = useState([]);
  const [selStates,setSelStates] = useState([]);
  const [selCities,setSelCities] = useState([]);
  const [selATS,setSelATS] = useState([]);
  const [selSalary,setSelSalary] = useState("All");
  const [selPosted,setSelPosted] = useState("All");
  const [remoteOnly,setRemoteOnly] = useState(false);
  const [h1bOnly,setH1bOnly] = useState(false);
  const [showFilters,setShowFilters] = useState(false);
  const [so,sSo] = useState("relevance");
  const [cq,sCq] = useState("");

  const allJobs = data?.jobs||[];
  const stats = data?.stats||{};
  const dist = data?.distributions||{};

  // Enrich
  const enriched = useMemo(() => allJobs.map(j => ({...j,
    _loc:normLoc(j.location,j.is_remote), _cat:catOf(j.title), _exp:expOf(j.title),
  })), [allJobs]);

  // Filter options
  const opts = useMemo(() => {
    const rc={},sc={},cc={},ac={},ec={};
    enriched.forEach(j => {
      rc[j._cat]=(rc[j._cat]||0)+1;
      if (j._loc.state) sc[j._loc.state]=(sc[j._loc.state]||0)+1;
      const ck = j._loc.isRemote?"Remote":(j._loc.city&&j._loc.city!=="Unknown"?j._loc.city:null);
      if (ck) cc[ck]=(cc[ck]||0)+1;
      ac[j.ats||"unknown"]=(ac[j.ats||"unknown"]||0)+1;
      ec[j._exp]=(ec[j._exp]||0)+1;
    });
    return {
      roles: ROLE_CATS.map(r=>({id:r.id,label:r.label,count:rc[r.id]||0})).filter(r=>r.count>0).concat(rc["other"]?[{id:"other",label:"Other",count:rc["other"]}]:[]),
      states: Object.entries(sc).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({id:k,label:`${US_STATES[k]||k} (${k})`,count:v})),
      cities: Object.entries(cc).sort((a,b)=>b[1]-a[1]).slice(0,30).map(([k,v])=>({id:k,label:k,count:v})),
      ats: Object.entries(ac).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({id:k,label:(ATS_META[k]||ATS_META.unknown).l,count:v})),
      exp: ["Entry","Mid","Senior","Staff","Lead","Principal"].filter(e=>ec[e]).map(e=>({id:e,label:e,count:ec[e]})),
    };
  }, [enriched]);

  // Apply filters
  const fj = useMemo(() => {
    let j = [...enriched];
    if (selRoles.length) j=j.filter(x=>selRoles.includes(x._cat));
    if (selExp.length) j=j.filter(x=>selExp.includes(x._exp));
    if (selStates.length) j=j.filter(x=>selStates.includes(x._loc.state)||(selStates.includes("Remote")&&x._loc.isRemote));
    if (selCities.length) j=j.filter(x=>selCities.includes(x._loc.city)||(selCities.includes("Remote")&&x._loc.isRemote));
    if (selATS.length) j=j.filter(x=>selATS.includes(x.ats));
    if (remoteOnly) j=j.filter(x=>x._loc.isRemote||x.is_remote);
    if (h1bOnly) j=j.filter(x=>x.sponsorship||likelySponsor(x));
    if (selSalary!=="All") { const mins={"$100K+":1e5,"$130K+":13e4,"$160K+":16e4,"$200K+":2e5,"$250K+":25e4}; j=j.filter(x=>(x.salary_max||0)>=(mins[selSalary]||0)); }
    if (selPosted!=="All") { const d={"24h":1,"3d":3,"7d":7,"14d":14,"30d":30}[selPosted]||9999; j=j.filter(x=>x.posted_at&&(Date.now()-new Date(x.posted_at).getTime())<d*864e5); }
    if (q) { const ql=q.toLowerCase(); j=j.filter(x=>((x.title||"")+(x.company||"")+(x.description||"")+(x.matched_skills||[]).join(" ")+(x.location||"")).toLowerCase().includes(ql)); }
    j.sort((a,b)=>so==="salary"?(b.salary_max||0)-(a.salary_max||0):so==="date"?new Date(b.posted_at||0)-new Date(a.posted_at||0):(b.relevance_score||0)-(a.relevance_score||0));
    return j;
  }, [enriched,selRoles,selExp,selStates,selCities,selATS,remoteOnly,h1bOnly,selSalary,selPosted,q,so]);

  const activeN = [selRoles,selStates,selCities,selATS,selExp].reduce((n,a)=>n+a.length,0)+(remoteOnly?1:0)+(h1bOnly?1:0)+(selSalary!=="All"?1:0)+(selPosted!=="All"?1:0);
  const clearAll = () => { setSelRoles([]);setSelExp([]);setSelStates([]);setSelCities([]);setSelATS([]);setRemoteOnly(false);setH1bOnly(false);setSelSalary("All");setSelPosted("All");sQ(""); };

  const iS={width:"100%",padding:"12px 16px",borderRadius:9,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:15,fontFamily:"'Source Sans 3',sans-serif",outline:"none",transition:"all .2s"};
  const selS={...iS,cursor:"pointer",maxWidth:170};
  const ttS={background:t.cd,border:`1px solid ${t.bd}`,borderRadius:8,fontSize:13,color:t.tx,boxShadow:t.sh};

  const SourceBadge = () => {
    const isLive=source==="render"; const color=isLive?t.ok:source==="static"?t.wm:t.txM;
    return <div style={{display:"flex",alignItems:"center",gap:7,fontSize:13,color:t.txM}}>
      <div style={{width:8,height:8,borderRadius:"50%",background:color,boxShadow:isLive?`0 0 8px ${color}`:"none",animation:isLive?"pulse 2s infinite":"none"}}/>
      <span style={{fontWeight:600}}>{isLive?"Live":"Static"}</span>
      {lastUpdated && <span style={{opacity:.7}}>· {timeAgo(lastUpdated)}</span>}
    </div>;
  };

  /* Loading / Error / Empty */
  if (loading) return <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif"}}><div style={{textAlign:"center"}}><BrandLogo size={56} t={t}/><div style={{fontSize:18,color:t.txS,marginTop:14,animation:"pulse 1.5s infinite"}}>Loading jobs...</div></div></div>;
  if (error && !data) return <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif"}}><div style={{textAlign:"center",maxWidth:480,padding:36}}><BrandLogo size={56} t={t}/><h2 style={{fontSize:26,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif",margin:"16px 0 10px"}}>Setting Up</h2><p style={{fontSize:16,color:t.txS,lineHeight:1.7}}>Run your first scrape:</p><code style={{display:"block",background:t.bgS,padding:18,borderRadius:10,fontSize:15,color:t.ac,marginTop:14,textAlign:"left",lineHeight:2.2}}>cd backend<br/>pip install -r requirements.txt<br/>python main.py --fast</code></div></div>;
  if (allJobs.length===0) return <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif"}}><div style={{textAlign:"center",maxWidth:480,padding:36}}><BrandLogo size={56} t={t}/><h2 style={{fontSize:26,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif",margin:"16px 0 10px"}}>No Jobs Yet</h2><p style={{fontSize:16,color:t.txS}}>Waiting for scraper data.</p><div style={{marginTop:16}}><SourceBadge/></div></div></div>;

  const TABS=["jobs","analytics","companies","trends","monitor"];

  return <div style={{minHeight:"100vh",background:t.bg,fontFamily:"'Source Sans 3',sans-serif",color:t.tx,fontSize:16}}>
    {/* ═══ NAV ═══ */}
    <nav style={{position:"sticky",top:0,zIndex:50,background:t.nav,backdropFilter:"blur(20px)",borderBottom:`1px solid ${t.bd}`,padding:"16px 30px",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
      <div style={{display:"flex",alignItems:"center",gap:14}}>
        <BrandLogo size={34} t={t}/>
        <h1 style={{fontSize:26,fontWeight:700,color:t.ac,fontFamily:"'Playfair Display',serif",margin:0,letterSpacing:"-0.02em"}}>JobScout</h1>
        <SourceBadge/>
      </div>
      <div style={{display:"flex",alignItems:"center",gap:10}}>
        {TABS.map(tb=><button key={tb} onClick={()=>setTab(tb)} style={{padding:"9px 18px",borderRadius:8,border:"none",background:tab===tb?t.gP:"transparent",color:tab===tb?"#fff":t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit",textTransform:"capitalize",transition:"all .15s"}}>{tb==="monitor"?"🖥 Monitor":tb}</button>)}
        <button onClick={()=>setMode(m=>m==="light"?"dark":"light")} style={{padding:"9px 16px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:16,cursor:"pointer"}}>{mode==="light"?"🌙":"☀️"}</button>
      </div>
    </nav>

    <div style={{maxWidth:1320,margin:"0 auto",padding:"22px 28px"}}>
      {/* ═══ STATS ═══ */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(6,1fr)",gap:14,marginBottom:24}}>
        {[[stats.total_jobs||0,"Total Jobs",t.ac],[stats.high_match||0,"High Match",t.ok],[`${stats.remote_pct||0}%`,"Remote",t.bl],[stats.avg_salary?fmtSal(stats.avg_salary):"\u2014","Avg Salary",t.wm],[`${stats.h1b_pct||0}%`,"H1B Sponsors",t.vi],[stats.companies_tracked||0,"Companies",t.acS]].map(([v,l,c])=>
          <div key={l} style={{background:t.cd,borderRadius:12,padding:"18px 14px",textAlign:"center",border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
            <div style={{fontSize:30,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{v}</div>
            <div style={{fontSize:12,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".05em",marginTop:4}}>{l}</div>
          </div>
        )}
      </div>

      {/* ════════════ JOBS TAB ════════════ */}
      {tab==="jobs"&&<div>
        {/* Quick bar */}
        <div style={{display:"flex",gap:9,flexWrap:"wrap",marginBottom:14,alignItems:"center"}}>
          <input placeholder="Search jobs, skills, companies..." value={q} onChange={e=>sQ(e.target.value)} style={{...iS,maxWidth:320}}/>
          <button onClick={()=>setRemoteOnly(r=>!r)} style={{padding:"10px 16px",borderRadius:8,border:`1.5px solid ${remoteOnly?t.ac:t.bd}`,background:remoteOnly?t.acL:"transparent",color:remoteOnly?t.ac:t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>🏠 Remote</button>
          <button onClick={()=>setH1bOnly(r=>!r)} style={{padding:"10px 16px",borderRadius:8,border:`1.5px solid ${h1bOnly?t.vi:t.bd}`,background:h1bOnly?`${t.vi}12`:"transparent",color:h1bOnly?t.vi:t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>🛂 H1B</button>
          <select value={selPosted} onChange={e=>setSelPosted(e.target.value)} style={selS}><option value="All">📅 Any Time</option><option value="24h">Last 24h</option><option value="3d">Last 3 days</option><option value="7d">Last 7 days</option><option value="14d">Last 14 days</option><option value="30d">Last 30 days</option></select>
          <select value={selSalary} onChange={e=>setSelSalary(e.target.value)} style={selS}><option value="All">💰 Any Salary</option><option value="$100K+">$100K+</option><option value="$130K+">$130K+</option><option value="$160K+">$160K+</option><option value="$200K+">$200K+</option><option value="$250K+">$250K+</option></select>
          <select value={so} onChange={e=>sSo(e.target.value)} style={selS}><option value="relevance">↓ Relevance</option><option value="salary">↓ Salary</option><option value="date">↓ Newest</option></select>
          <button onClick={()=>setShowFilters(f=>!f)} style={{padding:"10px 16px",borderRadius:8,border:`1.5px solid ${activeN?t.ac:t.bd}`,background:activeN?t.acL:"transparent",color:activeN?t.ac:t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>🎛 Filters{activeN?` (${activeN})`:""}</button>
          {activeN>0&&<button onClick={clearAll} style={{padding:"10px 14px",borderRadius:8,border:`1.5px solid ${t.er}30`,background:"transparent",color:t.er,fontSize:13,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>✕ Clear</button>}
          <span style={{fontSize:14,color:t.txM,marginLeft:"auto",fontWeight:600}}>{fj.length} of {allJobs.length}</span>
        </div>

        {/* Expanded filters */}
        {showFilters&&<div style={{background:t.cd,borderRadius:14,padding:22,border:`1px solid ${t.bd}`,marginBottom:18,display:"flex",flexDirection:"column",gap:18,boxShadow:t.shS}}>
          <Chips label="Role Category" options={opts.roles} selected={selRoles} onChange={setSelRoles} t={t}/>
          <Chips label="Experience Level" options={opts.exp} selected={selExp} onChange={setSelExp} t={t}/>
          <Chips label="State" options={opts.states} selected={selStates} onChange={setSelStates} t={t} pinned={PREFERRED_STATES}/>
          <Chips label="City / Tech Hub" options={opts.cities} selected={selCities} onChange={setSelCities} t={t} pinned={PREFERRED_CITIES}/>
          <Chips label="ATS Platform" options={opts.ats} selected={selATS} onChange={setSelATS} t={t}/>
        </div>}

        {/* Job cards */}
        <div style={{display:"flex",flexDirection:"column",gap:12}}>
          {fj.slice(0,60).map(j => {
            const sc=j.relevance_score||0, open=xJ===j.external_id, ats=ATS_META[j.ats]||ATS_META.unknown;
            const catLbl=ROLE_CATS.find(r=>r.id===j._cat)?.label||"Other";
            return <div key={j.external_id} onClick={()=>setXJ(open?null:j.external_id)} style={{background:t.cd,borderRadius:12,border:`1px solid ${t.bd}`,overflow:"hidden",cursor:"pointer",transition:"all .2s",boxShadow:open?t.sh:t.shS}}>
              <div style={{padding:"18px 22px",display:"flex",justifyContent:"space-between",alignItems:"center",gap:16}}>
                <div style={{display:"flex",alignItems:"center",gap:16,flex:1,minWidth:0}}>
                  <LogoImg name={j.company} size={42} t={t}/>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6,flexWrap:"wrap"}}>
                      <span style={{fontSize:18,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>{j.title}</span>
                      <Pill ch={catLbl} c={t.bl} t={t}/>
                      <Pill ch={`${ats.i} ${ats.l}`} c={ats.c} t={t}/>
                    </div>
                    <div style={{display:"flex",gap:14,fontSize:15,color:t.txS,flexWrap:"wrap"}}>
                      <span style={{fontWeight:700}}>{j.company}</span>
                      <span>{j._loc.display||"\u2014"}</span>
                      {j._loc.state&&<span style={{color:t.bl,fontWeight:600}}>📍 {j._loc.state}</span>}
                      {j._loc.isRemote&&<span style={{color:t.ok,fontWeight:700}}>🏠 Remote</span>}
                      {j.salary_max>0&&<span style={{color:t.wm,fontWeight:700}}>{fmtSal(j.salary_min)}–{fmtSal(j.salary_max)}</span>}
                      {j.posted_at&&<span style={{color:t.txM}}>{timeAgo(j.posted_at)}</span>}
                    </div>
                  </div>
                </div>
                <div style={{display:"flex",alignItems:"center",gap:12}}>
                  <div style={{width:56,height:56,borderRadius:12,display:"flex",alignItems:"center",justifyContent:"center",background:t.sBg(sc),flexShrink:0}}>
                    <span style={{fontSize:22,fontWeight:800,color:t.sTx(sc),fontFamily:"'Playfair Display',serif"}}>{(sc*100).toFixed(0)}</span>
                  </div>
                  <span style={{fontSize:20,color:t.txM,transform:open?"rotate(180deg)":"",transition:"transform .2s"}}>▾</span>
                </div>
              </div>
              {open&&<div style={{padding:"0 22px 18px",borderTop:`1px solid ${t.bd}`}}>
                <div style={{display:"flex",gap:6,flexWrap:"wrap",margin:"16px 0 12px"}}>
                  {(j.matched_skills||[]).map(s=><Pill key={s} ch={s} t={t} big/>)}
                  {(j.sponsorship||likelySponsor(j))&&<Pill ch="🛂 Likely H1B" c={t.vi} t={t} big/>}
                </div>
                {j.description&&<p style={{fontSize:15,color:t.txS,lineHeight:1.85,maxHeight:160,overflow:"hidden",margin:"12px 0"}}>{j.description.slice(0,700)}...</p>}
                <a href={j.url} target="_blank" rel="noopener noreferrer" onClick={e=>e.stopPropagation()} style={{display:"inline-block",padding:"12px 26px",borderRadius:9,background:t.gP,color:"#fff",fontSize:15,fontWeight:700,textDecoration:"none",marginTop:8,boxShadow:`0 3px 12px ${t.ac}30`,letterSpacing:".01em"}}>Apply →</a>
              </div>}
            </div>;
          })}
          {fj.length>60&&<div style={{textAlign:"center",padding:20,color:t.txM,fontSize:15}}>Showing 60 of {fj.length} — use filters to narrow</div>}
          {fj.length===0&&<div style={{textAlign:"center",padding:44,color:t.txM,fontSize:16}}>No jobs match. <button onClick={clearAll} style={{background:"none",border:"none",color:t.ac,cursor:"pointer",fontWeight:700,fontSize:16,fontFamily:"inherit",textDecoration:"underline"}}>Clear all filters</button></div>}
        </div>
      </div>}

      {/* ════════════ ANALYTICS ════════════ */}
      {tab==="analytics"&&<div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 18px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>ATS Distribution</h3>
          <ResponsiveContainer width="100%" height={260}><PieChart><Pie data={dist.ats||[]} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={3} stroke="none">
            {(dist.ats||[]).map((d,i)=><Cell key={i} fill={(ATS_META[d.name]||ATS_META.unknown).c} opacity={0.75}/>)}</Pie><Tooltip contentStyle={ttS}/></PieChart></ResponsiveContainer>
          <div style={{display:"flex",gap:12,flexWrap:"wrap",justifyContent:"center",marginTop:12}}>
            {(dist.ats||[]).map(d=>{const m=ATS_META[d.name]||ATS_META.unknown;return <span key={d.name} style={{fontSize:14,color:m.c,fontWeight:600}}>{m.i} {m.l}: {d.value}</span>;})}
          </div>
        </div>
        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 18px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Salary Distribution</h3>
          <ResponsiveContainer width="100%" height={260}><BarChart data={dist.salary_buckets||[]}>
            <XAxis dataKey="range" tick={{fill:t.txM,fontSize:12}} axisLine={{stroke:t.bd}} tickLine={false}/>
            <YAxis tick={{fill:t.txM,fontSize:12}} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Bar dataKey="count" radius={[6,6,0,0]}>{(dist.salary_buckets||[]).map((d,i)=><Cell key={i} fill={[t.wm,t.wm,t.acS,t.ok,t.ac,t.vi][i]||t.ac} opacity={0.6}/>)}</Bar>
          </BarChart></ResponsiveContainer>
        </div>
        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 18px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>30-Day Trend</h3>
          <ResponsiveContainer width="100%" height={260}><AreaChart data={data?.trend||[]}>
            <XAxis dataKey="date" tick={{fill:t.txM,fontSize:12}} axisLine={{stroke:t.bd}} tickLine={false} tickFormatter={v=>v.slice(5)}/>
            <YAxis tick={{fill:t.txM,fontSize:12}} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
          </AreaChart></ResponsiveContainer>
        </div>
        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 18px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Breakdown</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
            {[[`${stats.h1b_pct||0}%`,"H1B Sponsors",t.vi],[`${stats.remote_pct||0}%`,"Remote",t.ok],[`${stats.companies_tracked||0}`,"Companies",t.ac],[`${stats.high_match||0}`,"High Match",t.wm]].map(([v,l,c])=>
              <div key={l} style={{padding:20,borderRadius:12,background:`${c}08`,border:`1px solid ${c}20`,textAlign:"center"}}>
                <div style={{fontSize:38,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{v}</div>
                <div style={{fontSize:13,color:t.txM,marginTop:4}}>{l}</div>
              </div>)}
          </div>
        </div>
      </div>}

      {/* ════════════ COMPANIES ════════════ */}
      {tab==="companies"&&<div>
        <div style={{marginBottom:18}}><input placeholder="Search companies..." value={cq} onChange={e=>sCq(e.target.value)} style={{...iS,maxWidth:360}}/></div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(320px,1fr))",gap:16}}>
          {(data?.top_companies||[]).filter(c=>!cq||c.name.toLowerCase().includes(cq.toLowerCase())).map(co=>
            <div key={co.name} style={{background:t.cd,borderRadius:14,padding:22,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
                <div style={{display:"flex",alignItems:"center",gap:14}}>
                  <LogoImg name={co.name} size={38} t={t}/>
                  <h4 style={{margin:0,fontSize:18,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>{co.name}</h4>
                </div>
                <div style={{background:t.acL,padding:"6px 14px",borderRadius:8}}>
                  <span style={{fontSize:18,fontWeight:700,color:t.ac}}>{co.count}</span>
                  <span style={{fontSize:12,color:t.txM,marginLeft:6}}>jobs</span>
                </div>
              </div>
              <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                {enriched.filter(j=>j.company===co.name).slice(0,4).map((j,i)=>
                  <span key={i} style={{fontSize:13,padding:"4px 11px",borderRadius:6,background:t.bgS,color:t.txS,border:`1px solid ${t.bd}`}}>{j.title}</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>}

      {/* ════════════ TRENDS ════════════ */}
      {tab==="trends"&&<div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:16}}>
        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 18px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Jobs by Date</h3>
          <ResponsiveContainer width="100%" height={300}><AreaChart data={data?.trend||[]}>
            <XAxis dataKey="date" tick={{fill:t.txM,fontSize:12}} axisLine={{stroke:t.bd}} tickLine={false} tickFormatter={v=>v.slice(5)}/>
            <YAxis tick={{fill:t.txM,fontSize:12}} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/><Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
          </AreaChart></ResponsiveContainer>
        </div>
        <div style={{display:"flex",flexDirection:"column",gap:16}}>
          <div style={{background:t.cd,borderRadius:14,padding:22,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1}}>
            <h3 style={{margin:"0 0 16px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Top Companies</h3>
            {(data?.top_companies||[]).slice(0,8).map((co,i)=>
              <div key={co.name} style={{display:"flex",alignItems:"center",gap:12,padding:"10px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none"}}>
                <LogoImg name={co.name} size={24} t={t}/>
                <span style={{fontSize:15,fontWeight:600,color:t.tx,flex:1}}>{co.name}</span>
                <span style={{fontSize:15,fontWeight:700,color:t.ac}}>{co.count}</span>
              </div>)}
          </div>
          <div style={{background:t.cd,borderRadius:14,padding:22,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1}}>
            <h3 style={{margin:"0 0 16px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Top Locations</h3>
            {(dist.cities||[]).slice(0,8).map((c,i)=>
              <div key={c.name} style={{display:"flex",justifyContent:"space-between",padding:"10px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none"}}>
                <span style={{fontSize:15,fontWeight:600,color:t.tx}}>{c.name}</span>
                <span style={{fontSize:15,fontWeight:700,color:t.acS}}>{c.value}</span>
              </div>)}
          </div>
        </div>
      </div>}

      {/* ════════════ MONITOR ════════════ */}
      {tab==="monitor"&&<div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 20px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>System Health</h3>
          <div style={{display:"flex",flexDirection:"column",gap:4}}>
            <MRow l="Data Source" v={source==="render"?"🟢 Render (Live)":source==="static"?"🟡 Static":"Static Only"} c={source==="render"?t.ok:t.wm} t={t}/>
            <MRow l="Last Refresh" v={lastUpdated?timeAgo(lastUpdated):"\u2014"} c={t.ac} t={t}/>
            {health&&<>
              <MRow l="Server Status" v={health.status==="idle"?"✅ Idle":"⏳ Scraping..."} c={health.status==="scraping"?t.wm:t.ok} t={t}/>
              <MRow l="Uptime" v={`${health.uptime_hours||0} hours`} c={t.ac} t={t}/>
              <MRow l="Total Cycles" v={health.total_cycles||0} c={t.ac} t={t}/>
              <MRow l="New Jobs Found" v={health.total_new_jobs||0} c={t.ok} t={t}/>
              <MRow l="Scrape Duration" v={`${health.last_duration_sec||0}s`} c={t.ac} t={t}/>
              <MRow l="Scan Interval" v={`${(health.fast_interval_sec||300)/60} min`} c={t.ac} t={t}/>
              <MRow l="Companies" v={health.companies_tracked||0} c={t.ac} t={t}/>
              {health.last_error&&<MRow l="Last Error" v={health.last_error} c={t.er} t={t}/>}
            </>}
            {!health&&RENDER_API&&<div style={{fontSize:15,color:t.txM,padding:"14px 0"}}>Render not responding — may be cold starting (~30s).</div>}
          </div>
        </div>

        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 20px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Pipeline Status</h3>
          <div style={{display:"flex",flexDirection:"column",gap:16}}>
            <Chk done={!!RENDER_API} label="Render URL configured" detail={RENDER_API||"Set VITE_RENDER_URL in .env"} t={t}/>
            <Chk done={source==="render"} label="Render API responding" detail={source==="render"?"Live data flowing":"Using static fallback"} t={t}/>
            <Chk done={!!health} label="Health endpoint reachable" detail={health?`${health.total_cycles} cycles completed`:"Waiting..."} t={t}/>
            <Chk done={health?.total_cycles>0} label="First scrape completed" detail={health?.last_scrape_at?`Last: ${timeAgo(health.last_scrape_at)}`:"Pending"} t={t}/>
            <Chk done={allJobs.length>0} label="Jobs flowing to dashboard" detail={`${allJobs.length} jobs loaded`} t={t}/>
          </div>
          <div style={{marginTop:22,padding:16,background:t.bgS,borderRadius:10,border:`1px solid ${t.bd}`}}>
            <div style={{fontSize:12,fontWeight:700,color:t.txM,marginBottom:10,textTransform:"uppercase",letterSpacing:".06em"}}>Data Flow</div>
            <div style={{fontSize:14,color:t.txS,lineHeight:2.2}}>
              <span style={{color:t.ok}}>●</span> Render: Tier 1 (24 cos) → every 5 min<br/>
              <span style={{color:t.wm}}>●</span> Actions: all 109 → every 2 hours<br/>
              <span style={{color:t.bl}}>●</span> Dashboard auto-refresh → every 2 min
            </div>
          </div>
        </div>

        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 20px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Data Summary</h3>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
            {[[allJobs.length,"Total Jobs",t.ac],[opts.roles.length,"Role Categories",t.bl],[opts.states.length,"US States",t.vi],[opts.cities.length,"Cities",t.wm],
              [enriched.filter(j=>j._loc.isRemote).length,"Remote Jobs",t.ok],[enriched.filter(j=>j.sponsorship||likelySponsor(j)).length,"H1B Likely",t.vi],
              [(data?.top_companies||[]).length,"Active Companies",t.ac],[opts.ats.length,"ATS Platforms",t.acS]].map(([v,l,c])=>
              <div key={l} style={{padding:14,borderRadius:10,background:`${c}08`,border:`1px solid ${c}15`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <span style={{fontSize:14,color:t.txS}}>{l}</span>
                <span style={{fontSize:20,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{v}</span>
              </div>)}
          </div>
        </div>

        <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
          <h3 style={{margin:"0 0 20px",fontSize:14,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Recent Scrape Runs</h3>
          {(data?.runs||[]).length===0
            ?<div style={{padding:22,textAlign:"center",color:t.txM,fontSize:15}}>No history yet</div>
            :<div style={{display:"flex",flexDirection:"column",gap:8}}>
              {(data?.runs||[]).slice(0,10).map((r,i)=>
                <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"10px 0",borderBottom:`1px solid ${t.bd}`,fontSize:14}}>
                  <div style={{display:"flex",gap:14,alignItems:"center"}}>
                    <span style={{color:r.status==="completed"?t.ok:t.er,fontWeight:600}}>{r.status==="completed"?"✅":"❌"}</span>
                    <span style={{color:t.txS}}>{r.started_at?timeAgo(r.started_at):"\u2014"}</span>
                  </div>
                  <div style={{display:"flex",gap:16,color:t.txM}}>
                    {r.companies_scraped&&<span>{r.companies_scraped} cos</span>}
                    {r.new_jobs!=null&&<span style={{color:t.ok,fontWeight:600}}>+{r.new_jobs} new</span>}
                    {(r.errors||0)>0&&<span style={{color:t.er}}>{r.errors} err</span>}
                    {r.duration_sec&&<span>{r.duration_sec}s</span>}
                  </div>
                </div>)}
            </div>}
        </div>
      </div>}
    </div>

    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;800&family=Source+Sans+3:wght@300;400;500;600;700&display=swap');
      *{box-sizing:border-box;margin:0} html{font-size:16px} body{font-size:16px}
      ::-webkit-scrollbar{width:8px}::-webkit-scrollbar-track{background:${t.bgS}}::-webkit-scrollbar-thumb{background:${t.acS};border-radius:4px}
      ::selection{background:${t.acL};color:${t.ac}}
      input:focus,select:focus{border-color:${t.acS}!important;box-shadow:0 0 0 3px ${t.ac}12!important}
      @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    `}</style>
  </div>;
}

/* ═══ Monitor helpers ═══ */
function MRow({l,v,c,t}) {
  return <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"10px 0",borderBottom:`1px solid ${t.bd}`}}>
    <span style={{fontSize:15,color:t.txM,fontWeight:500}}>{l}</span>
    <span style={{fontSize:15,fontWeight:600,color:c}}>{v}</span>
  </div>;
}
function Chk({done,label,detail,t}) {
  return <div style={{display:"flex",alignItems:"flex-start",gap:12}}>
    <span style={{fontSize:18,marginTop:1}}>{done?"✅":"⬜"}</span>
    <div><div style={{fontSize:15,fontWeight:600,color:done?t.ok:t.txM}}>{label}</div>
    <div style={{fontSize:13,color:t.txM,marginTop:3}}>{detail}</div></div>
  </div>;
}
