"""
blocked_parser.py — Parser for the EMEA Solstice Blocked Accounts CSV.

Business rules:
  - customer_size_cohort_classification == "Scale cohort" → team = "Customer Success"
    These accounts are managed by individual CS team members (Tunde, Mathieu, Alvaro, etc.)
  - "101-650 Customers" → team = "Named Accounts"
  - "Top 100 Customers"  → team = "Strategic Accounts"

Status Detail emoji coding:
  🛑 = hard blocked (internal or external)
  👎 = issues / behind / challenged
  ✅ = green / no blockers

Join key: pc_end_customer_account_id == state.json account_id (case-insensitive)
"""
from __future__ import annotations
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Cohort → team label
COHORT_TEAM = {
    "Scale cohort":       "Customer Success",
    "101-650 Customers":  "Named Accounts",
    "Top 100 Customers":  "Strategic Accounts",
}

# Status Detail prefix → signal
STATUS_SIGNAL = {
    "✅": "green",
    "👎": "at_risk",
    "🛑": "blocked",
}

# Status Detail subtype keywords
CORE_REP_BLOCKING = "core rep is blocking"
TECH_BLOCKER      = "technical reason"
NO_CONTACT        = "not able to contact"
ACTIVE_DEAL       = "active deal"
NO_RESPONSE       = "no response"


def _signal(status_detail: str) -> str:
    for emoji, sig in STATUS_SIGNAL.items():
        if status_detail.startswith(emoji):
            return sig
    return "unknown"


def _subtype(status_detail: str) -> str | None:
    sd = status_detail.lower()
    if CORE_REP_BLOCKING in sd:
        return "core_rep_blocking"
    if TECH_BLOCKER in sd:
        return "tech_blocker"
    if NO_CONTACT in sd:
        return "no_contact"
    if ACTIVE_DEAL in sd:
        return "active_deal"
    if NO_RESPONSE in sd:
        return "no_response"
    return None


def parse_blocked_csv(filepath: Path) -> dict[str, dict]:
    """
    Parse the blocked accounts CSV.
    Returns {account_id_lower: enrichment_dict}.
    """
    results = {}
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            acc_id = row.get("pc_end_customer_account_id", "").strip().lower()
            if not acc_id:
                continue

            cohort       = row.get("customer_size_cohort_classification", "").strip()
            status_detail = row.get("Status Detail", "").strip()
            category     = row.get("Category", "").strip()

            results[acc_id] = {
                "account_name":        row.get("pc_account_name", "").strip(),
                "area":                row.get("Account_area", "").strip(),
                "region":              row.get("account_region", "").strip(),
                "district":            row.get("account_district", "").strip(),
                "cohort":              cohort,
                "team":                COHORT_TEAM.get(cohort, cohort),
                "is_cs_team":          cohort == "Scale cohort",
                "m3_complete":         row.get("M3:EB Buy-in Meeting Complete", "").strip().upper() == "Y",
                "m3_planned":          row.get("M3 Planned date", "").strip(),
                "m8_started":          row.get("M8:Upgrade started", "").strip().upper() == "Y",
                "m8_planned":          row.get("M8 Planned date", "").strip(),
                "m9_complete":         row.get("M9:Upgrade complete", "").strip().upper() == "Y",
                "m9_planned":          row.get("M9 Planned date", "").strip(),
                "upgrade_notes":       row.get("Upgrade Notes", "").strip(),
                "health_notes":        row.get("Account Health Notes", "").strip(),
                "exec_delay":          row.get("Exec validated delay (date to be unblocked)", "").strip(),
                "status_detail":       status_detail,
                "signal":              _signal(status_detail),
                "subtype":             _subtype(status_detail),
                "milestone_category":  category,
                "notes":               row.get("Notes", "").strip(),
            }
    logger.info("Parsed %d blocked accounts", len(results))
    return results


def merge_into_state(blocked: dict[str, dict], state_file: Path) -> dict:
    """
    Merge blocked account data into state.json under accounts[id]['blocked_data'].
    Returns summary: {matched, unmatched, cs_team, core_rep_blocking}.
    """
    state = json.loads(state_file.read_text(encoding="utf-8"))
    accounts = state.get("accounts", {})

    # Build lowercase → original ID map
    id_map = {k.lower(): k for k in accounts}

    matched = 0
    unmatched = 0
    cs_team = 0
    core_rep = 0

    for acc_id_lower, data in blocked.items():
        orig_id = id_map.get(acc_id_lower)
        if orig_id:
            accounts[orig_id]["blocked_data"] = data
            matched += 1
            if data.get("is_cs_team"):
                cs_team += 1
            if data.get("subtype") == "core_rep_blocking":
                core_rep += 1
        else:
            unmatched += 1

    state["accounts"] = accounts
    state["blocked_last_updated"] = datetime.now(timezone.utc).isoformat()
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    summary = {"matched": matched, "unmatched": unmatched,
                "cs_team": cs_team, "core_rep_blocking": core_rep}
    logger.info("Blocked merge: %s", summary)
    return summary


def load_and_merge(csv_path: Path, state_file: Path) -> dict:
    """One-shot: parse CSV and merge into state."""
    blocked = parse_blocked_csv(csv_path)
    return merge_into_state(blocked, state_file)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
    from agent.constants import STATE_FILE, DATA_DIR
    csv_path = DATA_DIR / "blocked_accounts.csv"
    result = load_and_merge(csv_path, STATE_FILE)
    print(f"Matched: {result['matched']} | Unmatched: {result['unmatched']} | "
          f"CS Team: {result['cs_team']} | Core Rep Blocking: {result['core_rep_blocking']}")
