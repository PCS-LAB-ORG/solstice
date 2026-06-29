"""
Parser for the "Detailed Account List" sheet (gid=0) of the DC CSE Tracker.
Handles both UTF-16 tab-delimited (manual Drive export) and UTF-8 CSV (auto export).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


def emoji_to_signal(val: str) -> str:
    v = val.strip()
    if v == "🟢":
        return "green"
    if v == "🟡":
        return "at_risk"
    if v == "🔴":
        return "blocked"
    return ""


def emoji_to_churn(val: str) -> str:
    v = val.strip()
    if v == "🔴":
        return "Red"
    if v == "🟡":
        return "Yellow"
    if v == "🟢":
        return "Green"
    return ""


def _yn(val: str) -> bool:
    return val.strip().upper() == "Y"


def _synthetic_id(name: str) -> str:
    return hashlib.md5(name.lower().strip().encode()).hexdigest()[:15]


def parse_row(row: dict, account_id: str) -> dict:
    """Parse one CSV row into a record dict. account_id may be pre-looked-up or empty string."""
    name = (row.get("Pc Account Name") or "").strip()
    aid = account_id if account_id else _synthetic_id(name)
    return {
        "account_id": aid,
        "account_name": name,
        "account_theatre": "EMEA",
        "sales_region": (row.get("Account District") or "").strip(),
        "arr": (row.get("ARR") or "").strip(),
        "active_cse": (row.get("DC assignment") or "").strip(),
        "cc_rep": (row.get("CC Rep (SPO)") or "").strip(),
        "signal": emoji_to_signal(row.get("DC Upgrade Status", "")),
        "churn_risk": emoji_to_churn(row.get("DC Indicated Churn Risk", "")),
        "m0_complete": _yn(row.get("M0:Internal Kickoff Complete", "")),
        "m1_complete": _yn(row.get("M1:Customer Outreach Complete", "")),
        "m2_complete": _yn(
            row.get("M2:Entitlements and Plan aligned with customer", "")
        ),
        "m3_complete": _yn(row.get("M3:EB Buy-in Meeting Complete", "")),
        "m4_complete": _yn(row.get("M4:Discovery complete", "")),
        "m5_complete": _yn(row.get("M5:Tech validation complete", "")),
        "m6_complete": _yn(row.get("M6: Activated", "")),
        "m7_complete": _yn(row.get("M7: PS Readiness", "")),
        "m8_started": _yn(row.get("M8:Upgrade started", "")),
        "m9_complete": _yn(row.get("M9:Upgrade complete", "")),
        "m3_planned": (row.get("M3 Planned date") or "").strip(),
        "m8_planned": (row.get("M8 Planned date") or "").strip(),
        "m9_planned": (row.get("M9 Planned date") or "").strip(),
        "status_detail": (row.get("Status Detail") or "").strip(),
        "health_notes": (row.get("Account Health Notes") or "").strip(),
        "upgrade_notes": (row.get("Upgrade Notes") or "").strip(),
        "next_renewal_date": (row.get("Next Cloud Renewal Date") or "").strip(),
        "dc_progress": "",
        "subtype": "",
    }


def _open_csv(filepath: Path) -> list[dict]:
    """Try UTF-16 tab-delimited first (manual Drive export), fall back to UTF-8 CSV."""
    for enc, delim in [("utf-16", "\t"), ("utf-8-sig", ","), ("latin-1", ",")]:
        try:
            with open(filepath, encoding=enc, newline="") as f:
                reader = csv.DictReader(f, delimiter=delim)
                rows = list(reader)
                if rows and "Pc Account Name" in (rows[0] or {}):
                    return rows
        except Exception:
            continue
    raise ValueError(f"Cannot parse {filepath} — unsupported encoding/delimiter")


def parse_account_list_csv(
    filepath: Path, name_to_id: dict | None = None
) -> list[dict]:
    """
    Parse the Detailed Account List CSV.
    name_to_id: {lower_name: account_id} lookup. Returns list of record dicts.
    """
    lookup = name_to_id or {}
    rows = _open_csv(filepath)
    records = []
    for row in rows:
        name = (row.get("Pc Account Name") or "").strip()
        if not name:
            continue
        aid = lookup.get(name.lower(), "")
        records.append(parse_row(row, aid))
    return records


def load_name_to_id(data_dir: Path) -> dict:
    """Load the pre-built name→Salesforce-ID lookup."""
    p = data_dir / "name_to_id.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}
