import { useState } from 'react'
import CompanyPriorityPanel from '../components/CompanyPriorityPanel'
import ScoreWeightDials from '../components/ScoreWeightDials'

function avatarColor(email) {
  let h = 0
  for (let i = 0; i < email.length; i++) h = email.charCodeAt(i) + ((h << 5) - h)
  const palette = ['#e74c3c','#3498db','#2ecc71','#9b59b6','#f39c12','#1abc9c','#e67e22','#34495e']
  return palette[Math.abs(h) % palette.length]
}

function ChipEditor({ chips, onChange, placeholder }) {
  const [input, setInput] = useState('')

  const add = (raw) => {
    const val = raw.trim().toLowerCase()
    if (!val || chips.includes(val)) return
    onChange([...chips, val])
    setInput('')
  }

  const onKey = (e) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(input) }
    if (e.key === 'Backspace' && !input && chips.length) onChange(chips.slice(0, -1))
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
      {chips.map(c => (
        <span key={c} style={{
          background: '#3498db22', color: '#3498db', borderRadius: 20,
          padding: '3px 10px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4,
        }}>
          {c}
          <button onClick={() => onChange(chips.filter(x => x !== c))}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#3498db', padding: 0, fontSize: 14, lineHeight: 1 }}>
            ×
          </button>
        </span>
      ))}
      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={onKey}
        onBlur={() => input && add(input)}
        placeholder={placeholder}
        style={{
          border: 'none', outline: 'none', background: 'transparent',
          fontSize: 13, minWidth: 120, color: 'inherit',
        }}
      />
    </div>
  )
}

function providerBadge(user) {
  const p = user?.app_metadata?.provider
  if (p === 'github') return 'via GitHub'
  if (p === 'google') return 'via Google'
  return 'via Email'
}

export function ProfileTab({ state }) {
  const {
    t, user, onLogout,
    companiesRoster, priorityCompanies, onCompaniesChange,
    priorityMode, onModeChange, scoreWeights, onWeightsChange,
    dreamRoleKeywords, onRolesChange,
    preferredLocations, onLocationsChange,
  } = state

  if (!user) return null

  const email = user.email || ''
  const name = user.user_metadata?.full_name || email
  const avatarUrl = user.user_metadata?.avatar_url

  const card = { background: t.cd, border: `1px solid ${t.bd}`, borderRadius: 12, padding: 20, marginBottom: 16 }
  const heading = { fontSize: 16, fontWeight: 700, color: t.tx, marginBottom: 14, margin: '0 0 14px' }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '24px 16px' }}>

      {/* Account card */}
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{
            width: 56, height: 56, borderRadius: '50%', overflow: 'hidden', flexShrink: 0,
            background: avatarUrl ? 'transparent' : avatarColor(email),
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontWeight: 700, fontSize: 22,
          }}>
            {avatarUrl
              ? <img src={avatarUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : email[0]?.toUpperCase()}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 18, color: t.tx, marginBottom: 2 }}>{name}</div>
            <div style={{ fontSize: 13, color: t.txM }}>{email}</div>
            <span style={{
              display: 'inline-block', marginTop: 6, fontSize: 11, fontWeight: 600,
              background: t.gP + '22', color: t.gP, borderRadius: 20, padding: '2px 10px',
            }}>
              {providerBadge(user)}
            </span>
          </div>
          <button
            onClick={onLogout}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid #e74c3c',
              background: 'transparent', color: '#e74c3c', fontWeight: 600,
              fontSize: 13, cursor: 'pointer', flexShrink: 0,
            }}
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Company Priorities */}
      <div style={card}>
        <h3 style={heading}>Company Priorities</h3>
        <CompanyPriorityPanel
          companies={priorityCompanies}
          onCompaniesChange={onCompaniesChange}
          mode={priorityMode}
          onModeChange={onModeChange}
          weights={scoreWeights}
          onWeightsChange={onWeightsChange}
          roster={companiesRoster || []}
          onOpenAddSearch={() => {}}
        />
      </div>

      {/* Score Weights */}
      <div style={card}>
        <h3 style={heading}>Score Weights</h3>
        <ScoreWeightDials weights={scoreWeights} onChange={onWeightsChange} />
      </div>

      {/* Job Preferences */}
      <div style={card}>
        <h3 style={heading}>Job Preferences</h3>
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: t.txM, marginBottom: 8 }}>Dream Role Keywords</div>
          <div style={{
            border: `1px solid ${t.bd}`, borderRadius: 8, padding: '8px 12px',
            background: t.bg, minHeight: 42,
          }}>
            <ChipEditor
              chips={dreamRoleKeywords}
              onChange={onRolesChange}
              placeholder="data engineer, ml engineer…"
            />
          </div>
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: t.txM, marginBottom: 8 }}>Preferred Locations</div>
          <div style={{
            border: `1px solid ${t.bd}`, borderRadius: 8, padding: '8px 12px',
            background: t.bg, minHeight: 42,
          }}>
            <ChipEditor
              chips={preferredLocations}
              onChange={onLocationsChange}
              placeholder="Remote, Dallas, Austin…"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
