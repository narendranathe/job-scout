import json
import os
import urllib.error
import urllib.request

import flask

from middleware.supabase_auth import require_auth

company_request_bp = flask.Blueprint("company_request", __name__)


@company_request_bp.route("/api/companies/request", methods=["POST"])
@require_auth
def request_company():
    data = flask.request.get_json(silent=True) or {}
    name = (data.get("company_name") or "").strip()
    if not name:
        return flask.jsonify({"error": "company_name required"}), 400

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return flask.jsonify({"error": "GitHub integration not configured"}), 503

    body = json.dumps({
        "title": f"[Company Request] {name}",
        "body": (
            f"**Requested by:** {flask.g.email}\n\n"
            f"Add scraping support for **{name}**.\n\n"
            "_Auto-filed by job-scout._"
        ),
        "labels": ["company-request"],
    }).encode()

    req = urllib.request.Request(
        "https://api.github.com/repos/narendranathe/job-scout/issues",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        issue_url = result.get("html_url", "")
        if not issue_url:
            return flask.jsonify({"error": "GitHub response missing issue URL"}), 502
        return flask.jsonify({"issue_url": issue_url}), 201
    except urllib.error.HTTPError as e:
        return flask.jsonify({"error": f"GitHub API error: {e.code}"}), 502
    except (urllib.error.URLError, OSError):
        return flask.jsonify({"error": "GitHub unreachable"}), 502
