"""
db.py — SQLite database for Solstice Agent.

Tables:
  accounts         — core account data from EMEA tracker
  account_blockers — active blocker tags per account
  blocked_data     — milestone + signal data from blocked accounts CSV
  ps_data          — PS engagement data from PS tracker CSV
  ai_enrichment    — Claude-extracted blocker/owner/accountable
  status_history   — every status change detected by the pipeline
  approved_tasks   — tasks approved by the user
  validation_errors— rows rejected by the validator

Usage:
  from agent.db import get_db, init_db, migrate_from_state
  db = get_db()
"""

from __future__ import annotations
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "solstice.db"


def get_db(path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a connection with row_factory=sqlite3.Row."""
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db(path: Path = DB_PATH) -> None:
    """Create all tables if they don't exist."""
    with get_db(path) as conn:
        conn.executescript("""
        -- Core account data (from EMEA tracker CSV)
        CREATE TABLE IF NOT EXISTS accounts (
            account_id          TEXT PRIMARY KEY,
            customer_name       TEXT,
            arr                 TEXT,
            active_cse          TEXT,
            backup_cse          TEXT,
            status              TEXT,
            status_changed_at   TEXT,
            expiration_date     TEXT,
            expiry_alerted_date TEXT,
            ps_engaged          TEXT,
            kickoff_date        TEXT,
            comments            TEXT,
            sales_region        TEXT,
            email_sent          TEXT,
            last_seen           TEXT,
            live_fire           INTEGER DEFAULT 0,
            live_fire_dc        TEXT DEFAULT '',
            account_theatre     TEXT DEFAULT 'EMEA',
            created_at          TEXT DEFAULT (datetime('now'))
        );

        -- Active blocker tags per account (checkbox columns from EMEA tracker)
        CREATE TABLE IF NOT EXISTS account_blockers (
            account_id   TEXT REFERENCES accounts(account_id) ON DELETE CASCADE,
            blocker_name TEXT,
            PRIMARY KEY (account_id, blocker_name)
        );

        -- Milestone + signal data (DC CSE Tracker is master source of truth)
        CREATE TABLE IF NOT EXISTS blocked_data (
            account_id          TEXT PRIMARY KEY REFERENCES accounts(account_id) ON DELETE CASCADE,
            area                TEXT,
            region              TEXT,
            district            TEXT,
            cohort              TEXT,
            team                TEXT,
            is_cs_team          INTEGER DEFAULT 0,
            -- Milestones M0-M9 (all from DC CSE Tracker)
            m0_complete         INTEGER DEFAULT 0,
            m1_complete         INTEGER DEFAULT 0,
            m1_planned          TEXT,
            m2_complete         INTEGER DEFAULT 0,
            m2_planned          TEXT,
            m3_complete         INTEGER DEFAULT 0,
            m3_planned          TEXT,
            m4_complete         INTEGER DEFAULT 0,
            m4_planned          TEXT,
            m5_complete         INTEGER DEFAULT 0,
            m5_planned          TEXT,
            m6_complete         INTEGER DEFAULT 0,
            m7_complete         INTEGER DEFAULT 0,
            m7_planned          TEXT,
            m8_started          INTEGER DEFAULT 0,
            m8_planned          TEXT,
            m8_actual           TEXT,
            m9_complete         INTEGER DEFAULT 0,
            m9_planned          TEXT,
            m9_actual           TEXT,
            -- DC metadata
            account_theatre     TEXT DEFAULT 'EMEA',
            dc_progress         TEXT,
            owner_e2e           TEXT,
            dc_assignment       TEXT,
            cc_rep              TEXT,
            cc_dsm              TEXT,
            churn_risk          TEXT,
            -- Extended DC fields (added via pipeline, must match _run_dc_pipeline upsert)
            last_edited_by      TEXT,
            last_edited_date    TEXT,
            roadmap_url         TEXT,
            ps_plan_url         TEXT,
            account_region      TEXT,
            current_project_status TEXT,
            next_renewal_date   TEXT,
            past_due_planned    TEXT,
            upgrade_duration_weeks TEXT,
            has_partner         TEXT,
            upgrade_partner     TEXT,
            m1_details          TEXT,
            m3_details          TEXT,
            m5_details          TEXT,
            milestone_aging     TEXT,
            days_since_milestone TEXT,
            momentum_x          TEXT,
            entitlement_provision TEXT,
            activation_status   TEXT,
            posture_workloads   TEXT,
            -- Notes and signals
            upgrade_notes       TEXT,
            health_notes        TEXT,
            exec_delay          TEXT,
            status_detail       TEXT,
            signal              TEXT,
            subtype             TEXT,
            milestone_category  TEXT,
            notes               TEXT,
            merged_at           TEXT,
            -- Unified Tracker 2.0 fields
            cortexcloud_renewable_acv TEXT DEFAULT '',
            pc_cc_migration_status TEXT DEFAULT '',
            field_indicated_churn TEXT DEFAULT ''
        );

        -- PS engagement data (from PS tracker CSV)
        CREATE TABLE IF NOT EXISTS ps_data (
            account_id        TEXT PRIMARY KEY REFERENCES accounts(account_id) ON DELETE CASCADE,
            ps_name           TEXT,
            country           TEXT,
            psc               TEXT,
            psc_shadow        TEXT,
            pm                TEXT,
            ps_status         TEXT,
            clarizen_id       TEXT,
            timeline          TEXT,
            notes             TEXT,
            match_confidence  REAL,
            matched_name      TEXT,
            merged_at         TEXT
        );

        -- Claude AI enrichment (blocker/owner/accountable from comments)
        CREATE TABLE IF NOT EXISTS ai_enrichment (
            account_id      TEXT PRIMARY KEY REFERENCES accounts(account_id) ON DELETE CASCADE,
            blocker         TEXT,
            owner           TEXT,
            accountable     TEXT,
            comments_hash   TEXT,
            enriched_at     TEXT
        );

        -- Status change history — every change detected by the pipeline
        CREATE TABLE IF NOT EXISTS status_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id  TEXT REFERENCES accounts(account_id) ON DELETE CASCADE,
            old_status  TEXT,
            new_status  TEXT,
            changed_at  TEXT,
            source      TEXT DEFAULT 'pipeline',
            file_source TEXT,
            field_name  TEXT
        );

        -- M1 outreach action plan (rebuilt on every DC sync)
        CREATE TABLE IF NOT EXISTS m1_suggestions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id    TEXT,
            account_name  TEXT NOT NULL,
            assigned_cse  TEXT NOT NULL,
            original_cse  TEXT,
            region        TEXT,
            status        TEXT,
            signal        TEXT,
            m1_planned    TEXT,
            category      TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        -- Approved tasks (from terminal approval flow)
        CREATE TABLE IF NOT EXISTS approved_tasks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id       TEXT,
            customer_name    TEXT,
            region           TEXT,
            cse              TEXT,
            category         TEXT,
            priority         TEXT,
            suggested_action TEXT,
            old_value        TEXT,
            new_value        TEXT,
            detected_at      TEXT,
            approved_at      TEXT DEFAULT (datetime('now'))
        );

        -- Validation errors (rows rejected by validator)
        CREATE TABLE IF NOT EXISTS validation_errors (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT,
            reason     TEXT,
            region     TEXT,
            file       TEXT,
            logged_at  TEXT DEFAULT (datetime('now'))
        );

        -- XSUP data from TAC Open XSUPs tracker
        CREATE TABLE IF NOT EXISTS xsup_data (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name    TEXT NOT NULL,
            account_id      TEXT,
            case_number     TEXT,
            case_status     TEXT,
            case_theatre    TEXT,
            xsup_number     TEXT,
            xsup_priority   TEXT,
            xsup_status     TEXT,
            summary         TEXT,
            component       TEXT,
            notes           TEXT,
            synced_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_xsup_account   ON xsup_data(account_name);
        CREATE INDEX IF NOT EXISTS idx_xsup_priority  ON xsup_data(xsup_priority);
        CREATE INDEX IF NOT EXISTS idx_xsup_status    ON xsup_data(xsup_status);
        CREATE INDEX IF NOT EXISTS idx_xsup_acct_id   ON xsup_data(account_id);

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_accounts_status      ON accounts(status);
        CREATE INDEX IF NOT EXISTS idx_accounts_theatre     ON accounts(account_theatre);
        CREATE INDEX IF NOT EXISTS idx_accounts_cse         ON accounts(active_cse);
        CREATE INDEX IF NOT EXISTS idx_accounts_region      ON accounts(sales_region);
        CREATE INDEX IF NOT EXISTS idx_status_history_acct  ON status_history(account_id);
        CREATE INDEX IF NOT EXISTS idx_status_history_date  ON status_history(changed_at);
        CREATE INDEX IF NOT EXISTS idx_status_history_src   ON status_history(file_source);
        CREATE INDEX IF NOT EXISTS idx_status_history_field ON status_history(field_name);
        CREATE INDEX IF NOT EXISTS idx_blocked_signal       ON blocked_data(signal);
        CREATE INDEX IF NOT EXISTS idx_approved_tasks_date  ON approved_tasks(detected_at);
        """)
    logger.info("Database initialised: %s", path)
    _migrate_schema(path)


def wipe_account_data(conn) -> None:
    """Wipe accounts + blocked_data only. Preserves status_history, COE, XSUP tables."""
    conn.execute("DELETE FROM blocked_data")
    conn.execute("DELETE FROM accounts")
    conn.execute("DELETE FROM account_blockers")
    conn.execute("DELETE FROM m1_suggestions")


def _migrate_schema(path: Path = DB_PATH) -> None:
    """Apply incremental ALTER TABLE migrations for columns added after initial deploy."""
    with get_db(path) as conn:
        try:
            conn.execute(
                "ALTER TABLE blocked_data ADD COLUMN m6_complete INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        # Unified Tracker 2.0 columns — added 2026-07-21
        try:
            conn.execute("ALTER TABLE blocked_data ADD COLUMN cortexcloud_renewable_acv TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE blocked_data ADD COLUMN pc_cc_migration_status TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE blocked_data ADD COLUMN field_indicated_churn TEXT DEFAULT ''")
        except Exception:
            pass
        # xsup_data table — added 2026-05-11
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS xsup_data (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name    TEXT NOT NULL,
            account_id      TEXT,
            case_number     TEXT,
            case_status     TEXT,
            case_theatre    TEXT,
            xsup_number     TEXT,
            xsup_priority   TEXT,
            xsup_status     TEXT,
            summary         TEXT,
            component       TEXT,
            notes           TEXT,
            synced_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_xsup_account   ON xsup_data(account_name);
        CREATE INDEX IF NOT EXISTS idx_xsup_priority  ON xsup_data(xsup_priority);
        CREATE INDEX IF NOT EXISTS idx_xsup_status    ON xsup_data(xsup_status);
        CREATE INDEX IF NOT EXISTS idx_xsup_acct_id   ON xsup_data(account_id);
        """)


def migrate_from_state(state_file: Path, path: Path = DB_PATH) -> dict:
    """
    One-time migration from state.json → SQLite.
    Idempotent — safe to run multiple times (uses INSERT OR REPLACE).
    """
    state = json.loads(state_file.read_text(encoding="utf-8"))
    accounts = state.get("accounts", {})
    now = datetime.now(timezone.utc).isoformat()

    counts = {
        "accounts": 0,
        "blockers": 0,
        "blocked_data": 0,
        "ps_data": 0,
        "ai_enrichment": 0,
        "status_history": 0,
    }

    with get_db(path) as conn:
        for account_id, acc in accounts.items():
            # accounts
            conn.execute(
                """
                INSERT OR IGNORE INTO accounts
                (account_id, customer_name, arr, active_cse, backup_cse, status,
                 status_changed_at, expiration_date, expiry_alerted_date, ps_engaged,
                 kickoff_date, comments, sales_region, email_sent, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    account_id,
                    acc.get("customer_name", ""),
                    acc.get("arr", ""),
                    acc.get("active_cse", ""),
                    acc.get("backup_cse", ""),
                    acc.get("status", ""),
                    acc.get("status_changed_at", ""),
                    acc.get("expiration_date", ""),
                    acc.get("expiry_alerted_date"),
                    acc.get("ps_engaged", ""),
                    acc.get("kickoff_date", ""),
                    acc.get("comments", ""),
                    acc.get("sales_region", ""),
                    acc.get("email_sent", ""),
                    acc.get("last_seen", now),
                ),
            )
            counts["accounts"] += 1

            # blockers
            conn.execute(
                "DELETE FROM account_blockers WHERE account_id=?", (account_id,)
            )
            for b in acc.get("blockers", []):
                conn.execute(
                    "INSERT OR IGNORE INTO account_blockers VALUES (?,?)",
                    (account_id, b),
                )
                counts["blockers"] += 1

            # blocked_data
            bd = acc.get("blocked_data")
            if bd:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO blocked_data
                    (account_id, area, region, district, cohort, team, is_cs_team,
                     m3_complete, m3_planned, m8_started, m8_planned,
                     m9_complete, m9_planned, upgrade_notes, health_notes,
                     exec_delay, status_detail, signal, subtype, milestone_category, notes, merged_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                    (
                        account_id,
                        bd.get("area", ""),
                        bd.get("region", ""),
                        bd.get("district", ""),
                        bd.get("cohort", ""),
                        bd.get("team", ""),
                        int(bd.get("is_cs_team", False)),
                        int(bd.get("m3_complete", False)),
                        bd.get("m3_planned", ""),
                        int(bd.get("m8_started", False)),
                        bd.get("m8_planned", ""),
                        int(bd.get("m9_complete", False)),
                        bd.get("m9_planned", ""),
                        bd.get("upgrade_notes", ""),
                        bd.get("health_notes", ""),
                        bd.get("exec_delay", ""),
                        bd.get("status_detail", ""),
                        bd.get("signal", ""),
                        bd.get("subtype"),
                        bd.get("milestone_category", ""),
                        bd.get("notes", ""),
                        bd.get("merged_at", now),
                    ),
                )
                counts["blocked_data"] += 1

            # ps_data
            ps = acc.get("ps_data")
            if ps:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ps_data
                    (account_id, ps_name, country, psc, psc_shadow, pm, ps_status,
                     clarizen_id, timeline, notes, match_confidence, matched_name, merged_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                    (
                        account_id,
                        ps.get("ps_name", ""),
                        ps.get("country", ""),
                        ps.get("psc", ""),
                        ps.get("psc_shadow", ""),
                        ps.get("pm", ""),
                        ps.get("ps_status", ""),
                        ps.get("clarizen_id", ""),
                        ps.get("timeline", ""),
                        ps.get("notes", ""),
                        ps.get("match_confidence"),
                        ps.get("matched_name", ""),
                        ps.get("merged_at", now),
                    ),
                )
                counts["ps_data"] += 1

            # ai_enrichment
            ai = acc.get("ai_enrichment")
            if ai:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ai_enrichment
                    (account_id, blocker, owner, accountable, comments_hash, enriched_at)
                    VALUES (?,?,?,?,?,?)
                """,
                    (
                        account_id,
                        ai.get("blocker"),
                        ai.get("owner"),
                        ai.get("accountable"),
                        ai.get("comments_hash", ""),
                        ai.get("enriched_at", now),
                    ),
                )
                counts["ai_enrichment"] += 1

            # status_history — two sources:
            # 1. migration: initial status from state.json (old_status=None)
            # 2. pipeline: real changes stored in state.json["pipeline_changes"]
            changed_at = acc.get("status_changed_at", "")
            status = acc.get("status", "")
            if status and changed_at:
                migration_exists = conn.execute(
                    "SELECT 1 FROM status_history WHERE account_id=? AND new_status=? AND source='migration'",
                    (account_id, status),
                ).fetchone()
                if not migration_exists:
                    conn.execute(
                        """
                        INSERT INTO status_history (account_id, old_status, new_status, changed_at, source)
                        VALUES (?,?,?,?,?)
                    """,
                        (account_id, None, status, changed_at, "migration"),
                    )
                    counts["status_history"] += 1

        # Restore pipeline changes from state.json (survive DB rebuilds)
        for change in state.get("pipeline_changes", []):
            existing = conn.execute(
                "SELECT 1 FROM status_history WHERE account_id=? AND old_status=? AND new_status=? AND source='pipeline'",
                (change["account_id"], change["old_status"], change["new_status"]),
            ).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO status_history (account_id, old_status, new_status, changed_at, source)
                    VALUES (?,?,?,?,?)
                """,
                    (
                        change["account_id"],
                        change["old_status"],
                        change["new_status"],
                        change["changed_at"],
                        "pipeline",
                    ),
                )
                counts["status_history"] += 1

    logger.info("Migration complete: %s", counts)
    return counts


def upsert_account(conn: sqlite3.Connection, account_id: str, acc: dict) -> bool:
    account_id = account_id.lower()
    """
    Update or insert one account. Returns True if status changed.
    Writes status change to status_history automatically.
    Full debug logging on every write. Never raises — logs errors and returns False.
    """
    try:
        existing = conn.execute(
            "SELECT status FROM accounts WHERE account_id=?", (account_id,)
        ).fetchone()

        old_status = existing["status"] if existing else None
        new_status = acc.get("status", "")
        status_changed = old_status != new_status and old_status is not None

        conn.execute(
            """
            INSERT OR IGNORE INTO accounts
            (account_id, customer_name, arr, active_cse, backup_cse, status,
             status_changed_at, expiration_date, expiry_alerted_date, ps_engaged,
             kickoff_date, comments, sales_region, email_sent, last_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                account_id,
                acc.get("customer_name", ""),
                acc.get("arr", ""),
                acc.get("active_cse", ""),
                acc.get("backup_cse", ""),
                new_status,
                acc.get("status_changed_at", ""),
                acc.get("expiration_date", ""),
                acc.get("expiry_alerted_date"),
                acc.get("ps_engaged", ""),
                acc.get("kickoff_date", ""),
                acc.get("comments", ""),
                acc.get("sales_region", ""),
                acc.get("email_sent", ""),
                acc.get("last_seen", ""),
            ),
        )
        logger.debug(
            "DB upsert: %s | customer=%s | status=%s | cse=%s",
            account_id,
            acc.get("customer_name", "?"),
            new_status,
            acc.get("active_cse", "?"),
        )

        if status_changed:
            conn.execute(
                """
                INSERT INTO status_history (account_id, old_status, new_status, changed_at, source)
                VALUES (?,?,?,?,?)
            """,
                (
                    account_id,
                    old_status,
                    new_status,
                    datetime.now(timezone.utc).isoformat(),
                    "pipeline",
                ),
            )
            logger.info(
                "DB status_history: %s | %s → %s",
                acc.get("customer_name", account_id),
                old_status,
                new_status,
            )

        # blockers
        conn.execute("DELETE FROM account_blockers WHERE account_id=?", (account_id,))
        for b in acc.get("blockers", []):
            conn.execute(
                "INSERT OR IGNORE INTO account_blockers VALUES (?,?)", (account_id, b)
            )

        return status_changed

    except Exception as e:
        logger.error(
            "DB upsert FAILED for %s (%s): %s",
            account_id,
            acc.get("customer_name", "?"),
            e,
        )
        return False


def sync_all(state_file: Path, db_path: Path = DB_PATH) -> dict:
    """
    Full sync: read state.json → upsert every account into DB.
    Called at startup and after every pipeline run.
    Returns {synced, errors, status_changes}.
    """
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        accounts = state.get("accounts", {})
    except Exception as e:
        logger.error("DB sync_all: failed to read state.json: %s", e)
        return {"synced": 0, "errors": 1, "status_changes": 0}

    counts = {"synced": 0, "errors": 0, "status_changes": 0}
    try:
        init_db(db_path)
        with get_db(db_path) as conn:
            for account_id, acc in accounts.items():
                try:
                    changed = upsert_account(conn, account_id, acc)
                    counts["synced"] += 1
                    if changed:
                        counts["status_changes"] += 1
                except Exception as e:
                    logger.error("DB sync_all row error %s: %s", account_id, e)
                    counts["errors"] += 1
    except Exception as e:
        logger.error("DB sync_all connection error: %s", e)
        counts["errors"] += 1

    logger.info(
        "DB sync_all complete: synced=%d errors=%d status_changes=%d",
        counts["synced"],
        counts["errors"],
        counts["status_changes"],
    )
    return counts


def load_accounts(path: Path = DB_PATH) -> dict:
    """
    Load all accounts from DB into the same dict structure as state.json.
    Used by reporter and other components for backward compatibility.
    """
    with get_db(path) as conn:
        accounts = {}
        for row in conn.execute("SELECT * FROM accounts"):
            aid = row["account_id"]
            acc = dict(row)

            # blockers
            acc["blockers"] = [
                r["blocker_name"]
                for r in conn.execute(
                    "SELECT blocker_name FROM account_blockers WHERE account_id=?",
                    (aid,),
                )
            ]

            # blocked_data
            bd = conn.execute(
                "SELECT * FROM blocked_data WHERE account_id=?", (aid,)
            ).fetchone()
            if bd:
                bd_dict = dict(bd)
                for _bool_col in (
                    "is_cs_team",
                    "m0_complete",
                    "m1_complete",
                    "m2_complete",
                    "m3_complete",
                    "m4_complete",
                    "m5_complete",
                    "m7_complete",
                    "m8_started",
                    "m9_complete",
                ):
                    bd_dict[_bool_col] = bool(bd_dict.get(_bool_col))
                acc["blocked_data"] = bd_dict

            # ps_data
            ps = conn.execute(
                "SELECT * FROM ps_data WHERE account_id=?", (aid,)
            ).fetchone()
            if ps:
                acc["ps_data"] = dict(ps)

            # ai_enrichment
            ai = conn.execute(
                "SELECT * FROM ai_enrichment WHERE account_id=?", (aid,)
            ).fetchone()
            if ai:
                acc["ai_enrichment"] = dict(ai)

            accounts[aid] = acc

    return accounts


def completed_by_week(path: Path = DB_PATH) -> dict[str, list[dict]]:
    """
    Return accounts that completed (status=Completed OR m9_complete=1) grouped by ISO week.
    Uses status_history for pipeline-detected completions, blocked_data.m9_complete as fallback.
    Format: {"2026-W12": [{customer_name, cse, date}], ...}
    """
    from datetime import date

    results: dict[str, list[dict]] = {}

    with get_db(path) as conn:
        # From status_history — pipeline-detected completions
        for row in conn.execute("""
            SELECT a.customer_name, a.active_cse, sh.changed_at
            FROM status_history sh
            JOIN accounts a ON a.account_id = sh.account_id
            WHERE sh.new_status = 'Completed'
            ORDER BY sh.changed_at
        """):
            try:
                dt = datetime.fromisoformat(row["changed_at"].replace("Z", "+00:00"))
                week_key = dt.strftime("%Y-W%W")
                results.setdefault(week_key, []).append(
                    {
                        "customer_name": row["customer_name"],
                        "cse": row["active_cse"],
                        "date": dt.strftime("%d %b %Y"),
                        "source": "pipeline",
                    }
                )
            except Exception:
                pass

        # From accounts directly (current Completed status)
        for row in conn.execute("""
            SELECT a.account_id, a.customer_name, a.active_cse, a.status_changed_at
            FROM accounts a
            WHERE a.status = 'Completed'
        """):
            try:
                dt = datetime.fromisoformat(
                    (row["status_changed_at"] or "").replace("Z", "+00:00")
                )
                week_key = dt.strftime("%Y-W%W")
                # Avoid duplicates with status_history
                existing = [e["customer_name"] for e in results.get(week_key, [])]
                if row["customer_name"] not in existing:
                    results.setdefault(week_key, []).append(
                        {
                            "customer_name": row["customer_name"],
                            "cse": row["active_cse"],
                            "date": dt.strftime("%d %b %Y"),
                            "source": "state",
                        }
                    )
            except Exception:
                pass

    return dict(sorted(results.items()))


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
    )
    from agent.constants import STATE_FILE, DATA_DIR

    print("Initialising database...")
    init_db()
    print("Migrating from state.json...")
    counts = migrate_from_state(STATE_FILE)
    print(f"  accounts:      {counts['accounts']}")
    print(f"  blockers:      {counts['blockers']}")
    print(f"  blocked_data:  {counts['blocked_data']}")
    print(f"  ps_data:       {counts['ps_data']}")
    print(f"  ai_enrichment: {counts['ai_enrichment']}")
    print(f"  status_history:{counts['status_history']}")
    print(f"\nDB: {DB_PATH}")
