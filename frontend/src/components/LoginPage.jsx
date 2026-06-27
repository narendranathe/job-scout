import { useState } from 'react'
import { supabase } from '../lib/supabase'

const REDIRECT = window.location.origin + '/job-scout/'

const C = {
  bg:      '#1C2B24',
  card:    '#F8F4EF',
  primary: '#2D5A4A',
  hover:   '#3A7060',
  gold:    '#C4A77D',
  text:    '#1C2B24',
  muted:   '#6B8278',
  subtle:  '#A09080',
  border:  'rgba(44,90,74,0.16)',
  inputBg: '#ffffff',
  error:   '#B03030',
}

function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" style={{ display: 'block' }}>
      <path fill={C.text} d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" style={{ display: 'block' }}>
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
    </svg>
  )
}

function LinkedInIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" style={{ display: 'block' }}>
      <path fill="#0077B5" d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  )
}

function AuthButton({ icon, label, onClick, disabled, chip, style = {} }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 12,
        padding: '11px 16px', borderRadius: 9,
        border: `1.5px solid ${hovered && !disabled ? C.primary : C.border}`,
        background: disabled ? '#F5F2EE' : (hovered ? '#FAFAF8' : C.inputBg),
        color: C.text, fontSize: 14, fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
        fontFamily: 'inherit', textAlign: 'left',
        boxShadow: hovered && !disabled ? `0 0 0 3px rgba(44,90,74,0.08)` : 'none',
        transition: 'border-color .15s, box-shadow .15s, background .15s',
        ...style,
      }}
    >
      <span style={{ width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {icon}
      </span>
      <span style={{ flex: 1 }}>{label}</span>
      {chip && (
        <span style={{
          fontSize: 10, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
          color: C.muted, background: 'rgba(44,90,74,0.08)',
          border: `1px solid rgba(44,90,74,0.15)`,
          borderRadius: 20, padding: '2px 8px', flexShrink: 0,
        }}>
          {chip}
        </span>
      )}
    </button>
  )
}

export default function LoginPage() {
  const [email, setEmail]   = useState('')
  const [sent, setSent]     = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState('')

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
    else { setLoading(false); setSent(true) }
  }

  const page = {
    minHeight: '100vh', background: C.bg,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: '24px 16px', fontFamily: "'Source Sans 3', 'Segoe UI', system-ui, sans-serif",
  }

  const card = {
    width: '100%', maxWidth: 420,
    background: C.card, borderRadius: 16, overflow: 'hidden',
    boxShadow: `0 0 0 1px rgba(196,167,125,0.25), 0 24px 64px rgba(0,0,0,0.45), 0 4px 16px rgba(0,0,0,0.2)`,
  }

  const headerBand = {
    background: 'linear-gradient(135deg, #2D5A4A 0%, #3D7060 100%)',
    padding: '28px 32px 24px',
    borderBottom: `1px solid ${C.gold}44`,
  }

  if (sent) return (
    <div style={page}>
      <div style={card}>
        <div style={headerBand}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
            <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: 26, fontWeight: 700, color: '#F0EAE0', letterSpacing: '-0.02em', lineHeight: 1 }}>
              JobScout
            </span>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.gold, display: 'inline-block', marginBottom: 3 }} />
          </div>
        </div>
        <div style={{ padding: '40px 32px 40px', textAlign: 'center' }}>
          <div style={{ fontSize: 36, marginBottom: 16 }}>✉️</div>
          <h2 style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: 22, fontWeight: 700, color: C.text, marginBottom: 10, textWrap: 'balance' }}>
            Check your inbox
          </h2>
          <p style={{ fontSize: 14, color: C.muted, lineHeight: 1.6 }}>
            We sent a magic link to<br />
            <strong style={{ color: C.primary }}>{email}</strong>
          </p>
          <p style={{ fontSize: 12, color: C.subtle, marginTop: 20 }}>
            Didn't get it? Check your spam folder or{' '}
            <button onClick={() => { setSent(false); setEmail('') }}
              style={{ background: 'none', border: 'none', color: C.primary, cursor: 'pointer', fontSize: 12, fontWeight: 600, padding: 0, fontFamily: 'inherit' }}>
              try again
            </button>
            .
          </p>
        </div>
      </div>
    </div>
  )

  return (
    <div style={page}>
      <div style={card}>
        {/* Header band */}
        <div style={headerBand}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
            <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: 26, fontWeight: 700, color: '#F0EAE0', letterSpacing: '-0.02em', lineHeight: 1 }}>
              JobScout
            </span>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.gold, display: 'inline-block', marginBottom: 3 }} />
          </div>
          <p style={{ fontSize: 13, color: 'rgba(240,234,224,0.6)', letterSpacing: '0.02em' }}>
            Your personal job discovery platform
          </p>
        </div>

        {/* Body */}
        <div style={{ padding: '28px 32px 32px', display: 'flex', flexDirection: 'column', gap: 0 }}>

          {error && (
            <div style={{
              fontSize: 13, color: C.error,
              background: 'rgba(176,48,48,0.07)',
              border: `1px solid rgba(176,48,48,0.15)`,
              borderRadius: 8, padding: '9px 12px', marginBottom: 16,
            }}>
              {error}
            </div>
          )}

          <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: C.muted, marginBottom: 12 }}>
            Continue with
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24 }}>
            <AuthButton
              icon={<GitHubIcon />}
              label="Continue with GitHub"
              onClick={() => oAuth('github')}
              disabled={loading}
            />
            <AuthButton
              icon={<GoogleIcon />}
              label="Continue with Google"
              onClick={() => oAuth('google')}
              disabled={loading}
            />
            <AuthButton
              icon={<LinkedInIcon />}
              label="Continue with LinkedIn"
              onClick={() => oAuth('linkedin_oidc')}
              disabled={loading}
            />
          </div>

          {/* Divider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
            <div style={{ flex: 1, height: 1, background: `linear-gradient(90deg, transparent, ${C.gold}66 40%, ${C.gold}66 60%, transparent)` }} />
            <span style={{ fontSize: 11, color: C.subtle, fontWeight: 500, letterSpacing: '0.04em', flexShrink: 0 }}>
              or use email
            </span>
            <div style={{ flex: 1, height: 1, background: `linear-gradient(90deg, transparent, ${C.gold}66 40%, ${C.gold}66 60%, transparent)` }} />
          </div>

          {/* Email form */}
          <form onSubmit={emailLogin} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input
              type="email"
              placeholder="your@email.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              style={{
                width: '100%', padding: '11px 14px', borderRadius: 9,
                border: `1.5px solid ${C.border}`, background: C.inputBg,
                fontSize: 14, color: C.text, fontFamily: 'inherit', outline: 'none',
              }}
              onFocus={e => { e.target.style.borderColor = C.primary; e.target.style.boxShadow = '0 0 0 3px rgba(44,90,74,0.1)' }}
              onBlur={e => { e.target.style.borderColor = C.border; e.target.style.boxShadow = 'none' }}
            />
            <button
              type="submit"
              disabled={loading || !email}
              style={{
                width: '100%', padding: '11px 16px', borderRadius: 9, border: 'none',
                background: C.primary, color: '#F0EAE0',
                fontSize: 14, fontWeight: 600, cursor: loading || !email ? 'not-allowed' : 'pointer',
                opacity: loading || !email ? 0.55 : 1,
                fontFamily: 'inherit', letterSpacing: '0.01em',
                transition: 'background .15s, box-shadow .15s',
              }}
              onMouseEnter={e => { if (!loading && email) { e.target.style.background = C.hover; e.target.style.boxShadow = '0 4px 12px rgba(44,90,74,0.3)' } }}
              onMouseLeave={e => { e.target.style.background = C.primary; e.target.style.boxShadow = 'none' }}
            >
              {loading ? 'Sending…' : 'Send magic link'}
            </button>
          </form>
        </div>

        <div style={{ padding: '0 32px 20px', fontSize: 11.5, color: C.subtle, textAlign: 'center', lineHeight: 1.5 }}>
          Your preferences and resume data are stored privately on your account.
        </div>
      </div>
    </div>
  )
}
