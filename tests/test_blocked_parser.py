"""
UNIT: agent/blocked_parser.py — Blocked Accounts CSV parser

Tests pure helpers:
  _signal()   — emoji prefix → signal string
  _subtype()  — keyword → blocker subtype
"""
import pytest
from agent.blocked_parser import _signal, _subtype


# ── _signal ───────────────────────────────────────────────────────────────────

class TestSignal:
    def test_green_tick_returns_green(self):
        assert _signal("✅ On track") == "green"

    def test_thumbs_down_returns_at_risk(self):
        assert _signal("👎 Behind schedule") == "at_risk"

    def test_stop_sign_returns_blocked(self):
        assert _signal("🛑 Hard blocked") == "blocked"

    def test_no_emoji_returns_unknown(self):
        assert _signal("No status detail") == "unknown"

    def test_empty_returns_unknown(self):
        assert _signal("") == "unknown"

    def test_emoji_not_at_start_returns_unknown(self):
        assert _signal("text before ✅ emoji") == "unknown"


# ── _subtype ──────────────────────────────────────────────────────────────────

class TestSubtype:
    def test_core_rep_blocking(self):
        assert _subtype("Core rep is blocking the deal") == "core_rep_blocking"

    def test_technical_reason(self):
        assert _subtype("Technical reason preventing upgrade") == "tech_blocker"

    def test_not_able_to_contact(self):
        assert _subtype("Not able to contact the customer") == "no_contact"

    def test_active_deal(self):
        assert _subtype("Active deal in negotiation") == "active_deal"

    def test_no_match_returns_none(self):
        assert _subtype("General status update") is None

    def test_empty_returns_none(self):
        assert _subtype("") is None

    def test_case_insensitive(self):
        assert _subtype("CORE REP IS BLOCKING") == "core_rep_blocking"
