"""
UNIT: agent/llm.py — Local Ollama LLM wrapper

Tests:
  _is_running()    — urlopen success → True; exception → False
  ensure_ollama()  — already running → no Popen; not running → Popen + poll; never starts → RuntimeError
  _best_model()    — primary found; fallback; any available; exception → primary
  chat()           — not running → RuntimeError; valid response → content; system_prompt included; expect_json=False → no format key
"""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, call, patch

import pytest

import agent.llm as llm
from agent.llm import (
    FALLBACK_MODEL,
    OLLAMA_BASE,
    PRIMARY_MODEL,
    _best_model,
    _is_running,
    chat,
    ensure_ollama,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_response(body: dict) -> MagicMock:
    """Return a context-manager mock that yields a readable fake HTTP response."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _tags_response(model_names: list[str]) -> MagicMock:
    """Fake /api/tags response containing the given model names."""
    body = {"models": [{"name": n} for n in model_names]}
    return _make_response(body)


# ── TestIsRunning ─────────────────────────────────────────────────────────────

class TestIsRunning:
    def test_returns_true_when_urlopen_succeeds(self):
        fake_resp = MagicMock()
        with patch("agent.llm.urllib.request.urlopen", return_value=fake_resp):
            assert _is_running() is True

    def test_returns_false_when_urlopen_raises(self):
        import urllib.error
        with patch(
            "agent.llm.urllib.request.urlopen",
            side_effect=urllib.error.URLError("refused"),
        ):
            assert _is_running() is False

    def test_returns_false_on_any_exception(self):
        with patch(
            "agent.llm.urllib.request.urlopen",
            side_effect=OSError("network error"),
        ):
            assert _is_running() is False

    def test_calls_correct_url(self):
        fake_resp = MagicMock()
        with patch("agent.llm.urllib.request.urlopen", return_value=fake_resp) as mock_open:
            _is_running()
        mock_open.assert_called_once_with(f"{OLLAMA_BASE}/api/tags", timeout=3)


# ── TestEnsureOllama ──────────────────────────────────────────────────────────

class TestEnsureOllama:
    def test_already_running_does_not_call_popen(self):
        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm.subprocess.Popen") as mock_popen,
        ):
            ensure_ollama()
        mock_popen.assert_not_called()

    def test_already_running_returns_none(self):
        with patch("agent.llm._is_running", return_value=True):
            result = ensure_ollama()
        assert result is None

    def test_not_running_calls_popen(self):
        import subprocess
        # First call: not running. Second call (poll): running.
        is_running_returns = [False, True]
        with (
            patch("agent.llm._is_running", side_effect=is_running_returns),
            patch("agent.llm.subprocess.Popen") as mock_popen,
            patch("agent.llm.time.sleep"),
        ):
            ensure_ollama()
        mock_popen.assert_called_once_with(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_not_running_popen_args_use_devnull(self):
        import subprocess
        is_running_returns = [False, True]
        with (
            patch("agent.llm._is_running", side_effect=is_running_returns),
            patch("agent.llm.subprocess.Popen") as mock_popen,
            patch("agent.llm.time.sleep"),
        ):
            ensure_ollama()
        _, kwargs = mock_popen.call_args
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL

    def test_polls_until_running(self):
        # Loop: sleep(1) THEN check _is_running each iteration.
        # initial check=False → Popen → poll loop:
        #   iter 0: sleep, check=False
        #   iter 1: sleep, check=False
        #   iter 2: sleep, check=True → return
        # Total: 3 sleeps, _is_running called 4 times (1 initial + 3 polls).
        is_running_sides = [False, False, False, True]
        with (
            patch("agent.llm._is_running", side_effect=is_running_sides),
            patch("agent.llm.subprocess.Popen"),
            patch("agent.llm.time.sleep") as mock_sleep,
        ):
            ensure_ollama()
        assert mock_sleep.call_count == 3

    def test_raises_runtime_error_if_never_starts(self):
        # First call: not running. All 15 poll calls: still not running.
        is_running_sides = [False] + [False] * 15
        with (
            patch("agent.llm._is_running", side_effect=is_running_sides),
            patch("agent.llm.subprocess.Popen"),
            patch("agent.llm.time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="15 seconds"):
                ensure_ollama()

    def test_sleeps_between_polls(self):
        is_running_sides = [False] + [False] * 15
        with (
            patch("agent.llm._is_running", side_effect=is_running_sides),
            patch("agent.llm.subprocess.Popen"),
            patch("agent.llm.time.sleep") as mock_sleep,
        ):
            with pytest.raises(RuntimeError):
                ensure_ollama()
        # 15 iterations → 15 sleeps of 1 second each
        assert mock_sleep.call_count == 15
        mock_sleep.assert_called_with(1)


# ── TestBestModel ─────────────────────────────────────────────────────────────

class TestBestModel:
    def test_returns_primary_when_found(self):
        resp = _tags_response([PRIMARY_MODEL, FALLBACK_MODEL, "other:7b"])
        with patch("agent.llm.urllib.request.urlopen", return_value=resp):
            assert _best_model() == PRIMARY_MODEL

    def test_returns_fallback_when_primary_missing(self):
        resp = _tags_response([FALLBACK_MODEL, "other:7b"])
        with patch("agent.llm.urllib.request.urlopen", return_value=resp):
            assert _best_model() == FALLBACK_MODEL

    def test_returns_any_available_when_both_missing(self):
        available = "some-model:latest"
        resp = _tags_response([available])
        with patch("agent.llm.urllib.request.urlopen", return_value=resp):
            result = _best_model()
        assert result == available

    def test_returns_primary_on_urlopen_exception(self):
        with patch(
            "agent.llm.urllib.request.urlopen",
            side_effect=OSError("connection refused"),
        ):
            assert _best_model() == PRIMARY_MODEL

    def test_returns_primary_on_json_decode_error(self):
        bad_resp = MagicMock()
        bad_resp.read.return_value = b"not-json"
        with patch("agent.llm.urllib.request.urlopen", return_value=bad_resp):
            assert _best_model() == PRIMARY_MODEL

    def test_returns_primary_when_models_list_empty(self):
        resp = _tags_response([])
        with patch("agent.llm.urllib.request.urlopen", return_value=resp):
            # No models available — falls through to return PRIMARY_MODEL
            assert _best_model() == PRIMARY_MODEL


# ── TestChat ──────────────────────────────────────────────────────────────────

class TestChat:
    def test_raises_runtime_error_when_not_running(self):
        with patch("agent.llm._is_running", return_value=False):
            with pytest.raises(RuntimeError, match="not running"):
                chat("hello")

    def test_returns_content_from_response(self):
        chat_body = {"message": {"content": "Ollama reply here"}}
        fake_resp = _make_response(chat_body)
        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch("agent.llm.urllib.request.urlopen", return_value=fake_resp),
        ):
            result = chat("What is 2+2?")
        assert result == "Ollama reply here"

    def test_system_prompt_added_as_first_message(self):
        chat_body = {"message": {"content": "ok"}}
        fake_resp = _make_response(chat_body)
        captured_request = {}

        def fake_urlopen(req, timeout=None):
            captured_request["body"] = json.loads(req.data)
            return fake_resp

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch("agent.llm.urllib.request.urlopen", fake_urlopen),
        ):
            chat("user message", system_prompt="be concise")

        messages = captured_request["body"]["messages"]
        assert messages[0] == {"role": "system", "content": "be concise"}
        assert messages[1] == {"role": "user", "content": "user message"}

    def test_no_system_prompt_omits_system_message(self):
        chat_body = {"message": {"content": "ok"}}
        fake_resp = _make_response(chat_body)
        captured_request = {}

        def fake_urlopen(req, timeout=None):
            captured_request["body"] = json.loads(req.data)
            return fake_resp

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch("agent.llm.urllib.request.urlopen", fake_urlopen),
        ):
            chat("just user")

        messages = captured_request["body"]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_expect_json_true_adds_format_key(self):
        chat_body = {"message": {"content": "{}"}}
        fake_resp = _make_response(chat_body)
        captured_request = {}

        def fake_urlopen(req, timeout=None):
            captured_request["body"] = json.loads(req.data)
            return fake_resp

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch("agent.llm.urllib.request.urlopen", fake_urlopen),
        ):
            chat("give me json", expect_json=True)

        assert captured_request["body"]["format"] == "json"

    def test_expect_json_false_omits_format_key(self):
        chat_body = {"message": {"content": "plain text"}}
        fake_resp = _make_response(chat_body)
        captured_request = {}

        def fake_urlopen(req, timeout=None):
            captured_request["body"] = json.loads(req.data)
            return fake_resp

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch("agent.llm.urllib.request.urlopen", fake_urlopen),
        ):
            chat("give me text", expect_json=False)

        assert "format" not in captured_request["body"]

    def test_uses_provided_model_over_best_model(self):
        chat_body = {"message": {"content": "ok"}}
        fake_resp = _make_response(chat_body)
        captured_request = {}

        def fake_urlopen(req, timeout=None):
            captured_request["body"] = json.loads(req.data)
            return fake_resp

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model") as mock_best,
            patch("agent.llm.urllib.request.urlopen", fake_urlopen),
        ):
            chat("hello", model="llama3:8b")

        assert captured_request["body"]["model"] == "llama3:8b"
        mock_best.assert_not_called()

    def test_calls_best_model_when_model_not_provided(self):
        chat_body = {"message": {"content": "ok"}}
        fake_resp = _make_response(chat_body)

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value="chosen:model") as mock_best,
            patch("agent.llm.urllib.request.urlopen", return_value=fake_resp),
        ):
            chat("hello")

        mock_best.assert_called_once()

    def test_raises_runtime_error_on_url_error(self):
        import urllib.error
        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch(
                "agent.llm.urllib.request.urlopen",
                side_effect=urllib.error.URLError("timeout"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Ollama request failed"):
                chat("hello")

    def test_stream_is_false_in_payload(self):
        chat_body = {"message": {"content": "ok"}}
        fake_resp = _make_response(chat_body)
        captured_request = {}

        def fake_urlopen(req, timeout=None):
            captured_request["body"] = json.loads(req.data)
            return fake_resp

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch("agent.llm.urllib.request.urlopen", fake_urlopen),
        ):
            chat("hello")

        assert captured_request["body"]["stream"] is False

    def test_posts_to_correct_endpoint(self):
        chat_body = {"message": {"content": "ok"}}
        fake_resp = _make_response(chat_body)
        captured_urls = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return fake_resp

        with (
            patch("agent.llm._is_running", return_value=True),
            patch("agent.llm._best_model", return_value=PRIMARY_MODEL),
            patch("agent.llm.urllib.request.urlopen", fake_urlopen),
        ):
            chat("hello")

        assert captured_urls[0] == f"{OLLAMA_BASE}/api/chat"
