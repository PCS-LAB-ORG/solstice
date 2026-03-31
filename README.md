# Solstice — EMEA CC Migration Dashboard

EMEA Cortex Cloud upgrade account monitor for 279 EMEA accounts. FastAPI + SQLite + vanilla JS.

## Quick Start

```bash
cd Solstice
python3 dashboard.py        # → http://localhost:8200
```

- `/` — Legacy dashboard
- `/v2` — Production dashboard (8 focused sections, DC-driven)

## Architecture

```
Google Drive CSVs (browser export)
    ↓
_run_dc_pipeline()          ← DC CSE Tracker is MASTER (all milestones)
    ↓
SQLite (data/solstice.db)  ← single operational store
    ↓
FastAPI (dashboard.py)     ← REST + SSE endpoints
    ↓
v2.html                    ← vanilla JS dashboard
```

## Data Sources

| File | Purpose | Priority |
|------|---------|----------|
| `data/dc_cse_tracker.csv` | **MASTER** — M0-M9, CSE, churn risk, account rep | 1 (wins all) |
| `data/emea_accounts.csv` | EMEA status, email_sent | 2 |
| `data/blocked_accounts.csv` | Signal, status_detail | 3 |
| `data/ps_tracker.csv` | PS engagement, Clarizen | 4 |

## Key Design Rules

1. **DC CSE Tracker is the only source of truth for milestones.** Never read M0-M9 from any other file.
2. **`_run_dc_pipeline()` is the single DC sync function.** Both pipeline paths call it. Never call `_mdc()` directly.
3. **Zero stale data.** Every refresh rebuilds `m1_suggestions` from fresh `blocked_data`.
4. **Audit log shows real values.** `status_history` stores actual FROM→TO with `file_source` + `field_name`.

## Database Tables

| Table | Description |
|-------|-------------|
| `accounts` | 279 EMEA accounts |
| `blocked_data` | Milestones M0-M9, signal, cc_rep, cc_dsm, churn_risk (DC master) |
| `ps_data` | PS engagement, Clarizen IDs |
| `ai_enrichment` | Ollama-extracted blocker/owner/accountable |
| `status_history` | Audit log with file_source + field_name |
| `m1_suggestions` | M1 action plan (rebuilt on every DC sync) |
| `approved_tasks` | Pipeline-approved actions |
| `validation_errors` | Rejected rows |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/stats` | KPI counts |
| `GET /api/milestones` | All accounts M0-M9 + SLA flags |
| `GET /api/sla-breaches` | SLA violation accounts |
| `GET /api/weekly` | Weekly M8/M9 movement |
| `GET /api/cse` | CSE workload |
| `GET /api/audit-log` | DC change history |
| `GET /api/m1-suggestions` | M1 action plan by category |
| `GET /api/in-progress` | Active upgrades (M8 started) |
| `GET /api/completed` | M9 complete accounts |
| `GET /api/dq` | Data quality issues |
| `GET /api/customer-search?q=` | Account search |
| `GET /api/customer/{id}` | Full account card |
| `GET /api/run-full` | SSE pipeline (downloads + full sync) |
| `GET /api/run-pipeline` | Non-SSE pipeline sync |

## SLA Framework (effective 2026-03-09, scale cohort only)

| Transition | Max |
|---|---|
| M3 → M8 | 14 days |
| M8 → M9 | 28 days |

Prospective only — no penalty for milestones before March 9.

## DC File Fields Used

| DC Column | DB Field | Purpose |
|-----------|----------|---------|
| `M0-M9:*` | `m0_complete`…`m9_complete` | Milestone flags |
| `DC Upgrade Progress Status` | `dc_progress` | Green/Yellow/Red |
| `DC Indicated account churn risk` | `churn_risk` | Churn risk flag |
| `Account Health Notes` | `health_notes` | Raw DC risk notes |
| `cc_Rep (SPO)` | `cc_rep` | Account team rep |
| `cc_DSM (SPO)` | `cc_dsm` | DSM name |
| `CSE Assigned` | `active_cse` | CSE (DC wins) |

## Refresh Cycle

```
User clicks Refresh All Data
    → Browser exports CSVs from Google Drive
    → _mb() blocked accounts, _mp() PS tracker → state.json
    → _run_dc_pipeline():
        1. Snapshot existing dc_data
        2. Merge DC CSV → state.json
        3. Upsert all milestones + cc_rep/dsm/churn_risk → blocked_data
        4. Diff → status_history (audit)
        5. Rebuild m1_suggestions (m1_complete=0 only)
    → EMEA CSV diff → status_history
    → Ollama enrichment → ai_enrichment
```
