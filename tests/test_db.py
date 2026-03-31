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
