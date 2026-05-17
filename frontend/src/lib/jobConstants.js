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
