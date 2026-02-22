"""
Alert notifier — sends Slack and/or WhatsApp notifications when dream roles appear.

Environment variables to set in Render (or .env for local):
  SLACK_WEBHOOK_URL      — Slack incoming webhook URL
  TWILIO_ACCOUNT_SID     — Twilio account SID (for WhatsApp)
  TWILIO_AUTH_TOKEN      — Twilio auth token
  TWILIO_WHATSAPP_FROM   — Twilio WhatsApp sender (e.g. whatsapp:+14155238886)
  TWILIO_WHATSAPP_TO     — Your WhatsApp number (e.g. whatsapp:+12145559876)
  DREAM_COMPANIES        — Comma-separated company names (e.g. "Anthropic,OpenAI,Stripe")
  DREAM_ROLE_KEYWORDS    — Comma-separated role keywords (e.g. "data engineer,ml engineer")

Setup guides:
  Slack:     https://api.slack.com/messaging/webhooks
  WhatsApp:  https://www.twilio.com/whatsapp (Twilio Sandbox)
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_TO = os.environ.get("TWILIO_WHATSAPP_TO", "")

# Parse dream criteria from environment variables
DREAM_COMPANIES = {
    s.strip().lower()
    for s in os.environ.get("DREAM_COMPANIES", "").split(",")
    if s.strip()
}
DREAM_ROLE_KEYWORDS = [
    s.strip().lower()
    for s in os.environ.get("DREAM_ROLE_KEYWORDS", "data engineer,ml engineer,data scientist").split(",")
    if s.strip()
]


def is_dream_job(job: dict) -> bool:
    """Check if a job matches dream criteria: dream company AND dream role keyword."""
    if not DREAM_COMPANIES or not DREAM_ROLE_KEYWORDS:
        return False
    company_match = job.get("company", "").lower() in DREAM_COMPANIES
    if not company_match:
        return False
    title = job.get("title", "").lower()
    return any(kw in title for kw in DREAM_ROLE_KEYWORDS)


def notify_dream_job(job: dict) -> bool:
    """Send alert if this is a dream job. Returns True if alert was sent."""
    if not is_dream_job(job):
        return False

    company = job.get("company", "Unknown")
    title = job.get("title", "Unknown")
    location = job.get("location", "")
    url = job.get("url", "")
    score = job.get("relevance_score", 0)
    salary_min = job.get("salary_min", 0)
    salary_max = job.get("salary_max", 0)

    sal_text = f"${salary_min // 1000}K–${salary_max // 1000}K" if salary_max else ""

    plain_msg = (
        f"🎯 DREAM JOB ALERT!\n"
        f"Role: {title}\n"
        f"Company: {company}\n"
        f"Location: {location}\n"
        f"Match: {int(score * 100)}%\n"
        + (f"Salary: {sal_text}\n" if sal_text else "")
        + f"Apply: {url}"
    )

    sent = False
    if SLACK_WEBHOOK:
        sent |= _send_slack(company, title, location, url, score, sal_text)
    if TWILIO_SID and TWILIO_TO:
        sent |= _send_whatsapp(plain_msg)

    if sent:
        log.info("🎯 Dream job alert sent: %s @ %s", title, company)
    else:
        log.warning(
            "Dream job matched but no channels configured — set SLACK_WEBHOOK_URL or Twilio env vars. Job: %s @ %s",
            title, company,
        )
    return sent


def _send_slack(company, title, location, url, score, sal_text) -> bool:
    """Send rich Slack block notification."""
    try:
        fields = [
            {"type": "mrkdwn", "text": f"*Role:*\n{title}"},
            {"type": "mrkdwn", "text": f"*Company:*\n{company}"},
            {"type": "mrkdwn", "text": f"*Location:*\n{location or 'Not specified'}"},
            {"type": "mrkdwn", "text": f"*Match Score:*\n{int(score * 100)}%"},
        ]
        if sal_text:
            fields.append({"type": "mrkdwn", "text": f"*Salary:*\n{sal_text}"})

        payload = {
            "text": f"🎯 Dream job alert: *{title}* at *{company}*",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🎯 Dream Job Alert!", "emoji": True},
                },
                {"type": "section", "fields": fields},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Apply Now →"},
                            "url": url,
                            "style": "primary",
                        }
                    ],
                },
            ],
        }
        resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=8)
        if resp.status_code != 200:
            log.warning("Slack webhook returned %d: %s", resp.status_code, resp.text[:200])
        return resp.status_code == 200
    except Exception as e:
        log.error("Slack notification failed: %s", e)
        return False


def _send_whatsapp(message: str) -> bool:
    """Send WhatsApp message via Twilio API."""
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
        log.error("WhatsApp notification failed: %s", e)
        return False
