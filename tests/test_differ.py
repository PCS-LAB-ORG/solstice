import csv, io, json, tempfile, os
from datetime import date, timedelta
from pathlib import Path
import pytest
from agent.differ import parse_csv, compute_diffs

SAMPLE_ACCOUNT_ID = "0010g00001j67uzaaq"

def make_csv_file(rows_by_index: dict) -> Path:
    """Create a temp CSV with exact column layout matching real file."""
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
    f = make_csv_file({0: SAMPLE_ACCOUNT_ID, 17: "Yes"})  # BYOK required? at index 17
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
    # status_changed_at is 20 days ago, status = Ready To Engage -> stale_outreach fires
    new = {SAMPLE_ACCOUNT_ID: sample_csv_row}
    diffs = compute_diffs(new, sample_state)
    stale = [d for d in diffs if d.get("stale_outreach")]
    assert len(stale) == 1, "Expected stale_outreach to fire for 20-day-old Ready To Engage status"
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
