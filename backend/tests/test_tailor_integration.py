"""
Tests for the tailor-resume integration in alerts/notifier.py (Issue #38).

Verifies:
  - Tailoring is skipped (no API call) when TAILOR_RESUME_API_URL is not set
  - A Timeout exception from requests.post is caught gracefully (returns None)
  - requests.post is called with the correct jd_text when TAILOR_RESUME_API_URL is set

All tests patch env vars and requests so no real network calls are made.
"""

import importlib
import sys
import os
import types
import unittest
from unittest.mock import patch, MagicMock

import requests as _requests


# ── Helpers ────────────────────────────────────────────────────────────────

DREAM_JOB = {
    "title": "Senior Data Engineer",
    "company": "anthropic",
    "location": "remote",
    "url": "https://example.com/job/1",
    "description": "Build data pipelines with Python, Spark, and Kafka.",
    "relevance_score": 0.85,
    "matched_skills": ["python", "spark", "kafka"],
}

BASE_ENV = {
    "DREAM_COMPANIES": "anthropic",
    "DREAM_ROLE_KEYWORDS": "senior data engineer",
    "DREAM_ALERT_SCORE": "0.70",
}


def _fresh_notifier(extra_env: dict | None = None):
    """Import a fresh copy of alerts.notifier with the given env vars set."""
    env = {**BASE_ENV, **(extra_env or {})}
    # Remove the cached module so module-level os.environ.get() calls re-run
    for key in list(sys.modules.keys()):
        if "notifier" in key:
            del sys.modules[key]
    with patch.dict(os.environ, env, clear=False):
        import alerts.notifier as notifier
        return notifier


# ── Tests ──────────────────────────────────────────────────────────────────

class TestTailorResumeIntegration(unittest.TestCase):

    def test_tailor_skipped_when_no_url(self):
        """
        When TAILOR_RESUME_API_URL is not set, _tailor_resume_for_job must
        return None immediately without making any HTTP call.
        """
        # Ensure the env var is absent
        env = {k: v for k, v in BASE_ENV.items()}
        env.pop("TAILOR_RESUME_API_URL", None)

        with patch.dict(os.environ, env, clear=False):
            # Remove cached module
            for key in list(sys.modules.keys()):
                if "notifier" in key:
                    del sys.modules[key]
            os.environ.pop("TAILOR_RESUME_API_URL", None)

            import alerts.notifier as notifier

            with patch("alerts.notifier.requests") as mock_requests:
                result = notifier._tailor_resume_for_job(DREAM_JOB)

            self.assertIsNone(result)
            mock_requests.post.assert_not_called()

    def test_tailor_graceful_on_timeout(self):
        """
        When requests.post raises requests.exceptions.Timeout, _tailor_resume_for_job
        must catch it, log a warning, and return None — no exception should propagate.
        """
        for key in list(sys.modules.keys()):
            if "notifier" in key:
                del sys.modules[key]

        with patch.dict(os.environ, {**BASE_ENV, "TAILOR_RESUME_API_URL": "https://tailor-resume-api.fly.dev"}, clear=False):
            import alerts.notifier as notifier

            with patch("alerts.notifier.requests") as mock_requests:
                mock_requests.post.side_effect = _requests.exceptions.Timeout("timed out")
                mock_requests.exceptions = _requests.exceptions

                result = notifier._tailor_resume_for_job(DREAM_JOB)

        self.assertIsNone(result)

    def test_tailor_called_on_dream_job(self):
        """
        When TAILOR_RESUME_API_URL is set and the API returns a tex_b64 value,
        _tailor_resume_for_job must POST to the correct endpoint with the job's
        description in jd_text and return the tex_b64 string.
        """
        api_url = "https://tailor-resume-api.fly.dev"

        for key in list(sys.modules.keys()):
            if "notifier" in key:
                del sys.modules[key]

        with patch.dict(os.environ, {**BASE_ENV, "TAILOR_RESUME_API_URL": api_url}, clear=False):
            import alerts.notifier as notifier

            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.return_value = {"tex_b64": "dGVzdA=="}  # base64("test")

            with patch("alerts.notifier.requests") as mock_requests:
                mock_requests.post.return_value = mock_response
                mock_requests.exceptions = _requests.exceptions

                result = notifier._tailor_resume_for_job(DREAM_JOB)

        # Verify return value
        self.assertEqual(result, "dGVzdA==")

        # Verify the call was made to the right endpoint with jd_text
        mock_requests.post.assert_called_once()
        call_kwargs = mock_requests.post.call_args

        called_url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("url", "")
        self.assertIn("/api/v1/resume/tailor", called_url)

        payload = call_kwargs[1].get("json") or (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
        self.assertEqual(payload.get("jd_text"), DREAM_JOB["description"])

    def test_tailor_returns_none_on_api_error(self):
        """
        When the API returns a non-OK status, _tailor_resume_for_job must
        return None without raising.
        """
        api_url = "https://tailor-resume-api.fly.dev"

        for key in list(sys.modules.keys()):
            if "notifier" in key:
                del sys.modules[key]

        with patch.dict(os.environ, {**BASE_ENV, "TAILOR_RESUME_API_URL": api_url}, clear=False):
            import alerts.notifier as notifier

            mock_response = MagicMock()
            mock_response.ok = False
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"

            with patch("alerts.notifier.requests") as mock_requests:
                mock_requests.post.return_value = mock_response
                mock_requests.exceptions = _requests.exceptions

                result = notifier._tailor_resume_for_job(DREAM_JOB)

        self.assertIsNone(result)

    def test_notify_dream_job_fires_despite_tailor_failure(self):
        """
        Even when _tailor_resume_for_job returns None (API down), notify_dream_job
        must still attempt to fire alerts on configured channels.
        """
        api_url = "https://tailor-resume-api.fly.dev"

        for key in list(sys.modules.keys()):
            if "notifier" in key:
                del sys.modules[key]

        with patch.dict(
            os.environ,
            {
                **BASE_ENV,
                "TAILOR_RESUME_API_URL": api_url,
                "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test",
            },
            clear=False,
        ):
            import alerts.notifier as notifier

            # Tailor call times out
            def _tailor_raises(*args, **kwargs):
                raise _requests.exceptions.Timeout("timed out")

            # Discord succeeds
            discord_resp = MagicMock()
            discord_resp.status_code = 204

            with patch("alerts.notifier._tailor_resume_for_job", return_value=None) as mock_tailor, \
                 patch("alerts.notifier.requests") as mock_requests:
                mock_requests.post.return_value = discord_resp
                mock_requests.exceptions = _requests.exceptions

                sent = notifier.notify_dream_job(DREAM_JOB)

        # Alert must have been attempted regardless of tailor result
        mock_tailor.assert_called_once_with(DREAM_JOB)
        mock_requests.post.assert_called()  # Discord was called


if __name__ == "__main__":
    unittest.main()
