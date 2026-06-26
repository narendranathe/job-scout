# User Profile, Logout & Preferences Design

**Date:** 2026-06-26
**Status:** Approved — moving to implementation
**Branch:** main (post-PR #123 merge)

---

## Problem Statement

JobScout now has Supabase auth, but once a user logs in there is no way to:
- See who they are logged in as
- Log out or switch to a different login method
- Edit job preferences (dream roles, preferred locations) — these fields exist in the backend but have no UI
- Access their priority companies and score weights outside the filter sidebar

---

## Solution: Header Chip + Profile Tab

Two complementary surfaces. The header chip is for quick identity awareness and logout. The Profile tab is the full account and preferences home.

---

## Architecture

### New files
- `frontend/src/components/UserChip.jsx` — avatar bubble + dropdown in the nav bar
- `frontend/src/tabs/ProfileTab.jsx` — full profile and settings tab

### Modified files
- `frontend/src/App.jsx`:
  - Add `'profile'` to the `TABS` array (renders as `👤 Profile`)
  - Add `handleLogout` function: calls `supabase.auth.signOut()`; `onAuthStateChange` subscription already handles clearing `user` state → LoginPage renders
  - Render `<UserChip>` in the nav bar between the ⚙️ button and the theme toggle
  - Add `dream_role_keywords` and `preferred_locations` state (arrays), populated from profile fetch
  - Add `handleRolesChange` and `handleLocationsChange` handlers with 300ms debounced save to `/api/profile`
  - Pass all props to `<ProfileTab>`
  - Pass `onOpenProfile={() => setTab('profile')}` to `<JobsTab>` (wires the `onOpenAddSearch` stub — fixes #120)
- `frontend/src/tabs/JobsTab.jsx`:
  - Pass `onOpenAddSearch` down to `<CompanyPriorityPanel>` (already destructured in state; just forward it)

---

## Component Designs

### UserChip (`frontend/src/components/UserChip.jsx`)

**Props:** `user` (Supabase user object), `onLogout` (function), `onOpenProfile` (function), `t` (theme object)

**Behaviour:**
- Renders an avatar bubble (32px circle) in the nav bar
  - Source: `user.user_metadata.avatar_url` if present (GitHub/Google both provide one)
  - Fallback: colored circle with first letter of email, using the same deterministic color hash from `CompanyAutocomplete`
- Clicking the bubble toggles a small dropdown (absolute-positioned below the bubble, `zIndex: 200`):
  - **"Signed in as [display_name or email]"** — non-interactive label, truncated at 28 chars with ellipsis
  - **"Profile & Settings"** — calls `onOpenProfile()`, closes dropdown
  - **"Sign out"** — calls `onLogout()`, closes dropdown
- Outside-click closes the dropdown (same `useRef` + `mousedown` handler pattern as `CompanyAutocomplete`)
- Respects the `t` theme object for background, border, text colors

**No "Switch account" item** — Sign out returns to LoginPage where any method can be chosen.

---

### ProfileTab (`frontend/src/tabs/ProfileTab.jsx`)

**Props received via `state` object** (same pattern as `JobsTab`):
```
t, user, onLogout,
companiesRoster, priorityCompanies, onCompaniesChange,
priorityMode, onModeChange, scoreWeights, onWeightsChange,
dreamRoleKeywords, onRolesChange,
preferredLocations, onLocationsChange
```

**Four sections, stacked vertically with consistent card styling:**

#### 1. Account card
- Large avatar (56px), same avatar/fallback logic as UserChip
- `user.user_metadata.full_name` or email as heading
- `user.email` as sub-label
- Login method badge: "via GitHub" / "via Google" / "via Email" — derived from `user.app_metadata.provider`
- Red "Sign out" button — calls `onLogout()`

#### 2. Company Priorities
- Section heading: "Company Priorities"
- Renders `<CompanyPriorityPanel>` directly with the same props passed from App.jsx state
- Changes sync instantly to the filter sidebar (shared state)
- `onOpenAddSearch` prop is `() => {}` (panel's internal add flow handles the GitHub issue-filing)

#### 3. Score Weights
- Section heading: "Score Weights"
- Renders `<ScoreWeightDials>` directly with `weights={scoreWeights}` and `onChange={onWeightsChange}`
- Changes sync instantly to the filter sidebar (shared state)

#### 4. Job Preferences
- Section heading: "Job Preferences"
- Two editable chip fields:

**Dream Role Keywords**
- Displays current keywords as removable chips (e.g. "data engineer ×", "ml engineer ×")
- Text input + Enter or comma to add a new keyword (trimmed, lowercased, deduplicated)
- Remove via × on each chip
- onChange fires `onRolesChange(newArray)` → 300ms debounced save to `/api/profile` as `dream_role_keywords` JSON string

**Preferred Locations**
- Same chip add/remove pattern
- e.g. "Remote", "Dallas", "Austin"
- onChange fires `onLocationsChange(newArray)` → 300ms debounced save to `/api/profile` as `preferred_locations` JSON string

---

## State additions in App.jsx

```javascript
// New state (alongside existing priority state)
const [dreamRoleKeywords, setDreamRoleKeywords] = useState([])
const [preferredLocations, setPreferredLocations] = useState([])

// Populated in the existing profile fetch useEffect
// d.dream_role_keywords — parse same way as priority_companies (array or JSON string)
// d.preferred_locations — same

// Handlers (same debounce pattern as savePriorityToProfile)
const handleRolesChange = (next) => {
  setDreamRoleKeywords(next)
  // debounced POST /api/profile with dream_role_keywords: JSON.stringify(next)
}
const handleLocationsChange = (next) => {
  setPreferredLocations(next)
  // debounced POST /api/profile with preferred_locations: JSON.stringify(next)
}
```

---

## Data flow

```
App.jsx state
  ├── user (Supabase user object)
  ├── priorityCompanies / priorityMode / scoreWeights  ← already exists
  ├── dreamRoleKeywords                                 ← new
  └── preferredLocations                               ← new

        │ passed as props
        ▼
  UserChip (nav bar)           ProfileTab              JobsTab filter sidebar
  - shows avatar + name        - Account card          - CompanyPriorityPanel (same state)
  - logout dropdown            - CompanyPriorityPanel  - ScoreWeightDials (same state)
  - → Profile tab              - ScoreWeightDials
                               - Dream roles chips
                               - Locations chips
```

Both `UserChip` and `ProfileTab` call the same `handleLogout` → `supabase.auth.signOut()` → `onAuthStateChange` fires → `setUser(null)` → App renders `<LoginPage />`.

---

## Backend

No new endpoints required. `dream_role_keywords` and `preferred_locations` already exist as columns in `user_profile` (added in the original schema). `profile_manager.py` already reads/writes them. The profile fetch `useEffect` just needs to parse and set the two new state vars.

---

## Testing approach

- After login: avatar bubble appears in nav bar
- Click bubble: dropdown shows email, "Profile & Settings", "Sign out"
- Click "Profile & Settings": navigates to Profile tab
- Profile tab: shows correct avatar, name, email, provider badge
- Edit a dream role keyword: persists after page refresh
- Edit priority companies in Profile tab: filter sidebar reflects change instantly
- Click "Sign out" (from either chip or profile tab): returns to LoginPage
- Return to app via any OAuth method: user state restores correctly

---

## Out of scope

- Editable display name / avatar upload
- Account deletion
- Email change
- Notification preferences
- LinkedIn OAuth (tracked in #121)
