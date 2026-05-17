/**
 * CompaniesTab — searchable grid of company cards with sample roles.
 */
import { LogoImg } from "../components/LogoImg.jsx";

export function CompaniesTab({ state }) {
  const { t, data, enriched, cq, sCq, iS } = state;

  return (
    <div>
      <div style={{marginBottom:18}}>
        <input placeholder="Search companies..." value={cq} onChange={e=>sCq(e.target.value)} style={{...iS,maxWidth:360}}/>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))",gap:14}}>
        {(data?.top_companies||[]).filter(c=>!cq||c.name.toLowerCase().includes(cq.toLowerCase())).map(co=>(
          <div key={co.name} style={{background:t.cd,borderRadius:14,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}>
              <div style={{display:"flex",alignItems:"center",gap:12}}>
                <LogoImg name={co.name} size={36} t={t}/>
                <h4 style={{margin:0,fontSize:16,fontWeight:700,color:t.tx,fontFamily:"'Playfair Display',serif"}}>{co.name}</h4>
              </div>
              <div style={{background:t.acL,padding:"5px 12px",borderRadius:8}}>
                <span style={{fontSize:16,fontWeight:700,color:t.ac}}>{co.count}</span>
                <span style={{fontSize:11,color:t.txM,marginLeft:4}}>jobs</span>
              </div>
            </div>
            <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
              {enriched.filter(j=>j.company===co.name).slice(0,4).map((j,i)=>(
                <span key={i} style={{fontSize:12,padding:"3px 10px",borderRadius:6,background:t.bgS,color:t.txS,border:`1px solid ${t.bd}`}}>{j.title}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
