"""Bulk-upload local PDF resumes to the live JobScout vault on Render.

Run this from your laptop (NOT inside the Render container) to walk a local
folder of PDFs and POST each one to ``/api/vault/upload``. Filenames are
parsed with the same ``parse_resume_filename`` logic the server uses, so
``Narendranath_GS_data.pdf`` is registered as ``Goldman Sachs / Data Engineer``.

Usage (PowerShell):

    cd job-scout\\backend
    $env:JOBSCOUT_API_URL = "https://your-app.onrender.com"
    $env:JOBSCOUT_API_SECRET = "your_secret"
    python -m tools.bulk_upload_to_render `
        --source-dir "C:\\Users\\naren\\OneDrive\\Desktop\\Resume Easy"

Flags:
    --dry-run            Parse + plan only, send nothing.
    --no-skip-existing   Upload even if the version_key already exists in
                         the vault (server will overwrite metadata).
    --include-docx       Also try .docx; expect server rejection since
                         /api/vault/upload validates PDF magic bytes.
    --limit N            Stop after N successful uploads (useful for smoke).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Recommended exclude regex for the bulk of "noise" files in
# C:\Users\naren\OneDrive\Desktop\Resume Easy. Surfaced via --help; not
# applied by default so this stays a generic tool.
RECOMMENDED_EXCLUDE = (
    r"(?i)^(?:jayanth|lankipalli|naru_kiran|sai_maruthi|siva\s+chandan)"
)

# Make ``storage.resume_vault`` importable when run as a script.
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from storage.resume_vault import parse_resume_filename  # noqa: E402

MAX_PDF_BYTES = 10_000_000
MAX_FIELD_LEN = 80
RETRY_DELAYS = (2, 4, 8)
DEFAULT_EXTENSIONS = (".pdf",)


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _fetch_existing_keys(api_url: str, secret: str | None, timeout: float) -> set[str]:
    """Return the set of version_keys already in the live vault."""
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    try:
        resp = requests.get(f"{api_url}/api/vault/list", headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! Could not fetch existing vault list ({e}); skip-existing disabled")
        return set()
    payload = resp.json()
    return {f.get("version_key") for f in payload.get("files", []) if f.get("version_key")}


def _upload_one(
    api_url: str,
    secret: str | None,
    pdf_path: Path,
    company: str,
    role: str | None,
    timeout: float,
    submitted_at: str | None = None,
) -> tuple[bool, str]:
    """POST one PDF. Returns (ok, message). Retries on transient errors."""
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    last_err = "unknown"
    for attempt, delay in enumerate((0,) + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            with pdf_path.open("rb") as fh:
                files = {"pdf": (pdf_path.name, fh, "application/pdf")}
                data = {"company": company}
                if role:
                    data["role"] = role
                if submitted_at:
                    data["submitted_at"] = submitted_at
                resp = requests.post(
                    f"{api_url}/api/vault/upload",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=timeout,
                )
        except requests.RequestException as e:
            last_err = f"network: {e}"
            continue
        if resp.status_code == 200:
            return True, "ok"
        # 4xx is permanent (bad PDF, oversize, unauthorized) — don't retry.
        if 400 <= resp.status_code < 500:
            try:
                body = resp.json().get("error", resp.text[:200])
            except ValueError:
                body = resp.text[:200]
            return False, f"HTTP {resp.status_code}: {body}"
        last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
    return False, f"giving up after retries ({last_err})"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bulk-upload PDFs to JobScout vault on Render.")
    p.add_argument(
        "--source-dir",
        required=True,
        help="Local directory to walk (recursively).",
    )
    p.add_argument(
        "--api-url",
        default=os.environ.get("JOBSCOUT_API_URL", ""),
        help="Render base URL, e.g. https://your-app.onrender.com (or set JOBSCOUT_API_URL).",
    )
    p.add_argument(
        "--api-secret",
        default=os.environ.get("JOBSCOUT_API_SECRET", ""),
        help="Bearer token (or set JOBSCOUT_API_SECRET). Omit if API_SECRET is unset on the server.",
    )
    p.add_argument("--dry-run", action="store_true", help="Parse and plan only; send nothing.")
    p.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Upload even if version_key already exists in the vault.",
    )
    p.set_defaults(skip_existing=True)
    p.add_argument(
        "--include-docx",
        action="store_true",
        help="Also include .docx (server will reject; useful for an audit listing).",
    )
    p.add_argument("--limit", type=int, default=0, help="Stop after N successful uploads.")
    p.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout (seconds).")
    p.add_argument(
        "--exclude",
        default="",
        help=(
            "Regex matched (case-insensitive, via .search) against each "
            "filename; matches are skipped. Recommended for the "
            "Resume Easy folder: "
            + RECOMMENDED_EXCLUDE
        ),
    )
    args = p.parse_args(argv)

    if not args.api_url:
        print("ERROR: --api-url is required (or set JOBSCOUT_API_URL).", file=sys.stderr)
        return 2
    api_url = args.api_url.rstrip("/")

    src = Path(args.source_dir).expanduser()
    if not src.is_dir():
        print(f"ERROR: source dir not found: {src}", file=sys.stderr)
        return 2

    exts = list(DEFAULT_EXTENSIONS)
    if args.include_docx:
        exts.append(".docx")

    exclude_re = None
    if args.exclude:
        try:
            exclude_re = re.compile(args.exclude)
        except re.error as e:
            print(f"ERROR: bad --exclude regex: {e}", file=sys.stderr)
            return 2

    candidates = sorted(
        f for f in src.rglob("*")
        if f.is_file() and f.suffix.lower() in exts
    )
    print(f"Found {len(candidates)} candidate file(s) under {src}")
    if not candidates:
        return 0

    existing: set[str] = set()
    if args.skip_existing and not args.dry_run:
        existing = _fetch_existing_keys(api_url, args.api_secret or None, args.timeout)
        print(f"Vault already contains {len(existing)} version_key(s)")

    uploaded = 0
    skipped_existing = 0
    skipped_oversize = 0
    skipped_unparseable = 0
    skipped_excluded = 0
    failed: list[tuple[str, str]] = []

    for pdf_path in candidates:
        if exclude_re and exclude_re.search(pdf_path.name):
            if args.dry_run:
                print(f"  - {pdf_path.name}: skip (--exclude match)")
            skipped_excluded += 1
            continue
        meta = parse_resume_filename(pdf_path.name)
        company = _truncate(meta.get("company"), MAX_FIELD_LEN)
        role = _truncate(meta.get("role"), MAX_FIELD_LEN)
        vk = meta.get("version_key") or ""

        if not company:
            print(f"  - {pdf_path.name}: skip (unparseable company)")
            skipped_unparseable += 1
            continue

        try:
            st = pdf_path.stat()
            size = st.st_size
            submitted_at = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()
        except OSError as e:
            print(f"  - {pdf_path.name}: stat failed ({e})")
            failed.append((pdf_path.name, f"stat: {e}"))
            continue
        if size > MAX_PDF_BYTES:
            print(f"  - {pdf_path.name}: skip ({size:,} bytes > {MAX_PDF_BYTES:,})")
            skipped_oversize += 1
            continue

        if args.skip_existing and vk in existing:
            skipped_existing += 1
            continue

        date_str = submitted_at[:10]
        plan = f"{company}" + (f" / {role}" if role else "") + f"  [{vk}]  ({date_str})"
        if args.dry_run:
            print(f"  · {pdf_path.name} -> {plan}  (dry-run)")
            uploaded += 1
            if args.limit and uploaded >= args.limit:
                break
            continue

        ok, msg = _upload_one(
            api_url, args.api_secret or None, pdf_path, company, role, args.timeout,
            submitted_at=submitted_at,
        )
        marker = "+" if ok else "x"
        print(f"  {marker} {pdf_path.name} -> {plan}  {msg}")
        if ok:
            uploaded += 1
            existing.add(vk)
            if args.limit and uploaded >= args.limit:
                print(f"Reached --limit {args.limit}; stopping.")
                break
        else:
            failed.append((pdf_path.name, msg))

    print()
    print("Summary")
    print(f"  uploaded:           {uploaded}")
    print(f"  skipped (existing): {skipped_existing}")
    print(f"  skipped (oversize): {skipped_oversize}")
    print(f"  skipped (parse):    {skipped_unparseable}")
    print(f"  skipped (exclude):  {skipped_excluded}")
    print(f"  failed:             {len(failed)}")
    for name, msg in failed:
        print(f"    - {name}: {msg}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
