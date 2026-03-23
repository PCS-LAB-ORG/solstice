import json
import logging
import time
from typing import Any

from agent.constants import CLASSIFIER_RETRY_DELAY_S, SYSTEM_PROMPT
from agent.llm import chat

logger = logging.getLogger(__name__)


def _build_message(diffs: list) -> str:
    accounts = []
    for d in diffs:
        accounts.append({
            "account_id":    d["account_id"],
            "customer_name": d["customer_name"],
            "region":        d["region"],
            "cse":           d["cse"],
            "changes":       d["changes"],
            "expiry_risk":   d.get("expiry_risk", False),
            "stale_outreach":d.get("stale_outreach", False),
            "comments":      d.get("comments", "")[:500],
        })
    return json.dumps({"accounts": accounts})


def _unclassified_results(diffs: list) -> list:
    return [
        {
            "account_id":      d["account_id"],
            "category":        "UNCLASSIFIED",
            "priority":        "HIGH",
            "suggested_action":"Manual review required — classifier failed.",
        }
        for d in diffs
    ]


def classify_diffs(diffs: list) -> list:
    if not diffs:
        return []

    message_content = _build_message(diffs)

    for attempt in range(2):
        try:
            raw = chat(message_content, system_prompt=SYSTEM_PROMPT, expect_json=True)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            # Ollama format=json may return object or array
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "accounts" in parsed:
                parsed = parsed["accounts"]
            if not isinstance(parsed, list):
                raise ValueError(f"Expected JSON array, got: {type(parsed)}")
            return parsed
        except Exception as e:
            logger.error("Classifier attempt %d failed: %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(CLASSIFIER_RETRY_DELAY_S)

    logger.error("Classifier failed after 2 attempts — UNCLASSIFIED for %d accounts", len(diffs))
    return _unclassified_results(diffs)
