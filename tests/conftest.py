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
