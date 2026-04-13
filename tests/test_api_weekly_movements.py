"""Tests for /api/weekly-movements."""

import pytest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import date, timedelta
from fastapi.testclient import TestClient
from agent.db import init_db, get_db


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


@contextmanager
def _client(db, seed=None):
    if seed:
        with get_db(db) as conn:
            for item in seed:
                aid, name, theatre, signal, m9, m9_actual, m8_actual = item
                conn.execute(
                    "INSERT INTO accounts (account_id,customer_name,active_cse,sales_region,account_theatre) VALUES (?,?,?,?,?)",
                    (aid, name, "Jane", "CEE", theatre),
                )
                conn.execute(
                    "INSERT INTO blocked_data (account_id,signal,m9_complete,m9_actual,m8_started,m8_actual,account_theatre,cohort) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        aid,
                        signal,
                        m9,
                        m9_actual,
                        1 if m8_actual else 0,
                        m8_actual,
                        theatre,
                        "Scale cohort",
                    ),
                )
    with (
        patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)),
        patch("dashboard.init_db"),
        patch("dashboard._ensure_db"),
    ):
        from dashboard import app

        yield TestClient(app, raise_server_exceptions=False)


def _monday(d=None):
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def test_returns_200(db):
    with _client(db) as c:
        assert c.get("/api/weekly-movements").status_code == 200


def test_returns_required_keys(db):
    with _client(db) as c:
        data = c.get("/api/weekly-movements").json()
    for k in ("week_of", "new_m9", "m8_started", "newly_blocked", "resolved"):
        assert k in data


def test_empty_db_all_empty_lists(db):
    with _client(db) as c:
        data = c.get("/api/weekly-movements").json()
    assert data["new_m9"] == []
    assert data["newly_blocked"] == []


def test_m9_completed_this_week_appears(db):
    monday = _monday().isoformat()
    seed = [("a1", "Acme", "EMEA", "green", 1, monday, "")]
    with _client(db, seed) as c:
        data = c.get("/api/weekly-movements").json()
    assert any(r["customer_name"] == "Acme" for r in data["new_m9"])


def test_week_of_is_monday(db):
    with _client(db) as c:
        data = c.get("/api/weekly-movements").json()
    week_of = date.fromisoformat(data["week_of"])
    assert week_of.weekday() == 0


def test_theatre_filter_applied(db):
    monday = _monday().isoformat()
    seed = [("a1", "Acme", "JAPAC", "green", 1, monday, "")]
    with _client(db, seed) as c:
        data = c.get("/api/weekly-movements?theatre=EMEA").json()
    assert data["new_m9"] == []


def test_date_param_selects_correct_week(db):
    last_monday = (_monday() - timedelta(weeks=1)).isoformat()
    seed = [("a1", "Acme", "EMEA", "green", 1, last_monday, "")]
    with _client(db, seed) as c:
        data = c.get(f"/api/weekly-movements?date={last_monday}").json()
    assert any(r["customer_name"] == "Acme" for r in data["new_m9"])


def test_m8_started_this_week_appears(db):
    monday = _monday().isoformat()
    seed = [("a1", "Beta", "EMEA", "green", 0, "", monday)]
    with _client(db, seed) as c:
        data = c.get("/api/weekly-movements").json()
    assert any(r["customer_name"] == "Beta" for r in data["m8_started"])
