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

# Paid / trial channels (kept for forkers)
SLACK_WEBHOOK  = os.environ.get("SLACK_WEBHOOK_URL", "")
TWILIO_SID     = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM    = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_TO      = os.environ.get("TWILIO_WHATSAPP_TO", "")

# ── Alert criteria ─────────────────────────────────────────────────────────
# Only alert when relevance score is high enough — avoids noise
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
        "data engineer,senior data engineer,ml engineer,ai engineer,analytics engineer"
    ).split(",")
    if s.strip()
]


# ── Public API ─────────────────────────────────────────────────────────────

def is_dream_job(job: dict) -> bool:
    """
    Returns True when ALL three conditions are met:
      1. Relevance score >= ALERT_MIN_SCORE (job actually fits your profile)
      2. Company is in your DREAM_COMPANIES list
      3. Job title contains one of your DREAM_ROLE_KEYWORDS
    """
    if not DREAM_COMPANIES or not DREAM_ROLE_KEYWORDS:
        return False

    score = job.get("relevance_score", 0.0)
    if score < ALERT_MIN_SCORE:
        return False  # Not relevant enough — skip

    company_match = job.get("company", "").lower() in DREAM_COMPANIES
    if not company_match:
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
    )

    results = []

    # ── Free channels ──────────────────────────────────────────
    if DISCORD_WEBHOOK:
        results.append(("Discord", _send_discord(company, title, location, url, score_pct, sal_text, skills_text)))

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


# ── Free: Discord ──────────────────────────────────────────────────────────

def _send_discord(company, title, location, url, score_pct, sal_text, skills_text) -> bool:
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
