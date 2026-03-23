"""
ps_parser.py — Parser for the EMEA Cortex Cloud PS Tracker CSV.

PS  = Professional Services
PSC = PS Consultant (the individual doing the work)
PM  = Project Manager

No Salesforce ID in this file — joins to state.json by fuzzy customer name matching.
Match confidence >= 0.72 required; unmatched accounts logged as warnings.

Usage:
  python3 agent/ps_parser.py   # merges into state.json, prints summary
  from agent.ps_parser import load_and_merge
"""
from __future__ import annotations
import csv
import json
import logging
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.85   # minimum similarity — below this creates false matches (e.g. Engie→Enaire)


def _normalise(name: str) -> str:
    """Lowercase, strip legal suffixes and punctuation for fuzzy comparison."""
    name = name.lower().strip()
    # Remove common legal suffixes
    for suffix in [
        r"\bplc\b", r"\bltd\.?", r"\bllc\b", r"\bs\.?a\.?s?\.?", r"\bs\.?p\.?a\.?",
        r"\bg\.?m\.?b\.?h\.?", r"\ba\.?g\.?", r"\bnv\b", r"\bbv\b", r"\bab\b",
        r"\bsa\b", r"\binc\.?", r"\bcorp\.?\b", r"\bgroup\b", r"\bholding\b",
    ]:
        name = re.sub(suffix, "", name)
    # Strip punctuation and extra whitespace
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalise(a), _normalise(b)).ratio()


def _best_match(ps_name: str, state_names: list[str]) -> tuple[str | None, float]:
    """Return (best_state_name, score) or (None, 0) if no match above threshold."""
    best_name, best_score = None, 0.0
    for sname in state_names:
        score = _similarity(ps_name, sname)
        if score > best_score:
            best_score = score
            best_name = sname
    if best_score >= FUZZY_THRESHOLD:
        return best_name, best_score
    return None, best_score


def parse_ps_csv(filepath: Path) -> list[dict]:
    """Parse PS tracker CSV. Returns list of PS account dicts."""
    records = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("PS Eligible Account Name", "").strip()
            if not name:
                continue
            records.append({
                "ps_name":        name,
                "country":        row.get("Country", "").strip(),
                "psc":            row.get("Assigned PSC", "").strip(),
                "psc_shadow":     row.get("Shadowed PSC", "").strip(),
                "pm":             row.get("Assigned PM", "").strip(),
                "ps_status":      row.get("Status", "").strip(),
                "clarizen_id":    row.get("Clarizen Project", "").strip(),
                "timeline":       row.get("Estimated Time for PS Engagement", "").strip(),
                "notes":          row.get("Notes", "").strip(),
            })
    logger.info("Parsed %d PS accounts", len(records))
    return records


def merge_into_state(ps_records: list[dict], state_file: Path) -> dict:
    """
    Fuzzy-match PS accounts to state.json by customer name.
    Writes ps_data into matched accounts. Returns summary.
    """
    state = json.loads(state_file.read_text(encoding="utf-8"))
    accounts = state.get("accounts", {})

    # Build name → account_id map for all state accounts
    state_names = {acc.get("customer_name", ""): aid
                   for aid, acc in accounts.items()
                   if acc.get("customer_name", "").strip()}
    name_list = list(state_names.keys())

    matched = 0
    unmatched = []
    low_confidence = []
    now = datetime.now(timezone.utc).isoformat()

    for rec in ps_records:
        best_name, score = _best_match(rec["ps_name"], name_list)
        if best_name:
            aid = state_names[best_name]
            accounts[aid]["ps_data"] = {
                **rec,
                "match_confidence": round(score, 3),
                "matched_name":     best_name,
                "merged_at":        now,
            }
            matched += 1
            if score < 0.85:
                low_confidence.append((rec["ps_name"], best_name, score))
                logger.debug("Low-confidence match: %r → %r (%.2f)", rec["ps_name"], best_name, score)
        else:
            unmatched.append(rec["ps_name"])
            logger.warning("No match for PS account: %r (best score %.2f)", rec["ps_name"], score)

    state["accounts"] = accounts
    state["ps_last_updated"] = now
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    summary = {
        "total":          len(ps_records),
        "matched":        matched,
        "unmatched":      len(unmatched),
        "low_confidence": len(low_confidence),
        "unmatched_list": unmatched,
        "low_conf_list":  low_confidence,
    }
    logger.info("PS merge: %d/%d matched, %d unmatched, %d low-confidence",
                matched, len(ps_records), len(unmatched), len(low_confidence))
    return summary


def load_and_merge(csv_path: Path, state_file: Path) -> dict:
    """One-shot: parse and merge."""
    return merge_into_state(parse_ps_csv(csv_path), state_file)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
    from agent.constants import STATE_FILE, DATA_DIR
    result = load_and_merge(DATA_DIR / "ps_tracker.csv", STATE_FILE)
    print(f"\nMatched:        {result['matched']}/{result['total']}")
    print(f"Unmatched:      {result['unmatched']}")
    print(f"Low-confidence: {result['low_confidence']}")
    if result["unmatched_list"]:
        print("\nUnmatched PS accounts (not in EMEA tracker):")
        for n in result["unmatched_list"]:
            print(f"  — {n}")
    if result["low_conf_list"]:
        print("\nLow-confidence matches (review manually):")
        for ps, st, sc in result["low_conf_list"]:
            print(f"  {sc:.2f}  {ps!r} → {st!r}")
