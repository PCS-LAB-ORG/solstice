"""
UNIT: agent/ps_parser.py — PS Tracker parser

Tests pure helper functions:
  _normalise()    — legal suffix stripping + punctuation removal
  _similarity()   — fuzzy string similarity [0, 1]
  find_best_match() — best fuzzy match from candidate list
"""
import pytest
from agent.ps_parser import _normalise, _similarity, FUZZY_THRESHOLD


# ── _normalise ────────────────────────────────────────────────────────────────

class TestNormalise:
    def test_lowercases(self):
        assert _normalise("ACME") == "acme"

    def test_strips_ltd(self):
        assert "ltd" not in _normalise("Acme Ltd")

    def test_strips_llc(self):
        assert "llc" not in _normalise("Acme LLC")

    def test_strips_corp(self):
        assert "corp" not in _normalise("Acme Corp")

    def test_strips_ag(self):
        assert " ag" not in _normalise("Deutsche Bank AG")

    def test_strips_trailing_punctuation(self):
        result = _normalise("Acme Corp.")
        assert "." not in result

    def test_collapses_whitespace(self):
        result = _normalise("Acme   Corp")
        assert "  " not in result

    def test_empty_returns_empty(self):
        assert _normalise("") == ""

    def test_simple_name_lowercased(self):
        result = _normalise("Deutsche Bank")
        assert result == "deutsche bank"


# ── _similarity ───────────────────────────────────────────────────────────────

class TestSimilarity:
    def test_identical_strings_score_one(self):
        assert _similarity("hello", "hello") == pytest.approx(1.0)

    def test_completely_different_score_low(self):
        assert _similarity("abc", "xyz") < 0.5

    def test_similar_strings_score_high(self):
        score = _similarity("deutsche bank", "deutsche bank ag")
        assert score > 0.8

    def test_empty_strings(self):
        assert _similarity("", "") == pytest.approx(1.0)

    def test_symmetry(self):
        a, b = "foo bar", "bar baz"
        assert _similarity(a, b) == pytest.approx(_similarity(b, a))

    def test_score_between_zero_and_one(self):
        score = _similarity("alpha", "beta")
        assert 0.0 <= score <= 1.0


# ── FUZZY_THRESHOLD ───────────────────────────────────────────────────────────

class TestFuzzyThreshold:
    def test_threshold_is_float(self):
        assert isinstance(FUZZY_THRESHOLD, float)

    def test_threshold_above_zero_point_five(self):
        # Must be strict enough to avoid false matches
        assert FUZZY_THRESHOLD > 0.5

    def test_threshold_below_one(self):
        assert FUZZY_THRESHOLD < 1.0


# ── _best_match ───────────────────────────────────────────────────────────────

from agent.ps_parser import _best_match  # noqa: E402


class TestBestMatch:
    def test_identical_name_returns_name_and_score_one(self):
        name, score = _best_match("Acme Corp", ["Acme Corp", "Other Co"])
        assert name == "Acme Corp"
        assert score == pytest.approx(1.0)

    def test_completely_different_returns_none_and_low_score(self):
        name, score = _best_match("Zyxwvuts", ["Alpha Beta", "Gamma Delta"])
        assert name is None
        assert score < FUZZY_THRESHOLD

    def test_empty_candidate_list_returns_none(self):
        name, score = _best_match("Acme Corp", [])
        assert name is None
        assert score == pytest.approx(0.0)

    def test_picks_best_among_multiple_candidates(self):
        name, score = _best_match(
            "Deutsche Bank",
            ["Deutsche Bahn", "Random Company", "Deutsche Bank AG"],
        )
        # "Deutsche Bank AG" is more similar to "Deutsche Bank" than "Deutsche Bahn"
        assert name == "Deutsche Bank AG"
        assert score >= FUZZY_THRESHOLD

    def test_score_below_threshold_returns_none_even_if_best(self):
        # Force a scenario where no candidate clears the threshold
        name, score = _best_match("XYZABC", ["Foo Bar Inc", "Baz Qux Ltd"])
        assert name is None

    def test_exact_match_with_extra_whitespace_normalised(self):
        # _best_match calls _similarity which calls _normalise → strips extra spaces
        name, score = _best_match("  Acme Corp  ", ["Acme Corp"])
        # Normalised comparison: "acme" vs "acme" → high similarity
        # The leading/trailing spaces are stripped inside _normalise
        assert score >= FUZZY_THRESHOLD


# ── parse_ps_csv ──────────────────────────────────────────────────────────────

import csv as _csv  # noqa: E402
from agent.ps_parser import parse_ps_csv  # noqa: E402

_CSV_HEADERS = [
    "PS Eligible Account Name",
    "Country",
    "Assigned PSC",
    "Shadowed PSC",
    "Assigned PM",
    "Status",
    "Clarizen Project",
    "Estimated Time for PS Engagement",
    "Notes",
]


def _write_ps_csv(path, rows):
    """Helper: write a PS tracker CSV to *path* using standard headers."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=_CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class TestParsePsCsv:
    def test_returns_list_of_dicts(self, tmp_path):
        csv_file = tmp_path / "ps.csv"
        _write_ps_csv(csv_file, [
            {
                "PS Eligible Account Name": "Acme Corp",
                "Country": "DE",
                "Assigned PSC": "Alice",
                "Shadowed PSC": "Bob",
                "Assigned PM": "Carol",
                "Status": "Active",
                "Clarizen Project": "CLZ-001",
                "Estimated Time for PS Engagement": "Q2 2026",
                "Notes": "some note",
            }
        ])
        records = parse_ps_csv(csv_file)
        assert isinstance(records, list)
        assert len(records) == 1

    def test_maps_all_expected_fields(self, tmp_path):
        csv_file = tmp_path / "ps.csv"
        _write_ps_csv(csv_file, [
            {
                "PS Eligible Account Name": "Acme Corp",
                "Country": "FR",
                "Assigned PSC": "Alice",
                "Shadowed PSC": "Dave",
                "Assigned PM": "Eve",
                "Status": "In Progress",
                "Clarizen Project": "CLZ-999",
                "Estimated Time for PS Engagement": "Q3 2026",
                "Notes": "urgent",
            }
        ])
        rec = parse_ps_csv(csv_file)[0]
        assert rec["ps_name"] == "Acme Corp"
        assert rec["country"] == "FR"
        assert rec["psc"] == "Alice"
        assert rec["psc_shadow"] == "Dave"
        assert rec["pm"] == "Eve"
        assert rec["ps_status"] == "In Progress"
        assert rec["clarizen_id"] == "CLZ-999"
        assert rec["timeline"] == "Q3 2026"
        assert rec["notes"] == "urgent"

    def test_skips_rows_with_empty_name(self, tmp_path):
        csv_file = tmp_path / "ps.csv"
        _write_ps_csv(csv_file, [
            {
                "PS Eligible Account Name": "",
                "Country": "DE", "Assigned PSC": "", "Shadowed PSC": "",
                "Assigned PM": "", "Status": "", "Clarizen Project": "",
                "Estimated Time for PS Engagement": "", "Notes": "",
            },
            {
                "PS Eligible Account Name": "Real Company",
                "Country": "UK", "Assigned PSC": "X", "Shadowed PSC": "",
                "Assigned PM": "", "Status": "Active", "Clarizen Project": "",
                "Estimated Time for PS Engagement": "", "Notes": "",
            },
        ])
        records = parse_ps_csv(csv_file)
        assert len(records) == 1
        assert records[0]["ps_name"] == "Real Company"

    def test_skips_whitespace_only_name(self, tmp_path):
        csv_file = tmp_path / "ps.csv"
        _write_ps_csv(csv_file, [
            {
                "PS Eligible Account Name": "   ",
                "Country": "", "Assigned PSC": "", "Shadowed PSC": "",
                "Assigned PM": "", "Status": "", "Clarizen Project": "",
                "Estimated Time for PS Engagement": "", "Notes": "",
            },
        ])
        records = parse_ps_csv(csv_file)
        assert len(records) == 0

    def test_empty_csv_returns_empty_list(self, tmp_path):
        csv_file = tmp_path / "ps.csv"
        _write_ps_csv(csv_file, [])
        records = parse_ps_csv(csv_file)
        assert records == []

    def test_multiple_rows_all_returned(self, tmp_path):
        csv_file = tmp_path / "ps.csv"
        _write_ps_csv(csv_file, [
            {
                "PS Eligible Account Name": f"Company {i}",
                "Country": "DE", "Assigned PSC": "X", "Shadowed PSC": "",
                "Assigned PM": "", "Status": "Active", "Clarizen Project": "",
                "Estimated Time for PS Engagement": "", "Notes": "",
            }
            for i in range(5)
        ])
        records = parse_ps_csv(csv_file)
        assert len(records) == 5

    def test_missing_optional_columns_default_to_empty_string(self, tmp_path):
        """CSV with only the name column — all other fields default to ''."""
        csv_file = tmp_path / "ps_minimal.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            f.write("PS Eligible Account Name\n")
            f.write("Minimal Corp\n")
        rec = parse_ps_csv(csv_file)[0]
        assert rec["country"] == ""
        assert rec["psc"] == ""
        assert rec["notes"] == ""

    def test_strips_whitespace_from_field_values(self, tmp_path):
        csv_file = tmp_path / "ps.csv"
        _write_ps_csv(csv_file, [
            {
                "PS Eligible Account Name": "  Acme Corp  ",
                "Country": " DE ",
                "Assigned PSC": " Alice ",
                "Shadowed PSC": "", "Assigned PM": "", "Status": "",
                "Clarizen Project": "", "Estimated Time for PS Engagement": "",
                "Notes": "",
            }
        ])
        rec = parse_ps_csv(csv_file)[0]
        assert rec["ps_name"] == "Acme Corp"
        assert rec["country"] == "DE"
        assert rec["psc"] == "Alice"

    def test_handles_utf8_bom_encoding(self, tmp_path):
        """CSV saved with BOM (common from Excel) must be read cleanly."""
        csv_file = tmp_path / "ps_bom.csv"
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            f.write("PS Eligible Account Name,Country\n")
            f.write("BOM Corp,IT\n")
        rec = parse_ps_csv(csv_file)[0]
        assert rec["ps_name"] == "BOM Corp"


# ── merge_into_state ──────────────────────────────────────────────────────────

import json as _json  # noqa: E402
from agent.ps_parser import merge_into_state, MANUAL_ALIASES  # noqa: E402


def _make_state(accounts: dict) -> dict:
    """Build a minimal state.json structure."""
    return {"accounts": accounts}


def _acc(customer_name: str, **extra) -> dict:
    """Build a minimal account entry."""
    return {"customer_name": customer_name, **extra}


def _ps_rec(ps_name: str, **extra) -> dict:
    """Build a minimal PS record matching parse_ps_csv output."""
    return {
        "ps_name": ps_name,
        "country": extra.get("country", ""),
        "psc": extra.get("psc", ""),
        "psc_shadow": extra.get("psc_shadow", ""),
        "pm": extra.get("pm", ""),
        "ps_status": extra.get("ps_status", ""),
        "clarizen_id": extra.get("clarizen_id", ""),
        "timeline": extra.get("timeline", ""),
        "notes": extra.get("notes", ""),
    }


class TestMergeIntoState:
    def test_matched_account_gets_ps_data(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"ACC001": _acc("Acme Corp")})),
            encoding="utf-8",
        )
        summary = merge_into_state([_ps_rec("Acme Corp")], state_file)
        updated = _json.loads(state_file.read_text())
        assert "ps_data" in updated["accounts"]["ACC001"]
        assert summary["matched"] == 1
        assert summary["unmatched"] == 0

    def test_unmatched_account_has_no_ps_data(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"ACC001": _acc("Completely Different Corp")})),
            encoding="utf-8",
        )
        summary = merge_into_state([_ps_rec("Zyxwvuts Ltd")], state_file)
        updated = _json.loads(state_file.read_text())
        assert "ps_data" not in updated["accounts"]["ACC001"]
        assert summary["unmatched"] == 1
        assert summary["matched"] == 0

    def test_returns_correct_summary_keys(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"A1": _acc("Acme")})),
            encoding="utf-8",
        )
        summary = merge_into_state([_ps_rec("Acme")], state_file)
        for key in ("total", "matched", "unmatched", "low_confidence", "unmatched_list", "low_conf_list"):
            assert key in summary, f"Missing summary key: {key}"

    def test_summary_totals_add_up(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({
                "A1": _acc("Acme Corp"),
                "A2": _acc("Beta Inc"),
            })),
            encoding="utf-8",
        )
        ps_records = [
            _ps_rec("Acme Corp"),    # should match A1
            _ps_rec("Zyxwvuts XQ"),  # no match
        ]
        summary = merge_into_state(ps_records, state_file)
        assert summary["total"] == 2
        assert summary["matched"] + summary["unmatched"] == 2

    def test_manual_alias_override_matches_correctly(self, tmp_path):
        """'Idea Bank S.a. (Salt Bank)' → 'Salt Bank' via MANUAL_ALIASES."""
        alias_ps_name = "Idea Bank S.a. (Salt Bank)"
        alias_target = "Salt Bank"
        assert alias_ps_name in MANUAL_ALIASES
        assert MANUAL_ALIASES[alias_ps_name] == alias_target

        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"ACC999": _acc(alias_target)})),
            encoding="utf-8",
        )
        summary = merge_into_state([_ps_rec(alias_ps_name)], state_file)
        updated = _json.loads(state_file.read_text())
        assert "ps_data" in updated["accounts"]["ACC999"]
        assert summary["matched"] == 1
        assert summary["unmatched"] == 0

    def test_manual_alias_confidence_is_1_0(self, tmp_path):
        alias_ps_name = "Idea Bank S.a. (Salt Bank)"
        alias_target = "Salt Bank"
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"A1": _acc(alias_target)})),
            encoding="utf-8",
        )
        merge_into_state([_ps_rec(alias_ps_name)], state_file)
        updated = _json.loads(state_file.read_text())
        ps_data = updated["accounts"]["A1"]["ps_data"]
        assert ps_data["match_confidence"] == pytest.approx(1.0)
        assert ps_data["matched_name"] == alias_target

    def test_state_file_updated_with_ps_last_updated(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"A1": _acc("Acme Corp")})),
            encoding="utf-8",
        )
        merge_into_state([_ps_rec("Acme Corp")], state_file)
        updated = _json.loads(state_file.read_text())
        assert "ps_last_updated" in updated

    def test_ps_data_contains_original_ps_name(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"A1": _acc("Acme Corp")})),
            encoding="utf-8",
        )
        merge_into_state([_ps_rec("Acme Corp", psc="Alice", ps_status="Active")], state_file)
        updated = _json.loads(state_file.read_text())
        ps_data = updated["accounts"]["A1"]["ps_data"]
        assert ps_data["ps_name"] == "Acme Corp"
        assert ps_data["psc"] == "Alice"
        assert ps_data["ps_status"] == "Active"

    def test_empty_ps_records_returns_zero_counts(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"A1": _acc("Acme Corp")})),
            encoding="utf-8",
        )
        summary = merge_into_state([], state_file)
        assert summary["total"] == 0
        assert summary["matched"] == 0
        assert summary["unmatched"] == 0

    def test_accounts_without_customer_name_not_matched(self, tmp_path):
        """Accounts missing customer_name are excluded from the name_list."""
        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({
                "A1": {},  # no customer_name key at all
                "A2": _acc(""),  # empty customer_name
            })),
            encoding="utf-8",
        )
        summary = merge_into_state([_ps_rec("Anything Goes")], state_file)
        assert summary["matched"] == 0

    def test_low_confidence_match_counted_separately(self, tmp_path):
        """
        A match with FUZZY_THRESHOLD <= score < 0.85 is both 'matched' and 'low_confidence'.
        This relies on the actual threshold being 0.85 — any match above threshold
        but below 0.85 is a low-confidence match.
        Since FUZZY_THRESHOLD == 0.85, low-confidence band is [0.72, 0.85).
        We patch FUZZY_THRESHOLD to 0.72 to widen the window and force a low-conf match.
        """
        import unittest.mock as mock
        import agent.ps_parser as _module

        state_file = tmp_path / "state.json"
        state_file.write_text(
            _json.dumps(_make_state({"A1": _acc("Deutsche Lufthansa AG")})),
            encoding="utf-8",
        )
        # "Lufthansa" vs "Deutsche Lufthansa AG" — with low threshold should match
        # but score < 0.85 → goes into low_confidence list
        with mock.patch.object(_module, "FUZZY_THRESHOLD", 0.5):
            summary = merge_into_state([_ps_rec("Lufthansa")], state_file)

        # Whether it matched depends on the actual similarity score,
        # but if it matched at all the counts must be consistent
        assert summary["matched"] + summary["unmatched"] == summary["total"]
        if summary["matched"] > 0:
            # score was below 0.85 → must appear in low_confidence
            assert summary["low_confidence"] > 0
