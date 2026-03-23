"""
enricher.py — AI-powered comment analyser.

For each account with comments, Claude extracts:
  - blocker:     concise description of the main technical/business blocker
  - owner:       named person responsible for next action (may differ from CSE)
  - accountable: escalation owner beyond the CSE (Product, TS lead, Engineering, AE)

Results cached in state.json under accounts[id]["ai_enrichment"].
Only re-calls Claude when the comment text has changed (hash comparison).

Usage:
  python3 agent/enricher.py            # enriches state.json in-place
  from agent.enricher import enrich_accounts
"""
from __future__ import annotations
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.constants import STATE_FILE, CLASSIFIER_RETRY_DELAY_S
from agent.llm import chat

logger = logging.getLogger(__name__)

BATCH_SIZE = 15  # accounts per Claude call

ENRICHER_PROMPT = (
    "You are analysing EMEA Prisma Cloud CC Migration account notes for the EMEA leadership team.\n"
    "For each account, read the comments carefully and extract:\n"
    "  blocker:     Concise description of the main technical or business blocker preventing migration. "
    "null if no blocker is mentioned.\n"
    "  owner:       The specific named person responsible for the next action. "
    "Look for patterns like 'X to do Y', 'assigned to X', 'X will'. "
    "If only the CSE is mentioned, use their name. null if unclear.\n"
    "  accountable: The escalation owner BEYOND the CSE — a Product Manager, TS lead, Engineering contact, "
    "Account Executive, or senior stakeholder. null if only the CSE is involved.\n\n"
    "Return a JSON array of objects with exactly these fields: "
    "account_id, blocker, owner, accountable.\n"
    "Values must be short strings (max 120 chars) or null. No prose, JSON array only."
)


def _comments_hash(comments: str) -> str:
    return hashlib.md5(comments.encode("utf-8")).hexdigest()


def _needs_enrichment(acc: dict) -> bool:
    """True if account has comments that haven't been enriched yet or have changed."""
    comments = (acc.get("comments") or "").strip()
    if not comments:
        return False
    existing = acc.get("ai_enrichment") or {}
    return existing.get("comments_hash") != _comments_hash(comments)


def _enrich_batch(batch: list[dict]) -> list[dict]:
    """Send one batch to Ollama. Returns list of enrichment dicts."""
    payload = [
        {
            "account_id":    acc["account_id"],
            "customer_name": acc.get("customer_name", ""),
            "cse":           acc.get("active_cse", ""),
            "status":        acc.get("status", ""),
            "comments":      (acc.get("comments") or "")[:600],
        }
        for acc in batch
    ]

    for attempt in range(2):
        try:
            raw = chat(json.dumps({"accounts": payload}), system_prompt=ENRICHER_PROMPT, expect_json=True)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw)
            # Handle {accounts: [...]} or [...] response
            if isinstance(parsed, dict) and "accounts" in parsed:
                parsed = parsed["accounts"]
            if isinstance(parsed, list):
                return parsed
        except Exception as e:
            logger.error("Enricher attempt %d failed: %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(CLASSIFIER_RETRY_DELAY_S)

    return [{"account_id": acc["account_id"], "blocker": None, "owner": None, "accountable": None}
            for acc in batch]


def enrich_accounts(state_file: Path = STATE_FILE) -> dict:
    """
    Enrich all accounts with comments that need (re-)enrichment.
    Updates state_file in-place. Returns summary dict.
    """
    state = json.loads(state_file.read_text(encoding="utf-8"))
    accounts = state.get("accounts", {})

    # Find accounts needing enrichment
    to_enrich = [
        {"account_id": aid, **acc}
        for aid, acc in accounts.items()
        if _needs_enrichment(acc)
    ]

    if not to_enrich:
        logger.info("Enricher: all accounts up to date, nothing to do.")
        return {"enriched": 0, "skipped": len(accounts)}

    logger.info("Enricher: %d accounts need enrichment (batch size %d)", len(to_enrich), BATCH_SIZE)
    now = datetime.now(timezone.utc).isoformat()
    enriched_count = 0

    for i in range(0, len(to_enrich), BATCH_SIZE):
        batch = to_enrich[i:i + BATCH_SIZE]
        logger.info("Enricher: processing batch %d-%d of %d", i + 1, i + len(batch), len(to_enrich))
        results = _enrich_batch(batch)

        # Write results back into accounts
        result_by_id = {r["account_id"]: r for r in results}
        for acc_stub in batch:
            aid = acc_stub["account_id"]
            result = result_by_id.get(aid, {})
            comments = (accounts[aid].get("comments") or "").strip()
            accounts[aid]["ai_enrichment"] = {
                "blocker":       result.get("blocker"),
                "owner":         result.get("owner"),
                "accountable":   result.get("accountable"),
                "comments_hash": _comments_hash(comments),
                "enriched_at":   now,
            }
            enriched_count += 1

    state["accounts"] = accounts
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    logger.info("Enricher: done. %d enriched, %d skipped.", enriched_count, len(accounts) - enriched_count)
    return {"enriched": enriched_count, "skipped": len(accounts) - enriched_count}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
    result = enrich_accounts()
    print(f"Enriched: {result['enriched']} | Skipped (cached): {result['skipped']}")
