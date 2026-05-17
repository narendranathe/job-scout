/**
 * Theme tokens — extracted from App.jsx as part of the split.
 *
 * Two palettes (light + dark), each a flat record of color tokens plus
 * two functions (sBg, sTx) that map a relevance score to background +
 * text colors. The score helpers stay in this module so any new tab
 * extracted into its own file can pull tokens AND score colors from one
 * import: `import { TH } from "./lib/theme.js"`.
 *
 * Color choices preserved exactly — same hex values, same gradient
 * strings, same shadow tokens. Renames would risk a visual diff.
 */
export const TH = {
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
