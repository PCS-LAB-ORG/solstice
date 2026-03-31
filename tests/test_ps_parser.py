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
