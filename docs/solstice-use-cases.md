# Solstice — Use Cases & Solutions

> **What the app is:** Real-time CC Migration operations dashboard covering ~1,800 accounts across EMEA, JAPAC, AMER, and LATAM. Source of truth is the DC CSE Tracker (Google Sheets). FastAPI + SQLite + vanilla JS, port 8200.

---

## Use Case → Solution Map

### 1. "What changed today?"

**Who:** VP, RC, team lead — first thing Monday morning or before a leadership call.

**Solution → `/daily`**

- Select a date (defaults to today), select theatre or leave on All.
- **KPI row** shows today's M9 completions, M8 starts, M3 buy-ins, regressions, total movements at a glance.
- **Cumulative banner** shows all-time totals — useful for QBR headlines.
- **Upgrades section** lists every M8/M9 movement with CSE name, region, timestamp.
- **30-day trend** bar chart shows M8+M9 daily volume — spot slow weeks instantly.
- **Theatre breakdown tiles** (EMEA / JAPAC / AMER / LATAM) with that day's M9/M8/M3 counts.

---

### 2. "Which accounts are stuck and why?"

**Who:** DC lead, team manager — preparing for a weekly blocker call with Sales.

**Solution → `/blockers`**

- Filter by theatre, region, or specific CSE.
- Accounts grouped into 5 buckets based on DC Status Detail:
  - **No Internal Kickoff** — NGS Sales rep hasn't responded to CSE
  - **Blocked by Account Team** — rep explicitly asked CSE to pause
  - **Technical Blocker** — CoE issue, product gap, XSIAM-related
  - **Active Deal** — XSIAM or other deal in flight, migration on hold
  - **Other** — at-risk accounts with no subtype classified
- Each row shows Rep name, DSM, DC Progress colour, and verbatim upgrade notes.
- Use the CSE dropdown to isolate one CSE's blocked list before 1:1 calls.

---

### 3. "Are we going to hit the week's targets?"

**Who:** PMO, RC, DC lead — Monday planning, Friday review.

**Solution → `/forecast`**

- **Next 7 Days table** lists every account with an M9 planned date in that window.
  - Confidence: HIGH (M8 active + DC Green), MED (M8 active), LOW (M8 not started)
  - Overdue banner shows count of accounts past M9 date — requires escalation.
- **4-week M9 velocity grid** — one column per week, M9 completions count, ↑/↓ arrows vs previous week.
- **Trend footer** — UP / DOWN / FLAT across the 4-week window.
- **Theatre tiles** — how many M9 targets each theatre owns this week.

---

### 4. "How is the team performing week over week?"

**Who:** VP, RC — QBR prep, monthly cadence review.

**Solution → `/ops` → Weekly Tracker section**

- Table shows M3/M5/M8/M9 completions by ISO week going back 12 weeks.
- Filter by theatre (EMEA / AMER / JAPAC / LATAM).
- Sort by week, see acceleration or deceleration at a glance.
- ▲/▼ indicators vs previous week on each milestone column.
- Scale cohort only — SMB and churn accounts are excluded.

---

### 5. "Who should we call first from the M1 list?"

**Who:** CSE lead, DC coordinator — setting weekly M1 outreach priorities.

**Solution → `/ops` → M1 Action Plan section**

- Shows all accounts not yet M1-complete, grouped by suggested action:
  - **CSE Assigned** — has a CSE, ready to contact
  - **Account Team** — blocked/no CSE, escalate to rep or DSM
  - **Reassign** — current CSE at capacity or needs rebalancing
- Each row shows: account name, current CSE, cc_Rep (SPO), cc_DSM, theatre, churn risk, DC signal.
- Filter by theatre. Sort by suggested action.
- Red churn risk accounts are automatically routed to Account Team bucket.

---

### 6. "What's the full history for this account?"

**Who:** CSE, DC lead, compliance — auditor asks "why is this account stuck at M5 since January?"

**Solution → `/audit`**

- Search by account name — timeline shows every tracked change: milestone advances, CSE reassignments, regressions (Y→N).
- Filter by field (M9 only, M8 only, CSE changes, etc.) or by theatre.
- Switch between Oldest First / Newest First.
- Stats bar at top: total M9 / M8 / M3 / CSE / regressions across the filtered set.
- Each entry: badge (M9/M8/CSE), account name in milestone colour, time of day, CSE name, theatre tag.

---

### 7. "I need to do a specific account deep-dive for a customer call"

**Who:** CSE, account team — pre-call prep for a single customer.

**Solution → `/ops` → Customer Search (top bar)**

- Type 3+ chars of any account name — instant search across all ~1,800 accounts.
- **Customer card** shows:
  - Header band colour-coded by DC Progress (Green/Yellow/Red)
  - Status split: EMEA status left, DC migration status right
  - DC alert bar: signal (green/blocked/at_risk) + churn risk + live fire flag
  - Full M0–M9 milestone progress bar with planned/actual dates
  - Notes panel: upgrade notes (left) + health notes (right)
  - 5-col metadata grid: CSE, cc_Rep, cc_DSM, cohort, theatre/region

---

### 8. "Which CSEs are overloaded? Who has capacity?"

**Who:** Team lead — monthly workload rebalancing.

**Solution → `/ops` → CSE Workload section**

- Per-CSE summary: total accounts, M9 complete count, M8 in-progress, blocked count, at-risk count.
- Signal breakdown per CSE: green / blocked / at_risk — spot who is carrying the hard accounts.
- Filter by theatre.
- Use alongside `/ops` M1 Action Plan to see redistribution impact before committing changes to DC file.

---

### 9. "Are we breaching SLA commitments?"

**Who:** RC, PMO — compliance with M3→M8 ≤14d and M8→M9 ≤28d commitments (scale cohort, from 2026-03-09).

**Solution → `/ops` → SLA section**

- Shows accounts in the SLA tracking window that have exceeded thresholds.
- M3→M8 breach: M3 complete, M8 not started, >14 days elapsed.
- M8→M9 breach: M8 started, M9 not complete, >28 days elapsed.
- Only scale cohort accounts (SLA framework applies to scale, not SMB).
- Prospective only — SLA clock starts from 2026-03-09.

---

### 10. "Refresh the data right now"

**Who:** Anyone — DC file was updated in the last hour, want to see it reflected.

**Solution → Any page → "⟳ Refresh Data" button** (on `/ops` and `/daily`)

- Triggers SSE stream: downloads latest DC CSE Tracker from Google Drive, parses all 4 theatres, upserts 56 columns per account, runs audit diff, backfills M8/M9 history, rebuilds M1 suggestions.
- Button shows live progress events ("Downloading DC file…", "Synced 1,791 accounts", "Done").
- All sections auto-reload when pipeline completes.
- All pages auto-refresh every 5 minutes when showing today's date (daily page) or every 60 seconds (ops page).

---

### 11. "Show me everything for JAPAC only"

**Who:** JAPAC RC lead — wants their own scoped view without EMEA noise.

**Solution → Theatre filter (present on every page)**

- All pages: `All | EMEA | AMER/NAM | JAPAC | LATAM` pills in page header.
- Selecting JAPAC filters: funnel, weekly tracker, M1 plan, CSE workload, blockers, forecast, audit, daily briefing — all scoped instantly.
- Switching theatre retains current date / search / sort state.

---

### 12. "I need to understand account regression — something went backwards"

**Who:** RC, team lead — spot-check after a sync, or following a complaint from a customer.

**Solution → `/audit` + `/daily`**

- `/audit`: filter by field → leave blank, sort newest first, look for red REGRESSION entries (Y→N on any milestone).
- `/daily`: Regressions section (collapsed by default) auto-expands if there are any on the selected date — shows exactly which accounts regressed, from which milestone, CSE, region.
- Both surfaces show the exact old_status → new_status values pulled from the DC file diff.

---

## Page Quick-Reference

| Page | URL | Primary use | Key filter |
|---|---|---|---|
| Ops | `/ops` | Daily ops, M1 planning, SLA, CSE workload | Theatre |
| Blockers | `/blockers` | Pre-call blocker review | Theatre + CSE + Region |
| Forecast | `/forecast` | Week targets, velocity trend | Theatre |
| Daily | `/daily` | Leadership standup | Date + Theatre |
| Audit | `/audit` | Account history, regression check | Theatre + Field + Search |

## Data Freshness

- **Source:** DC CSE Tracker (Google Sheets, auto-downloaded from Drive)
- **Refresh:** Manual via "⟳ Refresh Data" button, or automatic on startup
- **Latency:** ~30s for full 4-theatre sync including audit diff + M1 rebuild
- **History:** Audit log captures all changes since first sync (earliest entries from March 2026)
