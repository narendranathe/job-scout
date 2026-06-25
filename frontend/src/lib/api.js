import { currentAccessToken } from './supabase'

/**
 * API URL + auth-token helpers — extracted from App.jsx (CLAUDE.md
 * tech-debt #1, App.jsx split).
 *
 * Pure module: no React, no DOM mutation, only localStorage reads.
 * Everything here can be unit-tested in isolation if we ever add JSDOM-
 * backed Jest. Until then, the rest of the dashboard imports from here
 * so the API base URL is configured in exactly one place.
 *
 * Behavior preserved exactly: same env-var fallback chain, same trailing-
 * slash normalization, same localStorage keys ("jobscout_api_url" and
 * "vault_token"). Existing `${RENDER_API}/...` template strings keep
 * working unchanged because RENDER_API is exported as a const.
 */
export const DEFAULT_RENDER_URL = "https://jobscout-api-lasz.onrender.com";
export const STATIC_URL = "./api-data.json";

/**
 * Resolved Render API base URL. Lookup order:
 *   1. localStorage key "jobscout_api_url" (set via the SetupPanel UI)
 *   2. import.meta.env.VITE_RENDER_URL (set at Vite build time)
 *   3. empty string (the SetupPanel renders blocking when this is "")
 * Trailing slashes are stripped so callers can `${RENDER_API}/api/...`
 * without worrying about double slashes.
 */
// Exported (PR 5/N) so SetupPanel can read the current value without
// re-implementing the localStorage probe. Internal-leading underscore
// kept to mark this as "low-level — most callers want RENDER_API instead".
export const _readApiUrl = () => {
  if (typeof window === "undefined") return "";
  try { return (window.localStorage.getItem("jobscout_api_url") || "").trim(); }
  catch { return ""; }
};

export const RENDER_API =
  (_readApiUrl() || import.meta.env.VITE_RENDER_URL || "").replace(/\/+$/, "");

/**
 * Vault auth helpers.
 *
 * When the backend has API_SECRET set, every /api/vault/* call must
 * carry ``Authorization: Bearer <token>``. We read the token from
 * localStorage (key "vault_token") so the user can set it once via the
 * SetupPanel — a proper login UI is tracked as a follow-up.
 *
 * apiToken()    — safe read, returns "" outside browser
 * authHeaders() — spreadable into ``headers: { ... }`` only when a token
 *                 exists, so calls in dev (no API_SECRET) work unchanged.
 */
export const apiToken = () => {
  if (typeof window === "undefined") return "";
  try { return window.localStorage.getItem("vault_token") || ""; }
  catch { return ""; }
};

export const authHeaders = () => {
  if (currentAccessToken) return { Authorization: `Bearer ${currentAccessToken}` }
  // Fallback to legacy vault_token during transition period
  const t = apiToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}
