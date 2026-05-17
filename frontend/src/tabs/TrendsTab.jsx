/**
 * TrendsTab — area chart of jobs posted over time + top companies/locations.
 */
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { LogoImg } from "../components/LogoImg.jsx";

export function TrendsTab({ state }) {
  const { t, data, dist, ttS } = state;

  return (
    <div className="trends-col">
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Jobs Posted by Date</h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={data?.trend||[]}>
            <XAxis dataKey="date" tick={{fill:t.txM,fontSize:11}} axisLine={{stroke:t.bd}} tickLine={false} tickFormatter={v=>v.slice(5)}/>
            <YAxis tick={{fill:t.txM,fontSize:11}} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:14}}>
        <div style={{background:t.cd,borderRadius:14,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1}}>
          <h3 style={{margin:"0 0 14px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Top Companies</h3>
          {(data?.top_companies||[]).slice(0,8).map((co,i)=>(
            <div key={co.name} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none"}}>
              <LogoImg name={co.name} size={22} t={t}/>
              <span style={{fontSize:14,fontWeight:600,color:t.tx,flex:1}}>{co.name}</span>
              <span style={{fontSize:14,fontWeight:700,color:t.ac}}>{co.count}</span>
            </div>
          ))}
        </div>
        <div style={{background:t.cd,borderRadius:14,padding:20,border:`1px solid ${t.bd}`,boxShadow:t.shS,flex:1}}>
          <h3 style={{margin:"0 0 14px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Top Locations</h3>
          {(dist.cities||[]).slice(0,8).map((c,i)=>(
            <div key={c.name} style={{display:"flex",justifyContent:"space-between",padding:"9px 0",borderBottom:i<7?`1px solid ${t.bd}`:"none"}}>
              <span style={{fontSize:14,fontWeight:600,color:t.tx}}>{c.name}</span>
              <span style={{fontSize:14,fontWeight:700,color:t.acS}}>{c.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
