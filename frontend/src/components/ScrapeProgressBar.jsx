/**
 * Scrape progress bar (Manual Triggers / Monitor tab).
 *
 * Pure-presentational component — admin op cards reuse it with their own
 * snapshot shape (same {is_running, current_*, *_done, *_total, found,
 * new, eta_seconds} contract). The fill width transitions smoothly
 * between polls so a slow tick doesn't visually stutter. Caller is
 * responsible for hiding/showing it; this component just renders the
 * bar + labels for the given snapshot.
 */
export function ScrapeProgressBar({ snap, t }) {
  if (!snap) return null;
  const total = Math.max(0, snap.companies_total ?? 0);
  const done  = Math.max(0, Math.min(snap.companies_done ?? 0, total || Infinity));
  const pct   = total > 0 ? Math.min(100, Math.max(0, (done / total) * 100)) : 0;
  const eta   = snap.eta_seconds;
  return (
    <div style={{marginTop:4}}>
      <div style={{
        display:"flex",justifyContent:"space-between",alignItems:"baseline",
        gap:8,marginBottom:8,fontSize:13,color:t.txS,lineHeight:1.4,
        flexWrap:"wrap",
      }}>
        <div style={{minWidth:0,flex:"1 1 auto",wordBreak:"break-word",overflowWrap:"anywhere"}}>
          <strong style={{color:t.tx}}>
            {snap.current_company || "Initializing"}
          </strong>
          {" • "}{done}/{total || "?"} companies
        </div>
        {eta != null && eta > 0 && total > done && (
          <div style={{color:t.txM,fontVariantNumeric:"tabular-nums",flexShrink:0}}>
            ETA {Math.round(eta)}s
          </div>
        )}
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        style={{
          width:"100%",height:10,borderRadius:6,
          background:t.bd,overflow:"hidden",
          border:`1px solid ${t.bd}`,
        }}
      >
        <div style={{
          height:"100%",width:`${pct}%`,
          background:t.ac,
          // Transition slightly shorter than the 1.5s poll cadence so the
          // bar finishes "catching up" right as the next snapshot arrives —
          // no visible stall, no overshoot.
          transition:"width 1400ms cubic-bezier(.4,0,.2,1)",
          borderRadius:6,
        }}/>
      </div>
      <div style={{
        marginTop:8,fontSize:13,color:t.txS,lineHeight:1.4,
      }}>
        {snap.found ?? 0} jobs found
        {(snap.new ?? 0) > 0 && <> · <span style={{color:t.ok,fontWeight:600}}>{snap.new} new</span></>}
        {(snap.errors ?? 0) > 0 && <> · <span style={{color:t.er}}>{snap.errors} errors</span></>}
        {snap.mode && <span style={{color:t.txM}}> · {snap.mode}</span>}
      </div>
    </div>
  );
}
