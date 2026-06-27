import { useState, useEffect, useRef, useMemo } from 'react'

const TIER_LABELS = { 0: 'Platinum', 1: 'T1', 2: 'T2', 3: 'T3' }

function avatarColor(name) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h)
  const palette = ['#e74c3c','#3498db','#2ecc71','#9b59b6','#f39c12','#1abc9c','#e67e22','#34495e']
  return palette[Math.abs(h) % palette.length]
}

function ranked(query, roster) {
  if (!query) return []
  const q = query.toLowerCase()
  const prefix = roster.filter(c => c.name.toLowerCase().startsWith(q))
  const sub = roster.filter(c => !c.name.toLowerCase().startsWith(q) && c.name.toLowerCase().includes(q))
  const byCount = (a, b) => (b.job_count || 0) - (a.job_count || 0)
  return [...prefix.sort(byCount), ...sub.sort(byCount)].slice(0, 8)
}

function Bold({ text, query }) {
  const i = text.toLowerCase().indexOf(query.toLowerCase())
  if (i === -1) return <>{text}</>
  return <>{text.slice(0, i)}<strong>{text.slice(i, i + query.length)}</strong>{text.slice(i + query.length)}</>
}

export default function CompanyAutocomplete({ value, onChange, roster = [], style, inputStyle, onAddToPriority }) {
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(-1)
  const ref = useRef(null)

  const suggestions = useMemo(() => ranked(value, roster), [value, roster])
  const hasExact = roster.some(c => c.name.toLowerCase() === value.toLowerCase())
  const showAdd = value.length > 0 && !hasExact && onAddToPriority

  // Total items count (for keyboard nav bounds)
  const itemCount = suggestions.length + (showAdd ? 1 : 0)

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const pick = (name) => { onChange(name); setOpen(false); setHi(-1) }

  const keyDown = (e) => {
    if (!open) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setHi(h => Math.min(h + 1, itemCount - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi(h => Math.max(h - 1, 0)) }
    else if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'Enter' && hi >= 0) {
      e.preventDefault()
      if (hi < suggestions.length) pick(suggestions[hi].name)
      else if (showAdd) { onAddToPriority(value, false); setOpen(false) }
    }
  }

  const dropStyle = {
    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 1000,
    background: '#fff', border: '1px solid #e0e0e0', borderRadius: 8,
    listStyle: 'none', margin: '4px 0 0', padding: '4px 0',
    boxShadow: '0 6px 16px rgba(0,0,0,0.1)', maxHeight: 340, overflowY: 'auto',
  }
  const rowStyle = (active) => ({
    padding: '7px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
    background: active ? '#f5f5f5' : 'transparent',
  })

  return (
    <div ref={ref} style={{ position: 'relative', ...style }}>
      <input
        placeholder="Search jobs, skills, companies..."
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true); setHi(-1) }}
        onFocus={() => { if (value) setOpen(true) }}
        onKeyDown={keyDown}
        style={{ width: '100%', boxSizing: 'border-box', ...inputStyle }}
      />
      {open && itemCount > 0 && (
        <ul style={dropStyle}>
          {suggestions.map((co, i) => (
            <li key={co.name}
              style={rowStyle(hi === i)}
              onMouseDown={() => pick(co.name)}
              onMouseEnter={() => setHi(i)}
            >
              <span style={{
                width: 26, height: 26, borderRadius: '50%',
                background: avatarColor(co.name),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: 11, fontWeight: 700, flexShrink: 0,
              }}>
                {co.name[0].toUpperCase()}
              </span>
              <span style={{ flex: 1, fontSize: 13 }}><Bold text={co.name} query={value} /></span>
              {co.job_count > 0 && <span style={{ fontSize: 11, color: '#999' }}>{co.job_count} jobs</span>}
              {co.tier !== undefined && (
                <span style={{ fontSize: 10, color: '#777', border: '1px solid #e0e0e0', borderRadius: 3, padding: '1px 4px' }}>
                  {TIER_LABELS[co.tier] ?? `T${co.tier}`}
                </span>
              )}
            </li>
          ))}
          {showAdd && (
            <li
              style={{ ...rowStyle(hi === suggestions.length), borderTop: suggestions.length > 0 ? '1px solid #f0f0f0' : 'none', color: '#555', fontSize: 13 }}
              onMouseDown={() => { onAddToPriority(value, false); setOpen(false) }}
              onMouseEnter={() => setHi(suggestions.length)}
            >
              + Add "<strong>{value}</strong>" to my priority list →
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
