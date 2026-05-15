import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area } from "recharts";

/* ═══ Theme ═══════════════════════════════════════════════════════════ */
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

const ATS_META = {
  greenhouse:      {l:"Greenhouse",    c:"#3D8B6E",i:"🌿"},
  lever:           {l:"Lever",         c:"#6B5B8D",i:"⚡"},
  ashby:           {l:"Ashby",         c:"#C0776E",i:"💎"},
  smartrecruiters: {l:"SmartRecr.",    c:"#5B7B8D",i:"🎯"},
  bamboohr:        {l:"BambooHR",      c:"#73B761",i:"🎋"},
  workday:         {l:"Workday",       c:"#E86339",i:"💼"},
  unknown:         {l:"Other",         c:"#7A7A7A",i:"📄"},
};

/* ═══ Dream-company set + company aliases ═══ */
const DREAM_COMPANIES_SET = new Set([
  "anthropic","openai","stripe","databricks","snowflake","goldman sachs","walmart",
  "apple","nvidia","google","microsoft","disney","citadel","aqr","hrt",
  "hudson river trading","netflix","meta","spotify","fidelity","uber","bloomberg",
  "grubhub","doordash","amazon","salesforce","jp morgan chase","two sigma",
]);
// Common abbreviations → full company name (lowercase)
const COMPANY_ALIASES = {
  "gs":"goldman sachs","goldman":"goldman sachs",
  "jpmc":"jp morgan chase","jpm":"jp morgan chase","chase":"jp morgan chase",
  "msft":"microsoft",
  "goog":"google","googl":"google",
  "fb":"meta","fbk":"meta",
  "amzn":"amazon",
  "aapl":"apple",
  "nvda":"nvidia","nv":"nvidia",
  "hrt":"hudson river trading",
  "tsla":"tesla",
  "ubs":"ubs",
};
// Target role keywords for boosting in sort
const TARGET_ROLE_KW = [
  "data engineer","ml engineer","ai engineer","analytics engineer",
  "analytical engineer","data platform","mlops engineer",
];
// Resume version presets for the tracker
const RESUME_VERSIONS = ["_DE","_data","_SWE","_SE","_AE","_AI","_ML","standard","custom"];

/* ═══ Brand Logo — clean magnifying glass (Simplify-style minimal) ═══ */
function BrandLogo({ size = 32, t }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="JobScout">
      {/* Magnifying glass circle */}
      <circle cx="13" cy="13" r="9.5" stroke={t.ac} strokeWidth="2.5" fill="none"/>
      {/* Handle */}
      <line x1="20" y1="20" x2="28" y2="28" stroke={t.ac} strokeWidth="3" strokeLinecap="round"/>
      {/* Subtle crosshair inside */}
      <line x1="13" y1="7"  x2="13" y2="19" stroke={t.ac} strokeWidth="1" strokeLinecap="round" opacity="0.28"/>
      <line x1="7"  y1="13" x2="19" y2="13" stroke={t.ac} strokeWidth="1" strokeLinecap="round" opacity="0.28"/>
      {/* Center target dot */}
      <circle cx="13" cy="13" r="3" fill={t.ac}/>
    </svg>
  );
}

/* ═══ Company logo chain ═══ */
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
  "Goldman Sachs":"goldmansachs.com","Capital One":"capitalone.com","Walmart":"walmart.com",
  "Disney":"disney.com","Target":"target.com","Amex":"americanexpress.com","Deloitte":"deloitte.com",
  "Uber":"uber.com","Atlassian":"atlassian.com","Dropbox":"dropbox.com","Asana":"asana.com",
  "HubSpot":"hubspot.com","Zoom":"zoom.us","Amplitude":"amplitude.com","ClickHouse":"clickhouse.com",
};

function guessDomain(name) {
  if (!name) return null;
  const k = CO_DOMAINS[name];
  if (k) return k;
  return name.toLowerCase().replace(/[^a-z0-9]/g, "") + ".com";
}

function LogoImg({ name, size = 32, t }) {
  const [stage, setStage] = useState(0);
  const domain = guessDomain(name);
  if (!domain || stage >= 2) {
    const letter = (name || "?")[0].toUpperCase();
    const hue = [...(name||"")].reduce((h,c)=>h+c.charCodeAt(0),0) % 360;
    return (
      <div style={{width:size,height:size,borderRadius:8,background:`hsl(${hue},25%,92%)`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:size*0.44,fontWeight:800,color:`hsl(${hue},35%,40%)`,flexShrink:0,fontFamily:"system-ui,sans-serif"}}>
        {letter}
      </div>
    );
  }
  const srcs = [
    `https://www.google.com/s2/favicons?domain=${domain}&sz=${size*2}`,
    `https://logo.clearbit.com/${domain}?size=${size*2}`,
  ];
  return (
    <img src={srcs[stage]} alt="" width={size} height={size}
      style={{borderRadius:8,flexShrink:0,objectFit:"contain",background:"#fff",border:`1px solid ${t.bd}`}}
      onError={() => setStage(s => s + 1)}
    />
  );
}

/* ═══ Role categories ═══ */
const ROLE_CATS = [
  {id:"de",  label:"Data Engineer",   kw:["data engineer","etl engineer","data pipeline","data infrastructure","big data","analytics platform"]},
  {id:"ml",  label:"ML / AI",         kw:["ml engineer","machine learning","ai engineer","ai platform","mlops","llm","generative ai"]},
  {id:"ae",  label:"Analytics Eng",   kw:["analytics engineer","business intelligence","bi engineer","bi developer"]},
  {id:"ds",  label:"Data Scientist",  kw:["data scientist","research scientist","applied scientist"]},
  {id:"pe",  label:"Platform / Infra",kw:["platform engineer","infrastructure engineer","cloud engineer","devops","sre","site reliability"]},
  {id:"swe", label:"Software Eng",    kw:["software engineer","backend engineer","full stack","fullstack"]},
  {id:"da",  label:"Data Architect",  kw:["data architect","solutions architect"]},
];
function catOf(title) {
  const t = (title||"").toLowerCase();
  for (const c of ROLE_CATS) if (c.kw.some(k => t.includes(k))) return c.id;
  return "other";
}

/* ═══ Location ═══ */
const US_STATES={"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia"};
const ST_REV = Object.fromEntries(Object.entries(US_STATES).map(([k,v])=>[v.toLowerCase(),k]));
const HUBS={"San Francisco":"CA","San Jose":"CA","Palo Alto":"CA","Mountain View":"CA","Sunnyvale":"CA","Menlo Park":"CA","Cupertino":"CA","Santa Clara":"CA","Oakland":"CA","Redwood City":"CA","New York":"NY","Manhattan":"NY","Brooklyn":"NY","Seattle":"WA","Bellevue":"WA","Redmond":"WA","Austin":"TX","Dallas":"TX","Houston":"TX","Plano":"TX","Boston":"MA","Cambridge":"MA","Los Angeles":"CA","Santa Monica":"CA","Chicago":"IL","Denver":"CO","Boulder":"CO","Atlanta":"GA","Raleigh":"NC","Durham":"NC","Pittsburgh":"PA","Philadelphia":"PA","Portland":"OR","Salt Lake City":"UT","Miami":"FL","Washington":"DC","Arlington":"VA","McLean":"VA","San Diego":"CA","Irvine":"CA","Minneapolis":"MN","Detroit":"MI","Nashville":"TN"};
const REMOTE_WORDS=["remote","work from home","wfh","distributed","anywhere"];
const US_WORDS=["united states","usa","u.s.a.","u.s.","america"];
const PREFERRED_STATES=["TX","CA","NY","WA","CO","IL","GA","MA"];
const PREFERRED_CITIES=["Remote","Dallas","Austin","Plano","Houston","San Francisco","New York","Seattle"];

function normLoc(loc,isRemote){
  if(isRemote||(!loc&&isRemote))return{display:"Remote",city:"Remote",state:null,isRemote:true,isUS:true};
  if(!loc)return{display:"Unknown",city:null,state:null,isRemote:false,isUS:false};
  const raw=loc.trim(),low=raw.toLowerCase();
  if(REMOTE_WORDS.some(w=>low.includes(w)))return{display:"Remote",city:"Remote",state:null,isRemote:true,isUS:true};
  const isUS=US_WORDS.some(w=>low.includes(w))||/\b[A-Z]{2}\b/.test(raw);
  let state=null;
  const abbrM=raw.match(/\b([A-Z]{2})\b/);
  if(abbrM&&US_STATES[abbrM[1]])state=abbrM[1];
  if(!state)for(const[fn,ab]of Object.entries(ST_REV))if(low.includes(fn)){state=ab;break;}
  const parts=raw.split(",").map(s=>s.trim());
  let city=parts[0];
  if(HUBS[city]&&!state)state=HUBS[city];
  return{display:raw,city,state,isRemote:false,isUS:isUS||!!state};
}

function expOf(title){
  const t=(title||"").toLowerCase();
  if(/principal|distinguished|fellow/.test(t))return"Principal";
  if(/\bstaff\b/.test(t))return"Staff";
  if(/\blead\b|director|head of/.test(t))return"Lead";
  if(/senior|sr\b/.test(t))return"Senior";
  if(/junior|jr\b|associate|entry|intern/.test(t))return"Entry";
  return"Mid";
}

function likelySponsor(job){
  const text=((job.description||"")+" "+(job.company||"")).toLowerCase();
  if(/no sponsorship|not sponsor|unable to sponsor|citizen only/.test(text))return false;
  if(/visa sponsor|h1b|h-1b|sponsorship available/.test(text))return true;
  return["uber","meta","google","amazon","apple","microsoft","netflix","stripe","anthropic","openai","datadog","snowflake","databricks","two sigma","citadel","bloomberg","capital one","palantir","coinbase"].includes((job.company||"").toLowerCase());
}

/* ═══ Dream-company helpers ═══ */
function isDreamCo(company) {
  return DREAM_COMPANIES_SET.has((company||"").toLowerCase());
}
function isTargetRoleFn(title) {
  const t = (title||"").toLowerCase();
  return TARGET_ROLE_KW.some(kw => t.includes(kw));
}
function isSeniorFn(title) {
  return /senior|sr\b|staff\b|lead\b|principal|distinguished/i.test(title||"");
}

const isPlatinum = (job) => job?.tier === 'platinum';
const isHighComp = (job) => (job?.salary_max >= 220000) || isPlatinum(job);

/* ═══ Ranked search — alias-aware, with dream-company + role + seniority tiebreakers ═══
 *
 * Search quality tiers (primary sort):
 *   6 = exact title match
 *   5 = title starts with query
 *   4 = title contains query
 *   3 = company name or alias matches
 *   2 = matched skills
 *   1 = job description
 *
 * Within each tier the secondary ordering is:
 *   dream company first → target role first → senior+ first → relevance score
 *
 * Aliases: "GS" → Goldman Sachs, "Goldman" → Goldman Sachs,
 *          "JPMC"/"JPM"/"Chase" → JP Morgan Chase, "NVDA" → NVIDIA, etc.
 */
function searchRank(job, ql) {
  const title   = (job.title   || "").toLowerCase();
  const company = (job.company || "").toLowerCase();
  const skills  = (job.matched_skills || []).join(" ").toLowerCase();
  const desc    = (job.description || "").toLowerCase().slice(0, 600);
  // Expand alias: "GS" → "goldman sachs"
  const aliasExpanded = COMPANY_ALIASES[ql] || null;

  if (title === ql)                                                   return 6;
  if (title.startsWith(ql))                                          return 5;
  if (title.includes(ql))                                            return 4;
  if (company.includes(ql))                                          return 3;
  if (aliasExpanded && company.includes(aliasExpanded))              return 3; // alias hit
  if (skills.includes(ql))                                           return 2;
  if (desc.includes(ql))                                             return 1;
  return 0;
}

/* ═══ Data hook — dual source ═══ */
const RENDER_API = import.meta.env.VITE_RENDER_URL || "";
const STATIC_URL = "./api-data.json";

function useJobData() {
  const [data,setData]             = useState(null);
  const [loading,setLoading]       = useState(true);
  const [error,setError]           = useState(null);
  const [source,setSource]         = useState(null);
  const [health,setHealth]         = useState(null);
  const [lastUpdated,setLastUpdated] = useState(null);
  const m = useRef(true);

  const fetchData = useCallback(async () => {
    if (RENDER_API) {
      try {
        const r = await fetch(`${RENDER_API}/api/data`,{cache:"no-cache",signal:AbortSignal.timeout(8000)});
        if (r.ok) {
          const j = await r.json();
          if (m.current && j.jobs?.length > 0) {
            setData(j); setSource("render"); setLastUpdated(j.exported_at||null);
            setLoading(false); setError(null); return;
          }
        }
      } catch(e) { console.log("Render unavailable:",e.message); }
    }
    try {
      const r = await fetch(STATIC_URL,{cache:"no-cache"});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      if (m.current) {
        setData(j); setSource(RENDER_API?"static":"static-only");
        setLastUpdated(j.exported_at||null); setLoading(false); setError(null);
      }
    } catch(e) { if (m.current) { setError(e.message); setLoading(false); } }
  }, []);

  const fetchHealth = useCallback(async () => {
    if (!RENDER_API) return;
    try {
      const r = await fetch(`${RENDER_API}/api/health`,{signal:AbortSignal.timeout(5000)});
      if (r.ok && m.current) setHealth(await r.json());
    } catch { if (m.current) setHealth(null); }
  }, []);

  useEffect(() => {
    m.current = true;
    fetchData(); fetchHealth();
    const d = setInterval(fetchData, 2*60*1000);
    const h = setInterval(fetchHealth, 30*1000);
    return () => { m.current=false; clearInterval(d); clearInterval(h); };
  }, [fetchData, fetchHealth]);

  return { data, loading, error, source, health, lastUpdated, refetch: fetchData };
}

/* ═══ Application tracker — localStorage + optional Render API sync ═══ */
const LS_KEY = "jobscout_apps";
const ST_COLOR = {saved:"#4A7C9F",applied:"#3D8B6E",interview:"#C4A77D",offer:"#2D5A4A",rejected:"#B85450"};
const ST_LABEL = {saved:"🔖 Save",applied:"✅ Applied",interview:"📞 Interview",offer:"🎉 Offer",rejected:"✗ Pass"};

function useApplications() {
  const [apps, setApps] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
  });

  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(apps)); } catch {}
  }, [apps]);

  // Sync from Render API on mount if available
  useEffect(() => {
    if (!RENDER_API) return;
    fetch(`${RENDER_API}/api/applications`, {signal: AbortSignal.timeout(5000)})
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d?.applications) return;
        setApps(prev => {
          const m = {...prev};
          d.applications.forEach(a => { m[a.external_id] = a; });
          return m;
        });
      }).catch(() => {});
  }, []);

  const saveApp = useCallback((job, status = "saved") => {
    setApps(prev => {
      const now = new Date().toISOString();
      const ex = prev[job.external_id];
      const entry = {
        external_id: job.external_id,
        title: job.title, company: job.company, url: job.url || "",
        status, relevance_score: job.relevance_score || 0,
        salary_min: job.salary_min || 0, salary_max: job.salary_max || 0,
        location: job.location || "", notes: ex?.notes || "",
        saved_at: ex?.saved_at || now,
        applied_at: status === "applied" ? (ex?.applied_at || now) : (ex?.applied_at || null),
        updated_at: now,
      };
      if (RENDER_API) {
        fetch(`${RENDER_API}/api/applications`, {
          method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(entry),
        }).catch(() => {});
      }
      return {...prev, [job.external_id]: entry};
    });
  }, []);

  const removeApp = useCallback((extId) => {
    setApps(prev => { const n = {...prev}; delete n[extId]; return n; });
    if (RENDER_API) fetch(`${RENDER_API}/api/applications/${extId}`, {method:"DELETE"}).catch(()=>{});
  }, []);

  const updateField = useCallback((extId, field, value) => {
    setApps(prev => {
      if (!prev[extId]) return prev;
      const u = {...prev[extId], [field]: value, updated_at: new Date().toISOString()};
      if (RENDER_API) {
        fetch(`${RENDER_API}/api/applications`, {
          method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(u),
        }).catch(() => {});
      }
      return {...prev, [extId]: u};
    });
  }, []);

  return {apps, saveApp, removeApp, updateField};
}

/* ═══ Helpers ═══ */
const fmtSal = n => n ? `$${(n/1000).toFixed(0)}K` : "—";
const timeAgo = iso => {
  if (!iso) return "";
  const mins = Math.floor((Date.now()-new Date(iso).getTime())/60000);
  if (mins<1) return "just now"; if (mins<60) return `${mins}m ago`;
  if (mins<1440) return `${Math.floor(mins/60)}h ago`;
  return `${Math.floor(mins/1440)}d ago`;
};
const Pill = ({ch,c,t,big}) => (
  <span style={{display:"inline-block",fontSize:big?14:13,fontWeight:600,padding:big?"5px 12px":"4px 10px",borderRadius:6,background:`${c||t.ac}14`,color:c||t.ac,whiteSpace:"nowrap"}}>{ch}</span>
);

/* ═══ Chips filter component ═══ */
function Chips({options,selected,onChange,t,label,pinned}) {
  const sorted = useMemo(() => {
    if (!pinned?.length) return options;
    const ps = new Set(pinned);
    return [...options.filter(o=>ps.has(o.id)), ...options.filter(o=>!ps.has(o.id))];
  }, [options, pinned]);

  return (
    <div style={{display:"flex",flexDirection:"column",gap:7}}>
      {label && <span style={{fontSize:12,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".06em"}}>{label}</span>}
      <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
        {sorted.map(o => {
          const on = selected.includes(o.id);
          const isPinned = pinned?.includes(o.id);
          return (
            <button key={o.id} onClick={()=>onChange(on?selected.filter(s=>s!==o.id):[...selected,o.id])}
              style={{padding:"7px 14px",borderRadius:8,border:`1.5px solid ${on?t.ac:isPinned?t.wm+"60":t.bd}`,
                background:on?t.acL:isPinned?t.wmL+"40":"transparent",
                color:on?t.ac:t.txS,fontSize:13,fontWeight:on?700:isPinned?600:400,
                cursor:"pointer",fontFamily:"inherit",transition:"all .15s"}}>
              {isPinned&&!on?"★ ":""}{o.label}{o.count!=null?` (${o.count})`:""}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ═══ Monitor helpers ═══ */
function MRow({l,v,c,t}) {
  return (
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"10px 0",borderBottom:`1px solid ${t.bd}`}}>
      <span style={{fontSize:15,color:t.txM,fontWeight:500}}>{l}</span>
      <span style={{fontSize:15,fontWeight:600,color:c}}>{v}</span>
    </div>
  );
}
function Chk({done,label,detail,t}) {
  return (
    <div style={{display:"flex",alignItems:"flex-start",gap:12}}>
      <span style={{fontSize:18,marginTop:1}}>{done?"✅":"⬜"}</span>
      <div>
        <div style={{fontSize:15,fontWeight:600,color:done?t.ok:t.txM}}>{label}</div>
        <div style={{fontSize:13,color:t.txM,marginTop:3}}>{detail}</div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   MAIN DASHBOARD
   ═══════════════════════════════════════════════════════════════════ */
export default function App() {
  const [mode,setMode] = useState("light");
  const t = TH[mode];
  const {data,loading,error,source,health,lastUpdated,refetch} = useJobData();
  const [tab,setTab] = useState("jobs");
  const [xJ,setXJ] = useState(null);
  const [menuOpen,setMenuOpen] = useState(false);

  // Filters
  const [q,sQ]             = useState("");
  const [selRoles,setSelRoles]     = useState([]);
  const [selExp,setSelExp]         = useState([]);
  const [selStates,setSelStates]   = useState([]);
  const [selCities,setSelCities]   = useState([]);
  const [selATS,setSelATS]         = useState([]);
  const [selSalary,setSelSalary]   = useState("All");
  const [selPosted,setSelPosted]   = useState("All");
  const [remoteOnly,setRemoteOnly]       = useState(false);
  const [h1bOnly,setH1bOnly]             = useState(false);
  const [platinumOnly,setPlatinumOnly]   = useState(false);
  const [highCompOnly,setHighCompOnly]   = useState(false);
  const [showFilters,setShowFilters] = useState(false);
  const [so,sSo]           = useState("relevance");
  const [cq,sCq]           = useState("");

  // Application tracker
  const {apps, saveApp, removeApp, updateField} = useApplications();
  const [trackerFilter, setTrackerFilter]  = useState("All");
  const [editingNotes, setEditingNotes]    = useState(null);
  const [editingResume, setEditingResume]  = useState(null);

  // Resume Version Manager
  const [showResumeManager, setShowResumeManager] = useState(false);
  const [resumeVersions, setResumeVersions]       = useState([]);
  const [addingVersion, setAddingVersion]         = useState(false);
  const [rvForm, setRvForm]   = useState({version_key:"", display_name:"", resume_text:"", notes:""});
  const [rvResult, setRvResult] = useState(null);
  const [rvFile, setRvFile]     = useState(null);
  const [rvUploading, setRvUploading] = useState(false);
  const [compareA, setCompareA]   = useState("");
  const [compareB, setCompareB]   = useState("");
  const [compareResult, setCompareResult] = useState(null);

  // Pipeline kanban — API-backed application list
  const [applications, setApplications] = useState([]);
  const [appLoading, setAppLoading] = useState(false);

  // Manual scrape trigger + live progress polling (#19).
  // `scraping` reflects "we should keep polling the status endpoint" — set
  // when the POST returns 202 or 409, and cleared once snapshot.is_running
  // flips false. `scrapeProgress` is the latest snapshot from /api/scrape/status.
  const [scraping,setScraping]         = useState(false);
  const [scrapeMsg,setScrapeMsg]       = useState(null);
  const [scrapeProgress,setScrapeProgress] = useState(null);

  useEffect(() => {
    if (!scraping || !RENDER_API) return;
    let cancelled = false;
    const tick = async () => {
      // Skip polling while the tab is in the background — saves ~40 req/min
      // per backgrounded tab on a free-tier Render instance.
      if (typeof document !== "undefined" && document.hidden) return;
      try {
        const r = await fetch(`${RENDER_API}/api/scrape/status`,
                              { signal: AbortSignal.timeout(5000) });
        if (!r.ok) return;
        const snap = await r.json();
        if (cancelled) return;
        setScrapeProgress(snap);
        if (snap && snap.is_running === false) {
          setScraping(false);
          const s = snap.final_stats || {};
          const totals = `companies=${s.companies ?? snap.companies_done ?? "?"} · `
                       + `found=${s.found ?? snap.found ?? 0} · `
                       + `new=${s.new ?? snap.new ?? 0}`;
          setScrapeMsg(`✅ Scrape complete — ${totals}`);
        }
      } catch (_e) { /* transient — keep polling */ }
    };
    tick();
    const id = setInterval(tick, 1500);
    return () => { cancelled = true; clearInterval(id); };
  }, [scraping]);

  const triggerScrape = async () => {
    if (!RENDER_API) {
      setScrapeMsg("⚠️ No Render API configured. Set VITE_RENDER_URL in your .env file.");
      return;
    }
    setScrapeMsg(null);
    try {
      const resp = await fetch(`${RENDER_API}/api/scrape`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        signal: AbortSignal.timeout(12000),
      });
      // 202 (new run) and 409 (already running) both transition us into the
      // polling state — the snapshot endpoint is the single source of truth.
      if (resp.status === 202 || resp.status === 409) {
        const d = await resp.json().catch(() => ({}));
        if (d && d.snapshot) setScrapeProgress(d.snapshot);
        setScraping(true);
        if (resp.status === 202) setScrapeMsg("🚀 Scrape started — live progress below.");
        return;
      }
      const d = await resp.json().catch(() => ({}));
      setScrapeMsg(`❌ Error: ${d.error || resp.status}`);
    } catch(e) {
      setScrapeMsg(`❌ Could not reach Render: ${e.message}`);
    }
  };

  // Doctor health-check
  const [doctorLoading,setDoctorLoading] = useState(false);
  const [doctorResult,setDoctorResult]   = useState(null);
  const [doctorErr,setDoctorErr]         = useState(null);

  const runDoctor = async () => {
    if (!RENDER_API) {
      setDoctorErr("No Render API configured. Set VITE_RENDER_URL in your .env file.");
      return;
    }
    setDoctorLoading(true); setDoctorErr(null); setDoctorResult(null);
    try {
      const resp = await fetch(`${RENDER_API}/api/admin/doctor`, {
        signal: AbortSignal.timeout(15000),
      });
      const d = await resp.json();
      if (!resp.ok) {
        setDoctorErr(d.error || `HTTP ${resp.status}`);
      } else {
        setDoctorResult(d);
      }
    } catch(e) {
      setDoctorErr(`Could not reach Render: ${e.message}`);
    } finally {
      setDoctorLoading(false);
    }
  };

  // Re-extract skills across all resume_versions rows (#24)
  const [reextractLoading,setReextractLoading] = useState(false);
  const [reextractMsg,setReextractMsg]         = useState(null);

  const runReextract = async () => {
    if (!RENDER_API) {
      setReextractMsg({type:"err", text:"No Render API configured. Set VITE_RENDER_URL in your .env file."});
      return;
    }
    setReextractLoading(true); setReextractMsg(null);
    try {
      const resp = await fetch(`${RENDER_API}/api/admin/reextract-skills`, {
        method: "POST",
        signal: AbortSignal.timeout(60000),
      });
      const d = await resp.json();
      if (!resp.ok) {
        setReextractMsg({type:"err", text:d.error || `HTTP ${resp.status}`});
      } else {
        setReextractMsg({type:"ok",
          text:`✅ Updated ${d.updated}/${d.total} resume versions (${d.errors} errors)`});
      }
    } catch(e) {
      setReextractMsg({type:"err", text:`Could not reach Render: ${e.message}`});
    } finally {
      setReextractLoading(false);
    }
  };

  // Vault re-index from disk (#24)
  const [reindexLoading,setReindexLoading] = useState(false);
  const [reindexMsg,setReindexMsg]         = useState(null);

  const runReindex = async () => {
    if (!RENDER_API) {
      setReindexMsg({type:"err", text:"No Render API configured. Set VITE_RENDER_URL in your .env file."});
      return;
    }
    setReindexLoading(true); setReindexMsg(null);
    try {
      const resp = await fetch(`${RENDER_API}/api/admin/vault-reindex`, {
        method: "POST",
        signal: AbortSignal.timeout(60000),
      });
      const d = await resp.json();
      if (!resp.ok) {
        setReindexMsg({type:"err", text:d.error || `HTTP ${resp.status}`});
      } else {
        setReindexMsg({type:"ok",
          text:`✅ Indexed ${d.indexed} files in ${d.duration_ms}ms`});
      }
    } catch(e) {
      setReindexMsg({type:"err", text:`Could not reach Render: ${e.message}`});
    } finally {
      setReindexLoading(false);
    }
  };

  const fetchApplications = useCallback(async () => {
    setAppLoading(true);
    try {
      const base = RENDER_API;
      if (!base) return;
      const resp = await fetch(`${base}/api/applications`, {signal: AbortSignal.timeout(8000)});
      if (resp.ok) {
        const data = await resp.json();
        setApplications(Array.isArray(data) ? data : (data.applications || []));
      }
    } catch (e) {
      console.warn('Could not fetch applications:', e);
    } finally {
      setAppLoading(false);
    }
  }, []);

  useEffect(() => { fetchApplications(); }, [fetchApplications]);

  const fetchResumeVersions = useCallback(async () => {
    if (!RENDER_API) return;
    try {
      const r = await fetch(`${RENDER_API}/api/resume/versions`, {signal: AbortSignal.timeout(5000)});
      if (r.ok) setResumeVersions(await r.json());
    } catch {}
  }, []);

  const submitResumeVersion = async () => {
    if (!RENDER_API || !rvForm.version_key.trim()) return;
    setRvUploading(true);
    try {
      let r;
      if (rvFile) {
        // PDF upload path — use FormData
        const fd = new FormData();
        fd.append("file", rvFile);
        fd.append("version_key", rvForm.version_key);
        fd.append("display_name", rvForm.display_name || rvForm.version_key);
        fd.append("notes", rvForm.notes);
        r = await fetch(`${RENDER_API}/api/resume/versions/upload`, {method:"POST", body: fd});
      } else {
        // Text paste path — use JSON
        r = await fetch(`${RENDER_API}/api/resume/versions`, {
          method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(rvForm),
        });
      }
      const d = await r.json();
      if (r.ok) {
        const preview = d.skills.slice(0,5).join(", ") + (d.skills.length > 5 ? "…" : "");
        setRvResult({ok:true, msg:`✅ Saved! ${d.skills_extracted} skills found: ${preview}`});
        setRvForm({version_key:"", display_name:"", resume_text:"", notes:""});
        setRvFile(null);
        setAddingVersion(false);
        fetchResumeVersions();
      } else {
        setRvResult({ok:false, msg:`❌ ${d.error}`});
      }
    } catch(e) { setRvResult({ok:false, msg:`❌ ${e.message}`}); }
    finally { setRvUploading(false); }
  };

  const compareVersions = async () => {
    if (!RENDER_API || !compareA || !compareB || compareA === compareB) return;
    try {
      const r = await fetch(`${RENDER_API}/api/resume/versions/compare?a=${encodeURIComponent(compareA)}&b=${encodeURIComponent(compareB)}`);
      if (r.ok) setCompareResult(await r.json());
    } catch {}
  };

  const deleteResumeVersion = async (vk) => {
    if (!RENDER_API) return;
    try {
      await fetch(`${RENDER_API}/api/resume/versions/${encodeURIComponent(vk)}`, {method:"DELETE"});
      fetchResumeVersions();
    } catch {}
  };

  const allJobs = data?.jobs   || [];
  const stats   = data?.stats  || {};
  const dist    = data?.distributions || {};

  // Enrich jobs with derived fields. `_age_days` is computed from
  // effective_date (posted_at || first_seen_at, from the backend) and used by
  // the date filter AND the display-time relevance decay. Null when neither
  // field is set — those jobs are treated as age-unknown and slip through the
  // 30-day cap so we don't accidentally hide fresh ATS posts that lack dates.
  const enriched = useMemo(() => allJobs.map(j => {
    const eff = j.effective_date || j.posted_at || j.first_seen_at || "";
    let ageDays = null;
    if (eff) {
      const t = new Date(eff).getTime();
      if (!Number.isNaN(t)) {
        ageDays = Math.max(0, (Date.now() - t) / 864e5);
      }
    }
    // Display-only relevance: linear decay past day 14, floor at 0.5×.
    // Original relevance_score is preserved for tracker/applications usage.
    const base = j.relevance_score || 0;
    const decay = ageDays == null ? 1 : Math.max(0.5, 1 - Math.max(0, ageDays - 14) / 60);
    return {
      ...j,
      _loc: normLoc(j.location, j.is_remote),
      _cat: catOf(j.title),
      _exp: expOf(j.title),
      _age_days: ageDays,
      _display_score: base * decay,
    };
  }), [allJobs]);

  // Build company → applications map for "already applied here" intelligence
  const companyApps = useMemo(() => {
    const m = {};
    Object.values(apps).forEach(a => {
      const key = (a.company || "").toLowerCase();
      if (!m[key]) m[key] = [];
      m[key].push(a);
    });
    return m;
  }, [apps]);

  // Build filter option lists
  const opts = useMemo(() => {
    const rc={},sc={},cc={},ac={},ec={};
    enriched.forEach(j => {
      rc[j._cat]=(rc[j._cat]||0)+1;
      if (j._loc.state) sc[j._loc.state]=(sc[j._loc.state]||0)+1;
      const ck=j._loc.isRemote?"Remote":(j._loc.city&&j._loc.city!=="Unknown"?j._loc.city:null);
      if (ck) cc[ck]=(cc[ck]||0)+1;
      ac[j.ats||"unknown"]=(ac[j.ats||"unknown"]||0)+1;
      ec[j._exp]=(ec[j._exp]||0)+1;
    });
    return {
      roles:  ROLE_CATS.map(r=>({id:r.id,label:r.label,count:rc[r.id]||0})).filter(r=>r.count>0).concat(rc["other"]?[{id:"other",label:"Other",count:rc["other"]}]:[]),
      states: Object.entries(sc).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({id:k,label:`${US_STATES[k]||k} (${k})`,count:v})),
      cities: Object.entries(cc).sort((a,b)=>b[1]-a[1]).slice(0,30).map(([k,v])=>({id:k,label:k,count:v})),
      ats:    Object.entries(ac).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({id:k,label:(ATS_META[k]||ATS_META.unknown).l,count:v})),
      exp:    ["Entry","Mid","Senior","Staff","Lead","Principal"].filter(e=>ec[e]).map(e=>({id:e,label:e,count:ec[e]})),
    };
  }, [enriched]);

  // Apply filters + ranked search
  const fj = useMemo(() => {
    let j = [...enriched];
    if (selRoles.length) j = j.filter(x=>selRoles.includes(x._cat));
    if (selExp.length)   j = j.filter(x=>selExp.includes(x._exp));
    if (selStates.length) j=j.filter(x=>selStates.includes(x._loc.state)||(selStates.includes("Remote")&&x._loc.isRemote));
    if (selCities.length) j=j.filter(x=>selCities.includes(x._loc.city)||(selCities.includes("Remote")&&x._loc.isRemote));
    if (selATS.length)   j = j.filter(x=>selATS.includes(x.ats));
    if (remoteOnly)      j = j.filter(x=>x._loc.isRemote||x.is_remote);
    if (h1bOnly)         j = j.filter(x=>x.sponsorship||likelySponsor(x));
    if (platinumOnly)    j = j.filter(x=>isPlatinum(x));
    if (highCompOnly)    j = j.filter(x=>isHighComp(x));
    if (selSalary!=="All") {
      const mins={"$100K+":1e5,"$130K+":13e4,"$160K+":16e4,"$200K+":2e5,"$250K+":25e4};
      j = j.filter(x=>(x.salary_max||0)>=(mins[selSalary]||0));
    }
    if (selPosted!=="All") {
      const d={"24h":1,"3d":3,"7d":7,"14d":14,"30d":30}[selPosted]||9999;
      // Age uses effective_date (posted_at || first_seen_at). Jobs with no
      // date signal at all (_age_days === null) are excluded from explicit
      // recency filters — we can't honestly claim they're under 7 days old.
      j = j.filter(x => x._age_days != null && x._age_days < d);
    }
    // Hard recency cap: hide jobs older than 30 days unless they're platinum
    // tier (dream companies — keep them visible even if stale). Jobs with no
    // effective_date pass through (we don't know they're old).
    j = j.filter(x => x._age_days == null || x._age_days <= 30 || isPlatinum(x));

    if (q.trim()) {
      const ql = q.trim().toLowerCase();
      // Filter to only matching jobs (including alias hits)
      j = j.filter(x => searchRank(x, ql) > 0);
      // Multi-level sort:
      // 1. Search quality tier (6→1)
      // 2. Dream company first within same tier
      // 3. Target role (data/ml/ai engineer) first
      // 4. Senior+ first
      // 5. Relevance score as tiebreak
      j.sort((a,b) => {
        const aR = searchRank(a,ql), bR = searchRank(b,ql);
        if (bR !== aR) return bR - aR;
        const aDream = isDreamCo(a.company)?1:0, bDream = isDreamCo(b.company)?1:0;
        if (bDream !== aDream) return bDream - aDream;
        const aTarget = isTargetRoleFn(a.title)?1:0, bTarget = isTargetRoleFn(b.title)?1:0;
        if (bTarget !== aTarget) return bTarget - aTarget;
        const aSr = isSeniorFn(a.title)?1:0, bSr = isSeniorFn(b.title)?1:0;
        if (bSr !== aSr) return bSr - aSr;
        return (b._display_score||0)-(a._display_score||0);
      });
    } else {
      // Default browse: salary/date as selected, or relevance with dream-company boost
      j.sort((a,b) => {
        // Platinum always sorts first within any sort mode
        if (isPlatinum(a) && !isPlatinum(b)) return -1;
        if (!isPlatinum(a) && isPlatinum(b)) return 1;
        if (so==="salary") return (b.salary_max||0)-(a.salary_max||0);
        if (so==="date")   return new Date(b.effective_date||b.posted_at||0)-new Date(a.effective_date||a.posted_at||0);
        // Relevance sort: dream company gets +0.06 invisible boost so they surface first
        // among jobs with nearly identical scores. Uses the decayed display score
        // so stale jobs sink even when nominally scored identically to fresh ones.
        const aScore = (a._display_score||0) + (isDreamCo(a.company)?0.06:0)
                                               + (isTargetRoleFn(a.title)?0.03:0)
                                               + (isSeniorFn(a.title)?0.01:0);
        const bScore = (b._display_score||0) + (isDreamCo(b.company)?0.06:0)
                                               + (isTargetRoleFn(b.title)?0.03:0)
                                               + (isSeniorFn(b.title)?0.01:0);
        // Within a 0.05-wide score band, applied jobs drop to the bottom so
        // the user's eye lands on fresh roles first without losing context.
        const aBand = Math.floor(aScore * 20);
        const bBand = Math.floor(bScore * 20);
        if (aBand !== bBand) return bBand - aBand;
        const aApplied = a.application_status === 'applied' ? 1 : 0;
        const bApplied = b.application_status === 'applied' ? 1 : 0;
        if (aApplied !== bApplied) return aApplied - bApplied;
        return bScore - aScore;
      });
    }
    return j;
  }, [enriched,selRoles,selExp,selStates,selCities,selATS,remoteOnly,h1bOnly,platinumOnly,highCompOnly,selSalary,selPosted,q,so]);

  const activeN = [selRoles,selStates,selCities,selATS,selExp].reduce((n,a)=>n+a.length,0)
    +(remoteOnly?1:0)+(h1bOnly?1:0)+(platinumOnly?1:0)+(highCompOnly?1:0)+(selSalary!=="All"?1:0)+(selPosted!=="All"?1:0);
  const clearAll = () => {
    setSelRoles([]);setSelExp([]);setSelStates([]);setSelCities([]);
    setSelATS([]);setRemoteOnly(false);setH1bOnly(false);setPlatinumOnly(false);setHighCompOnly(false);
    setSelSalary("All");setSelPosted("All");sQ("");
  };

  const iS={width:"100%",padding:"12px 16px",borderRadius:9,border:`1px solid ${t.bd}`,background:t.inp,color:t.tx,fontSize:15,fontFamily:"'Source Sans 3',sans-serif",outline:"none"};
  const selS={...iS,cursor:"pointer",width:"auto",minWidth:130};
  const ttS={background:t.cd,border:`1px solid ${t.bd}`,borderRadius:8,fontSize:13,color:t.tx,boxShadow:t.sh};

  const SourceBadge = () => {
    const isLive=source==="render";
    const color=isLive?t.ok:source==="static"?t.wm:t.txM;
    return (
      <div style={{display:"flex",alignItems:"center",gap:6,fontSize:13,color:t.txM}}>
        <div style={{width:8,height:8,borderRadius:"50%",background:color,boxShadow:isLive?`0 0 8px ${color}`:"none",animation:isLive?"pulse 2s infinite":"none"}}/>
        <span style={{fontWeight:600}}>{isLive?"Live":"Static"}</span>
        {lastUpdated && <span style={{opacity:.7}}>· {timeAgo(lastUpdated)}</span>}
      </div>
    );
  };

  /* Loading / Error screens */
  if (loading) return (
    <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif"}}>
      <div style={{textAlign:"center"}}>
        <BrandLogo size={56} t={t}/>
        <div style={{fontSize:18,color:t.txS,marginTop:14,animation:"pulse 1.5s infinite"}}>Loading jobs...</div>
      </div>
    </div>
  );

  if (error && !data) return (
    <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif"}}>
      <div style={{textAlign:"center",maxWidth:480,padding:36}}>
        <BrandLogo size={56} t={t}/>
        <h2 style={{fontSize:26,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif",margin:"16px 0 10px"}}>Setting Up</h2>
        <p style={{fontSize:16,color:t.txS,lineHeight:1.7}}>Run your first scrape to populate the dashboard:</p>
        <code style={{display:"block",background:t.bgS,padding:18,borderRadius:10,fontSize:14,color:t.ac,marginTop:14,textAlign:"left",lineHeight:2.2}}>
          cd backend<br/>pip install -r requirements.txt<br/>python main.py --fast
        </code>
      </div>
    </div>
  );

  if (allJobs.length===0) return (
    <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:t.bg,fontFamily:"'Source Sans 3',sans-serif"}}>
      <div style={{textAlign:"center",maxWidth:480,padding:36}}>
        <BrandLogo size={56} t={t}/>
        <h2 style={{fontSize:26,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif",margin:"16px 0 10px"}}>No Jobs Yet</h2>
        <p style={{fontSize:16,color:t.txS}}>Waiting for scraper data.</p>
        <div style={{marginTop:16}}><SourceBadge/></div>
      </div>
    </div>
  );

  const trackerCount = Object.keys(apps).length;
  const TABS = ["jobs","rare","analytics","companies","trends","tracker","pipeline","monitor"];

  const PIPELINE_STAGES = [
    { key: 'saved',      label: 'Saved',        color: '#6b7280' },
    { key: 'applied',    label: 'Applied',      color: '#3b82f6' },
    { key: 'interview',  label: 'Phone Screen', color: '#f59e0b' },
    { key: 'offer',      label: 'Offer',        color: '#22c55e' },
    { key: 'rejected',   label: 'Rejected',     color: '#ef4444' },
  ];

  return (
    <div style={{minHeight:"100vh",background:t.bg,fontFamily:"'Source Sans 3',sans-serif",color:t.tx,fontSize:16}}>

      {/* ═══ NAV ═══ */}
      <nav style={{position:"sticky",top:0,zIndex:50,background:t.nav,backdropFilter:"blur(20px)",borderBottom:`1px solid ${t.bd}`}}>
        <div className="nav-wrap" style={{padding:"12px 24px"}}>
          {/* Logo + source */}
          <div style={{display:"flex",alignItems:"center",gap:12,flexShrink:0}}>
            <BrandLogo size={30} t={t}/>
            <h1 style={{fontSize:22,fontWeight:700,color:t.ac,fontFamily:"'Playfair Display',serif",margin:0,letterSpacing:"-0.02em"}}>JobScout</h1>
            <SourceBadge/>
          </div>
          {/* Tabs — horizontally scrollable on mobile */}
          <div className="nav-tabs">
            {TABS.map(tb => (
              <button key={tb} onClick={()=>{setTab(tb);setMenuOpen(false);}}
                style={{padding:"8px 16px",borderRadius:8,border:"none",
                  background:tab===tb?t.gP:"transparent",
                  color:tab===tb?"#fff":t.txM,
                  fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit",
                  textTransform:"capitalize",transition:"all .15s",flexShrink:0}}>
                {tb==="monitor"?"🖥 Monitor":tb==="tracker"?`📋 Tracker${trackerCount?" ("+trackerCount+")":""}`:tb==="pipeline"?`🗂 Pipeline${applications.length?" ("+applications.length+")":""}`:tb==="rare"?`🎯 Rare${stats.rare_skills?" ("+stats.rare_skills+")":""}`:tb}
              </button>
            ))}
          </div>
          {/* Theme toggle */}
          <button onClick={()=>setMode(m=>m==="light"?"dark":"light")}
            style={{padding:"8px 14px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:16,cursor:"pointer",flexShrink:0}}>
            {mode==="light"?"🌙":"☀️"}
          </button>
        </div>
      </nav>

      <div className="page-pad">

        {/* ═══ STATS ═══ */}
        <div className="stats-grid">
          {[
            [stats.total_jobs||0,       "Total Jobs",    t.ac],
            [stats.high_match||0,       "High Match",    t.ok],
            [`${stats.remote_pct||0}%`, "Remote",        t.bl],
            [stats.avg_salary?fmtSal(stats.avg_salary):"—","Avg Salary",t.wm],
            [stats.rare_skills||0,      "🎯 Rare Skills",t.vi],
            [stats.companies_tracked||0,"Companies",     t.acS],
          ].map(([v,l,c]) => (
            <div key={l} style={{background:t.cd,borderRadius:12,padding:"16px 12px",textAlign:"center",border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
              <div style={{fontSize:28,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{v}</div>
              <div style={{fontSize:11,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".05em",marginTop:4}}>{l}</div>
            </div>
          ))}
        </div>

        {/* ════════════ JOBS TAB ════════════ */}
        {tab==="jobs" && <div>
          {/* Filter bar */}
          <div className="filter-bar">
            <input placeholder="Search jobs, skills, companies..." value={q} onChange={e=>sQ(e.target.value)}
              style={{...iS,flex:"1 1 200px",maxWidth:340}}/>
            <button onClick={()=>setRemoteOnly(r=>!r)}
              style={{padding:"10px 14px",borderRadius:8,border:`1.5px solid ${remoteOnly?t.ac:t.bd}`,background:remoteOnly?t.acL:"transparent",color:remoteOnly?t.ac:t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
              🏠 Remote
            </button>
            <button onClick={()=>setH1bOnly(r=>!r)}
              style={{padding:"10px 14px",borderRadius:8,border:`1.5px solid ${h1bOnly?t.vi:t.bd}`,background:h1bOnly?`${t.vi}12`:"transparent",color:h1bOnly?t.vi:t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
              🛂 H1B
            </button>
            <button onClick={()=>setPlatinumOnly(r=>!r)}
              style={{padding:"10px 14px",borderRadius:8,border:`1.5px solid ${platinumOnly?"#b8860b":t.bd}`,background:platinumOnly?"#b8860b18":"transparent",color:platinumOnly?"#b8860b":t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
              ✦ Platinum
            </button>
            <button onClick={()=>setHighCompOnly(r=>!r)}
              style={{padding:"10px 14px",borderRadius:8,border:`1.5px solid ${highCompOnly?t.ok:t.bd}`,background:highCompOnly?`${t.ok}12`:"transparent",color:highCompOnly?t.ok:t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
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
              style={{padding:"10px 14px",borderRadius:8,border:`1.5px solid ${activeN?t.ac:t.bd}`,background:activeN?t.acL:"transparent",color:activeN?t.ac:t.txM,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>
              🎛 Filters{activeN?` (${activeN})`:""}
            </button>
            {activeN>0 && (
              <button onClick={clearAll}
                style={{padding:"10px 12px",borderRadius:8,border:`1.5px solid ${t.er}30`,background:"transparent",color:t.er,fontSize:13,fontWeight:600,cursor:"pointer",fontFamily:"inherit"}}>
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
              <Chips label="Role Category"   options={opts.roles}  selected={selRoles}  onChange={setSelRoles}  t={t}/>
              <Chips label="Experience Level" options={opts.exp}    selected={selExp}    onChange={setSelExp}    t={t}/>
              <Chips label="State"           options={opts.states} selected={selStates} onChange={setSelStates} t={t} pinned={PREFERRED_STATES}/>
              <Chips label="City / Hub"      options={opts.cities} selected={selCities} onChange={setSelCities} t={t} pinned={PREFERRED_CITIES}/>
              <Chips label="ATS Platform"    options={opts.ats}    selected={selATS}    onChange={setSelATS}    t={t}/>
            </div>
          )}

          {/* Job cards */}
          <div style={{display:"flex",flexDirection:"column",gap:10}}>
            {fj.slice(0,60).map(j => {
              const sc=j.relevance_score||0, open=xJ===j.external_id;
              const ats=ATS_META[j.ats]||ATS_META.unknown;
              const catLbl=ROLE_CATS.find(r=>r.id===j._cat)?.label||"Other";
              const isApplied = j.application_status === 'applied';
              return (
                <div key={j.external_id} onClick={()=>setXJ(open?null:j.external_id)}
                  style={{background:t.cd,borderRadius:12,border:`1px solid ${t.bd}`,overflow:"hidden",cursor:"pointer",transition:"all .2s",boxShadow:open?t.sh:t.shS,opacity:isApplied?0.45:1}}>
                  <div className="job-card-top" style={{padding:"16px 20px",display:"flex",justifyContent:"space-between",alignItems:"center",gap:12}}>
                    <div style={{display:"flex",alignItems:"center",gap:14,flex:1,minWidth:0}}>
                      <LogoImg name={j.company} size={40} t={t}/>
                      <div style={{flex:1,minWidth:0}}>
                        <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:5,flexWrap:"wrap"}}>
                          <span style={{fontSize:17,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>{j.title}</span>
                          {isApplied && <Pill ch={ST_LABEL.applied} c={ST_COLOR.applied} t={t}/>}
                          <Pill ch={catLbl} c={t.bl} t={t}/>
                          <Pill ch={`${ats.i} ${ats.l}`} c={ats.c} t={t}/>
                        </div>
                        <div className="job-meta" style={{display:"flex",gap:12,fontSize:14,color:t.txS,flexWrap:"wrap",alignItems:"center"}}>
                          <span style={{fontWeight:700}}>{j.company}</span>
                          {isPlatinum(j) && (
                            <span style={{
                              background:'linear-gradient(135deg, #b8860b, #ffd700)',
                              color:'#1a1a1a',
                              fontSize:'10px',
                              fontWeight:'700',
                              padding:'2px 6px',
                              borderRadius:'4px',
                              marginLeft:'6px',
                              letterSpacing:'0.5px',
                              textTransform:'uppercase',
                            }}>
                              PLATINUM
                            </span>
                          )}
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
                    <div style={{display:"flex",alignItems:"center",gap:10,flexShrink:0}}>
                      <div style={{width:52,height:52,borderRadius:12,display:"flex",alignItems:"center",justifyContent:"center",background:t.sBg(sc)}}>
                        <span style={{fontSize:20,fontWeight:800,color:t.sTx(sc),fontFamily:"'Playfair Display',serif"}}>{(sc*100).toFixed(0)}</span>
                      </div>
                      <span style={{fontSize:18,color:t.txM,transform:open?"rotate(180deg)":"",transition:"transform .2s"}}>▾</span>
                    </div>
                  </div>
                  {open && (
                    <div style={{padding:"0 20px 18px",borderTop:`1px solid ${t.bd}`}}>
                      <div style={{display:"flex",gap:6,flexWrap:"wrap",margin:"14px 0 10px"}}>
                        {(j.matched_skills||[]).map(s=><Pill key={s} ch={s} t={t} big/>)}
                        {(j.sponsorship||likelySponsor(j)) && <Pill ch="🛂 Likely H1B" c={t.vi} t={t} big/>}
                      </div>
                      {j.description && (
                        <p style={{fontSize:15,color:t.txS,lineHeight:1.85,maxHeight:160,overflow:"hidden",margin:"10px 0"}}>
                          {j.description.slice(0,700)}...
                        </p>
                      )}
                      {/* Application History for this company */}
                      {(() => {
                        const coKey = (j.company || "").toLowerCase();
                        const coHistory = (companyApps[coKey] || []).filter(a => a.status !== "saved");
                        if (!coHistory.length) return null;
                        return (
                          <div style={{margin:"12px 0",padding:"12px 16px",borderRadius:10,background:`${t.wm}10`,border:`1px solid ${t.wm}30`}}>
                            <div style={{fontSize:12,fontWeight:700,color:t.wm,textTransform:"uppercase",letterSpacing:".06em",marginBottom:8}}>
                              📋 Your history at {j.company}
                            </div>
                            {coHistory.map((a,i) => (
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
                        );
                      })()}
                      <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",marginTop:10}}>
                        <a href={j.url} target="_blank" rel="noopener noreferrer" onClick={e=>e.stopPropagation()}
                          style={{display:"inline-block",padding:"11px 24px",borderRadius:9,background:t.gP,color:"#fff",fontSize:15,fontWeight:700,textDecoration:"none",boxShadow:`0 3px 12px ${t.ac}30`}}>
                          Apply →
                        </a>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            const base = RENDER_API;
                            if (!base) return;
                            try {
                              const resp = await fetch(`${base}/api/applications`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                  external_id: j.external_id,
                                  title: j.title,
                                  company: j.company,
                                  url: j.url || '',
                                  status: 'applied',
                                  relevance_score: j.relevance_score || 0,
                                  salary_min: j.salary_min || 0,
                                  salary_max: j.salary_max || 0,
                                  location: j.location || '',
                                }),
                              });
                              if (resp.ok) {
                                const newApp = await resp.json();
                                setApplications(prev => {
                                  const filtered = prev.filter(a => a.external_id !== j.external_id);
                                  return [...filtered, newApp];
                                });
                              }
                            } catch (err) {
                              console.warn('Mark applied failed:', err);
                            }
                          }}
                          style={{
                            background: 'rgba(59,130,246,0.15)', color: '#3b82f6',
                            border: '1px solid rgba(59,130,246,0.3)', borderRadius: '4px',
                            padding: '3px 8px', fontSize: '11px', cursor: 'pointer',
                            marginLeft: '6px',
                          }}
                        >
                          ✓ Applied
                        </button>
                        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                          {Object.keys(ST_LABEL).map(st => {
                            const cur = apps[j.external_id];
                            const isCur = cur?.status === st;
                            const c = ST_COLOR[st];
                            return (
                              <button key={st} onClick={e=>{e.stopPropagation();isCur?removeApp(j.external_id):saveApp(j,st);}}
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
                    </div>
                  )}
                </div>
              );
            })}
            {fj.length>60 && (
              <div style={{textAlign:"center",padding:18,color:t.txM,fontSize:15}}>
                Showing 60 of {fj.length} — use filters to narrow results
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
        </div>}

        {/* ════════════ RARE SKILLS ════════════ */}
        {tab==="rare" && (() => {
          const rareJobs = enriched
            .filter(j => (j.rare_skill_hits||[]).length > 0)
            .sort((a,b) => (b.rare_skill_hits.length - a.rare_skill_hits.length) || ((b.relevance_score||0) - (a.relevance_score||0)));
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
                  {rareJobs.slice(0,80).map(j => {
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
                              <span style={{fontSize:16,fontWeight:800,color:t.sTx(sc),fontFamily:"'Playfair Display',serif"}}>{(sc*100).toFixed(0)}</span>
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
                  {rareJobs.length > 80 && (
                    <div style={{textAlign:"center",padding:18,color:t.txM,fontSize:14}}>
                      Showing 80 of {rareJobs.length}.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {/* ════════════ ANALYTICS ════════════ */}
        {tab==="analytics" && (
          <div className="two-col">
            <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
              <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>ATS Distribution</h3>
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={dist.ats||[]} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={95} paddingAngle={3} stroke="none">
                    {(dist.ats||[]).map((d,i)=><Cell key={i} fill={(ATS_META[d.name]||ATS_META.unknown).c} opacity={0.75}/>)}
                  </Pie>
                  <Tooltip contentStyle={ttS}/>
                </PieChart>
              </ResponsiveContainer>
              <div style={{display:"flex",gap:10,flexWrap:"wrap",justifyContent:"center",marginTop:10}}>
                {(dist.ats||[]).map(d=>{const m=ATS_META[d.name]||ATS_META.unknown;return<span key={d.name} style={{fontSize:13,color:m.c,fontWeight:600}}>{m.i} {m.l}: {d.value}</span>;})}
              </div>
            </div>
            <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
              <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Salary Distribution</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={dist.salary_buckets||[]}>
                  <XAxis dataKey="range" tick={{fill:t.txM,fontSize:11}} axisLine={{stroke:t.bd}} tickLine={false}/>
                  <YAxis tick={{fill:t.txM,fontSize:11}} axisLine={false} tickLine={false}/>
                  <Tooltip contentStyle={ttS}/>
                  <Bar dataKey="count" radius={[6,6,0,0]}>
                    {(dist.salary_buckets||[]).map((d,i)=><Cell key={i} fill={[t.wm,t.wm,t.acS,t.ok,t.ac,t.vi][i]||t.ac} opacity={0.6}/>)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
              <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>30-Day Posting Trend</h3>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={data?.trend||[]}>
                  <XAxis dataKey="date" tick={{fill:t.txM,fontSize:11}} axisLine={{stroke:t.bd}} tickLine={false} tickFormatter={v=>v.slice(5)}/>
                  <YAxis tick={{fill:t.txM,fontSize:11}} axisLine={false} tickLine={false}/>
                  <Tooltip contentStyle={ttS}/>
                  <Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
              <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Key Metrics</h3>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
                {[
                  [`${stats.h1b_pct||0}%`,"H1B Sponsors",t.vi],
                  [`${stats.remote_pct||0}%`,"Remote Jobs",t.ok],
                  [`${stats.companies_tracked||0}`,"Companies",t.ac],
                  [`${stats.high_match||0}`,`High Match (top 10% • ≥${stats.high_match_threshold?.toFixed(2)||"0.70"})`,t.wm],
                ].map(([v,l,c])=>(
                  <div key={l} style={{padding:18,borderRadius:12,background:`${c}08`,border:`1px solid ${c}20`,textAlign:"center"}}>
                    <div style={{fontSize:34,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{v}</div>
                    <div style={{fontSize:13,color:t.txM,marginTop:4}}>{l}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ════════════ COMPANIES ════════════ */}
        {tab==="companies" && <div>
          <div style={{marginBottom:18}}>
            <input placeholder="Search companies..." value={cq} onChange={e=>sCq(e.target.value)} style={{...iS,maxWidth:360}}/>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))",gap:14}}>
            {(data?.top_companies||[]).filter(c=>!cq||c.name.toLowerCase().includes(cq.toLowerCase())).map(co=>(
              <div key={co.name} style={{background:t.cd,borderRadius:14,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}>
                  <div style={{display:"flex",alignItems:"center",gap:12}}>
                    <LogoImg name={co.name} size={36} t={t}/>
                    <h4 style={{margin:0,fontSize:16,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>{co.name}</h4>
                  </div>
                  <div style={{background:t.acL,padding:"5px 12px",borderRadius:8}}>
                    <span style={{fontSize:16,fontWeight:700,color:t.ac}}>{co.count}</span>
                    <span style={{fontSize:11,color:t.txM,marginLeft:4}}>jobs</span>
                  </div>
                </div>
                <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
                  {enriched.filter(j=>j.company===co.name).slice(0,4).map((j,i)=>(
                    <span key={i} style={{fontSize:12,padding:"3px 10px",borderRadius:6,background:t.bgS,color:t.txS,border:`1px solid ${t.bd}`}}>{j.title}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>}

        {/* ════════════ TRENDS ════════════ */}
        {tab==="trends" && (
          <div className="trends-col">
            <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
              <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Jobs Posted by Date</h3>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={data?.trend||[]}>
                  <XAxis dataKey="date" tick={{fill:t.txM,fontSize:11}} axisLine={{stroke:t.bd}} tickLine={false} tickFormatter={v=>v.slice(5)}/>
                  <YAxis tick={{fill:t.txM,fontSize:11}} axisLine={false} tickLine={false}/>
                  <Tooltip contentStyle={ttS}/>
                  <Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div style={{background:t.cd,borderRadius:14,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1}}>
                <h3 style={{margin:"0 0 14px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Top Companies</h3>
                {(data?.top_companies||[]).slice(0,8).map((co,i)=>(
                  <div key={co.name} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none"}}>
                    <LogoImg name={co.name} size={22} t={t}/>
                    <span style={{fontSize:14,fontWeight:600,color:t.tx,flex:1}}>{co.name}</span>
                    <span style={{fontSize:14,fontWeight:700,color:t.ac}}>{co.count}</span>
                  </div>
                ))}
              </div>
              <div style={{background:t.cd,borderRadius:14,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1}}>
                <h3 style={{margin:"0 0 14px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Top Locations</h3>
                {(dist.cities||[]).slice(0,8).map((c,i)=>(
                  <div key={c.name} style={{display:"flex",justifyContent:"space-between",padding:"9px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none"}}>
                    <span style={{fontSize:14,fontWeight:600,color:t.tx}}>{c.name}</span>
                    <span style={{fontSize:14,fontWeight:700,color:t.acS}}>{c.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ════════════ TRACKER ════════════ */}
        {tab==="tracker" && (() => {
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
        })()}

        {/* ════════════ PIPELINE ════════════ */}
        {tab==="pipeline" && (
          <div>
            {/* Stats bar */}
            <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', flexWrap: 'wrap', fontSize: '14px', color: t.txS }}>
              <span>📨 Applied this week: <strong style={{color: t.tx}}>{applications.filter(a =>
                a.status === 'applied' && a.applied_at &&
                new Date(a.applied_at) > new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)
              ).length}</strong></span>
              <span>📞 In phone screen: <strong style={{color: t.tx}}>{applications.filter(a => a.status === 'interview').length}</strong></span>
              <span>🎯 Offers: <strong style={{color: t.tx}}>{applications.filter(a => a.status === 'offer').length}</strong></span>
              <span>📋 Total tracked: <strong style={{color: t.tx}}>{applications.length}</strong></span>
              {appLoading && <span style={{color: t.txM, fontStyle: 'italic'}}>Loading...</span>}
              {!RENDER_API && <span style={{color: t.er}}>⚠️ Set VITE_RENDER_URL to enable pipeline sync</span>}
              {RENDER_API && !appLoading && (
                <button onClick={fetchApplications}
                  style={{padding:'3px 10px',borderRadius:6,border:`1px solid ${t.bd}`,background:'transparent',color:t.txM,fontSize:12,cursor:'pointer',fontFamily:'inherit'}}>
                  ↻ Refresh
                </button>
              )}
            </div>

            {/* Kanban columns */}
            <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', alignItems: 'flex-start', paddingBottom: '12px' }}>
              {PIPELINE_STAGES.map(stage => {
                const stageApps = applications.filter(a => a.status === stage.key);
                return (
                  <div key={stage.key} style={{
                    minWidth: '200px', flex: '0 0 200px',
                    background: 'rgba(255,255,255,0.03)',
                    border: `1px solid ${stage.color}30`,
                    borderRadius: '10px', padding: '12px',
                  }}>
                    <div style={{
                      fontWeight: '700', fontSize: '12px', textTransform: 'uppercase',
                      letterSpacing: '0.8px', color: stage.color, marginBottom: '10px',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      {stage.label}
                      <span style={{
                        background: stage.color + '22', color: stage.color,
                        borderRadius: '10px', padding: '1px 7px', fontSize: '11px',
                      }}>{stageApps.length}</span>
                    </div>
                    {stageApps.length === 0 && (
                      <div style={{fontSize:'12px',color:t.txM,fontStyle:'italic',padding:'8px 4px',textAlign:'center'}}>empty</div>
                    )}
                    {stageApps.map(app => (
                      <div key={app.external_id} style={{
                        background: t.cd,
                        borderRadius: '6px', padding: '10px', marginBottom: '8px',
                        borderLeft: `3px solid ${stage.color}`,
                        boxShadow: t.shS,
                      }}>
                        <div style={{ fontWeight: '600', fontSize: '13px', marginBottom: '2px', color: t.tx }}>
                          {app.company}
                          {app.tier === 'platinum' && (
                            <span style={{
                              background: 'linear-gradient(135deg, #b8860b, #ffd700)',
                              color: '#1a1a1a', fontSize: '9px', fontWeight: '700',
                              padding: '1px 4px', borderRadius: '3px', marginLeft: '5px',
                            }}>PLATINUM</span>
                          )}
                        </div>
                        <div style={{ fontSize: '11px', color: t.txM, marginBottom: '6px' }}>
                          {app.title}
                        </div>
                        {(app.salary_min > 0) && (
                          <div style={{ fontSize: '11px', color: '#22c55e', marginBottom: '4px' }}>
                            ${Math.round(app.salary_min / 1000)}K–${Math.round((app.salary_max || app.salary_min) / 1000)}K
                          </div>
                        )}
                        <select
                          value={app.status}
                          onClick={e => e.stopPropagation()}
                          onChange={async (e) => {
                            const newStatus = e.target.value;
                            setApplications(prev => prev.map(a =>
                              a.external_id === app.external_id ? { ...a, status: newStatus } : a
                            ));
                            try {
                              await fetch(`${RENDER_API}/api/applications/${app.external_id}`, {
                                method: 'PATCH',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ status: newStatus }),
                              });
                            } catch (err) {
                              console.warn('Failed to update status:', err);
                            }
                          }}
                          style={{
                            width: '100%', fontSize: '11px', padding: '3px',
                            background: t.inp, color: t.tx,
                            border: `1px solid ${t.bd}`, borderRadius: '4px',
                            fontFamily: 'inherit', cursor: 'pointer',
                          }}
                        >
                          {PIPELINE_STAGES.map(s => (
                            <option key={s.key} value={s.key}>{s.label}</option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ════════════ MONITOR ════════════ */}
        {tab==="monitor" && (
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
                  <button onClick={triggerScrape} disabled={scraping||!RENDER_API}
                    style={{padding:"11px 22px",borderRadius:9,border:"none",
                      background:scraping?t.bgS:(RENDER_API?t.gP:`${t.txM}20`),
                      color:scraping||!RENDER_API?t.txM:"#fff",
                      fontSize:14,fontWeight:700,cursor:scraping||!RENDER_API?"not-allowed":"pointer",
                      fontFamily:"inherit",transition:"all .15s"}}>
                    {scraping?"⏳ Scraping...":"▶ Run Scrape Now"}
                  </button>
                  {scraping && scrapeProgress && scrapeProgress.is_running && (
                    <div style={{marginTop:10,fontSize:13,color:t.txS,fontWeight:500,lineHeight:1.5}}>
                      Scraping: <strong style={{color:t.tx}}>{scrapeProgress.current_company || "starting…"}</strong>
                      {" • "}{scrapeProgress.companies_done}/{scrapeProgress.companies_total} companies
                      {" • "}{scrapeProgress.found} jobs found
                      {scrapeProgress.new>0 && <> · <span style={{color:t.ok}}>{scrapeProgress.new} new</span></>}
                      {scrapeProgress.eta_seconds!=null && scrapeProgress.eta_seconds>0 &&
                        <> · ETA {Math.round(scrapeProgress.eta_seconds)}s</>}
                    </div>
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
        )}
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;800&family=Source+Sans+3:wght@300;400;500;600;700&display=swap');
        *{box-sizing:border-box;margin:0}
        html,body{font-size:16px}

        /* ── Responsive layouts ── */
        .page-pad{max-width:1320px;margin:0 auto;padding:20px 28px}
        .stats-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:22px}
        .nav-wrap{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
        .nav-tabs{display:flex;align-items:center;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;flex:1}
        .nav-tabs::-webkit-scrollbar{display:none}
        .two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
        .trends-col{display:grid;grid-template-columns:2fr 1fr;gap:16px}
        .filter-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;align-items:center}

        @media(max-width:1024px){
          .two-col{grid-template-columns:1fr}
          .trends-col{grid-template-columns:1fr}
          .stats-grid{grid-template-columns:repeat(3,1fr)}
        }
        @media(max-width:640px){
          .page-pad{padding:12px 12px}
          .stats-grid{grid-template-columns:repeat(2,1fr);gap:10px}
          .nav-wrap{padding:10px 14px!important}
          .nav-tabs button{padding:7px 11px!important;font-size:13px!important}
          .filter-bar select,.filter-bar input{font-size:14px}
          .job-card-top{flex-wrap:wrap}
          .job-meta{gap:8px!important}
        }

        /* ── Scrollbar ── */
        ::-webkit-scrollbar{width:6px}
        ::-webkit-scrollbar-track{background:${t.bgS}}
        ::-webkit-scrollbar-thumb{background:${t.acS};border-radius:3px}
        ::selection{background:${t.acL};color:${t.ac}}

        /* ── Focus ── */
        input:focus,select:focus{border-color:${t.acS}!important;box-shadow:0 0 0 3px ${t.ac}12!important}

        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
      `}</style>
    </div>
  );
}
