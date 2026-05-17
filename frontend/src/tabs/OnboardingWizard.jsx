/**
 * OnboardingWizard — scaffolding for Slice 2 of issue #89.
 *
 * Tracking:  https://github.com/narendranathe/job-scout/issues/91
 * Parent PRD: https://github.com/narendranathe/job-scout/issues/89
 * Spec:      docs/superpowers/specs/2026-05-17-first-run-onboarding-wizard.md
 *
 * This file is the empty shell for the 7-step onboarding wizard.
 * Slice 2 implements steps 1–4 (welcome, roles, companies, locations).
 * Slice 3 (#92) inserts steps 5–6 (vault, PIN) before the final commit.
 * Slice 4 (#93) wires the routing + read-only preview enforcement.
 *
 * Backend dependency: Slice 1 (#90) must land first — this component
 * fetches /api/role-taxonomy, /api/companies-roster, /api/locations-roster
 * and posts to the extended /api/profile.
 *
 * State shape (useReducer):
 *   {
 *     step: 1..7,                    // current step
 *     roles: string[],               // canonical role keys (taxonomy)
 *     customRoles: string[],         // user-added off-taxonomy roles
 *     pickedCompanies: string[],     // selected from roster
 *     trackedCompanies: string[],    // typed but not in roster
 *     locations: string[],           // preferred locations
 *     minTotalComp: number,          // 0 = off
 *     showUnsalaried: boolean,       // default true
 *     // Slice 3 adds:
 *     uploadedResume: {versionKey, company, role, submittedAt} | null,
 *     pin: string | null,
 *     skipPinAcknowledged: boolean,
 *   }
 *
 * Acceptance criteria for Slice 2 (see issue #91 for full list):
 *   - First-run detection auto-redirects to /setup
 *   - /setup?force=1 always shows the wizard
 *   - Steps 1–4 navigable forward and back; state preserved
 *   - Step 2 "Continue" disabled until ≥ 1 role selected
 *   - Step 4 fully skippable with safe defaults
 *   - On final commit: POST /api/profile, redirect to Jobs tab
 *   - Visual smoke: 375px viewport, no horizontal scroll
 */

import React, { useReducer, useEffect } from 'react';

// TODO(slice-2): replace with shared API helper if one lands during Slice 1
const API = (import.meta.env.VITE_RENDER_URL || '').replace(/\/+$/, '');

const initialState = {
  step: 1,
  roles: [],
  customRoles: [],
  pickedCompanies: [],
  trackedCompanies: [],
  locations: [],
  minTotalComp: 0,
  showUnsalaried: true,
  // Slice 3 fields — left null/false so the reducer doesn't error
  uploadedResume: null,
  pin: null,
  skipPinAcknowledged: false,
};

function reducer(state, action) {
  switch (action.type) {
    case 'NEXT':
      return { ...state, step: Math.min(state.step + 1, 7) };
    case 'BACK':
      return { ...state, step: Math.max(state.step - 1, 1) };
    case 'GOTO':
      return { ...state, step: action.step };
    case 'SET':
      return { ...state, [action.field]: action.value };
    case 'TOGGLE_ROLE': {
      const has = state.roles.includes(action.role);
      return {
        ...state,
        roles: has
          ? state.roles.filter((r) => r !== action.role)
          : [...state.roles, action.role],
      };
    }
    case 'TOGGLE_COMPANY': {
      const has = state.pickedCompanies.includes(action.company);
      return {
        ...state,
        pickedCompanies: has
          ? state.pickedCompanies.filter((c) => c !== action.company)
          : [...state.pickedCompanies, action.company],
      };
    }
    case 'TRACK_COMPANY':
      return state.trackedCompanies.includes(action.company)
        ? state
        : { ...state, trackedCompanies: [...state.trackedCompanies, action.company] };
    default:
      return state;
  }
}

export default function OnboardingWizard() {
  const [state, dispatch] = useReducer(reducer, initialState);

  // TODO(slice-2): fetch /api/role-taxonomy + /api/companies-roster +
  // /api/locations-roster on mount and stash in component state.
  useEffect(() => {
    // no-op scaffold
  }, []);

  return (
    <div style={{ maxWidth: 720, margin: '40px auto', padding: 16 }}>
      <StepProgress current={state.step} total={7} />
      {state.step === 1 && <Step1Welcome dispatch={dispatch} />}
      {state.step === 2 && <Step2Roles state={state} dispatch={dispatch} />}
      {state.step === 3 && <Step3Companies state={state} dispatch={dispatch} />}
      {state.step === 4 && <Step4Locations state={state} dispatch={dispatch} />}
      {/* Slice 3 inserts Steps 5–6 here */}
      {state.step >= 5 && <PlaceholderStep state={state} dispatch={dispatch} />}
    </div>
  );
}

function StepProgress({ current, total }) {
  return (
    <div style={{ marginBottom: 24, fontSize: 13, opacity: 0.7 }}>
      Step {current} of {total}
    </div>
  );
}

// ── Step 1 — Welcome ────────────────────────────────────────────────
function Step1Welcome({ dispatch }) {
  return (
    <div>
      <h1>Welcome to JobScout</h1>
      <p>
        We'll personalize your dashboard in about 5 minutes — pick your
        target roles, the companies you care about, and (optionally)
        upload a resume so we can match it against new postings.
      </p>
      <button onClick={() => dispatch({ type: 'NEXT' })}>Get started</button>
      <button onClick={() => {/* TODO(slice-4): skip → preview mode */}}>
        Skip — I'm just looking
      </button>
    </div>
  );
}

// ── Step 2 — Roles ──────────────────────────────────────────────────
function Step2Roles({ state, dispatch }) {
  // TODO(slice-2): render chip cloud from fetched taxonomy
  // TODO(slice-2): free-text "Add another" input → customRoles
  // TODO(slice-2): disable "Continue" until state.roles.length > 0
  return (
    <div>
      <h2>What roles are you targeting?</h2>
      <p>Pick all that apply. We use this to rank jobs.</p>
      <pre>{JSON.stringify({ roles: state.roles, customRoles: state.customRoles }, null, 2)}</pre>
      <button onClick={() => dispatch({ type: 'BACK' })}>Back</button>
      <button onClick={() => dispatch({ type: 'NEXT' })}>Continue</button>
    </div>
  );
}

// ── Step 3 — Companies ──────────────────────────────────────────────
function Step3Companies({ state, dispatch }) {
  // TODO(slice-2): two tabs — Pick from list (chip cloud, grouped by tier)
  //                          Type a name (autocomplete + "track anyway")
  // TODO(slice-2): live preview: "{N} selected · ~{M} matching jobs"
  return (
    <div>
      <h2>Which companies do you care about?</h2>
      <pre>{JSON.stringify({
        picked: state.pickedCompanies,
        tracked: state.trackedCompanies,
      }, null, 2)}</pre>
      <button onClick={() => dispatch({ type: 'BACK' })}>Back</button>
      <button onClick={() => dispatch({ type: 'NEXT' })}>Continue</button>
    </div>
  );
}

// ── Step 4 — Locations & Compensation ───────────────────────────────
function Step4Locations({ state, dispatch }) {
  // TODO(slice-2): locations chip-input + autocomplete
  // TODO(slice-2): min total comp slider, show_unsalaried toggle
  // TODO(slice-2): on Continue (or Finish in Slice 2), POST /api/profile
  return (
    <div>
      <h2>Locations & compensation (optional)</h2>
      <pre>{JSON.stringify({
        locations: state.locations,
        minTotalComp: state.minTotalComp,
        showUnsalaried: state.showUnsalaried,
      }, null, 2)}</pre>
      <button onClick={() => dispatch({ type: 'BACK' })}>Back</button>
      <button onClick={() => dispatch({ type: 'NEXT' })}>Finish</button>
    </div>
  );
}

function PlaceholderStep({ state }) {
  return (
    <div>
      <p>
        Step {state.step} lands in a later slice (vault / PIN / done).
        For Slice 2, the wizard exits here by POSTing to /api/profile
        and redirecting to the Jobs tab.
      </p>
    </div>
  );
}
