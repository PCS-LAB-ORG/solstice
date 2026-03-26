"""
dc_parser.py — Parser for the DC CSE Tracker (master source of truth).

This is the authoritative file. Its data wins over all other sources on conflict.
Filters to EMEA accounts only. Merges into state.json by account_id (Salesforce ID).

Key fields extracted:
  - CSE Assigned       → active_cse  (wins over EMEA accounts CSV)
  - PC_CC_Migration_status → dc_status
  - All M0-M9 milestone dates and completion flags
  - Email sent         → email_sent
  - Status Detail      → status_detail
  - DC assignment      → dc_assignment
  - Owner: End to end upgrade → owner_e2e
"""
from __future__ import annotations
import csv
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BOOL_YES = {"y", "yes", "true", "1", "x"}


def _yn(val: str) -> bool:
    return val.strip().lower() in BOOL_YES


def _clean_cse(val: str) -> str:
    """Return CSE name or empty string. Rejects date-like and junk values."""
    v = val.strip()
    if not v or re.match(r"^\d", v) or "/" in v or "@" in v:
        return ""
    if v.lower() in {"to be hired", "tbd", "n/a", "-"}:
        return ""
    # Known typo in DC file
    if v == "Mikhail Bahkmetiev":
        return "Mikhail Bakhmetiev"
    return v


def parse_dc_csv(filepath: Path) -> list[dict]:
    """Parse DC CSE Tracker CSV. Returns EMEA-only records."""
    records = []
    with open(filepath, newline="", encoding="utf-8-sig", errors="ignore") as f:
        for row in csv.DictReader(f):
            if row.get("account_theatre", "").strip().upper() != "EMEA":
                continue
            aid = row.get("pc_end_customer_account_id", "").strip().lower()
            if not aid:
                continue
            records.append({
                "account_id":       aid,
                "account_name":     row.get("pc_account_name", "").strip(),
                "active_cse":       _clean_cse(row.get("CSE Assigned", "")),
                "dc_assignment":    row.get("DC assignment", "").strip(),
                "owner_e2e":        row.get("Owner: End to end upgrade", "").strip(),
                "dc_status":        row.get("PC_CC_Migration_status", "").strip(),
                "cohort":           row.get("customer_size_cohort_classification", "").strip(),
                "email_sent":       row.get("Email sent", "").strip(),
                "status_detail":    row.get("Status Detail", "").strip(),
                "live_fire":        _yn(row.get("Live-fire", "")),
                # Milestones
                "m0_complete":      _yn(row.get("M0:Internal Kickoff Complete", "")),
                "m1_complete":      _yn(row.get("M1:Customer Outreach Complete", "")),
                "m1_planned":       row.get("Date - M1:Internal Kickoff Complete", "").strip(),
                "m2_complete":      _yn(row.get("M2:Entitlements and Plan aligned with customer", "")),
                "m2_planned":       row.get("Date - M2:Entitlements and Plan aligned with customer", "").strip(),
                "m3_complete":      _yn(row.get("M3:EB Buy-in Meeting Complete", "")),
                "m3_planned":       row.get("M3 Planned date", "").strip(),
                "m3_actual":        row.get("Date - M3:EB Buy-in Meeting Complete", "").strip(),
                "m4_complete":      _yn(row.get("M4:Discovery complete", "")),
                "m4_planned":       row.get("Date - M4:Discovery complete", "").strip(),
                "m5_complete":      _yn(row.get("M5:Tech validation complete", "")),
                "m5_planned":       row.get("Date - M5:Tech validation complete", "").strip(),
                "m7_complete":      _yn(row.get("M7:Legal and operational upgrade readiness", "")),
                "m8_started":       _yn(row.get("M8:Upgrade started", "")),
                "m8_planned":       row.get("M8 Planned date", "").strip(),
                "m8_actual":        row.get("Date - M8:Upgrade started", "").strip(),
                "m9_complete":      _yn(row.get("M9:Upgrade complete", "")),
                "m9_planned":       row.get("M9 Planned date", "").strip(),
                "m9_actual":        row.get("Date - M9:Upgrade complete", "").strip(),
                "upgrade_notes":    row.get("Upgrade Notes", "").strip(),
                "health_notes":     row.get("Account Health Notes", "").strip(),
                "pm_status":        row.get("PM Status", "").strip(),
                "dc_progress":      row.get("DC Upgrade Progress Status", "").strip(),
                "cc_rep":           row.get("cc_Rep (SPO)", "").strip(),
                "cc_dsm":           row.get("cc_DSM (SPO)", "").strip(),
                "churn_risk":       row.get("DC Indicated account churn risk", "").strip(),
                "merged_at":        datetime.now(timezone.utc).isoformat(),
            })
    logger.info("DC CSE Tracker: parsed %d EMEA records", len(records))
    return records


def merge_into_state(records: list[dict], state_file: Path) -> dict:
    """
    Merge DC records into state.json by account_id.
    DC CSE Tracker wins on: active_cse, email_sent, all milestone fields.
    Returns summary dict.
    """
    state = json.loads(state_file.read_text(encoding="utf-8"))
    accounts = state.get("accounts", {})

    # Build case-insensitive ID lookup (state keys may be mixed case)
    lower_map = {k.lower(): k for k in accounts}

    matched = 0
    unmatched = []

    for rec in records:
        aid_lower = rec["account_id"]  # already lowercased by parse_dc_csv
        aid = lower_map.get(aid_lower)
        if aid is None:
            unmatched.append(rec["account_name"])
            continue

        acc = accounts[aid]

        # DC always wins on CSE
        if rec["active_cse"]:
            acc["active_cse"] = rec["active_cse"]

        # DC always wins on email_sent (if it has a value)
        if rec["email_sent"]:
            acc["email_sent"] = rec["email_sent"]

        # DC live_fire wins if True
        if rec["live_fire"]:
            acc["live_fire"] = True

        # Store full DC data for milestone access
        acc["dc_data"] = rec
        matched += 1

    state["accounts"] = accounts
    state["dc_last_updated"] = datetime.now(timezone.utc).isoformat()
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    logger.info("DC merge: %d/%d matched, %d unmatched",
                matched, len(records), len(unmatched))
    return {"total": len(records), "matched": matched,
            "unmatched": len(unmatched), "unmatched_list": unmatched}


def load_and_merge(csv_path: Path, state_file: Path) -> dict:
    """One-shot: parse and merge."""
    return merge_into_state(parse_dc_csv(csv_path), state_file)
