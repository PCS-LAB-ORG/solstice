"""Tests for /api/compare — 4-theatre side-by-side."""
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


@contextmanager
def _client(db, seed=None):
    if seed:
        with get_db(db) as conn:
            for aid, name, theatre, signal, m9, m9_actual in seed:
                conn.execute(
                    "INSERT INTO accounts (account_id,customer_name,account_theatre) VALUES (?,?,?)",
                    (aid, name, theatre))
                conn.execute(
                    "INSERT INTO blocked_data (account_id,signal,m9_complete,m9_actual,account_theatre) VALUES (?,?,?,?,?)",
                    (aid, signal, m9, m9_actual, theatre))
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(db)), \
         patch("dashboard.init_db"), \
         patch("dashboard._ensure_db"):
        from dashboard import app
        yield TestClient(app, raise_server_exceptions=False)


def test_returns_200(db):
    with _client(db) as c:
        assert c.get("/api/compare").status_code == 200


def test_returns_theatres_key(db):
    with _client(db) as c:
        assert "theatres" in c.get("/api/compare").json()


def test_all_four_theatres_present(db):
    with _client(db) as c:
        data = c.get("/api/compare").json()
    names = [t["theatre"] for t in data["theatres"]]
    for t in ("EMEA","JAPAC","AMER","LATAM"):
        assert t in names


def test_each_theatre_has_required_keys(db):
    with _client(db) as c:
        data = c.get("/api/compare").json()
    for t in data["theatres"]:
        for k in ("theatre","m9_total","m9_this_week","blocked","at_risk","sla_overdue"):
            assert k in t


def test_m9_total_counts_correctly(db):
    seed = [(f"e{i}",f"Co{i}","EMEA","green",1,"") for i in range(3)]
    with _client(db, seed) as c:
        data = c.get("/api/compare").json()
    emea = next(t for t in data["theatres"] if t["theatre"] == "EMEA")
    assert emea["m9_total"] == 3


def test_blocked_count_correct(db):
    seed = [(f"j{i}",f"JCo{i}","JAPAC","blocked",0,"") for i in range(2)]
    with _client(db, seed) as c:
        data = c.get("/api/compare").json()
    japac = next(t for t in data["theatres"] if t["theatre"] == "JAPAC")
    assert japac["blocked"] == 2


def test_at_risk_count_correct(db):
    seed = [("a1","Acme","AMER","at_risk",0,""),("a2","Beta","AMER","green",0,"")]
    with _client(db, seed) as c:
        data = c.get("/api/compare").json()
    amer = next(t for t in data["theatres"] if t["theatre"] == "AMER")
    assert amer["at_risk"] == 1


def test_m9_this_week_uses_current_week(db):
    from datetime import date, timedelta
    monday = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    seed = [("a1","Acme","LATAM","green",1,monday)]
    with _client(db, seed) as c:
        data = c.get("/api/compare").json()
    latam = next(t for t in data["theatres"] if t["theatre"] == "LATAM")
    assert latam["m9_this_week"] >= 1
