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
    with patch("agent.approver.Prompt.ask", side_effect=["a", "s"]):
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
