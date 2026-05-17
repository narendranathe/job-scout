/**
 * AnalyticsTab — 4 charts: ATS pie, salary bars, 30-day posting trend, key metrics.
 */
import {
  Area, AreaChart, Bar, BarChart, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { ATS_META } from "../lib/jobConstants.js";

export function AnalyticsTab({ state }) {
  const { t, data, dist, stats, ttS } = state;

  return (
    <div className="two-col">
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>ATS Distribution</h3>
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie data={dist.ats||[]} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={95} paddingAngle={3} stroke="none">
              {(dist.ats||[]).map((d,i)=><Cell key={i} fill={(ATS_META[d.name]||ATS_META.unknown).c} opacity={0.75}/>)}
            </Pie>
            <Tooltip contentStyle={ttS}/>
          </PieChart>
        </ResponsiveContainer>
        <div style={{display:"flex",gap:10,flexWrap:"wrap",justifyContent:"center",marginTop:10}}>
          {(dist.ats||[]).map(d=>{const m=ATS_META[d.name]||ATS_META.unknown;return<span key={d.name} style={{fontSize:13,color:m.c,fontWeight:600}}>{m.i} {m.l}: {d.value}</span>;})}
        </div>
      </div>
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Salary Distribution</h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={dist.salary_buckets||[]}>
            <XAxis dataKey="range" tick={{fill:t.txM,fontSize:11}} axisLine={{stroke:t.bd}} tickLine={false}/>
            <YAxis tick={{fill:t.txM,fontSize:11}} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Bar dataKey="count" radius={[6,6,0,0]}>
              {(dist.salary_buckets||[]).map((d,i)=><Cell key={i} fill={[t.wm,t.wm,t.acS,t.ok,t.ac,t.vi][i]||t.ac} opacity={0.6}/>)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>30-Day Posting Trend</h3>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data?.trend||[]}>
            <XAxis dataKey="date" tick={{fill:t.txM,fontSize:11}} axisLine={{stroke:t.bd}} tickLine={false} tickFormatter={v=>v.slice(5)}/>
            <YAxis tick={{fill:t.txM,fontSize:11}} axisLine={false} tickLine={false}/>
            <Tooltip contentStyle={ttS}/>
            <Area type="monotone" dataKey="count" stroke={t.acS} fill={`${t.acS}15`} strokeWidth={2}/>
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div style={{background:t.cd,borderRadius:14,padding:24,border:`1px solid ${t.bd}`,boxShadow:t.shS}}>
        <h3 style={{margin:"0 0 18px",fontSize:13,color:t.txM,fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>Key Metrics</h3>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
          {[
            [`${stats.h1b_pct||0}%`,"H1B Sponsors",t.vi],
            [`${stats.remote_pct||0}%`,"Remote Jobs",t.ok],
            [`${stats.companies_tracked||0}`,"Companies",t.ac],
            [`${stats.high_match||0}`,`High Match (top 10% • ≥${stats.high_match_threshold?.toFixed(2)||"0.70"})`,t.wm],
          ].map(([v,l,c])=>(
            <div key={l} style={{padding:18,borderRadius:12,background:`${c}08`,border:`1px solid ${c}20`,textAlign:"center"}}>
              <div style={{fontSize:34,fontWeight:700,color:c,fontFamily:"'Playfair Display',serif"}}>{v}</div>
              <div style={{fontSize:13,color:t.txM,marginTop:4}}>{l}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
