"""
Supabase Storage via REST API — no supabase-py dependency.

Uses only `requests` (already in requirements.txt) to call the
Supabase Storage HTTP endpoints directly. Falls back gracefully when
SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY are not set.
"""
import logging
import os

import requests

log = logging.getLogger(__name__)

BUCKET = "resumes"
_TIMEOUT = 30


def _creds():
    """Return (base_url, headers) or (None, None) if env vars not set."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None, None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    return f"{url}/storage/v1", headers


def available() -> bool:
    base, _ = _creds()
    return base is not None


def upload(path: str, data: bytes) -> bool:
    """Upload bytes to BUCKET/path. Overwrites if already present (upsert)."""
    base, headers = _creds()
    if not base:
        return False
    try:
        resp = requests.post(
            f"{base}/object/{BUCKET}/{path}",
            data=data,
            headers={
                **headers,
                "Content-Type": "application/pdf",
                "x-upsert": "true",
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code not in (200, 201):
            log.error("Supabase upload failed %s: %s %s", path, resp.status_code, resp.text[:200])
            return False
        log.info("Supabase upload OK: %s (%d bytes)", path, len(data))
        return True
    except Exception as exc:
        log.error("Supabase upload error %s: %s", path, exc)
        return False


def signed_url(path: str, expires_in: int = 3600) -> str | None:
    """Return a signed download URL valid for expires_in seconds, or None."""
    base, headers = _creds()
    if not base:
        return None
    try:
        resp = requests.post(
            f"{base}/object/sign/{BUCKET}/{path}",
            json={"expiresIn": expires_in},
            headers={**headers, "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning("Supabase sign failed %s: %s %s", path, resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        raw = data.get("signedURL") or data.get("signedUrl") or ""
        if not raw:
            return None
        # Supabase sometimes returns a relative path — make it absolute.
        if raw.startswith("/"):
            supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
            return f"{supabase_url}{raw}"
        return raw
    except Exception as exc:
        log.warning("Supabase sign error %s: %s", path, exc)
        return None


def remove(path: str) -> bool:
    """Delete a single file from the bucket. Non-fatal if missing."""
    base, headers = _creds()
    if not base:
        return False
    try:
        resp = requests.delete(
            f"{base}/object/{BUCKET}",
            json={"prefixes": [path]},
            headers={**headers, "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code not in (200, 204):
            log.warning("Supabase delete failed %s: %s %s", path, resp.status_code, resp.text[:200])
            return False
        log.info("Supabase delete OK: %s", path)
        return True
    except Exception as exc:
        log.warning("Supabase delete error %s: %s", path, exc)
        return False


def list_folder(folder: str) -> list:
    """List objects under folder/. Returns [] on error or unavailability."""
    base, headers = _creds()
    if not base:
        return []
    try:
        resp = requests.post(
            f"{base}/object/list/{BUCKET}",
            json={"prefix": folder, "limit": 1000, "offset": 0},
            headers={**headers, "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        return resp.json() or []
    except Exception as exc:
        log.warning("Supabase list error %s: %s", folder, exc)
        return []
