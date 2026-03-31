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

            def _g(col): return row.get(col, "").strip()
            def _yn(col): return _g(col).upper() == "Y"

            results[acc_id] = {
                "account_name":        _g("pc_account_name"),
                "area":                _g("Account_area"),
                "region":              _g("account_region"),
                "district":            _g("account_district"),
                "cohort":              cohort,
                "team":                COHORT_TEAM.get(cohort, cohort),
                "is_cs_team":          cohort == "Scale cohort",
                # ── Milestones (current CSV: M3/M8/M9; DC CSV will add M0-M7) ──
                "m0_complete":         _yn("M0:Internal Kickoff Complete"),
                "m0_planned":          _g("M0 Planned date"),
                "m1_complete":         _yn("M1:Customer Outreach Complete"),
                "m1_planned":          _g("M1 Planned date"),
                "m1_details":          _g("M1 Details"),
                "m2_complete":         _yn("M2:Entitlements and Plan aligned with customer"),
                "m2_planned":          _g("M2 Planned date"),
                "m2_details":          _g("M2 Details"),
                "m3_complete":         _yn("M3:EB Buy-in Meeting Complete"),
                "m3_planned":          _g("M3 Planned date"),
                "m3_details":          _g("M3 Details"),
                "m4_complete":         _yn("M4:Discovery complete"),
                "m4_planned":          _g("M4 Planned date"),
                "m5_complete":         _yn("M5:Tech validation complete"),
                "m5_planned":          _g("M5 Planned date"),
                "m5_details":          _g("M5 Details"),
                "m7_complete":         _yn("M7:Legal and operational upgrade readiness"),
                "m7_planned":          _g("M7 Planned date"),
                "m8_started":          _yn("M8:Upgrade started"),
                "m8_planned":          _g("M8 Planned date"),
                "m8_details":          _g("M8 Details"),
                "m9_complete":         _yn("M9:Upgrade complete"),
                "m9_planned":          _g("M9 Planned date"),
                "m9_details":          _g("M9 Details"),
                # ── Notes and status ──
                "upgrade_notes":       _g("Upgrade Notes"),
                "health_notes":        _g("Account Health Notes"),
                "exec_delay":          _g("Exec validated delay (date to be unblocked)"),
                "pm_status":           _g("PM Status"),
                "pm_notes":            _g("PM Upgrade Notes"),
                "provisioning_status": _g("Provisioning status"),
                "activation_status":   _g("activation_tenant_status"),
                "accountable_dc_cse":  _g("Accountable DC/CSE name"),
                "owner_e2e":           _g("Owner: End to end upgrade"),
                "next_milestone":      _g("Next milestone"),
                "upgrade_partner":     _g("Upgrade partner name"),
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


def check_milestone_stalls(accounts: dict) -> list[dict]:
    """
    Detect accounts stalled between milestones beyond allowed timelines.
    Rules (Scale cohort only, effective 2026-03-09, prospective):
      M3 → M8: 14 days max (M3 complete but M8 not started)
      M8 → M9: 28 days max (M8 started but M9 not complete)
    M0→M1 and M1→M3 not enforced yet (no date data available).

    Returns list of stall dicts sorted by days_stalled descending.
    """
    from datetime import datetime, date, timezone
    from agent.constants import MILESTONE_MAX_DAYS, MILESTONE_RULES_EFFECTIVE, MILESTONE_RULES_COHORT

    effective_date = date.fromisoformat(MILESTONE_RULES_EFFECTIVE)
    today = datetime.now(timezone.utc).date()
    stalls = []

    def _parse(s: str):
        if not s: return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try: return datetime.strptime(s.strip(), fmt).date()
            except: pass
        return None

    for aid, acc in accounts.items():
        bd = acc.get("blocked_data", {})
        if not bd: continue
        if not bd.get("is_cs_team"): continue                    # Scale cohort only
        if acc.get("ps_data", {}).get("ps_status"): continue     # PS customers exempt
        if acc.get("status") in ("Completed", "Cancelled", "Churning/Churned"): continue

        m3_done  = bd.get("m3_complete", False)
        m8_done  = bd.get("m8_started",  False)
        m9_done  = bd.get("m9_complete", False)
        m3_date  = _parse(bd.get("m3_planned", ""))
        m8_date  = _parse(bd.get("m8_planned", ""))
        m9_date  = _parse(bd.get("m9_planned", ""))
        name     = acc.get("customer_name", "—")
        cse      = acc.get("active_cse", "") or "⚠ NO OWNER"

        # M3 → M8: M3 complete, M8 not started, reference date = m3_planned
        if m3_done and not m8_done and m3_date:
            ref = max(m3_date, effective_date)  # no retroactive
            days_stalled = (today - ref).days
            if days_stalled >= MILESTONE_MAX_DAYS["M3_M8"]:
                stalls.append({
                    "account_id":   aid,
                    "customer_name": name,
                    "cse":          cse,
                    "transition":   "M3 → M8",
                    "max_days":     MILESTONE_MAX_DAYS["M3_M8"],
                    "days_stalled": days_stalled,
                    "over_by":      days_stalled - MILESTONE_MAX_DAYS["M3_M8"],
                    "ref_date":     ref.isoformat(),
                    "status":       acc.get("status", "—"),
                    "signal":       bd.get("signal", ""),
                })

        # M8 → M9: M8 started, M9 not complete, reference date = m8_planned
        if m8_done and not m9_done and m8_date:
            ref = max(m8_date, effective_date)
            days_stalled = (today - ref).days
            if days_stalled >= MILESTONE_MAX_DAYS["M8_M9"]:
                stalls.append({
                    "account_id":   aid,
                    "customer_name": name,
                    "cse":          cse,
                    "transition":   "M8 → M9",
                    "max_days":     MILESTONE_MAX_DAYS["M8_M9"],
                    "days_stalled": days_stalled,
                    "over_by":      days_stalled - MILESTONE_MAX_DAYS["M8_M9"],
                    "ref_date":     ref.isoformat(),
                    "status":       acc.get("status", "—"),
                    "signal":       bd.get("signal", ""),
                })

    stalls.sort(key=lambda x: -x["over_by"])
    return stalls


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
