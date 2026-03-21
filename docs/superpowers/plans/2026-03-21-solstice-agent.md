# Solstice Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python agent that watches a CSV export of 300 EMEA Prisma Cloud migration accounts, classifies changes using Claude, routes them through a terminal approval step, and appends approved tasks to a CSV for manual AppSheet import.

**Architecture:** A standalone CLI process (`main.py`) orchestrates: watchdog file monitor → CSV differ → Claude Vertex classifier → Rich terminal approval → CSV/state writer. A separate lightweight FastAPI process (`api.py`) provides a `/status` health endpoint. No database — state lives in `data/state.json`.

**Tech Stack:** Python 3.9+, watchdog 6.0.0, anthropic[vertex] 0.49.0, fastapi 0.115.0, uvicorn 0.34.0, rich 13.9.0, pytest

**Spec:** `docs/superpowers/specs/2026-03-21-solstice-agent-design.md`

---

## File Map

| File | Responsibility |
|---|---|
| `agent/constants.py` | All enums, CSV column mappings, system prompt — single source of truth |
| `agent/differ.py` | Parse CSV rows → account dicts; diff new CSV vs state.json (PASS 1 + PASS 2) |
| `agent/classifier.py` | Send diffs to Claude Vertex; parse response; handle errors with retry |
| `agent/approver.py` | Rich terminal UI: display task, collect [A]/[R]/[E]/[S] decision |
| `agent/writer.py` | Append approved tasks to `pending_tasks.csv`; update `state.json`; log UNCLASSIFIED |
| `agent/watcher.py` | watchdog FileSystemEventHandler; triggers pipeline on CSV drop |
| `agent/main.py` | Entry point: bootstrap detection, starts watcher, orchestrates pipeline |
| `agent/api.py` | FastAPI `/status` GET — reads state.json, returns health dict |
| `tests/test_constants.py` | Verify constant values and counts |
| `tests/test_differ.py` | Diff logic with fixture CSVs and state dicts |
| `tests/test_classifier.py` | Mocked Claude calls; retry logic; UNCLASSIFIED fallback |
| `tests/test_approver.py` | Mocked input; approve/reject/edit/skip flows |
| `tests/test_writer.py` | File I/O: append behavior, state update, bootstrap output |
| `tests/conftest.py` | Shared fixtures: sample CSV rows, state dicts, diff results |

---

## Task 1: Scaffold — Project Structure and Dependencies

**Files:**
- Create: `Solstice/requirements.txt`
- Create: `Solstice/pytest.ini`
- Create: `Solstice/agent/__init__.py`
- Create: `Solstice/tests/__init__.py`
- Create: `Solstice/tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
# Solstice/requirements.txt
watchdog==6.0.0
anthropic[vertex]==0.49.0
fastapi==0.115.0
uvicorn==0.34.0
rich==13.9.0
pytest==8.3.5
httpx==0.28.1
```

- [ ] **Step 2: Create pytest.ini**

```ini
# Solstice/pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 3: Create package init files**

```python
# Solstice/agent/__init__.py
# (empty)

# Solstice/tests/__init__.py
# (empty)
```

- [ ] **Step 4: Create conftest.py with shared fixtures**

```python
# Solstice/tests/conftest.py
import pytest
from datetime import date, timedelta

SAMPLE_ACCOUNT_ID = "0010g00001j67uzaaq"

SAMPLE_CSV_ROW = {
    "account_id": SAMPLE_ACCOUNT_ID,
    "customer_name": "Acme Corp",
    "arr": "50000",
    "active_cse": "Tunde Adenugba",
    "backup_cse": "",
    "status": "Ready To Engage",
    "sales_region": "CEE",
    "comments": "Test comment",
    "expiration_date": "",
    "ps_engaged": "",
    "kickoff_date": "",
    "email_sent": "",
    "blockers": [],
}

SAMPLE_STATE_ACCOUNT = {
    "customer_name": "Acme Corp",
    "arr": "50000",
    "active_cse": "Tunde Adenugba",
    "backup_cse": "",
    "status": "Ready To Engage",
    "status_changed_at": (date.today() - timedelta(days=20)).isoformat() + "T00:00:00Z",
    "expiration_date": "",
    "expiry_alerted_date": None,
    "ps_engaged": "",
    "kickoff_date": "",
    "comments": "Test comment",
    "sales_region": "CEE",
    "email_sent": "",
    "blockers": [],
    "last_seen": "2026-03-21T16:00:00Z",
}

@pytest.fixture
def sample_csv_row():
    return dict(SAMPLE_CSV_ROW)

@pytest.fixture
def sample_state_account():
    return dict(SAMPLE_STATE_ACCOUNT)

@pytest.fixture
def sample_state(sample_state_account):
    return {
        "last_run": "2026-03-21T16:00:00Z",
        "accounts": {SAMPLE_ACCOUNT_ID: sample_state_account},
    }
```

- [ ] **Step 5: Install dependencies**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pip3 install -r requirements.txt
```

Expected: All packages install without error.

- [ ] **Step 6: Verify pytest discovers tests**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest --collect-only
```

Expected: `no tests ran` (no test files yet — this is correct).

- [ ] **Step 7: Commit**

```bash
git add Solstice/requirements.txt Solstice/pytest.ini Solstice/agent/__init__.py Solstice/tests/__init__.py Solstice/tests/conftest.py
git commit -m "chore: scaffold Solstice agent project structure"
```

---

## Task 2: constants.py — All Enums, Column Mappings, System Prompt

**Files:**
- Create: `Solstice/agent/constants.py`
- Create: `Solstice/tests/test_constants.py`

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_constants.py
from agent.constants import (
    STATUSES, REGIONS, BLOCKER_COLS, ESCALATION_STATUSES,
    OUTREACH_STATUSES, TASK_CATEGORIES, CSV_COL_ACCOUNT_ID,
    CSV_COL_STATUS, CSV_COL_SALES_REGION, CSV_COL_EXPIRATION_DATE,
    CSV_COL_KICKOFF_DATE, SYSTEM_PROMPT, DATA_DIR,
)

def test_status_count():
    assert len(STATUSES) == 15

def test_region_count():
    assert len(REGIONS) == 11

def test_blocker_col_count():
    assert len(BLOCKER_COLS) == 14

def test_escalation_statuses_subset_of_statuses():
    for s in ESCALATION_STATUSES:
        assert s in STATUSES

def test_outreach_statuses_subset_of_statuses():
    for s in OUTREACH_STATUSES:
        assert s in STATUSES

def test_task_categories_contains_unclassified():
    assert "UNCLASSIFIED" in TASK_CATEGORIES

def test_task_categories_count():
    assert len(TASK_CATEGORIES) == 7

def test_account_id_col_is_index_zero():
    assert CSV_COL_ACCOUNT_ID == 0

def test_kickoff_date_col_has_newline():
    assert "\n" in CSV_COL_KICKOFF_DATE

def test_system_prompt_lists_six_classifiable_categories():
    for cat in ["ESCALATION", "CUSTOMER_OUTREACH", "BLOCKER_REVIEW",
                "STATUS_UPDATE", "PS_ENGAGEMENT", "EXPIRY_RISK"]:
        assert cat in SYSTEM_PROMPT

def test_data_dir_points_to_data_folder():
    assert str(DATA_DIR).endswith("data")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_constants.py -v
```

Expected: `ImportError: cannot import name 'STATUSES' from 'agent.constants'`

- [ ] **Step 3: Implement constants.py**

```python
# Solstice/agent/constants.py
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
PENDING_TASKS_FILE = DATA_DIR / "pending_tasks.csv"
PENDING_REVIEW_LOG = DATA_DIR / "pending_review.log"
AGENT_LOG = DATA_DIR / "agent.log"

# --- CSV Column Mapping (by index, not name — headers are non-standard) ---
# Column 0 header is '\xa0\xa0' (non-breaking spaces) — use index
CSV_COL_ACCOUNT_ID = 0          # e.g. 0010g00001j67uzaaq
CSV_COL_CUSTOMER_NAME = 1       # "Customer name"
CSV_COL_ARR = 2                 # "ARR"
CSV_COL_ACTIVE_CSE = 3          # "Active CSE (s)"
CSV_COL_BACKUP_CSE = 4          # "Irene Backup CSE"
CSV_COL_STATUS = 5              # "Status"
CSV_COL_SALES_REGION = 10       # "Sales region"
CSV_COL_COMMENTS = 12           # "Comments"
CSV_COL_EXPIRATION_DATE = 13    # "Expiration date"
CSV_COL_PS_ENGAGED = 36         # "PS Engaged"
CSV_COL_KICKOFF_DATE = 35       # "Kickoff\nDate"
CSV_COL_EMAIL_SENT = 41         # "Email Sent"

# Blocker column indices (16-30)
BLOCKER_COL_INDICES = [16, 17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]
BLOCKER_COLS = [
    "APIs usage / custom integrations / scripts (blocker)",
    "BYOK required?",
    "AgentiX required?",
    "Alibaba or IBM (blocker)",
    "OIDC SSO (blocker)",
    "Custom Compliance (blocker)",
    "Unsupported \nNotifications/Integrations (blocker)",
    "Terraform (provider&onboarding) (blocker)",
    "Agentless AKS/EKS in auto-mode (blocker)",
    "serverless with layers from different accounts (blocker)",
    "serverless runtime protection (blocker)",
    "serverless without internet connection (blocker)",
    "Linux Functions without External Package URL (blocker)",
    "app-embeded protection capabilities (blocker)",
]
assert len(BLOCKER_COL_INDICES) == len(BLOCKER_COLS) == 14

# --- Domain Constants ---
STATUSES = [
    "Ready To Engage",
    "Account team contacted",
    "Upgrade Email Sent",
    "Kick Off Scheduled",
    "Customer Engaged",
    "In Progress",
    "Customer Acceptance",
    "PS",
    "Completed",
    "On Hold",
    "Backoff",
    "Sales Hold",
    "Blocked: Tech limitation",
    "Churning/Churned",
    "Cancelled",
]

REGIONS = [
    "Alps", "Benelux", "CEE", "France", "Germany",
    "Gulf/North Africa", "Nordics", "SEUR", "Saudi/LBS",
    "Turkey/SA", "UKI",
]

TASK_CATEGORIES = [
    "ESCALATION",
    "CUSTOMER_OUTREACH",
    "BLOCKER_REVIEW",
    "STATUS_UPDATE",
    "PS_ENGAGEMENT",
    "EXPIRY_RISK",
    "UNCLASSIFIED",
]

ESCALATION_STATUSES = ["Backoff", "Sales Hold", "Churning/Churned", "Cancelled"]
OUTREACH_STATUSES = ["Ready To Engage", "Account team contacted"]

CUSTOMER_OUTREACH_STALE_DAYS = 14
EXPIRY_RISK_DAYS = 30

# --- Claude Config ---
VERTEX_PROJECT = "pa-sase-insights-tools"
VERTEX_REGION = "us-east5"
VERTEX_MODEL = "claude-sonnet-4-6"
CLASSIFIER_MAX_TOKENS = 1024
CLASSIFIER_RETRY_DELAY_S = 5

SYSTEM_PROMPT = (
    "You are a Prisma Cloud CC Migration task classifier for the EMEA team.\n"
    "Classify each account change into exactly one category from: "
    "ESCALATION, CUSTOMER_OUTREACH, BLOCKER_REVIEW, STATUS_UPDATE, PS_ENGAGEMENT, EXPIRY_RISK.\n"
    "Assign priority: HIGH, MEDIUM, or LOW.\n"
    "Write a one-sentence suggested_action in imperative form "
    "(e.g. \"Escalate to regional manager — account moved to Sales Hold\").\n"
    "Return a JSON array only, no prose."
)

# --- Output CSV Header ---
PENDING_TASKS_HEADER = [
    "account_id", "customer_name", "region", "cse", "category",
    "priority", "suggested_action", "old_value", "new_value", "detected_at",
]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_constants.py -v
```

Expected: 11 PASSED

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/constants.py Solstice/tests/test_constants.py
git commit -m "feat: constants.py — all enums, CSV column map, Claude config"
```

---

## Task 3: differ.py — CSV Parser and Diff Engine

**Files:**
- Create: `Solstice/agent/differ.py`
- Create: `Solstice/tests/test_differ.py`

The differ has two jobs:
- `parse_csv(filepath)` → list of account dicts, keyed by account_id
- `compute_diffs(new_accounts, state)` → list of diff dicts (PASS 1: field changes + PASS 2: expiry check)

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_differ.py
import csv, io, json, tempfile, os
from datetime import date, timedelta
from pathlib import Path
import pytest
from agent.differ import parse_csv, compute_diffs

SAMPLE_ACCOUNT_ID = "0010g00001j67uzaaq"

def make_csv_file(rows_by_index: dict) -> Path:
    """Create a temp CSV with exact column layout matching real file."""
    # 43 columns total; fill with empty strings, override by index
    header = ['\xa0\xa0'] + [
        'Customer name', 'ARR', 'Active CSE (s)', 'Irene Backup CSE', 'Status',
        'Live-fire', 'Live-Fire DC assigned', 'Acct Team (sales rep)',
        'Acct Team (DCs in that region)', 'Sales region', 'Account Territory Area',
        'Comments', 'Expiration date', 'Existing Cortex customer?', 'Custom Policies',
        'APIs usage / custom integrations / scripts (blocker)', 'BYOK required?',
        'AgentiX required?', 'CSP', 'Alibaba or IBM (blocker)', 'OIDC SSO (blocker)',
        'Custom Compliance (blocker)', 'Unsupported \nNotifications/Integrations (blocker)',
        'Terraform (provider&onboarding) (blocker)', 'Agentless AKS/EKS in auto-mode (blocker)',
        'serverless with layers from different accounts (blocker)',
        'serverless runtime protection (blocker)',
        'serverless without internet connection (blocker)',
        'Linux Functions without External Package URL (blocker)',
        'app-embeded protection capabilities (blocker)',
        'Entitlements - Email ID', 'activation_tenant_status', 'xdr_id', 'SSO Configured',
        'Kickoff\nDate', 'PS Engaged', 'Module', '#SFDC', '#XSUP', 'Customer size',
        'Email Sent', 'Email Subject',
    ]
    row = [''] * 43
    for idx, val in rows_by_index.items():
        row[idx] = val

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='')
    writer = csv.writer(tmp)
    writer.writerow(header)
    writer.writerow(row)
    tmp.close()
    return Path(tmp.name)


def test_parse_csv_returns_account_dict():
    f = make_csv_file({0: SAMPLE_ACCOUNT_ID, 1: "Acme", 5: "Ready To Engage", 10: "CEE"})
    try:
        accounts = parse_csv(f)
        assert SAMPLE_ACCOUNT_ID in accounts
        assert accounts[SAMPLE_ACCOUNT_ID]["customer_name"] == "Acme"
        assert accounts[SAMPLE_ACCOUNT_ID]["status"] == "Ready To Engage"
        assert accounts[SAMPLE_ACCOUNT_ID]["sales_region"] == "CEE"
    finally:
        os.unlink(f)


def test_parse_csv_skips_rows_with_empty_account_id():
    f = make_csv_file({0: "", 1: "Ghost"})
    try:
        accounts = parse_csv(f)
        assert len(accounts) == 0
    finally:
        os.unlink(f)


def test_parse_csv_extracts_active_blockers():
    f = make_csv_file({0: SAMPLE_ACCOUNT_ID, 17: "Yes"})  # BYOK required?
    try:
        accounts = parse_csv(f)
        assert "BYOK required?" in accounts[SAMPLE_ACCOUNT_ID]["blockers"]
    finally:
        os.unlink(f)


def test_compute_diffs_detects_status_change(sample_csv_row, sample_state):
    new = {SAMPLE_ACCOUNT_ID: {**sample_csv_row, "status": "Sales Hold"}}
    diffs = compute_diffs(new, sample_state)
    assert len(diffs) == 1
    assert diffs[0]["account_id"] == SAMPLE_ACCOUNT_ID
    assert any(c["field"] == "Status" and c["new"] == "Sales Hold" for c in diffs[0]["changes"])


def test_compute_diffs_escalation_flag(sample_csv_row, sample_state):
    new = {SAMPLE_ACCOUNT_ID: {**sample_csv_row, "status": "Backoff"}}
    diffs = compute_diffs(new, sample_state)
    assert diffs[0]["escalation"] is True


def test_compute_diffs_no_change_produces_no_diff(sample_csv_row, sample_state):
    # status_changed_at is 20 days ago in conftest, status = Ready To Engage
    # → stale_outreach fires but no field changes exist
    new = {SAMPLE_ACCOUNT_ID: sample_csv_row}
    diffs = compute_diffs(new, sample_state)
    # stale_outreach diff should fire (20 days > 14 day threshold)
    stale = [d for d in diffs if d.get("stale_outreach")]
    assert len(stale) == 1, "Expected stale_outreach to fire for 20-day-old Ready To Engage status"
    # No other (non-stale) diffs should exist
    non_stale = [d for d in diffs if not d.get("stale_outreach")]
    assert len(non_stale) == 0


def test_compute_diffs_expiry_risk_fires_when_within_30_days(sample_csv_row, sample_state):
    soon = (date.today() + timedelta(days=15)).strftime("%m/%d/%y")
    sample_state["accounts"][SAMPLE_ACCOUNT_ID]["expiry_alerted_date"] = None
    new = {SAMPLE_ACCOUNT_ID: {**sample_csv_row, "expiration_date": soon}}
    diffs = compute_diffs(new, sample_state)
    assert any(d.get("expiry_risk") for d in diffs)


def test_compute_diffs_expiry_risk_suppressed_if_alerted_today(sample_csv_row, sample_state):
    soon = (date.today() + timedelta(days=15)).strftime("%m/%d/%y")
    sample_state["accounts"][SAMPLE_ACCOUNT_ID]["expiry_alerted_date"] = date.today().isoformat()
    new = {SAMPLE_ACCOUNT_ID: {**sample_csv_row, "expiration_date": soon}}
    diffs = compute_diffs(new, sample_state)
    assert not any(d.get("expiry_risk") for d in diffs)


def test_compute_diffs_customer_outreach_stale(sample_csv_row, sample_state):
    # conftest sets status_changed_at = 20 days ago, status = Ready To Engage
    new = {SAMPLE_ACCOUNT_ID: sample_csv_row}
    diffs = compute_diffs(new, sample_state)
    assert any(d.get("stale_outreach") for d in diffs)


def test_compute_diffs_new_account_no_state():
    new_id = "newaccount123"
    new = {new_id: {
        "account_id": new_id, "customer_name": "New Co", "arr": "",
        "active_cse": "", "backup_cse": "", "status": "Ready To Engage",
        "sales_region": "UKI", "comments": "", "expiration_date": "",
        "ps_engaged": "", "kickoff_date": "", "email_sent": "", "blockers": [],
    }}
    diffs = compute_diffs(new, {"last_run": "", "accounts": {}})
    assert len(diffs) == 1
    assert diffs[0]["account_id"] == new_id
    assert diffs[0]["new_account"] is True
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_differ.py -v
```

Expected: `ImportError: cannot import name 'parse_csv' from 'agent.differ'`

- [ ] **Step 3: Implement differ.py**

```python
# Solstice/agent/differ.py
from __future__ import annotations
import csv
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Any, Optional

from agent.constants import (
    CSV_COL_ACCOUNT_ID, CSV_COL_CUSTOMER_NAME, CSV_COL_ARR,
    CSV_COL_ACTIVE_CSE, CSV_COL_BACKUP_CSE, CSV_COL_STATUS,
    CSV_COL_SALES_REGION, CSV_COL_COMMENTS, CSV_COL_EXPIRATION_DATE,
    CSV_COL_PS_ENGAGED, CSV_COL_KICKOFF_DATE, CSV_COL_EMAIL_SENT,
    BLOCKER_COL_INDICES, BLOCKER_COLS,
    ESCALATION_STATUSES, OUTREACH_STATUSES,
    CUSTOMER_OUTREACH_STALE_DAYS, EXPIRY_RISK_DAYS,
)


def _parse_row(row: list[str]) -> Optional[dict[str, Any]]:
    """Convert a raw CSV row (list of strings) into an account dict. Returns None if no account_id."""
    account_id = row[CSV_COL_ACCOUNT_ID].strip()
    if not account_id:
        return None
    active_blockers = [
        BLOCKER_COLS[i]
        for i, col_idx in enumerate(BLOCKER_COL_INDICES)
        if col_idx < len(row) and row[col_idx].strip()
    ]
    return {
        "account_id": account_id,
        "customer_name": row[CSV_COL_CUSTOMER_NAME].strip() if CSV_COL_CUSTOMER_NAME < len(row) else "",
        "arr": row[CSV_COL_ARR].strip() if CSV_COL_ARR < len(row) else "",
        "active_cse": row[CSV_COL_ACTIVE_CSE].strip() if CSV_COL_ACTIVE_CSE < len(row) else "",
        "backup_cse": row[CSV_COL_BACKUP_CSE].strip() if CSV_COL_BACKUP_CSE < len(row) else "",
        "status": row[CSV_COL_STATUS].strip() if CSV_COL_STATUS < len(row) else "",
        "sales_region": row[CSV_COL_SALES_REGION].strip() if CSV_COL_SALES_REGION < len(row) else "",
        "comments": row[CSV_COL_COMMENTS].strip() if CSV_COL_COMMENTS < len(row) else "",
        "expiration_date": row[CSV_COL_EXPIRATION_DATE].strip() if CSV_COL_EXPIRATION_DATE < len(row) else "",
        "ps_engaged": row[CSV_COL_PS_ENGAGED].strip() if CSV_COL_PS_ENGAGED < len(row) else "",
        "kickoff_date": row[CSV_COL_KICKOFF_DATE].strip() if CSV_COL_KICKOFF_DATE < len(row) else "",
        "email_sent": row[CSV_COL_EMAIL_SENT].strip() if CSV_COL_EMAIL_SENT < len(row) else "",
        "blockers": active_blockers,
    }


def parse_csv(filepath: Path) -> dict[str, dict]:
    """Parse a CSV export. Returns {account_id: account_dict}."""
    accounts = {}
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            parsed = _parse_row(row)
            if parsed:
                accounts[parsed["account_id"]] = parsed
    return accounts


def _parse_expiry_date(date_str: str) -> date | None:
    """Parse MM/DD/YY or MM/DD/YYYY expiration dates."""
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


TRACKED_FIELDS = [
    ("status", "Status"),
    ("customer_name", "Customer name"),
    ("arr", "ARR"),
    ("active_cse", "Active CSE"),
    ("backup_cse", "Backup CSE"),
    ("sales_region", "Sales region"),
    ("expiration_date", "Expiration date"),
    ("ps_engaged", "PS Engaged"),
    ("kickoff_date", "Kickoff Date"),
    ("email_sent", "Email Sent"),
    ("comments", "Comments"),
]


def compute_diffs(new_accounts: dict, state: dict) -> list[dict]:
    """
    PASS 1: compare new_accounts vs state["accounts"] — detect field changes.
    PASS 2: date-check — flag expiry risk (independent of changes).
    Returns list of diff dicts for classifier.
    """
    state_accounts = state.get("accounts", {})
    today = date.today()
    diffs = []

    for account_id, new in new_accounts.items():
        prev = state_accounts.get(account_id)
        diff = {
            "account_id": account_id,
            "customer_name": new["customer_name"],
            "region": new["sales_region"],
            "cse": new["active_cse"],
            "changes": [],
            "escalation": False,
            "stale_outreach": False,
            "expiry_risk": False,
            "new_account": prev is None,
            "comments": new["comments"],
        }

        # PASS 1: field diffs
        if prev is None:
            # new account — treat as STATUS_UPDATE
            diff["changes"].append({"field": "Status", "old": None, "new": new["status"]})
        else:
            for field_key, field_label in TRACKED_FIELDS:
                old_val = prev.get(field_key, "")
                new_val = new.get(field_key, "")
                if old_val != new_val:
                    diff["changes"].append({"field": field_label, "old": old_val, "new": new_val})

            # blocker changes
            old_blockers = set(prev.get("blockers", []))
            new_blockers = set(new.get("blockers", []))
            for b in new_blockers - old_blockers:
                diff["changes"].append({"field": "Blocker", "old": None, "new": b})

            # escalation flag
            if new["status"] in ESCALATION_STATUSES and prev.get("status") != new["status"]:
                diff["escalation"] = True

            # CUSTOMER_OUTREACH staleness (checked even without field changes)
            if new["status"] in OUTREACH_STATUSES:
                changed_at_str = prev.get("status_changed_at", "")
                if changed_at_str:
                    try:
                        changed_at = datetime.fromisoformat(changed_at_str.replace("Z", "+00:00")).date()
                        if (today - changed_at).days > CUSTOMER_OUTREACH_STALE_DAYS:
                            diff["stale_outreach"] = True
                    except ValueError:
                        pass

        # PASS 2: expiry risk (independent of changes)
        expiry_date = _parse_expiry_date(new.get("expiration_date", ""))
        if expiry_date:
            alerted_today_str = (prev or {}).get("expiry_alerted_date")
            alerted_today = alerted_today_str == today.isoformat() if alerted_today_str else False
            if not alerted_today and (expiry_date - today).days <= EXPIRY_RISK_DAYS:
                diff["expiry_risk"] = True

        # Only include accounts with something to act on
        if diff["changes"] or diff["stale_outreach"] or diff["expiry_risk"]:
            diffs.append(diff)

    return diffs
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_differ.py -v
```

Expected: All tests PASSED

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/differ.py Solstice/tests/test_differ.py
git commit -m "feat: differ.py — CSV parser + diff engine (PASS 1 + PASS 2)"
```

---

## Task 4: classifier.py — Claude Vertex Classification

**Files:**
- Create: `Solstice/agent/classifier.py`
- Create: `Solstice/tests/test_classifier.py`

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_classifier.py
import json
from unittest.mock import MagicMock, patch
import pytest
from agent.classifier import classify_diffs, _build_message

SAMPLE_DIFF = {
    "account_id": "abc123",
    "customer_name": "Acme Corp",
    "region": "CEE",
    "cse": "Tunde",
    "changes": [{"field": "Status", "old": "Ready To Engage", "new": "Sales Hold"}],
    "escalation": True,
    "stale_outreach": False,
    "expiry_risk": False,
    "new_account": False,
    "comments": "",
}

CLAUDE_RESPONSE = json.dumps([{
    "account_id": "abc123",
    "category": "ESCALATION",
    "priority": "HIGH",
    "suggested_action": "Escalate to regional manager.",
}])


def mock_client(response_text):
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def test_build_message_includes_account_id():
    msg = _build_message([SAMPLE_DIFF])
    assert "abc123" in msg


def test_build_message_is_valid_json():
    msg = _build_message([SAMPLE_DIFF])
    parsed = json.loads(msg)
    assert "accounts" in parsed
    assert parsed["accounts"][0]["account_id"] == "abc123"


def test_classify_diffs_returns_classification():
    with patch("agent.classifier._get_client", return_value=mock_client(CLAUDE_RESPONSE)):
        results = classify_diffs([SAMPLE_DIFF])
    assert len(results) == 1
    assert results[0]["account_id"] == "abc123"
    assert results[0]["category"] == "ESCALATION"
    assert results[0]["priority"] == "HIGH"
    assert "suggested_action" in results[0]


def test_classify_diffs_retries_on_failure():
    fail_client = MagicMock()
    fail_client.messages.create.side_effect = [
        Exception("network error"),
        MagicMock(content=[MagicMock(text=CLAUDE_RESPONSE)]),
    ]
    with patch("agent.classifier._get_client", return_value=fail_client):
        with patch("agent.classifier.time.sleep"):  # don't actually sleep in tests
            results = classify_diffs([SAMPLE_DIFF])
    assert fail_client.messages.create.call_count == 2
    assert results[0]["category"] == "ESCALATION"


def test_classify_diffs_returns_unclassified_after_two_failures():
    fail_client = MagicMock()
    fail_client.messages.create.side_effect = Exception("always fails")
    with patch("agent.classifier._get_client", return_value=fail_client):
        with patch("agent.classifier.time.sleep"):
            results = classify_diffs([SAMPLE_DIFF])
    assert results[0]["category"] == "UNCLASSIFIED"
    assert results[0]["account_id"] == "abc123"


def test_classify_diffs_handles_invalid_json_response():
    with patch("agent.classifier._get_client", return_value=mock_client("not json at all")):
        with patch("agent.classifier.time.sleep"):
            results = classify_diffs([SAMPLE_DIFF])
    assert results[0]["category"] == "UNCLASSIFIED"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_classifier.py -v
```

Expected: `ImportError: cannot import name 'classify_diffs' from 'agent.classifier'`

- [ ] **Step 3: Implement classifier.py**

```python
# Solstice/agent/classifier.py
import json
import logging
import time
from typing import Any

from agent.constants import (
    VERTEX_PROJECT, VERTEX_REGION, VERTEX_MODEL,
    CLASSIFIER_MAX_TOKENS, CLASSIFIER_RETRY_DELAY_S, SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def _get_client():
    from anthropic import AnthropicVertex
    return AnthropicVertex(project_id=VERTEX_PROJECT, region=VERTEX_REGION)


def _build_message(diffs: list[dict]) -> str:
    """Serialize diffs into the JSON string sent to Claude."""
    accounts = []
    for d in diffs:
        accounts.append({
            "account_id": d["account_id"],
            "customer_name": d["customer_name"],
            "region": d["region"],
            "cse": d["cse"],
            "changes": d["changes"],
            "expiry_risk": d.get("expiry_risk", False),
            "stale_outreach": d.get("stale_outreach", False),
            "comments": d.get("comments", "")[:500],  # truncate long comments
        })
    return json.dumps({"accounts": accounts})


def _unclassified_results(diffs: list[dict]) -> list[dict]:
    return [
        {
            "account_id": d["account_id"],
            "category": "UNCLASSIFIED",
            "priority": "HIGH",
            "suggested_action": "Manual review required — classifier failed.",
        }
        for d in diffs
    ]


def classify_diffs(diffs: list[dict]) -> list[dict[str, Any]]:
    """
    Send diffs to Claude Vertex. Returns list of classification dicts.
    One retry with CLASSIFIER_RETRY_DELAY_S backoff. Falls back to UNCLASSIFIED on failure.
    """
    if not diffs:
        return []

    client = _get_client()
    message_content = _build_message(diffs)

    for attempt in range(2):
        try:
            response = client.messages.create(
                model=VERTEX_MODEL,
                max_tokens=CLASSIFIER_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": message_content}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            results = json.loads(raw)
            if not isinstance(results, list):
                raise ValueError("Expected JSON array from Claude")
            return results
        except Exception as e:
            logger.error("Classifier attempt %d failed: %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(CLASSIFIER_RETRY_DELAY_S)

    logger.error("Classifier failed after 2 attempts — returning UNCLASSIFIED for %d accounts", len(diffs))
    return _unclassified_results(diffs)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_classifier.py -v
```

Expected: All tests PASSED

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/classifier.py Solstice/tests/test_classifier.py
git commit -m "feat: classifier.py — Claude Vertex batch classification + retry + UNCLASSIFIED fallback"
```

---

## Task 5: approver.py — Rich Terminal Approval UI

**Files:**
- Create: `Solstice/agent/approver.py`
- Create: `Solstice/tests/test_approver.py`

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_approver.py
from unittest.mock import patch
import pytest
from agent.approver import run_approval

TASK = {
    "account_id": "abc123",
    "customer_name": "Acme Corp",
    "region": "CEE",
    "cse": "Tunde",
    "category": "ESCALATION",
    "priority": "HIGH",
    "suggested_action": "Escalate to regional manager.",
    "old_value": "Ready To Engage",
    "new_value": "Sales Hold",
    "detected_at": "2026-03-21T16:00:00Z",
}


def test_approve_task_returns_task_unchanged():
    with patch("agent.approver.Prompt.ask", return_value="a"):
        approved, skipped = run_approval([TASK])
    assert len(approved) == 1
    assert approved[0]["account_id"] == "abc123"
    assert skipped == 0


def test_reject_task_returns_empty():
    with patch("agent.approver.Prompt.ask", return_value="r"):
        approved, skipped = run_approval([TASK])
    assert len(approved) == 0
    assert skipped == 0


def test_edit_task_updates_suggested_action():
    with patch("agent.approver.Prompt.ask", side_effect=["e", "My custom action"]):
        approved, skipped = run_approval([TASK])
    assert len(approved) == 1
    assert approved[0]["suggested_action"] == "My custom action"


def test_skip_all_returns_remaining_as_skipped():
    tasks = [TASK, {**TASK, "account_id": "xyz456"}]
    responses = ["a", "s"]  # approve first, skip rest
    with patch("agent.approver.Prompt.ask", side_effect=responses):
        approved, skipped = run_approval(tasks)
    assert len(approved) == 1
    assert skipped == 1


def test_empty_task_list_returns_immediately():
    approved, skipped = run_approval([])
    assert approved == []
    assert skipped == 0


def test_case_insensitive_input():
    with patch("agent.approver.Prompt.ask", return_value="A"):
        approved, skipped = run_approval([TASK])
    assert len(approved) == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_approver.py -v
```

Expected: `ImportError: cannot import name 'run_approval' from 'agent.approver'`

- [ ] **Step 3: Implement approver.py**

```python
# Solstice/agent/approver.py
from datetime import datetime, timezone
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich import box

console = Console()

PRIORITY_COLOR = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}
CATEGORY_COLOR = {
    "ESCALATION": "bold red",
    "CUSTOMER_OUTREACH": "orange1",
    "BLOCKER_REVIEW": "yellow",
    "STATUS_UPDATE": "cyan",
    "PS_ENGAGEMENT": "blue",
    "EXPIRY_RISK": "magenta",
    "UNCLASSIFIED": "white",
}


def _display_task(task: dict, idx: int, total: int) -> None:
    color = PRIORITY_COLOR.get(task["priority"], "white")
    cat_color = CATEGORY_COLOR.get(task["category"], "white")

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Field", style="dim", width=20)
    table.add_column("Value")
    table.add_row("Account", f"[bold]{task['customer_name']}[/bold] ({task['account_id']})")
    table.add_row("Region / CSE", f"{task['region']} / {task['cse']}")
    table.add_row("Category", f"[{cat_color}]{task['category']}[/{cat_color}]")
    table.add_row("Priority", f"[{color}]{task['priority']}[/{color}]")
    table.add_row("Change", f"{task.get('old_value', '—')} → {task.get('new_value', '—')}")
    table.add_row("Suggested action", f"[italic]{task['suggested_action']}[/italic]")

    console.print(Panel(
        table,
        title=f"[bold]Task {idx}/{total}[/bold]",
        border_style=color,
    ))


def run_approval(tasks: list[dict]) -> tuple[list[dict], int]:
    """
    Interactive terminal approval loop.
    Returns (approved_tasks, skipped_count).
    """
    if not tasks:
        return [], 0

    approved = []
    skipped = 0
    total = len(tasks)

    for i, task in enumerate(tasks, start=1):
        _display_task(task, i, total)

        choice = Prompt.ask(
            "[bold][A][/bold]pprove  [bold][R][/bold]eject  [bold][E][/bold]dit  [bold][S][/bold]kip all",
            default="a",
        ).strip().lower()

        if choice == "a":
            approved.append(task)
        elif choice == "r":
            console.print("[dim]Rejected.[/dim]")
        elif choice == "e":
            new_action = Prompt.ask("New suggested action")
            approved.append({**task, "suggested_action": new_action})
        elif choice == "s":
            skipped = total - i + 1  # current task + all remaining
            console.print(f"[dim]Skipping {skipped} remaining task(s).[/dim]")
            break

    console.print(f"\n[green]Approved: {len(approved)}[/green]  "
                  f"[dim]Skipped: {skipped}[/dim]")
    return approved, skipped
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_approver.py -v
```

Expected: All tests PASSED

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/approver.py Solstice/tests/test_approver.py
git commit -m "feat: approver.py — Rich terminal approval UI (approve/reject/edit/skip)"
```

---

## Task 6: writer.py — CSV Output and State Update

**Files:**
- Create: `Solstice/agent/writer.py`
- Create: `Solstice/tests/test_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_writer.py
import csv, json, tempfile, os
from pathlib import Path
from datetime import date
import pytest
from agent.writer import (
    write_approved_tasks, update_state, bootstrap_state,
    write_unclassified_log,
)
from agent.constants import PENDING_TASKS_HEADER

SAMPLE_ACCOUNT_ID = "0010g00001j67uzaaq"

APPROVED_TASK = {
    "account_id": SAMPLE_ACCOUNT_ID,
    "customer_name": "Acme Corp",
    "region": "CEE",
    "cse": "Tunde",
    "category": "ESCALATION",
    "priority": "HIGH",
    "suggested_action": "Escalate to regional manager.",
    "old_value": "Ready To Engage",
    "new_value": "Sales Hold",
    "detected_at": "2026-03-21T16:00:00Z",
}


def test_write_approved_tasks_creates_file_with_header(tmp_path):
    out = tmp_path / "pending_tasks.csv"
    write_approved_tasks([APPROVED_TASK], out)
    rows = list(csv.DictReader(open(out)))
    assert rows[0]["account_id"] == SAMPLE_ACCOUNT_ID
    assert rows[0]["category"] == "ESCALATION"


def test_write_approved_tasks_appends_on_second_call(tmp_path):
    out = tmp_path / "pending_tasks.csv"
    write_approved_tasks([APPROVED_TASK], out)
    write_approved_tasks([{**APPROVED_TASK, "account_id": "other"}], out)
    rows = list(csv.DictReader(open(out)))
    assert len(rows) == 2


def test_write_approved_tasks_empty_list_creates_header_only(tmp_path):
    out = tmp_path / "pending_tasks.csv"
    write_approved_tasks([], out)
    with open(out) as f:
        lines = f.readlines()
    assert len(lines) == 1  # header only


def test_update_state_writes_all_fields(tmp_path, sample_csv_row, sample_state):
    state_file = tmp_path / "state.json"
    new_accounts = {SAMPLE_ACCOUNT_ID: {**sample_csv_row, "status": "Sales Hold"}}
    update_state(sample_state, new_accounts, state_file)
    loaded = json.loads(state_file.read_text())
    acc = loaded["accounts"][SAMPLE_ACCOUNT_ID]
    assert acc["status"] == "Sales Hold"
    assert "status_changed_at" in acc
    assert "last_seen" in acc


def test_update_state_only_updates_status_changed_at_on_status_change(tmp_path, sample_csv_row, sample_state):
    state_file = tmp_path / "state.json"
    original_changed_at = sample_state["accounts"][SAMPLE_ACCOUNT_ID]["status_changed_at"]
    # no status change
    new_accounts = {SAMPLE_ACCOUNT_ID: sample_csv_row}
    update_state(sample_state, new_accounts, state_file)
    loaded = json.loads(state_file.read_text())
    assert loaded["accounts"][SAMPLE_ACCOUNT_ID]["status_changed_at"] == original_changed_at


def test_update_state_updates_expiry_alerted_date_when_expiry_risk(tmp_path, sample_csv_row, sample_state):
    state_file = tmp_path / "state.json"
    sample_csv_row["expiration_date"] = (date.today()).strftime("%m/%d/%y")
    new_accounts = {SAMPLE_ACCOUNT_ID: sample_csv_row}
    update_state(sample_state, new_accounts, state_file, expiry_flagged={SAMPLE_ACCOUNT_ID})
    loaded = json.loads(state_file.read_text())
    assert loaded["accounts"][SAMPLE_ACCOUNT_ID]["expiry_alerted_date"] == date.today().isoformat()


def test_bootstrap_state_creates_state_with_300_accounts(tmp_path):
    csv_path = Path("/Users/mbanica/Documents/Code_Samples/CC/Solstice/data/EMEA Accounts CC Migrations - Accounts.csv")
    if not csv_path.exists():
        pytest.skip("Real CSV not available")
    from agent.differ import parse_csv
    accounts = parse_csv(csv_path)
    state_file = tmp_path / "state.json"
    tasks_file = tmp_path / "pending_tasks.csv"
    bootstrap_state(accounts, state_file, tasks_file)
    loaded = json.loads(state_file.read_text())
    assert len(loaded["accounts"]) == len(accounts)
    # pending_tasks.csv should be header only
    rows = list(csv.DictReader(open(tasks_file)))
    assert len(rows) == 0


def test_write_unclassified_log_appends(tmp_path):
    log = tmp_path / "pending_review.log"
    diff = {"account_id": "abc", "customer_name": "X", "changes": []}
    write_unclassified_log([diff], log)
    content = log.read_text()
    assert "abc" in content
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_writer.py -v
```

Expected: `ImportError: cannot import name 'write_approved_tasks' from 'agent.writer'`

- [ ] **Step 3: Implement writer.py**

```python
# Solstice/agent/writer.py
from __future__ import annotations
import csv
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from agent.constants import PENDING_TASKS_HEADER

logger = logging.getLogger(__name__)


def write_approved_tasks(tasks: list[dict], output_file: Path) -> None:
    """Append approved tasks to CSV. Creates file with header if it doesn't exist."""
    file_exists = output_file.exists() and output_file.stat().st_size > 0
    with open(output_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PENDING_TASKS_HEADER, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for task in tasks:
            writer.writerow(task)


def update_state(
    current_state: dict,
    new_accounts: dict,
    state_file: Path,
    expiry_flagged: Optional[set] = None,
) -> None:
    """
    Update state.json with latest account data.
    - status_changed_at updated ONLY when status changes.
    - expiry_alerted_date set to today for accounts in expiry_flagged set.
    """
    expiry_flagged = expiry_flagged or set()
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    state_accounts = current_state.get("accounts", {})

    for account_id, new in new_accounts.items():
        prev = state_accounts.get(account_id, {})
        prev_status = prev.get("status", "")
        new_status = new.get("status", "")

        state_accounts[account_id] = {
            "customer_name": new.get("customer_name", ""),
            "arr": new.get("arr", ""),
            "active_cse": new.get("active_cse", ""),
            "backup_cse": new.get("backup_cse", ""),
            "status": new_status,
            "status_changed_at": now if new_status != prev_status else prev.get("status_changed_at", now),
            "expiration_date": new.get("expiration_date", ""),
            "expiry_alerted_date": today if account_id in expiry_flagged else prev.get("expiry_alerted_date"),
            "ps_engaged": new.get("ps_engaged", ""),
            "kickoff_date": new.get("kickoff_date", ""),
            "comments": new.get("comments", ""),
            "sales_region": new.get("sales_region", ""),
            "email_sent": new.get("email_sent", ""),
            "blockers": new.get("blockers", []),
            "last_seen": now,
        }

    new_state = {
        "last_run": now,
        "accounts": state_accounts,
    }
    state_file.write_text(json.dumps(new_state, indent=2, ensure_ascii=False))
    logger.info("State updated: %d accounts", len(state_accounts))


def bootstrap_state(accounts: dict, state_file: Path, tasks_file: Path) -> None:
    """
    First-run bootstrap. Writes all accounts to state.json without generating tasks.
    Creates pending_tasks.csv with header row only.
    """
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date().isoformat()
    state_accounts = {}

    for account_id, acc in accounts.items():
        state_accounts[account_id] = {
            "customer_name": acc.get("customer_name", ""),
            "arr": acc.get("arr", ""),
            "active_cse": acc.get("active_cse", ""),
            "backup_cse": acc.get("backup_cse", ""),
            "status": acc.get("status", ""),
            "status_changed_at": today + "T00:00:00Z",  # prevents stale-outreach on first run
            "expiration_date": acc.get("expiration_date", ""),
            "expiry_alerted_date": None,
            "ps_engaged": acc.get("ps_engaged", ""),
            "kickoff_date": acc.get("kickoff_date", ""),
            "comments": acc.get("comments", ""),
            "sales_region": acc.get("sales_region", ""),
            "email_sent": acc.get("email_sent", ""),
            "blockers": acc.get("blockers", []),
            "last_seen": now,
        }

    state = {"last_run": now, "accounts": state_accounts}
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    # Create pending_tasks.csv with header only
    with open(tasks_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PENDING_TASKS_HEADER)
        writer.writeheader()

    print(f"Bootstrap complete. {len(accounts)} accounts loaded. Drop a new CSV to begin monitoring.")


def write_unclassified_log(unclassified: list[dict], log_file: Path) -> None:
    """Append UNCLASSIFIED accounts to pending_review.log for manual review."""
    now = datetime.now(timezone.utc).isoformat()
    with open(log_file, "a", encoding="utf-8") as f:
        for diff in unclassified:
            f.write(f"[{now}] UNCLASSIFIED: {diff['account_id']} ({diff.get('customer_name', '')})\n")
            f.write(f"  Changes: {diff.get('changes', [])}\n\n")
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_writer.py -v
```

Expected: All tests PASSED (bootstrap test may skip if CSV not present — that is expected)

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/writer.py Solstice/tests/test_writer.py
git commit -m "feat: writer.py — append CSV, update state.json, bootstrap, UNCLASSIFIED log"
```

---

## Task 7: watcher.py — Watchdog File Monitor

**Files:**
- Create: `Solstice/agent/watcher.py`
- Create: `Solstice/tests/test_watcher.py`

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_watcher.py
from unittest.mock import MagicMock, patch
from pathlib import Path
from agent.watcher import CsvDropHandler


def test_csv_handler_calls_callback_on_csv_created(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "accounts.csv")
    handler.on_created(event)
    assert len(called_with) == 1
    assert called_with[0] == Path(event.src_path)


def test_csv_handler_ignores_non_csv_files(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "notes.txt")
    handler.on_created(event)
    assert len(called_with) == 0


def test_csv_handler_ignores_directory_events(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = True
    event.src_path = str(tmp_path / "subdir")
    handler.on_created(event)
    assert len(called_with) == 0


def test_csv_handler_triggers_on_modified(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "accounts.csv")
    handler.on_modified(event)
    assert len(called_with) == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_watcher.py -v
```

Expected: `ImportError: cannot import name 'CsvDropHandler' from 'agent.watcher'`

- [ ] **Step 3: Implement watcher.py**

```python
# Solstice/agent/watcher.py
import logging
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class CsvDropHandler(FileSystemEventHandler):
    """Watchdog handler. Calls callback(path) when a CSV file is created or modified."""

    def __init__(self, callback: Callable[[Path], None]):
        super().__init__()
        self._callback = callback

    def _handle(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() == ".csv":
            logger.info("CSV detected: %s", path)
            self._callback(path)

    def on_created(self, event) -> None:
        self._handle(event)

    def on_modified(self, event) -> None:
        self._handle(event)


def start_watching(watch_dir: Path, callback: Callable[[Path], None]) -> None:
    """Start blocking watchdog loop. Ctrl+C to stop."""
    handler = CsvDropHandler(callback=callback)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()
    logger.info("Watching %s for CSV drops...", watch_dir)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_watcher.py -v
```

Expected: All tests PASSED

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/watcher.py Solstice/tests/test_watcher.py
git commit -m "feat: watcher.py — watchdog CSV drop handler"
```

---

## Task 8: main.py — Bootstrap and Pipeline Orchestration

**Files:**
- Create: `Solstice/agent/main.py`
- Create: `Solstice/tests/test_main.py`

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_main.py
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
from agent.main import run_pipeline, load_state


def test_load_state_returns_empty_if_no_file(tmp_path):
    state = load_state(tmp_path / "state.json")
    assert state == {"last_run": "", "accounts": {}}


def test_load_state_returns_parsed_json(tmp_path):
    f = tmp_path / "state.json"
    f.write_text('{"last_run": "now", "accounts": {}}')
    state = load_state(f)
    assert state["last_run"] == "now"


def test_run_pipeline_bootstrap_when_no_state(tmp_path):
    csv_path = Path("/Users/mbanica/Documents/Code_Samples/CC/Solstice/data/EMEA Accounts CC Migrations - Accounts.csv")
    if not csv_path.exists():
        pytest.skip("Real CSV not available")

    state_file = tmp_path / "state.json"
    tasks_file = tmp_path / "pending_tasks.csv"
    review_log = tmp_path / "pending_review.log"

    with patch("agent.main.STATE_FILE", state_file), \
         patch("agent.main.PENDING_TASKS_FILE", tasks_file), \
         patch("agent.main.PENDING_REVIEW_LOG", review_log):
        run_pipeline(csv_path)

    assert state_file.exists()
    assert tasks_file.exists()
    state = json.loads(state_file.read_text())
    assert len(state["accounts"]) > 0


def test_run_pipeline_classifies_and_approves(tmp_path):
    from tests.conftest import SAMPLE_ACCOUNT_ID, SAMPLE_STATE_ACCOUNT

    csv_path = Path("/Users/mbanica/Documents/Code_Samples/CC/Solstice/data/EMEA Accounts CC Migrations - Accounts.csv")
    if not csv_path.exists():
        pytest.skip("Real CSV not available")

    state_file = tmp_path / "state.json"
    tasks_file = tmp_path / "pending_tasks.csv"
    review_log = tmp_path / "pending_review.log"

    # Pre-populate state with one account at stale status
    pre_state = {
        "last_run": "2026-01-01T00:00:00Z",
        "accounts": {SAMPLE_ACCOUNT_ID: SAMPLE_STATE_ACCOUNT},
    }
    state_file.write_text(json.dumps(pre_state))

    mock_classification = [{"account_id": SAMPLE_ACCOUNT_ID, "category": "CUSTOMER_OUTREACH",
                            "priority": "HIGH", "suggested_action": "Follow up."}]

    with patch("agent.main.STATE_FILE", state_file), \
         patch("agent.main.PENDING_TASKS_FILE", tasks_file), \
         patch("agent.main.PENDING_REVIEW_LOG", review_log), \
         patch("agent.main.classify_diffs", return_value=mock_classification), \
         patch("agent.main.run_approval", return_value=([mock_classification[0]], 0)):
        run_pipeline(csv_path)

    assert tasks_file.exists()


def test_run_pipeline_unclassified_goes_to_log_not_csv(tmp_path):
    """UNCLASSIFIED tasks must go to pending_review.log only, never to pending_tasks.csv."""
    csv_path = Path("/Users/mbanica/Documents/Code_Samples/CC/Solstice/data/EMEA Accounts CC Migrations - Accounts.csv")
    if not csv_path.exists():
        pytest.skip("Real CSV not available")

    from tests.conftest import SAMPLE_ACCOUNT_ID, SAMPLE_STATE_ACCOUNT

    state_file = tmp_path / "state.json"
    tasks_file = tmp_path / "pending_tasks.csv"
    review_log = tmp_path / "pending_review.log"

    pre_state = {
        "last_run": "2026-01-01T00:00:00Z",
        "accounts": {SAMPLE_ACCOUNT_ID: SAMPLE_STATE_ACCOUNT},
    }
    state_file.write_text(json.dumps(pre_state))

    unclassified = [{"account_id": SAMPLE_ACCOUNT_ID, "category": "UNCLASSIFIED",
                     "priority": "HIGH", "suggested_action": "Manual review required."}]

    with patch("agent.main.STATE_FILE", state_file), \
         patch("agent.main.PENDING_TASKS_FILE", tasks_file), \
         patch("agent.main.PENDING_REVIEW_LOG", review_log), \
         patch("agent.main.classify_diffs", return_value=unclassified):
        run_pipeline(csv_path)

    # pending_review.log should contain the account
    assert review_log.exists()
    assert SAMPLE_ACCOUNT_ID in review_log.read_text()
    # pending_tasks.csv should NOT contain the account
    import csv as csvlib
    if tasks_file.exists():
        rows = list(csvlib.DictReader(open(tasks_file)))
        assert not any(r.get("account_id") == SAMPLE_ACCOUNT_ID for r in rows)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_main.py -v
```

Expected: `ImportError: cannot import name 'run_pipeline' from 'agent.main'`

- [ ] **Step 3: Implement main.py**

```python
# Solstice/agent/main.py
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.constants import DATA_DIR, STATE_FILE, PENDING_TASKS_FILE, PENDING_REVIEW_LOG, AGENT_LOG
from agent.differ import parse_csv, compute_diffs
from agent.classifier import classify_diffs
from agent.approver import run_approval
from agent.writer import write_approved_tasks, update_state, bootstrap_state, write_unclassified_log
from agent.watcher import start_watching

# Module-level logger — handlers added in main() after DATA_DIR is ensured to exist
logger = logging.getLogger(__name__)


def load_state(state_file: Path = STATE_FILE) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load state.json: %s", e)
    return {"last_run": "", "accounts": {}}


def run_pipeline(csv_path: Path) -> None:
    """Full pipeline: parse → diff → classify → approve → write."""
    logger.info("Pipeline triggered by: %s", csv_path)
    state = load_state(STATE_FILE)

    # Bootstrap: no state yet
    if not state["accounts"]:
        logger.info("No state found — bootstrapping from %s", csv_path)
        accounts = parse_csv(csv_path)
        bootstrap_state(accounts, STATE_FILE, PENDING_TASKS_FILE)
        return

    # Parse new CSV
    new_accounts = parse_csv(csv_path)
    if not new_accounts:
        logger.warning("CSV produced 0 accounts — skipping pipeline")
        return

    # Diff
    diffs = compute_diffs(new_accounts, state)
    if not diffs:
        logger.info("No changes detected.")
        print("No changes detected.")
        update_state(state, new_accounts, STATE_FILE)
        return

    logger.info("%d diffs detected", len(diffs))

    # Classify
    classifications = classify_diffs(diffs)

    # Merge diff context into classification results for approver
    diff_by_id = {d["account_id"]: d for d in diffs}
    tasks = []
    unclassified_diffs = []

    for c in classifications:
        acc_id = c["account_id"]
        diff = diff_by_id.get(acc_id, {})
        changes = diff.get("changes", [])
        old_val = changes[0]["old"] if changes else ""
        new_val = changes[0]["new"] if changes else ""

        task = {
            "account_id": acc_id,
            "customer_name": diff.get("customer_name", ""),
            "region": diff.get("region", ""),
            "cse": diff.get("cse", ""),
            "category": c["category"],
            "priority": c["priority"],
            "suggested_action": c["suggested_action"],
            "old_value": str(old_val) if old_val is not None else "",
            "new_value": str(new_val) if new_val is not None else "",
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

        if c["category"] == "UNCLASSIFIED":
            unclassified_diffs.append(diff)
        else:
            tasks.append(task)

    # Log unclassified
    if unclassified_diffs:
        write_unclassified_log(unclassified_diffs, PENDING_REVIEW_LOG)
        logger.warning("%d UNCLASSIFIED accounts written to pending_review.log", len(unclassified_diffs))

    # Approve
    if tasks:
        approved, skipped = run_approval(tasks)
    else:
        approved, skipped = [], 0

    # Write
    if approved:
        write_approved_tasks(approved, PENDING_TASKS_FILE)
        logger.info("%d tasks written to pending_tasks.csv", len(approved))

    # Collect accounts that triggered expiry risk
    expiry_flagged = {d["account_id"] for d in diffs if d.get("expiry_risk")}

    # Update state
    update_state(state, new_accounts, STATE_FILE, expiry_flagged=expiry_flagged)
    logger.info("Pipeline complete.")


def main():
    DATA_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(AGENT_LOG),
            logging.StreamHandler(sys.stdout),
        ],
    )
    print("Solstice Agent — watching", DATA_DIR, "for CSV drops. Ctrl+C to stop.")
    start_watching(DATA_DIR, callback=run_pipeline)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_main.py -v
```

Expected: All tests PASSED (some may skip if CSV not present)

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/main.py Solstice/tests/test_main.py
git commit -m "feat: main.py — bootstrap detection, pipeline orchestration, CLI entry point"
```

---

## Task 9: api.py — FastAPI Status Endpoint

**Files:**
- Create: `Solstice/agent/api.py`
- Create: `Solstice/tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# Solstice/tests/test_api.py
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from pathlib import Path
from agent.api import app


def make_state(last_run, n_accounts):
    return {
        "last_run": last_run,
        "accounts": {f"id{i}": {} for i in range(n_accounts)},
    }


def test_status_returns_200():
    state = make_state("2026-03-21T16:00:00Z", 300)
    with patch("agent.api.load_state", return_value=state):
        client = TestClient(app)
        r = client.get("/status")
    assert r.status_code == 200


def test_status_contains_account_count():
    state = make_state("2026-03-21T16:00:00Z", 42)
    with patch("agent.api.load_state", return_value=state):
        client = TestClient(app)
        r = client.get("/status")
    assert r.json()["account_count"] == 42


def test_status_contains_last_run():
    state = make_state("2026-03-21T16:00:00Z", 10)
    with patch("agent.api.load_state", return_value=state):
        client = TestClient(app)
        r = client.get("/status")
    assert r.json()["last_run"] == "2026-03-21T16:00:00Z"


def test_status_when_no_state():
    with patch("agent.api.load_state", return_value={"last_run": "", "accounts": {}}):
        client = TestClient(app)
        r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["account_count"] == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_api.py -v
```

Expected: `ImportError: cannot import name 'app' from 'agent.api'`

- [ ] **Step 3: Implement api.py**

```python
# Solstice/agent/api.py
from fastapi import FastAPI
from agent.main import load_state

app = FastAPI(title="Solstice Agent Status API")


@app.get("/status")
def status():
    state = load_state()
    return {
        "status": "ok",
        "last_run": state.get("last_run", ""),
        "account_count": len(state.get("accounts", {})),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest tests/test_api.py -v
```

Expected: All tests PASSED

- [ ] **Step 5: Commit**

```bash
git add Solstice/agent/api.py Solstice/tests/test_api.py
git commit -m "feat: api.py — FastAPI /status endpoint"
```

---

## Task 10: Full Test Run + README

**Files:**
- Modify: `Solstice/README.md`

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
pytest -v
```

Expected: All tests PASSED, 0 failures.

- [ ] **Step 2: Smoke test — bootstrap with real CSV**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 -c "
from pathlib import Path
from agent.main import run_pipeline
run_pipeline(Path('data/EMEA Accounts CC Migrations - Accounts.csv'))
"
```

Expected output:
```
Bootstrap complete. 300 accounts loaded. Drop a new CSV to begin monitoring.
```
And `data/state.json` exists with 300 accounts, `data/pending_tasks.csv` has header row only.

- [ ] **Step 3: Write README.md**

```markdown
# Solstice Agent

EMEA CC Migration account monitor. Watches for CSV exports, classifies changes with Claude, routes through terminal approval, outputs AppSheet-ready tasks.

## Setup

```bash
pip3 install -r requirements.txt
```

## Run

```bash
# Agent (watcher + pipeline + approval)
python3 agent/main.py

# Status API (separate terminal)
python3 agent/api.py
# → http://localhost:8100/status
```

## Usage

1. Export the EMEA sheet as CSV: **File → Download → CSV**
2. Drop the CSV into `data/` — the agent detects it automatically
3. Review proposed tasks in the terminal: `[A]pprove / [R]eject / [E]dit / [S]kip`
4. Import `data/pending_tasks.csv` into AppSheet

## First Run (Bootstrap)

On first run with no `data/state.json`, the agent loads all accounts as baseline — no tasks are generated. Drop a second CSV export to begin monitoring changes.

## Tests

```bash
pytest -v
```
```

- [ ] **Step 4: Commit**

```bash
git add Solstice/README.md
git commit -m "docs: Solstice agent README — setup, usage, bootstrap instructions"
```

- [ ] **Step 5: Final commit tag**

```bash
git add Solstice/
git commit -m "feat: Solstice agent MVP — complete implementation"
```

---

## Quick Reference — Running the Agent

```bash
# Terminal 1: agent
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 agent/main.py

# Terminal 2: status API (optional)
python3 agent/api.py

# Check status
curl http://localhost:8100/status
```
