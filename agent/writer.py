from __future__ import annotations
import csv
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from agent.constants import PENDING_TASKS_HEADER
from agent.db import get_db, init_db, upsert_account, DB_PATH

logger = logging.getLogger(__name__)


def write_approved_tasks(tasks: list, output_file: Path) -> None:
    """Append approved tasks to CSV. Creates file with header if it doesn't exist."""
    file_exists = output_file.exists() and output_file.stat().st_size > 0
    with open(output_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PENDING_TASKS_HEADER, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for task in tasks:
            writer.writerow(task)


def update_state(
    current_state: dict,
    new_accounts: dict,
    state_file: Path,
    expiry_flagged: Optional[set] = None,
) -> None:
    """Update state.json. status_changed_at updated ONLY on status change."""
    expiry_flagged = expiry_flagged or set()
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    state_accounts = current_state.get("accounts", {})

    for account_id, new in new_accounts.items():
        prev = state_accounts.get(account_id, {})
        prev_status = prev.get("status", "")
        new_status = new.get("status", "")

        state_accounts[account_id] = {
            "customer_name": new.get("customer_name", ""),
            "arr": new.get("arr", ""),
            "active_cse": new.get("active_cse", ""),
            "backup_cse": new.get("backup_cse", ""),
            "status": new_status,
            "status_changed_at": now if new_status != prev_status else prev.get("status_changed_at", now),
            "expiration_date": new.get("expiration_date", ""),
            "expiry_alerted_date": today if account_id in expiry_flagged else prev.get("expiry_alerted_date"),
            "ps_engaged": new.get("ps_engaged", ""),
            "kickoff_date": new.get("kickoff_date", ""),
            "comments": new.get("comments", ""),
            "sales_region": new.get("sales_region", ""),
            "email_sent": new.get("email_sent", ""),
            "blockers": new.get("blockers", []),
            "last_seen": now,
        }

    state_file.write_text(json.dumps(
        {"last_run": now, "accounts": state_accounts},
        indent=2, ensure_ascii=False,
    ))

    # Sync to SQLite DB
    try:
        init_db()
        with get_db() as conn:
            for account_id, acc in state_accounts.items():
                upsert_account(conn, account_id, acc)
    except Exception as e:
        logger.warning("DB sync failed (non-fatal): %s", e)

    logger.info("State updated: %d accounts", len(state_accounts))


def bootstrap_state(accounts: dict, state_file: Path, tasks_file: Path) -> None:
    """First-run bootstrap. No tasks generated. pending_tasks.csv gets header only."""
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date().isoformat()
    state_accounts = {}

    for account_id, acc in accounts.items():
        state_accounts[account_id] = {
            "customer_name": acc.get("customer_name", ""),
            "arr": acc.get("arr", ""),
            "active_cse": acc.get("active_cse", ""),
            "backup_cse": acc.get("backup_cse", ""),
            "status": acc.get("status", ""),
            "status_changed_at": today + "T00:00:00Z",  # prevents stale-outreach on first run
            "expiration_date": acc.get("expiration_date", ""),
            "expiry_alerted_date": None,
            "ps_engaged": acc.get("ps_engaged", ""),
            "kickoff_date": acc.get("kickoff_date", ""),
            "comments": acc.get("comments", ""),
            "sales_region": acc.get("sales_region", ""),
            "email_sent": acc.get("email_sent", ""),
            "blockers": acc.get("blockers", []),
            "last_seen": now,
        }

    state_file.write_text(json.dumps(
        {"last_run": now, "accounts": state_accounts},
        indent=2, ensure_ascii=False,
    ))
    with open(tasks_file, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=PENDING_TASKS_HEADER).writeheader()

    print(f"Bootstrap complete. {len(accounts)} accounts loaded. Drop a new CSV to begin monitoring.")


def write_unclassified_log(unclassified: list, log_file: Path) -> None:
    """Append UNCLASSIFIED accounts to pending_review.log."""
    now = datetime.now(timezone.utc).isoformat()
    with open(log_file, "a", encoding="utf-8") as f:
        for diff in unclassified:
            f.write(f"[{now}] UNCLASSIFIED: {diff['account_id']} ({diff.get('customer_name', '')})\n")
            f.write(f"  Changes: {diff.get('changes', [])}\n\n")
