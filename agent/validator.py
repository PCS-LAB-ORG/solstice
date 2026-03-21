from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from agent.constants import SALESFORCE_ID_PATTERN, REGIONS

logger = logging.getLogger(__name__)

_REASON_LABELS = {
    "INVALID_ACCOUNT_ID": "Not a valid Salesforce ID (expected 15-18 alphanumeric chars)",
    "NON_EMEA_REGION": "Not in EMEA REGIONS list",
}


def validate_accounts(
    accounts: dict, csv_filename: str = ""
) -> tuple[dict, list[dict]]:
    """
    Split accounts into (valid, invalid).
    valid:   {account_id: account_dict} — safe to pass to compute_diffs()
    invalid: list of {"account_id": str, "reason": str, "region": str, "file": str}

    Rules (applied in order):
    1. account_id must match SALESFORCE_ID_PATTERN (15-18 alphanumeric chars)
    2. sales_region must be in REGIONS or empty (empty = unknown, not blocked)
    """
    valid: dict = {}
    invalid: list[dict] = []

    for account_id, acc in accounts.items():
        # Rule 1: Salesforce ID format
        if not account_id or not SALESFORCE_ID_PATTERN.match(account_id):
            invalid.append({
                "account_id": account_id,
                "reason": "INVALID_ACCOUNT_ID",
                "region": acc.get("sales_region", ""),
                "file": csv_filename,
            })
            logger.debug("INVALID_ACCOUNT_ID: %s (file=%s)", account_id, csv_filename)
            continue

        # Rule 2: EMEA region check (empty region passes — unknown, not confirmed non-EMEA)
        region = acc.get("sales_region", "")
        if region and region not in REGIONS:
            invalid.append({
                "account_id": account_id,
                "reason": "NON_EMEA_REGION",
                "region": region,
                "file": csv_filename,
            })
            logger.debug(
                "NON_EMEA_REGION: %s region=%s (file=%s)", account_id, region, csv_filename
            )
            continue

        valid[account_id] = acc

    return valid, invalid


def write_validation_errors(invalid_entries: list[dict], log_file: Path) -> None:
    """
    Append invalid_entries to log_file. Creates file if it does not exist.
    One line per entry in the format:
      [ISO_TIMESTAMP] REASON_CODE: account_id=ID region=REGION reason="Human readable" file=FILE
    """
    if not invalid_entries:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_file, "a", encoding="utf-8") as f:
        for entry in invalid_entries:
            reason_code = entry.get("reason", "UNKNOWN")
            acc_id = entry.get("account_id", "")
            region = entry.get("region", "")
            file_ = entry.get("file", "")
            human = _REASON_LABELS.get(reason_code, reason_code)
            region_part = f" region={region}" if region else ""
            f.write(
                f"[{now}] {reason_code}: account_id={acc_id}{region_part}"
                f" reason=\"{human}\" file={file_}\n"
            )
