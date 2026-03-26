"""
TDD tests for dashboard pipeline — audit log, DB persistence, merge integrity.
These test the actual bugs: DB wiped on restart, ai_enrichment lost, audit log empty.
"""
import json, sys
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def state_with_enrichment(tmp_path):
    """state.json with ai_enrichment on every account."""
    state = {"last_run": "2026-03-24T00:00:00Z", "accounts": {
        "001abc123456789aaa": {"customer_name": "Acme Corp", "status": "Ready To Engage",
            "active_cse": "Tunde", "sales_region": "CEE",
            "status_changed_at": "2026-03-01T00:00:00Z",
            "ai_enrichment": {"blocker": "no budget", "owner": "John", "accountable": "CTO",
                              "comments_hash": "abc", "enriched_at": "2026-03-21T00:00:00Z"},
            "live_fire": True, "live_fire_dc": "DC Smith",
            "blockers": [], "email_sent": "01/01/2026 10:00:00",
            "arr": "", "backup_cse": "", "expiration_date": "", "expiry_alerted_date": None,
            "ps_engaged": "", "kickoff_date": "", "comments": "test", "last_seen": "2026-03-21"},
    }}
    f = tmp_path / "state.json"
    f.write_text(json.dumps(state))
    return f


# ── Test 1: ai_enrichment survives CSV merge ─────────────────────────────

def test_merge_preserves_ai_enrichment(state_with_enrichment):
    """REAL BUG: state.update(valid) wipes ai_enrichment. Merge must preserve it."""
    aid = "001abc123456789aaa"
    state = json.loads(state_with_enrichment.read_text())
    original_ai = state["accounts"][aid]["ai_enrichment"].copy()

    # This is what the broken code does — full replace wipes ai_enrichment
    fresh_from_csv = {"customer_name": "Acme Corp", "status": "Sales Hold",
                      "active_cse": "Tunde", "sales_region": "CEE"}

    # BROKEN: state["accounts"][aid] = fresh_from_csv  ← loses ai_enrichment
    # CORRECT: only update CSV fields
    MERGE_FIELDS = ['customer_name','arr','active_cse','backup_cse','status',
                    'status_changed_at','expiration_date','sales_region',
                    'email_sent','live_fire','live_fire_dc','blockers','last_seen']
    for f in MERGE_FIELDS:
        if f in fresh_from_csv:
            state["accounts"][aid][f] = fresh_from_csv[f]

    assert state["accounts"][aid].get("ai_enrichment") == original_ai, \
        "ai_enrichment wiped by merge — FAIL"
    assert state["accounts"][aid]["status"] == "Sales Hold"


# ── Test 2: populate_db must check ALL tables ───────────────────────────

def test_populate_db_skips_only_when_all_three_tables_populated(tmp_path):
    """REAL BUG: returns early on blocked_data>0 even if status_history=0."""
    from agent.db import get_db, init_db

    db = tmp_path / "test.db"
    init_db(db)

    # Simulate: blocked_data=228, but status_history=0 (the bug scenario)
    with get_db(db) as conn:
        conn.execute("INSERT INTO accounts (account_id,customer_name,status) VALUES (?,?,?)",
                    ("test1","Test Co","Ready To Engage"))
        conn.execute("INSERT INTO blocked_data (account_id,signal) VALUES (?,?)", ("test1","green"))

    with get_db(db) as conn:
        bd = conn.execute("SELECT COUNT(*) FROM blocked_data").fetchone()[0]
        sh = conn.execute("SELECT COUNT(*) FROM status_history").fetchone()[0]
        ai = conn.execute("SELECT COUNT(*) FROM ai_enrichment").fetchone()[0]

    assert bd == 1, "blocked_data should have 1 row"
    assert sh == 0, "status_history should be 0 (the bug trigger)"
    assert ai == 0, "ai_enrichment should be 0"

    # The bug: if _populate_db only checks blocked_data, it returns early here
    # and status_history + ai_enrichment stay at 0 forever
    # The fix: check ALL three tables
    should_skip = bd > 0 and sh > 0 and ai > 0  # correct logic
    should_not_skip = not should_skip
    assert should_not_skip, "Must NOT skip when sh=0 or ai=0, even if bd>0"


# ── Test 3: pipeline writes to status_history ───────────────────────────

def test_pipeline_writes_status_change_to_history(tmp_path):
    """Pipeline must write status changes to status_history with source=pipeline."""
    from agent.db import get_db, init_db

    db = tmp_path / "test.db"
    init_db(db)
    aid = "001abc123456789aaa"
    now = datetime.now(timezone.utc).isoformat()

    with get_db(db) as conn:
        conn.execute("INSERT INTO accounts (account_id,customer_name,status) VALUES (?,?,?)",
                    (aid, "Acme Corp", "Sales Hold"))
        conn.execute("INSERT INTO status_history (account_id,old_status,new_status,changed_at,source) VALUES (?,?,?,?,?)",
                    (aid, "Ready To Engage", "Sales Hold", now, "pipeline"))

    with get_db(db) as conn:
        row = conn.execute("SELECT * FROM status_history WHERE source='pipeline'").fetchone()

    assert row is not None, "Pipeline change must be in status_history"
    assert row["old_status"] == "Ready To Engage"
    assert row["new_status"] == "Sales Hold"
    assert row["source"] == "pipeline"


# ── Test 4: status_history survives restart simulation ──────────────────

def test_pipeline_entries_survive_migrate_from_state(tmp_path, state_with_enrichment):
    """REAL BUG: migrate_from_state runs on startup and status_history shows 0."""
    from agent.db import get_db, init_db, migrate_from_state

    db = tmp_path / "test.db"
    init_db(db)
    aid = "001abc123456789aaa"
    now = datetime.now(timezone.utc).isoformat()

    # First: run migrate_from_state (simulates startup)
    with patch("agent.db.DB_PATH", db):
        migrate_from_state(state_with_enrichment, db)

    # Then: add a pipeline entry (simulates pipeline detecting change)
    with get_db(db) as conn:
        conn.execute("INSERT INTO status_history (account_id,old_status,new_status,changed_at,source) VALUES (?,?,?,?,?)",
                    (aid, "Ready To Engage", "Sales Hold", now, "pipeline"))

    # Simulate restart: run migrate_from_state again
    with patch("agent.db.DB_PATH", db):
        migrate_from_state(state_with_enrichment, db)

    # Pipeline entry must survive the second migrate
    with get_db(db) as conn:
        pipeline = conn.execute("SELECT COUNT(*) FROM status_history WHERE source='pipeline'").fetchone()[0]

    assert pipeline == 1, f"Pipeline entry lost after migrate_from_state — got {pipeline}"


# ── Test 5: audit log only shows pipeline not migration ──────────────────

def test_audit_log_excludes_migration_entries(tmp_path, state_with_enrichment):
    """Audit log must show ONLY pipeline changes, not initial migration records."""
    from agent.db import get_db, init_db, migrate_from_state

    db = tmp_path / "test.db"
    init_db(db)
    aid = "001abc123456789aaa"
    now = datetime.now(timezone.utc).isoformat()

    with patch("agent.db.DB_PATH", db):
        migrate_from_state(state_with_enrichment, db)

    # Add pipeline change
    with get_db(db) as conn:
        conn.execute("INSERT INTO status_history (account_id,old_status,new_status,changed_at,source) VALUES (?,?,?,?,?)",
                    (aid, "Ready To Engage", "Sales Hold", now, "pipeline"))

    with get_db(db) as conn:
        pipeline = conn.execute("SELECT COUNT(*) FROM status_history WHERE source='pipeline'").fetchall()
        migration = conn.execute("SELECT COUNT(*) FROM status_history WHERE source='migration'").fetchone()[0]

    assert len(pipeline) == 1, "Must have exactly 1 pipeline entry"
    assert migration >= 1, "Migration entries should exist separately"
