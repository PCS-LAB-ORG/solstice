# Solstice

Global CC Migration monitor — EMEA, JAPAC, AMER, LATAM.
FastAPI + SQLite + vanilla JS. 8-page ops dashboard.

## Pages

| URL | Purpose |
|---|---|
| `/ops` | Main ops: KPI counters, milestone funnel, SLA breach list, M1 action plan |
| `/blockers` | Call prep: blocked/at-risk by subtype, inline call brief, blocker age |
| `/forecast` | Velocity: next-week M9 targets, 4-week trend, SLA countdown |
| `/daily` | Leadership briefing: daily movements, 30-day M8/M9 trend |
| `/audit` | Full change history with export |
| `/cse` | CSE workload: account load, blocked counts, monthly velocity |
| `/weekly` | Weekly movement digest: new M9, M8 started, newly blocked, resolved |
| `/compare` | 4-theatre side-by-side comparison for QBR |

## Setup

```bash
pip install -r requirements.txt
cd Solstice && python3 dashboard.py
# Opens on http://localhost:8200
```

## Data sync

Click **Refresh Data** on any page, or:
```bash
curl http://localhost:8200/api/run-pipeline
```

Data source: DC CSE Tracker (Google Drive). All milestone data (M0-M9), CSE assignment, signal, and subtype derive from this single source of truth.

## Architecture

```
dashboard.py          FastAPI entry point — all routes + API endpoints
agent/
  db.py               SQLite schema + upsert operations
  dc_parser.py        DC CSE Tracker CSV parser (EMEA/JAPAC/AMER/LATAM)
  differ.py           Audit diff engine (field-level change detection)
  validator.py        Salesforce ID validation + theatre filter
static/
  solstice.js         Shared design system — nav, search, account modal, badges
  solstice.css        Design tokens (Ops Center cyan aesthetic)
  v2.html             /ops
  blockers.html       /blockers
  forecast.html       /forecast
  daily.html          /daily
  audit.html          /audit
  cse.html            /cse
  weekly.html         /weekly
  compare.html        /compare
```

## Tests

```bash
# Python (321 tests)
/opt/homebrew/opt/python@3.14/bin/python3 -m pytest tests/ -q

# JavaScript pure functions (25 tests)
node tests/js/test_pure_fns.js
```

## Design system

All pages share `static/solstice.js` via `window.S`:

| Function | Usage |
|---|---|
| `S.initNav('page')` | Renders nav + theatre health bar + global search |
| `S.openAccountCard(id)` | Full account modal with milestones, SLA, call prep |
| `S.slaCountdownHTML(...)` | SLA countdown badge (M3->M8 <=14d, M8->M9 <=28d) |
| `S.blockerAgeHTML(date)` | "Blocked N days" badge (green->amber->red) |
| `S.syncSummary(events)` | Dismissible toast after pipeline refresh |
| `S.exportCSV(rows, fn)` | Client-side CSV download |
