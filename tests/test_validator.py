import pytest
from pathlib import Path
from agent.validator import validate_accounts, write_validation_errors

# --- Helpers ---

VALID_ID = "0010g00001j67uzaaq"  # 18-char alphanumeric Salesforce ID
VALID_ID_15 = "001700000AbcDef"  # 15-char alphanumeric Salesforce ID


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
    assert invalid[0]["account_id"] == "false"
    assert "INVALID_ACCOUNT_ID" in invalid[0]["reason"]


def test_true_account_id_rejected():
    accounts = {"TRUE": make_account(account_id="TRUE")}
    valid, invalid = validate_accounts(accounts)
    assert len(valid) == 0
    assert len(invalid) == 1
    assert invalid[0]["account_id"] == "true"


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
        {
            "account_id": "FALSE",
            "reason": "INVALID_ACCOUNT_ID",
            "region": "",
            "file": "test.csv",
        },
        {
            "account_id": "abc123",
            "reason": "NON_EMEA_REGION",
            "region": "LATAM",
            "file": "test.csv",
        },
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
    entry = {
        "account_id": "FALSE",
        "reason": "INVALID_ACCOUNT_ID",
        "region": "",
        "file": "t.csv",
    }
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
    assert VALID_ID_15.lower() in valid_15
    assert VALID_ID in valid_18


def test_csv_filename_appears_in_invalid_entries():
    accounts = {"FALSE": make_account(account_id="FALSE")}
    _, invalid = validate_accounts(accounts, csv_filename="blah.csv")
    assert invalid[0]["file"] == "blah.csv"
