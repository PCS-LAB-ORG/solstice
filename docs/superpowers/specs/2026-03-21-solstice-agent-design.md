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
- Output: `pending_tasks.csv` ready for AppSheet manual import (appended, never overwritten mid-session)
- Wrapper: FastAPI with `/status` endpoint only; pipeline runs as a standalone CLI process
- Runs on: EMEA lead's local machine

Out of scope for MVP: AppSheet API write, Drive API polling, multi-user web UI, Okta auth, cross-regional feeds.

---

## 3. Data Model

### Source: EMEA Accounts CC Migrations - Accounts.csv

**Key identifier:** column 0 (account ID, e.g. `0010g00001j67uzaaq`)

**Tracked fields (all stored in state.json):**

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
| 14x blocker columns | boolean | See blocker constants below |

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

### Blocker Field Constants (14 fields)

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

| Category | Trigger | Pipeline stage | Default Priority |
|---|---|---|---|
| `ESCALATION` | Status changed to: Backoff / Sales Hold / Churning+Churned / Cancelled | differ.py (change-driven) | HIGH |
| `CUSTOMER_OUTREACH` | Status = Ready To Engage or Account team contacted AND `status_changed_at` > 14 days ago | differ.py (staleness check against state.json) | HIGH |
| `BLOCKER_REVIEW` | Any blocker column changed to a non-empty value | differ.py (change-driven) | MEDIUM |
| `STATUS_UPDATE` | Status changed (non-escalation path) | differ.py (change-driven) | MEDIUM |
| `PS_ENGAGEMENT` | PS Engaged changed OR Kickoff Date set OR status = Kick Off Scheduled | differ.py (change-driven) | MEDIUM |
| `EXPIRY_RISK` | Expiration date <= 30 days from scan date | differ.py (date-check pass, runs after diff, independent of changes) | HIGH |
| `UNCLASSIFIED` | Claude API failure during classification | classifier.py (error fallback) | HIGH |

`EXPIRY_RISK` runs as a separate pass in `differ.py` after the change-diff pass. It fires regardless of whether the account had other changes. Deduplication: on each scan, if `expiry_alerted_date == today's date`, the alert is suppressed for that account. If `expiry_alerted_date != today` (including null), the alert fires and `expiry_alerted_date` is set to today. This means the alert fires at most once per calendar day, repeating daily until the account expires or its status changes. `expiry_alerted_date` is never manually reset — it self-rearms each new day automatically.

`UNCLASSIFIED` tasks bypass the approver UI and are written directly to `pending_review.log` only — never to `pending_tasks.csv`. They require manual review.

`status_changed_at` in `state.json` is updated **only when a status change is detected in PASS 1**. If no status change is found for an account in a given scan, `status_changed_at` retains its previous value unchanged. This is the mechanism that makes the 14-day staleness check work correctly across multiple scans.

### Task Output Schema

Each approved task written to `pending_tasks.csv`:

```
account_id, customer_name, region, cse, category, priority,
suggested_action, old_value, new_value, detected_at
```

---

## 5. Architecture

### Runtime Model

The agent runs as a **standalone CLI process** (`python agent/main.py`), not inside uvicorn. A separate lightweight FastAPI process provides the `/status` endpoint only. The `/run-now` endpoint is removed from MVP to avoid blocking the event loop during interactive terminal approval.

```
python agent/main.py          <- blocking CLI process (watcher + pipeline + approval)
python agent/api.py           <- non-blocking FastAPI /status endpoint (separate process)
```

### Pipeline

```
User drops CSV export into Solstice/data/
        |
        v
[watcher.py] watchdog FileSystemEventHandler
detects new/modified CSV in data/ folder
        |
        v
[differ.py] PASS 1: load new CSV + state.json
compute per-account field diffs (changed fields, new accounts, status changes)
        |
[differ.py] PASS 2: date-check pass
flag accounts with expiration_date <= today + 30 days (not already alerted today)
        |
        v
[classifier.py] send diffs batch to Claude (Anthropic Vertex)
Input: list of change dicts (see Claude Integration section)
Output: list of {account_id, category, priority, suggested_action}
On API failure: log error, skip classification, write raw diffs to pending_review.log
        |
        v
[approver.py] Rich terminal UI (blocking, runs in main thread)
display each proposed task: account name, region, CSE, category, priority, suggested action
user: [A]pprove / [R]eject / [E]dit suggested_action / [S]kip all remaining
        |
        v
[writer.py] APPEND approved tasks to pending_tasks.csv (never overwrite)
update state.json: all tracked fields + status_changed_at + expiry_alerted_date
        |
        v
User imports pending_tasks.csv into AppSheet manually
```

### FastAPI Status API (api.py)

| Endpoint | Method | Purpose |
|---|---|---|
| `/status` | GET | Returns agent health, last run time, pending task count from state.json |

Runs on `localhost:8100`. Separate process from the CLI agent.

---

## 6. Claude Integration

### Input format (per account diff)

`classifier.py` sends a single batch request to Claude with all diffs from one scan:

```json
{
  "accounts": [
    {
      "account_id": "0010g00001j67uzaaq",
      "customer_name": "4prime Sp Z O O",
      "region": "CEE",
      "cse": "Tunde Adenugba",
      "changes": [
        {"field": "Status", "old": "Ready To Engage", "new": "Sales Hold"}
      ],
      "expiry_risk": false,
      "comments": "12/03: Sales advised of blocker..."
    }
  ]
}
```

### System prompt (constants.py)

```
You are a Prisma Cloud CC Migration task classifier for the EMEA team.
Classify each account change into exactly one category from: ESCALATION, CUSTOMER_OUTREACH,
BLOCKER_REVIEW, STATUS_UPDATE, PS_ENGAGEMENT, EXPIRY_RISK.
Assign priority: HIGH, MEDIUM, or LOW.
Write a one-sentence suggested_action in imperative form (e.g. "Escalate to regional manager — account moved to Sales Hold").
Return a JSON array only, no prose.
```

### Expected output schema

```json
[
  {
    "account_id": "0010g00001j67uzaaq",
    "category": "ESCALATION",
    "priority": "HIGH",
    "suggested_action": "Escalate to regional manager — account moved to Sales Hold."
  }
]
```

### Error handling

- If Vertex AI call fails (network, quota, timeout): log full error to `agent.log`, write affected accounts to `pending_review.log` with raw diff for manual review. Do not crash the pipeline — continue to approval with category = `UNCLASSIFIED`.
- Retry: one retry with 5s backoff before falling back.

---

## 7. File Structure

```
Solstice/
  data/
    EMEA Accounts CC Migrations - Accounts.csv   <- drop exports here
    state.json        <- auto-generated, last known state per account
    pending_tasks.csv <- output, AppSheet-ready (append mode)
    pending_review.log <- accounts skipped due to classifier failure
    agent.log         <- runtime log
  agent/
    main.py           <- CLI entry point (watcher + pipeline)
    api.py            <- FastAPI /status endpoint (separate process)
    watcher.py        <- watchdog file monitor
    differ.py         <- CSV diff engine + date-check pass
    classifier.py     <- Claude Vertex classification
    approver.py       <- Rich terminal approval UI
    writer.py         <- CSV output (append) + state update
    constants.py      <- all status/category/blocker/region enums + system prompt
  docs/
    superpowers/specs/
      2026-03-21-solstice-agent-design.md
  requirements.txt    <- pinned versions
  README.md
```

---

## 8. Tech Stack

| Component | Library | Pinned version |
|---|---|---|
| File watcher | `watchdog` | 6.0.0 |
| LLM | `anthropic[vertex]` | 0.49.0 |
| API wrapper | `fastapi` + `uvicorn` | 0.115.0 / 0.34.0 |
| Terminal UI | `rich` | 13.9.0 |
| Data handling | stdlib `csv` + `json` | — |

`requirements.txt` pins all versions above. `pip install -r requirements.txt` is the full setup.

LLM config (matches existing project):
- Project: `pa-sase-insights-tools`
- Region: `us-east5`
- Model: `claude-sonnet-4-6`
- Auth: ADC (gcloud, already active)

---

## 9. State Management

`state.json` is the agent's memory. All tracked fields are stored per account to enable full diff detection.

```json
{
  "last_run": "2026-03-21T16:00:00Z",
  "accounts": {
    "0010g00001j67uzaaq": {
      "customer_name": "4prime Sp Z O O",
      "arr": "",
      "active_cse": "Tunde Adenugba",
      "backup_cse": "",
      "status": "Sales Hold",
      "status_changed_at": "2026-03-07T00:00:00Z",
      "expiration_date": "12/31/26",
      "expiry_alerted_date": null,
      "ps_engaged": "",
      "kickoff_date": "",
      "comments": "12/03: Sales advised...",
      "sales_region": "CEE",
      "email_sent": "",
      "blockers": ["OIDC SSO (blocker)"],
      "last_seen": "2026-03-21T16:00:00Z"
    }
  }
}
```

### Bootstrap mode (first run, no state.json)

- All 300 accounts written to `state.json` with current CSV values
- `status_changed_at` set to today for all accounts (no staleness tasks on first run)
- No tasks generated — baseline only
- `pending_tasks.csv` is created empty (header row only)
- Message printed: `Bootstrap complete. 300 accounts loaded. Drop a new CSV to begin monitoring.`

### pending_tasks.csv behavior

- **Append mode**: new approved tasks are always appended, never overwritten
- User is responsible for archiving/clearing the file after AppSheet import
- On bootstrap: file created with header row only

---

## 10. Roadmap

| Phase | Scope | Target |
|---|---|---|
| MVP | This spec — file watcher, Claude classifier, terminal approval, CSV output | Week 1-2 |
| v1 | Web approval dashboard (FastAPI), Okta SSO, per-user audit trail, /run-now endpoint | Week 3-4 |
| v2 | AppSheet API write (replace manual CSV import), Drive API polling (replace manual export) | Month 2 |
| v3 | Cross-regional feeds (JAPAC, LATAM, NAM), consolidated dashboard, analytics | Month 3+ |

---

## 11. Out of Scope (MVP)

- AppSheet API authentication / direct write
- Google Drive API / real-time file monitoring
- Multi-user concurrent access
- Okta / SSO integration
- Email monitoring
- Cross-regional data (NAM, JAPAC, LATAM)
- `/run-now` HTTP endpoint (deferred to v1 — blocks event loop during interactive approval)
- Automated scheduling / cron (user runs `python agent/main.py` manually)
