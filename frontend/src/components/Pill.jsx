/**
 * Pill — small status/tag chip used across the dashboard. Memoless;
 * inline-rendered everywhere from JobCard meta rows to filter chips
 * to the SetupPanel error banner.
 *
 * Props:
 *   ch  — children/text content
 *   c   — accent color override (defaults to t.ac)
 *   t   — theme tokens (light or dark)
 *   big — boolean, slightly larger padding + font
 */
export const Pill = ({ch,c,t,big}) => (
  <span style={{display:"inline-block",fontSize:big?14:13,fontWeight:600,padding:big?"5px 12px":"4px 10px",borderRadius:6,background:`${c||t.ac}14`,color:c||t.ac,whiteSpace:"nowrap"}}>{ch}</span>
);
