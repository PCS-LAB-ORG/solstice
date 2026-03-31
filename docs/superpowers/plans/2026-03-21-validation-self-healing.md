# Validation & Self-Healing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a data validation layer that blocks invalid account IDs and non-EMEA accounts before they reach Claude, fixes the watcher self-loop by moving the watched folder to `data/inbox/`, and adds 13 backtests.

**Architecture:** A new `validator.py` module sits between `parse_csv()` and `compute_diffs()` in the pipeline. It splits parsed accounts into (valid, invalid), logs invalid entries to `validation_errors.log`, and returns only valid accounts downstream. The watcher is re-pointed from `data/` to `data/inbox/` so agent-output files never trigger the pipeline.

**Tech Stack:** Python 3.9+, re (stdlib), pathlib (stdlib), pytest

**Spec:** `docs/superpowers/specs/2026-03-21-validation-self-healing-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `agent/constants.py` | Modify | Add `INBOX_DIR`, `VALIDATION_ERRORS_LOG`, `SALESFORCE_ID_PATTERN` |
| `agent/validator.py` | Create | `validate_accounts()` + `write_validation_errors()` |
| `agent/main.py` | Modify | Wire validator into pipeline; watch `INBOX_DIR`; create inbox on startup |
| `tests/test_validator.py` | Create | 13 backtests covering all validation rules |
| `README.md` | Modify | Update drop path from `data/` to `data/inbox/` |

**Note on `NON_EMEA_SKIP_IF_PRESENT`:** The spec mentions removing this constant, but it was never added to `constants.py` (it was dropped during spec review). No removal step is needed.

---

## Task 1: constants.py — Add Inbox and Validation Constants

**Files:**
- Modify: `Solstice/agent/constants.py`

The current top of `constants.py` is:

```python
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
PENDING_TASKS_FILE = DATA_DIR / "pending_tasks.csv"
PENDING_REVIEW_LOG = DATA_DIR / "pending_review.log"
AGENT_LOG = DATA_DIR / "agent.log"
```

- [ ] **Step 1: Add `import re` and three new constants**

Change the top of the file to:

```python
import re
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
INBOX_DIR = DATA_DIR / "inbox"
STATE_FILE = DATA_DIR / "state.json"
PENDING_TASKS_FILE = DATA_DIR / "pending_tasks.csv"
PENDING_REVIEW_LOG = DATA_DIR / "pending_review.log"
AGENT_LOG = DATA_DIR / "agent.log"
VALIDATION_ERRORS_LOG = DATA_DIR / "validation_errors.log"

# Salesforce account IDs are 15 or 18 alphanumeric characters.
# "TRUE" (4 chars) and "FALSE" (5 chars) are rejected by the length check.
SALESFORCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]{15,18}$")
```

Leave all remaining constants below unchanged.

- [ ] **Step 2: Verify import works**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && python3 -c "
import sys; sys.path.insert(0, '.')
from agent.constants import INBOX_DIR, VALIDATION_ERRORS_LOG, SALESFORCE_ID_PATTERN
print('INBOX_DIR:', INBOX_DIR)
print('VALIDATION_ERRORS_LOG:', VALIDATION_ERRORS_LOG)
print('pattern matches 18-char ID:', bool(SALESFORCE_ID_PATTERN.match('0010g00001j67uzaaq')))
print('pattern rejects FALSE:', not bool(SALESFORCE_ID_PATTERN.match('FALSE')))
"
```

Expected:
```
INBOX_DIR: /Users/mbanica/Documents/Code_Samples/CC/Solstice/data/inbox
VALIDATION_ERRORS_LOG: /Users/mbanica/Documents/Code_Samples/CC/Solstice/data/validation_errors.log
pattern matches 18-char ID: True
pattern rejects FALSE: True
```

- [ ] **Step 3: Run existing suite — confirm no regressions**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && pytest -v --tb=short 2>&1 | tail -5
```

Expected: `54 passed`

- [ ] **Step 4: Commit**

```bash
git -C /Users/mbanica/Documents/Code_Samples/CC add Solstice/agent/constants.py
git -C /Users/mbanica/Documents/Code_Samples/CC commit -m "feat: constants — INBOX_DIR, VALIDATION_ERRORS_LOG, SALESFORCE_ID_PATTERN

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: validator.py — Validation Module (TDD)

**Files:**
- Create: `Solstice/tests/test_validator.py`
- Create: `Solstice/agent/validator.py`

- [ ] **Step 1: Write all 13 failing tests**

Create `/Users/mbanica/Documents/Code_Samples/CC/Solstice/tests/test_validator.py`:

```python
import pytest
from pathlib import Path
from agent.validator import validate_accounts, write_validation_errors

# --- Helpers ---

VALID_ID = "0010g00001j67uzaaq"   # 18-char alphanumeric Salesforce ID
VALID_ID_15 = "001700000AbcDef"   # 15-char alphanumeric Salesforce ID


def make_account(account_id=VALID_ID, sales_region="CEE", status="Ready To Engage"):
    return {
        "account_id": account_id,
        "customer_name": "Acme Corp",
        "arr": "50000",
        "active_cse": "Tunde",
        "backup_cse": "",
        "status": status,
        "sales_region": sales_region,
        "comments": "",
        "expiration_date": "",
        "ps_engaged": "",
        "kickoff_date": "",
        "email_sent": "",
        "blockers": [],
    }


# --- Tests ---

def test_valid_account_passes():
    accounts = {VALID_ID: make_account()}
    valid, invalid = validate_accounts(accounts)
    assert VALID_ID in valid
    assert len(invalid) == 0


def test_false_account_id_rejected():
    accounts = {"FALSE": make_account(account_id="FALSE")}
    valid, invalid = validate_accounts(accounts)
    assert len(valid) == 0
    assert len(invalid) == 1
    assert invalid[0]["account_id"] == "FALSE"
    assert "INVALID_ACCOUNT_ID" in invalid[0]["reason"]


def test_true_account_id_rejected():
    accounts = {"TRUE": make_account(account_id="TRUE")}
    valid, invalid = validate_accounts(accounts)
    assert len(valid) == 0
    assert len(invalid) == 1
    assert invalid[0]["account_id"] == "TRUE"


def test_empty_account_id_rejected():
    # Defense-in-depth: parse_csv() already skips empty IDs, but validator
    # must also handle this case when called independently.
    accounts = {"": make_account(account_id="")}
    valid, invalid = validate_accounts(accounts)
    assert len(valid) == 0
    assert len(invalid) == 1


def test_non_emea_region_rejected():
    accounts = {VALID_ID: make_account(sales_region="LATAM")}
    valid, invalid = validate_accounts(accounts)
    assert len(valid) == 0
    assert len(invalid) == 1
    assert invalid[0]["account_id"] == VALID_ID
    assert "NON_EMEA_REGION" in invalid[0]["reason"]


def test_empty_region_passes():
    # Empty region = unknown, not confirmed non-EMEA — passes through
    accounts = {VALID_ID: make_account(sales_region="")}
    valid, invalid = validate_accounts(accounts)
    assert VALID_ID in valid
    assert len(invalid) == 0


def test_na_value_passes():
    # #N/A field values are not validation failures — Claude handles them
    accounts = {VALID_ID: make_account(status="#N/A")}
    valid, invalid = validate_accounts(accounts)
    assert VALID_ID in valid
    assert len(invalid) == 0


def test_mixed_batch():
    accounts = {
        VALID_ID: make_account(),
        "FALSE": make_account(account_id="FALSE"),
        "0010g00001j6mRWAAY": make_account(
            account_id="0010g00001j6mRWAAY", sales_region="LATAM"
        ),
    }
    valid, invalid = validate_accounts(accounts)
    assert len(valid) == 1
    assert VALID_ID in valid
    assert len(invalid) == 2


def test_all_invalid_returns_empty_valid():
    accounts = {
        "FALSE": make_account(account_id="FALSE"),
        "TRUE": make_account(account_id="TRUE"),
    }
    valid, invalid = validate_accounts(accounts)
    assert valid == {}
    assert len(invalid) == 2


def test_validation_errors_log_written(tmp_path):
    log_file = tmp_path / "validation_errors.log"
    invalid_entries = [
        {"account_id": "FALSE", "reason": "INVALID_ACCOUNT_ID", "region": "", "file": "test.csv"},
        {"account_id": "abc123", "reason": "NON_EMEA_REGION", "region": "LATAM", "file": "test.csv"},
    ]
    write_validation_errors(invalid_entries, log_file)
    content = log_file.read_text()
    assert "FALSE" in content
    assert "INVALID_ACCOUNT_ID" in content
    assert "NON_EMEA_REGION" in content
    assert "LATAM" in content


def test_validation_errors_log_appends(tmp_path):
    # write_validation_errors must APPEND — second call adds more lines, not overwrite
    log_file = tmp_path / "validation_errors.log"
    entry = {"account_id": "FALSE", "reason": "INVALID_ACCOUNT_ID", "region": "", "file": "t.csv"}
    write_validation_errors([entry], log_file)
    write_validation_errors([entry], log_file)
    lines = [l for l in log_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 2  # two calls, one line each


def test_valid_salesforce_id_formats():
    # Both 15-char and 18-char IDs must pass
    acc_15 = {VALID_ID_15: make_account(account_id=VALID_ID_15)}
    acc_18 = {VALID_ID: make_account(account_id=VALID_ID)}
    valid_15, _ = validate_accounts(acc_15)
    valid_18, _ = validate_accounts(acc_18)
    assert VALID_ID_15 in valid_15
    assert VALID_ID in valid_18


def test_csv_filename_appears_in_invalid_entries():
    accounts = {"FALSE": make_account(account_id="FALSE")}
    _, invalid = validate_accounts(accounts, csv_filename="blah.csv")
    assert invalid[0]["file"] == "blah.csv"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && pytest tests/test_validator.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'validate_accounts' from 'agent.validator'`

- [ ] **Step 3: Implement validator.py**

Create `/Users/mbanica/Documents/Code_Samples/CC/Solstice/agent/validator.py`:

```python
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from agent.constants import SALESFORCE_ID_PATTERN, REGIONS

logger = logging.getLogger(__name__)

_REASON_LABELS = {
    "INVALID_ACCOUNT_ID": "Not a valid Salesforce ID (expected 15-18 alphanumeric chars)",
    "NON_EMEA_REGION": "Not in EMEA REGIONS list",
}


def validate_accounts(
    accounts: dict, csv_filename: str = ""
) -> tuple[dict, list[dict]]:
    """
    Split accounts into (valid, invalid).
    valid:   {account_id: account_dict} — safe to pass to compute_diffs()
    invalid: list of {"account_id": str, "reason": str, "region": str, "file": str}

    Rules (applied in order):
    1. account_id must match SALESFORCE_ID_PATTERN (15-18 alphanumeric chars)
    2. sales_region must be in REGIONS or empty (empty = unknown, not blocked)
    """
    valid: dict = {}
    invalid: list[dict] = []

    for account_id, acc in accounts.items():
        # Rule 1: Salesforce ID format
        if not account_id or not SALESFORCE_ID_PATTERN.match(account_id):
            invalid.append({
                "account_id": account_id,
                "reason": "INVALID_ACCOUNT_ID",
                "region": acc.get("sales_region", ""),
                "file": csv_filename,
            })
            logger.warning("INVALID_ACCOUNT_ID: %s (file=%s)", account_id, csv_filename)
            continue

        # Rule 2: EMEA region check (empty region passes — unknown, not confirmed non-EMEA)
        region = acc.get("sales_region", "")
        if region and region not in REGIONS:
            invalid.append({
                "account_id": account_id,
                "reason": "NON_EMEA_REGION",
                "region": region,
                "file": csv_filename,
            })
            logger.warning(
                "NON_EMEA_REGION: %s region=%s (file=%s)", account_id, region, csv_filename
            )
            continue

        valid[account_id] = acc

    return valid, invalid


def write_validation_errors(invalid_entries: list[dict], log_file: Path) -> None:
    """
    Append invalid_entries to log_file. Creates file if it does not exist.
    One line per entry in the format:
      [ISO_TIMESTAMP] REASON_CODE: account_id=ID region=REGION reason="Human readable" file=FILE
    """
    if not invalid_entries:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_file, "a", encoding="utf-8") as f:
        for entry in invalid_entries:
            reason_code = entry.get("reason", "UNKNOWN")
            acc_id = entry.get("account_id", "")
            region = entry.get("region", "")
            file_ = entry.get("file", "")
            human = _REASON_LABELS.get(reason_code, reason_code)
            region_part = f" region={region}" if region else ""
            f.write(
                f"[{now}] {reason_code}: account_id={acc_id}{region_part}"
                f" reason=\"{human}\" file={file_}\n"
            )
```

- [ ] **Step 4: Run tests — expect 13 passing**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && pytest tests/test_validator.py -v
```

Expected: `13 passed`

If any test fails, fix the **implementation** — do NOT change the tests.

- [ ] **Step 5: Run full suite**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && pytest -v --tb=short 2>&1 | tail -5
```

Expected: `67 passed` (54 existing + 13 new)

- [ ] **Step 6: Commit**

```bash
git -C /Users/mbanica/Documents/Code_Samples/CC add Solstice/agent/validator.py Solstice/tests/test_validator.py
git -C /Users/mbanica/Documents/Code_Samples/CC commit -m "feat: validator.py — Salesforce ID check, EMEA region filter, validation log

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: main.py — Wire Validator + Fix Inbox Watcher

**Files:**
- Modify: `Solstice/agent/main.py`
- Modify: `Solstice/tests/test_main.py` (if needed — see Step 2)

The current `main.py` imports are:
```python
from agent.constants import DATA_DIR, STATE_FILE, PENDING_TASKS_FILE, PENDING_REVIEW_LOG, AGENT_LOG
```

And `run_pipeline()` currently calls `compute_diffs(new_accounts, state)` without any validation step.

- [ ] **Step 1: Update main.py**

Make these five targeted changes:

**Change 1 — constants import** (line 7): add `INBOX_DIR` and `VALIDATION_ERRORS_LOG`:
```python
from agent.constants import DATA_DIR, INBOX_DIR, STATE_FILE, PENDING_TASKS_FILE, PENDING_REVIEW_LOG, AGENT_LOG, VALIDATION_ERRORS_LOG
```

**Change 2 — add validator import** (after line 8, `from agent.differ import ...`):
```python
from agent.validator import validate_accounts, write_validation_errors
```

**Change 3 — add validation step in `run_pipeline()`**. Replace:
```python
    new_accounts = parse_csv(csv_path)
    if not new_accounts:
        logger.warning("CSV produced 0 accounts — skipping pipeline")
        return

    diffs = compute_diffs(new_accounts, state)
```
With:
```python
    new_accounts = parse_csv(csv_path)
    if not new_accounts:
        logger.warning("CSV produced 0 accounts — skipping pipeline")
        return

    valid_accounts, invalid_entries = validate_accounts(new_accounts, csv_filename=csv_path.name)
    if invalid_entries:
        write_validation_errors(invalid_entries, VALIDATION_ERRORS_LOG)
        logger.warning("%d invalid rows written to validation_errors.log", len(invalid_entries))
    if not valid_accounts:
        logger.warning("No valid EMEA accounts after validation — skipping pipeline")
        return

    diffs = compute_diffs(valid_accounts, state)
```

**Change 4 — use `valid_accounts` in the no-diffs early exit**. Replace:
```python
        update_state(state, new_accounts, STATE_FILE)
```
With:
```python
        update_state(state, valid_accounts, STATE_FILE)
```

**Change 5 — use `valid_accounts` in the final `update_state` call and fix `main()`**. Replace:
```python
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
```
With:
```python
    update_state(state, valid_accounts, STATE_FILE, expiry_flagged=expiry_flagged)
    logger.info("Pipeline complete.")


def main():
    DATA_DIR.mkdir(exist_ok=True)
    INBOX_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(AGENT_LOG),
            logging.StreamHandler(sys.stdout),
        ],
    )
    print(f"Solstice Agent — watching {INBOX_DIR} for CSV drops. Ctrl+C to stop.")
    start_watching(INBOX_DIR, callback=run_pipeline)
```

- [ ] **Step 2: Fix test_main.py — patch validate_accounts**

The existing `test_run_pipeline_classifies_and_approves` and `test_run_pipeline_unclassified_goes_to_log_not_csv` tests in `tests/test_main.py` pre-populate state with `SAMPLE_ACCOUNT_ID` and then parse the real CSV. After adding validation, `validate_accounts()` will be called on all accounts from the CSV — which is correct behavior, but the tests also need `SAMPLE_ACCOUNT_ID` to survive validation (it is a valid Salesforce ID, so it should pass automatically).

Run the tests first to see if they already pass:
```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && pytest tests/test_main.py -v --tb=short
```

If any test fails with "No valid EMEA accounts" or similar, add this patch to the failing test(s):
```python
with patch("agent.main.validate_accounts", side_effect=lambda accs, **kw: (accs, [])):
```

Add it inside the existing `with patch(...)` block. Example for `test_run_pipeline_classifies_and_approves`:
```python
    with patch("agent.main.STATE_FILE", state_file), \
         patch("agent.main.PENDING_TASKS_FILE", tasks_file), \
         patch("agent.main.PENDING_REVIEW_LOG", review_log), \
         patch("agent.main.validate_accounts", side_effect=lambda accs, **kw: (accs, [])), \
         patch("agent.main.classify_diffs", return_value=mock_classification), \
         patch("agent.main.run_approval", return_value=([mock_classification[0]], 0)):
        run_pipeline(csv_path)
```

Apply the same `validate_accounts` patch to any other test in `test_main.py` that calls `run_pipeline()` and is failing.

- [ ] **Step 3: Run full suite**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && pytest -v --tb=short 2>&1 | tail -8
```

Expected: `67 passed` (or more if test_main.py patches added lines). Zero failures.

- [ ] **Step 4: Smoke test**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && python3 -c "
import sys; sys.path.insert(0, '.')
from agent.constants import INBOX_DIR
print('main.py imports OK')
print('Drop CSVs here:', INBOX_DIR)
"
```

Expected:
```
main.py imports OK
Drop CSVs here: /Users/mbanica/Documents/Code_Samples/CC/Solstice/data/inbox
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/mbanica/Documents/Code_Samples/CC add Solstice/agent/main.py Solstice/tests/test_main.py
git -C /Users/mbanica/Documents/Code_Samples/CC commit -m "feat: main.py — wire validator, fix watcher self-loop (inbox/ dir)

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: README + Final Verification

**Files:**
- Modify: `Solstice/README.md`

- [ ] **Step 1: Update drop instruction**

In `README.md`, find this line in the Usage section:
```
2. Drop the CSV into `data/` — the agent detects it automatically
```

Replace with:
```
2. Drop the CSV into `data/inbox/` — the agent detects it automatically (`inbox/` is created on first run)
```

- [ ] **Step 2: Final full test run**

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice && pytest -v
```

Expected: all pass, 0 failures.

- [ ] **Step 3: Commit**

```bash
git -C /Users/mbanica/Documents/Code_Samples/CC add Solstice/README.md
git -C /Users/mbanica/Documents/Code_Samples/CC commit -m "docs: drop CSV into data/inbox/ not data/

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Quick Reference — Running After This Change

```bash
cd /Users/mbanica/Documents/Code_Samples/CC/Solstice
python3 run.py
# Agent now watches data/inbox/ — drop CSV exports there
# Invalid rows (bad IDs, non-EMEA regions) logged to data/validation_errors.log
# Agent output files in data/ never trigger the pipeline again
```
