"""
Unit tests for agent/account_list_parser.py
Uses synthetic fixture rows — no file I/O.
"""

import pytest
from agent.account_list_parser import parse_row, emoji_to_signal, emoji_to_churn

SAMPLE_ROW = {
    "Pc Account Name": "Acme Corp",
    "Account District": "UK Majors",
    "ARR": "500000",
    "DC Upgrade Status": "🟢",
    "DC Indicated Churn Risk": "🟡",
    "DC assignment": "Jane CSE",
    "CC Rep (SPO)": " Chris Rep",
    "M0:Internal Kickoff Complete": "Y",
    "M1:Customer Outreach Complete": "Y",
    "M2:Entitlements and Plan aligned with customer": "Y",
    "M3:EB Buy-in Meeting Complete": "N",
    "M4:Discovery complete": "",
    "M5:Tech validation complete": "",
    "Provisioned": "Y",
    "M6: Activated": "",
    "M7: PS Readiness": "",
    "M8:Upgrade started": "",
    "M9:Upgrade complete": "",
    "Status Detail": "On track",
    "M3 Planned date": "4/30/2026",
    "M8 Planned date": "8/31/2026",
    "M9 Planned date": "9/30/2026",
    "Account Health Notes": "Good",
    "Next Cloud Renewal Date": "12/31/2026",
    "Upgrade Notes": "No blockers",
}

KNOWN_ID = "abc123"


class TestEmojiToSignal:
    def test_green_emoji(self):
        assert emoji_to_signal("🟢") == "green"

    def test_yellow_emoji(self):
        assert emoji_to_signal("🟡") == "at_risk"

    def test_red_emoji(self):
        assert emoji_to_signal("🔴") == "blocked"

    def test_blank(self):
        assert emoji_to_signal("") == ""

    def test_space(self):
        assert emoji_to_signal(" ") == ""


class TestEmojiToChurn:
    def test_red_is_red(self):
        assert emoji_to_churn("🔴") == "Red"

    def test_yellow_is_yellow(self):
        assert emoji_to_churn("🟡") == "Yellow"

    def test_green_is_green(self):
        assert emoji_to_churn("🟢") == "Green"

    def test_blank(self):
        assert emoji_to_churn("") == ""


class TestParseRow:
    def test_account_name(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["account_name"] == "Acme Corp"

    def test_account_id_used_when_provided(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["account_id"] == KNOWN_ID

    def test_synthetic_id_when_no_id(self):
        r = parse_row(SAMPLE_ROW, "")
        assert len(r["account_id"]) == 15
        assert r["account_id"].isalnum()

    def test_sales_region(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["sales_region"] == "UK Majors"

    def test_active_cse_from_dc_assignment(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["active_cse"] == "Jane CSE"

    def test_cc_rep_stripped(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["cc_rep"] == "Chris Rep"

    def test_m0_complete_y(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m0_complete"] is True

    def test_m1_complete_y(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m1_complete"] is True

    def test_m3_complete_n(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m3_complete"] is False

    def test_m4_complete_blank(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m4_complete"] is False

    def test_m6_complete_blank(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m6_complete"] is False

    def test_signal_from_dc_upgrade_status(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["signal"] == "green"

    def test_churn_risk_from_dc_churn(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["churn_risk"] == "Yellow"

    def test_m3_planned(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m3_planned"] == "4/30/2026"

    def test_m8_planned(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["m8_planned"] == "8/31/2026"

    def test_account_theatre_hardcoded_emea(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["account_theatre"] == "EMEA"

    def test_status_detail(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["status_detail"] == "On track"

    def test_health_notes(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["health_notes"] == "Good"

    def test_upgrade_notes(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["upgrade_notes"] == "No blockers"

    def test_arr(self):
        r = parse_row(SAMPLE_ROW, KNOWN_ID)
        assert r["arr"] == "500000"
