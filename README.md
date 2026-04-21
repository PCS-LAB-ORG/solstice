# Solstice v2.0

Global CC Migration monitor — EMEA, JAPAC, AMER, LATAM.
FastAPI + SQLite + vanilla JS. Docker-first. 8-page ops dashboard.

---

## Quick Start (Docker — recommended)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed (`gcloud` in PATH)
- ADC credentials configured: `gcloud auth application-default login`

### 1. Clone the repo

```bash
git clone https://github.com/shpapy/solstice.git
cd solstice
```

### 2. Start the container

```bash
docker compose up -d
```

That's it. The dashboard is now running at **http://localhost:8200/ops**

### 3. Load fresh data

Click **Refresh Data** on any page (top-right button).

The pipeline will:
1. Get an ADC token via `gcloud auth application-default print-access-token`
2. Download the DC CSE Tracker directly from Google Drive
3. Parse all milestones (M0–M9), signals, subtypes across all theatres
4. Rebuild the M1 action plan and audit history
5. Refresh the dashboard

> **Note:** Google Drive Desktop does not need to be installed. Data is fetched via the Google Drive API using your ADC token.

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
| [`/blockers`](http://localhost:8200/blockers) | Call prep: blocked/at-risk accounts grouped by subtype, expanded detail panel |
| [`/forecast`](http://localhost:8200/forecast) | Velocity: 12-week M9 trend, 3-month targets, overdue section, confidence logic |
| [`/daily`](http://localhost:8200/daily) | Leadership briefing: daily movements grouped by milestone type |
| [`/audit`](http://localhost:8200/audit) | Full change history with field/theatre/sort filters |
| [`/cse`](http://localhost:8200/cse) | CSE workload: account load, blocked counts, M9 velocity |
| [`/weekly`](http://localhost:8200/weekly) | Weekly digest: new M9, M8 started, newly blocked, resolved |

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

## Data sync

Data source: **DC CSE Tracker** (Google Drive, file ID `1Te5rQqhQZlGzpBk-ertJlizOgCKxfl-aa9t4Oj2mpSI`).

All milestone data (M0-M9), CSE assignment, signal, and subtype derive from this single source of truth. The file ID and tab configuration live in `data/drive_config.json`.

To trigger a sync via API:
```bash
curl http://localhost:8200/api/run-pipeline
```

---

## Architecture

```
dashboard.py          FastAPI entry point — all routes + API endpoints
Dockerfile            python:3.13-slim + gcloud CLI
docker-compose.yml    port 8200, data/ volume, ADC credentials mount
agent/
  db.py               SQLite schema + upsert operations
  dc_parser.py        DC CSE Tracker CSV parser — all theatres, M0-M9, signal/subtype
  differ.py           Audit diff engine (field-level change detection)
  validator.py        Salesforce ID validation + theatre filter
static/
  solstice.css        Design system tokens + shared components (bsec/shdr/sbody/arow)
  solstice.js         Shared JS — nav, search, account modal, S.toggleSec
  v2.html             /ops
  blockers.html       /blockers
  forecast.html       /forecast
  daily.html          /daily
  audit.html          /audit
  cse.html            /cse
  weekly.html         /weekly
data/
  solstice.db         SQLite — all account state, milestone history, audit log (volume-mounted)
  dc_cse_tracker.csv  Last downloaded DC CSV (volume-mounted)
  drive_config.json   Google Drive file IDs and tab config
```

## Design system

All pages share `static/solstice.js` via `window.S` and `static/solstice.css`:

| CSS class | Purpose |
|---|---|
| `.bsec` / `.shdr` / `.sbody` | Collapsible section — collapsed by default |
| `.reg-hdr` | Sub-group header inside a section |
| `.arow` / `.aname` | Account row — clickable, opens detail modal |
| `.move` | Movement card (daily page) |

| JS function | Usage |
|---|---|
| `S.initNav('page')` | Renders nav + theatre health bar + global search |
| `S.toggleSec(hdr, secId?)` | Collapse/expand a `.bsec` section |
| `S.openAccountCard(id)` | Full account modal with milestones, SLA, call prep |
| `S.syncSummary(events)` | Dismissible toast after pipeline refresh |
| `S.exportCSV(rows, fn)` | Client-side CSV download |

## Tests

```bash
# Python (321 tests) — run inside container or locally
python3 -m pytest tests/ -q

# JavaScript pure functions
node tests/js/test_pure_fns.js
```
