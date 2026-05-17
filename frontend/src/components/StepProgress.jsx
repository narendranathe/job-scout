/**
 * StepProgress — horizontal "1/7 → 2/7 → …" indicator for the wizard.
 *
 * Pure presentation, no state. Clicking a step jumps to it via
 * onJump(step) when allowed (only steps the user has already passed).
 *
 * Props:
 *   step:       current step (1-based)
 *   total:      total steps
 *   labels:     {1: "Welcome", 2: "Roles", ...} — string per step
 *   onJump:     optional (stepNumber) => void; enabled for past steps only
 *   t:          theme tokens
 */
export function StepProgress({ step, total, labels, onJump, t }) {
  const steps = Array.from({ length: total }, (_, i) => i + 1);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        flexWrap: "wrap",
        margin: "0 auto 24px",
      }}
      aria-label={`Step ${step} of ${total}`}
    >
      {steps.map((s, i) => {
        const isActive = s === step;
        const isComplete = s < step;
        const isClickable = onJump && s < step;
        const dotColor = isActive ? t.ac : isComplete ? t.ok : t.bd;

        return (
          <div
            key={s}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <button
              type="button"
              onClick={() => isClickable && onJump(s)}
              disabled={!isClickable}
              aria-current={isActive ? "step" : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderRadius: 18,
                border: `1px solid ${isActive ? t.ac : isComplete ? t.ok : t.bd}`,
                background: isActive ? t.ac : "transparent",
                color: isActive ? "#fff" : isComplete ? t.ok : t.txM,
                cursor: isClickable ? "pointer" : "default",
                fontSize: 12,
                fontWeight: 600,
                fontFamily: "inherit",
                transition: "all .12s",
              }}
              title={
                isClickable
                  ? `Go back to step ${s}`
                  : isActive
                  ? "Current step"
                  : "Not yet reached"
              }
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  background: isActive ? "#fff" : dotColor,
                  color: isActive ? t.ac : "#fff",
                  fontSize: 11,
                  fontWeight: 700,
                  lineHeight: 1,
                }}
              >
                {isComplete ? "✓" : s}
              </span>
              <span>{labels?.[s] || ""}</span>
            </button>
            {i < steps.length - 1 && (
              <span
                aria-hidden
                style={{
                  width: 12,
                  height: 1,
                  background: s < step ? t.ok : t.bd,
                  marginRight: -2,
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
