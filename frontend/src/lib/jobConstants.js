/**
 * Shared constants and helpers used by JobCard, JobsTab, and the
 * relevance/filtering logic. Extracted from App.jsx as part of the
 * App.jsx split so the per-tab modules can import without dragging in
 * the whole App.jsx surface.
 *
 * Pure data + pure functions only. No React, no DOM, no fetch.
 */

/**
 * ATS metadata: per-platform display label, color, and icon. Used by
 * JobCard chips and the ATS-distribution chart in Analytics.
 */
export const ATS_META = {
  greenhouse:      {l:"Greenhouse",    c:"#3D8B6E",i:"🌿"},
  lever:           {l:"Lever",         c:"#6B5B8D",i:"⚡"},
  ashby:           {l:"Ashby",         c:"#C0776E",i:"💎"},
  smartrecruiters: {l:"SmartRecr.",    c:"#5B7B8D",i:"🎯"},
  bamboohr:        {l:"BambooHR",      c:"#73B761",i:"🎋"},
  workday:         {l:"Workday",       c:"#E86339",i:"💼"},
  unknown:         {l:"Other",         c:"#7A7A7A",i:"📄"},
};

/**
 * Role categories — keyword-based bucketing for filter chips + the
 * per-card `_cat` annotation. Keep IDs short (used as data keys).
 */
export const ROLE_CATS = [
  {id:"de",  label:"Data Engineer",   kw:["data engineer","etl engineer","data pipeline","data infrastructure","big data","analytics platform"]},
  {id:"ml",  label:"ML / AI",         kw:["ml engineer","machine learning","ai engineer","ai platform","mlops","llm","generative ai"]},
  {id:"ae",  label:"Analytics Eng",   kw:["analytics engineer","business intelligence","bi engineer","bi developer"]},
  {id:"ds",  label:"Data Scientist",  kw:["data scientist","research scientist","applied scientist"]},
  {id:"pe",  label:"Platform / Infra",kw:["platform engineer","infrastructure engineer","cloud engineer","devops","sre","site reliability"]},
  {id:"swe", label:"Software Eng",    kw:["software engineer","backend engineer","full stack","fullstack"]},
  {id:"da",  label:"Data Architect",  kw:["data architect","solutions architect"]},
];

/**
 * Click-event helper: stops propagation so a button click inside an
 * expandable card doesn't also toggle the card open/close state.
 */
export function stopProp(e) { e.stopPropagation(); }

/**
 * Shared stable empty-object/array references for JobCards with no
 * expanded rows / no company history. Sharing identity across cards
 * keeps React.memo's shallow === happy — otherwise every card render
 * would get a fresh ``{}`` and the memoization would never engage.
 */
export const EMPTY_OBJ = Object.freeze({});
export const EMPTY_ARR = Object.freeze([]);

/**
 * Default-resume job-fit chip color scale (Issue #39 part A). ≥75% green,
 * 50–75% yellow, <50% red. Returns plain hex strings derived from `pct` +
 * the active theme so React.memo doesn't have to track new object
 * identities each render.
 *
 * R2: also returns a `label` ("Strong"/"Moderate"/"Weak") and `icon`
 * (colored circle emoji) so the chip carries non-color signals — WCAG
 * 1.4.1 (use of color) requires that meaning isn't conveyed by color
 * alone. Screen readers and color-blind users see the same information.
 */
export function jobFitTone(pct, t) {
  if (pct >= 75) return { fg: t.ok, bg: `${t.ok}18`, bd: `${t.ok}40`, label: "Strong",   icon: "🟢" };
  if (pct >= 50) return { fg: t.wm, bg: `${t.wm}18`, bd: `${t.wm}40`, label: "Moderate", icon: "🟡" };
  return            { fg: t.er, bg: `${t.er}18`, bd: `${t.er}40`, label: "Weak",     icon: "🔴" };
}

/**
 * Application status colors + labels. Shared between JobCard's status
 * pills, the Tracker tab's status column, and the Pipeline tab kanban.
 * Status keys map to DB column values; do not change keys without a
 * matching backend migration.
 */
export const ST_COLOR = {saved:"#4A7C9F",applied:"#3D8B6E",interview:"#C4A77D",offer:"#2D5A4A",rejected:"#B85450"};
export const ST_LABEL = {saved:"🔖 Save",applied:"✅ Applied",interview:"📞 Interview",offer:"🎉 Offer",rejected:"✗ Pass"};

/**
 * "Platinum" tier check — jobs scraped from Tier 0 dream companies are
 * pre-tagged on the backend. Highlighted in the JobCard meta row.
 */
export const isPlatinum = (job) => job?.tier === 'platinum';

/**
 * High-comp filter — used by the rare-roles tab to surface FAANG-level
 * compensation. Either platinum tier OR explicit salary band over 220K.
 */
export const isHighComp = (job) => (job?.salary_max >= 220000) || isPlatinum(job);

/**
 * Heuristic visa-sponsorship signal for a job that has no explicit
 * sponsorship flag. Looks for the obvious "we sponsor" phrases in the
 * description. Cheap; runs on every JobCard render — keep it short.
 */
export function likelySponsor(job){
  const text=((job.description||"")+" "+(job.company||"")).toLowerCase();
  if(/no sponsorship|not sponsor|unable to sponsor|citizen only/.test(text))return false;
  if(/visa sponsor|h1b|h-1b|sponsorship available/.test(text))return true;
  return["uber","meta","google","amazon","apple","microsoft","netflix","stripe","anthropic","openai","datadog","snowflake","databricks","two sigma","citadel","bloomberg","capital one","palantir","coinbase"].includes((job.company||"").toLowerCase());
}

// ─── Dream company ranking (41 entries, personal priority order) ─────────────
export const DREAM_COMPANY_RANK = Object.freeze({
  "anthropic": 1, "openai": 2, "stripe": 3, "databricks": 4, "snowflake": 5,
  "goldman sachs": 6, "walmart": 7, "apple": 8, "nvidia": 9, "google": 10,
  "microsoft": 11, "disney": 12, "citadel": 13, "citadel securities": 14,
  "aqr capital": 15, "hudson river trading": 16, "jane street": 17,
  "two sigma": 18, "jump trading": 19, "sig": 20, "imc trading": 21,
  "bridgewater associates": 22, "flow traders": 23, "tower research capital": 24,
  "millennium management": 25, "point72": 26, "optiver": 27,
  "virtu financial": 28, "pimco": 29, "netflix": 30, "meta": 31,
  "spotify": 32, "fidelity": 33, "uber": 34, "bloomberg": 35,
  "morgan stanley": 36, "blackrock": 37, "doordash": 38, "amazon": 39,
  "salesforce": 40, "jp morgan chase": 41,
});

export function getDreamRank(company) {
  return DREAM_COMPANY_RANK[(company || "").toLowerCase()] ?? null;
}

// ─── Skill lists mirroring backend/core/relevance.py weights ─────────────────
export const CORE_SKILLS = [
  "python","sql","spark","pyspark","kafka","airflow","etl","data pipeline",
  "data lake","data warehouse","azure","aws","databricks","delta lake","microsoft fabric",
];

export const SECONDARY_SKILLS = [
  "docker","kubernetes","terraform","ci/cd","dbt","snowflake","redshift","bigquery",
  "postgresql","sql server","mongodb","fastapi","flask","rest api","git","linux","bash",
  "mlflow","mlops","machine learning","pytorch","tensorflow","scikit-learn","tableau",
  "powerbi","looker","flink","kinesis","data mesh","numpy","pandas","scipy",
  "quantitative","statistical modeling","backtesting",
];

// Score weights (mirrors relevance.py)
const W = { core:0.36, secondary:0.17, title:0.15, location:0.10, experience:0.10, sponsorship:0.08, salary:0.04, platinum:0.08 };

/**
 * Estimate the contribution of each scoring component for a job row.
 * Returns an array of rows ready to render as mini-bar breakdown.
 * Frontend-only: uses matched_skills + job fields; never calls the backend.
 */
export function estimateScoreBreakdown(j) {
  const matched = (j.matched_skills || []).map(s => s.toLowerCase());
  const title = (j.title || "").toLowerCase();
  const desc = (j.description || "").toLowerCase();
  const loc = ((j._loc && j._loc.display) || j.location || "").toLowerCase();

  const coreHits = CORE_SKILLS.filter(s => matched.some(m => m.includes(s)));
  const secHits = SECONDARY_SKILLS.filter(s => matched.some(m => m.includes(s)));

  const coreEst = Math.min(W.core, (coreHits.length / 15) * W.core);

  const secEst = Math.min(W.secondary, (secHits.length / 35) * W.secondary);

  let titleEst = 0; let titleDriver = "no match";
  if (/data engineer/.test(title))       { titleEst = W.title;       titleDriver = "data engineer"; }
  else if (/ml engineer|machine learning engineer/.test(title)) { titleEst = W.title * (14/15); titleDriver = "ml engineer"; }
  else if (/quant/.test(title))          { titleEst = W.title * (13/15); titleDriver = "quant"; }
  else if (/analytics engineer/.test(title)) { titleEst = W.title * (12/15); titleDriver = "analytics engineer"; }
  else if (/platform engineer/.test(title))  { titleEst = W.title * (8/15);  titleDriver = "platform engineer"; }
  else if (/engineer|scientist/.test(title)) { titleEst = W.title * (5/15);  titleDriver = "engineer/scientist"; }

  let locEst = 0; let locDriver = "no match";
  if (/remote/.test(loc) || j._loc?.isRemote) { locEst = W.location; locDriver = "remote"; }
  else if (/dallas|austin|tx|texas/.test(loc)) { locEst = W.location * 0.8; locDriver = "TX metro"; }

  let expEst = 0; let expDriver = "none";
  const expText = title + " " + desc;
  if (/\bstaff\b|\bprincipal\b|\blead\b/.test(expText))    { expEst = W.experience;       expDriver = "staff/principal/lead"; }
  else if (/\bsenior\b|\bsr\.?\b/.test(expText))           { expEst = W.experience * 0.9; expDriver = "senior"; }
  else if (/4\+\s*years|5\+\s*years/.test(expText))        { expEst = W.experience * 0.7; expDriver = "4+ years"; }

  const sponsorFlag = j.sponsorship;
  let sponsEst = 0; let sponsDriver = "neutral";
  if (sponsorFlag === 1)  { sponsEst =  W.sponsorship; sponsDriver = "H1B positive"; }
  else if (sponsorFlag === -1) { sponsEst = -W.sponsorship; sponsDriver = "no sponsorship"; }

  let salEst = 0; let salDriver = "no salary";
  const smax = j.salary_max || 0;
  if (smax >= 300000)      { salEst = W.salary;       salDriver = `$${Math.round(smax/1000)}K max`; }
  else if (smax >= 220000) { salEst = W.salary * 0.8; salDriver = `$${Math.round(smax/1000)}K max`; }
  else if (smax >= 150000) { salEst = W.salary * 0.5; salDriver = `$${Math.round(smax/1000)}K max`; }

  const platEst = isPlatinum(j) ? W.platinum : 0;

  const rows = [
    { label:"Core skills",      maxPct:36, estPct:Math.round(coreEst*100),    driver: coreHits.length ? `${coreHits.length}/15: ${coreHits.slice(0,4).join(", ")}` : "none matched" },
    { label:"Secondary skills", maxPct:17, estPct:Math.round(secEst*100),     driver: secHits.length  ? `${secHits.length}/35: ${secHits.slice(0,3).join(", ")}` : "none matched" },
    { label:"Title relevance",  maxPct:15, estPct:Math.round(titleEst*100),   driver: titleDriver },
    { label:"Location",         maxPct:10, estPct:Math.round(locEst*100),     driver: locDriver },
    { label:"Experience level", maxPct:10, estPct:Math.round(expEst*100),     driver: expDriver },
    { label:"Sponsorship",      maxPct: 8, estPct:Math.round(sponsEst*100),   driver: sponsDriver },
    { label:"Salary tier",      maxPct: 4, estPct:Math.round(salEst*100),     driver: salDriver },
    { label:"Platinum boost",   maxPct: 8, estPct:Math.round(platEst*100),    driver: isPlatinum(j) ? "Tier 0 company" : "not tier 0" },
  ];
  return rows;
}

/**
 * JobCard's inline style record. Frozen so React.memo never gets a new
 * identity from a recompute — every card shares the same prototype.
 */
export const JC_STYLES = Object.freeze({
  topRow: {padding:"16px 20px",display:"flex",justifyContent:"space-between",alignItems:"center",gap:12},
  titleRow: {display:"flex",alignItems:"center",gap:14,flex:1,minWidth:0},
  titleInner: {flex:1,minWidth:0},
  titleLine: {display:"flex",alignItems:"center",gap:8,marginBottom:5,flexWrap:"wrap"},
  metaRow: {display:"flex",gap:12,fontSize:14,flexWrap:"wrap",alignItems:"center"},
  scoreCluster: {display:"flex",alignItems:"center",gap:10,flexShrink:0},
  platinum: {
    background:'linear-gradient(135deg, #b8860b, #ffd700)',
    color:'#1a1a1a',fontSize:'10px',fontWeight:'700',padding:'2px 6px',
    borderRadius:'4px',marginLeft:'6px',letterSpacing:'0.5px',textTransform:'uppercase',
  },
  appliedBtn: {
    background:'rgba(59,130,246,0.15)', color:'#3b82f6',
    border:'1px solid rgba(59,130,246,0.3)', borderRadius:'4px',
    padding:'3px 8px', fontSize:'11px', cursor:'pointer', marginLeft:'6px',
  },
  skillsRow: {display:"flex",gap:6,flexWrap:"wrap",margin:"14px 0 10px"},
  actionsRow: {display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",marginTop:10},
  statusBtnsRow: {display:"flex",gap:6,flexWrap:"wrap"},
  rkBar: {flex:1,height:8,borderRadius:5,overflow:"hidden"},
  vdGrid: {display:"flex",flexDirection:"column",gap:4},
});
