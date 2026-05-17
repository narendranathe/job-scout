import { useState, useMemo, useEffect, useCallback, useRef, memo } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area } from "recharts";
// API + auth helpers extracted to lib/api.js (1/N of the App.jsx split).
// Same constants, same behavior — only the location changes. Existing
// `${RENDER_API}/...` template strings work unchanged.
import { DEFAULT_RENDER_URL, STATIC_URL, RENDER_API, apiToken, authHeaders } from "./lib/api.js";
// Theme tokens (light + dark palettes) extracted to lib/theme.js (PR 2/N).
import { TH } from "./lib/theme.js";
// Display formatting helpers extracted to lib/format.js (PR 3/N).
import { fmtSal, timeAgo } from "./lib/format.js";
// Small presentational components (PR 4/N).
import { BrandLogo } from "./components/BrandLogo.jsx";
import { LogoImg, CO_DOMAINS, guessDomain } from "./components/LogoImg.jsx";
import { ScrapeProgressBar } from "./components/ScrapeProgressBar.jsx";
// First-run setup panel (PR 5/N).
import { SetupPanel } from "./components/SetupPanel.jsx";
// Vault tab row (memoized, PR 6/N).
import { VaultRow } from "./components/VaultRow.jsx";
// Shared job constants + helpers (PR 7/N + PR 8/N).
import {
  ATS_META,
  ROLE_CATS,
  stopProp,
  EMPTY_OBJ,
  EMPTY_ARR,
  jobFitTone as _jobFitTone,
  ST_COLOR,
  ST_LABEL,
  JC_STYLES,
  isPlatinum,
  isHighComp,
  likelySponsor,
} from "./lib/jobConstants.js";
// Pill + JobCard extracted (PR 8/N).
import { Pill } from "./components/Pill.jsx";
import { JobCard } from "./components/JobCard.jsx";
// Small presentational components (PR 9/N).
import { Chips } from "./components/Chips.jsx";
import { MRow, Chk } from "./components/MRow.jsx";
// Per-tab modules (PR 10/N onward).
import { MonitorTab } from "./tabs/MonitorTab.jsx";
import { PipelineTab } from "./tabs/PipelineTab.jsx";

// ATS_META imported from ./lib/jobConstants.js (top of file).

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

// BrandLogo, LogoImg/CO_DOMAINS/guessDomain, ScrapeProgressBar imported from ./components/* (PR 4/N).


/* ═══ Role categories ═══ */
// ROLE_CATS imported from ./lib/jobConstants.js (top of file).
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

// likelySponsor imported from ./lib/jobConstants.js (top).

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

// isPlatinum, isHighComp imported from ./lib/jobConstants.js (top).

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
/* RENDER_API resolves in this order so users never have to touch .env:
 *   1. localStorage key "jobscout_api_url" (set via the in-app Settings panel)
 *   2. VITE_RENDER_URL build-time env var (legacy / power users)
 *   3. "" → SetupPanel renders on first load and blocks the dashboard until
 *      the user pastes their Render URL (prefilled with the project default).
 * The value is read once at module load; the Save action calls location.reload()
 * so every existing `${RENDER_API}/...` template string keeps working.
 */
// DEFAULT_RENDER_URL / RENDER_API / STATIC_URL imported from lib/api.js (above).

/* ───── Vault auth helpers ───────────────────────────────────────────
 * When the backend has API_SECRET set, every /api/vault/* call must
 * carry ``Authorization: Bearer <token>``. We read the token from
 * localStorage (key "vault_token") so the user can set it once via
 * DevTools — a proper login UI is tracked as a follow-up.
 *
 * apiToken()    — safe read, returns "" outside browser
 * authHeaders() — spreadable into ``headers: { ... }`` only when a
 *                 token exists, so calls in dev (no API_SECRET) work
 *                 unchanged.
 */
// apiToken / authHeaders imported from lib/api.js (top of file).

// SetupPanel moved to ./components/SetupPanel.jsx (PR 5/N).


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
// ST_COLOR + ST_LABEL imported from ./lib/jobConstants.js (top).

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
// fmtSal + timeAgo imported from ./lib/format.js (top of file).
// Pill imported from ./components/Pill.jsx (top).

/* ═══ Chips filter component ═══ */
// Chips, MRow, Chk imported from ./components/* (PR 9/N).

// JC_STYLES + JobCard extracted to ./lib/jobConstants.js + ./components/JobCard.jsx (PR 8/N).


// VaultRow extracted to ./components/VaultRow.jsx (PR 6/N).


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
  // Setup panel: shows blocking when no Render URL is configured;
  // user can also re-open from the header ⚙️ button to edit.
  const [setupOpen, setSetupOpen] = useState(() => !RENDER_API);

  // Best-match vault integration on job cards
  const [bestMatchByJob, setBestMatchByJob] = useState({});
  const [versionDetails, setVersionDetails] = useState({});
  const [expandedVersionRow, setExpandedVersionRow] = useState({});
  // Per-version-key PDF download state: { [versionKey]: {loading, error} }
  const [pdfDownloadState, setPdfDownloadState] = useState({});

  // ── Default-resume → per-card job-fit chip (Issue #39 part A) ────
  // `defaultResumeVersion` is the user's chosen "main" resume, fetched
  // from /api/profile on mount. When null, no chip is rendered and we
  // never fire job-fit calls. `jobFitByJob` caches per-card results
  // {loading, error, pct, versionKey} so the parent batch effect can
  // tell which jobs still need a fetch for the current default.
  // `jobFitInflightRef` caps concurrency at MAX_JOB_FIT_CONCURRENCY.
  // `jobFitPendingRef` tracks "we're about to fetch this id" so two
  // pump() ticks can't queue the same id before fetchJobFit() bumps
  // the inflight counter.
  const [defaultResumeVersion, setDefaultResumeVersion] = useState(null);
  const [defaultUpdating, setDefaultUpdating] = useState(false);
  const [defaultMsg, setDefaultMsg] = useState(null);
  // R2 #2: empty-state hint banner above the Jobs list when no default
  // resume is configured. Persisted dismissal in localStorage so users
  // who've already seen the hint don't get pestered every reload.
  const [defaultHintDismissed, setDefaultHintDismissed] = useState(() => {
    try { return localStorage.getItem("jobscout_default_hint_dismissed") === "1"; }
    catch { return false; }
  });
  const dismissDefaultHint = useCallback(() => {
    setDefaultHintDismissed(true);
    try { localStorage.setItem("jobscout_default_hint_dismissed", "1"); } catch {}
  }, []);
  const [jobFitByJob, setJobFitByJob] = useState({});
  const jobFitInflightRef = useRef(0);
  const jobFitPendingRef = useRef(new Set());
  // R2 #6: event-driven re-pump replaces the old setInterval(250ms). The
  // batch effect below installs its `pump` function into this ref so
  // fetchJobFit()'s finally block can immediately try to fill the
  // freshly-vacated slot. Mutating a ref doesn't trigger a re-render.
  const jobFitPumpRef = useRef(() => {});

  // Fetch the profile once on mount so we know whether to render chips.
  // No retry/backoff — if /api/profile is offline, we just don't show
  // chips, which is the same as "no default configured".
  useEffect(() => {
    if (!RENDER_API) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`${RENDER_API}/api/profile`, {
          signal: AbortSignal.timeout(8000),
        });
        if (!r.ok || cancelled) return;
        const d = await r.json();
        if (cancelled) return;
        setDefaultResumeVersion(d.default_resume_version || null);
      } catch (_e) { /* offline / 5xx — silently no chip */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // Wipe the job-fit cache when the user changes default resume — stale
  // percentages against the OLD resume would mislead. The parent batch
  // effect re-queues every visible card after this clears.
  useEffect(() => {
    setJobFitByJob({});
    jobFitPendingRef.current = new Set();
  }, [defaultResumeVersion]);

  const fetchBestMatch = useCallback(async (job) => {
    const key = job.external_id;
    if (!key) return;
    if (!RENDER_API) {
      setBestMatchByJob(prev => ({...prev, [key]: {loading:false, error:"No API configured", data:null}}));
      return;
    }
    let already = false;
    setBestMatchByJob(prev => {
      if (prev[key]?.loading) { already = true; return prev; }
      return {...prev, [key]: {loading:true, error:null, data:prev[key]?.data || null}};
    });
    if (already) return;
    const jd = (job.description || job.title || "").trim().slice(0, 20000);
    if (!jd) {
      setBestMatchByJob(prev => ({...prev, [key]: {loading:false, error:"No job description", data:null}}));
      return;
    }
    try {
      const r = await fetch(`${RENDER_API}/api/vault/best-match`, {
        method:"POST",
        headers:{"Content-Type":"application/json", ...authHeaders()},
        body: JSON.stringify({job_description: jd, top_n: 5}),
        signal: AbortSignal.timeout(15000),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const rankings = Array.isArray(d.rankings) ? d.rankings : [];
      setBestMatchByJob(prev => ({...prev, [key]: {loading:false, error:null, data:{count:d.count||0, rankings}}}));
    } catch (e) {
      const msg = (e?.name === "TimeoutError" || /timed out/i.test(e?.message||""))
        ? "Match timed out — try again"
        : (e?.message === "HTTP 404" ? "Vault endpoint not found" : (e?.message||"Failed"));
      setBestMatchByJob(prev => ({...prev, [key]: {loading:false, error:msg, data:null}}));
    }
  }, []);

  // Tunables for the per-card job-fit fetcher. Grouped + named so reviewers
  // don't have to grep two unrelated literals (5 and 60) across this file.
  //  - MAX_JOB_FIT_CONCURRENCY: enough that the top of a freshly-mounted
  //    Jobs tab fills in within ~2-3 seconds, low enough that we don't
  //    trip Render's free-tier worker pool.
  //  - JOB_FIT_VISIBLE_SLICE: matches the same `.slice(0, N)` used to render
  //    JobCards below, so we only fetch fits for cards the user can see.
  //    Must stay in sync with the render slice.
  const MAX_JOB_FIT_CONCURRENCY = 5;
  const JOB_FIT_VISIBLE_SLICE = 60;

  // Fetches a single job-fit result. Designed to be invoked from the
  // batch effect — pre-checks cache + inflight set so the effect can
  // fire-and-forget. The inflight counter is decremented in `finally`
  // so a thrown error doesn't permanently park the slot.
  const fetchJobFit = useCallback(async (extId, jobDescription, versionKey) => {
    if (!RENDER_API || !extId || !versionKey) {
      jobFitPendingRef.current.delete(extId);
      return;
    }
    const jd = (jobDescription || "").trim().slice(0, 20000);
    if (!jd) {
      setJobFitByJob(prev => ({...prev, [extId]: {loading:false, error:"No JD", pct:null, versionKey}}));
      jobFitPendingRef.current.delete(extId);
      return;
    }
    jobFitInflightRef.current += 1;
    setJobFitByJob(prev => {
      const cur = prev[extId];
      if (cur && cur.versionKey === versionKey && cur.pct != null) return prev;
      return {...prev, [extId]: {loading:true, error:null, pct:null, versionKey}};
    });
    try {
      const r = await fetch(`${RENDER_API}/api/vault/job-fit`, {
        method: "POST",
        headers: {"Content-Type":"application/json", ...authHeaders()},
        body: JSON.stringify({version_key: versionKey, job_description: jd}),
        signal: AbortSignal.timeout(12000),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const combined = typeof d.combined_score === "number" ? d.combined_score : 0;
      const pct = Math.round(combined * 100);
      setJobFitByJob(prev => ({...prev, [extId]: {loading:false, error:null, pct, versionKey}}));
    } catch (e) {
      const msg = (e?.name === "TimeoutError") ? "timeout" : (e?.message || "failed");
      setJobFitByJob(prev => ({...prev, [extId]: {loading:false, error:msg, pct:null, versionKey}}));
    } finally {
      jobFitInflightRef.current = Math.max(0, jobFitInflightRef.current - 1);
      jobFitPendingRef.current.delete(extId);
      // R2 #6: immediately try to refill the slot we just freed. The
      // batch effect installs the live pump function into this ref; if
      // we're not on the Jobs tab anymore (or the effect cleaned up),
      // the ref still points to a no-op so this is safe.
      jobFitPumpRef.current();
    }
  }, []);

  const fetchVersionDetails = useCallback(async (versionKey) => {
    if (!RENDER_API || !versionKey) return;
    let skip = false;
    setVersionDetails(prev => {
      if (prev[versionKey]?.data || prev[versionKey]?.loading) { skip = true; return prev; }
      return {...prev, [versionKey]: {loading:true, error:null, data:null}};
    });
    if (skip) return;
    try {
      const r = await fetch(`${RENDER_API}/api/vault/version/${encodeURIComponent(versionKey)}`, {
        headers: { ...authHeaders() },
        signal: AbortSignal.timeout(10000),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setVersionDetails(prev => ({...prev, [versionKey]: {loading:false, error:null, data:d}}));
    } catch (e) {
      setVersionDetails(prev => ({...prev, [versionKey]: {loading:false, error:e.message||"Failed", data:null}}));
    }
  }, []);

  // One-click PDF download for a vault resume version. Uses fetch+blob
  // instead of `<a href>` because the vault endpoints require a Bearer
  // header (set when API_SECRET is configured) — anchor downloads can't
  // send custom headers. A query-token fallback would leak the secret
  // into server logs / browser history, so we deliberately avoid that.
  // The blob URL is revoked after the click to release the memory.
  const downloadResumePdf = useCallback(async (versionKey, fallbackName) => {
    if (!RENDER_API || !versionKey) return;
    let inFlight = false;
    setPdfDownloadState(prev => {
      if (prev[versionKey]?.loading) { inFlight = true; return prev; }
      return {...prev, [versionKey]: {loading:true, error:null}};
    });
    if (inFlight) return;
    let blobUrl = null;
    try {
      const r = await fetch(
        `${RENDER_API}/api/vault/version/${encodeURIComponent(versionKey)}/pdf`,
        { headers: { ...authHeaders() }, signal: AbortSignal.timeout(20000) },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      // Prefer the server-supplied filename from Content-Disposition; fall
      // back to "<version_key>.pdf" so the download still works if the
      // header is stripped by a proxy.
      const cd = r.headers.get("Content-Disposition") || "";
      const m = /filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?/i.exec(cd);
      const filename = (m && m[1]) || fallbackName || `${versionKey}.pdf`;
      blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setPdfDownloadState(prev => ({...prev, [versionKey]: {loading:false, error:null}}));
    } catch (e) {
      const msg = (e?.name === "TimeoutError" || /timed out/i.test(e?.message||""))
        ? "Download timed out — try again"
        : (e?.message === "HTTP 404" ? "Resume PDF not found"
          : (e?.message === "HTTP 401" ? "Auth required — set vault_token"
            : (e?.message || "Download failed")));
      setPdfDownloadState(prev => ({...prev, [versionKey]: {loading:false, error:msg}}));
    } finally {
      // Revoke after a tick so the click handler has a chance to fire.
      if (blobUrl) setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    }
  }, []);

  // Stable callback passed into <JobCard/>. Toggling card N's "open" only
  // mutates the single `xJ` string, which we then compare per-card via
  // `open === (xJ === j.external_id)` so unaffected cards skip re-render.
  const toggleCardOpen = useCallback((extId) => {
    setXJ(prev => prev === extId ? null : extId);
  }, []);

  // Per-card "Find Best Resume → version row View ▾" toggle. Mutates only
  // the `[extId]:[versionKey]:bool` slice so other cards' expanded state
  // is untouched.
  const toggleVersionRow = useCallback((extId, versionKey) => {
    const rowKey = `${extId}:${versionKey}`;
    let wasOpen = false;
    setExpandedVersionRow(prev => {
      wasOpen = !!prev[rowKey];
      return {...prev, [rowKey]: !wasOpen};
    });
    if (!wasOpen) fetchVersionDetails(versionKey);
  }, [fetchVersionDetails]);

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

  // Resume Vault tab
  const [vaultStats, setVaultStats]         = useState(null);
  const [vaultFiles, setVaultFiles]         = useState([]);
  const [vaultLoading, setVaultLoading]     = useState(false);
  const [vaultError, setVaultError]         = useState("");
  const [vaultSearch, setVaultSearch]       = useState("");
  const [vaultSort, setVaultSort]           = useState("company");
  const [vaultExpanded, setVaultExpanded]   = useState(null);
  const [vaultDetails, setVaultDetails]     = useState({});
  const [vaultCmpA, setVaultCmpA]           = useState("");
  const [vaultCmpB, setVaultCmpB]           = useState("");
  const [vaultCmpResult, setVaultCmpResult] = useState(null);
  const [vaultCmpLoading, setVaultCmpLoading] = useState(false);
  const [vaultUpFile, setVaultUpFile]       = useState(null);
  const [vaultUpCompany, setVaultUpCompany] = useState("");
  const [vaultUpRole, setVaultUpRole]       = useState("");
  const [vaultUpStatus, setVaultUpStatus]   = useState(null);
  const [vaultUpLoading, setVaultUpLoading] = useState(false);
  const vaultFileInputRef = useRef(null);
  const filteredVaultFiles = useMemo(() => {
    const q = vaultSearch.toLowerCase();
    const arr = q
      ? vaultFiles.filter(f => [f.version_key, f.company, f.role, f.filename, f.display_name]
          .filter(Boolean).some(v => String(v).toLowerCase().includes(q)))
      : vaultFiles.slice();
    const k = vaultSort;
    arr.sort((a, b) => {
      if (k === "size_bytes") return (b.size_bytes || 0) - (a.size_bytes || 0);
      return String(a[k] || "").toLowerCase().localeCompare(String(b[k] || "").toLowerCase());
    });
    return arr;
  }, [vaultFiles, vaultSearch, vaultSort]);

  // Manual scrape trigger + live progress polling (#19, #20).
  // `scraping` reflects "we should keep polling the status endpoint at the
  // fast cadence" — set when the POST returns 202 or 409, or when the slow
  // passive poller notices a background scrape running. Cleared once
  // snapshot.is_running flips false. `scrapeProgress` is the latest snapshot
  // from /api/scrape/status.
  const [scraping,setScraping]         = useState(false);
  const [scrapeMsg,setScrapeMsg]       = useState(null);
  const [scrapeProgress,setScrapeProgress] = useState(null);

  // Show the progress bar when we're actively polling OR the snapshot says
  // a scrape is in flight (covers the background scrape thread case where
  // the user never clicked the button).
  const barVisible = !!(scrapeProgress && scrapeProgress.is_running);

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
        // Guard against stale-response reordering: if a later poll arrives
        // before an earlier one, drop the older snapshot so the bar can't
        // jump backwards. Snapshots from the same run carry monotonic
        // started_at; companies_done is also monotonic within a run.
        setScrapeProgress(prev => {
          if (!prev) return snap;
          if (prev.started_at && snap.started_at && snap.started_at < prev.started_at) {
            return prev;  // older run, ignore
          }
          if (prev.started_at === snap.started_at &&
              (snap.companies_done ?? 0) < (prev.companies_done ?? 0)) {
            return prev;  // out-of-order poll within same run
          }
          return snap;
        });
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

  // Passive low-rate poll for background-scrape progress (#20). When the
  // Monitor tab is mounted but we haven't manually triggered a scrape, ping
  // the status endpoint every 10s. If it reports is_running=true, flip into
  // the fast-poll branch above so the bar appears for the background thread
  // too. Auto-pauses when the tab is hidden.
  useEffect(() => {
    if (!RENDER_API || scraping || tab !== "monitor") return;
    let cancelled = false;
    const passive = async () => {
      if (typeof document !== "undefined" && document.hidden) return;
      try {
        const r = await fetch(`${RENDER_API}/api/scrape/status`,
                              { signal: AbortSignal.timeout(5000) });
        if (!r.ok || cancelled) return;
        const snap = await r.json();
        if (cancelled) return;
        if (snap && snap.is_running) {
          setScrapeProgress(snap);
          setScraping(true);  // hand off to the fast poller
        }
      } catch (_e) { /* network hiccup, retry next tick */ }
    };
    passive();
    const id = setInterval(passive, 10000);
    return () => { cancelled = true; clearInterval(id); };
  }, [scraping, tab]);

  // Auto-clear the result toast 3s after a scrape finishes.
  useEffect(() => {
    if (!scrapeMsg || scraping) return;
    if (!scrapeMsg.startsWith("✅")) return;
    const id = setTimeout(() => setScrapeMsg(null), 3000);
    return () => clearTimeout(id);
  }, [scrapeMsg, scraping]);

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

  // Purge stale jobs (#23) — destructive, scrape-gated.
  const [purgeDays,setPurgeDays]       = useState(4);
  const [purgeLoading,setPurgeLoading] = useState(false);
  const [purgeMsg,setPurgeMsg]         = useState(null);
  const [purgeIsErr,setPurgeIsErr]     = useState(false);

  const runPurgeStale = async () => {
    if (!RENDER_API) {
      setPurgeIsErr(true);
      setPurgeMsg("No Render API configured. Set VITE_RENDER_URL in your .env file.");
      return;
    }
    const days = Number(purgeDays);
    if (!Number.isFinite(days) || days < 1) {
      setPurgeIsErr(true);
      setPurgeMsg("Days inactive must be a positive integer (≥ 1).");
      return;
    }
    const ok = window.confirm(
      `Permanently delete jobs inactive for ${days} day${days===1?"":"s"}? This cannot be undone.`
    );
    if (!ok) return;
    setPurgeLoading(true); setPurgeMsg(null); setPurgeIsErr(false);
    try {
      const resp = await fetch(`${RENDER_API}/api/admin/purge-stale`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({hours: days * 24}),
        signal: AbortSignal.timeout(30000),
      });
      const d = await resp.json().catch(() => ({}));
      if (resp.status === 409) {
        setPurgeIsErr(true);
        setPurgeMsg("Cannot purge while scrape is running. Retry in a few minutes.");
      } else if (!resp.ok) {
        setPurgeIsErr(true);
        setPurgeMsg(d.error || `HTTP ${resp.status}`);
      } else {
        setPurgeIsErr(false);
        setPurgeMsg(`Purged ${d.purged} jobs (threshold: ${d.hours_threshold}h).`);
      }
    } catch(e) {
      setPurgeIsErr(true);
      setPurgeMsg(`Could not reach Render: ${e.message}`);
    } finally {
      setPurgeLoading(false);
    }
  };

  // Clear DB cache (VACUUM) — destructive, scrape-gated.
  const [vacuumLoading,setVacuumLoading] = useState(false);
  const [vacuumMsg,setVacuumMsg]         = useState(null);
  const [vacuumIsErr,setVacuumIsErr]     = useState(false);

  const runClearCache = async () => {
    if (!RENDER_API) {
      setVacuumIsErr(true);
      setVacuumMsg("No Render API configured. Set VITE_RENDER_URL in your .env file.");
      return;
    }
    const ok = window.confirm(
      "Run VACUUM on the database? This reclaims unused space and may take a few seconds."
    );
    if (!ok) return;
    setVacuumLoading(true); setVacuumMsg(null); setVacuumIsErr(false);
    try {
      const resp = await fetch(`${RENDER_API}/api/admin/clear-cache`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        signal: AbortSignal.timeout(60000),
      });
      const d = await resp.json().catch(() => ({}));
      if (resp.status === 409) {
        setVacuumIsErr(true);
        setVacuumMsg("Cannot clear cache while scrape is running. Retry in a few minutes.");
      } else if (!resp.ok) {
        setVacuumIsErr(true);
        setVacuumMsg(d.error || `HTTP ${resp.status}`);
      } else {
        const mb = (d.bytes_reclaimed / 1024 / 1024).toFixed(2);
        setVacuumIsErr(false);
        setVacuumMsg(`Reclaimed ${mb} MB (${d.db_size_before} → ${d.db_size_after} bytes).`);
      }
    } catch(e) {
      setVacuumIsErr(true);
      setVacuumMsg(`Could not reach Render: ${e.message}`);
    } finally {
      setVacuumLoading(false);
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

  // Stable "✓ Applied" callback for <JobCard/>. POSTs to the pipeline API
  // and merges the response into the applications list. Takes the job at
  // call time so memoized JobCards don't capture stale closures.
  const markApplied = useCallback(async (job) => {
    const base = RENDER_API;
    if (!base) return;
    try {
      const resp = await fetch(`${base}/api/applications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          external_id: job.external_id,
          title: job.title,
          company: job.company,
          url: job.url || '',
          status: 'applied',
          relevance_score: job.relevance_score || 0,
          salary_min: job.salary_min || 0,
          salary_max: job.salary_max || 0,
          location: job.location || '',
        }),
      });
      if (resp.ok) {
        const newApp = await resp.json();
        setApplications(prev => {
          const filtered = prev.filter(a => a.external_id !== job.external_id);
          return [...filtered, newApp];
        });
      }
    } catch (err) {
      console.warn('Mark applied failed:', err);
    }
  }, []);

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

  const fetchVault = useCallback(async () => {
    if (!RENDER_API) return;
    setVaultLoading(true);
    setVaultError("");
    try {
      const [sr, lr] = await Promise.all([
        fetch(`${RENDER_API}/api/vault/stats`, {headers: {...authHeaders()}, signal: AbortSignal.timeout(8000)}),
        fetch(`${RENDER_API}/api/vault/list`,  {headers: {...authHeaders()}, signal: AbortSignal.timeout(8000)}),
      ]);
      if (sr.ok) setVaultStats(await sr.json());
      else setVaultStats(null);
      if (lr.ok) {
        const j = await lr.json();
        setVaultFiles(j.files || []);
      } else {
        setVaultFiles([]);
      }
      if (!sr.ok || !lr.ok) {
        setVaultError(`Vault load failed: stats HTTP ${sr.status}, list HTTP ${lr.status}`);
      }
    } catch (e) {
      setVaultError(e.message || "Failed to load vault");
    } finally {
      setVaultLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "vault" && RENDER_API && !vaultStats && !vaultLoading) fetchVault();
  }, [tab, fetchVault, vaultStats, vaultLoading]);

  // useCallback-wrapped so <VaultRow/> memoization isn't busted by a new
  // function identity on every parent render. Uses the functional
  // setVaultDetails form for the "already loaded?" short-circuit so we
  // don't need vaultDetails in the deps array.
  const fetchVaultVersionDetails = useCallback(async (vk) => {
    if (!RENDER_API) return;
    let skip = false;
    setVaultDetails(prev => {
      if (prev[vk]) { skip = true; return prev; }
      return {...prev, [vk]: {__loading:true}};
    });
    if (skip) return;
    try {
      const r = await fetch(`${RENDER_API}/api/vault/version/${encodeURIComponent(vk)}`, {headers: {...authHeaders()}, signal: AbortSignal.timeout(8000)});
      if (r.ok) {
        const d = await r.json();
        setVaultDetails(prev => ({...prev, [vk]: d}));
      } else {
        let msg = `HTTP ${r.status}`;
        try { const j = await r.json(); if (j?.error) msg = j.error; } catch {}
        setVaultDetails(prev => ({...prev, [vk]: {error: msg}}));
      }
    } catch (e) {
      setVaultDetails(prev => ({...prev, [vk]: {error: e.message || "Failed to load details"}}));
    }
  }, []);

  const deleteVaultVersion = useCallback(async (vk) => {
    if (!RENDER_API) return;
    if (!window.confirm(`Delete vault version "${vk}"? This removes the DB record AND the PDF file from the server.`)) return;
    try {
      const r = await fetch(`${RENDER_API}/api/vault/version/${encodeURIComponent(vk)}`, {method:"DELETE", headers: {...authHeaders()}, signal: AbortSignal.timeout(8000)});
      if (!r.ok) {
        let msg = `HTTP ${r.status}`;
        try { const j = await r.json(); if (j?.error) msg = j.error; } catch {}
        setVaultError(`Delete failed: ${msg}`);
        return;
      }
      setVaultDetails(prev => { const n = {...prev}; delete n[vk]; return n; });
      fetchVault();
    } catch (e) {
      setVaultError(`Delete failed: ${e.message || "network error"}`);
    }
  }, [fetchVault]);

  // Stable toggle for <VaultRow/>: opens the row, closes any other, fires
  // details fetch on first open. Passing this single callback (instead of
  // a fresh arrow per row) is what lets React.memo skip re-rendering rows
  // unrelated to the click.
  const toggleVaultRow = useCallback((versionKey, isOpen) => {
    if (isOpen) {
      setVaultExpanded(null);
    } else {
      setVaultExpanded(versionKey);
      fetchVaultVersionDetails(versionKey);
    }
  }, [fetchVaultVersionDetails]);

  // Set a vault version as the user's default resume (Issue #39 part A).
  // Round-trips through POST /api/profile so the backend validates the
  // key exists; on success we mirror the new value into local state to
  // flip the badge instantly. Pass empty string to clear the default.
  const setAsDefaultResume = useCallback(async (versionKey) => {
    if (!RENDER_API) return;
    setDefaultUpdating(true);
    setDefaultMsg(null);
    try {
      const r = await fetch(`${RENDER_API}/api/profile`, {
        method: "POST",
        headers: {"Content-Type": "application/json", ...authHeaders()},
        body: JSON.stringify({default_resume_version: versionKey || ""}),
        signal: AbortSignal.timeout(8000),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        setDefaultMsg({ok:false, text: d.error || `HTTP ${r.status}`});
        return;
      }
      setDefaultResumeVersion(versionKey || null);
      setDefaultMsg({ok:true, text: versionKey
        ? `✅ Default resume set to ${versionKey}`
        : "✅ Default resume cleared"});
    } catch (e) {
      setDefaultMsg({ok:false, text: e.message || "Network error"});
    } finally {
      setDefaultUpdating(false);
    }
  }, []);

  // Auto-clear the toast 4s after a successful set so it doesn't hang
  // around as visual noise.
  useEffect(() => {
    if (!defaultMsg || !defaultMsg.ok) return;
    const id = setTimeout(() => setDefaultMsg(null), 4000);
    return () => clearTimeout(id);
  }, [defaultMsg]);

  const compareVaultVersions = async () => {
    if (!RENDER_API || !vaultCmpA || !vaultCmpB || vaultCmpA === vaultCmpB) return;
    setVaultCmpLoading(true);
    setVaultCmpResult(null);
    try {
      const r = await fetch(`${RENDER_API}/api/vault/compare`, {
        method:"POST", headers:{"Content-Type":"application/json", ...authHeaders()},
        body: JSON.stringify({version_a: vaultCmpA, version_b: vaultCmpB}),
      });
      const d = await r.json();
      setVaultCmpResult(d);
    } catch (e) {
      setVaultCmpResult({error: e.message || "Compare failed"});
    } finally {
      setVaultCmpLoading(false);
    }
  };

  const uploadVaultPdf = async () => {
    if (!RENDER_API || !vaultUpFile || !vaultUpCompany.trim()) {
      setVaultUpStatus({ok:false, msg:"PDF file and company name required"});
      return;
    }
    // Mirrors MAX_PDF_BYTES in backend/storage/resume_vault.py:337 and
    // backend/routes/vault_routes.py:69. Frontend was artificially rejecting
    // 5–10 MB PDFs that the server would have accepted.
    const MAX_UPLOAD_BYTES = 10_000_000;
    if (vaultUpFile.size > MAX_UPLOAD_BYTES) {
      setVaultUpStatus({ok:false, msg:`❌ File too large (${(vaultUpFile.size/1024/1024).toFixed(1)} MB) — max 10 MB`});
      return;
    }
    setVaultUpLoading(true);
    setVaultUpStatus(null);
    try {
      const b64 = await new Promise((resolve, reject) => {
        const fr = new FileReader();
        fr.onload = () => {
          const res = fr.result || "";
          const idx = String(res).indexOf("base64,");
          resolve(idx >= 0 ? String(res).slice(idx + 7) : "");
        };
        fr.onerror = () => reject(new Error("Failed to read file"));
        fr.readAsDataURL(vaultUpFile);
      });
      const r = await fetch(`${RENDER_API}/api/vault/upload`, {
        method:"POST", headers:{"Content-Type":"application/json", ...authHeaders()},
        body: JSON.stringify({
          pdf_base64: b64,
          company: vaultUpCompany.trim(),
          role: vaultUpRole.trim() || undefined,
          filename: vaultUpFile.name,
        }),
      });
      const d = await r.json();
      if (r.ok) {
        setVaultUpStatus({ok:true, msg:`✅ Uploaded as ${d.version_key} (${d.skill_count||0} skills)`});
        setVaultUpFile(null);
        setVaultUpCompany("");
        setVaultUpRole("");
        if (vaultFileInputRef.current) vaultFileInputRef.current.value = "";
        setVaultDetails(prev => { const n = {...prev}; delete n[d.version_key]; return n; });
        setVaultCmpResult(null);
        fetchVault();
      } else {
        setVaultUpStatus({ok:false, msg:`❌ ${d.error || "Upload failed"}`});
      }
    } catch (e) {
      setVaultUpStatus({ok:false, msg:`❌ ${e.message}`});
    } finally {
      setVaultUpLoading(false);
    }
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

  // Pre-filter the company-history list so the JobCard call site doesn't
  // do an inline `.filter()` per render (fresh array → React.memo would
  // see a new prop identity on every parent render even when nothing
  // about that company actually changed). One memo keyed on the already-
  // memoized companyApps gives every card a stable === reference.
  const coHistoryByCompany = useMemo(() => {
    const m = {};
    for (const k in companyApps) {
      m[k] = companyApps[k].filter(a => a.status !== "saved");
    }
    return m;
  }, [companyApps]);

  // Group expanded "View ▾" rows by job external_id so each <JobCard/>
  // can receive only its own slice. Without this every card would see
  // the full map and React.memo's shallow `===` would break whenever any
  // other card toggled a sub-row. Cards with zero expanded rows share the
  // single EMPTY_OBJ identity to stay referentially stable across renders.
  const expandedByJob = useMemo(() => {
    const m = {};
    for (const k of Object.keys(expandedVersionRow)) {
      if (!expandedVersionRow[k]) continue;
      const i = k.indexOf(":");
      if (i < 0) continue;
      const extId = k.slice(0, i);
      const vk = k.slice(i + 1);
      if (!m[extId]) m[extId] = {};
      m[extId][vk] = true;
    }
    return m;
  }, [expandedVersionRow]);

  // Per-card slice of versionDetails. Without this every JobCard would
  // receive the full versionDetails map; any setVersionDetails(prev =>
  // ({...prev, [vk]: ...})) call from ANY card would produce a new map
  // identity and React.memo's shallow `vdMap !== nextVdMap` would force
  // every card to re-render. Build a slice keyed on each card's
  // expandedByJob entries — cards with no expanded rows share the frozen
  // EMPTY_OBJ identity so === stays stable.
  const vdMapByJob = useMemo(() => {
    const m = {};
    for (const extId in expandedByJob) {
      const rows = expandedByJob[extId];
      const slice = {};
      for (const vk in rows) {
        if (versionDetails[vk] !== undefined) slice[vk] = versionDetails[vk];
      }
      m[extId] = slice;
    }
    return m;
  }, [expandedByJob, versionDetails]);

  // Per-job slice of pdfDownloadState. Same memoization rationale as
  // vdMapByJob: each JobCard only sees download state for version_keys
  // in its own rankings, so a download triggered on card A never
  // invalidates card B's React.memo shallow check. Cards with no
  // download activity share the EMPTY_OBJ identity.
  const pdfStateByJob = useMemo(() => {
    const m = {};
    for (const extId in bestMatchByJob) {
      const rankings = bestMatchByJob[extId]?.data?.rankings;
      if (!Array.isArray(rankings) || rankings.length === 0) continue;
      const slice = {};
      for (const rk of rankings) {
        const vk = rk?.version_key;
        if (vk && pdfDownloadState[vk] !== undefined) slice[vk] = pdfDownloadState[vk];
      }
      if (Object.keys(slice).length > 0) m[extId] = slice;
    }
    return m;
  }, [bestMatchByJob, pdfDownloadState]);

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

  // Latest-cache ref so the batch effect below can read the current
  // jobFitByJob without subscribing to it as a dep (which would tear
  // down + rebuild the interval on every single fit result writing
  // back into state — 60 cards × one fit each = 60 effect rebuilds).
  const jobFitCacheRef = useRef(jobFitByJob);
  useEffect(() => { jobFitCacheRef.current = jobFitByJob; }, [jobFitByJob]);

  // Parent-level batch fetcher for the per-card job-fit chips (Issue
  // #39 part A). Walks the *visible* slice of `fj` (the same 60 cards
  // we actually render) and queues fetches for any job that doesn't
  // already have a fresh cached score for the current
  // `defaultResumeVersion`. Concurrency-capped by
  // `MAX_JOB_FIT_CONCURRENCY` via a useRef counter — the queue drains
  // itself as in-flight requests finish.
  //
  // R2 #6: event-driven refill replaces the old 250ms setInterval. We
  // install `pump` into `jobFitPumpRef`, and fetchJobFit()'s finally
  // block invokes the ref to retry immediately when a slot frees up.
  // No more wasted timer ticks while the queue is idle and steady.
  //
  // Critical: this effect intentionally OMITS `jobFitByJob` from its
  // deps and reads through `jobFitCacheRef` instead. Including it
  // would rebuild the effect on every result write-back.
  useEffect(() => {
    if (!RENDER_API || !defaultResumeVersion || tab !== "jobs") {
      // Make absolutely sure stale pump from a previous effect run
      // doesn't keep dequeuing after we navigated away.
      jobFitPumpRef.current = () => {};
      return;
    }
    const visible = fj.slice(0, JOB_FIT_VISIBLE_SLICE);
    let cancelled = false;
    const pump = () => {
      if (cancelled) return;
      const cache = jobFitCacheRef.current;
      for (const j of visible) {
        if (jobFitInflightRef.current >= MAX_JOB_FIT_CONCURRENCY) break;
        const extId = j.external_id;
        if (!extId) continue;
        if (jobFitPendingRef.current.has(extId)) continue;
        const existing = cache[extId];
        // skip if already fetched (or in flight) for the current default
        if (existing && existing.versionKey === defaultResumeVersion) continue;
        // mark pending BEFORE fetchJobFit() reads inflight to avoid two
        // pump() ticks queuing the same id while the first call hasn't
        // yet bumped the counter.
        jobFitPendingRef.current.add(extId);
        fetchJobFit(extId, j.description || j.title || "", defaultResumeVersion);
      }
    };
    jobFitPumpRef.current = pump;
    pump();
    return () => {
      cancelled = true;
      // Restore no-op so a late finally() from a request we're
      // abandoning doesn't trigger queueing into the wrong context.
      jobFitPumpRef.current = () => {};
    };
  }, [fj, defaultResumeVersion, tab, fetchJobFit]);

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
  const TABS = ["jobs","rare","analytics","companies","trends","tracker","vault","pipeline","monitor"];

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
                {tb==="monitor"?"🖥 Monitor":tb==="tracker"?`📋 Tracker${trackerCount?" ("+trackerCount+")":""}`:tb==="pipeline"?`🗂 Pipeline${applications.length?" ("+applications.length+")":""}`:tb==="rare"?`🎯 Rare${stats.rare_skills?" ("+stats.rare_skills+")":""}`:tb==="vault"?`📁 Vault${vaultFiles.length?" ("+vaultFiles.length+")":""}`:tb}
              </button>
            ))}
          </div>
          {/* Server settings */}
          <button onClick={() => setSetupOpen(true)} aria-label="Server settings"
            title={RENDER_API ? `Connected to ${RENDER_API}` : "Not connected — click to set up"}
            style={{padding:"8px 12px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:16,cursor:"pointer",flexShrink:0,marginRight:6}}>
            ⚙️{!RENDER_API && <span style={{marginLeft:4, fontSize:12, color:t.wm}}>setup</span>}
          </button>
          {/* Theme toggle */}
          <button onClick={()=>setMode(m=>m==="light"?"dark":"light")}
            style={{padding:"8px 14px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:16,cursor:"pointer",flexShrink:0}}>
            {mode==="light"?"🌙":"☀️"}
          </button>
        </div>
      </nav>
      {setupOpen && (
        <SetupPanel mode={RENDER_API ? "settings" : "blocking"} onClose={() => setSetupOpen(false)} t={t} />
      )}

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
            {fj.slice(0, JOB_FIT_VISIBLE_SLICE).map(j => {
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
            {fj.length > JOB_FIT_VISIBLE_SLICE && (
              <div style={{textAlign:"center",padding:18,color:t.txM,fontSize:15}}>
                Showing {JOB_FIT_VISIBLE_SLICE} of {fj.length} — use filters to narrow results
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

        {/* ════════════ VAULT ════════════ */}
        {tab==="vault" && (() => {
          const filteredFiles = filteredVaultFiles;

          const labelStyle = {fontSize:12,color:t.txM,fontWeight:600,textTransform:"uppercase",letterSpacing:".06em",marginBottom:6,display:"block"};
          const cardStyle = {background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS,marginBottom:18};
          const btnPrimary = {padding:"9px 18px",borderRadius:9,border:"none",background:t.gP,color:"#fff",fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:"inherit"};
          const btnSecondary = {padding:"7px 14px",borderRadius:8,border:`1px solid ${t.bd}`,background:"transparent",color:t.txS,fontSize:13,fontWeight:500,cursor:"pointer",fontFamily:"inherit"};
          const btnDanger = {padding:"7px 14px",borderRadius:8,border:`1px solid ${t.er}40`,background:`${t.er}10`,color:t.er,fontSize:13,fontWeight:500,cursor:"pointer",fontFamily:"inherit"};

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
        })()}

        {/* ════════════ PIPELINE ════════════ */}
        {tab==='pipeline' && (
          <PipelineTab state={{ t, applications, appLoading, fetchApplications, setApplications }} />
        )}

        {/* ════════════ MONITOR ════════════ */}
        {tab==='monitor' && (
          <MonitorTab state={{
            t,
            source, lastUpdated, health, data, allJobs,
            barVisible, scrapeProgress, scrapeMsg, triggerScrape,
            doctorLoading, doctorErr, doctorResult, runDoctor,
            purgeDays, setPurgeDays, purgeLoading, purgeMsg, purgeIsErr, runPurgeStale,
            reextractLoading, reextractMsg, runReextract,
            vacuumLoading, vacuumMsg, vacuumIsErr, runClearCache,
            reindexLoading, reindexMsg, runReindex,
          }} />
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
          .vault-cmp-grid{grid-template-columns:1fr!important}
          .vault-row{flex-direction:column;align-items:stretch!important}
          .vault-row button{width:100%}
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
