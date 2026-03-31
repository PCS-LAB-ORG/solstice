"""
UNIT: agent/db.py — SQLite database operations

Tests:
  get_db()    — returns connection with row_factory
  init_db()   — creates all required tables
  upsert_account() — inserts and updates accounts
"""
import sqlite3
import json
from pathlib import Path
import pytest

from agent.db import get_db, init_db


# ── get_db ────────────────────────────────────────────────────────────────────

class TestGetDb:
    def test_returns_connection(self, tmp_path):
        conn = get_db(tmp_path / "test.db")
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_row_factory_set(self, tmp_path):
        conn = get_db(tmp_path / "test.db")
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_connection_is_usable(self, tmp_path):
        conn = get_db(tmp_path / "test.db")
        result = conn.execute("SELECT 1 as val").fetchone()
        assert result["val"] == 1
        conn.close()


# ── init_db ───────────────────────────────────────────────────────────────────

class TestInitDb:
    def test_creates_accounts_table(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        conn = get_db(db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "accounts" in tables
        conn.close()

    def test_creates_blocked_data_table(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        conn = get_db(db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "blocked_data" in tables
        conn.close()

    def test_creates_status_history_table(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        conn = get_db(db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "status_history" in tables
        conn.close()

    def test_idempotent_on_second_call(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        init_db(db)  # must not raise
        conn = get_db(db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "accounts" in tables
        conn.close()

    def test_accounts_table_has_account_id_column(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        conn = get_db(db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        assert "account_id" in cols
        conn.close()

    def test_status_history_has_field_name_column(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        conn = get_db(db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(status_history)").fetchall()}
        assert "field_name" in cols
        conn.close()

    def test_blocked_data_has_signal_column(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        conn = get_db(db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(blocked_data)").fetchall()}
        assert "signal" in cols
        conn.close()


# ── migrate_from_state ────────────────────────────────────────────────────────

from agent.db import migrate_from_state


def _make_state(tmp_path, accounts, pipeline_changes=None):
    f = tmp_path / "state.json"
    data = {"last_run": "", "accounts": accounts}
    if pipeline_changes is not None:
        data["pipeline_changes"] = pipeline_changes
    f.write_text(json.dumps(data))
    return f


class TestMigrateFromState:

    # ── empty state ──────────────────────────────────────────────────────────

    def test_empty_state_all_counts_zero(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        state = _make_state(tmp_path, {})
        counts = migrate_from_state(state, db)
        assert counts["accounts"] == 0
        assert counts["blockers"] == 0
        assert counts["blocked_data"] == 0
        assert counts["ps_data"] == 0
        assert counts["ai_enrichment"] == 0
        assert counts["status_history"] == 0

    def test_empty_state_no_rows_in_db(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        state = _make_state(tmp_path, {})
        migrate_from_state(state, db)
        with get_db(db) as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        assert row_count == 0

    # ── single account — core fields ─────────────────────────────────────────

    def test_one_account_count(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "status": "active",
                "status_changed_at": "2026-01-01T00:00:00+00:00",
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["accounts"] == 1

    def test_one_account_stored_in_db(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "arr": "100000",
                "active_cse": "jdoe",
                "status": "active",
                "status_changed_at": "2026-01-01T00:00:00+00:00",
            }
        }
        state = _make_state(tmp_path, accounts)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE account_id=?", ("001ABC123456789",)
            ).fetchone()
        assert row is not None
        assert row["customer_name"] == "Acme Corp"
        assert row["arr"] == "100000"
        assert row["active_cse"] == "jdoe"

    def test_account_with_status_creates_status_history(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "status": "active",
                "status_changed_at": "2026-01-01T00:00:00+00:00",
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["status_history"] == 1
        with get_db(db) as conn:
            hist = conn.execute(
                "SELECT * FROM status_history WHERE account_id=?", ("001ABC123456789",)
            ).fetchone()
        assert hist is not None
        assert hist["new_status"] == "active"
        assert hist["source"] == "migration"
        assert hist["old_status"] is None

    def test_account_without_status_no_status_history(self, tmp_path):
        """Account with empty status should not create a status_history entry."""
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "status": "",
                "status_changed_at": "2026-01-01T00:00:00+00:00",
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["status_history"] == 0

    def test_account_without_status_changed_at_no_status_history(self, tmp_path):
        """Account with status but no timestamp should not create a status_history entry."""
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "status": "active",
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["status_history"] == 0

    # ── blocked_data ─────────────────────────────────────────────────────────

    def test_account_with_blocked_data_count(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "status": "",
                "blocked_data": {
                    "area": "EMEA",
                    "region": "WE",
                    "signal": "green",
                    "m3_complete": True,
                    "m9_complete": False,
                },
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["blocked_data"] == 1

    def test_account_with_blocked_data_stored_in_db(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "blocked_data": {
                    "area": "EMEA",
                    "region": "WE",
                    "signal": "green",
                    "m3_complete": True,
                    "m9_complete": False,
                    "subtype": "tech_blocker",
                },
            }
        }
        state = _make_state(tmp_path, accounts)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            bd = conn.execute(
                "SELECT * FROM blocked_data WHERE account_id=?", ("001ABC123456789",)
            ).fetchone()
        assert bd is not None
        assert bd["area"] == "EMEA"
        assert bd["signal"] == "green"
        assert bd["m3_complete"] == 1
        assert bd["subtype"] == "tech_blocker"

    def test_account_without_blocked_data_not_counted(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["blocked_data"] == 0

    # ── blockers list ────────────────────────────────────────────────────────

    def test_account_with_blockers_count(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "blockers": ["no_contact", "tech_blocker"],
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["blockers"] == 2

    def test_account_blockers_stored_in_db(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "blockers": ["no_contact", "tech_blocker"],
            }
        }
        state = _make_state(tmp_path, accounts)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            rows = conn.execute(
                "SELECT blocker_name FROM account_blockers WHERE account_id=?",
                ("001ABC123456789",)
            ).fetchall()
        names = {r["blocker_name"] for r in rows}
        assert names == {"no_contact", "tech_blocker"}

    # ── ps_data ──────────────────────────────────────────────────────────────

    def test_account_with_ps_data_count(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "ps_data": {
                    "ps_name": "Alice",
                    "country": "DE",
                    "ps_status": "active",
                },
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["ps_data"] == 1

    def test_account_without_ps_data_not_counted(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {"customer_name": "Acme Corp"}
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["ps_data"] == 0

    # ── ai_enrichment ────────────────────────────────────────────────────────

    def test_account_with_ai_enrichment_count(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "ai_enrichment": {
                    "blocker": "no_contact",
                    "owner": "jdoe",
                },
            }
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["ai_enrichment"] == 1

    def test_account_without_ai_enrichment_not_counted(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {"customer_name": "Acme Corp"}
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["ai_enrichment"] == 0

    # ── multiple accounts ────────────────────────────────────────────────────

    def test_multiple_accounts_count(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {"customer_name": "Acme Corp", "status": "active", "status_changed_at": "2026-01-01T00:00:00+00:00"},
            "002DEF123456789": {"customer_name": "Beta Inc",  "status": "blocked", "status_changed_at": "2026-01-02T00:00:00+00:00"},
            "003GHI123456789": {"customer_name": "Gamma LLC", "status": "complete", "status_changed_at": "2026-01-03T00:00:00+00:00"},
        }
        state = _make_state(tmp_path, accounts)
        counts = migrate_from_state(state, db)
        assert counts["accounts"] == 3
        assert counts["status_history"] == 3

    def test_multiple_accounts_all_stored(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {"customer_name": "Acme Corp"},
            "002DEF123456789": {"customer_name": "Beta Inc"},
        }
        state = _make_state(tmp_path, accounts)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        assert total == 2

    # ── idempotency (INSERT OR IGNORE) ───────────────────────────────────────

    def test_idempotent_second_run_accounts_count_identical(self, tmp_path):
        """accounts / blockers / blocked_data counts are identical on both runs.
        status_history count is intentionally 0 on the second run because the
        idempotency guard (SELECT 1 WHERE source='migration') skips re-insertion."""
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "status": "active",
                "status_changed_at": "2026-01-01T00:00:00+00:00",
                "blocked_data": {"area": "EMEA", "signal": "green"},
                "blockers": ["no_contact"],
            }
        }
        state = _make_state(tmp_path, accounts)
        counts1 = migrate_from_state(state, db)
        counts2 = migrate_from_state(state, db)
        # counts that use INSERT OR IGNORE / DELETE+INSERT are stable
        assert counts1["accounts"] == counts2["accounts"]
        assert counts1["blockers"] == counts2["blockers"]
        assert counts1["blocked_data"] == counts2["blocked_data"]
        # status_history guard skips re-insertion on second run → 0 new rows
        assert counts2["status_history"] == 0

    def test_idempotent_no_duplicate_accounts(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {"customer_name": "Acme Corp", "status": "active", "status_changed_at": "2026-01-01T00:00:00+00:00"},
        }
        state = _make_state(tmp_path, accounts)
        migrate_from_state(state, db)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        assert total == 1

    def test_idempotent_no_duplicate_status_history(self, tmp_path):
        """Second migration run must not add a second status_history entry."""
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "status": "active",
                "status_changed_at": "2026-01-01T00:00:00+00:00",
            }
        }
        state = _make_state(tmp_path, accounts)
        migrate_from_state(state, db)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM status_history WHERE account_id=? AND source='migration'",
                ("001ABC123456789",)
            ).fetchone()[0]
        assert total == 1

    def test_idempotent_no_duplicate_blockers(self, tmp_path):
        """Blockers are deleted then re-inserted each run — final count must stay 2."""
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {
                "customer_name": "Acme Corp",
                "blockers": ["no_contact", "tech_blocker"],
            }
        }
        state = _make_state(tmp_path, accounts)
        migrate_from_state(state, db)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM account_blockers WHERE account_id=?",
                ("001ABC123456789",)
            ).fetchone()[0]
        assert total == 2

    # ── pipeline_changes in state.json ───────────────────────────────────────

    def test_pipeline_changes_imported(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {"customer_name": "Acme Corp"},
        }
        pipeline_changes = [
            {
                "account_id": "001ABC123456789",
                "old_status": "active",
                "new_status": "complete",
                "changed_at": "2026-02-01T00:00:00+00:00",
            }
        ]
        state = _make_state(tmp_path, accounts, pipeline_changes=pipeline_changes)
        counts = migrate_from_state(state, db)
        assert counts["status_history"] == 1
        with get_db(db) as conn:
            hist = conn.execute(
                "SELECT * FROM status_history WHERE source='pipeline'",
            ).fetchone()
        assert hist is not None
        assert hist["old_status"] == "active"
        assert hist["new_status"] == "complete"

    def test_pipeline_changes_idempotent(self, tmp_path):
        """Pipeline change imported twice must not create duplicate rows."""
        db = tmp_path / "test.db"
        init_db(db)
        accounts = {
            "001ABC123456789": {"customer_name": "Acme Corp"},
        }
        pipeline_changes = [
            {
                "account_id": "001ABC123456789",
                "old_status": "active",
                "new_status": "complete",
                "changed_at": "2026-02-01T00:00:00+00:00",
            }
        ]
        state = _make_state(tmp_path, accounts, pipeline_changes=pipeline_changes)
        migrate_from_state(state, db)
        migrate_from_state(state, db)
        with get_db(db) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM status_history WHERE source='pipeline'",
            ).fetchone()[0]
        assert total == 1

    # ── returns dict with all expected keys ──────────────────────────────────

    def test_return_value_has_all_keys(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        state = _make_state(tmp_path, {})
        counts = migrate_from_state(state, db)
        expected_keys = {"accounts", "blockers", "blocked_data", "ps_data", "ai_enrichment", "status_history"}
        assert expected_keys.issubset(counts.keys())
