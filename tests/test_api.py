import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from agent.api import app


def make_state(last_run, n_accounts):
    return {
        "last_run": last_run,
        "accounts": {f"id{i}": {} for i in range(n_accounts)},
    }


def test_status_returns_200():
    state = make_state("2026-03-21T16:00:00Z", 300)
    with patch("agent.api.load_state", return_value=state):
        client = TestClient(app)
        r = client.get("/status")
    assert r.status_code == 200


def test_status_contains_account_count():
    state = make_state("2026-03-21T16:00:00Z", 42)
    with patch("agent.api.load_state", return_value=state):
        client = TestClient(app)
        r = client.get("/status")
    assert r.json()["account_count"] == 42


def test_status_contains_last_run():
    state = make_state("2026-03-21T16:00:00Z", 10)
    with patch("agent.api.load_state", return_value=state):
        client = TestClient(app)
        r = client.get("/status")
    assert r.json()["last_run"] == "2026-03-21T16:00:00Z"


def test_status_when_no_state():
    with patch("agent.api.load_state", return_value={"last_run": "", "accounts": {}}):
        client = TestClient(app)
        r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["account_count"] == 0
