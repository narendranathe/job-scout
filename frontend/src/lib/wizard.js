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
 *
 * ──────────────────────────────────────────────────────────────────
 * Local-first completion model (fix/wizard-401-detection-attempt-B)
 * ──────────────────────────────────────────────────────────────────
 * The wizard ships before Slice 4's LoginScreen, so on any deployment
 * with API_SECRET set the POST /api/profile commit will 401 — there's
 * no way for the user to authenticate yet. To keep the wizard
 * USE-able in that window, we treat onboarding completion as a
 * client-side fact:
 *
 *   1. detectOnboardingState() checks a local "complete" flag first
 *      and short-circuits if it's set. The flag is the authority for
 *      "should we show the wizard", not /api/profile. (Belt-and-
 *      braces: this also defends against GET /api/profile ever
 *      starting to 401 in the future — today it's open, tomorrow it
 *      may not be.)
 *
 *   2. persistProfile() always commits the wizard's state to
 *      localStorage FIRST, then attempts the server POST. On a 401
 *      it returns a structured outcome (`{ok: false, reason: "401",
 *      pending: true}`) rather than throwing, so the wizard can
 *      finish the flow and surface a "synced locally — will push
 *      after you sign in" notice instead of dead-ending the user.
 *
 *   3. flushPendingProfile() replays the deferred POST once the user
 *      authenticates (Slice 4 LoginScreen calls this after a
 *      successful PIN entry). On 2xx we drop the local pending
 *      payload; on another 401 we keep it.
 *
 * Dev mode (no API_SECRET) is unaffected: persistProfile gets a 2xx,
 * the localStorage flag is set as a cache (still useful — it skips a
 * /api/profile round-trip on next mount), and no pending-sync notice
 * fires.
 */

import { RENDER_API, authHeaders } from "./api.js";

/* ═══════════════════════════════════════════════════════════════════
   localStorage keys (centralised so Slice 4's LoginScreen can read
   them without duplicating the names)
   ═══════════════════════════════════════════════════════════════════ */

// Set to "1" once the user finishes the wizard, regardless of whether
// the server POST succeeded. Cleared by the Slice 4 "Reset onboarding"
// admin card.
export const LS_WIZARD_COMPLETE = "jobscout_wizard_complete";

// Set to "preview" when the user takes the Step-1 skip path; cleared
// when they later complete the wizard for real.
export const LS_WIZARD_MODE = "jobscout_wizard_mode";

// Holds the JSON-serialised profile payload that 401'd. Slice 4's
// LoginScreen calls flushPendingProfile() after login to replay it.
export const LS_WIZARD_PENDING_PROFILE = "jobscout_wizard_pending_profile";

/* ─── small localStorage helpers (SSR-safe) ─── */
function lsGet(key) {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function lsSet(key, value) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* quota / private-mode — ignore, server sync is the fallback */
  }
}
function lsDel(key) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

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
 *   "first-run"  — show the wizard (blocking)
 *   "force"      — URL says ?force=1 or path /setup, show wizard
 *   "onboarded"  — skip wizard, render dashboard normally
 *
 * NOTE: this function never returns "unknown" anymore. The previous
 * "unknown" branch let users behind a PIN-gated deployment slip past
 * the wizard entirely (App.jsx treats anything that isn't "first-run"
 * /"force" as "render the dashboard"), which was the bug this branch
 * fixes. The new decision table:
 *
 *   local complete flag set?           → onboarded (skip network)
 *   profile GET succeeds + onboarded_at → onboarded (and cache flag)
 *   profile GET succeeds + any prior signal → onboarded (cache flag)
 *   profile GET succeeds + zero signal  → first-run
 *   profile GET → 401/403              → first-run (PIN-gated deploy
 *                                         that's never seen this user)
 *   profile GET → 5xx / network error  → onboarded (don't regress
 *                                         working users on a blip;
 *                                         consistent w/ prior fallback)
 */
export async function detectOnboardingState() {
  // Path / query short-circuits — always win over the API probe so
  // returning users can re-enter the wizard at will.
  if (typeof window !== "undefined") {
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("force") === "1") return "force";
    if (window.location.pathname.replace(/\/+$/, "") === "/setup") return "force";
  }

  // Local-first short-circuit. The wizard sets this flag on completion
  // regardless of whether the server commit succeeded, so a PIN-gated
  // deployment doesn't re-prompt the user every visit. This also caches
  // the 2xx-path result so we skip a network round-trip on next mount.
  if (lsGet(LS_WIZARD_COMPLETE) === "1") return "onboarded";

  if (!RENDER_API) {
    // No backend configured — there's nothing to probe. Default to
    // showing the wizard so the user lands somewhere useful instead
    // of an empty dashboard. The wizard's RENDER_API guard will surface
    // the "configure the API first" prompt via the existing SetupPanel.
    return "first-run";
  }

  try {
    const [profileResp, vaultResp] = await Promise.all([
      fetch(`${RENDER_API}/api/profile`, {
        signal: AbortSignal.timeout(8000),
      }),
      fetch(`${RENDER_API}/api/vault/stats`, {
        headers: { ...authHeaders() },
        signal: AbortSignal.timeout(8000),
      }),
    ]);

    // 401/403 on the (today-open) GET profile means the deployment has
    // tightened auth — we can't tell whether the user has onboarded,
    // but we know the local flag says no. Show the wizard; the
    // localStorage commit + Slice 4 sync path handle the rest.
    if (profileResp.status === 401 || profileResp.status === 403) {
      return "first-run";
    }
    if (!profileResp.ok) {
      // 5xx — could be a deploy restart, Render cold start mid-probe,
      // etc. Don't regress users who finished onboarding on a previous
      // visit before the local flag existed; default to onboarded.
      // The next mount with a working backend will re-evaluate.
      return "onboarded";
    }
    const profile = await profileResp.json();

    // onboarded_at is the explicit completion marker. Set by the wizard
    // on Step 7, also set to "preview" by the Step 1 skip path (Slice 4
    // wires the read-only enforcement; we just honour the sentinel).
    if (profile.onboarded_at) {
      // Cache it so next mount short-circuits without the network.
      lsSet(LS_WIZARD_COMPLETE, "1");
      return "onboarded";
    }

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
    // Some signal is set but onboarded_at isn't — pre-wizard user
    // already configured things. Cache as onboarded so we don't
    // re-prompt them.
    lsSet(LS_WIZARD_COMPLETE, "1");
    return "onboarded";
  } catch (_e) {
    // Network failure (DNS, CORS, abort, timeout). Same reasoning as
    // the 5xx branch: don't regress already-onboarded users. The
    // 401 path above is where we positively branch into "first-run";
    // a network blip can't distinguish that from anything else, so
    // we default to onboarded.
    return "onboarded";
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
 * Build the JSON body /api/profile expects from the wizard state.
 * Extracted so flushPendingProfile() can re-POST the exact same shape
 * the original attempt sent.
 */
function buildProfileBody(state, taxonomy, opts = {}) {
  return {
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
}

async function postProfile(body) {
  const csrf =
    (typeof window !== "undefined" &&
      window.localStorage.getItem("jobscout_csrf")) ||
    "";
  return fetch(`${RENDER_API}/api/profile`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      ...authHeaders(),
    },
    credentials: "include",
    body: JSON.stringify(body),
  });
}

/**
 * Persist the wizard's accumulated state to /api/profile.
 *
 * Called at the end of step 4 (interim commit in Slice 2 — see PRD
 * §2.7) and again at step 7 (final commit including
 * default_resume_version + skip_pin_acknowledged).
 *
 * Behaviour change vs the original implementation: this function
 * **never throws** and never silently 401s. It always commits the
 * "wizard complete" flag to localStorage, then attempts the server
 * POST. The return value tells the caller what happened:
 *
 *   { ok: true,  synced: true,  pending: false }  — server accepted
 *   { ok: true,  synced: false, pending: true,  reason: "auth_required" }
 *     — 401/403: stashed in localStorage for flushPendingProfile()
 *   { ok: false, synced: false, pending: false, reason, message }
 *     — non-auth error (400 validation, no RENDER_API): caller should
 *       surface the message via saveError but the wizard does NOT
 *       complete.
 *
 * The previous "throw on any non-2xx" contract is preserved for
 * non-auth errors so validation regressions still bubble up to the UI.
 * Only 401/403 are translated into the soft "pending" outcome — they're
 * the only failure mode where the user genuinely can't act yet (no
 * LoginScreen until Slice 4).
 */
export async function persistProfile(state, taxonomy, opts = {}) {
  if (!RENDER_API) {
    return {
      ok: false,
      synced: false,
      pending: false,
      reason: "no_backend",
      message: "RENDER_API not configured",
    };
  }
  const body = buildProfileBody(state, taxonomy, opts);

  // Always mark the wizard complete locally first. Even if the server
  // POST fails (auth or otherwise), we don't want to re-prompt the
  // user on next mount — they've done the work and they can re-enter
  // the wizard via ?force=1 if they need to.
  lsSet(LS_WIZARD_COMPLETE, "1");
  if (opts.markPreview) lsSet(LS_WIZARD_MODE, "preview");
  else if (opts.includeOnboardedAt) lsSet(LS_WIZARD_MODE, "completed");

  let r;
  try {
    r = await postProfile(body);
  } catch (e) {
    // Network failure — treat like 401: stash for later sync, return
    // pending. The flag is already set so the user gets into the
    // dashboard; the deferred sync will retry on next login / visit.
    lsSet(LS_WIZARD_PENDING_PROFILE, JSON.stringify(body));
    return {
      ok: true,
      synced: false,
      pending: true,
      reason: "network_error",
      message: String(e?.message || e),
    };
  }

  if (r.ok) {
    // Server accepted — drop any stale pending payload (a previous
    // attempt may have failed and queued one).
    lsDel(LS_WIZARD_PENDING_PROFILE);
    try {
      return { ok: true, synced: true, pending: false, body: await r.json() };
    } catch {
      return { ok: true, synced: true, pending: false };
    }
  }

  if (r.status === 401 || r.status === 403) {
    // PIN-gated deployment, no LoginScreen yet (Slice 4 wires it).
    // Stash the body so flushPendingProfile() can replay after login.
    lsSet(LS_WIZARD_PENDING_PROFILE, JSON.stringify(body));
    return {
      ok: true,
      synced: false,
      pending: true,
      reason: "auth_required",
      message:
        "Saved on your device. Sign in (Slice 4) to sync to the server.",
    };
  }

  // 400/5xx etc. — surface the server message; do NOT stash (a 400 is
  // a permanent failure and we don't want to replay it after login).
  // Roll back the local flag so the user can try again — a validation
  // error means the wizard state is broken.
  lsDel(LS_WIZARD_COMPLETE);
  lsDel(LS_WIZARD_MODE);
  let msg = `HTTP ${r.status}`;
  try {
    const e = await r.json();
    if (e.error) msg = e.error;
  } catch (_) {}
  return {
    ok: false,
    synced: false,
    pending: false,
    reason: `http_${r.status}`,
    message: msg,
  };
}

/**
 * Replay a pending wizard commit after the user authenticates.
 *
 * Slice 4's LoginScreen calls this immediately after a successful
 * /api/login. Returns the same outcome shape as persistProfile().
 * No-ops (returning {ok: true, synced: false, pending: false,
 * reason: "nothing_pending"}) when there's no queued payload.
 */
export async function flushPendingProfile() {
  if (!RENDER_API) {
    return { ok: false, synced: false, pending: true, reason: "no_backend" };
  }
  const raw = lsGet(LS_WIZARD_PENDING_PROFILE);
  if (!raw) {
    return {
      ok: true,
      synced: false,
      pending: false,
      reason: "nothing_pending",
    };
  }
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    // Corrupted payload — drop it rather than replaying garbage.
    lsDel(LS_WIZARD_PENDING_PROFILE);
    return { ok: false, synced: false, pending: false, reason: "corrupted" };
  }
  let r;
  try {
    r = await postProfile(body);
  } catch (e) {
    return {
      ok: true,
      synced: false,
      pending: true,
      reason: "network_error",
      message: String(e?.message || e),
    };
  }
  if (r.ok) {
    lsDel(LS_WIZARD_PENDING_PROFILE);
    return { ok: true, synced: true, pending: false };
  }
  if (r.status === 401 || r.status === 403) {
    // Still not authed — keep the payload queued.
    return { ok: true, synced: false, pending: true, reason: "auth_required" };
  }
  // 400/5xx — drop, surface message.
  lsDel(LS_WIZARD_PENDING_PROFILE);
  let msg = `HTTP ${r.status}`;
  try {
    const e = await r.json();
    if (e.error) msg = e.error;
  } catch (_) {}
  return {
    ok: false,
    synced: false,
    pending: false,
    reason: `http_${r.status}`,
    message: msg,
  };
}

/**
 * Read-only helper for UI badges ("syncing…", "saved locally").
 * Slice 4's PreviewModeBanner / wizard-complete toast will read this.
 */
export function hasPendingProfile() {
  return lsGet(LS_WIZARD_PENDING_PROFILE) !== null;
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
