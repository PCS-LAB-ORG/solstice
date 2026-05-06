# Solstice v2.1

Global CC Migration monitor — EMEA, JAPAC, AMER, LATAM.
FastAPI + SQLite + vanilla JS. Docker-first. 10-page ops dashboard.

---

## Quick Start (Docker — recommended)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed (`gcloud` in PATH)
- ADC credentials configured: `gcloud auth application-default login`
- [Google Drive for Desktop](https://www.google.com/drive/download/) installed and signed in

### 1. Install and configure Google Drive for Desktop

Solstice reads the DC CSE Tracker directly from your local Google Drive mount. Without this the **Refresh Data** button will not work.

1. Download and install [Google Drive for Desktop](https://www.google.com/drive/download/)
2. Sign in with your Palo Alto Networks Google account
3. In the app settings → **Google Drive** → select **Mirror files** (not Stream) so files are available locally
4. Wait for the initial sync to complete
5. Find the `DC CSE Tracker` file in your local Google Drive folder and note its path — it will look like:
   - **macOS:** `/Users/<you>/Google Drive/My Drive/...`
   - **Windows:** `G:\My Drive\...`
6. Open `data/drive_config.json` and confirm the file ID matches the tracker. The pipeline uses the Google Drive API (not the local path) but the local mount is required for ADC token resolution to work correctly.

### 2. Clone the repo

```bash
git clone https://github.com/shpapy/solstice.git
cd solstice
```

### 3. Start the container

```bash
docker compose up -d
```

The dashboard is now running at **http://localhost:8200/ops**

### 4. Load fresh data

Click **Refresh Data** on any page (top-right button).

The pipeline will:
1. Get an ADC token via `gcloud auth application-default print-access-token`
2. Download the DC CSE Tracker directly from Google Drive API
3. Parse all milestones (M0–M9), signals, subtypes across all theatres
4. Rebuild the M1 action plan and audit history
5. Refresh the dashboard

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
| [`/blockers`](http://localhost:8200/blockers) | Call prep: blocked/at-risk accounts grouped by subtype (incl. M0 Not Started, M0→M1 Stuck), expanded detail panel |
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
  db.py               SQLite schema + upsert operations (journal_mode=DELETE for Docker compat)
  dc_parser.py        DC CSE Tracker CSV parser — all theatres, M0-M9, signal/subtype
  differ.py           Audit diff engine (field-level change detection)
  validator.py        Salesforce ID validation + theatre filter
static/
  solstice.css        Design system tokens + shared components (bsec/shdr/sbody/arow)
  solstice.js         Shared JS — nav, search, account modal, S.toggleSec, SLA countdown
  v2.html             /ops
  blockers.html       /blockers  (M0 Not Started + M0→M1 Stuck sections at top)
  forecast.html       /forecast
  daily.html          /daily
  audit.html          /audit
  cse.html            /cse       (M8 in-flight count per CSE)
  weekly.html         /weekly
  scope.html          /scope
  wins.html           /wins
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

## SLA thresholds (current)

Defined in `static/solstice.js` — `S.slaCountdown()` and `S.blockerAge()`:

| Phase | Current SLA | Amber | Red |
|---|:-:|:-:|:-:|
| M3 → M8 | 14d | — | > 14d |
| M8 → M9 | 28d | — | > 28d |
| Blocker age | — | > 7d | > 21d |

> Data analysis (Apr 2026, n=201 M3→M8, n=35 M8→M9) suggests raising to 30d / 45d / 30d respectively. To update, edit the `used > N` and `limit:N` values in `slaCountdown` and `days<=N` in `blockerAge`.

---

## Operator runbook

### Day-to-day

1. Open **http://localhost:8200/ops** — check KPI counters and M1 action plan
2. Click **Refresh Data** to pull latest from Google Drive (takes ~10s)
3. Use **global search** (top-right) to jump to any account
4. Click any account row to open the detail modal (milestones, SLA badge, call prep, history)

### Key pages for each role

| Role | Go to |
|---|---|
| CSE / DSM daily check | `/blockers` → filter by theatre |
| Leadership update | `/daily` or `/weekly` |
| M8 upgrade tracking | `/cse` → see M8 in-flight per CSE |
| Theatre wins overview | `/wins` |
| Full account list | `/scope` |
| Change audit | `/audit` |

### Theatre filter

Every page has theatre pills: **All / EMEA / JAPAC / AMER / LATAM**. Add `?theatre=EMEA` to any URL to deep-link a filtered view.

### If the app shows a disk I/O error

```bash
# On the host (not inside the container):
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
# Python — run inside container or locally
python3 -m pytest tests/ -q

# JavaScript pure functions
node tests/js/test_pure_fns.js
```
