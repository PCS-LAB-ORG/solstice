# Solstice Agent

EMEA CC Migration account monitor. Watches for CSV exports, classifies changes with Claude (Anthropic Vertex), routes through terminal approval, outputs AppSheet-ready tasks.

## Setup

```bash
pip3 install -r requirements.txt
```

## Run

```bash
# Terminal 1: agent (watcher + pipeline + approval)
cd Solstice
python3 run.py
# or: python3 -m agent.main

# Terminal 2: status API (optional)
python3 -m agent.api
# → http://localhost:8100/status
```

## Usage

1. Export the EMEA sheet as CSV: **File → Download → CSV**
2. Drop the CSV into `data/` — the agent detects it automatically
3. Review proposed tasks in the terminal: `[A]pprove / [R]eject / [E]dit / [S]kip all`
4. Import `data/pending_tasks.csv` into AppSheet

## First Run (Bootstrap)

On first run with no `data/state.json`, the agent loads all accounts as baseline — no tasks are generated. Drop a second CSV export to begin monitoring changes.

## Output Files

| File | Description |
|---|---|
| `data/state.json` | Agent memory — last known state per account |
| `data/pending_tasks.csv` | AppSheet-ready approved tasks (append mode) |
| `data/pending_review.log` | Accounts that failed Claude classification |
| `data/agent.log` | Runtime log |

## Tests

```bash
cd Solstice && pytest -v
```

## Architecture

```
CSV drop → watchdog → differ (PASS1: field changes, PASS2: expiry risk)
        → Claude Vertex classifier → Rich terminal approval → pending_tasks.csv
```
