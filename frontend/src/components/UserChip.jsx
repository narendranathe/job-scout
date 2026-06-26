import { useState, useRef, useEffect } from 'react'

function avatarColor(email) {
  let h = 0
  for (let i = 0; i < email.length; i++) h = email.charCodeAt(i) + ((h << 5) - h)
  const palette = ['#e74c3c','#3498db','#2ecc71','#9b59b6','#f39c12','#1abc9c','#e67e22','#34495e']
  return palette[Math.abs(h) % palette.length]
}

export default function UserChip({ user, onLogout, onOpenProfile, t }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (!user) return null

  const email = user.email || ''
  const name = user.user_metadata?.full_name || email
  const avatarUrl = user.user_metadata?.avatar_url
  const label = name.length > 28 ? name.slice(0, 28) + '…' : name

  return (
    <div ref={ref} style={{ position: 'relative', flexShrink: 0 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: 32, height: 32, borderRadius: '50%', border: `2px solid ${t.bd}`,
          cursor: 'pointer', overflow: 'hidden', padding: 0,
          background: avatarUrl ? 'transparent' : avatarColor(email),
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 13,
        }}
        aria-label="User menu"
      >
        {avatarUrl
          ? <img src={avatarUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : email[0]?.toUpperCase()}
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 40, right: 0, minWidth: 200,
          background: t.cd, border: `1px solid ${t.bd}`, borderRadius: 10,
          boxShadow: t.sh, zIndex: 200, overflow: 'hidden',
        }}>
          <div style={{ padding: '10px 14px', fontSize: 12, color: t.txM, borderBottom: `1px solid ${t.bd}` }}>
            Signed in as<br />
            <strong style={{ color: t.tx }}>{label}</strong>
          </div>
          <button
            onClick={() => { setOpen(false); onOpenProfile() }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '10px 14px', border: 'none', background: 'transparent',
              color: t.tx, fontSize: 14, cursor: 'pointer',
            }}
          >
            Profile &amp; Settings
          </button>
          <button
            onClick={() => { setOpen(false); onLogout() }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '10px 14px', border: 'none', background: 'transparent',
              color: '#e74c3c', fontSize: 14, cursor: 'pointer',
              borderTop: `1px solid ${t.bd}`,
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
