"""
Thin wrapper around supabase-py's Storage API.

Falls back gracefully when SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY
are not set — all functions return False/None/[] instead of raising.
This keeps the vault working locally and on Render without Supabase
configured.
"""
import logging
import os

log = logging.getLogger(__name__)

BUCKET = "resumes"

_client = None


def _get():
    global _client
    if _client is not None:
        return _client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _client = create_client(url, key)
        log.info("Supabase Storage client ready")
    except Exception as exc:
        log.warning("Supabase client init failed: %s", exc)
    return _client


def available() -> bool:
    return _get() is not None


def upload(path: str, data: bytes) -> bool:
    """Upload bytes to BUCKET/path. Overwrites if already present."""
    client = _get()
    if not client:
        return False
    try:
        client.storage.from_(BUCKET).upload(
            path, data,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        log.info("Supabase upload OK: %s (%d bytes)", path, len(data))
        return True
    except Exception as exc:
        log.error("Supabase upload failed %s: %s", path, exc)
        return False


def signed_url(path: str, expires_in: int = 3600) -> str | None:
    """Return a signed download URL valid for expires_in seconds, or None."""
    client = _get()
    if not client:
        return None
    try:
        result = client.storage.from_(BUCKET).create_signed_url(path, expires_in)
        return result.get("signedURL") or result.get("signed_url")
    except Exception as exc:
        log.warning("Supabase signed URL failed %s: %s", path, exc)
        return None


def remove(path: str) -> bool:
    """Delete a single file from the bucket. Idempotent — missing file = True."""
    client = _get()
    if not client:
        return False
    try:
        client.storage.from_(BUCKET).remove([path])
        log.info("Supabase delete OK: %s", path)
        return True
    except Exception as exc:
        log.warning("Supabase delete failed %s: %s", path, exc)
        return False


def list_folder(folder: str) -> list:
    """List objects under folder/. Returns [] on error or unavailability."""
    client = _get()
    if not client:
        return []
    try:
        return client.storage.from_(BUCKET).list(folder) or []
    except Exception as exc:
        log.warning("Supabase list failed %s: %s", folder, exc)
        return []
