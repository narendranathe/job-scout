# JobScout — First-Run Onboarding Wizard

**Date:** 2026-05-17
**Status:** Draft (Pending Approval)
**Owner:** Naren
**Type:** Product Requirements Document (PRD)

---

## 1 · Problem Statement

JobScout's dashboard opens directly on the Jobs tab and assumes a configured
user. There is no onboarding. A first-time visitor sees:

* A nine-tab dashboard with no idea where to start
* Job cards filtered by `relevance_score`, but the scoring weights come
  from `core/relevance.py` (developer-edited) — the visitor has no way
  to tell the system what roles they want
* A Vault tab full of upload affordances but no narrative — "what should
  I upload first?"
* A Setup panel in Monitor, gated behind an API token they haven't seen
  yet

The 153 scraped companies live in `config/companies.py`, edited by
developers. The user has no UI to express "these are the companies I
care about" — the only signal is the `dream_companies` JSON column
inside `user_profile`, which is currently written by direct API call,
not by a screen. The PIN-based auth is enforced everywhere but has no
first-run "create your PIN" experience — new users hit a 401 wall.

The data model is already most of what we need (`user_profile`,
`resume_versions`, `applications`); the gap is **the experience that
populates it**.

---

## 2 · Goals

| # | Goal | Measure |
|---|------|---------|
| G1 | First-time user reaches a personalized Jobs tab in ≤ 5 minutes | Wall-clock from landing to first relevance-sorted view |
| G2 | Target roles + companies + resume preferences are all settable from the browser (zero `companies.py` edits required for normal use) | Count of user prefs writable from UI = 100% of `user_profile` columns |
| G3 | At least one resume PDF is in the vault before the wizard exits | `/api/vault/stats.pdf_count ≥ 1` after onboarding |
| G4 | Returning user with a PIN never sees the wizard again | Wizard re-entry only via explicit `/setup` route |
| G5 | The wizard runs against the same backend a power-user can also drive via JSON API — no parallel REST surface | Every wizard write maps 1:1 to an existing endpoint or a single new one |

## Non-Goals

* **Multi-user / multi-tenant.** JobScout stays single-user with one PIN.
  No accounts, no SSO, no Stripe.
* **Removing `config/companies.py`.** The 153-company scraper roster
  stays developer-curated; user "target companies" is a filter +
  alert-priority layer on top.
* **In-browser scraper config for new ATS platforms.** Adding a brand-new
  company to the scrape rotation still requires a `companies.py` edit
  (and possibly a new scraper module). The wizard can capture *intent*
  ("track this company even though I don't see it yet") but doesn't
  add it to the scrape roster.
* **AutoApply AI integration.** Out of scope for this PRD — that's a
  separate AutoApply project. Onboarding completion does *not* enroll
  the user into auto-applying.
* **Dark/light theme picker, locale, accessibility audit.** All deferred
  to a separate UI polish pass.

---

## 3 · Personas

### P1 — Naren (Power User, today's primary)

Built JobScout for himself. Already has 245 PDFs in a folder, a PIN, a
known Render URL. For him the wizard is **a faster way to mass-edit
preferences he currently has to write Python config for**, plus a way
to demo the project to others without exposing his `.env`.

### P2 — Friend or recruiter trying the live demo

Lands on the GitHub Pages dashboard from a link. Wants to scope what
JobScout does in under 2 minutes before deciding whether to stand up
their own instance. Needs a *read-only preview path* (current dashboard
behavior) that doesn't force them through the wizard.

### P3 — Self-hosted user (future)

Forks the repo, deploys to their own Render. Wants the wizard the first
time they open the dashboard so they don't have to learn the API to
populate `user_profile`. This persona is the long-term target.

---

## 4 · User Journey (Text Flow)

```
Landing
  ├─ Detect first-run state (no PIN set + no profile rows) ──▶ Wizard step 1
  ├─ PIN set, no session cookie ───────────────────────────────▶ Login step
  └─ Valid session ────────────────────────────────────────────▶ Jobs tab

Wizard
  Step 1 — Welcome + What This Does
    └─ "Get started" (primary) | "Skip — I'm just looking" (secondary, goes to read-only)

  Step 2 — Pick Your Roles
    Multi-select chip cloud from the role taxonomy:
      Data Engineer · ML Engineer · AI Engineer · Analytics Engineer ·
      Data Scientist · Software Engineer · Backend Engineer ·
      Platform Engineer · Quant Strategist · Data Analyst ·
      Site Reliability Engineer
    + free-text "Add another…" input for off-taxonomy roles
    → writes to user_profile.dream_role_keywords (existing column)

  Step 3 — Pick / Type Target Companies
    Tabbed UI with two modes:
      A. Pick from list — searchable chip cloud of the 153 scraped companies,
         pre-grouped by tier (Dream · Top · Stretch). Each toggled chip writes
         to user_profile.dream_companies. Sample preview: "12 selected · 47 jobs
         in vault right now match."
      B. Type a name — autocomplete against the 153, with a "track anyway"
         fallback when the typed name has no match. Tracked-but-unscraped
         companies go into a new user_profile.tracked_companies column +
         surface a small warning chip: "Not currently scraped — we'll
         alert you if a posting appears."

  Step 4 — Locations & Compensation (optional)
    Preferred locations chip input (remote, dallas, austin, …) →
      user_profile.preferred_locations
    Minimum total comp slider (optional) → user_profile.min_total_comp
    "Show jobs missing salary data?" toggle → user_profile.show_unsalaried
    Skip-able.

  Step 5 — Resume Vault
    Two paths:
      A. "I have one resume to start" — drag-drop a PDF;
         parse_resume_filename runs in the browser preview, user confirms
         (or edits) detected Company/Role/Date, single POST /api/vault/upload.
         Sets it as default resume.
      B. "I have many resumes" (advanced) — link to docs page explaining
         the bulk_upload_to_render.py CLI, with the recommended exclude
         pattern pre-filled.

  Step 6 — Lock It With a PIN
    "Create a PIN" — 4–8 digit input + confirm. POST /api/set-pin.
    "Skip for now (anyone with the URL can edit your preferences)" — explicit
    consent box, sets user_profile.skip_pin_acknowledged = 1.

  Step 7 — Done
    Confetti-free success card with:
      "{N} roles, {M} companies, {V} resumes — let's find your next job."
    [ Go to dashboard ]
```

The whole flow is one React component (`<OnboardingWizard>`) with
internal step state in `useReducer`. No new routes besides `/setup`.
Each step is independently skippable except role selection (G2 hard
requirement: at least one role must be set before exit).

---

## 5 · Functional Requirements

### 5.1 First-Run Detection

The dashboard is considered "first-run" when **both** conditions hold:

* `GET /api/profile` returns either 404 or a row where
  `dream_role_keywords == [] && dream_companies == [] && pin_hash == ""`
* `GET /api/vault/stats` returns `pdf_count == 0`

When both are true on initial load, the dashboard redirects to
`/setup`. A `?force=1` query param lets returning users re-enter the
wizard. A new `user_profile.onboarded_at` timestamp tracks completion
so the redirect never fires again after the wizard runs.

### 5.2 Role Picker

* Canonical taxonomy lives in a new `backend/config/role_taxonomy.py`
  — currently the role list is split across `core/relevance.py`
  (skill weights), `storage/company_rules.py::ROLE_ALIASES` (filename
  abbrevs), and JD parsing. Consolidate into one file.
* The wizard reads the taxonomy via a new `GET /api/role-taxonomy`
  endpoint (cacheable, no auth — public list).
* Selecting roles persists to `user_profile.dream_role_keywords`
  (existing column) — array of canonical role strings.
* Free-text "add another" entries are stored alongside, marked
  `is_custom: true` so the UI can render them differently.

### 5.3 Company Picker / Type-to-Track

* "Pick" tab lists the 153 companies from a new public endpoint
  `GET /api/companies-roster` that returns `[{name, tier, ats,
  job_count_30d}]`. Existing `config/companies.py` is the source.
* "Type" tab uses the same roster for autocomplete.
* A name not in the roster gets a "track anyway" affordance →
  appends to **new** `user_profile.tracked_companies` JSON column.
* Background scraper continues to use `config/companies.py`. The
  Jobs tab filter prefers `dream_companies ∪ tracked_companies`; for
  tracked-but-not-scraped names, the dashboard shows a chip ("Not yet
  scraped — alerts only") and surfaces them in a follow-up admin
  email/Discord ping if they ever appear in a future scrape (e.g. a
  contractor opened a Greenhouse board under that name).

### 5.4 Locations & Compensation

* `preferred_locations` already in schema; UI is a chip-input with
  autocomplete against the distinct `jobs.location` values from the
  last 30 days (new endpoint `GET /api/locations-roster`).
* Two new optional columns:
  * `min_total_comp INTEGER DEFAULT 0` — when > 0, Jobs tab hides
    rows with `salary_max < min_total_comp` (and the user toggles
    `show_unsalaried` to control rows with `salary_max == 0`).
  * `show_unsalaried INTEGER DEFAULT 1` — default keeps current
    behavior (showing rows with missing salary).

### 5.5 Resume Vault Onboarding

* The single-PDF path opens a drag-drop zone wired to existing
  `POST /api/vault/upload` (multipart). On drop, run
  `parse_resume_filename` client-side (port the function to JS or
  hit a new `POST /api/vault/parse-filename` echo endpoint) and show
  a preview card with editable Company / Role / Submitted-at fields.
* On confirm: PUT to `/api/vault/upload` with all three plus the PDF
  bytes. Server already handles `submitted_at` (shipped in PR #68).
* On success: write `default_resume_version = result.version_key` into
  `user_profile` (column already exists per `profile_manager.py:143`).
* The "I have many resumes" path is a static info card pointing at
  `backend/tools/bulk_upload_to_render.py --help`, with the
  recommended `--exclude` regex copy-pasteable.

### 5.6 PIN Setup

* The existing `POST /api/set-pin` endpoint is sufficient — wizard
  just wraps it. No password complexity rules beyond length (4–8
  digits). PIN is hashed with `pbkdf2_hmac` already (see
  `profile_manager.py`).
* "Skip for now" writes `skip_pin_acknowledged = 1` and surfaces a
  permanent banner on the dashboard until a PIN is set.

### 5.7 Login Screen

* When `pin_hash != ""` and no valid session cookie, render the login
  step instead of the wizard. Single PIN input + "Sign in".
* Session: 30-day signed cookie (Flask's stdlib `itsdangerous`,
  already a transitive dep via Flask). New endpoint
  `POST /api/login` that validates PIN and sets the cookie. Existing
  Bearer-token API_SECRET path stays untouched for power users + the
  bulk uploader script.

---

## 6 · Data Model Changes

Three new columns on `user_profile`, one new column type, no new tables:

```sql
-- profile_manager.create_table additions
ALTER TABLE user_profile ADD COLUMN tracked_companies TEXT DEFAULT '[]';
ALTER TABLE user_profile ADD COLUMN min_total_comp INTEGER DEFAULT 0;
ALTER TABLE user_profile ADD COLUMN show_unsalaried INTEGER DEFAULT 1;
ALTER TABLE user_profile ADD COLUMN onboarded_at TEXT;
ALTER TABLE user_profile ADD COLUMN skip_pin_acknowledged INTEGER DEFAULT 0;
```

All five additions follow the existing `ALTER TABLE … IF NOT EXISTS`
idempotent pattern (`profile_manager.py:140-150`).

Role taxonomy lives in code, not the DB:

```python
# backend/config/role_taxonomy.py — new file
ROLES = [
    {"key": "data_engineer", "label": "Data Engineer",
     "skills": ["python", "sql", "spark", "airflow", "etl"]},
    {"key": "ml_engineer", "label": "ML Engineer",
     "skills": ["python", "pytorch", "mlflow", "feature store"]},
    # …
]
```

`core/relevance.py` switches from inline role heuristics to importing
`ROLES`. `storage/company_rules.py::ROLE_ALIASES` also imports from
here. One canonical taxonomy, three consumers.

---

## 7 · Vertical Slices

Ship in four independently mergeable slices. Each ends with a working
dashboard.

### Slice 1 — Backend Foundations
* Add five new `user_profile` columns
* Create `backend/config/role_taxonomy.py` and migrate `relevance.py`
  + `company_rules.py` to consume it (regression test that scoring
  hasn't shifted)
* New endpoints: `GET /api/role-taxonomy`, `GET /api/companies-roster`,
  `GET /api/locations-roster`, `POST /api/login` (cookie auth)
* `pytest`: schema migration test, public-roster endpoints return
  expected shape, login cookie round-trip, PIN-set then login then
  preference write E2E.

### Slice 2 — Wizard Component (Steps 1–4)
* `<OnboardingWizard>` React component with `useReducer` state
* Steps 1 (welcome), 2 (roles), 3 (companies — picker + type), 4
  (locations/comp)
* `/setup` route in App.jsx
* First-run detection in App.jsx top-level
* No vault, no PIN step yet — those land in Slice 3

### Slice 3 — Vault Onboarding + PIN (Steps 5–6)
* Drag-drop PDF upload with parsed-metadata preview
* Single-PDF wizard path → `POST /api/vault/upload`
* "Many resumes" info card with copy-pasteable bulk_upload command
* PIN setup step (wraps existing `/api/set-pin`)
* Skip-PIN banner

### Slice 4 — Login + Polish
* Login screen (PIN entry, sets cookie)
* Returning-user routing logic
* "Reset onboarding" admin button on the Monitor tab
* Public-preview mode (skip wizard, dashboard works read-only until
  any write attempt, then prompts to set up)

Each slice gets its own PR; merge order is 1 → 2 → 3 → 4. Slices 2
and 3 can develop in parallel against Slice 1's API once that's
green.

---

## 8 · Open Questions

| # | Question | Default if unanswered |
|---|----------|-----------------------|
| Q1 | Should typed-but-unscraped companies trigger a developer notification (Discord ping to Naren) so they can be added to `companies.py`? | Yes, with rate-limit |
| Q2 | Is "Skip — I'm just looking" a real path, or do we hard-gate the dashboard behind onboarding? | Allow skip (P2 persona) — read-only access until first write |
| Q3 | Session cookie domain — `Secure; HttpOnly; SameSite=Lax` enough, or do we need CSRF tokens for write endpoints? | Add CSRF token for POSTs from cookie-authed sessions; Bearer-authed requests keep current behavior |
| Q4 | Multiple resume vault on first run — should the "many resumes" path support a server-side zip upload to avoid asking the user to run a Python script? | Defer (deferred-mark in Slice 3 docs) |
| Q5 | Role taxonomy — keep flat list or add a hierarchy ("Data" → DE / DA / DS)? | Flat for v1 |

---

## 9 · Success Metrics

### Functional (must-pass before merge)

* Fresh container + empty DB → wizard appears on first load (no
  manual config)
* All 7 wizard steps reachable in order; back-button preserves state
* On completion: `/api/profile` returns the user-supplied
  `dream_role_keywords`, `dream_companies`, `tracked_companies`;
  `/api/vault/list` includes the uploaded PDF; `pin_hash` non-empty
* Returning user with cookie loads Jobs tab directly (no wizard
  flash)

### Observability

* New `onboarded_at` column gives a single source of truth for
  "user completed wizard"
* Add three counters to `/api/admin/doctor`:
  `onboarded_users` (0 or 1 today), `wizard_steps_skipped`,
  `tracked_but_unscraped_companies_count`

### Manual UAT (post-merge)

1. Naren walks through wizard on a fresh laptop, no `.env`, just the
   Render URL. Time-to-first-job ≤ 5 min.
2. Wizard re-entry via `?force=1` works without nuking prior config.
3. Bulk uploader still works against a PIN-enabled server (`API_SECRET`
   Bearer auth unaffected by the new cookie auth).

---

## 10 · Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Cookie auth + Bearer auth diverging in the routes layer (security inconsistency) | Med | Single `_check_auth()` helper handles both; existing Bearer tests stay green, new tests cover cookie path |
| Wizard adds a backend coupling we can't easily remove (e.g., onboarded_at column becomes load-bearing) | Low | All new columns nullable / have safe defaults; can be ignored if wizard is later replaced |
| Typed-company tracking becomes a quiet graveyard (users add 50 names, no scraping happens) | Med | UI shows "not yet scraped" chip + the doctor-counter surfaces it; periodic Discord notification per Q1 |
| Role taxonomy refactor breaks relevance scoring | Med | Regression test: snapshot 100 jobs' current `relevance_score`, assert ≤ ±0.02 drift after refactor |
| PIN cookie session leaks via shared link (user copies the URL with cookie?) | Low | Cookies aren't in URLs; standard browser behavior. Document the risk in step 6 copy |

---

## 11 · Out of Scope / Future Work

* OAuth / SSO (would require multi-user model first)
* Wizard analytics dashboard (step drop-off, time-per-step)
* Onboarding email drip (no email channel today; Discord/Telegram only)
* Mobile-first redesign of the wizard (responsive defaults from
  Tailwind/CSS only)
* Role-recommendation engine ("based on your uploaded resume, you might
  want to track …")
* GitHub Action / cron to email "your weekly job digest"
* AutoApply AI extension installation step

---

## 12 · Appendix — Endpoint Diff Summary

| Endpoint | Status | Purpose |
|---|---|---|
| `GET /api/role-taxonomy` | **NEW** | Public list of canonical roles for the picker |
| `GET /api/companies-roster` | **NEW** | Public list of scraped companies + tier + recent job count |
| `GET /api/locations-roster` | **NEW** | Distinct `jobs.location` values from last 30 days |
| `POST /api/login` | **NEW** | PIN → signed session cookie |
| `POST /api/logout` | **NEW** | Clear session cookie |
| `GET /api/profile` | EXTEND | Add `tracked_companies`, `min_total_comp`, `show_unsalaried`, `onboarded_at`, `skip_pin_acknowledged` to response |
| `POST /api/profile` | EXTEND | Accept the same five new fields |
| `POST /api/vault/upload` | NO CHANGE | Already accepts `submitted_at` (PR #68) |
| `POST /api/set-pin` | NO CHANGE | Wizard wraps existing endpoint |
| `POST /api/verify-pin` | DEPRECATE in favor of `/api/login` | Keep for back-compat one release, then remove |

---

## 13 · Acceptance Checklist (entrance to implementation)

* [ ] PRD approved by owner
* [ ] Slice 1 → 4 broken into GitHub issues, each ≤ 1 PR of work
* [ ] Role taxonomy schema reviewed (Q5 closed)
* [ ] Cookie + CSRF strategy reviewed (Q3 closed)
* [ ] Wizard copy reviewed (welcome, completion, skip-PIN warning)
* [ ] Read-only preview decision (Q2 closed)
