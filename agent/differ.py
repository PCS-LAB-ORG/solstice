from __future__ import annotations
import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from agent.constants import (
    CSV_COL_ACCOUNT_ID, CSV_COL_CUSTOMER_NAME, CSV_COL_ARR,
    CSV_COL_ACTIVE_CSE, CSV_COL_BACKUP_CSE, CSV_COL_STATUS,
    CSV_COL_SALES_REGION, CSV_COL_COMMENTS, CSV_COL_EXPIRATION_DATE,
    CSV_COL_PS_ENGAGED, CSV_COL_KICKOFF_DATE, CSV_COL_EMAIL_SENT,
    BLOCKER_COL_INDICES, BLOCKER_COLS,
    ESCALATION_STATUSES, OUTREACH_STATUSES,
    CUSTOMER_OUTREACH_STALE_DAYS, EXPIRY_RISK_DAYS,
)


def _parse_row(row: list) -> Optional[dict[str, Any]]:
    """Convert a raw CSV row into an account dict. Returns None if no account_id."""
    account_id = row[CSV_COL_ACCOUNT_ID].strip()
    if not account_id:
        return None
    active_blockers = [
        BLOCKER_COLS[i]
        for i, col_idx in enumerate(BLOCKER_COL_INDICES)
        if col_idx < len(row) and row[col_idx].strip()
    ]
    def _get(idx):
        return row[idx].strip() if idx < len(row) else ""
    return {
        "account_id": account_id,
        "customer_name": _get(CSV_COL_CUSTOMER_NAME),
        "arr": _get(CSV_COL_ARR),
        "active_cse": _get(CSV_COL_ACTIVE_CSE),
        "backup_cse": _get(CSV_COL_BACKUP_CSE),
        "status": _get(CSV_COL_STATUS),
        "sales_region": _get(CSV_COL_SALES_REGION),
        "comments": _get(CSV_COL_COMMENTS),
        "expiration_date": _get(CSV_COL_EXPIRATION_DATE),
        "ps_engaged": _get(CSV_COL_PS_ENGAGED),
        "kickoff_date": _get(CSV_COL_KICKOFF_DATE),
        "email_sent": _get(CSV_COL_EMAIL_SENT),
        "blockers": active_blockers,
    }


def parse_csv(filepath: Path) -> dict[str, dict]:
    """Parse CSV export. Returns {account_id: account_dict}."""
    accounts = {}
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            parsed = _parse_row(row)
            if parsed:
                accounts[parsed["account_id"]] = parsed
    return accounts


def _parse_expiry_date(date_str: str) -> Optional[date]:
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


TRACKED_FIELDS = [
    ("status", "Status"),
    ("customer_name", "Customer name"),
    ("arr", "ARR"),
    ("active_cse", "Active CSE"),
    ("backup_cse", "Backup CSE"),
    ("sales_region", "Sales region"),
    ("expiration_date", "Expiration date"),
    ("ps_engaged", "PS Engaged"),
    ("kickoff_date", "Kickoff Date"),
    ("email_sent", "Email Sent"),
    ("comments", "Comments"),
]


def compute_diffs(new_accounts: dict, state: dict) -> list[dict]:
    """
    PASS 1: diff new_accounts vs state["accounts"] — field changes.
    PASS 2: date-check — flag expiry risk independent of changes.
    Returns list of diff dicts for classifier.
    """
    state_accounts = state.get("accounts", {})
    today = date.today()
    diffs = []

    for account_id, new in new_accounts.items():
        prev = state_accounts.get(account_id)
        diff = {
            "account_id": account_id,
            "customer_name": new["customer_name"],
            "region": new["sales_region"],
            "cse": new["active_cse"],
            "changes": [],
            "escalation": False,
            "stale_outreach": False,
            "expiry_risk": False,
            "new_account": prev is None,
            "comments": new["comments"],
        }

        if prev is None:
            diff["changes"].append({"field": "Status", "old": None, "new": new["status"]})
        else:
            for field_key, field_label in TRACKED_FIELDS:
                old_val = prev.get(field_key, "")
                new_val = new.get(field_key, "")
                if old_val != new_val:
                    diff["changes"].append({"field": field_label, "old": old_val, "new": new_val})

            old_blockers = set(prev.get("blockers", []))
            new_blockers = set(new.get("blockers", []))
            for b in new_blockers - old_blockers:
                diff["changes"].append({"field": "Blocker", "old": None, "new": b})

            if new["status"] in ESCALATION_STATUSES and prev.get("status") != new["status"]:
                diff["escalation"] = True

            if new["status"] in OUTREACH_STATUSES:
                changed_at_str = prev.get("status_changed_at", "")
                if changed_at_str:
                    try:
                        changed_at = datetime.fromisoformat(
                            changed_at_str.replace("Z", "+00:00")
                        ).date()
                        if (today - changed_at).days > CUSTOMER_OUTREACH_STALE_DAYS:
                            diff["stale_outreach"] = True
                    except ValueError:
                        pass

        # PASS 2: expiry risk
        expiry_date = _parse_expiry_date(new.get("expiration_date", ""))
        if expiry_date:
            alerted_str = (prev or {}).get("expiry_alerted_date")
            already_alerted = alerted_str == today.isoformat() if alerted_str else False
            if not already_alerted and (expiry_date - today).days <= EXPIRY_RISK_DAYS:
                diff["expiry_risk"] = True

        if diff["changes"] or diff["stale_outreach"] or diff["expiry_risk"]:
            diffs.append(diff)

    return diffs
