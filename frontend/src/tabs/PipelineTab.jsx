/**
 * PipelineTab — kanban view of applications grouped by status stage.
 *
 * Extracted from App.jsx. Owns its PIPELINE_STAGES constant (only used
 * here). Status changes are dispatched via setApplications + PATCH to
 * /api/applications/<ext_id>; both are passed in from App() via state.
 */
import { RENDER_API } from "../lib/api.js";

const PIPELINE_STAGES = [
  { key: 'saved',      label: 'Saved',        color: '#6b7280' },
  { key: 'applied',    label: 'Applied',      color: '#3b82f6' },
  { key: 'interview',  label: 'Phone Screen', color: '#f59e0b' },
  { key: 'offer',      label: 'Offer',        color: '#22c55e' },
  { key: 'rejected',   label: 'Rejected',     color: '#ef4444' },
];

export function PipelineTab({ state }) {
  const { t, applications, appLoading, fetchApplications, setApplications } = state;

  return (
    <div>
      {/* Stats bar */}
      <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', flexWrap: 'wrap', fontSize: '14px', color: t.txS }}>
        <span>📨 Applied this week: <strong style={{color: t.tx}}>{applications.filter(a =>
          a.status === 'applied' && a.applied_at &&
          new Date(a.applied_at) > new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)
        ).length}</strong></span>
        <span>📞 In phone screen: <strong style={{color: t.tx}}>{applications.filter(a => a.status === 'interview').length}</strong></span>
        <span>🎯 Offers: <strong style={{color: t.tx}}>{applications.filter(a => a.status === 'offer').length}</strong></span>
        <span>📋 Total tracked: <strong style={{color: t.tx}}>{applications.length}</strong></span>
        {appLoading && <span style={{color: t.txM, fontStyle: 'italic'}}>Loading...</span>}
        {!RENDER_API && <span style={{color: t.er}}>⚠️ Set VITE_RENDER_URL to enable pipeline sync</span>}
        {RENDER_API && !appLoading && (
          <button onClick={fetchApplications}
            style={{padding:'3px 10px',borderRadius:6,border:`1px solid ${t.bd}`,background:'transparent',color:t.txM,fontSize:12,cursor:'pointer',fontFamily:'inherit'}}>
            ↻ Refresh
          </button>
        )}
      </div>

      {/* Kanban columns */}
      <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', alignItems: 'flex-start', paddingBottom: '12px' }}>
        {PIPELINE_STAGES.map(stage => {
          const stageApps = applications.filter(a => a.status === stage.key);
          return (
            <div key={stage.key} style={{
              minWidth: '200px', flex: '0 0 200px',
              background: 'rgba(255,255,255,0.03)',
              border: `1px solid ${stage.color}30`,
              borderRadius: '10px', padding: '12px',
            }}>
              <div style={{
                fontWeight: '700', fontSize: '12px', textTransform: 'uppercase',
                letterSpacing: '0.8px', color: stage.color, marginBottom: '10px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                {stage.label}
                <span style={{
                  background: stage.color + '22', color: stage.color,
                  borderRadius: '10px', padding: '1px 7px', fontSize: '11px',
                }}>{stageApps.length}</span>
              </div>
              {stageApps.length === 0 && (
                <div style={{fontSize:'12px',color:t.txM,fontStyle:'italic',padding:'8px 4px',textAlign:'center'}}>empty</div>
              )}
              {stageApps.map(app => (
                <div key={app.external_id} style={{
                  background: t.cd,
                  borderRadius: '6px', padding: '10px', marginBottom: '8px',
                  borderLeft: `3px solid ${stage.color}`,
                  boxShadow: t.shS,
                }}>
                  <div style={{ fontWeight: '600', fontSize: '13px', marginBottom: '2px', color: t.tx }}>
                    {app.company}
                    {app.tier === 'platinum' && (
                      <span style={{
                        background: 'linear-gradient(135deg, #b8860b, #ffd700)',
                        color: '#1a1a1a', fontSize: '9px', fontWeight: '700',
                        padding: '1px 4px', borderRadius: '3px', marginLeft: '5px',
                      }}>PLATINUM</span>
                    )}
                  </div>
                  <div style={{ fontSize: '11px', color: t.txM, marginBottom: '6px' }}>
                    {app.title}
                  </div>
                  {(app.salary_min > 0) && (
                    <div style={{ fontSize: '11px', color: '#22c55e', marginBottom: '4px' }}>
                      ${Math.round(app.salary_min / 1000)}K–${Math.round((app.salary_max || app.salary_min) / 1000)}K
                    </div>
                  )}
                  <select
                    value={app.status}
                    onClick={e => e.stopPropagation()}
                    onChange={async (e) => {
                      const newStatus = e.target.value;
                      setApplications(prev => prev.map(a =>
                        a.external_id === app.external_id ? { ...a, status: newStatus } : a
                      ));
                      try {
                        await fetch(`${RENDER_API}/api/applications/${app.external_id}`, {
                          method: 'PATCH',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ status: newStatus }),
                        });
                      } catch (err) {
                        console.warn('Failed to update status:', err);
                      }
                    }}
                    style={{
                      width: '100%', fontSize: '11px', padding: '3px',
                      background: t.inp, color: t.tx,
                      border: `1px solid ${t.bd}`, borderRadius: '4px',
                      fontFamily: 'inherit', cursor: 'pointer',
                    }}
                  >
                    {PIPELINE_STAGES.map(s => (
                      <option key={s.key} value={s.key}>{s.label}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
