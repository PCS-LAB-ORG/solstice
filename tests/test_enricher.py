"""
UNIT: agent/enricher.py — AI comment analyser

Tests pure/mockable functions:
  _comments_hash()     — consistent MD5 hash of comment text
  enrich_accounts()    — skips accounts with no comments, re-uses cache, calls LLM
                         (LLM call mocked)
"""
import json
import hashlib
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from agent.enricher import _comments_hash


# ── _comments_hash ────────────────────────────────────────────────────────────

class TestCommentsHash:
    def test_same_input_same_hash(self):
        assert _comments_hash("hello") == _comments_hash("hello")

    def test_different_input_different_hash(self):
        assert _comments_hash("hello") != _comments_hash("world")

    def test_returns_string(self):
        assert isinstance(_comments_hash("test"), str)

    def test_matches_md5(self):
        expected = hashlib.md5("test text".encode("utf-8")).hexdigest()
        assert _comments_hash("test text") == expected

    def test_empty_string_has_hash(self):
        result = _comments_hash("")
        assert isinstance(result, str)
        assert len(result) == 32  # MD5 hex length

    def test_unicode_input(self):
        result = _comments_hash("Ünïcödé text")
        assert isinstance(result, str)
        assert len(result) == 32


# ── _needs_enrichment ─────────────────────────────────────────────────────────

from agent.enricher import _needs_enrichment


class TestNeedsEnrichment:
    def test_no_comments_returns_false(self):
        assert _needs_enrichment({}) is False

    def test_empty_string_comments_returns_false(self):
        assert _needs_enrichment({"comments": ""}) is False

    def test_whitespace_only_comments_returns_false(self):
        assert _needs_enrichment({"comments": "   "}) is False

    def test_comments_with_no_existing_enrichment_returns_true(self):
        acc = {"comments": "customer blocked by legal"}
        assert _needs_enrichment(acc) is True

    def test_comments_with_empty_enrichment_dict_returns_true(self):
        acc = {"comments": "customer blocked by legal", "ai_enrichment": {}}
        assert _needs_enrichment(acc) is True

    def test_comments_unchanged_hash_matches_returns_false(self):
        text = "customer blocked by legal"
        h = _comments_hash(text)
        acc = {
            "comments": text,
            "ai_enrichment": {"comments_hash": h, "blocker": "legal", "owner": None, "accountable": None},
        }
        assert _needs_enrichment(acc) is False

    def test_comments_changed_hash_mismatch_returns_true(self):
        original = "customer blocked by legal"
        updated = "customer blocked by budget"
        h = _comments_hash(original)
        acc = {
            "comments": updated,
            "ai_enrichment": {"comments_hash": h, "blocker": "legal", "owner": None, "accountable": None},
        }
        assert _needs_enrichment(acc) is True

    def test_none_comments_returns_false(self):
        assert _needs_enrichment({"comments": None}) is False

    def test_enrichment_none_value_with_comments_returns_true(self):
        acc = {"comments": "some notes", "ai_enrichment": None}
        assert _needs_enrichment(acc) is True


# ── enrich_accounts ───────────────────────────────────────────────────────────

from agent.enricher import enrich_accounts


def _make_state(accounts: dict) -> dict:
    return {"accounts": accounts}


FAKE_ENRICHMENT_JSON = json.dumps(
    [{"account_id": "a1", "blocker": "no budget", "owner": "John", "accountable": None}]
)


class TestEnrichAccounts:
    def test_empty_accounts_returns_zero_enriched(self, tmp_path):
        sf = tmp_path / "state.json"
        sf.write_text(json.dumps(_make_state({})))
        result = enrich_accounts(sf)
        assert result == {"enriched": 0, "skipped": 0}

    def test_no_comments_skips_all(self, tmp_path):
        sf = tmp_path / "state.json"
        accounts = {
            "a1": {"comments": "", "customer_name": "Acme"},
            "a2": {"comments": None, "customer_name": "Beta"},
            "a3": {"customer_name": "Gamma"},
        }
        sf.write_text(json.dumps(_make_state(accounts)))
        result = enrich_accounts(sf)
        assert result == {"enriched": 0, "skipped": 3}

    def test_already_enriched_unchanged_skips(self, tmp_path):
        sf = tmp_path / "state.json"
        text = "migration blocked by firewall policy"
        h = _comments_hash(text)
        accounts = {
            "a1": {
                "comments": text,
                "ai_enrichment": {
                    "comments_hash": h,
                    "blocker": "firewall",
                    "owner": "Alice",
                    "accountable": None,
                    "enriched_at": "2026-01-01T00:00:00+00:00",
                },
            }
        }
        sf.write_text(json.dumps(_make_state(accounts)))
        result = enrich_accounts(sf)
        assert result == {"enriched": 0, "skipped": 1}

    def test_account_needing_enrichment_calls_batch_and_writes_result(self, tmp_path):
        sf = tmp_path / "state.json"
        accounts = {"a1": {"comments": "no budget this quarter", "customer_name": "Acme"}}
        sf.write_text(json.dumps(_make_state(accounts)))

        with patch("agent.enricher.chat", return_value=FAKE_ENRICHMENT_JSON):
            result = enrich_accounts(sf)

        assert result["enriched"] == 1
        assert result["skipped"] == 0

        written = json.loads(sf.read_text())
        enrichment = written["accounts"]["a1"]["ai_enrichment"]
        assert enrichment["blocker"] == "no budget"
        assert enrichment["owner"] == "John"
        assert enrichment["accountable"] is None
        assert enrichment["comments_hash"] == _comments_hash("no budget this quarter")
        assert "enriched_at" in enrichment

    def test_hash_updated_in_state_file_on_write(self, tmp_path):
        sf = tmp_path / "state.json"
        old_text = "original comment"
        new_text = "updated comment — new issue"
        old_hash = _comments_hash(old_text)
        accounts = {
            "a1": {
                "comments": new_text,
                "ai_enrichment": {
                    "comments_hash": old_hash,
                    "blocker": "old",
                    "owner": None,
                    "accountable": None,
                    "enriched_at": "2026-01-01T00:00:00+00:00",
                },
            }
        }
        sf.write_text(json.dumps(_make_state(accounts)))

        fake = json.dumps([{"account_id": "a1", "blocker": "updated blocker", "owner": "Eve", "accountable": "PM"}])
        with patch("agent.enricher.chat", return_value=fake):
            enrich_accounts(sf)

        written = json.loads(sf.read_text())
        enrichment = written["accounts"]["a1"]["ai_enrichment"]
        assert enrichment["comments_hash"] == _comments_hash(new_text)
        assert enrichment["blocker"] == "updated blocker"

    def test_multiple_accounts_mixed_state(self, tmp_path):
        sf = tmp_path / "state.json"
        cached_text = "already done"
        cached_hash = _comments_hash(cached_text)
        accounts = {
            "a1": {"comments": "needs enrichment", "customer_name": "X"},
            "a2": {
                "comments": cached_text,
                "ai_enrichment": {"comments_hash": cached_hash, "blocker": None, "owner": None, "accountable": None},
            },
            "a3": {"comments": None},
        }
        sf.write_text(json.dumps(_make_state(accounts)))

        fake = json.dumps([{"account_id": "a1", "blocker": "tech issue", "owner": "Bob", "accountable": None}])
        with patch("agent.enricher.chat", return_value=fake):
            result = enrich_accounts(sf)

        assert result["enriched"] == 1
        assert result["skipped"] == 2

    def test_state_file_written_back_preserves_other_fields(self, tmp_path):
        sf = tmp_path / "state.json"
        accounts = {
            "a1": {
                "comments": "blocked by certs",
                "customer_name": "Acme",
                "status": "blocked",
                "some_other_field": "preserved",
            }
        }
        state = _make_state(accounts)
        state["metadata"] = {"version": 42}
        sf.write_text(json.dumps(state))

        with patch("agent.enricher.chat", return_value=FAKE_ENRICHMENT_JSON):
            enrich_accounts(sf)

        written = json.loads(sf.read_text())
        assert written["metadata"]["version"] == 42
        assert written["accounts"]["a1"]["customer_name"] == "Acme"
        assert written["accounts"]["a1"]["status"] == "blocked"
        assert written["accounts"]["a1"]["some_other_field"] == "preserved"

    def test_returns_enriched_count_equals_accounts_with_comments(self, tmp_path):
        sf = tmp_path / "state.json"
        accounts = {
            "a1": {"comments": "issue one"},
            "a2": {"comments": "issue two"},
            "a3": {"comments": ""},
        }
        sf.write_text(json.dumps(_make_state(accounts)))

        fake = json.dumps([
            {"account_id": "a1", "blocker": "b1", "owner": "O1", "accountable": None},
            {"account_id": "a2", "blocker": "b2", "owner": "O2", "accountable": None},
        ])
        with patch("agent.enricher.chat", return_value=fake):
            result = enrich_accounts(sf)

        assert result["enriched"] == 2
        assert result["skipped"] == 1
