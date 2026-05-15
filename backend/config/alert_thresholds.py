"""Per-tier alert thresholds for the dream-job notifier.

Each tier maps to the minimum relevance_score that triggers an alert.
A platinum-tier company at 0.45 is worth knowing about; a tier-1 company
at the same score is not. The default is the fallback for jobs where the
tier was not set during scoring.

Env var override: ALERT_THRESHOLDS_OVERRIDE (JSON) lets ops swap values
without redeploy. Example:
  ALERT_THRESHOLDS_OVERRIDE='{"platinum": 0.35, "tier1": 0.65}'
"""

import json
import os

ALERT_THRESHOLDS = {
    "default": 0.70,
    # tier=0 in companies.py is mapped to 'platinum' in main.py; matches CLAUDE.md
    # ("relevance_score >= 0.40 for dream companies").
    "platinum": 0.40,
    "tier1": 0.55,
    "tier2": 0.70,
    "tier3": 0.80,
    # Alias so callers using either name still resolve correctly.
    "tier0": 0.40,
}

_override = os.environ.get("ALERT_THRESHOLDS_OVERRIDE", "").strip()
if _override:
    try:
        ALERT_THRESHOLDS.update(json.loads(_override))
    except json.JSONDecodeError:
        # Bad JSON in env — keep defaults rather than crash the notifier.
        pass


def threshold_for(tier: str) -> float:
    """Return the alert threshold for a given tier label.

    Tier labels match what main.py writes to raw_job["tier"]:
    'platinum', 'tier0', 'tier1', 'tier2', 'tier3'. Unknown labels
    fall through to the default.
    """
    if not tier:
        return ALERT_THRESHOLDS["default"]
    return ALERT_THRESHOLDS.get(tier.lower(), ALERT_THRESHOLDS["default"])
