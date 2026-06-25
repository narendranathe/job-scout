const DIALS = [
  { key: 'skills',       label: 'Skills',        hint: 'Core + secondary skill match' },
  { key: 'role_fit',     label: 'Role Fit',       hint: 'Title + experience level' },
  { key: 'logistics',    label: 'Logistics',      hint: 'Location + sponsorship + salary' },
  { key: 'company_tier', label: 'Company Tier',   hint: 'Platinum tier bonus' },
]

export default function ScoreWeightDials({ weights, onChange }) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0) || 1

  const update = (key, raw) => onChange({ ...weights, [key]: Number(raw) })

  return (
    <div style={{ marginTop: 12 }}>
      <p style={{ margin: '0 0 8px', fontSize: 12, color: '#888', fontWeight: 600 }}>TUNE RESULTS</p>
      {DIALS.map(({ key, label, hint }) => {
        const pct = Math.round((weights[key] ?? 0) / total * 100)
        return (
          <div key={key} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
              <span style={{ fontWeight: 500 }}>{label} <span style={{ color: '#aaa', fontWeight: 400 }}>— {hint}</span></span>
              <span style={{ color: '#555', minWidth: 32, textAlign: 'right' }}>{pct}%</span>
            </div>
            <input
              type="range" min={0} max={100}
              value={weights[key] ?? 25}
              onChange={e => update(key, e.target.value)}
              style={{ width: '100%', accentColor: '#000' }}
            />
          </div>
        )
      })}
    </div>
  )
}
