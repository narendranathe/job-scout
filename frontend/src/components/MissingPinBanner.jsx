/**
 * MissingPinBanner — persistent yellow banner shown when no PIN is set
 * and the user acknowledged the skip during onboarding.
 *
 * PRD #89 Slice 3. Renders at the top of the dashboard until a PIN is
 * configured. Click → re-enters the wizard at step 6 via /setup?force=1.
 *
 * Props:
 *   t:        theme tokens
 *   profile:  the /api/profile response (or null while loading)
 *
 * The decision to render is encapsulated here: only show when
 * skip_pin_acknowledged == true AND has_pin == false. The dashboard
 * mounts this unconditionally; the component self-decides whether to
 * appear.
 */
export function MissingPinBanner({ t, profile }) {
  if (!profile) return null;
  if (profile.has_pin) return null;
  if (!profile.skip_pin_acknowledged) return null;

  const goSetPin = () => {
    if (typeof window === "undefined") return;
    const u = new URL(window.location.href);
    u.pathname = "/setup";
    u.searchParams.set("force", "1");
    u.searchParams.set("step", "6"); // hint; OnboardingWizard will honour later
    window.location.href = u.toString();
  };

  return (
    <div
      role="alert"
      style={{
        background: t.wm || "#c47a00",
        color: "#fff",
        padding: "10px 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        fontSize: 13,
        fontWeight: 500,
        flexWrap: "wrap",
      }}
    >
      <span>
        ⚠️ No PIN set — anyone with this URL can edit your preferences.
      </span>
      <button
        type="button"
        onClick={goSetPin}
        style={{
          background: "rgba(255,255,255,0.18)",
          color: "#fff",
          border: "1px solid rgba(255,255,255,0.35)",
          padding: "6px 12px",
          borderRadius: 6,
          fontSize: 12,
          fontWeight: 600,
          cursor: "pointer",
          fontFamily: "inherit",
        }}
      >
        Set a PIN
      </button>
    </div>
  );
}
