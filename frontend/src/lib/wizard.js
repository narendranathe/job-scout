/**
 * Onboarding wizard helpers — first-run detection, reducer, API binders.
 *
 * Pure module. No React imports beyond useReducer's reducer signature.
 * The actual <OnboardingWizard> component lives in
 * ../tabs/OnboardingWizard.jsx and consumes this module's exports.
 *
 * PRD #89 Slice 2. The wizard owns the user's onboarding state machine;
 * the rest of the app should treat the wizard as opaque and react only
 * to "onboarding completed" via a refetch of /api/profile.
 */

import { RENDER_API, authHeaders } from "./api.js";

/* ═══════════════════════════════════════════════════════════════════
   First-run detection
   ═══════════════════════════════════════════════════════════════════ */

/**
 * Detect whether the user should be redirected into the wizard.
 *
 * "First run" means: the user has NO configured roles, NO configured
 * dream companies, NO PIN set, and zero PDFs in the vault. This is a
 * conservative AND — if ANY of those signals is present, we assume the
 * user has used the dashboard before and skip the wizard.
 *
 * Returns one of:
 *   "first-run"      — show the wizard (blocking)
 *   "force"          — URL says ?force=1 or path /setup, show wizard
 *   "onboarded"      — skip wizard, render dashboard normally
 *   "login-required" — server is PIN-protected and we have no valid
 *                      Bearer/cookie; caller should prompt for login
 *                      (Slice 4 LoginScreen) and re-detect on success
 *   "unknown"        — probe failed for an unrelated reason (network,
 *                      5xx); fall back to onboarded so a flaky server
 *                      doesn't permanently block the user
 *
 * The probe sends ``credentials: "include"`` + ``authHeaders()`` so an
 * already-authenticated visitor (Bearer in localStorage OR a valid
 * session cookie) is recognised and never sees the login prompt.
 */
export async function detectOnboardingState() {
  // Path / query short-circuits — always win over the API probe so
  // returning users can re-enter the wizard at will.
  if (typeof window !== "undefined") {
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("force") === "1") return "force";
    if (window.location.pathname.replace(/\/+$/, "") === "/setup") return "force";
  }

  if (!RENDER_API) return "unknown";

  try {
    const [profileResp, vaultResp] = await Promise.all([
      fetch(`${RENDER_API}/api/profile`, {
        headers: { ...authHeaders() },
        credentials: "include",
        signal: AbortSignal.timeout(8000),
      }),
      fetch(`${RENDER_API}/api/vault/stats`, {
        headers: { ...authHeaders() },
        credentials: "include",
        signal: AbortSignal.timeout(8000),
      }),
    ]);

    // 401/403 on the profile probe means the server is auth-gated and
    // we have no valid credentials yet. We CANNOT decide first-run vs
    // onboarded without reading the profile, so the caller has to log
    // the user in first and re-run this probe. Returning a distinct
    // sentinel (instead of "unknown") prevents the old bug where a
    // brand-new user behind a PIN-protected deployment silently
    // skipped the wizard.
    if (profileResp.status === 401 || profileResp.status === 403) {
      return "login-required";
    }

    if (!profileResp.ok) return "unknown";
    const profile = await profileResp.json();

    // onboarded_at is the explicit completion marker. Set by the wizard
    // on Step 7, also set to "preview" by the Step 1 skip path (Slice 4
    // wires the read-only enforcement; we just honour the sentinel).
    if (profile.onboarded_at) return "onboarded";

    const hasRoles = (profile.dream_role_keywords || []).length > 0;
    const hasCompanies = (profile.dream_companies || []).length > 0;
    const hasPin = profile.has_pin === true;

    // Vault probe is best-effort — a 401 (locked vault) just means we
    // can't tell, so we err on the side of showing the wizard.
    let pdfCount = 0;
    if (vaultResp.ok) {
      const v = await vaultResp.json();
      pdfCount = v.stats?.pdf_count || v.pdf_count || 0;
    }

    if (!hasRoles && !hasCompanies && !hasPin && pdfCount === 0) {
      return "first-run";
    }
    return "onboarded";
  } catch (_e) {
    return "unknown";
  }
}

/* ═══════════════════════════════════════════════════════════════════
   Reducer + initial state
   ═══════════════════════════════════════════════════════════════════ */

export const TOTAL_STEPS = 7;

export const STEP_LABELS = {
  1: "Welcome",
  2: "Roles",
  3: "Companies",
  4: "Locations",
  5: "Resume",
  6: "PIN",
  7: "Done",
};

export const initialWizardState = () => ({
  step: 1,
  // Step 2 — roles
  roles: [],          // canonical role keys from /api/role-taxonomy
  customRoles: [],    // free-text role strings (chip-style)
  // Step 3 — companies
  pickedCompanies: [],   // from the scraped roster
  trackedCompanies: [],  // user-typed, not in the scraped roster
  // Step 4 — locations + comp
  locations: [],
  minTotalComp: 0,
  showUnsalaried: true,
  // Step 5 — resume (set by Slice 3's PdfDropzone component)
  uploadedResumeVersion: null,
  // Step 6 — PIN (set by Slice 3's PinSetup component)
  pinSet: false,
  skipPinAcknowledged: false,
  // UI
  saving: false,
  saveError: null,
});

export function wizardReducer(state, action) {
  switch (action.type) {
    case "GO_TO_STEP":
      return { ...state, step: Math.max(1, Math.min(TOTAL_STEPS, action.step)) };
    case "NEXT":
      return { ...state, step: Math.min(TOTAL_STEPS, state.step + 1) };
    case "BACK":
      return { ...state, step: Math.max(1, state.step - 1) };
    case "TOGGLE_ROLE": {
      const exists = state.roles.includes(action.roleKey);
      return {
        ...state,
        roles: exists
          ? state.roles.filter((r) => r !== action.roleKey)
          : [...state.roles, action.roleKey],
      };
    }
    case "ADD_CUSTOM_ROLE": {
      const v = (action.value || "").trim();
      if (!v) return state;
      if (state.customRoles.includes(v)) return state;
      return { ...state, customRoles: [...state.customRoles, v] };
    }
    case "REMOVE_CUSTOM_ROLE":
      return {
        ...state,
        customRoles: state.customRoles.filter((r) => r !== action.value),
      };
    case "TOGGLE_PICKED_COMPANY": {
      const exists = state.pickedCompanies.includes(action.name);
      return {
        ...state,
        pickedCompanies: exists
          ? state.pickedCompanies.filter((c) => c !== action.name)
          : [...state.pickedCompanies, action.name],
      };
    }
    case "ADD_TRACKED_COMPANY": {
      const v = (action.name || "").trim();
      if (!v) return state;
      if (state.trackedCompanies.includes(v)) return state;
      if (state.pickedCompanies.includes(v)) return state;
      return { ...state, trackedCompanies: [...state.trackedCompanies, v] };
    }
    case "REMOVE_TRACKED_COMPANY":
      return {
        ...state,
        trackedCompanies: state.trackedCompanies.filter((c) => c !== action.name),
      };
    case "TOGGLE_LOCATION": {
      const exists = state.locations.includes(action.location);
      return {
        ...state,
        locations: exists
          ? state.locations.filter((l) => l !== action.location)
          : [...state.locations, action.location],
      };
    }
    case "ADD_CUSTOM_LOCATION": {
      const v = (action.value || "").trim();
      if (!v) return state;
      if (state.locations.includes(v)) return state;
      return { ...state, locations: [...state.locations, v] };
    }
    case "SET_MIN_COMP":
      return { ...state, minTotalComp: Math.max(0, Number(action.value) || 0) };
    case "SET_SHOW_UNSALARIED":
      return { ...state, showUnsalaried: !!action.value };
    case "SET_UPLOADED_RESUME":
      return { ...state, uploadedResumeVersion: action.versionKey };
    case "SET_PIN_SET":
      return { ...state, pinSet: true };
    case "SET_SKIP_PIN_ACK":
      return { ...state, skipPinAcknowledged: true };
    case "SAVE_START":
      return { ...state, saving: true, saveError: null };
    case "SAVE_OK":
      return { ...state, saving: false, saveError: null };
    case "SAVE_FAIL":
      return { ...state, saving: false, saveError: action.message };
    default:
      return state;
  }
}

/* ═══════════════════════════════════════════════════════════════════
   API helpers
   ═══════════════════════════════════════════════════════════════════ */

/**
 * Translate the wizard's roles/companies state into the role keywords
 * the existing relevance engine uses. Backend stores them in
 * ``dream_role_keywords``; we feed labels (display strings) because that's
 * what the engine matches against job titles.
 */
function rolesToKeywords(roles, customRoles, taxonomy) {
  const labels = [];
  for (const key of roles) {
    const r = taxonomy?.find((t) => t.key === key);
    if (r) labels.push(r.label.toLowerCase());
  }
  for (const c of customRoles) {
    labels.push(c.toLowerCase());
  }
  return labels;
}

/**
 * Persist the wizard's accumulated state to /api/profile.
 *
 * Called at the end of step 4 (interim commit in Slice 2 — see PRD
 * §2.7) and again at step 7 (final commit including
 * default_resume_version + skip_pin_acknowledged).
 *
 * Tolerates the no-cookie case: if API_SECRET is set and we haven't
 * logged in yet, this will fail with 401. The caller surfaces the error.
 */
export async function persistProfile(state, taxonomy, opts = {}) {
  if (!RENDER_API) {
    throw new Error("RENDER_API not configured");
  }
  const csrf =
    (typeof window !== "undefined" &&
      window.localStorage.getItem("jobscout_csrf")) ||
    "";
  const body = {
    dream_role_keywords: rolesToKeywords(state.roles, state.customRoles, taxonomy),
    dream_companies: state.pickedCompanies,
    tracked_companies: state.trackedCompanies,
    preferred_locations: state.locations,
    min_total_comp: state.minTotalComp,
    show_unsalaried: state.showUnsalaried,
    ...(opts.includeOnboardedAt ? { onboarded_at: new Date().toISOString() } : {}),
    ...(opts.markPreview ? { onboarded_at: "preview" } : {}),
    ...(opts.skipPinAcknowledged ? { skip_pin_acknowledged: true } : {}),
    ...(opts.defaultResumeVersion
      ? { default_resume_version: opts.defaultResumeVersion }
      : {}),
  };
  const r = await fetch(`${RENDER_API}/api/profile`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      ...authHeaders(),
    },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const e = await r.json();
      if (e.error) msg = e.error;
    } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

/**
 * Fetch the public roster endpoints in parallel.
 *
 * Returns {roles, companies, locations} all as arrays. Network failures
 * yield empty arrays — the wizard renders an empty picker rather than
 * blocking; the user can still type custom entries.
 */
export async function fetchRosters() {
  if (!RENDER_API) {
    return { roles: [], companies: [], locations: [] };
  }
  const safe = async (path, key) => {
    try {
      const r = await fetch(`${RENDER_API}${path}`, {
        signal: AbortSignal.timeout(8000),
      });
      if (!r.ok) return [];
      const d = await r.json();
      return d[key] || [];
    } catch {
      return [];
    }
  };
  const [roles, companies, locations] = await Promise.all([
    safe("/api/role-taxonomy", "roles"),
    safe("/api/companies-roster", "companies"),
    safe("/api/locations-roster", "locations"),
  ]);
  return { roles, companies, locations };
}
