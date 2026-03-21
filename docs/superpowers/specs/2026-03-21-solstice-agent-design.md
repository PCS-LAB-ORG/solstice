# Solstice Agent — Design Spec
**Date:** 2026-03-21
**Author:** Marius (EMEA Lead)
**Status:** Approved

---

## 1. Problem Statement

The EMEA team (4 people: Marius, Irene, Alvaro + 1) manages 300 Prisma Cloud CC Migration accounts across 11 sales regions. Status is tracked in a Google Sheet (AppSheet as source of truth). Currently, detecting account status changes, identifying required actions, and updating the tracker is manual and error-prone.

The Solstice Agent automates change detection, classifies required actions using an LLM, routes them through a human approval step, and generates AppSheet-ready updates.

---

## 2. Scope — MVP

- Input: manually exported CSV dropped into `Solstice/data/`
- Monitor: file system (watchdog), no live API auth required
- Classify: Claude (Anthropic Vertex) assigns task category + priority
- Approve: terminal UI (Rich), one task at a time, approve / reject / edit
- Output: `pending_tasks.csv` ready for AppSheet manual import
- Wrapper: FastAPI with `/status` and `/run-now` endpoints
- Runs on: EMEA lead's local machine (always-on background process)

Out of scope for MVP: AppSheet API write, Drive API polling, multi-user web UI, Okta auth, cross-regional feeds.

---

## 3. Data Model

### Source: EMEA Accounts CC Migrations - Accounts.csv

**Key identifier:** column 0 (account ID, e.g. `0010g00001j67uzaaq`)

**Tracked fields:**

| Field | Type | Notes |
|---|---|---|
| Customer name | string | Display name |
| ARR | string | Annual recurring revenue |
| Active CSE(s) | string | Primary owner |
| Irene Backup CSE | string | Backup owner |
| Status | enum | See status constants below |
| Expiration date | date | MM/DD/YY format |
| PS Engaged | string | Professional Services flag |
| Kickoff Date | date | |
| Comments | text | Free-form notes |
| Sales region | enum | See region constants below |
| Email Sent | string | Outreach tracking |
| 11x blocker columns | boolean | See blocker constants below |

### Status Constants (15 values)

```
Ready To Engage
Account team contacted
Upgrade Email Sent
Kick Off Scheduled
Customer Engaged
In Progress
Customer Acceptance
PS
Completed
On Hold
Backoff
Sales Hold
Blocked: Tech limitation
Churning/Churned
Cancelled
```

### Sales Region Constants (11 values)

```
Alps, Benelux, CEE, France, Germany,
Gulf/North Africa, Nordics, SEUR, Saudi/LBS, Turkey/SA, UKI
```

### Blocker Field Constants (11 fields)

```
APIs usage / custom integrations / scripts (blocker)
BYOK required?
AgentiX required?
Alibaba or IBM (blocker)
OIDC SSO (blocker)
Custom Compliance (blocker)
Unsupported Notifications/Integrations (blocker)
Terraform (provider&onboarding) (blocker)
Agentless AKS/EKS in auto-mode (blocker)
serverless with layers from different accounts (blocker)
serverless runtime protection (blocker)
serverless without internet connection (blocker)
Linux Functions without External Package URL (blocker)
app-embeded protection capabilities (blocker)
```

---

## 4. Task Categories

Each change produces exactly one task with a primary category and priority.

| Category | Trigger | Default Priority |
|---|---|---|
| `ESCALATION` | Status → Backoff / Sales Hold / Churning+Churned / Cancelled | HIGH |
| `CUSTOMER_OUTREACH` | Status = Ready To Engage or Account team contacted, stale >2 weeks | HIGH |
| `BLOCKER_REVIEW` | Any blocker column flipped to a non-empty value | MEDIUM |
| `STATUS_UPDATE` | Status changed (non-escalation path) | MEDIUM |
| `PS_ENGAGEMENT` | PS Engaged changed OR Kickoff Date set OR Kick Off Scheduled | MEDIUM |
| `EXPIRY_RISK` | Expiration date <= 30 days from today | HIGH |

### Task Output Schema

Each approved task written to `pending_tasks.csv`:

```
account_id, customer_name, region, cse, category, priority,
suggested_action, old_value, new_value, detected_at
```

---

## 5. Architecture

```
User drops CSV export into Solstice/data/
        |
        v
[watcher.py] watchdog FileSystemEventHandler
detects new/modified CSV in data/ folder
        |
        v
[differ.py] load new CSV + state.json
compute per-account diffs (changed fields, new accounts, status changes)
        |
        v
[classifier.py] send diffs to Claude (Anthropic Vertex)
claude-sonnet-4-6, us-east5, pa-sase-insights-tools
returns: category, priority, suggested_action per account
        |
        v
[approver.py] Rich terminal UI
display each proposed task
user: [A]pprove / [R]eject / [E]dit / [S]kip all remaining
        |
        v
[writer.py] write approved tasks to pending_tasks.csv
update state.json to new CSV baseline
        |
        v
User imports pending_tasks.csv into AppSheet manually
```

### FastAPI Wrapper (main.py)

| Endpoint | Method | Purpose |
|---|---|---|
| `/status` | GET | Returns agent health, last run time, pending task count |
| `/run-now` | POST | Triggers immediate scan of data/ folder |

Runs on `localhost:8100`. Uvicorn, single worker.

---

## 6. File Structure

```
Solstice/
  data/
    EMEA Accounts CC Migrations - Accounts.csv   <- drop exports here
    state.json        <- auto-generated, last known state per account
    pending_tasks.csv <- output, AppSheet-ready
  agent/
    main.py           <- FastAPI entry point
    watcher.py        <- watchdog file monitor
    differ.py         <- CSV diff engine
    classifier.py     <- Claude Vertex classification
    approver.py       <- Rich terminal approval UI
    writer.py         <- CSV output + state update
    constants.py      <- all status/category/blocker/region enums
  docs/
    superpowers/specs/
      2026-03-21-solstice-agent-design.md
  requirements.txt
  README.md
```

---

## 7. Tech Stack

| Component | Library | Version |
|---|---|---|
| File watcher | `watchdog` | latest |
| LLM | `anthropic[vertex]` | latest |
| API wrapper | `fastapi` + `uvicorn` | latest |
| Terminal UI | `rich` | latest |
| Data handling | stdlib `csv` + `json` | — |

LLM config (matches existing project):
- Project: `pa-sase-insights-tools`
- Region: `us-east5`
- Model: `claude-sonnet-4-6`
- Auth: ADC (gcloud, already active)

---

## 8. State Management

`state.json` is the agent's memory. Structure:

```json
{
  "last_run": "2026-03-21T16:00:00Z",
  "accounts": {
    "0010g00001j67uzaaq": {
      "customer_name": "4prime Sp Z O O",
      "status": "Sales Hold",
      "expiration_date": "...",
      "blockers": ["OIDC SSO (blocker)"],
      "last_seen": "2026-03-21T16:00:00Z"
    }
  }
}
```

On first run with no `state.json`: all 300 accounts are treated as new, generating an initial baseline without triggering tasks (bootstrap mode).

---

## 9. Roadmap

| Phase | Scope | Target |
|---|---|---|
| MVP | This spec — file watcher, Claude classifier, terminal approval, CSV output | Week 1-2 |
| v1 | Web approval dashboard (FastAPI), Okta SSO, per-user audit trail | Week 3-4 |
| v2 | AppSheet API write (replace manual CSV import), Drive API polling (replace manual export) | Month 2 |
| v3 | Cross-regional feeds (JAPAC, LATAM, NAM), consolidated dashboard, analytics | Month 3+ |

---

## 10. Out of Scope (MVP)

- AppSheet API authentication / direct write
- Google Drive API / real-time file monitoring
- Multi-user concurrent access
- Okta / SSO integration
- Email monitoring
- Cross-regional data (NAM, JAPAC, LATAM)
- Automated scheduling / cron (user runs manually or via /run-now)
