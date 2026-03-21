# Solstice Agent

EMEA CC Migration account monitor. Watches for CSV exports, classifies changes with Claude (Anthropic Vertex), routes through terminal approval, generates an HTML report, and outputs AppSheet-ready tasks.

## Setup

```bash
pip3 install -r requirements.txt
```

## Run

```bash
# Agent (watcher + pipeline + approval + auto report)
cd Solstice
python3 run.py

# Status API (optional, separate terminal)
python3 -m agent.api
# → http://localhost:8100/status

# Generate report manually at any time
python3 agent/reporter.py
```

## Usage

1. Export the EMEA sheet as CSV: **File → Download → CSV**
2. Drop the CSV into `data/inbox/` — agent detects it automatically
3. Review proposed tasks in the terminal: `[A]pprove / [R]eject / [E]dit / [S]kip all`
4. HTML report auto-opens in browser after each approved run
5. Import `data/pending_tasks.csv` into AppSheet

## Validation (self-healing)

Before any row reaches Claude, the agent runs automatic validation:

| Check | Rule | Action |
|---|---|---|
| Salesforce ID | Must be 15–18 alphanumeric chars | Skip + log |
| EMEA region | Must be in the EMEA REGIONS list | Skip + log |
| `#N/A` field values | Not a validation failure | Passed to Claude |
| Legend/color-key rows | Fail ID check | Silently filtered (DEBUG log only) |

Rejected rows are written to `data/validation_errors.log`. Valid rows continue through the pipeline.

## HTML Report

Auto-generated to `outputs/report_YYYYMMDD_HHMMSS.html` after every approved run. Contains:

| Section | Contents |
|---|---|
| **Status Overview** | Donut chart + table of all accounts by current status |
| **Approved Tasks** | Cards for tasks approved this session, sorted HIGH→LOW priority |
| **What To Do Next** | Grouped action table: Ready To Engage → Account Team Contacted → Churning/Sales Hold → Escalation → Blocked → On Hold |
| **Completed** | Accounts that reached Completed status with date |

### What To Do Next — column logic

| Group | Last Contact source |
|---|---|
| Ready To Engage | `email_sent` date (or status_changed_at fallback) — colour-coded red/amber/green |
| Account Team Contacted | `email_sent` date — colour-coded by staleness (red >14d, amber >7d, green <7d) |
| Blocked | Full blocker list as tags |
| All groups | Active blockers shown as amber tags under customer name |

## First Run (Bootstrap)

On first run with no `data/state.json`, the agent loads all accounts as baseline — no tasks are generated. Drop a second CSV export into `data/inbox/` to begin monitoring changes.

**IMPORTANT:** If state.json has accumulated dirty accounts (legend rows, non-Salesforce IDs), clean it by dropping a fresh CSV into inbox/ — the pipeline re-validates all accounts on each run.

## Output Files

| File | Description |
|---|---|
| `data/state.json` | Agent memory — last known state per account (279 EMEA accounts) |
| `data/pending_tasks.csv` | AppSheet-ready approved tasks (append mode) |
| `data/pending_review.log` | Accounts that failed Claude classification |
| `data/validation_errors.log` | Rows rejected by validation (bad ID or non-EMEA) |
| `data/agent.log` | Runtime log |
| `data/inbox/` | Drop CSV exports here (watched by agent) |
| `outputs/` | Timestamped HTML reports |

## Watcher Behaviour

- Watches `data/inbox/` only — agent-generated files in `data/` never re-trigger the pipeline
- 5-second debounce — same file dropped twice fires only once
- Legend/color-key rows (status names in ID column) logged at DEBUG, not WARNING

## Tests

```bash
cd Solstice && pytest -v   # 67 tests, 0 network calls, ~0.25s
```

## Architecture

```
data/inbox/ CSV drop
  → watchdog (5s debounce)
  → validator (Salesforce ID + EMEA region check → validation_errors.log)
  → differ (PASS 1: field changes + escalation/stale flags | PASS 2: expiry risk)
  → Claude Vertex classifier (pa-sase-insights-tools, us-east5, claude-sonnet-4-6)
  → Rich terminal approval [A]/[R]/[E]/[S]
  → writer (pending_tasks.csv + state.json update)
  → reporter (HTML report → auto-opens in browser)
```

## Modules

| File | Responsibility |
|---|---|
| `run.py` | Entry point — sets sys.path, suppresses EOL warnings |
| `agent/constants.py` | All enums, column indices, paths, Claude config |
| `agent/differ.py` | CSV parser + diff engine (PASS 1 + PASS 2) |
| `agent/validator.py` | Salesforce ID + EMEA region validation |
| `agent/classifier.py` | Claude Vertex batch classification + retry |
| `agent/approver.py` | Rich terminal approval UI |
| `agent/writer.py` | CSV append, state.json update, bootstrap |
| `agent/watcher.py` | Watchdog CSV drop handler (debounced) |
| `agent/main.py` | Pipeline orchestration + CLI entry point |
| `agent/reporter.py` | HTML report generator (Chart.js donut + 4 sections) |
| `agent/api.py` | FastAPI /status endpoint (port 8100) |
