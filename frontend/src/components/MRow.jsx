/**
 * MRow + Chk — small rows used in the Monitor tab. Pure presentational,
 * no state.
 */

/**
 * One label/value row with a colored value. Used in the Monitor tab's
 * health summary card.
 */
export function MRow({l,v,c,t}) {
  return (
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"10px 0",borderBottom:`1px solid ${t.bd}`}}>
      <span style={{fontSize:15,color:t.txM,fontWeight:500}}>{l}</span>
      <span style={{fontSize:15,fontWeight:600,color:c}}>{v}</span>
    </div>
  );
}

/**
 * Checklist row with done/not-done indicator + main label + sub-detail.
 * Used by the Monitor tab to render setup progress checklist.
 */
export function Chk({done,label,detail,t}) {
  return (
    <div style={{display:"flex",alignItems:"flex-start",gap:12}}>
      <span style={{fontSize:18,marginTop:1}}>{done?"✅":"⬜"}</span>
      <div>
        <div style={{fontSize:15,fontWeight:600,color:done?t.ok:t.txM}}>{label}</div>
        <div style={{fontSize:13,color:t.txM,marginTop:3}}>{detail}</div>
      </div>
    </div>
  );
}
