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
