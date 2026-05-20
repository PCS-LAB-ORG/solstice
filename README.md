# Solstice v2.4

Global CC Migration monitor — EMEA, JAPAC, AMER, LATAM.
FastAPI + SQLite + vanilla JS. Docker-first. 10-page ops dashboard.

---

## Quick Start (Docker — recommended)

### Prerequisites

All standard for PANW — you almost certainly have these already:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running
- `gcloud` CLI installed and authenticated: `gcloud auth application-default login`
- [Google Drive for Desktop](https://www.google.com/drive/download/) installed, signed in with your `@paloaltonetworks.com` account, and set to **Mirror Files** mode

> **Mirror Files vs Stream Files:** In Google Drive for Desktop settings → Google Drive → select **Mirror files**. This makes `.gsheet` files available locally. Stream mode won't work.

### 1. Clone the repo

```bash
git clone https://github.com/shpapy/solstice.git
cd solstice
```

### 2. Run setup

```bash
./setup.sh
```

This auto-detects your PANW Google Drive account, writes a `.env` file, and verifies the required tracker files are accessible. Takes about 2 seconds.

Example output:
```
✅ Found Google Drive account: jsmith@paloaltonetworks.com
✅ Written .env
✅ Found: DC CSE Tracker
✅ Found: XSUP Tracker
✅ Found: COE Tracker

🚀 Ready. Run: docker compose up -d
```

### 3. Start the container

```bash
docker compose up -d
```

The dashboard is now running at **http://localhost:8200/ops**

> **First run:** the DB will be empty. Click **Refresh Data** on the ops page to pull fresh data.

### 5. Load fresh data

Click **Refresh Data** (top-right button on any page).

The pipeline will:
1. Get an ADC token via `gcloud auth application-default print-access-token`
2. Download the DC CSE Tracker CSV from Google Drive API
3. Download the XSUP Tracker (xlsx) and parse open XSUPs
4. Download the COE Tracker (xlsx) — Sheet1 (feature/blocker issues) + Cortex Bugs tab
5. Parse all milestones (M0–M9), signals, subtypes across all theatres
6. Rebuild the M1 action plan and audit history
7. Refresh the dashboard

> **Troubleshooting Refresh Data:** If the refresh fails with an auth error, run `gcloud auth application-default login` and restart the container with `docker compose restart`.

### Useful commands

```bash
docker compose up -d            # start (or restart)
docker compose up -d --build    # rebuild image after code changes
docker compose down             # stop
docker compose logs -f solstice # stream logs
docker compose ps               # check status
```

---

## Pages

| URL | Purpose |
|---|---|
| [`/ops`](http://localhost:8200/ops) | Main ops: KPI counters, milestone funnel, M1 action plan, theatre comparison |
| [`/blockers`](http://localhost:8200/blockers) | Call prep: blocked/at-risk accounts grouped by subtype — expand any row to see COE issues + Cortex Bugs |
| [`/forecast`](http://localhost:8200/forecast) | Velocity: 12-week M9 trend, 3-month targets, overdue section, confidence logic |
| [`/daily`](http://localhost:8200/daily) | Leadership briefing: daily movements grouped by milestone type |
| [`/audit`](http://localhost:8200/audit) | Full change history with field/theatre/sort filters |
| [`/cse`](http://localhost:8200/cse) | CSE workload: M8 in-flight count per CSE, sorted by load, theatre filter |
| [`/weekly`](http://localhost:8200/weekly) | Weekly digest: new M9, M8 started, newly blocked, resolved |
| [`/scope`](http://localhost:8200/scope) | Account scope explorer: full account list with milestone status per theatre |
| [`/wins`](http://localhost:8200/wins) | Upgrade wins: M9 complete counts and M8 active by theatre with rate bars |

---

## Local development (without Docker)

Only needed if you're modifying the code:

```bash
# Requires Python 3.12+
pip install -r requirements.txt
python3 dashboard.py
# → http://localhost:8200
```

---

## Data sources

Three Google Drive files are pulled on every **Refresh Data**:

| Source | Format | Purpose |
|---|---|---|
| DC CSE Tracker | CSV (gid=0) | Master account list — all milestones, CSE assignment, DC status, upgrade notes |
| XSUP Tracker | xlsx | Open TAC XSUPs linked to accounts — P1/P2 displayed on blockers page |
| Central Technical COE Tracker | xlsx | Feature/blocker requests (Sheet1) + Cortex Bugs per account |

File IDs are configured in `data/drive_config.json`. The pipeline uses the Google Drive API with ADC credentials — no service account needed.

To trigger a sync via API:
```bash
curl http://localhost:8200/api/run-pipeline
```

---

## Database schema

SQLite at `data/solstice.db` (volume-mounted — survives container restarts).

| Table | Source | Description |
|---|---|---|
| `accounts` | DC CSE Tracker | One row per account — name, theatre, CSE, signal, status |
| `blocked_data` | DC CSE Tracker | Milestone flags, subtype, upgrade/health notes, DC progress |
| `status_history` | DC CSE Tracker | Milestone change log (diff per refresh) |
| `ps_data` | DC CSE Tracker | PS engagement data — PSC, PM, Clarizen ID, timeline |
| `xsup_data` | XSUP Tracker | Open XSUPs — number, priority, status, summary, component |
| `coe_issues` | COE Tracker Sheet1 | Feature/blocker requests — issue ID, priority, module, status, timeline |
| `coe_bugs` | COE Tracker Cortex Bugs | XSUP-linked bugs — SPO DC classification, escalation status, summary |
| `parity_gaps` | Manual seed | 10 product parity gaps with description and roadmap ETA |
| `parity_gap_accounts` | Manual seed | Links parity gaps to affected accounts |
| `m1_suggestions` | Pipeline | AI-generated M1 action plan per account |
| `ai_enrichment` | Pipeline | Enrichment metadata |

Both `coe_issues` and `coe_bugs` carry an `account_id` foreign key resolved via exact + fuzzy name matching against the `accounts` table (~97% match rate for issues, ~68% for bugs — remaining unmatched are internal/test accounts or customers outside the tracked cohort).

---

## Architecture

```
dashboard.py          FastAPI entry point — all routes + API endpoints
Dockerfile            python:3.13-slim + gcloud CLI
docker-compose.yml    port 8200, data/ volume, ADC + Google Drive mounts
agent/
  db.py               SQLite schema + upsert operations
  dc_parser.py        DC CSE Tracker CSV parser — all theatres, M0-M9, signal/subtype
  differ.py           Audit diff engine (field-level change detection)
  validator.py        Salesforce ID validation + theatre filter
static/
  solstice.css        Design system tokens + shared components
  solstice.js         Shared JS — nav, search, account modal, S.toggleSec, SLA countdown
  v2.html             /ops
  blockers.html       /blockers
  forecast.html       /forecast
  daily.html          /daily
  audit.html          /audit
  cse.html            /cse
  weekly.html         /weekly
  scope.html          /scope
  wins.html           /wins
data/
  solstice.db         SQLite — all account state, milestone history, audit log (gitignored)
  drive_config.json   Google Drive file IDs and tab config (gitignored)
```

> `data/` is gitignored — no live data is committed to the repo.

---

## Design system

All pages share `static/solstice.js` via `window.S` and `static/solstice.css`:

| CSS class | Purpose |
|---|---|
| `.bsec` / `.shdr` / `.sbody` | Collapsible section — collapsed by default |
| `.reg-hdr` | Sub-group header inside a section |
| `.arow` / `.aname` | Account row — clickable, opens expand panel |
| `.expand-panel` | Inline detail panel — milestones, COE issues, Cortex Bugs |
| `.coe-section` | COE enrichment block inside expand panel |

| JS function | Usage |
|---|---|
| `S.initNav('page')` | Renders nav + theatre health bar + global search |
| `S.toggleSec(hdr, secId?)` | Collapse/expand a `.bsec` section |
| `S.openAccountCard(id)` | Full account modal with milestones, SLA, call prep |
| `S.syncSummary(events)` | Dismissible toast after pipeline refresh |
| `S.exportCSV(rows, fn)` | Client-side CSV download |

---

## SLA thresholds

Defined in `static/solstice.js`:

| Phase | SLA | Amber | Red |
|---|:-:|:-:|:-:|
| M3 → M8 | 14d | — | > 14d |
| M8 → M9 | 28d | — | > 28d |
| Blocker age | — | > 7d | > 21d |

---

## Operator runbook

### Day-to-day

1. Open **http://localhost:8200/ops** — check KPI counters and M1 action plan
2. Click **Refresh Data** to pull latest from Google Drive (~15s)
3. Use **global search** (top-right) to jump to any account
4. Click any account row on the blockers page to see milestones, COE issues, and Cortex Bugs inline

### Key pages by role

| Role | Go to |
|---|---|
| CSE / DSM daily check | `/blockers` → filter by theatre |
| Leadership update | `/daily` or `/weekly` |
| M8 upgrade tracking | `/cse` → M8 in-flight per CSE |
| Theatre wins overview | `/wins` |
| Full account list | `/scope` |
| Change audit | `/audit` |

### Theatre filter

Every page has theatre pills: **All / EMEA / JAPAC / AMER / LATAM**. Add `?theatre=EMEA` to any URL to deep-link a filtered view.

### If the app shows a disk I/O error

```bash
sqlite3 data/solstice.db "PRAGMA wal_checkpoint(TRUNCATE);"
rm -f data/solstice.db-wal data/solstice.db-shm
docker compose restart
```

### Rebuilding after code changes

```bash
docker compose build --no-cache
docker compose up -d
```

---

## Tests

```bash
python3 -m pytest tests/ -q
node tests/js/test_pure_fns.js
```
