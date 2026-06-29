"""Tests for /api/velocity."""

import pytest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import date, timedelta, datetime, timezone
from fastapi.testclient import TestClient
from agent.db import init_db, get_db

MILESTONES = [
    "M1 Outreach",
    "M2 Entitlements",
    "M3 Buy-in",
    "M4 Discovery",
    "M5 Tech Validation",
    "M8 Upgrade Started",
    "M9 Upgrade Complete",
]


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


def _seed(db, rows):
    """rows: list of (account_id, name, theatre, field_name, changed_at)"""
    with get_db(db) as conn:
        for aid, name, theatre, field_name, changed_at in rows:
            conn.execute(
                "INSERT OR IGNORE INTO accounts (account_id,customer_name,active_cse,sales_region,account_theatre) VALUES (?,?,?,?,?)",
                (aid, name, "CSE", "Region", theatre),
            )
            conn.execute(
                "INSERT OR IGNORE INTO blocked_data (account_id,signal,m9_complete,account_theatre,cohort) VALUES (?,?,?,?,?)",
                (aid, "green", 0, theatre, "Scale cohort"),
            )
            conn.execute(
                "INSERT INTO status_history (account_id,field_name,old_status,new_status,changed_at) VALUES (?,?,?,?,?)",
                (aid, field_name, "N", "Y", changed_at),
            )


@contextmanager
def _client(db):
    with (
        patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)),
        patch("dashboard.init_db"),
        patch("dashboard._ensure_db"),
    ):
        from dashboard import app

        yield TestClient(app, raise_server_exceptions=False)


def _this_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def test_this_week_all_theatres(db):
    """this_week.by_theatre always has all 4 theatres regardless of theatre param."""
    monday = _this_monday()
    ts = f"{monday}T10:00:00"
    _seed(
        db,
        [
            ("a1", "Alpha", "EMEA", "M8 Upgrade Started", ts),
            ("a2", "Beta", "AMER", "M9 Upgrade Complete", ts),
        ],
    )
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4&theatre=EMEA")
    assert r.status_code == 200
    data = r.json()
    assert set(data["this_week"]["by_theatre"].keys()) == {
        "AMER",
        "EMEA",
        "JAPAC",
        "LATAM",
    }
    assert data["this_week"]["by_theatre"]["EMEA"]["M8 Upgrade Started"] == 1
    assert data["this_week"]["by_theatre"]["AMER"]["M9 Upgrade Complete"] == 1


def test_history_theatre_filter(db):
    """History rows are filtered by theatre param."""
    monday = _this_monday() - timedelta(weeks=1)
    ts = f"{monday}T10:00:00"
    _seed(
        db,
        [
            ("b1", "Bravo", "EMEA", "M8 Upgrade Started", ts),
            ("b2", "Charlie", "AMER", "M8 Upgrade Started", ts),
        ],
    )
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4&theatre=EMEA")
    data = r.json()
    # history filtered to EMEA only
    week_row = data["history"][0] if data["history"] else {}
    assert week_row.get("M8 Upgrade Started", 0) == 1


def test_history_theatre_all(db):
    """When theatre='', history sums across all theatres."""
    monday = _this_monday() - timedelta(weeks=1)
    ts = f"{monday}T10:00:00"
    _seed(
        db,
        [
            ("c1", "Delta", "EMEA", "M8 Upgrade Started", ts),
            ("c2", "Echo", "AMER", "M8 Upgrade Started", ts),
        ],
    )
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4")
    data = r.json()
    week_row = data["history"][0] if data["history"] else {}
    assert week_row.get("M8 Upgrade Started", 0) == 2


def test_weeks_param_limits_history(db):
    """history contains at most `weeks` entries."""
    with _client(db) as c:
        r = c.get("/api/velocity?weeks=4")
    data = r.json()
    assert len(data["history"]) <= 4


def test_response_shape(db):
    """Response has required keys."""
    with _client(db) as c:
        r = c.get("/api/velocity")
    data = r.json()
    assert "this_week" in data
    assert "history" in data
    assert "updated_at" in data
    assert "range" in data["this_week"]
    assert "by_theatre" in data["this_week"]
