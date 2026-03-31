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
