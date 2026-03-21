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

    assert review_log.exists()
    assert SAMPLE_ACCOUNT_ID in review_log.read_text()
    import csv as csvlib
    if tasks_file.exists():
        rows = list(csvlib.DictReader(open(tasks_file)))
        assert not any(r.get("account_id") == SAMPLE_ACCOUNT_ID for r in rows)
