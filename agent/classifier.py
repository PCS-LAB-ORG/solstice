import json
import logging
import time
from typing import Any

from agent.constants import (
    VERTEX_PROJECT, VERTEX_REGION, VERTEX_MODEL,
    CLASSIFIER_MAX_TOKENS, CLASSIFIER_RETRY_DELAY_S, SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def _get_client():
    from anthropic import AnthropicVertex
    return AnthropicVertex(project_id=VERTEX_PROJECT, region=VERTEX_REGION)


def _build_message(diffs: list) -> str:
    accounts = []
    for d in diffs:
        accounts.append({
            "account_id": d["account_id"],
            "customer_name": d["customer_name"],
            "region": d["region"],
            "cse": d["cse"],
            "changes": d["changes"],
            "expiry_risk": d.get("expiry_risk", False),
            "stale_outreach": d.get("stale_outreach", False),
            "comments": d.get("comments", "")[:500],
        })
    return json.dumps({"accounts": accounts})


def _unclassified_results(diffs: list) -> list:
    return [
        {
            "account_id": d["account_id"],
            "category": "UNCLASSIFIED",
            "priority": "HIGH",
            "suggested_action": "Manual review required — classifier failed.",
        }
        for d in diffs
    ]


def classify_diffs(diffs: list) -> list:
    if not diffs:
        return []

    client = _get_client()
    message_content = _build_message(diffs)

    for attempt in range(2):
        try:
            response = client.messages.create(
                model=VERTEX_MODEL,
                max_tokens=CLASSIFIER_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": message_content}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            results = json.loads(raw)
            if not isinstance(results, list):
                raise ValueError("Expected JSON array from Claude")
            return results
        except Exception as e:
            logger.error("Classifier attempt %d failed: %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(CLASSIFIER_RETRY_DELAY_S)

    logger.error("Classifier failed after 2 attempts — UNCLASSIFIED for %d accounts", len(diffs))
    return _unclassified_results(diffs)
