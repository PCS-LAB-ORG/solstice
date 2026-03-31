"""
UNIT: agent/dc_parser.py — DC CSE Tracker parser

Tests pure helper functions:
  _yn()                  — boolean normalisation
  _signal_from_detail()  — emoji → signal
  _subtype_from_detail() — text → blocker subtype
  _status_from_dc()      — DC fields → engagement status
  _clean_cse()           — CSE name sanitisation
  parse_dc_csv()         — CSV parsing with minimal fixture
"""
import csv
import io
import json
from pathlib import Path
import pytest

from agent.dc_parser import (
    _yn, _signal_from_detail, _subtype_from_detail,
    _status_from_dc, _clean_cse, parse_dc_csv, merge_into_state,
)


# ── _yn ───────────────────────────────────────────────────────────────────────

class TestYn:
    def test_y_is_true(self):          assert _yn("y") is True
    def test_Y_is_true(self):          assert _yn("Y") is True
    def test_yes_is_true(self):        assert _yn("yes") is True
    def test_x_is_true(self):          assert _yn("x") is True
    def test_1_is_true(self):          assert _yn("1") is True
    def test_true_is_true(self):       assert _yn("true") is True
    def test_empty_is_false(self):     assert _yn("") is False
    def test_n_is_false(self):         assert _yn("n") is False
    def test_no_is_false(self):        assert _yn("no") is False
    def test_whitespace_stripped(self): assert _yn("  y  ") is True
    def test_zero_is_false(self):      assert _yn("0") is False


# ── _signal_from_detail ───────────────────────────────────────────────────────

class TestSignalFromDetail:
    def test_green_tick_returns_green(self):
        assert _signal_from_detail("✅ On track") == "green"

    def test_stop_sign_returns_blocked(self):
        assert _signal_from_detail("🛑 Blocked by legal") == "blocked"

    def test_thumbs_down_returns_at_risk(self):
        assert _signal_from_detail("👎 Behind schedule") == "at_risk"

    def test_empty_returns_empty(self):
        assert _signal_from_detail("") == ""

    def test_no_emoji_returns_empty(self):
        assert _signal_from_detail("Upgrade in progress") == ""

    def test_emoji_must_be_prefix(self):
        # emoji in the middle doesn't count
        assert _signal_from_detail("Notes: ✅ done") == ""


# ── _subtype_from_detail ──────────────────────────────────────────────────────

class TestSubtypeFromDetail:
    def test_no_contact_phrase(self):
        assert _subtype_from_detail("not able to contact or connect with ngs team") == "no_contact"

    def test_internal_kickoff_phrase(self):
        assert _subtype_from_detail("blocked from internal kick-off meeting") == "no_contact"

    def test_core_rep_blocking(self):
        assert _subtype_from_detail("core rep is blocking the migration") == "core_rep_blocking"

    def test_account_team_blocking(self):
        assert _subtype_from_detail("account team is blocking upgrade") == "core_rep_blocking"

    def test_technical_reason(self):
        assert _subtype_from_detail("technical reason for delay") == "tech_blocker"

    def test_technical_blocker(self):
        assert _subtype_from_detail("technical blocker — needs eng fix") == "tech_blocker"

    def test_tech_limitation(self):
        assert _subtype_from_detail("tech limitation prevents migration") == "tech_blocker"

    def test_active_deal(self):
        assert _subtype_from_detail("active deal in progress") == "active_deal"

    def test_self_hosted(self):
        assert _subtype_from_detail("self-hosted deployment required") == "self_hosted"

    def test_empty_returns_empty(self):
        assert _subtype_from_detail("") == ""

    def test_no_match_returns_empty(self):
        assert _subtype_from_detail("upgrade started last week") == ""


# ── _status_from_dc ───────────────────────────────────────────────────────────

class TestStatusFromDc:
    def test_upgrade_complete_in_detail(self):
        assert _status_from_dc("upgrade complete confirmed", "") == "Completed"

    def test_cc_nnl_status(self):
        assert _status_from_dc("", "CC NNL") == "Completed"

    def test_upgrade_started(self):
        assert _status_from_dc("upgrade started last week", "") == "In Progress"

    def test_upgrade_in_progress(self):
        assert _status_from_dc("upgrade in progress", "") == "In Progress"

    def test_tech_validation_won(self):
        assert _status_from_dc("tech validation won by team", "") == "Customer Engaged"

    def test_customer_meeting_completed(self):
        assert _status_from_dc("customer meeting completed successfully", "") == "Customer Engaged"

    def test_customer_outreach_complete(self):
        assert _status_from_dc("customer outreach complete", "") == "Account team contacted"

    def test_outreach_made(self):
        assert _status_from_dc("outreach made to account", "") == "Account team contacted"

    def test_churn_status(self):
        assert _status_from_dc("", "Churn") == "Churning/Churned"

    def test_default_returns_account_team_contacted(self):
        assert _status_from_dc("", "") == "Account team contacted"


# ── _clean_cse ────────────────────────────────────────────────────────────────

class TestCleanCse:
    def test_normal_name_returned(self):
        assert _clean_cse("John Smith") == "John Smith"

    def test_known_typo_fixed(self):
        assert _clean_cse("Mikhail Bahkmetiev") == "Mikhail Bakhmetiev"

    def test_empty_returns_empty(self):
        assert _clean_cse("") == ""

    def test_whitespace_only_returns_empty(self):
        assert _clean_cse("   ") == ""

    def test_date_like_rejected(self):
        assert _clean_cse("12/03/2024") == ""

    def test_starts_with_digit_rejected(self):
        assert _clean_cse("3 people") == ""

    def test_at_sign_rejected(self):
        assert _clean_cse("john@company.com") == ""

    def test_slash_rejected(self):
        assert _clean_cse("John/Jane") == ""

    def test_tbd_rejected(self):
        assert _clean_cse("tbd") == ""

    def test_na_rejected(self):
        assert _clean_cse("n/a") == ""

    def test_to_be_hired_rejected(self):
        assert _clean_cse("to be hired") == ""

    def test_strips_whitespace(self):
        assert _clean_cse("  Jane Doe  ") == "Jane Doe"


# ── parse_dc_csv ──────────────────────────────────────────────────────────────

DC_HEADERS = [
    "account_theatre", "pc_end_customer_account_id", "pc_account_name",
    "CSE Assigned", "DC assignment", "Owner: End to end upgrade",
    "PC_CC_Migration_status", "customer_size_cohort_classification",
    "Email sent", "Status Detail", "Live-fire",
    "M0:Internal Kickoff Complete", "M1:Customer Outreach Complete",
    "Date - M1:Internal Kickoff Complete",
    "M2:Entitlements and Plan aligned with customer",
    "Date - M2:Entitlements and Plan aligned with customer",
    "M3:EB Buy-in Meeting Complete", "M3 Planned date",
    "Date - M3:EB Buy-in Meeting Complete",
    "M4:Discovery complete", "Date - M4:Discovery complete",
    "M5:Tech validation complete", "Date - M5:Tech validation complete",
    "M7:Legal and operational upgrade readiness",
    "M8:Upgrade started", "M8 Planned date", "Date - M8:Upgrade started",
    "M9:Upgrade complete", "M9 Planned date", "Date - M9:Upgrade complete",
    "Upgrade Notes", "Account Health Notes", "PM Status",
    "DC Upgrade Progress Status", "cc_Rep (SPO)", "cc_DSM (SPO)",
    "DC Indicated account churn risk", "Last edited by", "Last edited date",
    "roadmap", "ps plan", "account_region", "current_project_status",
    "next_cloud_renewal_date", "Past due planned dates",
    "Planned upgrade duration (weeks)", "Is there partner",
    "Upgrade partner name", "M1 Details", "M3 Details", "M5 Details",
    "Milestone aging calculation", "Days since milestones advanced", "MomentumX",
    "entitlement_provision", "activation_tenant_status", "Posture workloads",
]


def _make_dc_csv(tmp_path: Path, rows: list[dict]) -> Path:
    f = tmp_path / "dc.csv"
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=DC_HEADERS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            full = {h: "" for h in DC_HEADERS}
            full.update(row)
            w.writerow(full)
    return f


class TestParseDcCsv:
    def test_emea_row_included(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "EMEA", "pc_end_customer_account_id": "abc123",
             "pc_account_name": "Acme Ltd"}
        ])
        records = parse_dc_csv(f)
        assert len(records) == 1
        assert records[0]["account_id"] == "abc123"

    def test_japac_row_included(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "JAPAC", "pc_end_customer_account_id": "jp001",
             "pc_account_name": "Tokyo Corp"}
        ])
        records = parse_dc_csv(f)
        assert len(records) == 1

    def test_unknown_theatre_excluded(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "APAC", "pc_end_customer_account_id": "x1",
             "pc_account_name": "X Corp"}
        ])
        records = parse_dc_csv(f)
        assert len(records) == 0

    def test_missing_account_id_excluded(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "EMEA", "pc_end_customer_account_id": ""}
        ])
        records = parse_dc_csv(f)
        assert len(records) == 0

    def test_account_id_lowercased(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "EMEA", "pc_end_customer_account_id": "ABC123XYZ"}
        ])
        records = parse_dc_csv(f)
        assert records[0]["account_id"] == "abc123xyz"

    def test_m3_complete_parsed(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "EMEA", "pc_end_customer_account_id": "a1",
             "M3:EB Buy-in Meeting Complete": "y"}
        ])
        records = parse_dc_csv(f)
        assert records[0]["m3_complete"] is True

    def test_signal_derived_from_status_detail(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "EMEA", "pc_end_customer_account_id": "a1",
             "Status Detail": "🛑 Blocked by legal team"}
        ])
        records = parse_dc_csv(f)
        assert records[0]["signal"] == "blocked"

    def test_multiple_rows_returned(self, tmp_path):
        f = _make_dc_csv(tmp_path, [
            {"account_theatre": "EMEA", "pc_end_customer_account_id": "a1"},
            {"account_theatre": "EMEA", "pc_end_customer_account_id": "a2"},
        ])
        records = parse_dc_csv(f)
        assert len(records) == 2


# ── merge_into_state ──────────────────────────────────────────────────────────

class TestMergeIntoState:
    def _make_state(self, tmp_path, accounts: dict) -> Path:
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"accounts": accounts}))
        return f

    def test_matched_account_gets_cse(self, tmp_path):
        sf = self._make_state(tmp_path, {"abc123": {"active_cse": "Old CSE"}})
        records = [{"account_id": "abc123", "active_cse": "New CSE",
                    "email_sent": "", "live_fire": False,
                    "account_name": "Acme"}]
        merge_into_state(records, sf)
        state = json.loads(sf.read_text())
        assert state["accounts"]["abc123"]["active_cse"] == "New CSE"

    def test_unmatched_account_not_in_state(self, tmp_path):
        sf = self._make_state(tmp_path, {"existing": {}})
        records = [{"account_id": "unknown_id", "active_cse": "CSE",
                    "email_sent": "", "live_fire": False, "account_name": "X"}]
        result = merge_into_state(records, sf)
        assert result["unmatched"] == 1

    def test_state_file_updated_with_dc_last_updated(self, tmp_path):
        sf = self._make_state(tmp_path, {})
        merge_into_state([], sf)
        state = json.loads(sf.read_text())
        assert "dc_last_updated" in state
