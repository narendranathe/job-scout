import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)

// Synchronous token read for authHeaders() in api.js.
// Updated by the onAuthStateChange listener below.
export let currentAccessToken = null

// Seed from existing session on page load
supabase.auth.getSession().then(({ data: { session } }) => {
  currentAccessToken = session?.access_token ?? null
})

// Keep in sync as auth state changes (sign-in, sign-out, token refresh)
supabase.auth.onAuthStateChange((_event, session) => {
  currentAccessToken = session?.access_token ?? null
})
