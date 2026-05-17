/**
 * Chips — multi-select filter UI. Used by the Jobs tab for category +
 * location filters and a few other places. Pinned items float to the
 * top of the list (sorted via useMemo so the recompute is amortized).
 *
 * Props:
 *   options  — Array<{id, label, count?}>
 *   selected — Array<string> of selected ids
 *   onChange — (newSelected) => void
 *   t        — theme tokens
 *   label    — optional uppercase label above the chip row
 *   pinned   — optional Array<string> of ids that float to the top
 */
import { useMemo } from "react";

export function Chips({options,selected,onChange,t,label,pinned}) {
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
