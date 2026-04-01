"""Tests for /api/cse-workload."""
import pytest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import date
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
            for aid, name, cse, theatre, signal, m9, m9_actual in seed:
                conn.execute(
                    "INSERT INTO accounts (account_id,customer_name,active_cse,account_theatre) VALUES (?,?,?,?)",
                    (aid, name, cse, theatre))
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
        assert c.get("/api/cse-workload").status_code == 200


def test_returns_list(db):
    with _client(db) as c:
        assert isinstance(c.get("/api/cse-workload").json(), list)


def test_empty_db_returns_empty(db):
    with _client(db) as c:
        assert c.get("/api/cse-workload").json() == []


def test_groups_by_cse(db):
    seed = [
        ("a1","Acme","Jane","EMEA","blocked",0,""),
        ("a2","Beta","Jane","EMEA","green",0,""),
        ("a3","Gamma","Mike","EMEA","green",0,""),
    ]
    with _client(db, seed) as c:
        data = c.get("/api/cse-workload").json()
    names = [r["cse"] for r in data]
    assert "Jane" in names
    assert "Mike" in names


def test_account_count_correct(db):
    seed = [
        ("a1","Acme","Jane","EMEA","blocked",0,""),
        ("a2","Beta","Jane","EMEA","green",0,""),
    ]
    with _client(db, seed) as c:
        data = c.get("/api/cse-workload").json()
    jane = next(r for r in data if r["cse"] == "Jane")
    assert jane["account_count"] == 2


def test_blocked_count_correct(db):
    seed = [
        ("a1","Acme","Jane","EMEA","blocked",0,""),
        ("a2","Beta","Jane","EMEA","blocked",0,""),
        ("a3","Gamma","Jane","EMEA","green",0,""),
    ]
    with _client(db, seed) as c:
        data = c.get("/api/cse-workload").json()
    jane = next(r for r in data if r["cse"] == "Jane")
    assert jane["blocked_count"] == 2


def test_theatre_filter(db):
    seed = [
        ("a1","Acme","Jane","EMEA","green",0,""),
        ("a2","Beta","Mike","JAPAC","green",0,""),
    ]
    with _client(db, seed) as c:
        data = c.get("/api/cse-workload?theatre=EMEA").json()
    assert all(r["cse"] == "Jane" for r in data)


def test_m9_this_month_counted(db):
    first = date.today().replace(day=1).isoformat()
    seed = [("a1","Acme","Jane","EMEA","green",1,first)]
    with _client(db, seed) as c:
        data = c.get("/api/cse-workload").json()
    jane = next(r for r in data if r["cse"] == "Jane")
    assert jane["m9_this_month"] >= 1


def test_response_has_required_keys(db):
    seed = [("a1","Acme","Jane","EMEA","green",0,"")]
    with _client(db, seed) as c:
        data = c.get("/api/cse-workload").json()
    for key in ("cse","account_count","blocked_count","at_risk_count","m9_this_month"):
        assert key in data[0]
