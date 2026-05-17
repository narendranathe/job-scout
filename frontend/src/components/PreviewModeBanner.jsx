/**
 * PreviewModeBanner — top-of-page notice that the user is in preview mode.
 *
 * PRD #89 Slice 4 §4.2. Renders when the wizard's Step-1 skip path set
 * onboarded_at = "preview". Persists across every page load until the
 * user completes proper setup.
 *
 * The component self-decides whether to render based on the profile:
 * the App.jsx caller mounts it unconditionally.
 *
 * Click → enters /setup?force=1 to drop preview mode and walk the
 * full wizard.
 */
export function PreviewModeBanner({ t, profile }) {
  if (!profile) return null;
  if (profile.onboarded_at !== "preview") return null;

  const startSetup = () => {
    if (typeof window === "undefined") return;
    const u = new URL(window.location.href);
    u.pathname = "/setup";
    u.searchParams.set("force", "1");
    window.location.href = u.toString();
  };

  return (
    <div
      role="status"
      style={{
        background: t.acS || "#2563eb",
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
        👀 Preview mode — you can browse but can't save changes until you
        complete setup.
      </span>
      <button
        type="button"
        onClick={startSetup}
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
        Start setup
      </button>
    </div>
  );
}
