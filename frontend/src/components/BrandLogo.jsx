/**
 * JobScout SVG logo — a stylized magnifying glass with crosshair.
 * Pure presentational component. ``t`` is the active theme (light or
 * dark) so the accent color tracks the user's theme toggle.
 */
export function BrandLogo({ size = 32, t }) {
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
