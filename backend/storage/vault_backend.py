"""Storage backends for the resume vault.

Defines a thin abstraction over PDF + extracted-text storage so the same
``resume_vault`` logic works against the local filesystem (dev,
single-host) or Cloudflare R2 (production on ephemeral hosts like
Render free tier, where the local filesystem is wiped on every restart).

Two backends ship:

* ``LocalVaultBackend(vault_dir)`` — writes to ``{vault_dir}/pdf/`` and
  ``{vault_dir}/text/``. Matches the historical on-disk layout exactly,
  so anything that worked with the pre-R2 code still works after this
  refactor.

* ``R2VaultBackend(...)`` — uses ``boto3`` against Cloudflare R2's
  S3-compatible API. Keys mirror the local layout: ``pdf/<filename>``
  and ``text/<version_key>.txt``. ``boto3`` is imported lazily so the
  package stays optional — only required when ``VAULT_BACKEND=r2``.

Configuration via environment:

    VAULT_BACKEND=local                          # default
    VAULT_BACKEND=r2
        R2_ACCOUNT_ID=<your account>
        R2_BUCKET=<bucket name>
        R2_ACCESS_KEY_ID=<key id>
        R2_SECRET_ACCESS_KEY=<secret>
        R2_REGION=auto                           # optional, defaults to "auto"

Backends expose a uniform shape. ``write_pdf`` / ``read_pdf`` /
``list_pdfs`` / ``delete_pdf`` for the binaries; symmetric ``*_text``
methods for extracted text. Each list entry is a ``FileInfo`` dict
with ``key``, ``size``, ``mtime`` (UTC ISO 8601).
"""

from __future__ import annotations

import io
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TypedDict

log = logging.getLogger(__name__)


class FileInfo(TypedDict):
    key: str        # e.g. "Narendranath_GS_DE.pdf"
    size: int       # bytes
    mtime: str      # ISO 8601 UTC


class VaultBackend(ABC):
    """Abstract storage backend for PDFs + extracted text."""

    # ── PDF binary store ────────────────────────────────────────────
    @abstractmethod
    def write_pdf(self, filename: str, data: bytes, mtime: float | None = None) -> None: ...

    @abstractmethod
    def read_pdf(self, filename: str) -> bytes: ...

    @abstractmethod
    def delete_pdf(self, filename: str) -> bool:
        """Return True if a file existed and was deleted."""

    @abstractmethod
    def exists_pdf(self, filename: str) -> bool: ...

    @abstractmethod
    def list_pdfs(self) -> list[FileInfo]: ...

    # ── Extracted-text store ────────────────────────────────────────
    @abstractmethod
    def write_text(self, version_key: str, text: str, mtime: float | None = None) -> None: ...

    @abstractmethod
    def read_text(self, version_key: str) -> str | None:
        """Return the cached extracted text, or None if missing."""

    @abstractmethod
    def delete_text(self, version_key: str) -> bool: ...

    @abstractmethod
    def list_texts(self) -> list[FileInfo]: ...

    # ── Diagnostic ──────────────────────────────────────────────────
    @abstractmethod
    def describe(self) -> dict:
        """Short config snapshot — used by /api/vault/stats."""

    # ── Convenience ─────────────────────────────────────────────────
    def pdf_local_path(self, filename: str) -> str | None:
        """Return the local filesystem path for a PDF, or None.

        ``LocalVaultBackend`` returns the absolute on-disk path so
        callers (and historical tests) can ``os.path.exists`` it.
        ``R2VaultBackend`` returns None — the PDF lives in object
        storage, not on the local fs.

        Default implementation returns None; LocalVaultBackend overrides.
        """
        return None

    def text_local_path(self, version_key: str) -> str | None:
        """Symmetric with ``pdf_local_path`` for extracted text files."""
        return None


# ═════════════════════════════════════════════════════════════════════
#   LOCAL FILESYSTEM BACKEND
# ═════════════════════════════════════════════════════════════════════

def _validate_key(filename: str) -> None:
    """Reject keys that obviously aren't valid vault filenames.

    Catches null bytes, explicit slashes, and ``..`` traversal sequences
    — none of those can legitimately appear in a vault filename. When
    the offending key looks like a path-traversal payload (contains
    ``..`` or slashes), the error message uses the ``refusing to write
    outside vault`` phrasing so callers + tests grepping for it see a
    consistent message across the key-validation and realpath layers.
    """
    if not filename or "\x00" in filename:
        raise ValueError(f"Invalid vault key: {filename!r}")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(
            f"refusing to write outside vault: invalid key {filename!r}"
        )


class LocalVaultBackend(VaultBackend):
    """Filesystem-backed vault under ``{vault_dir}/pdf`` + ``{vault_dir}/text``."""

    def __init__(self, vault_dir: str):
        self.vault_dir = vault_dir
        self.pdf_dir = os.path.join(vault_dir, "pdf")
        self.text_dir = os.path.join(vault_dir, "text")
        os.makedirs(self.pdf_dir, exist_ok=True)
        os.makedirs(self.text_dir, exist_ok=True)

    def _pdf_path(self, filename: str) -> str:
        _validate_key(filename)
        target = os.path.realpath(os.path.join(self.pdf_dir, filename))
        root = os.path.realpath(self.pdf_dir)
        if not (target == root or target.startswith(root + os.sep)):
            # Message kept verbatim from the pre-backend code path —
            # downstream tests grep for "refusing to write outside vault".
            raise ValueError(
                f"refusing to write outside vault: {target!r} not under {root!r}"
            )
        return target

    def _text_path(self, version_key: str) -> str:
        _validate_key(version_key + ".txt")
        return os.path.join(self.text_dir, f"{version_key}.txt")

    def write_pdf(self, filename: str, data: bytes, mtime: float | None = None) -> None:
        path = self._pdf_path(filename)
        with open(path, "wb") as f:
            f.write(data)
        if mtime is not None:
            os.utime(path, (mtime, mtime))

    def read_pdf(self, filename: str) -> bytes:
        with open(self._pdf_path(filename), "rb") as f:
            return f.read()

    def delete_pdf(self, filename: str) -> bool:
        path = self._pdf_path(filename)
        if not os.path.exists(path):
            return False
        os.unlink(path)
        return True

    def exists_pdf(self, filename: str) -> bool:
        try:
            return os.path.exists(self._pdf_path(filename))
        except ValueError:
            return False

    def list_pdfs(self) -> list[FileInfo]:
        results: list[FileInfo] = []
        for fname in sorted(os.listdir(self.pdf_dir)):
            if not fname.lower().endswith(".pdf"):
                continue
            full = os.path.join(self.pdf_dir, fname)
            st = os.stat(full)
            results.append({
                "key": fname,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        return results

    def write_text(self, version_key: str, text: str, mtime: float | None = None) -> None:
        path = self._text_path(version_key)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if mtime is not None:
            os.utime(path, (mtime, mtime))

    def read_text(self, version_key: str) -> str | None:
        path = self._text_path(version_key)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def delete_text(self, version_key: str) -> bool:
        path = self._text_path(version_key)
        if not os.path.exists(path):
            return False
        os.unlink(path)
        return True

    def list_texts(self) -> list[FileInfo]:
        results: list[FileInfo] = []
        for fname in sorted(os.listdir(self.text_dir)):
            if not fname.lower().endswith(".txt"):
                continue
            full = os.path.join(self.text_dir, fname)
            st = os.stat(full)
            results.append({
                "key": fname,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        return results

    def describe(self) -> dict:
        return {"backend": "local", "vault_dir": self.vault_dir}

    def pdf_local_path(self, filename: str) -> str | None:
        try:
            return self._pdf_path(filename)
        except ValueError:
            return None

    def text_local_path(self, version_key: str) -> str | None:
        try:
            return self._text_path(version_key)
        except ValueError:
            return None


# ═════════════════════════════════════════════════════════════════════
#   CLOUDFLARE R2 BACKEND
# ═════════════════════════════════════════════════════════════════════

class R2VaultBackend(VaultBackend):
    """Cloudflare R2-backed vault. PDFs at ``pdf/<filename>``, text at
    ``text/<version_key>.txt``.

    ``boto3`` is imported lazily on first use so the dependency stays
    optional for local-only setups.
    """

    PDF_PREFIX = "pdf/"
    TEXT_PREFIX = "text/"

    def __init__(
        self,
        account_id: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "auto",
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise RuntimeError(
                "VAULT_BACKEND=r2 requires boto3. Install with: pip install boto3"
            ) from e

        if not all([account_id, bucket, access_key_id, secret_access_key]):
            raise ValueError(
                "R2VaultBackend requires R2_ACCOUNT_ID, R2_BUCKET, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
            )

        self.bucket = bucket
        self.account_id = account_id
        # R2's S3-compatible endpoint. The "auto" region is Cloudflare's
        # default; boto3 only uses it for the SigV4 signature, not for
        # routing (R2 is single-region under the hood).
        self.endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            # path-style addressing matches R2's URL scheme; the default
            # virtual-host style ``{bucket}.{endpoint}`` doesn't resolve.
            config=Config(s3={"addressing_style": "path"}),
        )

    def _put(self, key: str, body: bytes, mtime: float | None, content_type: str) -> None:
        metadata = {}
        if mtime is not None:
            # Custom metadata survives across PUTs and is returned in
            # the HeadObject response. We store the submission date here
            # rather than relying on R2's LastModified, which always
            # reflects the upload time, not the original file mtime.
            metadata["submitted-at"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        kwargs = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": body,
            "ContentType": content_type,
        }
        if metadata:
            kwargs["Metadata"] = metadata
        self.client.put_object(**kwargs)

    def _get(self, key: str) -> bytes | None:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            # boto3 sometimes raises a generic ClientError for 404s
            # depending on bucket config; check the error code.
            if getattr(e, "response", {}).get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return resp["Body"].read()

    def _delete(self, key: str) -> bool:
        # S3's DeleteObject is idempotent — it returns 204 whether the
        # key existed or not. To honor our "True if existed" contract
        # we have to HEAD first.
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                return False
            raise
        self.client.delete_object(Bucket=self.bucket, Key=key)
        return True

    def _list(self, prefix: str, suffix: str) -> list[FileInfo]:
        results: list[FileInfo] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                if not key.lower().endswith(suffix):
                    continue
                # Strip the prefix so the returned key matches the
                # filename callers expect (mirrors LocalVaultBackend).
                fname = key[len(prefix):]
                if not fname:
                    continue
                # Prefer the submitted-at custom metadata over R2's
                # LastModified, so dashboards show the application date
                # rather than the upload date.
                mtime = self._fetch_submitted_at(key) or obj["LastModified"]
                if hasattr(mtime, "isoformat"):
                    mtime = mtime.astimezone(timezone.utc).isoformat()
                results.append({"key": fname, "size": obj["Size"], "mtime": mtime})
        results.sort(key=lambda r: r["key"])
        return results

    def _fetch_submitted_at(self, key: str) -> str | None:
        """Read the ``submitted-at`` custom metadata if present.

        HEAD is roughly free relative to GET, but doing one per list
        entry still inflates list latency. Acceptable for ~250 entries
        on a free tier; revisit if vault grows large.
        """
        try:
            resp = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        return resp.get("Metadata", {}).get("submitted-at")

    # ── PDF ─────────────────────────────────────────────────────────
    def write_pdf(self, filename: str, data: bytes, mtime: float | None = None) -> None:
        _validate_key(filename)
        self._put(self.PDF_PREFIX + filename, data, mtime, "application/pdf")

    def read_pdf(self, filename: str) -> bytes:
        _validate_key(filename)
        data = self._get(self.PDF_PREFIX + filename)
        if data is None:
            raise FileNotFoundError(filename)
        return data

    def delete_pdf(self, filename: str) -> bool:
        _validate_key(filename)
        return self._delete(self.PDF_PREFIX + filename)

    def exists_pdf(self, filename: str) -> bool:
        try:
            _validate_key(filename)
        except ValueError:
            return False
        try:
            self.client.head_object(Bucket=self.bucket, Key=self.PDF_PREFIX + filename)
            return True
        except Exception:
            return False

    def list_pdfs(self) -> list[FileInfo]:
        return self._list(self.PDF_PREFIX, ".pdf")

    # ── Text ────────────────────────────────────────────────────────
    def write_text(self, version_key: str, text: str, mtime: float | None = None) -> None:
        _validate_key(version_key + ".txt")
        self._put(
            self.TEXT_PREFIX + f"{version_key}.txt",
            text.encode("utf-8"),
            mtime,
            "text/plain; charset=utf-8",
        )

    def read_text(self, version_key: str) -> str | None:
        _validate_key(version_key + ".txt")
        data = self._get(self.TEXT_PREFIX + f"{version_key}.txt")
        return data.decode("utf-8") if data is not None else None

    def delete_text(self, version_key: str) -> bool:
        _validate_key(version_key + ".txt")
        return self._delete(self.TEXT_PREFIX + f"{version_key}.txt")

    def list_texts(self) -> list[FileInfo]:
        return self._list(self.TEXT_PREFIX, ".txt")

    def describe(self) -> dict:
        return {
            "backend": "r2",
            "bucket": self.bucket,
            "endpoint": self.endpoint_url,
        }


# ═════════════════════════════════════════════════════════════════════
#   FACTORY
# ═════════════════════════════════════════════════════════════════════

# Only the R2 backend is cached; instantiating it spins up a boto3
# client which is expensive (TLS handshake, signer init). Local backends
# are cheap and re-instantiated on every call so test fixtures that
# monkeypatch ``storage.resume_vault.VAULT_DIR`` keep working without
# needing a cache-bust hook.
_R2_BACKEND: R2VaultBackend | None = None


def get_vault_backend() -> VaultBackend:
    """Return the configured vault backend.

    Reads ``VAULT_BACKEND`` env var (``local`` | ``r2``). Default is
    ``local`` for back-compat with the historical on-disk layout.

    Local backends read ``storage.resume_vault.VAULT_DIR`` at call time
    so monkey-patched test fixtures resolve correctly. R2 backends are
    cached across calls for the process lifetime.
    """
    global _R2_BACKEND

    backend = os.environ.get("VAULT_BACKEND", "local").strip().lower()
    if backend == "r2":
        if _R2_BACKEND is None:
            _R2_BACKEND = R2VaultBackend(
                account_id=os.environ.get("R2_ACCOUNT_ID", "").strip(),
                bucket=os.environ.get("R2_BUCKET", "").strip(),
                access_key_id=os.environ.get("R2_ACCESS_KEY_ID", "").strip(),
                secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", "").strip(),
                region=os.environ.get("R2_REGION", "auto").strip() or "auto",
            )
            log.info("Vault backend: R2 (bucket=%s)", os.environ.get("R2_BUCKET", ""))
        return _R2_BACKEND

    # Local — read VAULT_DIR from the resume_vault module so tests that
    # monkeypatch it see the patched value. Falls back to the env var,
    # then to the default ``backend/resume_vault/`` directory.
    try:
        from storage import resume_vault as rv_mod
        vault_dir = rv_mod.VAULT_DIR
    except (ImportError, AttributeError):
        vault_dir = os.environ.get(
            "RESUME_VAULT_PATH",
            os.path.join(os.path.dirname(__file__), "..", "resume_vault"),
        )
    return LocalVaultBackend(vault_dir)


def reset_vault_backend() -> None:
    """Drop the cached R2 backend. Used by tests that swap R2 env vars."""
    global _R2_BACKEND
    _R2_BACKEND = None
