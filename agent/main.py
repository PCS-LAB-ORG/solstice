import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.constants import DATA_DIR, INBOX_DIR, STATE_FILE, PENDING_TASKS_FILE, PENDING_REVIEW_LOG, AGENT_LOG, VALIDATION_ERRORS_LOG
from agent.differ import parse_csv, compute_diffs
from agent.validator import validate_accounts, write_validation_errors
from agent.classifier import classify_diffs
from agent.approver import run_approval
from agent.writer import write_approved_tasks, update_state, bootstrap_state, write_unclassified_log
from agent.watcher import start_watching
from agent.reporter import generate_report

# Module-level logger — handlers configured in main() after DATA_DIR exists
logger = logging.getLogger(__name__)


def load_state(state_file: Path = STATE_FILE) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load state.json: %s", e)
    return {"last_run": "", "accounts": {}}


def run_pipeline(csv_path: Path) -> None:
    """Full pipeline: parse -> diff -> classify -> approve -> write."""
    logger.info("Pipeline triggered by: %s", csv_path)
    state = load_state(STATE_FILE)

    if not state["accounts"]:
        logger.info("No state found — bootstrapping from %s", csv_path)
        accounts = parse_csv(csv_path)
        bootstrap_state(accounts, STATE_FILE, PENDING_TASKS_FILE)
        return

    new_accounts = parse_csv(csv_path)
    if not new_accounts:
        logger.warning("CSV produced 0 accounts — skipping pipeline")
        return

    valid_accounts, invalid_entries = validate_accounts(new_accounts, csv_filename=csv_path.name)
    if invalid_entries:
        write_validation_errors(invalid_entries, VALIDATION_ERRORS_LOG)
        logger.warning("%d invalid rows written to validation_errors.log", len(invalid_entries))
    if not valid_accounts:
        logger.warning("No valid EMEA accounts after validation — skipping pipeline")
        return

    diffs = compute_diffs(valid_accounts, state)
    if not diffs:
        logger.info("No changes detected.")
        print("No changes detected.")
        update_state(state, valid_accounts, STATE_FILE)
        return

    logger.info("%d diffs detected", len(diffs))
    classifications = classify_diffs(diffs)

    diff_by_id = {d["account_id"]: d for d in diffs}
    tasks = []
    unclassified_diffs = []

    for c in classifications:
        acc_id = c["account_id"]
        diff = diff_by_id.get(acc_id, {})
        changes = diff.get("changes", [])
        old_val = changes[0]["old"] if changes else ""
        new_val = changes[0]["new"] if changes else ""

        task = {
            "account_id": acc_id,
            "customer_name": diff.get("customer_name", ""),
            "region": diff.get("region", ""),
            "cse": diff.get("cse", ""),
            "category": c["category"],
            "priority": c["priority"],
            "suggested_action": c["suggested_action"],
            "old_value": str(old_val) if old_val is not None else "",
            "new_value": str(new_val) if new_val is not None else "",
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

        if c["category"] == "UNCLASSIFIED":
            unclassified_diffs.append(diff)
        else:
            tasks.append(task)

    if unclassified_diffs:
        write_unclassified_log(unclassified_diffs, PENDING_REVIEW_LOG)
        logger.warning("%d UNCLASSIFIED accounts written to pending_review.log", len(unclassified_diffs))

    if tasks:
        approved, skipped = run_approval(tasks)
    else:
        approved, skipped = [], 0

    if approved:
        write_approved_tasks(approved, PENDING_TASKS_FILE)
        logger.info("%d tasks written to pending_tasks.csv", len(approved))
        report_path = generate_report()
        logger.info("Report generated: %s", report_path)
        print(f"Report → {report_path}")
        import subprocess
        subprocess.Popen(["open", str(report_path)])

    expiry_flagged = {d["account_id"] for d in diffs if d.get("expiry_risk")}
    update_state(state, valid_accounts, STATE_FILE, expiry_flagged=expiry_flagged)
    logger.info("Pipeline complete.")


def main():
    DATA_DIR.mkdir(exist_ok=True)
    INBOX_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(AGENT_LOG),
            logging.StreamHandler(sys.stdout),
        ],
    )
    print(f"Solstice Agent — watching {INBOX_DIR} for CSV drops. Ctrl+C to stop.")
    start_watching(INBOX_DIR, callback=run_pipeline)


if __name__ == "__main__":
    main()
