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
        with patch("agent.classifier.time.sleep"):
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
