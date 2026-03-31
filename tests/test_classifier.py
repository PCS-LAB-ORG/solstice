import json
from unittest.mock import patch
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

OLLAMA_RESPONSE = json.dumps([{
    "account_id": "abc123",
    "category": "ESCALATION",
    "priority": "HIGH",
    "suggested_action": "Escalate to regional manager.",
}])


def test_build_message_includes_account_id():
    msg = _build_message([SAMPLE_DIFF])
    assert "abc123" in msg


def test_build_message_is_valid_json():
    msg = _build_message([SAMPLE_DIFF])
    parsed = json.loads(msg)
    assert "accounts" in parsed
    assert parsed["accounts"][0]["account_id"] == "abc123"


def test_classify_diffs_returns_classification():
    with patch("agent.classifier.chat", return_value=OLLAMA_RESPONSE):
        results = classify_diffs([SAMPLE_DIFF])
    assert len(results) == 1
    assert results[0]["account_id"] == "abc123"
    assert results[0]["category"] == "ESCALATION"
    assert results[0]["priority"] == "HIGH"
    assert "suggested_action" in results[0]


def test_classify_diffs_retries_on_failure():
    call_count = {"n": 0}
    def chat_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise Exception("network error")
        return OLLAMA_RESPONSE

    with patch("agent.classifier.chat", side_effect=chat_side_effect), \
         patch("agent.classifier.time.sleep"):
        results = classify_diffs([SAMPLE_DIFF])
    assert call_count["n"] == 2
    assert results[0]["category"] == "ESCALATION"


def test_classify_diffs_returns_unclassified_after_two_failures():
    with patch("agent.classifier.chat", side_effect=Exception("always fails")), \
         patch("agent.classifier.time.sleep"):
        results = classify_diffs([SAMPLE_DIFF])
    assert results[0]["category"] == "UNCLASSIFIED"
    assert results[0]["account_id"] == "abc123"


def test_classify_diffs_handles_invalid_json_response():
    with patch("agent.classifier.chat", return_value="not json at all"), \
         patch("agent.classifier.time.sleep"):
        results = classify_diffs([SAMPLE_DIFF])
    assert results[0]["category"] == "UNCLASSIFIED"
