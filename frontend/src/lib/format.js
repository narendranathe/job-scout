/**
 * Display formatting helpers — extracted from App.jsx.
 *
 * Pure functions, no React. Everything here is safe to call from any
 * render path. ``timeAgo`` reads ``Date.now()`` so callers that need
 * stable rendering across re-renders should pass a frozen timestamp.
 */

/**
 * Format a USD salary as a compact dollar-K string. Returns "—" for
 * falsy input so JSX can render `{fmtSal(job.salary_min)}` without
 * a conditional.
 */
export const fmtSal = (n) => n ? `$${(n / 1000).toFixed(0)}K` : "—";

/**
 * Human-friendly "5m ago" / "2h ago" / "3d ago" for any ISO timestamp.
 * Falls back to "" when the input is empty so chips can render blank
 * instead of "NaNd ago".
 */
export const timeAgo = (iso) => {
  if (!iso) return "";
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
};
