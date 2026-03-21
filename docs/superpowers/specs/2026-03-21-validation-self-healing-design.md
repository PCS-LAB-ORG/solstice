# Solstice Agent — Validation & Self-Healing Design

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Data validation layer, inbox watcher fix, backtests

---

## Problem Statement

Three issues observed in production run:

1. **Watcher self-loop** — agent writes `pending_tasks.csv` to `data/`, watchdog picks it up and triggers a second pipeline run.
2. **Invalid account rows** — rows with `account_id = "FALSE"`, `"TRUE"`, or blank reach the differ and classifier with garbage data.
3. **Non-EMEA accounts** — accounts with regions outside the EMEA REGIONS list (e.g. LATAM) appear in the EMEA agent's pipeline and should never reach the classifier or approver.

---

## Design

### 1. Inbox Folder (`data/inbox/`)

**Problem:** Watcher watches `data/`, which includes agent-output files (`pending_tasks.csv`, `agent.log`, `pending_review.log`, `validation_errors.log`, `state.json`). Any write to these files re-triggers the pipeline.

**Fix:** Move the watched directory from `data/` to `data/inbox/`. The agent never writes to `inbox/`. User drops CSV exports into `inbox/`. Agent outputs stay in `data/`.

**Changes:**
- `constants.py`: Add `INBOX_DIR = DATA_DIR / "inbox"`
- `main.py`: Pass `INBOX_DIR` to `start_watching()` instead of `DATA_DIR`
- `main()`: Create `INBOX_DIR` on startup alongside `DATA_DIR`
- `README.md`: Update drop instructions to point to `data/inbox/`

---

### 2. `validator.py` — Data Validation Module

**Position in pipeline:** After `parse_csv()`, before `compute_diffs()`.

**Interface:**
```python
def validate_accounts(accounts: dict, csv_filename: str = "") -> tuple[dict, list[dict]]:
    """
    Returns (valid_accounts, invalid_entries).
    valid_accounts: {account_id: account_dict} — safe to pass to compute_diffs()
    invalid_entries: list of {"account_id": str, "reason": str, "region": str, "file": str}
    csv_filename: basename of the source CSV, included in log entries for traceability.
    """

def write_validation_errors(invalid_entries: list[dict], log_file: Path) -> None:
    """
    Appends invalid_entries to log_file. Creates the file if it does not exist.
    One line per entry in the format shown below.
    """
```

**Validation rules (applied in order):**

| Rule | Condition | Action |
|---|---|---|
| Valid Salesforce ID | `account_id` matches `^[a-zA-Z0-9]{15,18}$` | Skip + log if invalid. `"TRUE"` (4 chars) and `"FALSE"` (5 chars) are already rejected by the length check — no explicit exclusion needed. |
| EMEA region | `sales_region` is in `REGIONS` constant OR `sales_region` is empty | Skip + log if non-EMEA region detected. Empty region passes (region unknown, not confirmed non-EMEA). |

**Note:** `#N/A` field values are NOT a validation failure — they pass through to Claude for classification.

**Log format (`data/validation_errors.log`):**
```
[2026-03-21T17:46:40Z] INVALID_ACCOUNT_ID: account_id=FALSE reason="Not a valid Salesforce ID" file=blah.csv
[2026-03-21T17:46:40Z] NON_EMEA_REGION: account_id=0010g00001j6mRWAAY region=LATAM reason="Not in EMEA REGIONS list" file=blah.csv
```

---

### 3. Pipeline Integration (`main.py`)

Updated `run_pipeline()` flow:

```
parse_csv(csv_path)
  → validate_accounts(accounts, csv_filename=csv_path.name)   # NEW — splits valid/invalid
  → write_validation_errors(invalid, VALIDATION_ERRORS_LOG)   # NEW — appends to log
  → compute_diffs(valid_accounts, state)
  → classify_diffs(diffs)
  → run_approval(tasks)
  → write_approved_tasks(approved)
  → update_state(state, valid_accounts)  # NOTE: only valid accounts update state
```

If `valid_accounts` is empty after validation, pipeline logs a warning and exits without calling Claude.

---

### 4. Constants

Add to `constants.py`:
```python
INBOX_DIR = DATA_DIR / "inbox"
VALIDATION_ERRORS_LOG = DATA_DIR / "validation_errors.log"
SALESFORCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]{15,18}$")
# Non-EMEA accounts are always skipped — no flag needed.
# REGIONS constant (already present) is the source of truth for EMEA membership.
```

---

### 5. Backtests (`tests/test_validator.py`)

Tests cover all validation rules and edge cases:

| Test | Description |
|---|---|
| `test_valid_account_passes` | Standard Salesforce ID + EMEA region → included in valid |
| `test_false_account_id_rejected` | account_id="FALSE" → invalid, logged |
| `test_true_account_id_rejected` | account_id="TRUE" → invalid, logged |
| `test_empty_account_id_rejected` | account_id="" → invalid, logged. Defense-in-depth: `parse_csv()` already filters these, but `validate_accounts()` must also reject them in case it is called independently. |
| `test_non_emea_region_rejected` | sales_region="LATAM" → invalid, logged |
| `test_empty_region_passes` | sales_region="" → valid (region unknown, not confirmed non-EMEA) |
| `test_na_value_passes` | status="#N/A" → valid (passes through to Claude) |
| `test_mixed_batch` | 3 accounts: 1 valid, 1 FALSE id, 1 LATAM → returns 1 valid, 2 invalid |
| `test_all_invalid_returns_empty_valid` | All rows invalid → valid={}, pipeline exits early |
| `test_validation_errors_log_written` | Invalid rows → entries written to log file with correct format |
| `test_valid_salesforce_id_formats` | 15-char and 18-char IDs both accepted |

---

### 6. Files Changed

| File | Change |
|---|---|
| `agent/constants.py` | Add `INBOX_DIR`, `VALIDATION_ERRORS_LOG`, `SALESFORCE_ID_PATTERN` (remove `NON_EMEA_SKIP_IF_PRESENT`) |
| `agent/validator.py` | New — `validate_accounts()`, `write_validation_errors()` |
| `agent/main.py` | Wire validator into pipeline; watch `INBOX_DIR`; create inbox on startup |
| `tests/test_validator.py` | New — 11 backtests |
| `README.md` | Update drop path to `data/inbox/` |

**Files NOT changed:** `differ.py`, `classifier.py`, `approver.py`, `writer.py`, `watcher.py`, `api.py`

---

### 7. Out of Scope

- Approver UI warning banner for non-EMEA accounts (non-EMEA accounts are now blocked before reaching the approver — no UI change needed)
- Auto-correction of `#N/A` values (passed through to Claude as-is)
- Region inference from account_id or customer_name
- Any change to AppSheet write-back logic
