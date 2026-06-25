import { useState } from 'react'
import { supabase } from '../lib/supabase'

const REDIRECT = window.location.origin + '/job-scout/'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const oAuth = async (provider) => {
    setLoading(true)
    setError('')
    const { error: e } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: REDIRECT },
    })
    if (e) { setError(e.message); setLoading(false) }
  }

  const emailLogin = async (ev) => {
    ev.preventDefault()
    setLoading(true)
    setError('')
    const { error: e } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: REDIRECT },
    })
    if (e) { setError(e.message); setLoading(false) }
    else setSent(true)
  }

  const wrap = { maxWidth: 380, margin: '80px auto', padding: 32, display: 'flex', flexDirection: 'column', gap: 12, fontFamily: 'system-ui', textAlign: 'center' }
  const btn = { padding: '10px 16px', borderRadius: 8, border: '1px solid #ddd', cursor: 'pointer', background: '#fff', fontSize: 14 }

  if (sent) return (
    <div style={wrap}>
      <h2 style={{ margin: 0 }}>Check your email</h2>
      <p>We sent a magic link to <strong>{email}</strong></p>
    </div>
  )

  return (
    <div style={wrap}>
      <h1 style={{ margin: 0, fontSize: 28 }}>Job Scout</h1>
      <p style={{ color: '#666', margin: 0 }}>Sign in to save your preferences.</p>
      {error && <p style={{ color: '#c00', margin: 0 }}>{error}</p>}
      <button style={{ ...btn, background: '#24292e', color: '#fff', border: 'none' }}
        onClick={() => oAuth('github')} disabled={loading}>
        Continue with GitHub
      </button>
      <button style={{ ...btn, background: '#4285f4', color: '#fff', border: 'none' }}
        onClick={() => oAuth('google')} disabled={loading}>
        Continue with Google
      </button>
      <button style={{ ...btn, background: '#0077b5', color: '#fff', border: 'none' }}
        onClick={() => oAuth('linkedin_oidc')} disabled={loading}>
        Continue with LinkedIn
      </button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <hr style={{ flex: 1, border: 'none', borderTop: '1px solid #eee' }} />
        <span style={{ color: '#aaa', fontSize: 12 }}>or</span>
        <hr style={{ flex: 1, border: 'none', borderTop: '1px solid #eee' }} />
      </div>
      <form onSubmit={emailLogin} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <input type="email" placeholder="your@email.com" value={email}
          onChange={e => setEmail(e.target.value)} required
          style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid #ddd', fontSize: 14 }} />
        <button type="submit" disabled={loading || !email}
          style={{ ...btn, background: '#000', color: '#fff', border: 'none' }}>
          Send magic link
        </button>
      </form>
    </div>
  )
}
