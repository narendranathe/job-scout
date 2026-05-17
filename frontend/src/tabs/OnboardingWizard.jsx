/**
 * OnboardingWizard — the first-run setup flow.
 *
 * PRD #89. This file ships Slice 2 (Steps 1-4 fully built, Steps 5-7
 * placeholders that Slice 3 fills in). Renders as a full-page blocking
 * component when App.jsx's onboarding probe routes here.
 *
 * State is a useReducer (see ../lib/wizard.js). Back-button preserves
 * everything; final commit happens on step 4 (Slice 2 interim per PRD
 * §2.7) or step 7 (Slice 3 final).
 *
 * Layout: centred card on a backdrop, scrollable when content overflows.
 * Mobile: works at 375px wide (PRD acceptance criterion).
 */
import { useEffect, useMemo, useReducer, useState } from "react";

import { TH } from "../lib/theme.js";
import { RENDER_API, authHeaders } from "../lib/api.js";
import {
  TOTAL_STEPS,
  STEP_LABELS,
  initialWizardState,
  wizardReducer,
  fetchRosters,
  persistProfile,
} from "../lib/wizard.js";
import { ChipCloud } from "../components/ChipCloud.jsx";
import { StepProgress } from "../components/StepProgress.jsx";
// Slice 3 step components — replace the Step5/6 placeholders that
// shipped with Slice 2.
import { PdfDropzone } from "../components/PdfDropzone.jsx";
import { PinSetup } from "../components/PinSetup.jsx";
import { BulkUploadHelpCard } from "../components/BulkUploadHelpCard.jsx";

const CSRF_LS_KEY = "jobscout_csrf";

const BG_OVERLAY = "rgba(0,0,0,0.5)";

export function OnboardingWizard({ mode = "light", onComplete, onSkip }) {
  const t = TH[mode];
  const [state, dispatch] = useReducer(wizardReducer, undefined, initialWizardState);
  const [rosters, setRosters] = useState({ roles: [], companies: [], locations: [] });
  const [rostersLoaded, setRostersLoaded] = useState(false);

  // Fetch all three rosters in parallel on mount. We don't block the
  // wizard if they fail — pickers just render empty and the user can
  // type free-text values.
  useEffect(() => {
    let cancelled = false;
    fetchRosters().then((r) => {
      if (!cancelled) {
        setRosters(r);
        setRostersLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Step gating ──────────────────────────────────────────────────
  // PRD G2 hard requirement: at least one role selected before step 2 can
  // advance. Custom roles count too — a user who typed "Robotics Engineer"
  // hasn't picked from the taxonomy but has expressed intent.
  const canAdvanceStep2 =
    state.roles.length > 0 || state.customRoles.length > 0;

  // ── Step-7 final commit (Slice 3) ───────────────────────────────
  // Slice 2 committed at the end of step 4; Slice 3 moves the commit
  // to step 7 so default_resume_version + skip_pin_acknowledged are
  // included in the same POST. Step 4 now just advances to step 5.
  const finalCommit = async () => {
    dispatch({ type: "SAVE_START" });
    try {
      await persistProfile(state, rosters.roles, {
        includeOnboardedAt: true,
        ...(state.uploadedResumeVersion
          ? { defaultResumeVersion: state.uploadedResumeVersion }
          : {}),
        ...(state.skipPinAcknowledged
          ? { skipPinAcknowledged: true }
          : {}),
      });
      dispatch({ type: "SAVE_OK" });
      onComplete?.();
    } catch (e) {
      dispatch({ type: "SAVE_FAIL", message: String(e?.message || e) });
    }
  };

  // Read the CSRF token live so step 6's /api/login refresh propagates
  // without re-rendering the wizard.
  const getCsrf = () => {
    if (typeof window === "undefined") return "";
    try {
      return window.localStorage.getItem(CSRF_LS_KEY) || "";
    } catch {
      return "";
    }
  };
  const setCsrf = (csrf) => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(CSRF_LS_KEY, csrf);
    } catch {}
  };

  // Skip path from Step 1 — sets onboarded_at to the sentinel "preview".
  // Slice 4 enforces the read-only mode; here we just persist the marker
  // so the wizard doesn't re-fire on next reload.
  const skipWizard = async () => {
    dispatch({ type: "SAVE_START" });
    try {
      await persistProfile(state, rosters.roles, { markPreview: true });
      dispatch({ type: "SAVE_OK" });
      onSkip?.();
    } catch (e) {
      // Even on failure, fall through — preview mode is best-effort.
      dispatch({ type: "SAVE_FAIL", message: String(e?.message || e) });
      onSkip?.();
    }
  };

  // ── Roster shaping for the pickers ───────────────────────────────
  const roleOptions = useMemo(
    () =>
      (rosters.roles || []).map((r) => ({
        value: r.key,
        label: r.label,
        sublabel: r.abbrevs?.[0] ? `(${r.abbrevs[0]})` : "",
      })),
    [rosters.roles]
  );

  const companyOptions = useMemo(
    () =>
      (rosters.companies || []).map((c) => ({
        value: c.name,
        label: c.name,
        sublabel: c.job_count_30d > 0 ? `${c.job_count_30d} open` : "",
        group: c.tier_label || "Other",
      })),
    [rosters.companies]
  );

  const locationOptions = useMemo(
    () =>
      (rosters.locations || []).slice(0, 80).map((l) => ({
        value: l.location,
        label: l.location,
        sublabel: l.job_count > 1 ? `${l.job_count}` : "",
      })),
    [rosters.locations]
  );

  const customRoleSelected = useMemo(
    () => new Set([...state.roles, ...state.customRoles]),
    [state.roles, state.customRoles]
  );

  // ── Render ──────────────────────────────────────────────────────
  const overlay = {
    position: "fixed",
    inset: 0,
    background: BG_OVERLAY,
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "center",
    padding: "20px",
    overflowY: "auto",
    zIndex: 1000,
  };
  const card = {
    background: t.cd,
    color: t.tx,
    border: `1px solid ${t.bd}`,
    borderRadius: 14,
    padding: "28px",
    maxWidth: 720,
    width: "100%",
    margin: "20px auto",
    fontFamily: "inherit",
    boxShadow: t.shL || "0 12px 40px rgba(0,0,0,0.35)",
  };
  const heading = {
    fontFamily: "'Playfair Display', serif",
    fontSize: 28,
    margin: "8px 0 4px",
  };
  const sub = { color: t.txM, fontSize: 14, marginBottom: 20 };
  const btnPrimary = {
    padding: "11px 22px",
    borderRadius: 8,
    border: `1px solid ${t.ac}`,
    background: t.ac,
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "inherit",
  };
  const btnSecondary = {
    padding: "11px 22px",
    borderRadius: 8,
    border: `1px solid ${t.bd}`,
    background: "transparent",
    color: t.tx,
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "inherit",
  };

  return (
    <div style={overlay}>
      <div style={card}>
        <StepProgress
          step={state.step}
          total={TOTAL_STEPS}
          labels={STEP_LABELS}
          onJump={(s) => dispatch({ type: "GO_TO_STEP", step: s })}
          t={t}
        />

        {state.saveError && (
          <div
            style={{
              padding: "10px 14px",
              borderRadius: 8,
              background: t.er || "#fee",
              color: "#900",
              border: "1px solid #f99",
              fontSize: 13,
              marginBottom: 16,
            }}
          >
            Could not save: {state.saveError}
          </div>
        )}

        {/* ─── Step 1: Welcome ─── */}
        {state.step === 1 && (
          <>
            <h1 style={heading}>Welcome to JobScout.</h1>
            <p style={sub}>
              A two-minute setup so the dashboard knows what to surface for you.
              You can skip any step except role selection.
            </p>
            <ul style={{ color: t.tx, fontSize: 14, lineHeight: 1.7, paddingLeft: 18 }}>
              <li>Pick the roles you're targeting</li>
              <li>Pick (or type) your target companies</li>
              <li>Optional: locations &amp; minimum comp</li>
              <li>Upload your resume so we can score every job against it</li>
              <li>Optional: set a PIN so only you can change preferences</li>
            </ul>
            <div style={{ display: "flex", gap: 12, marginTop: 28 }}>
              <button
                type="button"
                style={btnPrimary}
                onClick={() => dispatch({ type: "NEXT" })}
              >
                Get started →
              </button>
              <button
                type="button"
                style={btnSecondary}
                onClick={skipWizard}
                disabled={state.saving}
                title="Browse the dashboard read-only — you can come back any time"
              >
                Skip — I'm just looking
              </button>
            </div>
          </>
        )}

        {/* ─── Step 2: Roles ─── */}
        {state.step === 2 && (
          <>
            <h1 style={heading}>Which roles?</h1>
            <p style={sub}>
              Pick everything you'd consider. Add custom titles if the
              taxonomy doesn't cover a niche you target.
            </p>
            <ChipCloud
              options={roleOptions}
              selected={customRoleSelected}
              onToggle={(value) => {
                // Picker chips toggle into `roles`; custom chips into
                // `customRoles`. ChipCloud doesn't know the distinction,
                // so we route by whether the value appears in roleOptions.
                if (roleOptions.some((o) => o.value === value)) {
                  dispatch({ type: "TOGGLE_ROLE", roleKey: value });
                } else {
                  dispatch({ type: "REMOVE_CUSTOM_ROLE", value });
                }
              }}
              onAdd={(value) =>
                dispatch({ type: "ADD_CUSTOM_ROLE", value })
              }
              onRemove={(value) =>
                dispatch({ type: "REMOVE_CUSTOM_ROLE", value })
              }
              t={t}
              placeholder="Add a custom role (e.g. Robotics Engineer)"
              emptyHint={
                rostersLoaded ? "No roles loaded" : "Loading roles…"
              }
            />
            <FooterNav
              t={t}
              onBack={() => dispatch({ type: "BACK" })}
              onNext={() => dispatch({ type: "NEXT" })}
              nextDisabled={!canAdvanceStep2}
              nextHint={
                canAdvanceStep2 ? null : "Pick at least one role to continue"
              }
            />
          </>
        )}

        {/* ─── Step 3: Companies ─── */}
        {state.step === 3 && (
          <>
            <h1 style={heading}>Which companies?</h1>
            <p style={sub}>
              Pick from the roster JobScout already scrapes, or type any
              name to track it. Typed names trigger alerts when matching
              jobs surface (Slice 4 wires the maintainer ping for
              not-yet-scraped names).
            </p>
            <ChipCloud
              options={companyOptions}
              selected={
                new Set([...state.pickedCompanies, ...state.trackedCompanies])
              }
              onToggle={(value) => {
                if (companyOptions.some((o) => o.value === value)) {
                  dispatch({ type: "TOGGLE_PICKED_COMPANY", name: value });
                } else {
                  dispatch({ type: "REMOVE_TRACKED_COMPANY", name: value });
                }
              }}
              onAdd={(value) =>
                dispatch({ type: "ADD_TRACKED_COMPANY", name: value })
              }
              onRemove={(value) =>
                dispatch({ type: "REMOVE_TRACKED_COMPANY", name: value })
              }
              t={t}
              placeholder="Type a company name…"
              emptyHint={
                rostersLoaded ? "No companies loaded" : "Loading companies…"
              }
              searchable={true}
              maxHeight={380}
            />
            <div style={{ marginTop: 12, color: t.txM, fontSize: 13 }}>
              {state.pickedCompanies.length} picked · {state.trackedCompanies.length} typed-to-track
            </div>
            <FooterNav
              t={t}
              onBack={() => dispatch({ type: "BACK" })}
              onNext={() => dispatch({ type: "NEXT" })}
            />
          </>
        )}

        {/* ─── Step 4: Locations & Comp ─── */}
        {state.step === 4 && (
          <>
            <h1 style={heading}>Locations &amp; compensation</h1>
            <p style={sub}>
              All optional — leave blank to see every match regardless of
              where it's based or what it pays.
            </p>
            <div style={{ marginBottom: 24 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: ".06em",
                  color: t.txM,
                  marginBottom: 8,
                }}
              >
                Preferred locations
              </div>
              <ChipCloud
                options={locationOptions}
                selected={state.locations}
                onToggle={(value) => {
                  if (locationOptions.some((o) => o.value === value)) {
                    dispatch({ type: "TOGGLE_LOCATION", location: value });
                  } else {
                    dispatch({ type: "TOGGLE_LOCATION", location: value });
                  }
                }}
                onAdd={(value) =>
                  dispatch({ type: "ADD_CUSTOM_LOCATION", value })
                }
                onRemove={(value) =>
                  dispatch({ type: "TOGGLE_LOCATION", location: value })
                }
                t={t}
                placeholder="Add a city (e.g. Boulder, CO)"
                emptyHint={
                  rostersLoaded
                    ? "No locations seen in last 30 days — type your own"
                    : "Loading locations…"
                }
                maxHeight={240}
              />
            </div>

            <div style={{ marginBottom: 24 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: ".06em",
                  color: t.txM,
                  marginBottom: 8,
                }}
              >
                Minimum total comp (USD/yr)
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <input
                  type="range"
                  min="0"
                  max="500000"
                  step="10000"
                  value={state.minTotalComp}
                  onChange={(e) =>
                    dispatch({ type: "SET_MIN_COMP", value: e.target.value })
                  }
                  style={{ flex: 1 }}
                />
                <div
                  style={{
                    minWidth: 110,
                    fontSize: 14,
                    fontWeight: 600,
                    color: t.tx,
                    textAlign: "right",
                  }}
                >
                  {state.minTotalComp === 0
                    ? "Any salary"
                    : `$${state.minTotalComp.toLocaleString()}`}
                </div>
              </div>
            </div>

            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 14,
                color: t.tx,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={state.showUnsalaried}
                onChange={(e) =>
                  dispatch({
                    type: "SET_SHOW_UNSALARIED",
                    value: e.target.checked,
                  })
                }
              />
              Show jobs with no salary listed
            </label>

            <FooterNav
              t={t}
              onBack={() => dispatch({ type: "BACK" })}
              onNext={() => dispatch({ type: "NEXT" })}
              nextLabel="Continue →"
            />
          </>
        )}

        {/* ─── Step 5: Resume Vault (Slice 3) ─── */}
        {state.step === 5 && (
          <>
            <h1 style={heading}>Add a resume</h1>
            <p style={sub}>
              Drop a single PDF to set as your default — or skip to the
              CLI helper below for bulk-uploading a folder.
            </p>
            <PdfDropzone
              t={t}
              apiBase={RENDER_API}
              authHeaders={authHeaders}
              csrfToken={getCsrf()}
              onUploaded={(result) => {
                if (result?.version_key) {
                  dispatch({
                    type: "SET_UPLOADED_RESUME",
                    versionKey: result.version_key,
                  });
                }
              }}
            />
            <div style={{ marginTop: 24 }}>
              <BulkUploadHelpCard
                t={t}
                apiBase={RENDER_API}
                apiToken={
                  typeof window !== "undefined"
                    ? window.localStorage.getItem("vault_token") || ""
                    : ""
                }
              />
            </div>
            <FooterNav
              t={t}
              onBack={() => dispatch({ type: "BACK" })}
              onNext={() => dispatch({ type: "NEXT" })}
              nextLabel={
                state.uploadedResumeVersion ? "Continue →" : "Skip for now →"
              }
            />
          </>
        )}

        {/* ─── Step 6: PIN (Slice 3) ─── */}
        {state.step === 6 && (
          <>
            <h1 style={heading}>Set a PIN</h1>
            <p style={sub}>
              Protects your preferences from anyone else who has this
              dashboard URL. You can change or remove it later from the
              Monitor tab.
            </p>
            <PinSetup
              t={t}
              apiBase={RENDER_API}
              authHeaders={authHeaders}
              csrfToken={getCsrf()}
              onPinSet={() => {
                dispatch({ type: "SET_PIN_SET" });
                dispatch({ type: "NEXT" });
              }}
              onSkip={() => {
                dispatch({ type: "SET_SKIP_PIN_ACK" });
                dispatch({ type: "NEXT" });
              }}
              onCsrfRefresh={(csrf) => setCsrf(csrf)}
            />
            <FooterNav
              t={t}
              onBack={() => dispatch({ type: "BACK" })}
              onNext={() => dispatch({ type: "NEXT" })}
              nextLabel="Skip step →"
            />
          </>
        )}

        {/* ─── Step 7: Done ─── */}
        {state.step === 7 && (
          <>
            <h1 style={heading}>You're set.</h1>
            <p style={sub}>
              {state.roles.length + state.customRoles.length} roles ·{" "}
              {state.pickedCompanies.length + state.trackedCompanies.length} companies ·{" "}
              {state.uploadedResumeVersion ? "1" : "0"} resume — let's find your next job.
            </p>
            <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
              <button
                type="button"
                style={btnPrimary}
                disabled={state.saving}
                onClick={finalCommit}
              >
                {state.saving ? "Saving…" : "Go to dashboard →"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Footer nav ─────────────────────────────────────────────────── */

function FooterNav({ t, onBack, onNext, nextDisabled, nextHint, nextLabel }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginTop: 28,
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <button
        type="button"
        onClick={onBack}
        style={{
          padding: "11px 22px",
          borderRadius: 8,
          border: `1px solid ${t.bd}`,
          background: "transparent",
          color: t.tx,
          fontSize: 14,
          fontWeight: 600,
          cursor: "pointer",
          fontFamily: "inherit",
        }}
      >
        ← Back
      </button>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        {nextHint && (
          <span style={{ color: t.txM, fontSize: 12 }}>{nextHint}</span>
        )}
        <button
          type="button"
          onClick={onNext}
          disabled={nextDisabled}
          style={{
            padding: "11px 22px",
            borderRadius: 8,
            border: `1px solid ${nextDisabled ? t.bd : t.ac}`,
            background: nextDisabled ? t.bgS : t.ac,
            color: nextDisabled ? t.txM : "#fff",
            fontSize: 14,
            fontWeight: 600,
            cursor: nextDisabled ? "not-allowed" : "pointer",
            fontFamily: "inherit",
          }}
        >
          {nextLabel || "Continue →"}
        </button>
      </div>
    </div>
  );
}

