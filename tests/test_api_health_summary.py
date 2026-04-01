"""Tests for /api/health-summary — theatre health status logic."""
import pytest
from contextlib import contextmanager
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent.db import init_db, get_db


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    init_db(p)
    return p


@pytest.fixture
def client(db):
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"), \
         patch("dashboard._ensure_db"):
        from dashboard import app
        yield TestClient(app, raise_server_exceptions=False)


@contextmanager
def _seeded_client(db, accounts_and_signals):
    """Helper: seed DB and yield patched TestClient (patch stays active during use)."""
    with get_db(db) as conn:
        for aid, name, theatre, signal, m9 in accounts_and_signals:
            conn.execute("INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                         (aid, name, theatre))
            conn.execute("INSERT INTO blocked_data (account_id,signal,m9_complete,account_theatre) VALUES (?,?,?,?)",
                         (aid, signal, m9, theatre))
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"), \
         patch("dashboard._ensure_db"):
        from dashboard import app as _app
        yield TestClient(_app, raise_server_exceptions=False)


def test_returns_200(client):
    r = client.get("/api/health-summary")
    assert r.status_code == 200


def test_returns_dict_with_all_theatres(client):
    data = client.get("/api/health-summary").json()
    assert isinstance(data, dict)
    for t in ("EMEA", "JAPAC", "AMER", "LATAM"):
        assert t in data


def test_each_theatre_has_status_and_counts(client):
    data = client.get("/api/health-summary").json()
    for t, v in data.items():
        assert "status" in v
        assert "m9" in v
        assert "blocked" in v
        assert "at_risk" in v


def test_status_values_are_valid(client):
    data = client.get("/api/health-summary").json()
    for t, v in data.items():
        assert v["status"] in ("green", "amber", "red")


def test_empty_db_all_green(client):
    data = client.get("/api/health-summary").json()
    for t, v in data.items():
        assert v["status"] == "green"
        assert v["blocked"] == 0


def test_red_when_blocked_gt_5(db):
    accounts = [(f"e{i}", f"Co{i}", "EMEA", "blocked", 0) for i in range(6)]
    with _seeded_client(db, accounts) as c:
        data = c.get("/api/health-summary").json()
    assert data["EMEA"]["status"] == "red"
    assert data["EMEA"]["blocked"] == 6


def test_amber_when_blocked_3_to_5(db):
    accounts = [(f"e{i}", f"Co{i}", "EMEA", "blocked", 0) for i in range(3)]
    with _seeded_client(db, accounts) as c:
        data = c.get("/api/health-summary").json()
    assert data["EMEA"]["status"] == "amber"


def test_m9_count_correct(db):
    accounts = [(f"e{i}", f"Co{i}", "EMEA", "green", 1) for i in range(4)]
    with _seeded_client(db, accounts) as c:
        data = c.get("/api/health-summary").json()
    assert data["EMEA"]["m9"] == 4
