"""Canonical company + role tagging rules for resume filenames.

Single source of truth for ``parse_resume_filename`` in
``backend/storage/resume_vault.py``. Imports are one-way:
``resume_vault`` consumes from here; nothing here imports from there.

Two-way bridge with the AutoApply AI tag builder
(``backend/app/services/resume_generator.py`` in the separate
``autoapply-ai`` repo). That builder goes
``(name, company, role_title, job_id) → "Narendranath_GS_DE_JOB123"``;
JobScout's parser goes the inverse direction. The canonical short-name
and role-abbreviation maps below are the union of:

* JobScout's pre-existing legacy aliases (e.g. ``"data" → Data Engineer``,
  ``"bofa" → Bank of America``)
* AutoApply's canonical ``_COMPANY_SHORT`` and ``_ROLE_ABBREVS`` tables

For each key the lowercase form is canonical; lookups in the parser
``.lower()`` the input before matching. JobID handling (the optional
``_{JobID}`` segment of the AutoApply grammar) is in ``JOB_ID_RE`` below.

Known cross-system asymmetry (called out in the AutoApply notes):

* ``_company_matches`` in AutoApply's retrieval agent computes initials
  by splitting on whitespace only, so ``"JP Morgan Chase"`` → ``"jmc"``.
* This module — and the AutoApply tag builder — treat ``"JPMC"`` as the
  canonical short name. Retrieval is permissive (it accepts ``"jmc"`` or
  ``"jpmc"``); tag-building is canonical (only ``"JPMC"``). This file
  takes the canonical side.
"""

from __future__ import annotations

import re

# ── Company short-name → canonical display name ──────────────────────────
# Keys are lowercase. Order doesn't matter — lookup is by exact key.
COMPANY_ALIASES: dict[str, str] = {
    # Finance
    "gs": "Goldman Sachs", "gsjc": "Goldman Sachs",
    "jpmc": "JPMorgan Chase", "jpmorgan": "JPMorgan Chase",
    "bofa": "Bank of America", "bankofamerica": "Bank of America",
    "ms": "Morgan Stanley", "morganstanley": "Morgan Stanley",
    "aexp": "American Express", "americanexpress": "American Express",
    "capitalone": "Capital One", "capital_one": "Capital One",
    "wellsfargo": "Wells Fargo",
    # Big tech — JobScout legacy
    "meta": "Meta", "facebook": "Meta",
    "disney": "Disney", "walt_disney": "Disney",
    "sf": "Salesforce", "salesforce": "Salesforce",
    # Big tech — added from AutoApply _COMPANY_SHORT
    "msft": "Microsoft", "microsoft": "Microsoft",
    "amzn": "Amazon", "amazon": "Amazon",
    "nflx": "Netflix", "netflix": "Netflix",
    "google": "Google", "alphabet": "Google",
    # Misc
    "qt": "Quantitative Trading",
    "sams": "Sam's Club",
    "at&t": "AT&T", "att": "AT&T",
    "ibm": "IBM", "ea": "Electronic Arts",
    "cvs": "CVS Health",
}

# ── Role abbreviation → canonical role name ─────────────────────────────
# Keys are lowercase. AutoApply's substring-match table is inverted here:
# we key on the canonical abbreviation (DE, MLE, …) and on legacy long
# forms (data, ml, …) so both legacy and AutoApply filenames parse.
#
# Derived from ``config/role_taxonomy.ROLES`` so the wizard's
# /api/role-taxonomy picker and the filename parser stay in lock-step
# (PRD #89 Slice 1). Adding a role/abbrev there flows here automatically;
# the regression test in tests/test_role_taxonomy.py pins the resulting
# dict so a taxonomy edit can't silently break filename parsing.
from config.role_taxonomy import alias_map as _role_alias_map

ROLE_ALIASES: dict[str, str] = _role_alias_map()

# ── Multi-word companies that appear as consecutive filename tokens ──────
# Tuple of lowercased parts → canonical display name. ``None`` means
# "don't merge — let downstream logic pick the trailing word(s) up as
# role" (used for "goldman_sachs_ai" → company=Goldman Sachs, role=AI).
MULTI_WORD_COMPANIES: dict[tuple[str, ...], str | None] = {
    ("goldman", "sachs"): "Goldman Sachs",
    ("capital", "one"): "Capital One",
    ("bank", "of", "america"): "Bank of America",
    ("morgan", "stanley"): "Morgan Stanley",
    ("american", "express"): "American Express",
    ("wells", "fargo"): "Wells Fargo",
    ("walt", "disney"): "Disney",
    # AutoApply expanded forms
    ("jp", "morgan"): "JPMorgan Chase",
    ("jp", "morgan", "chase"): "JPMorgan Chase",
    ("meta", "platforms"): "Meta",
    # 3-word disambiguation — let trailing word fall through to role
    ("goldman", "sachs", "ai"): None,
}

# ── JobID detection ─────────────────────────────────────────────────────
# AutoApply grammar: ``{FirstName}_{CompanyShort}_{RoleAbbrev}[_{JobID}]``
# JobID examples seen: JOB123, JOB456, REQ12345. Pattern: uppercase
# letters and digits, length ≥ 3, must contain at least one digit (so
# "DE" doesn't accidentally match). Parser only treats the LAST token as
# a JobID when there are ≥ 2 role-segment tokens — otherwise we'd
# misclassify a single-token alphanumeric role.
JOB_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*\d[A-Z0-9]*$|^\d{3,}$")


def is_job_id(token: str) -> bool:
    """True if ``token`` looks like an AutoApply JobID segment.

    Conservative — must be all-uppercase-or-digit and contain at least
    one digit. ``"DE"`` → False; ``"JOB123"`` → True; ``"REQ12345"`` →
    True; ``"12345"`` → True.
    """
    if not token:
        return False
    return bool(JOB_ID_RE.match(token))
