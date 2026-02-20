"""
Email notification system — sends formatted HTML digest emails.
"""

import asyncio
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

from config.settings import NotificationConfig

logger = logging.getLogger(__name__)


class EmailNotifier:

    def __init__(self, config: NotificationConfig):
        self.config = config
        self._enabled = bool(config.smtp_user and config.recipient_email)

    async def send_job_digest(self, jobs: list[dict]) -> bool:
        if not self._enabled or not jobs:
            return False
        subject = f"🎯 {len(jobs)} New Match{'es' if len(jobs) != 1 else ''} — JobScout"
        html = self._build_html(jobs)
        return await asyncio.to_thread(self._send_smtp, subject, html)

    def _send_smtp(self, subject: str, html: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.smtp_user
            msg["To"] = self.config.recipient_email
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as s:
                s.ehlo(); s.starttls(); s.login(self.config.smtp_user, self.config.smtp_password)
                s.send_message(msg)
            return True
        except Exception as exc:
            logger.error("SMTP error: %s", exc)
            return False

    def _build_html(self, jobs: list[dict]) -> str:
        now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
        cards = "\n".join(self._card(j) for j in jobs[:25])
        return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#0f172a;font-family:system-ui,sans-serif;">
        <div style="max-width:640px;margin:0 auto;padding:24px;">
        <div style="background:linear-gradient(135deg,#1e293b,#334155);border-radius:16px;padding:32px;margin-bottom:24px;border:1px solid #475569;">
            <h1 style="color:#f1f5f9;margin:0 0 8px;font-size:24px;">🎯 JobScout Alert</h1>
            <p style="color:#94a3b8;margin:0;font-size:14px;">{now}</p>
            <p style="color:#38bdf8;margin:8px 0 0;font-size:16px;font-weight:600;">{len(jobs)} new high-relevance matches</p>
        </div>{cards}
        <div style="text-align:center;padding:24px 0;color:#64748b;font-size:12px;">
            <p>JobScout — Direct ATS pipeline · No third-party APIs</p>
        </div></div></body></html>"""

    def _card(self, j: dict) -> str:
        score = j.get("relevance_score", 0)
        sc = "#22c55e" if score >= 0.85 else "#38bdf8" if score >= 0.7 else "#fbbf24"
        bg = "#14532d" if score >= 0.85 else "#0c4a6e" if score >= 0.7 else "#713f12"
        skills = j.get("matched_skills")
        if isinstance(skills, str):
            try: skills = json.loads(skills)
            except: skills = []
        skill_html = " ".join(f'<span style="background:#1e293b;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:11px;">{s}</span>' for s in (skills or [])[:6])
        remote = '<span style="background:#14532d;color:#4ade80;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:8px;">Remote</span>' if j.get("is_remote") else ""
        return f"""<div style="background:#1e293b;border-radius:12px;padding:20px;margin-bottom:12px;border:1px solid #334155;">
        <div style="display:flex;justify-content:space-between;align-items:start;">
        <div style="flex:1;"><a href="{j.get('url','#')}" style="color:#f1f5f9;font-size:16px;font-weight:600;text-decoration:none;">{j.get('title','')}</a>{remote}
        <p style="color:#94a3b8;margin:4px 0 0;font-size:14px;">{j.get('company','')} · {j.get('location','')} · {j.get('ats','')}</p></div>
        <span style="background:{bg};color:{sc};padding:4px 12px;border-radius:8px;font-weight:700;font-size:14px;">{score:.0%}</span></div>
        <div style="margin-top:10px;">{skill_html}</div></div>"""
