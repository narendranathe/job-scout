/**
 * Auth + mode helpers for the dashboard.
 *
 * PRD #89 Slice 4 §4.2. Three signals the dashboard derives from
 * /api/profile + localStorage:
 *
 *   mode:        "preview" | "full"
 *   loginNeeded: boolean — show <LoginScreen> when profile.has_pin
 *                && no csrf_token in localStorage
 *   isPreview:   boolean — true when profile.onboarded_at === "preview"
 *
 * Pure module. Caller passes the profile in; we derive state. Avoids
 * tight coupling between App.jsx and the specific shape of the auth
 * cookie / CSRF mechanism.
 */

const CSRF_LS_KEY = "jobscout_csrf";

export function hasCsrf() {
  if (typeof window === "undefined") return false;
  try {
    return !!window.localStorage.getItem(CSRF_LS_KEY);
  } catch {
    return false;
  }
}

export function getCsrf() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(CSRF_LS_KEY) || "";
  } catch {
    return "";
  }
}

export function setCsrf(csrf) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CSRF_LS_KEY, csrf || "");
  } catch (_) {}
}

export function clearCsrf() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CSRF_LS_KEY);
  } catch (_) {}
}

/**
 * Derive the dashboard mode from the profile response.
 *
 * "preview" — Step 1's skip path set onboarded_at to the "preview"
 *             sentinel. The dashboard shows everything in read-only
 *             mode (write attempts open the "Set up first" modal).
 * "full"    — Default. Normal dashboard, write actions work.
 */
export function deriveMode(profile) {
  if (profile?.onboarded_at === "preview") return "preview";
  return "full";
}

/**
 * Should we show the LoginScreen?
 *
 * Returns true ONLY when the server has a PIN configured AND we don't
 * already hold a CSRF token (the proxy for "valid session cookie").
 * Without a PIN, login is meaningless — fall through to the dashboard.
 *
 * Cookie validity isn't directly checkable from JS (HttpOnly), so we
 * use the CSRF token as a "session marker". A stale CSRF + dead cookie
 * means the user will get a 401 on the first write attempt; the App
 * should then call clearCsrf() and re-render the LoginScreen.
 */
export function shouldShowLogin(profile) {
  if (!profile) return false;
  if (!profile.has_pin) return false;
  return !hasCsrf();
}

/**
 * Logout: clear local session state and POST /api/logout.
 *
 * Tolerates network failure — local state still clears so the user
 * lands on the LoginScreen on the next page load.
 */
export async function logout(apiBase) {
  clearCsrf();
  if (!apiBase) return;
  try {
    await fetch(`${apiBase}/api/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch (_) {}
}
