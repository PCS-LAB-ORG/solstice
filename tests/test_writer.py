import csv, json
from pathlib import Path
from datetime import date
import pytest
from agent.writer import write_approved_tasks, update_state, bootstrap_state, write_unclassified_log
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
    assert len(lines) == 1

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
    new_accounts = {SAMPLE_ACCOUNT_ID: sample_csv_row}
    update_state(sample_state, new_accounts, state_file)
    loaded = json.loads(state_file.read_text())
    assert loaded["accounts"][SAMPLE_ACCOUNT_ID]["status_changed_at"] == original_changed_at

def test_update_state_updates_expiry_alerted_date_when_expiry_risk(tmp_path, sample_csv_row, sample_state):
    state_file = tmp_path / "state.json"
    new_accounts = {SAMPLE_ACCOUNT_ID: sample_csv_row}
    update_state(sample_state, new_accounts, state_file, expiry_flagged={SAMPLE_ACCOUNT_ID})
    loaded = json.loads(state_file.read_text())
    assert loaded["accounts"][SAMPLE_ACCOUNT_ID]["expiry_alerted_date"] == date.today().isoformat()

def test_bootstrap_state_creates_state_with_accounts(tmp_path):
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
    rows = list(csv.DictReader(open(tasks_file)))
    assert len(rows) == 0

def test_write_unclassified_log_appends(tmp_path):
    log = tmp_path / "pending_review.log"
    diff = {"account_id": "abc", "customer_name": "X", "changes": []}
    write_unclassified_log([diff], log)
    content = log.read_text()
    assert "abc" in content
