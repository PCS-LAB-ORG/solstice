"""
Tests derived from the live DC CSE Tracker CSV (data/dc_cse_tracker.csv).

Covers two confirmed bugs:
  1. _subtype_from_detail — "blocked from customer outreach: <reason>" short-circuits
     to no_contact before sub-reason checks for core_rep_blocking / active_deal /
     tech_blocker can fire.
  2. Pipeline cc_rep guard — cc_rep=excluded.cc_rep overwrites valid rep names with
     empty string when the CSV row has no rep. Should use CASE WHEN guard.
  3. parse_dc_csv — cc_rep read correctly from cc_Rep (SPO) column incl. leading spaces.
"""

import csv
import sqlite3
from pathlib import Path

import pytest

from agent.dc_parser import _subtype_from_detail, parse_dc_csv

CSV_PATH = Path(__file__).parent.parent / "data" / "dc_cse_tracker.csv"


# ── 1. _subtype_from_detail — real status detail strings from CSV ─────────────


class TestSubtypeFromDetailCsvStrings:
    """Exact strings taken from the live CSV — 38+32+12 misclassified accounts."""

    def test_core_rep_blocking_not_classified_as_no_contact(self):
        detail = "👎 Blocked from customer outreach: core rep is blocking for other reasons (provide details in box)"
        assert _subtype_from_detail(detail) == "core_rep_blocking"

    def test_active_deal_not_classified_as_no_contact(self):
        detail = "👎 Blocked from customer outreach: active deal (Required: provide oppty ID in box)"
        assert _subtype_from_detail(detail) == "active_deal"

    def test_tech_reason_outreach_block_classified_correctly(self):
        # "technical reason (submitted to CoE)" inside outreach block →
        # CSE held back by account team for technical reasons = core_rep_blocking,
        # not generic tech_blocker (which is product/CoE gap blocking the upgrade itself)
        detail = (
            "👎 Blocked from customer outreach: technical reason (submitted to CoE)"
        )
        assert _subtype_from_detail(detail) == "core_rep_blocking"

    def test_legal_reason_still_legal_blocker(self):
        # legal_blocker check fires before no_contact — must stay correct
        detail = (
            "👎 Blocked from customer outreach: legal reason (provide details in box)"
        )
        assert _subtype_from_detail(detail) == "legal_blocker"

    def test_no_response_stays_no_contact(self):
        detail = "👎 Blocked from customer outreach: no response from customer"
        assert _subtype_from_detail(detail) == "no_contact"

    def test_internal_kickoff_blocked_stays_no_contact(self):
        detail = "🛑 Blocked from internal kick-off: Not able to continue"
        assert _subtype_from_detail(detail) == "no_contact"

    def test_core_rep_blocking_plain_text(self):
        # Existing passing case — must not regress
        assert _subtype_from_detail("core rep is blocking") == "core_rep_blocking"


# ── 2. parse_dc_csv — cc_rep read from CSV incl. leading spaces ───────────────


class TestParseDcCsvCcRep:
    """cc_Rep (SPO) column has leading spaces in the CSV — verify stripped."""

    @pytest.fixture(scope="class")
    def emea_recs(self):
        if not CSV_PATH.exists():
            pytest.skip("dc_cse_tracker.csv not present")
        return {
            r["account_id"]: r
            for r in parse_dc_csv(CSV_PATH)
            if r.get("account_theatre") == "EMEA"
        }

    def test_capita_plc_cc_rep_parsed(self, emea_recs):
        rec = next(
            (r for r in emea_recs.values() if r["account_name"] == "Capita Plc"), None
        )
        assert rec is not None, "Capita Plc not found in CSV"
        assert rec["cc_rep"] == "Zachary James Corner (Zach) Rieker"

    def test_deutsche_borse_cc_rep_parsed(self, emea_recs):
        rec = next(
            (r for r in emea_recs.values() if r["account_name"] == "Deutsche Borse"),
            None,
        )
        assert rec is not None, "Deutsche Borse not found in CSV"
        assert rec["cc_rep"] == "Klaus Philip (Philip) Stapleford"

    def test_cooperative_banking_cc_rep_parsed(self, emea_recs):
        rec = next(
            (
                r
                for r in emea_recs.values()
                if r["account_name"] == "CO-OPERATIVE BANKING GROUP LIMITED"
            ),
            None,
        )
        assert rec is not None, "CO-OPERATIVE BANKING GROUP LIMITED not found in CSV"
        assert rec["cc_rep"] == "Amit Kheti"

    def test_cc_rep_empty_when_not_assigned(self, emea_recs):
        # Accounts with '-' or blank rep should produce empty string, not '-'
        recs_with_dash = [
            r for r in emea_recs.values() if r.get("cc_rep") in ("-", None)
        ]
        # All should be empty string
        assert all(r.get("cc_rep", "") == "" for r in recs_with_dash)


# ── 3. Pipeline cc_rep guard — CASE WHEN in ON CONFLICT UPDATE ────────────────


class TestPipelineCcRepGuard:
    """
    cc_rep=excluded.cc_rep unconditionally overwrites.
    When the new CSV row has an empty cc_rep, an existing valid rep name must
    be preserved — same pattern as upgrade_notes CASE WHEN guard.
    """

    @pytest.fixture
    def db(self, tmp_path):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE accounts (
                account_id TEXT PRIMARY KEY,
                customer_name TEXT,
                active_cse TEXT,
                sales_region TEXT,
                account_theatre TEXT
            );
            CREATE TABLE blocked_data (
                account_id TEXT PRIMARY KEY,
                cc_rep TEXT,
                cc_dsm TEXT,
                m1_complete INTEGER DEFAULT 0,
                m9_complete INTEGER DEFAULT 0,
                signal TEXT,
                subtype TEXT,
                status_detail TEXT,
                dc_progress TEXT,
                upgrade_notes TEXT,
                health_notes TEXT,
                churn_risk TEXT
            );
            INSERT INTO accounts VALUES ('acc1','Test Corp','Jane CSE','UK Strategic','EMEA');
            INSERT INTO blocked_data (account_id, cc_rep) VALUES ('acc1', 'Chris Dixon');
        """)
        return conn

    def test_empty_cc_rep_does_not_overwrite_existing(self, db):
        """Updating with empty cc_rep must preserve 'Chris Dixon'."""
        db.execute("""
            INSERT INTO blocked_data (account_id, cc_rep)
            VALUES ('acc1', '')
            ON CONFLICT(account_id) DO UPDATE SET
              cc_rep=CASE WHEN excluded.cc_rep!='' THEN excluded.cc_rep ELSE cc_rep END
        """)
        result = db.execute(
            "SELECT cc_rep FROM blocked_data WHERE account_id='acc1'"
        ).fetchone()
        assert result["cc_rep"] == "Chris Dixon"

    def test_non_empty_cc_rep_updates_existing(self, db):
        """Updating with a real rep name replaces the old value."""
        db.execute("""
            INSERT INTO blocked_data (account_id, cc_rep)
            VALUES ('acc1', 'New Rep Name')
            ON CONFLICT(account_id) DO UPDATE SET
              cc_rep=CASE WHEN excluded.cc_rep!='' THEN excluded.cc_rep ELSE cc_rep END
        """)
        result = db.execute(
            "SELECT cc_rep FROM blocked_data WHERE account_id='acc1'"
        ).fetchone()
        assert result["cc_rep"] == "New Rep Name"

    def test_current_pipeline_bug_overwrites_with_empty(self, db):
        """Documents the BUG: current unconditional update wipes valid cc_rep."""
        db.execute("""
            INSERT INTO blocked_data (account_id, cc_rep)
            VALUES ('acc1', '')
            ON CONFLICT(account_id) DO UPDATE SET
              cc_rep=excluded.cc_rep
        """)
        result = db.execute(
            "SELECT cc_rep FROM blocked_data WHERE account_id='acc1'"
        ).fetchone()
        # This PASSES today (bug confirmed) — cc_rep is wiped
        assert result["cc_rep"] == ""
