"""
UNIT: dashboard.py — FastAPI route tests

Uses FastAPI TestClient with a temp SQLite DB (patched via agent.db.DB_PATH).
Tests response structure only — no assertions on live data values.
"""
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from fastapi.testclient import TestClient
from agent.db import init_db, get_db


@pytest.fixture
def test_db(tmp_path):
    """Temp DB initialised with schema."""
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _make_client(test_db):
    """Return TestClient with get_db patched to always use test_db."""
    from dashboard import app
    with patch("dashboard.get_db", side_effect=lambda *a, **k: get_db(test_db)), \
         patch("dashboard.init_db", side_effect=lambda *a, **k: None):
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(test_db):
    yield from _make_client(test_db)


@pytest.fixture
def client_with_data(test_db):
    """TestClient with one account + blocked_data row seeded."""
    with get_db(test_db) as conn:
        conn.execute("""INSERT INTO accounts
            (account_id, customer_name, active_cse, status, sales_region, account_theatre)
            VALUES (?, ?, ?, ?, ?, ?)""",
            ("acc001", "Acme Corp", "Jane Doe", "Ready To Engage", "CEE", "EMEA"))
        conn.execute("""INSERT INTO blocked_data
            (account_id, signal, subtype, m9_complete, account_theatre)
            VALUES (?, ?, ?, ?, ?)""",
            ("acc001", "blocked", "no_contact", 0, "EMEA"))
    yield from _make_client(test_db)


# ── /api/theatres ─────────────────────────────────────────────────────────────

class TestApiTheatres:
    def test_returns_200(self, client):
        r = client.get("/api/theatres")
        assert r.status_code == 200

    def test_returns_list(self, client):
        assert isinstance(r := client.get("/api/theatres").json(), list)


# ── /api/customer-search ──────────────────────────────────────────────────────

class TestApiCustomerSearch:
    def test_short_query_returns_empty(self, client):
        r = client.get("/api/customer-search?q=a")
        assert r.status_code == 200
        assert r.json() == []

    def test_empty_query_returns_empty(self, client):
        r = client.get("/api/customer-search?q=")
        assert r.status_code == 200
        assert r.json() == []

    def test_valid_query_returns_list(self, client_with_data):
        r = client_with_data.get("/api/customer-search?q=Acme")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_matching_query_finds_account(self, client_with_data):
        r = client_with_data.get("/api/customer-search?q=Acme")
        results = r.json()
        assert any(a.get("customer_name") == "Acme Corp" for a in results)

    def test_no_match_returns_empty_list(self, client_with_data):
        r = client_with_data.get("/api/customer-search?q=ZZZUnknown")
        assert r.json() == []


# ── /api/customer/{account_id} ────────────────────────────────────────────────

class TestApiCustomerDetail:
    def test_missing_account_returns_error(self, client):
        r = client.get("/api/customer/nonexistent_id")
        assert r.status_code == 404

    def test_existing_account_returns_200(self, client_with_data):
        r = client_with_data.get("/api/customer/acc001")
        assert r.status_code == 200

    def test_existing_account_has_customer_name(self, client_with_data):
        r = client_with_data.get("/api/customer/acc001")
        assert r.json().get("customer_name") == "Acme Corp"


# ── /api/blockers ─────────────────────────────────────────────────────────────

class TestApiBlockers:
    def test_returns_200(self, client):
        r = client.get("/api/blockers")
        assert r.status_code == 200

    def test_returns_dict_with_subtype_buckets(self, client):
        data = client.get("/api/blockers").json()
        assert isinstance(data, dict)
        assert "no_contact" in data
        assert "core_rep_blocking" in data
        assert "tech_blocker" in data
        assert "active_deal" in data
        assert "other" in data

    def test_theatre_filter_accepted(self, client):
        r = client.get("/api/blockers?theatre=EMEA")
        assert r.status_code == 200

    def test_blocked_account_appears_in_correct_bucket(self, client_with_data):
        data = client_with_data.get("/api/blockers").json()
        # acc001 has subtype=no_contact
        assert any(a["customer_name"] == "Acme Corp" for a in data["no_contact"])


# ── /api/forecast ─────────────────────────────────────────────────────────────

class TestApiForecast:
    def test_returns_200(self, client):
        r = client.get("/api/forecast")
        assert r.status_code == 200

    def test_theatre_param_accepted(self, client):
        r = client.get("/api/forecast?theatre=EMEA")
        assert r.status_code == 200


# ── /api/audit-log ────────────────────────────────────────────────────────────

class TestApiAuditLog:
    def test_returns_200(self, client):
        r = client.get("/api/audit-log")
        assert r.status_code == 200

    def test_returns_list(self, client):
        assert isinstance(client.get("/api/audit-log").json(), list)


# ── / redirect ────────────────────────────────────────────────────────────────

class TestRootRedirect:
    def test_root_redirects(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code in (307, 301, 302)
