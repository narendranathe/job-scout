"""
JobScout Alert Notifier — fires when a new dream job is found.

Supports 4 channels (set whichever env vars you have — all are optional):

  ┌─────────────────────────────────────────────────────────────────────┐
  │  FREE (no limits, no expiry)                                        │
  │  ─────────────────────────────────────────────────────────────────  │
  │  Discord  → DISCORD_WEBHOOK_URL                                     │
  │  Telegram → TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID                  │
  │                                                                     │
  │  PAID / TRIAL (great for forks that have these accounts)            │
  │  ─────────────────────────────────────────────────────────────────  │
  │  Slack    → SLACK_WEBHOOK_URL          (30-day free trial)          │
  │  WhatsApp → TWILIO_ACCOUNT_SID         ($15 free credit then paid)  │
  │             TWILIO_AUTH_TOKEN                                        │
  │             TWILIO_WHATSAPP_FROM                                     │
  │             TWILIO_WHATSAPP_TO                                       │
  └─────────────────────────────────────────────────────────────────────┘

Alert criteria (both must be true):
  1. job relevance_score >= ALERT_MIN_SCORE  (default 0.65)
  2. company is in DREAM_COMPANIES
  3. job title contains a DREAM_ROLE_KEYWORD

Setup guides:
  Discord:  Server Settings → Integrations → Webhooks → New Webhook → Copy URL
  Telegram: @BotFather → /newbot → get token; then message your bot → get chat_id
            from https://api.telegram.org/bot<TOKEN>/getUpdates
  Slack:    api.slack.com/apps → Incoming Webhooks → Add to Workspace
  WhatsApp: twilio.com → Messaging → Try WhatsApp → Sandbox
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

# ── Channel credentials ────────────────────────────────────────────────────
# Free channels
DISCORD_WEBHOOK  = os.environ.get("DISCORD_WEBHOOK_URL", "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Tailor-resume integration ──────────────────────────────────────────────
# Optional — if set, the notifier will call the tailor-resume API before
# each dream-job alert and attach a note if a tailored .tex was generated.
#
#   TAILOR_RESUME_API_URL      — base URL of tailor-resume API
#                                (e.g. https://tailor-resume-api.fly.dev)
#   TAILOR_RESUME_PROFILE_PATH — path to a plain-text profile/resume file
#                                used as the "artifact" for tailoring
#
# Both are optional. If TAILOR_RESUME_API_URL is not set the call is skipped
# entirely (no error, no slowdown). If the API is unreachable the alert fires
# normally — the tailoring step is strictly best-effort.
TAILOR_RESUME_API_URL      = os.environ.get("TAILOR_RESUME_API_URL", "")
TAILOR_RESUME_PROFILE_PATH = os.environ.get("TAILOR_RESUME_PROFILE_PATH", "")

# Paid / trial channels (kept for forkers)
SLACK_WEBHOOK  = os.environ.get("SLACK_WEBHOOK_URL", "")
TWILIO_SID     = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM    = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_TO      = os.environ.get("TWILIO_WHATSAPP_TO", "")

# ── Alert criteria ─────────────────────────────────────────────────────────
# Per-tier thresholds live in config/alert_thresholds.py. The legacy
# DREAM_ALERT_SCORE env var, if set, overrides every tier with a single value
# (kept for users who want a flat threshold). Otherwise, a job's threshold is
# resolved from its company tier: platinum=0.40, tier1=0.55, tier2=0.70, tier3=0.80.
from config.alert_thresholds import threshold_for, ALERT_THRESHOLDS  # noqa: E402

DREAM_ALERT_SCORE_OVERRIDE = os.environ.get("DREAM_ALERT_SCORE")  # legacy escape hatch
ALERT_MIN_SCORE = float(os.environ.get("ALERT_MIN_SCORE", "0.65"))

DREAM_COMPANIES = {
    s.strip().lower()
    for s in os.environ.get("DREAM_COMPANIES", "").split(",")
    if s.strip()
}
DREAM_ROLE_KEYWORDS = [
    s.strip().lower()
    for s in os.environ.get(
        "DREAM_ROLE_KEYWORDS",
        "data engineer,senior data engineer,sr data engineer,ml engineer,"
        "ai engineer,analytics engineer,analytical engineer,data platform engineer,"
        "staff data engineer,principal data engineer,lead data engineer"
    ).split(",")
    if s.strip()
]


# ── Tailor-resume helper ────────────────────────────────────────────────────

def _tailor_resume_for_job(job: dict):
    """
    Best-effort call to the tailor-resume API.

    Returns the tex_b64 string on success, or None if:
      - TAILOR_RESUME_API_URL is not configured
      - The API times out (5 s hard limit)
      - Any other network / HTTP error occurs

    The alert pipeline must NEVER fail because of this function — all
    exceptions are caught and logged at WARNING level only.
    """
    if not TAILOR_RESUME_API_URL:
        return None

    jd_text = job.get("description") or ""

    # Load profile artifact from disk if a path was provided
    artifact = "No profile provided"
    if TAILOR_RESUME_PROFILE_PATH:
        try:
            with open(TAILOR_RESUME_PROFILE_PATH, "r", encoding="utf-8") as fh:
                artifact = fh.read().strip() or artifact
        except Exception as e:
            log.warning("Could not read TAILOR_RESUME_PROFILE_PATH (%s): %s", TAILOR_RESUME_PROFILE_PATH, e)

    try:
        resp = requests.post(
            f"{TAILOR_RESUME_API_URL.rstrip('/')}/api/v1/resume/tailor",
            json={"jd_text": jd_text, "artifact": artifact},
            timeout=5,
        )
        if resp.ok:
            data = resp.json()
            tex_b64 = data.get("tex_b64")
            if tex_b64:
                log.info("Tailor-resume: .tex generated for %s @ %s", job.get("title"), job.get("company"))
                return tex_b64
            log.warning("Tailor-resume: API returned OK but no tex_b64 in response")
        else:
            log.warning("Tailor-resume: API returned %d — %s", resp.status_code, resp.text[:200])
    except requests.exceptions.Timeout:
        log.warning("Tailor-resume: API timed out after 5 s — skipping for %s @ %s",
                    job.get("title"), job.get("company"))
    except Exception as e:
        log.warning("Tailor-resume: API call failed (%s) — alert will fire without tailored resume", e)

    return None


# ── Public API ─────────────────────────────────────────────────────────────

def is_dream_job(job: dict) -> bool:
    """
    Returns True when ALL three conditions are met:
      1. job.tier resolves to a tier-specific threshold (platinum 0.40, tier1 0.55, ...)
         OR DREAM_ALERT_SCORE_OVERRIDE is set and acts as a flat threshold.
      2. Relevance score >= the resolved threshold.
      3. Job title contains one of DREAM_ROLE_KEYWORDS.

    DREAM_COMPANIES (env var) is now an OPTIONAL allowlist — if set, only those
    companies fire alerts. If unset, the tier system alone decides eligibility.
    """
    if not DREAM_ROLE_KEYWORDS:
        return False

    # Optional company allowlist — preserved for users who want strict control.
    if DREAM_COMPANIES:
        company_low = job.get("company", "").lower()
        if company_low not in DREAM_COMPANIES:
            return False

    # Threshold: env override beats tier table. Both apply per-job.
    if DREAM_ALERT_SCORE_OVERRIDE:
        try:
            threshold = float(DREAM_ALERT_SCORE_OVERRIDE)
        except ValueError:
            threshold = threshold_for(job.get("tier", ""))
    else:
        threshold = threshold_for(job.get("tier", ""))

    score = job.get("relevance_score", 0.0)
    if score < threshold:
        return False

    title = job.get("title", "").lower()
    return any(kw in title for kw in DREAM_ROLE_KEYWORDS)


def notify_dream_job(job: dict) -> bool:
    """
    Send alerts for a matched dream job across all configured channels.
    Returns True if at least one channel successfully delivered.
    """
    if not is_dream_job(job):
        return False

    company  = job.get("company", "Unknown")
    title    = job.get("title", "Unknown")
    location = job.get("location", "")
    url      = job.get("url", "")
    score    = job.get("relevance_score", 0.0)
    sal_min  = job.get("salary_min", 0)
    sal_max  = job.get("salary_max", 0)
    skills   = job.get("matched_skills", [])
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]

    sal_text   = f"${sal_min // 1000}K–${sal_max // 1000}K" if sal_max else ""
    skills_text = ", ".join(skills[:6]) if skills else "—"
    score_pct  = f"{int(score * 100)}%"

    # ── Tailor resume (best-effort) ────────────────────────────
    tex_b64 = _tailor_resume_for_job(job)
    tailor_note = (
        "\nResume:   Tailored .tex generated — download from job dashboard"
        if tex_b64 else ""
    )

    # Plain text for channels that don't support rich formatting
    plain = (
        f"🎯 DREAM JOB ALERT\n"
        f"Role:     {title}\n"
        f"Company:  {company}\n"
        f"Location: {location or 'Not specified'}\n"
        f"Match:    {score_pct}\n"
        f"Skills:   {skills_text}\n"
        + (f"Salary:   {sal_text}\n" if sal_text else "")
        + f"Apply:    {url}"
        + tailor_note
    )

    results = []

    # ── Free channels ──────────────────────────────────────────
    if DISCORD_WEBHOOK:
        results.append(("Discord", _send_discord(
            company, title, location, url, score_pct, sal_text, skills_text, tex_b64=tex_b64,
        )))

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        results.append(("Telegram", _send_telegram(plain)))

    # ── Paid / trial channels (kept for forkers) ───────────────
    if SLACK_WEBHOOK:
        results.append(("Slack", _send_slack(company, title, location, url, score_pct, sal_text, skills_text)))

    if TWILIO_SID and TWILIO_TO:
        results.append(("WhatsApp", _send_whatsapp(plain)))

    sent = any(ok for _, ok in results)
    if sent:
        channels = [name for name, ok in results if ok]
        log.info("🎯 Dream job alert sent via %s: %s @ %s (score=%s)", channels, title, company, score_pct)
    elif results:
        log.warning("Dream job matched but all channels failed: %s @ %s", title, company)
    else:
        log.warning(
            "Dream job matched but no channels configured — "
            "set DISCORD_WEBHOOK_URL or TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID "
            "(free) or SLACK_WEBHOOK_URL / TWILIO_* (paid). Job: %s @ %s",
            title, company,
        )
    return sent


# ── Error rate alert ──────────────────────────────────────────────────────

def alert_high_error_rate(stats: dict):
    """
    Fire Discord alert if >10% of scraped companies errored.
    stats dict must contain 'companies' (int) and 'errors' (int).
    """
    companies = stats.get("companies", 0)
    errors = stats.get("errors", 0)
    if companies == 0 or errors / companies <= 0.10:
        return

    error_pct = round(errors / companies * 100)
    msg = (
        f"**JobScout scrape error rate: {error_pct}%**\n"
        f"Companies attempted: {companies} | Errors: {errors}\n"
        f"Cycle: {stats.get('cycle', '?')} | New jobs found: {stats.get('new', 0)}"
    )
    _send_discord_message(msg)


def _send_discord_message(message: str):
    """Send a plain text message to the Discord webhook."""
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10)
    except Exception as e:
        log.warning("Discord alert failed: %s", e)


# ── Free: Discord ──────────────────────────────────────────────────────────

def _send_discord(company, title, location, url, score_pct, sal_text, skills_text, tex_b64=None) -> bool:
    """
    Discord webhook — completely free, no rate limits for personal use.
    Rich embed with color-coded score bar.

    Setup:
      1. In your Discord server: Settings → Integrations → Webhooks → New Webhook
      2. Name it "JobScout", choose a channel, click "Copy Webhook URL"
      3. Set env var: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
    """
    try:
        # Color: green for high score, yellow for medium
        score_num = int(score_pct.replace("%", ""))
        color = 0x2D5A4A if score_num >= 80 else 0xC4A77D if score_num >= 65 else 0x7A7A7A

        fields = [
            {"name": "🏢 Company",  "value": company,                    "inline": True},
            {"name": "📍 Location", "value": location or "Not specified", "inline": True},
            {"name": "⭐ Match",    "value": score_pct,                   "inline": True},
        ]
        if sal_text:
            fields.append({"name": "💰 Salary", "value": sal_text, "inline": True})
        if skills_text and skills_text != "—":
            fields.append({"name": "🛠 Matched Skills", "value": skills_text, "inline": False})
        if tex_b64:
            fields.append({
                "name": "📄 Tailored Resume",
                "value": "Tailored .tex generated — download from job dashboard",
                "inline": False,
            })

        payload = {
            "content": f"🎯 **Dream job alert!** {title} at **{company}**",
            "embeds": [{
                "title":       title,
                "url":         url,
                "color":       color,
                "fields":      fields,
                "footer":      {"text": "JobScout • Apply now →"},
                "timestamp":   None,
            }],
        }
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=8)
        if resp.status_code not in (200, 204):
            log.warning("Discord webhook returned %d: %s", resp.status_code, resp.text[:200])
        return resp.status_code in (200, 204)
    except Exception as e:
        log.error("Discord notification failed: %s", e)
        return False


# ── Free: Telegram ─────────────────────────────────────────────────────────

def _send_telegram(message: str) -> bool:
    """
    Telegram Bot API — completely free, instant push to phone/desktop.

    Setup:
      1. Open Telegram → search @BotFather → /newbot → follow prompts
      2. Copy the bot token (looks like: 123456789:ABCdef...)
      3. Start a chat with your new bot (send any message)
      4. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
         Find your chat_id in the response (under message.chat.id)
      5. Set env vars:
           TELEGRAM_BOT_TOKEN=123456789:ABCdef...
           TELEGRAM_CHAT_ID=123456789
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "Markdown",
        }
        resp = requests.post(url, json=payload, timeout=8)
        if not resp.ok:
            log.warning("Telegram returned %d: %s", resp.status_code, resp.text[:200])
        return resp.ok
    except Exception as e:
        log.error("Telegram notification failed: %s", e)
        return False


# ── Paid/Trial: Slack ──────────────────────────────────────────────────────

def _send_slack(company, title, location, url, score_pct, sal_text, skills_text) -> bool:
    """
    Slack incoming webhook — rich block message.
    NOTE: Slack's free plan has a 90-day message history limit.
          Workspace creation gives 30 days free of some paid features.

    Setup:
      1. api.slack.com/apps → Create New App → From scratch
      2. Incoming Webhooks → Activate → Add to Workspace → pick channel
      3. Copy webhook URL → set SLACK_WEBHOOK_URL env var
    """
    try:
        fields = [
            {"type": "mrkdwn", "text": f"*Role:*\n{title}"},
            {"type": "mrkdwn", "text": f"*Company:*\n{company}"},
            {"type": "mrkdwn", "text": f"*Location:*\n{location or 'Not specified'}"},
            {"type": "mrkdwn", "text": f"*Match Score:*\n{score_pct}"},
        ]
        if sal_text:
            fields.append({"type": "mrkdwn", "text": f"*Salary:*\n{sal_text}"})
        if skills_text and skills_text != "—":
            fields.append({"type": "mrkdwn", "text": f"*Skills:*\n{skills_text}"})

        payload = {
            "text": f"🎯 Dream job: *{title}* at *{company}*",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🎯 Dream Job Alert!", "emoji": True}},
                {"type": "section", "fields": fields},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Apply Now →"},
                     "url": url, "style": "primary"},
                ]},
            ],
        }
        resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=8)
        if resp.status_code != 200:
            log.warning("Slack webhook returned %d: %s", resp.status_code, resp.text[:200])
        return resp.status_code == 200
    except Exception as e:
        log.error("Slack notification failed: %s", e)
        return False


# ── Paid/Trial: WhatsApp via Twilio ───────────────────────────────────────

def _send_whatsapp(message: str) -> bool:
    """
    Twilio WhatsApp — requires $15 free credit (then pay-as-you-go).
    ~$0.005/message after trial.

    Setup:
      1. twilio.com → sign up → get Account SID + Auth Token from dashboard
      2. Messaging → Try it out → Send a WhatsApp message
      3. Send the join code from your phone to the Twilio sandbox number
      4. Set env vars:
           TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
           TWILIO_AUTH_TOKEN=your_token
           TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
           TWILIO_WHATSAPP_TO=whatsapp:+1XXXXXXXXXX
    """
    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
            data={"From": TWILIO_FROM, "To": TWILIO_TO, "Body": message},
            auth=(TWILIO_SID, TWILIO_TOKEN),
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            log.warning("Twilio returned %d: %s", resp.status_code, resp.text[:200])
        return resp.status_code in (200, 201)
    except Exception as e:
        log.error("WhatsApp/Twilio notification failed: %s", e)
        return False
